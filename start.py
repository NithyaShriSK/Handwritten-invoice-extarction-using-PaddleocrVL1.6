import sys
import os
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import torch
import json
import re
import ollama
from transformers import AutoConfig, AutoProcessor, AutoModel

# ---- Settings ----
model_path = "PaddlePaddle/PaddleOCR-VL-1.6"
image_path = "invoice.png"  # Swap this out dynamically for any invoice image file

# Use "table" mode to preserve multi-column structured text layouts
task = "table" 

# File Saving Targets
preprocessed_image_output_path = "preprocessed_full_invoice.png"
raw_txt_output_path = "raw_ocr_result.txt"
final_json_output_path = "invoice_data.json"

# ---- CHANGED: Configured for local LLaMA 3 execution ----
OLLAMA_MODEL = "llama3"  # Standard 8B model. Use "llama3:70b" if running the larger variant.
# ------------------

# ---- 1. BASIC PREPROCESSING (NO DOWNSAMPLING / NO SLICING) ----
def preprocess_image(image_path, save_path="preprocessed_full_invoice.png"):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Remove background scanning noise while leaving the high-res text pixels crisp
    denoised = cv2.fastNlMeansDenoising(gray, None, h=6, templateWindowSize=7, searchWindowSize=21)

    # Deskew Layout Alignment
    coords = np.column_stack(np.where(denoised > 0))
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) > 0.5:
            (h, w) = denoised.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            denoised = cv2.warpAffine(denoised, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # Enhance table line contrast and low-light text exposure
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(12, 12))
    contrast_enhanced = clahe.apply(denoised)

    # Convert to PIL and apply native sharpness matrices
    pil_img = Image.fromarray(contrast_enhanced).convert('L')
    pil_img = pil_img.filter(ImageFilter.SHARPEN)
    pil_img = ImageEnhance.Contrast(pil_img).enhance(1.4)
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.3)

    pil_img.save(save_path)
    print(f"[Save] Saved baseline preprocessed invoice to: {save_path}")

    return pil_img

print("=== Starting Image Preprocessing ===")
preprocessed_full_image = preprocess_image(image_path, save_path=preprocessed_image_output_path)

# Image resolution boundaries control for PaddleOCR-VL (Uncapped context max sizing)
max_pixels = 32 * 1024 * 1024

# -------- Inference Setup --------
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
PROMPTS = {"table": "Table Recognition:"}

print("Loading config and registering custom model class...")
config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)

def apply_causal_mask_patch():
    modeling_module = None
    for mod_name, mod_obj in sys.modules.items():
        if "modeling_paddleocr_vl" in mod_name:
            modeling_module = mod_obj
            break
    if modeling_module is not None and not hasattr(modeling_module, "_patched"):
        original_create_causal_mask = modeling_module.create_causal_mask
        def patched_create_causal_mask(*args, **kwargs):
            if "inputs_embeds" in kwargs:
                kwargs["inputs_embeds"] = kwargs.pop("inputs_embeds")
            return original_create_causal_mask(*args, **kwargs)
        modeling_module.create_causal_mask = patched_create_causal_mask
        modeling_module._patched = True
        return True
    return False

apply_causal_mask_patch()

print("Loading model parameters onto GPU...")
model = AutoModel.from_pretrained(
    model_path, config=config, torch_dtype=torch.bfloat16, trust_remote_code=True
).to(DEVICE).eval()

apply_causal_mask_patch()
processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
min_pix = processor.image_processor.min_pixels if hasattr(processor.image_processor, 'min_pixels') else 14

# -------- SINGLE-SHOT FULL INVOICE INFERENCE --------
print("\n=== Running Unified OCR Text Generation Inference ===")

messages = [
    {
        "role": "user",
        "content": [
            {"type": "image", "image": preprocessed_full_image},
            {"type": "text", "text": PROMPTS[task]},
        ]
    }
]

inputs = processor.apply_chat_template(
    messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt",
    images_kwargs={"size": {"shortest_edge": min_pix, "longest_edge": max_pixels}},
).to(model.device)

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=2048,   # Boosted token cap to handle processing a full single-shot canvas response safely
        do_sample=False,       # Strict greedy decoding eliminates row column shifting
        repetition_penalty=1.05
    )

full_raw_ocr_string = processor.decode(outputs[0][inputs["input_ids"].shape[-1]:-1], skip_special_tokens=True)
print(f"[OK] Complete unified text output extracted.")

# ---- 2. ADVANCED TEXT NORMALIZATION LAYER ----
def clean_ocr_gstins(text):
    def close_gaps(match):
        return match.group(0).replace(" ", "")
    pattern = r'\b\d{2}\s*[A-Z]{5}\s*\d{4}\s*[A-Z]{1}\s*[A-Z0-9]{1}\s*[Z0-9]{1}\s*[A-Z0-9]{1}\b'
    return re.sub(pattern, close_gaps, text, flags=re.IGNORECASE)

normalized_ocr_string = clean_ocr_gstins(full_raw_ocr_string)
normalized_ocr_string = re.sub(r'(\d+),(\d+)\.(?!\d)', r'\1\2.0', normalized_ocr_string)

with open(raw_txt_output_path, "w", encoding="utf-8") as txt_file:
    txt_file.write(normalized_ocr_string)
print(f"[Save] Saved normalized baseline text output to: {raw_txt_output_path}")

# ---- 3. REGEX-BASED GROUNDING FALLBACK GENERATION ----
def extract_field_via_regex(pattern, text, default_value=None):
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else default_value

