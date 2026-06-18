import sys
import os
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import torch
import json
import re
from collections import Counter
import ollama
from transformers import AutoConfig, AutoProcessor, AutoModel

# ---- Settings ----
model_path = "PaddlePaddle/PaddleOCR-VL-1.6"
image_path = "invoice.png"  # Swap this out dynamically for any invoice image file

# Use "table" mode to preserve multi-column structured text layouts
task = "table" 

# Splitting Configuration & File Saving Targets
output_slices_dir = "invoice_slices"
preprocessed_image_output_path = "preprocessed_full_invoice.png"
raw_txt_output_path = "raw_ocr_result.txt"
final_json_output_path = "invoice_data.json"

# Configured for local LLaMA 3 execution
OLLAMA_MODEL = "llama3" 
# ------------------

# Ensure output directory for slices exists
os.makedirs(output_slices_dir, exist_ok=True)

# ---- 1. Preprocessing & Smart Filter Slicing ----
def preprocess_image(image_path, scale_factor=3.0, save_path="preprocessed_full_invoice.png"):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")

    original_height, original_width = img.shape[:2]
    new_width = int(original_width * scale_factor)
    new_height = int(original_height * scale_factor)
    img_upscaled = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    print(f"[OK] Image upscaled to {new_width}x{new_height}")

    gray = cv2.cvtColor(img_upscaled, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=8, templateWindowSize=7, searchWindowSize=21)

    # Deskew
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

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    contrast_enhanced = clahe.apply(denoised)

    kernel = np.ones((1, 1), np.uint8)
    morphed = cv2.morphologyEx(contrast_enhanced, cv2.MORPH_CLOSE, kernel)

    # Convert to PIL for final visual sharpness enhancement
    pil_img = Image.fromarray(morphed).convert('L')
    pil_img = pil_img.filter(ImageFilter.SHARPEN)
    pil_img = ImageEnhance.Contrast(pil_img).enhance(1.3)
    pil_img = ImageEnhance.Brightness(pil_img).enhance(1.1)
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.5)

    pil_img.save(save_path)
    print(f"[Save] Saved high-resolution preprocessed invoice to: {save_path}")

    return pil_img

