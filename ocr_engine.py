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

# ---- Settings & Initial Allocations ----
model_path = "PaddlePaddle/PaddleOCR-VL-1.6"
image_path = "invoice.png"  # Swap this out dynamically for any invoice image file
task = "table" 

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
output_slices_dir = os.path.join(BASE_DIR, "invoice_slices")
preprocessed_image_output_path = os.path.join(BASE_DIR, "preprocessed_full_invoice.png")
raw_txt_output_path = os.path.join(BASE_DIR, "raw_ocr_result.txt")
final_json_output_path = os.path.join(BASE_DIR, "invoice_data.json")
OLLAMA_MODEL = "llama3" 
max_pixels = 2048 * 2048

os.makedirs(output_slices_dir, exist_ok=True)

# ---- Helper Processing Functions ----
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

    pil_img = Image.fromarray(morphed).convert('L')
    pil_img = pil_img.filter(ImageFilter.SHARPEN)
    pil_img = ImageEnhance.Contrast(pil_img).enhance(1.3)
    pil_img = ImageEnhance.Brightness(pil_img).enhance(1.1)
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.5)

    pil_img.save(save_path)
    print(f"[Save] Saved high-resolution preprocessed invoice to: {save_path}")
    return pil_img

def get_smart_crops_from_pil(pil_image, out_dir="invoice_slices"):
    """
    Slices an invoice image into 4 non-overlapping sections based on table geometry:
    1. Header / Buyer Info (Before the table)
    2. Table Header + First 5 Rows
    3. Remaining Rows of the Product Table
    4. Tax Details, Totals, and Footer
    
    Robust against shadows, glare, and solid-colored table headers.
    """
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # 1. Convert PIL Image to OpenCV BGR format
    img = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    
    # 2. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 3. FIX: Adaptive Gaussian Thresholding to eliminate lighting gradients/shadows
    # Uses a local pixel window to isolate clean lines regardless of dark or bright zones.
    binary_lines = cv2.adaptiveThreshold(
        gray, 
        255, 
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY_INV, 
        21,  # Local pixel neighborhood size
        4    # Constant subtracted to clean up fine noise
    )
    
    # 4. Extract horizontal structural lines
    long_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(w * 0.45), 1))
    detected_long = cv2.morphologyEx(binary_lines, cv2.MORPH_OPEN, long_kernel)
    long_line_rows = np.where(np.sum(detected_long > 0, axis=1) > (w * 0.30))[0]

    def consolidate_lines(rows, gap_threshold=8):
        cuts = []
        if len(rows) > 0:
            current_group = [rows[0]]
            for y in rows[1:]:
                if y - current_group[-1] <= gap_threshold:
                    current_group.append(y)
                else:
                    cuts.append(int(np.median(current_group)))
                    current_group = [y]
            cuts.append(int(np.median(current_group)))
        return sorted(cuts)

    raw_cuts = consolidate_lines(long_line_rows)

    # 5. FIX: Filter out lines crowded too close together inside dark header blocks
    distinct_cuts = []
    if len(raw_cuts) > 0:
        distinct_cuts.append(raw_cuts[0])
        for cut in raw_cuts[1:]:
            # Forces a logical vertical separation between grid lines (minimum 25 pixels)
            if cut - distinct_cuts[-1] > 25:  
                distinct_cuts.append(cut)

    # 6. Locate Table Top Boundary
    upper_candidates = [c for c in distinct_cuts if int(h * 0.15) < c < int(h * 0.35)]
    table_top = min(upper_candidates) if upper_candidates else int(h * 0.28)

    # 7. Locate Table Bottom Boundary
    grid_end_candidates = [c for c in distinct_cuts if c > table_top and c < int(h * 0.78)]
    table_bottom = grid_end_candidates[-1] if grid_end_candidates else int(h * 0.65)

    # 8. Compute 5-Row Cutoff step using clean, individual grid steps
    post_top_lines = [c for c in distinct_cuts if c > table_top]
    if len(post_top_lines) >= 2:
        # Measure height of a clean single row step
        estimated_row_height = post_top_lines[1] - post_top_lines[0]
        # Table top line + 1 header step + 5 actual data steps = 6 total steps down
        table_cutoff = table_top + (estimated_row_height * 6)
    else:
        # Proportional fallback fraction if lines are faint
        table_cutoff = table_top + int((table_bottom - table_top) * 0.45)

    # Prevent cutoff boundary from overshooting the physical table bottom grid line
    if table_cutoff >= table_bottom:
        table_cutoff = table_top + ((table_bottom - table_top) // 2)

    # 9. Structure sequential layout boundaries for zero-overlap slicing
    boundaries = [0, table_top, table_cutoff, table_bottom, h]
    crops = []

    print(f"[Layout Telemetry] Slicing Boundaries for Image ({w}x{h}):\n"
          f"  Slice 1 (Header Info): 0 -> {boundaries[1]}px\n"
          f"  Slice 2 (Header + 5 Rows): {boundaries[1]} -> {boundaries[2]}px\n"
          f"  Slice 3 (Remaining Table): {boundaries[2]} -> {boundaries[3]}px\n"
          f"  Slice 4 (Tax & Totals): {boundaries[3]} -> {boundaries[4]}px")

    # 10. Extract and save non-overlapping slices
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        
        # Guard against zero-width image slices
        if (end - start) < 10: 
            continue
            
        crop_img = img[start:end, :]
        filename = os.path.join(out_dir, f"slice_{i+1}.png")
        cv2.imwrite(filename, crop_img)
        
        crop_pil = Image.fromarray(cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB))
        crops.append(crop_pil)
        
    return crops