invoice_number = extract_field_via_regex(r'Invoice\s*No\s*.\s*:\s*(\d+)', normalized_ocr_string)
invoice_date = extract_field_via_regex(r'Invoice\s*Date\s*.\s*:\s*([\d/]+)', normalized_ocr_string)
state_code = extract_field_via_regex(r'State\s*Code\s*:\s*(\d+)', normalized_ocr_string)

raw_tokens = re.split(r'[\s,:\n\t]+', normalized_ocr_string.upper())
gst_candidates = []
for token in raw_tokens:
    cleaned = re.sub(r'[^A-Z0-9]', '', token)
    if len(cleaned) == 15 and cleaned.startswith("33"):
        if cleaned not in gst_candidates:
            gst_candidates.append(cleaned)

scouted_seller_gst = gst_candidates[0] if len(gst_candidates) > 0 else None
scouted_buyer_gst = gst_candidates[1] if len(gst_candidates) > 1 else None


# ---- 4. DETERMINISTIC OLLAMA JSON SEGREGATION ENGINE ----
print(f"\n=== Sending Unified Text Block to JSON Engine ({OLLAMA_MODEL}) ===")

llm_prompt = f"""
You are an expert Indian tax invoice document parser. Read this raw OCR text string and extract the details into a single valid JSON payload following the Target Schema precisely.

--- RAW OCR INPUT TEXT START ---
{normalized_ocr_string}
--- RAW OCR INPUT TEXT END ---

### Target JSON Schema:
{{
  "supplier_details": {{
    "company_name": "string or null",
    "address": "string or null",
    "contact_numbers": ["string"],
    "gstin": "string or null",
    "state_code": "string or null"
  }},
  "invoice_meta": {{
    "invoice_no": "string or null",
    "invoice_date": "string or null (DD/MM/YYYY)",
    "e_way_bill_no": "string or null",
    "transportation_mode": "string or null",
    "vehicle_no": "string or null"
  }},
  "buyer_details": {{
    "company_name": "string or null",
    "address": "string or null",
    "gstin": "string or null",
    "state_code": "string or null"
  }},
  "line_items": [
    {{
      "s_no": "integer or null",
      "product_name": "string or null",
      "hsn_code": "string or null",
      "quantity": "float or null",
      "rate": "float or null",
      "amount": "float or null"
    }}
  ],
  "financial_summary": {{
    "total_amount_before_tax": "float or null",
    "cgst_percentage": "float or null",
    "cgst_amount": "float or null",
    "sgst_percentage": "float or null",
    "sgst_amount": "float or null",
    "igst_percentage": "float or null",
    "igst_amount": "float or null",
    "total_tax_amount": "float or null",
    "grand_total": "float or null"
  }},
  "bank_details": {{
    "account_name": "string or null",
    "account_no": "string or null",
    "bank_name": "string or null",
    "ifsc_code": "string or null",
    "branch": "string or null"
  }},
  "additional_info": {{
    "notes": "string or null",
    "declaration": "string or null"
  }}
}}

Return ONLY valid raw JSON syntax. Do not write text greetings or markdown block wraps.
"""

try:
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": llm_prompt}],
        format="json",
        options={
            "temperature": 0.0,
            # ---- CHANGED: Expanded context allocation for LLaMA 3 tokenization weights ----
            "num_predict": 8192
        }
    )
    
    if 'message' in response and 'content' in response['message']:
        response_text = response['message']['content'].strip()
    else:
        response_text = response['response'].strip()
        
    extracted_json = json.loads(response_text)

    # ---- 5. DYNAMIC RECONSTRUCTION CONSOLIDATOR ----
    final_structured_invoice = {
        "seller_name": extracted_json.get("supplier_details", {}).get("company_name") or "Unknown Seller",
        "seller_gst_no": extracted_json.get("supplier_details", {}).get("gstin") or scouted_seller_gst,
        "invoice_number": extracted_json.get("invoice_meta", {}).get("invoice_no") or invoice_number,
        "invoice_date": extracted_json.get("invoice_meta", {}).get("invoice_date") or invoice_date,
        "state_code": extracted_json.get("supplier_details", {}).get("state_code") or state_code,
        "transportation_mode": extracted_json.get("invoice_meta", {}).get("transportation_mode"),
        "buyer_name": extracted_json.get("buyer_details", {}).get("company_name") or "Unknown Buyer",
        "buyer_gst_no": extracted_json.get("buyer_details", {}).get("gstin") or scouted_buyer_gst,
        "product_details": extracted_json.get("line_items", []),
        "cgst": extracted_json.get("financial_summary", {}).get("cgst_amount"),
        "sgst": extracted_json.get("financial_summary", {}).get("sgst_amount"),
        "igst": extracted_json.get("financial_summary", {}).get("igst_amount"),
        "total_amount": extracted_json.get("financial_summary", {}).get("grand_total"),
        "bank_details": extracted_json.get("bank_details", {})
    }

    with open(final_json_output_path, "w", encoding="utf-8") as json_file:
        json.dump(final_structured_invoice, json_file, indent=2, ensure_ascii=False)
        
    print("\n=== FINAL PARSED STRUCTURED JSON RESULT ===")
    print(json.dumps(final_structured_invoice, indent=2, ensure_ascii=False))
    print(f"\n[SUCCESS] Document parsed successfully: {final_json_output_path}")

except Exception as e:
    print(f"\n[Execution error compiling structural JSON]: {e}")