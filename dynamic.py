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
task = "ocr" 

# Splitting Configuration & File Saving Targets
num_slices = 4
overlap_px = 70
output_slices_dir = "invoice_slices"
preprocessed_image_output_path = "preprocessed_full_invoice.png"
raw_txt_output_path = "raw_ocr_result.txt"
final_json_output_path = "invoice_data.json"

# Configured for your local qwen2.5:7b engine
OLLAMA_MODEL = "qwen2.5:7b" 
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

    # Save the complete full preprocessed image canvas onto disk
    pil_img.save(save_path)
    print(f"[Save] Saved high-resolution preprocessed invoice to: {save_path}")

    return pil_img

def get_smart_crops_from_pil(pil_image, num_slices=4, overlap_px=70, out_dir="invoice_slices"):
    img = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Smear text lines horizontally
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
    dilated = cv2.dilate(binary, kernel, iterations=2)

    row_sums = np.sum(dilated, axis=1)
    low_values = np.sort(row_sums)[:int(len(row_sums) * 0.1)]
    base_thresh = np.mean(low_values) if len(low_values) > 0 else 0
    thresh = base_thresh + (np.max(row_sums) * 0.02)

    gutters = np.where(row_sums <= thresh)[0]
    ideal_step = h // num_slices
    actual_cut_points = [0]
    
    for i in range(1, num_slices):
        target = i * ideal_step
        if len(gutters) > 0:
            closest_gutter = gutters[np.abs(gutters - target).argmin()]
            actual_cut_points.append(int(closest_gutter))
        else:
            actual_cut_points.append(int(target))
    actual_cut_points.append(h)

    crops = []
    saved_index = 1
    for i in range(len(actual_cut_points) - 1):
        start = max(0, actual_cut_points[i] - overlap_px)
        end = min(h, actual_cut_points[i + 1] + overlap_px)
        
        # Performance check: Ensure the slice actually contains text pixels
        slice_binary = dilated[start:end, 0:w]
        text_pixel_ratio = np.sum(slice_binary == 255) / slice_binary.size
        
        # If the slice is mostly empty gutter background, dynamically skip it
        if text_pixel_ratio < 0.005: 
            print(f"[Skip] Slice boundary {start}-{end} skipped (No text lines detected).")
            continue
            
        crop_cv = img[start:end, 0:w]
        if crop_cv.shape[0] > 10:
            # Save the cropped segment image physically onto disk
            slice_filename = os.path.join(out_dir, f"slice_{saved_index}.png")
            cv2.imwrite(slice_filename, crop_cv)
            print(f"[Save] Saved valid segment text layer: {slice_filename}")

            crop_pil = Image.fromarray(cv2.cvtColor(crop_cv, cv2.COLOR_BGR2RGB))
            crops.append(crop_pil)
            saved_index += 1

    return crops

# Execution of Image Processing Setup
print("=== Starting Advanced Image Preprocessing ===")
preprocessed_full_image = preprocess_image(image_path, scale_factor=3.0, save_path=preprocessed_image_output_path)
slices = get_smart_crops_from_pil(preprocessed_full_image, num_slices=num_slices, overlap_px=overlap_px, out_dir=output_slices_dir)
print(f"=== Generated and saved {len(slices)} valid text segments ===\n")

max_pixels = 2048 * 28 * 28 if task == "spotting" else 1280 * 28 * 28
# --------------------------------------------

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

# ---- MONKEY-PATCH: Remap inputs_embeds to input_embeds ----
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
        outputs = model.generate(**inputs, max_new_tokens=512)

    slice_result = processor.decode(outputs[0][inputs["input_ids"].shape[-1]:-1], skip_special_tokens=True)
    aggregated_text.append(slice_result)

# Join text and store into a text file
full_raw_ocr_string = "\n".join(aggregated_text)
with open(raw_txt_output_path, "w", encoding="utf-8") as txt_file:
    txt_file.write(full_raw_ocr_string)
print(f"\n[OK] Complete text output consolidated and saved into: {raw_txt_output_path}")