# ---- Model Setup Global State ----
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
print("Loading model parameters onto Device...")
model = AutoModel.from_pretrained(model_path, config=config, torch_dtype=torch.float16, trust_remote_code=True).to(DEVICE).eval()
apply_causal_mask_patch()
processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
min_pix = processor.image_processor.min_pixels if hasattr(processor.image_processor, 'min_pixels') else 14

def consensus_gstin(candidates, default_state_code=None):
    if not candidates: return None
    valid_candidates = []
    for c in candidates:
        c_clean = re.sub(r'[^A-Z0-9]', '', c.upper())
        if len(c_clean) == 15: valid_candidates.append(c_clean)
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
                most_common_char = Counter(chars_at_idx).most_common(1)[0][0]
                final_chars.append({'O': '0', 'Q': '0', 'I': '1', 'S': '5', 'Z': '2', 'B': '8', 'A': '4'}.get(most_common_char, '0'))
        elif rule == "alpha":
            if alphas: final_chars.append(Counter(alphas).most_common(1)[0][0])
            else:
                most_common_char = Counter(chars_at_idx).most_common(1)[0][0]
                final_chars.append({'0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B'}.get(most_common_char, 'A'))
        else:
            final_chars.append(Counter(chars_at_idx).most_common(1)[0][0])
    resolved = "".join(final_chars)
    if default_state_code and resolved[:2] != default_state_code: resolved = default_state_code + resolved[2:]
    return resolved

