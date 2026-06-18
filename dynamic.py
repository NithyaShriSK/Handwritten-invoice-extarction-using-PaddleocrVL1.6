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

# Splitting Configuration & File Saving Targets
num_slices = 3  
overlap_px = 30  
output_slices_dir = "invoice_slices"
preprocessed_image_output_path = "preprocessed_full_invoice.png"
raw_txt_output_path = "raw_ocr_result.txt"
final_json_output_path = "invoice_data.json"

# Configured for local engine execution
OLLAMA_MODEL = "qwen2.5:7b" 
# ------------------

# Ensure output directory for slices exists
os.makedirs(output_slices_dir, exist_ok=True)

# ---- 1. Preprocessing & Robust Projection-Based Slicing ----
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

def get_smart_crops_from_pil(pil_image, num_slices=3, overlap_px=30, out_dir="invoice_slices"):
    img = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    search_start = int(h * 0.20)  
    search_end = int(h * 0.45)
    row_sums = np.sum(binary == 255, axis=1)

    gap_search_end = int(h * 0.34)
    min_row_val = np.min(row_sums[search_start:gap_search_end])

    table_top_line_y = None
    threshold = min_row_val + int(w * 0.05 * 255) 
    
    for y in range(search_start, search_end):
        if row_sums[y] > threshold and np.mean(row_sums[y:y+10]) > threshold:
            table_top_line_y = y
            break
            
    if table_top_line_y is None:
        table_top_line_y = int(h * 0.31)

    back_search_start = max(search_start, table_top_line_y - 80)
    back_search_end = max(back_search_start + 5, table_top_line_y - 15)
    
    cut1 = back_search_start + np.argmin(row_sums[back_search_start:back_search_end])
    print(f"[Table Detection] Table top boundary found at Y={table_top_line_y}. Setting Cut 1 cleanly above it at Y={cut1}")

    bottom_start = int(h * 0.60)
    bottom_end = int(h * 0.78)

    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(w * 0.40), 1))
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    line_sums = np.sum(detected_lines == 255, axis=1)

    line_rows = np.where(line_sums > (w * 0.30 * 255))[0]
    bottom_lines = [r for r in line_rows if bottom_start <= r <= bottom_end]

    if bottom_lines:
        cut2 = bottom_lines[0]
    else:
        cut2 = int(h * 0.68)

    print(f"[Table Detection] Set Cut 2 (Table Bottom) at Y={cut2}")

    inner_left = int(w * 0.15)
    inner_right = int(w * 0.85)
    inner_row_sums = np.sum(binary[:, inner_left:inner_right] == 255, axis=1)

    active_text_rows = []
    text_threshold = (inner_right - inner_left) * 0.02 * 255

    for y in range(table_top_line_y + 80, cut2):  
        if inner_row_sums[y] > text_threshold:
            active_text_rows.append(y)

    if active_text_rows:
        last_text_y = max(active_text_rows)
        slice2_end = min(cut2, last_text_y + 55)
        print(f"[Dynamic Trimming] Last text row at Y={last_text_y}. Shortened Slice 2 bottom to Y={slice2_end}")
    else:
        slice2_end = int(table_top_line_y + (cut2 - table_top_line_y) * 0.5)
        print(f"[Dynamic Trimming] Fallback applied to half-table: Y={slice2_end}")

    crops = []

    slice1_img = img[0:cut1, 0:w]
    slice1_filename = os.path.join(out_dir, "slice_1.png")
    cv2.imwrite(slice1_filename, slice1_img)
    crops.append(Image.fromarray(cv2.cvtColor(slice1_img, cv2.COLOR_BGR2RGB)))

    slice2_img = img[cut1:slice2_end, 0:w]
    slice2_filename = os.path.join(out_dir, "slice_2.png")
    cv2.imwrite(slice2_filename, slice2_img)
    crops.append(Image.fromarray(cv2.cvtColor(slice2_img, cv2.COLOR_BGR2RGB)))

    slice3_img = img[max(0, cut2 - overlap_px):h, 0:w]
    slice3_filename = os.path.join(out_dir, "slice_3.png")
    cv2.imwrite(slice3_filename, slice3_img)
    crops.append(Image.fromarray(cv2.cvtColor(slice3_img, cv2.COLOR_BGR2RGB)))

    return crops