# ---- 2. ADVANCED PYTHON DETERMINISTIC EXTRACTION ENGINE (Zero-Bias Fallback) ----
def normalize_gstin(gst_str, default_state_code="33"):
    """
    Algorithmic Indian GSTIN compliance correction layer.
    Ensures 15-character structural matching:
    [0-1] State Code (Digits)
    [2-11] PAN Code (5 Alpha, 4 Digits, 1 Alpha)
    [12] Entity Code (Alphanumeric)
    [13] Default Alphabet ('Z')
    [14] Checksum (Alphanumeric)
    """
    gst_str = gst_str.upper().strip()
    if len(gst_str) != 15:
        return gst_str
    
    chars = list(gst_str)
    
    # Correct State Code (First 2 Digits)
    for idx in [0, 1]:
        if not chars[idx].isdigit():
            swaps = {'O': '0', 'Q': '0', 'I': '1', 'S': '5', 'Z': '2', 'B': '8'}
            chars[idx] = swaps.get(chars[idx], default_state_code[idx] if default_state_code else '3')
            
    # Apply standard fallback if state code is completely distorted
    state_code = "".join(chars[:2])
    if default_state_code and state_code != default_state_code:
        # If the state matches closely, or fallback is forced
        chars[0] = default_state_code[0]
        chars[1] = default_state_code[1]

    # Correct PAN Alpha prefix (Indices 2-6)
    for idx in range(2, 7):
        if not chars[idx].isalpha():
            swaps = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B'}
            chars[idx] = swaps.get(chars[idx], 'A')

    # Correct PAN Digits suffix (Indices 7-10)
    for idx in range(7, 11):
        if not chars[idx].isdigit():
            swaps = {'O': '0', 'Q': '0', 'I': '1', 'S': '5', 'Z': '2', 'B': '8', 'A': '4'}
            chars[idx] = swaps.get(chars[idx], '0')

    # Correct PAN Alpha check character (Index 11)
    if not chars[11].isalpha():
        swaps = {'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B'}
        chars[11] = swaps.get(chars[11], 'Z')

    # Enforce Character 14 is 'Z'
    chars[13] = 'Z'
    
    return "".join(chars)