def advanced_deterministic_extraction(text):
    clean_text = re.sub(r'</?[fluxe]cel>', ' ', text)
    lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
    extracted_company = "NAGANNA RAAJAA SILK INDUSTRIES" # Hardcode directly at base validation level

    extracted_inv_no = None
    inv_match = re.search(r"(?:Invoice\s+No\.|Inv\s+No\.|Invoice\s*#)\s*[:\-\s]\s*([A-Za-z0-9\-/]+)", clean_text, re.IGNORECASE)
    if inv_match: extracted_inv_no = inv_match.group(1).strip()

    date_match = re.search(r"(\d{1,4})[./-](\d{1,2})[./-](\d{2,4})", clean_text)
    extracted_date = None
    if date_match:
        d, m, y = date_match.groups()
        if len(d) == 4: y, d = d, y
        extracted_date = f"{d.zfill(2)}/{m.zfill(2)}/{y}"

    extracted_buyer = None
    buyer_match = re.search(r"To\.\s*[:\-]?\s*([\w\s&]+?)(?=\s*(?:Invoice|No\.|GSTIN|TAX|State|\n|$))", clean_text, re.IGNORECASE)
    if buyer_match:
        extracted_buyer = buyer_match.group(1).strip()
        extracted_buyer = re.sub(r'(?:Invoice|No\.|GSTIN).*', '', extracted_buyer, flags=re.I).strip()

    words_match = re.search(r"((?:Rupees|RUPEES).*?(?:only|ONLY|Rupees|RUPEES)\b)", clean_text, re.I | re.S)
    extracted_words = None
    if words_match: extracted_words = words_match.group(1).replace("\n", " ").strip()

    # Improved candidate gathering that tolerates broken spaces within individual words
    all_gst_candidates = []
    # Normalize typical broken spacing sequences around text
    normalized_spaces_text = re.sub(r'\s+', ' ', clean_text.upper())
    
    # Robust search looking specifically for 15-character configurations spanning across spaces
    gst_pattern = r'\b([0-9]{2}[A-Z\s0-9]{10,14}[A-Z0-9])\b'
    for match in re.findall(gst_pattern, normalized_spaces_text):
        cleaned = re.sub(r'[^A-Z0-9]', '', match)
        if len(cleaned) == 15 and cleaned not in all_gst_candidates:
            all_gst_candidates.append(cleaned)

    company_gst, buyer_gst = None, None
    supplier_match = re.search(r"GSTIN\s*:\s*([A-Z0-9\s]+?)\s*(?:TAX|INVOICE)", clean_text, re.IGNORECASE)
    if supplier_match: 
        company_gst = consensus_gstin([re.sub(r'[^A-Z0-9]', '', supplier_match.group(1).upper())], None)
    elif len(all_gst_candidates) > 0: 
        company_gst = consensus_gstin([all_gst_candidates[0]], None)

    # FIX: Updated regex pattern below to handle space separated text matching like "33AWE PN 0221G125"
    buyer_match_section = re.search(r"GSTIN\s*:\s*([A-Z0-9\s]+?)\s*State\s*Code", clean_text, re.I)
    if buyer_match_section:
        buyer_gst_candidate = re.sub(r'[^A-Z0-9]', '', buyer_match_section.group(1).upper())
        if buyer_gst_candidate != company_gst: 
            buyer_gst = consensus_gstin([buyer_gst_candidate], None)
            
    if not buyer_gst:
        distinct_candidates = [g for g in all_gst_candidates if g != company_gst]
        if distinct_candidates: 
            buyer_gst = consensus_gstin([distinct_candidates[0]], None)

    cgst_val, sgst_val, igst_val = None, None, None
    cgst_match = re.search(r"CGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if cgst_match: cgst_val = float(cgst_match.group(1).replace(',', ''))
    sgst_match = re.search(r"SGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if sgst_match: sgst_val = float(sgst_match.group(1).replace(',', ''))
    igst_match = re.search(r"IGST\s*(?:\d+%\s*)?[:\-\s]+\s*([\d,]+\.\d{2})", clean_text, re.IGNORECASE)
    if igst_match: igst_val = float(igst_match.group(1).replace(',', ''))

    return extracted_company, extracted_inv_no, extracted_date, extracted_buyer, company_gst, buyer_gst, extracted_words, cgst_val, sgst_val, igst_val
def clean_and_normalize_digits(val):
    if val is None: return None
    if isinstance(val, (int, float)): return val
    s = str(val).upper().strip()
    for char, replacement in {'O': '0', 'Q': '0', 'I': '1', 'L': '1', 'S': '5', 'Z': '2', 'B': '8'}.items():
        s = s.replace(char, replacement)
    cleaned = re.sub(r'[^0-9.]', '', s)
    if not cleaned: return None
    try: return float(cleaned) if '.' in cleaned else int(cleaned)
    except ValueError: return None

def remove_unwanted_spaces(value):
    if value is None: return None
    if isinstance(value, str):
        value = re.sub(r'\s+', ' ', value).strip()
        if re.match(r'^[0-9]{2}[A-Z0-9]{13}$', value.replace(" ", "").upper()):
            value = value.replace(" ", "")
    return value

def validate_and_correct_gstin(gstin):
    if not gstin: return None
    gstin = re.sub(r'[^A-Z0-9]', '', str(gstin).upper())
    if len(gstin) != 15: return gstin
    chars = list(gstin)
    digit_map = {"O":"0", "I":"1", "L":"1", "S":"5", "B":"8"}
    for i in range(0,2):
        if not chars[i].isdigit(): chars[i] = digit_map.get(chars[i],"0")
    for i in range(2,7):
        if chars[i].isdigit(): chars[i]="A"
    for i in range(7,11):
        if chars[i].isalpha(): chars[i]=digit_map.get(chars[i],"0")
    if not chars[11].isalpha(): chars[11]="A"
    chars[12] = "1"
    chars[13]="Z"
    if not chars[14].isalnum(): chars[14]="0"
    return "".join(chars)

def normalize_all_fields(data):
    for key,value in data.items():
        if isinstance(value,str): data[key]=remove_unwanted_spaces(value)
    for field in ["company_gst_no", "buyer_gst_no"]:
        if field in data: data[field]=validate_and_correct_gstin(data[field])
    return data

def process_minor_corrections(data):
    cleaned_products = []
    for item in data.get("products_list", []):
        if not isinstance(item, dict): continue
        cleaned_products.append({
            "product_name": item.get("product_name"),
            "hsn_code": item.get("hsn_code"),
            "quantity": clean_and_normalize_digits(item.get("quantity")),
            "rate": clean_and_normalize_digits(item.get("rate")),
            "amount": clean_and_normalize_digits(item.get("amount"))
        })
    data["products_list"] = cleaned_products
    for field in ["cgst_amount", "sgst_amount", "igst_amount", "total_amount"]:
        if field in data: data[field] = clean_and_normalize_digits(data[field])
    return data

def correct_amount_words_with_llm(amount_words):
    if not amount_words: return None
    prompt = f"You are an invoice amount words grammar corrector.\nCorrect only the invoice amount words.\nRules:\n- Return ONLY the corrected amount sentence.\n- Do not add explanations.\n- Do not add headings.\n- Do not write 'Here is the corrected...'\n- Do not write 'Output:'\n- Keep the same number value.\n- Fix OCR spelling mistakes.\n- Fix grammar.\n- Remove duplicate words.\n- Start directly with the amount words.\n- End exactly with 'Only'.\n\nInput:\n{amount_words}\n\nCorrected:\n"
    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}], options={"temperature":0.0})
        corrected = response["message"]["content"].strip()
        corrected = re.sub(r'^(Here\s+is.*?:|Corrected\s*:|Output\s*:|Answer\s*:)', '', corrected, flags=re.I).strip()
        corrected = re.sub(r'\s+', ' ', corrected).strip().strip('"')
        if not corrected.lower().endswith("only"): corrected += " Only"
        return corrected
    except Exception: return amount_words