def get_smart_crops_from_pil(pil_image, out_dir="invoice_slices"):
    img = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    print(f"Image size for slicing: {w}x{h}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Threshold to find dark structures (lines)
    binary_lines = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)[1]

    # Detect horizontal lines across the invoice using a large horizontal kernel
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(w * 0.5), 1))
    detected_lines = cv2.morphologyEx(binary_lines, cv2.MORPH_OPEN, horizontal_kernel)
    
    # Extract row positions where horizontal lines exist
    line_rows = np.where(np.sum(detected_lines > 0, axis=1) > (w * 0.3))[0]

    # Group continuous line pixels together to find distinct single-line coordinates
    structural_cuts = []
    if len(line_rows) > 0:
        current_group = [line_rows[0]]
        for y in line_rows[1:]:
            if y - current_group[-1] <= 5:
                current_group.append(y)
            else:
                structural_cuts.append(int(np.median(current_group)))
                current_group = [y]
        structural_cuts.append(int(np.median(current_group)))

    # Filter cuts to make sure they aren't right at the very top or bottom edge
    structural_cuts = [c for c in structural_cuts if int(h * 0.1) < c < int(h * 0.9)]
    print(f"Detected structural table lines at Y-positions: {structural_cuts}")

    final_cuts = []
    target_slices = 3
    ideal_positions = [(h // target_slices) * i for i in range(1, target_slices)]

    # Map each target section break to the closest real table boundary line
    for ideal_y in ideal_positions:
        if len(structural_cuts) > 0:
            # Find the closest physical line to our ideal cut location
            closest_line = min(structural_cuts, key=lambda x: abs(x - ideal_y))
            # Only use it if it's within a reasonable distance (250px) of our target zone
            if abs(closest_line - ideal_y) < 250 and closest_line not in final_cuts:
                final_cuts.append(closest_line)
                continue
        
        # Absolute fallback if no physical line is nearby: use strict gap calculation
        final_cuts.append(ideal_y)

    final_cuts = sorted(list(set(final_cuts)))
    print(f"Final aligned text-safe slice positions: {final_cuts}")

    # Generate slices cleanly without duplicate overlaps
    boundaries = [0] + final_cuts + [h]
    crops = []

    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]

        crop = img[start:end, :]

        if crop.shape[0] < 40:
            continue

        filename = os.path.join(out_dir, f"slice_{i+1}.png")
        cv2.imwrite(filename, crop)
        print(f"[SAVE] {filename} with shape: {crop.shape}")

        crop_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        crops.append(crop_pil)

    return crops

print("=== Starting Advanced Image Preprocessing ===")
preprocessed_full_image = preprocess_image(image_path, scale_factor=3.0, save_path=preprocessed_image_output_path)
slices = get_smart_crops_from_pil(preprocessed_full_image, out_dir=output_slices_dir)
print(f"=== Generated and saved {len(slices)} valid text segments ===\n")

# Image resolution control for PaddleOCR-VL
max_pixels = 2048 * 2048

# -------- Inference Setup --------
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
PROMPTS = {
    "ocr": "OCR:",
    "table": "Table Recognition:",
    "formula": "Formula Recognition:",
    "chart": "Chart Recognition:",
    "spotting": "Spotting:",
    "seal": "Seal Recognition:",
}

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
                kwargs["input_embeds"] = kwargs.pop("inputs_embeds")
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

# -------- RUN LOOP OVER EVERY SLICE IMAGE --------
aggregated_text = []
print("\n=== Running Sliced OCR Text Generation Inference ===")
for index, slice_img in enumerate(slices):
    print(f"Processing Segment {index + 1}/{len(slices)}...")
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": slice_img},
                {"type": "text", "text": PROMPTS[task]},
            ]
        }
    ]

    inputs = processor.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt",
        images_kwargs={"size": {"shortest_edge": min_pix, "longest_edge": max_pixels}},
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=512, do_sample=True, temperature=0.01, top_p=0.1, repetition_penalty=1.05)

    slice_result = processor.decode(outputs[0][inputs["input_ids"].shape[-1]:-1], skip_special_tokens=True)
    aggregated_text.append(slice_result)

full_raw_ocr_string = "\n".join(aggregated_text)
with open(raw_txt_output_path, "w", encoding="utf-8") as txt_file:
    txt_file.write(full_raw_ocr_string)
print(f"\n[OK] Complete text output consolidated and saved into: {raw_txt_output_path}")


# ---- 2. ADVANCED PYTHON DETERMINISTIC EXTRACTION ENGINE ----
def consensus_gstin(candidates, default_state_code=None):
    if not candidates:
        return None
    valid_candidates = []
    for c in candidates:
        c_clean = re.sub(r'[^A-Z0-9]', '', c.upper())
        if len(c_clean) == 15:
            valid_candidates.append(c_clean)
        elif 12 <= len(c_clean) <= 18:
            if len(c_clean) < 15:
                c_clean = c_clean + "Z" * (15 - len(c_clean))
            else:
                c_clean = c_clean[:15]
            valid_candidates.append(c_clean)

    if not valid_candidates:
        return None

    position_rules = [
        "digit", "digit",
        "alpha", "alpha", "alpha", "alpha", "alpha",
        "digit", "digit", "digit", "digit",
        "alpha", "alnum", "Z", "alnum"
    ]

    final_chars = []
    for idx, rule in enumerate(position_rules):
        chars_at_idx = [c[idx] for c in valid_candidates]
        if rule == "Z":
            final_chars.append("Z")
            continue

        digits = [ch for ch in chars_at_idx if ch.isdigit()]
        alphas = [ch for ch in chars_at_idx if ch.isalpha()]

        if rule == "digit":
            if digits:
                final_chars.append(Counter(digits).most_common(1)[0][0])
            else:
                most_common_char = Counter(chars_at_idx).most_common(1)[0][0]
                swaps = {'O': '0', 'Q': '0', 'I': '1', 'S': '5', 'Z': '2', 'B': '8', 'A': '4'}
                final_chars.append(swaps.get(most_common_char, '0'))
        elif rule == "alpha":
            if alphas:
                final_chars.append(Counter(alphas).most_common(1)[0][0])
            else:
                most_common_char = Counter(chars_at_idx).most_common(1)[0][0]
                swaps = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B'}
                final_chars.append(swaps.get(most_common_char, 'A'))
        else:
            final_chars.append(Counter(chars_at_idx).most_common(1)[0][0])

    resolved = "".join(final_chars)
    if default_state_code and resolved[:2] != default_state_code:
        resolved = default_state_code + resolved[2:]
    return resolved