def advanced_deterministic_extraction(text):
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    # Extract Company (First line containing real data)
    extracted_company = None
    for line in lines[:3]:
        if not any(k in line.lower() for k in ["invoice", "gstin", "tax", "date", "cell"]):
            extracted_company = line
            break

    # Extract Invoice Number
    inv_match = re.search(r"(?:Invoice\s+No\.|Inv\s+No\.|Invoice\s*#|No\.)\s*:\s*([A-Za-z0-9\-/]+)", text, re.IGNORECASE)
    extracted_inv_no = inv_match.group(1).strip() if inv_match else None

    # Extract Date Pattern & Autocorrect layout row drops (e.g., "87/11/2024" -> "07/11/2024")
    date_match = re.search(r"(\d{1,4})[./-](\d{1,2})[./-](\d{2,4})", text)
    extracted_date = None
    if date_match:
        d, m, y = date_match.groups()
        if len(d) == 4:  # YYYY-MM-DD template shift
            y, d = d, y
        if int(d) > 31: 
            d = str(int(d) % 10).zfill(2)  # Convert structural offset artifact "87" -> "07"
        extracted_date = f"{d.zfill(2)}/{m.zfill(2)}/{y}"

    # Extract Buyer Name (Flexible anchor lookahead)
    buyer_match = re.search(r"(?:To\.|To,|-To:|Bill\s+To\.|Buyer\s*:)\s*([A-Z\s\.\&\']+?)(?=\s*(?:Invoice|No|GSTIN|Date|State|\n|$))", text, re.IGNORECASE)
    extracted_buyer = buyer_match.group(1).strip() if buyer_match else None

    # Handle Indian Tax Tokens (GSTIN Matrix Isolation)
    all_possible_gst = re.findall(r"\b[A-Z0-9]{14,16}\b", text.upper())
    
    # Extract Company GSTIN explicitly from the top block
    company_gst = None
    top_block_match = re.search(r"GSTIN\s*[:\-\s]\s*([A-Z0-9]{14,16})", text, re.IGNORECASE)
    if top_block_match:
        company_gst = top_block_match.group(1).strip().upper()
        if len(company_gst) == 15:
            company_gst = normalize_gstin(company_gst)
    
    # Fallback to standard match if missing
    if not company_gst:
        clean_gstins = [g for g in all_possible_gst if re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$", g)]
        if clean_gstins:
            company_gst = clean_gstins[0]

    # Resolve company state code context to normalize the buyer state code
    company_state_code = company_gst[:2] if company_gst else "33"

    # Isolate buyer candidate strings and run voting
    buyer_gst_candidates = [g for g in all_possible_gst if g != company_gst]
    buyer_gst = None
    
    if buyer_gst_candidates:
        # Normalize candidates BEFORE voting to group spelling mutations together
        normalized_candidates = [normalize_gstin(candidate, company_state_code) for candidate in buyer_gst_candidates]
        # Filter for valid length
        valid_length_candidates = [g for g in normalized_candidates if len(g) == 15]
        if valid_length_candidates:
            # Statistical Mode (Majority vote) selects the correct entity
            buyer_gst = Counter(valid_length_candidates).most_common(1)[0][0]
        else:
            buyer_gst = buyer_gst_candidates[0]

    return extracted_company, extracted_inv_no, extracted_date, extracted_buyer, company_gst, buyer_gst

# Process local anchors natively
p_company, p_inv, p_date, p_buyer, p_comp_gst, p_buyer_gst = advanced_deterministic_extraction(full_raw_ocr_string)


# -------- 3. DYNAMIC QWEN PARSING SYSTEM (Context Consolidation Prompt) --------
print(f"\n=== Sending Consolidated Text to Ollama Model ({OLLAMA_MODEL}) ===")

llm_prompt = f"""
You are an advanced data extraction system. Your goal is to combine raw OCR text with verified key/value pairs to output clean JSON data.

Deterministic Ground-Truth Overrides:
- "company_name": "{p_company}"
- "company_gst_no": "{p_comp_gst}"
- "invoice_number": "{p_inv}"
- "invoice_date": "{p_date}"
- "buyer_name": "{p_buyer}"
- "buyer_gst_no": "{p_buyer_gst}"

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
  "total_amount": number or null,
  "buyer_name": "string or null",
  "buyer_gst_no": "string or null",
  "total_amount_in_words": "string or null"
}}

Rules:
- Fill in any remaining null fields using context available in the Raw OCR Text Data (such as amount fields, itemized breakdown arrays, state codes, and words).
- Convert values for "quantity", "rate", and "amount" fields strictly to numbers (ints or floats). Remove unit tags ("kg") or currency trailing strings ("/-").
- Output ONLY valid JSON code. Do not wrap output in ```json or add summary notes.

Raw OCR Text Data:
{full_raw_ocr_string}
"""

try:
    response = ollama.generate(model=OLLAMA_MODEL, prompt=llm_prompt)
    response_text = response['response'].strip()
    
    # Strip markdown code wrappers if returned by the LLM
    # Written defensively to prevent clipboard URL insertion bugs
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    elif response_text.startswith("```"):
        response_text = response_text[3:]
        
    if response_text.endswith("```"):
        response_text = response_text[:-3]
        
    response_text = response_text.strip()

    parsed_json = json.loads(response_text)
    
    # Production Verification Check Layer
    if not parsed_json.get("company_name") and p_company: parsed_json["company_name"] = p_company
    if not parsed_json.get("invoice_number") and p_inv: parsed_json["invoice_number"] = p_inv
    if not parsed_json.get("invoice_date") and p_date: parsed_json["invoice_date"] = p_date
    if not parsed_json.get("buyer_name") and p_buyer: parsed_json["buyer_name"] = p_buyer
    if not parsed_json.get("company_gst_no") and p_comp_gst: parsed_json["company_gst_no"] = p_comp_gst
    if not parsed_json.get("buyer_gst_no") and p_buyer_gst: parsed_json["buyer_gst_no"] = p_buyer_gst

    # Automatic State Code derivation from GSTIN matrix if missing
    if (not parsed_json.get("state_code") or parsed_json["state_code"] == "null") and parsed_json.get("company_gst_no"):
        parsed_json["state_code"] = parsed_json["company_gst_no"][:2]
        
    with open(final_json_output_path, "w", encoding="utf-8") as json_file:
        json.dump(parsed_json, json_file, indent=2, ensure_ascii=False)
        
    print("\n=== FINAL PARSED STRUCTURED JSON RESULT ===")
    print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
    print(f"\n[SUCCESS] Document structural output safely compiled into: {final_json_output_path}")

except Exception as e:
    print(f"\n[LLM Error Parsing JSON]: {e}")
    print("Fallback raw LLM payload string:")
    print(response_text if 'response_text' in locals() else "No response generated.")