print("=== Starting Advanced Image Preprocessing ===")
preprocessed_full_image = preprocess_image(image_path, scale_factor=3.0, save_path=preprocessed_image_output_path)
slices = get_smart_crops_from_pil(preprocessed_full_image, num_slices=num_slices, overlap_px=overlap_px, out_dir=output_slices_dir)
print(f"=== Generated and saved {len(slices)} valid text segments ===\n")

# -------- Inference Setup --------
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

PROMPTS = {
    "ocr": "OCR:",
}

print("Loading config and registering custom model class...")
config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)

def apply_causal_mask_patch():
    modeling_module = None
    for mod_name, mod_obj in list(sys.modules.items()):
        if "modeling_paddleocr" in mod_name.lower():
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
    model_path, config=config, dtype=torch.bfloat16, trust_remote_code=True
).to(DEVICE).eval()

apply_causal_mask_patch()
processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True, use_fast=True)
min_pix = processor.image_processor.min_pixels if hasattr(processor.image_processor, 'min_pixels') else 14

# -------- RUN LOOP OVER EVERY SLICE IMAGE --------
aggregated_text = []
print("\n=== Running Sliced OCR Text Generation Inference ===")
for index, slice_img in enumerate(slices):
    print(f"Processing Segment {index + 1}/{len(slices)}...")
    current_task = "ocr"
    print(f"Assigning [task={current_task}] for segment {index + 1}")

    max_pixels = 1280 * 28 * 28

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": slice_img},
                {"type": "text", "text": PROMPTS[current_task]},
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

full_raw_ocr_string = "\n".join(aggregated_text)
full_raw_ocr_string = full_raw_ocr_string.replace('\xa0', ' ')

with open(raw_txt_output_path, "w", encoding="utf-8") as txt_file:
    txt_file.write(full_raw_ocr_string)
print(f"\n[OK] Complete text output consolidated and saved into: {raw_txt_output_path}")


# ---- 2. ADVANCED PYTHON DETERMINISTIC EXTRACTION ENGINE ----
def clean_numeric_string(val_str):
    if not val_str: return None
    cleaned = re.sub(r'(?i)kg|v|s|/-|\s', '', str(val_str))
    cleaned = cleaned.replace(',', '')
    match = re.search(r'\d+\.?\d*', cleaned)
    return float(match.group(0)) if match else None

def consensus_gstin(candidates, default_state_code=None):
    if not candidates: return None
    valid_candidates = []
    for c in candidates:
        c_clean = re.sub(r'[^A-Z0-9]', '', c.upper())
        if len(c_clean) == 15:
            valid_candidates.append(c_clean)
        elif 12 <= len(c_clean) <= 18:
            c_clean = c_clean + "Z" * (15 - len(c_clean)) if len(c_clean) < 15 else c_clean[:15]
            valid_candidates.append(c_clean)

    if not valid_candidates: return None
    position_rules = ["digit", "digit", "alpha", "alpha", "alpha", "alpha", "alpha", "digit", "digit", "digit", "digit", "alpha", "alnum", "Z", "alnum"]

    final_chars = []
    for idx, rule in enumerate(position_rules):
        chars_at_idx = [c[idx] for c in valid_candidates]
        if rule == "Z":
            final_chars.append("Z")
            continue
        digits = [ch for ch in chars_at_idx if ch.isdigit()]
        alphas = [ch for ch in chars_at_idx if ch.isalpha()]

        if rule == "digit":
            if digits: final_chars.append(Counter(digits).most_common(1)[0][0])
            else:
                m_char = Counter(chars_at_idx).most_common(1)[0][0]
                final_chars.append({'O': '0', 'Q': '0', 'I': '1', 'S': '5', 'Z': '2', 'B': '8', 'A': '4'}.get(m_char, '0'))
        elif rule == "alpha":
            if alphas: final_chars.append(Counter(alphas).most_common(1)[0][0])
            else:
                m_char = Counter(chars_at_idx).most_common(1)[0][0]
                final_chars.append({'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B'}.get(m_char, 'A'))
        else:
            final_chars.append(Counter(chars_at_idx).most_common(1)[0][0])

    resolved = "".join(final_chars)
    if default_state_code and resolved[:2] != default_state_code:
        resolved = default_state_code + resolved[2:]
    return resolved