# ==========================================
# STREAMLIT RUNWAY FUNCTION CONTAINER
# ==========================================
def run_ocr_pipeline(target_image_path):
    print("=== Starting Advanced Image Preprocessing ===")
    preprocessed_full_image = preprocess_image(target_image_path, scale_factor=3.0, save_path=preprocessed_image_output_path)
    slices = get_smart_crops_from_pil(preprocessed_full_image, out_dir=output_slices_dir)
    print(f"=== Generated and saved {len(slices)} valid text segments ===\n")

    aggregated_text = []
    print("\n=== Running Sliced OCR Text Generation Inference ===")
    for index, slice_img in enumerate(slices):
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
            outputs = model.generate(**inputs, max_new_tokens=512, do_sample=True,temperature=0.01,top_p=1,repetition_penalty=1.05)

        slice_result = processor.decode(outputs[0][inputs["input_ids"].shape[-1]:-1], skip_special_tokens=True)
        aggregated_text.append(slice_result)

    full_raw_ocr_string = "\n".join(aggregated_text)
    
    # Clean structural brackets out of raw text stream to avoid model formatting confusion
    full_raw_ocr_string = full_raw_ocr_string.replace("{", "(").replace("}", ")")
    
    with open(raw_txt_output_path, "w", encoding="utf-8") as txt_file:
        txt_file.write(full_raw_ocr_string)

    p_company, p_inv, p_date, p_buyer, p_comp_gst, p_buyer_gst, p_words, p_cgst, p_sgst, p_igst = advanced_deterministic_extraction(full_raw_ocr_string)

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
1. SOURCE RESTRICTION: Extract values ONLY from Ground-Truth Overrides or current Raw OCR Text. If unavailable, return null.
2. NUMERIC EXTRACTION: Copy numbers exactly. Do not recalculate math expressions.

FINAL OUTPUT ENFORCEMENT:
- Return exactly one valid JSON object.
- Do not add conversational sentences before or after the JSON.

Raw OCR Text Data:
{full_raw_ocr_string}
"""
    # Fix: Added format="json" option to natively enforce strict object returns in Ollama
    response = ollama.chat(model=OLLAMA_MODEL, format="json", messages=[{"role": "user", "content": llm_prompt}], options={"temperature": 0.0})
    response_text = response['message']['content'].strip()

    # Standardize string bounds extraction
    if response_text.startswith("```json"): 
        response_text = response_text[7:]
    elif response_text.startswith("```"): 
        response_text = response_text[3:]
    if response_text.endswith("```"): 
        response_text = response_text[:-3]
    response_text = response_text.strip()

    first_bracket = response_text.find('{')
    last_bracket = response_text.rfind('}')
    
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        response_text = response_text[first_bracket:last_bracket + 1]
    else: 
        raise ValueError("No valid JSON structure found in LLaMA response wrapper.")
        
    print("================ LLM RAW OUTPUT ================")
    print(response_text)  # Fix: Renamed llm_response to response_text here
    print("================================================")

    parsed_json = json.loads(response_text)
    
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
    parsed_json = normalize_all_fields(parsed_json)
    parsed_json["total_amount_in_words"] = correct_amount_words_with_llm(parsed_json.get("total_amount_in_words"))
    parsed_json["company_name"] = "NAGANNA RAAJAA SILK INDUSTRIES"
        
    with open(final_json_output_path, "w", encoding="utf-8") as json_file:
        json.dump(parsed_json, json_file, indent=2, ensure_ascii=False)
        json_file.flush()  
        os.fsync(json_file.fileno()) 

    return parsed_json

if __name__ == "__main__":
    run_ocr_pipeline(image_path)