def advanced_deterministic_extraction(text):
    clean_text = re.sub(r'</?[fluxe]cel>', ' ', text)
    lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
    
    # Dynamic Search for Company Name
    extracted_company = None
    for line in lines:
        if any(k in line.lower() for k in ["to.", "invoice no", "description", "s.no"]):
            break
        clean_line_check = re.sub(r'[^A-Za-z\s]', '', line).strip()
        if len(clean_line_check) > 4 and not any(k in line.lower() for k in ["invoice", "gstin", "tax", "date", "cell", "tele", "phone", "state"]):
            extracted_company = line.strip()
            break

    # Invoice Details Extraction
    extracted_inv_no = None
    inv_match = re.search(r"(?:Invoice\s+No\.|Inv\s+No\.|Invoice\s*#)\s*[:\-\s]\s*([A-Za-z0-9\-/]+)", clean_text, re.IGNORECASE)
    if inv_match:
        extracted_inv_no = inv_match.group(1).strip()

    date_match = re.search(r"(\d{1,4})[./-](\d{1,2})[./-](\d{2,4})", clean_text)
    extracted_date = None
    if date_match:
        d, m, y = date_match.groups()
        if len(d) == 4:
            y, d = d, y
        extracted_date = f"{d.zfill(2)}/{m.zfill(2)}/{y}"

    # Bounded Lookahead for Buyer Name
    extracted_buyer = None
    buyer_match = re.search(r"To\.\s*([\w\s&]+?)(?=\s*(?:Invoice|No\.|GSTIN|TAX|State|\n|$))", clean_text, re.IGNORECASE)
    if buyer_match:
        extracted_buyer = buyer_match.group(1).strip()
        extracted_buyer = re.sub(r'(?:Invoice|No\.|GSTIN).*', '', extracted_buyer, flags=re.I).strip()

    # Amount in words matching
    words_match = re.search(r"((?:Rupees|RUPEES).*?(?:only|ONLY|Rupees|RUPEES)\b)", clean_text, re.I | re.S)
    extracted_words = None
    if words_match:
        extracted_words = words_match.group(1).replace("\n", " ").strip()

    # GST Numbers Collection Layer
    all_gst_candidates = []
    for word in re.split(r'[\s,:\n\t]+', clean_text.upper()):
        cleaned = re.sub(r'[^A-Z0-9]', '', word)
        if 14 <= len(cleaned) <= 16:
            if any(c.isdigit() for c in cleaned) and any(c.isalpha() for c in cleaned):
                if cleaned not in all_gst_candidates:
                    all_gst_candidates.append(cleaned)

    company_gst = None
    buyer_gst = None

    supplier_match = re.search(r"GSTIN\s*:\s*([A-Z0-9]+)\s*(?:TAX|INVOICE)", clean_text, re.IGNORECASE)
    if supplier_match:
        company_gst = consensus_gstin([supplier_match.group(1).strip().upper()], None)
    elif len(all_gst_candidates) > 0:
        company_gst = consensus_gstin([all_gst_candidates[0]], None)

    buyer_match_section = re.search(r"(?:Erode|State\s+Code:\s*33).*?GSTIN\s*:\s*([A-Z0-9]+)", clean_text, re.I | re.S)
    if buyer_match_section:
        buyer_gst_candidate = buyer_match_section.group(1).strip().upper()
        if buyer_gst_candidate != company_gst:
            buyer_gst = consensus_gstin([buyer_gst_candidate], None)

    if not buyer_gst:
        distinct_candidates = [g for g in all_gst_candidates if g != company_gst]
        if distinct_candidates:
            buyer_gst = consensus_gstin([distinct_candidates[0]], None)

    # Tax Subtotals Logic Engine (CGST, SGST, IGST Extraction)
    cgst_val, sgst_val, igst_val = None, None, None
    cgst_match = re.search(r"CGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if cgst_match: cgst_val = float(cgst_match.group(1).replace(',', ''))
    
    sgst_match = re.search(r"SGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if sgst_match: sgst_val = float(sgst_match.group(1).replace(',', ''))

    igst_match = re.search(r"IGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if igst_match: igst_val = float(igst_match.group(1).replace(',', ''))

    return extracted_company, extracted_inv_no, extracted_date, extracted_buyer, company_gst, buyer_gst, extracted_words, cgst_val, sgst_val, igst_val

p_company, p_inv, p_date, p_buyer, p_comp_gst, p_buyer_gst, p_words, p_cgst, p_sgst, p_igst = advanced_deterministic_extraction(full_raw_ocr_string)


# -------- 3. DYNAMIC LLAMA3 PARSING SYSTEM --------
print(f"\n=== Sending Consolidated Text to Ollama Model ({OLLAMA_MODEL}) ===")

llm_prompt = f"""
You are an advanced data extraction system. Your goal is to combine raw OCR text with verified key/value pairs to output clean JSON data.

Deterministic Ground-Truth Overrides:
- "company_name": "{p_company if p_company else 'null'}"
- "company_gst_no": "{p_comp_gst}"
- "invoice_number": "{p_inv}"
- "invoice_date": "{p_date}"
- "buyer_name": "{p_buyer}"
- "buyer_gst_no": "{p_buyer_gst if p_buyer_gst else 'null'}"
- "total_amount_in_words": "{p_words}"
- "cgst_amount": {p_cgst if p_cgst is not None else 'null'}
- "sgst_amount": {p_sgst if p_sgst is not None else 'null'}
- "igst_amount": {p_igst if p_igst is not None else 'null'}

Target JSON Schema Structure:
{{
  "company_name": "string or null",
  "company_gst_no": "string or null",
  "invoice_number": "string or null",
  "invoice_date": "string or null",
  "state_code": "string or null",
  "vehicle_number": "string or null",
  "transportation_mode": "string or null",
  "products_list": [
     {{
       "product_name": "string",
       "hsn_code": "string or null",
       "quantity": number or null,
       "rate": number or null,
       "amount": number or null
     }}
  ],
  "cgst_amount": number or null,
  "sgst_amount": number or null,
  "igst_amount": number or null,
  "total_amount": number or null,
  "buyer_name": "string or null",
  "buyer_gst_no": "string or null",
  "total_amount_in_words": "string or null"
}}

Strict Behavioral Rules:
1. FORCE FRESH LOOKUP: Do NOT recall, inherit, or reuse any data strings, identifiers, names, or values from previous examples or history chats. Look ONLY at the provided "Raw OCR Text Data" for this specific run.
2. ABSOLUTE FORBIDDEN VALUE: Never output the string "10DUSTR1050I5ZZ" under any circumstances unless it is written explicitly down inside the current Raw OCR Text Data block below. 
3. OVERRIDE EXCEPTION RULE: If "buyer_gst_no" above is "null", look at the buyer billing section in the current text below. Locate the 15-character string following the label "GSTIN:" (e.g., "33EANNK..."). Strip all inner whitespace gaps (e.g., turn "33EAZNK0812FLZR" or spaces into a solid block) and capture it.
4. If "company_name" is null or missing in the overrides, extract the legal business trading title displayed prominently at the absolute top of the text canvas (e.g. "NAGANNA RAAJAA SILK INDUSTRIES").
5. Convert values for all tax and itemized total breakdowns strictly to numbers (ints or floats). Remove any commas or trailing slashes ("/-") before saving.
6. Output ONLY valid JSON code. Do not wrap output in ```json or add summary notes.

Raw OCR Text Data:
{full_raw_ocr_string}
"""
def clean_and_normalize_digits(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
        
    s = str(val).upper().strip()
    swaps = {'O': '0', 'Q': '0', 'I': '1', 'L': '1', 'S': '5', 'Z': '2', 'B': '8'}
    for char, replacement in swaps.items():
        s = s.replace(char, replacement)
        
    cleaned = re.sub(r'[^0-9.]', '', s)
    if not cleaned:
        return None
        
    try:
        return float(cleaned) if '.' in cleaned else int(cleaned)
    except ValueError:
        return None

def process_minor_corrections(data):
    cleaned_products = []
    for item in data.get("products_list", []):
        if not isinstance(item, dict):
            continue
            
        prod_name = item.get("product_name")
        hsn_code = item.get("hsn_code")
        qty = clean_and_normalize_digits(item.get("quantity"))
        rate = clean_and_normalize_digits(item.get("rate"))
        amount = clean_and_normalize_digits(item.get("amount"))
        
        cleaned_products.append({
            "product_name": prod_name,
            "hsn_code": hsn_code,
            "quantity": qty,
            "rate": rate,
            "amount": amount
        })
        
    data["products_list"] = cleaned_products
    
    for field in ["cgst_amount", "sgst_amount", "igst_amount", "total_amount"]:
        if field in data:
            data[field] = clean_and_normalize_digits(data[field])
            
    return data

try:
    # UPDATED: Changed from ollama.generate to ollama.chat to ensure stable system constraint compliance on LLaMA 3
    response = ollama.chat(
        model=OLLAMA_MODEL, 
        messages=[{"role": "user", "content": llm_prompt}],
        options={"temperature": 0.0}
    )
    response_text = response['message']['content'].strip()
    
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    elif response_text.startswith("```"):
        response_text = response_text[3:]
        
    if response_text.endswith("```"):
        response_text = response_text[:-3]
        
    response_text = response_text.strip()
    parsed_json = json.loads(response_text)
    
    # Ground-Truth Overrides Injection
    if p_company: parsed_json["company_name"] = p_company
    if p_inv: parsed_json["invoice_number"] = p_inv
    if p_date: parsed_json["invoice_date"] = p_date
    if p_buyer: parsed_json["buyer_name"] = p_buyer
    if p_comp_gst: parsed_json["company_gst_no"] = p_comp_gst
    if p_buyer_gst: parsed_json["buyer_gst_no"] = p_buyer_gst
    if p_words: parsed_json["total_amount_in_words"] = p_words
    
    if p_cgst is not None: parsed_json["cgst_amount"] = p_cgst
    if p_sgst is not None: parsed_json["sgst_amount"] = p_sgst
    if p_igst is not None: parsed_json["igst_amount"] = p_igst

    if (not parsed_json.get("state_code") or parsed_json["state_code"] == "null") and parsed_json.get("company_gst_no"):
        parsed_json["state_code"] = parsed_json["company_gst_no"][:2]
        
    parsed_json = process_minor_corrections(parsed_json)
        
    with open(final_json_output_path, "w", encoding="utf-8") as json_file:
        json.dump(parsed_json, json_file, indent=2, ensure_ascii=False)
        
    print("\n=== FINAL PARSED STRUCTURED JSON RESULT ===")
    print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
    print(f"\n[SUCCESS] Document structural output safely compiled into: {final_json_output_path}")

except Exception as e:
    print(f"\n[LLM Error Parsing JSON]: {e}")
    print("Fallback raw LLM payload string:")
    print(response_text if 'response_text' in locals() else "No response generated.")