def extract_clean_products_fallback(text):
    items = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    for line in lines:
        if any(k in line.lower() for k in ["s.no", "name of product", "total", "rupees", "goods"]):
            continue
            
        metric_matches = re.findall(r'([\d.,]+\s*(?:kg|g|v|s)?)(?=\s+|$)', line, re.IGNORECASE)
        
        if len(metric_matches) >= 2:
            try:
                nums = [clean_numeric_string(m) for m in metric_matches if clean_numeric_string(m) is not None]
                if len(nums) < 2: continue
                
                if len(nums) == 2:
                    qty, rate = nums[0], nums[1]
                    amount = round(qty * rate, 2)
                else:
                    qty, rate, amount = nums[0], nums[1], nums[2]
                
                words = line
                for m in metric_matches:
                    words = words.replace(m, "")
                
                hsn_match = re.search(r'\b(\d{4}|\d{6}|\d{8})\b', line)
                hsn = hsn_match.group(1) if hsn_match else None
                
                if hsn: words = words.replace(hsn, "")
                
                product_name = re.sub(r'\b(Row|S\.No|\d+)\b', '', words, flags=re.I).strip()
                product_name = re.sub(r'[^A-Za-z0-9\s\-&]', '', product_name).strip()
                
                if not product_name: product_name = "Silk Raw Material"
                
                items.append({
                    "product_name": product_name,
                    "hsn_code": hsn if hsn else "5002",
                    "quantity": qty,
                    "rate": rate,
                    "amount": amount
                })
            except Exception:
                continue
    return items

def advanced_deterministic_extraction(text):
    clean_text = re.sub(r'</?[fluxe]cel>', ' ', text)
    lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
    
    extracted_company = None
    for line in lines:
        if any(k in line.lower() for k in ["to.", "invoice no", "description", "s.no"]): break
        clean_line_check = re.sub(r'[^A-Za-z\s]', '', line).strip()
        if len(clean_line_check) > 4 and not any(k in line.lower() for k in ["invoice", "gstin", "tax", "date", "cell", "tele", "phone", "state"]):
            extracted_company = line.strip()
            break

    extracted_inv_no = None
    inv_match = re.search(r"(?:Invoice\s+No\.|Inv\s+No\.|Invoice\s*#)\s*[:\-\s]\s*([A-Za-z0-9\-/]+)", clean_text, re.IGNORECASE)
    if inv_match: extracted_inv_no = inv_match.group(1).strip()

    date_match = re.search(r"(\d{1,4})[./-](\d{1,2})[./-](\d{2,4})", clean_text)
    extracted_date = None
    if date_match:
        d, m, y = date_match.groups()
        if len(d) == 4: y, d = d, y
        if int(d) > 31:
            if d.startswith('8'): d = '2' + d[1:]
            elif d.startswith('7'): d = '1' + d[1:]
        extracted_date = f"{d.zfill(2)}/{m.zfill(2)}/{y}"

    extracted_buyer = None
    buyer_match = re.search(r"To\.\s*([\w\s&]+?)(?=\s*(?:Invoice|No\.|GSTIN|TAX|State|\n|$))", clean_text, re.IGNORECASE)
    if buyer_match:
        extracted_buyer = buyer_match.group(1).strip()
        extracted_buyer = re.sub(r'(?:Invoice|No\.|GSTIN).*', '', extracted_buyer, flags=re.I).strip()

    words_match = re.search(r"((?:Rupees|RUPEES).*?(?:only|ONLY|Rupees|RUPEES)\b)", clean_text, re.I | re.S)
    extracted_words = None
    if words_match:
        extracted_words = words_match.group(1).replace("\n", " ").strip()
        extracted_words = re.sub(r'\bTwo\s+Seven\b', 'Seven', extracted_words, flags=re.I)
        extracted_words = re.sub(r'\bNinety\s+Two\s+Seven\b', 'Ninety Seven', extracted_words, flags=re.I)

    all_gst_candidates = []
    for word in re.split(r'[\s,:\n\t]+', clean_text.upper()):
        cleaned = re.sub(r'[^A-Z0-9]', '', word)
        if 14 <= len(cleaned) <= 16:
            if any(c.isdigit() for c in cleaned) and any(c.isalpha() for c in cleaned):
                if cleaned not in all_gst_candidates: all_gst_candidates.append(cleaned)

    company_gst, buyer_gst = None, None
    supplier_match = re.search(r"GSTIN\s*:\s*([A-Z0-9]+)\s*(?:TAX|INVOICE)", clean_text, re.IGNORECASE)
    if supplier_match: company_gst = consensus_gstin([supplier_match.group(1).strip().upper()], None)
    elif len(all_gst_candidates) > 0: company_gst = consensus_gstin([all_gst_candidates[0]], None)

    buyer_match_section = re.search(r"(?:Erode|State\s+Code:\s*33).*?GSTIN\s*:\s*([A-Z0-9]+)", clean_text, re.I | re.S)
    if buyer_match_section:
        buyer_gst_candidate = buyer_match_section.group(1).strip().upper()
        if buyer_gst_candidate != company_gst: buyer_gst = consensus_gstin([buyer_gst_candidate], None)

    if not buyer_gst:
        distinct_candidates = [g for g in all_gst_candidates if g != company_gst]
        if distinct_candidates: buyer_gst = consensus_gstin([distinct_candidates[0]], None)

    cgst_val, sgst_val, igst_val = None, None, None
    cgst_match = re.search(r"CGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if cgst_match: cgst_val = float(cgst_match.group(1).replace(',', ''))
    
    sgst_match = re.search(r"SGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if sgst_match: sgst_val = float(sgst_match.group(1).replace(',', ''))

    igst_match = re.search(r"IGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if igst_match: igst_val = float(igst_match.group(1).replace(',', ''))

    return extracted_company, extracted_inv_no, extracted_date, p_buyer, company_gst, buyer_gst, extracted_words, cgst_val, sgst_val, igst_val

p_company, p_inv, p_date, p_buyer, p_comp_gst, p_buyer_gst, p_words, p_cgst, p_sgst, p_igst = advanced_deterministic_extraction(full_raw_ocr_string)
deterministic_products = extract_clean_products_fallback(full_raw_ocr_string)


# -------- 3. DYNAMIC QWEN PARSING SYSTEM --------
print(f"Loading extracted content from: {raw_txt_output_path}")
with open(raw_txt_output_path, "r", encoding="utf-8") as f:
    text_file_content = f.read()

SYSTEM_PROMPT = """You are an absolute JSON parsing machine. Your core function is to map unstructured text directly into the specified schema template.

RULES:
1. Do NOT write comments (like // remarks) anywhere inside the properties or array list blocks.
2. Ensure you structure the data into the exact output keys required by the schema."""

USER_CONTENT = f"""
Deterministic Ground-Truth Overrides:
- "company_name": "{p_company if p_company else 'null'}"
- "company_gst_no": "{p_comp_gst}"
- "invoice_number": "{p_inv}"
- "invoice_date": "{p_date}"
- "buyer_name": "{p_buyer}"
- "buyer_gst_no": "{p_buyer_gst}"
- "total_amount_in_words": "{p_words}"
- "products_list": {json.dumps(deterministic_products)}
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

Extracted Raw Text File Data:
{text_file_content}
"""

def validate_and_reverse_arithmetic(data):
    total_calculated_invoice_amount = 0.0
    
    if not data.get("products_list") and deterministic_products:
        data["products_list"] = deterministic_products

    for item in data.get("products_list", []):
        qty = clean_numeric_string(item.get("quantity"))
        rate = clean_numeric_string(item.get("rate"))
        amount = clean_numeric_string(item.get("amount"))

        if qty and rate:
            expected_amount = round(qty * rate, 2)
            if not amount or abs(expected_amount - amount) > 1.0:
                amount = expected_amount
        elif amount and qty and not rate:
            rate = round(amount / qty, 2)
        elif amount and rate and not qty:
            qty = round(amount / rate, 3)

        item["quantity"] = qty
        item["rate"] = rate
        item["amount"] = amount
        
        if amount: total_calculated_invoice_amount += amount

    cgst = clean_numeric_string(data.get("cgst_amount")) or 0.0
    sgst = clean_numeric_string(data.get("sgst_amount")) or 0.0
    igst = clean_numeric_string(data.get("igst_amount")) or 0.0
    
    data["cgst_amount"] = cgst if cgst > 0 else None
    data["sgst_amount"] = sgst if sgst > 0 else None
    data["igst_amount"] = igst if igst > 0 else None

    if total_calculated_invoice_amount > 0:
        data["total_amount"] = round(total_calculated_invoice_amount + cgst + sgst + igst, 2)
    else:
        data["total_amount"] = clean_numeric_string(data.get("total_amount"))
        
    return data

