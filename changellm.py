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

    # Convert to PIL for final visual crispness enhancement
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


# ---- EXTRACTION ENGINE HELPER PASS (Dynamic Layout Anchoring) ----
def parse_anchored_fields(text):
    # 1. Flexible, dynamic pattern to extract any alphanumeric invoice reference token
    inv_match = re.search(r"(?:Invoice\s+No\.|Inv\s+No\.|Invoice\s*#)\s*:\s*([A-Za-z0-9\-/]+)", text, re.IGNORECASE)
    extracted_inv_no = inv_match.group(1) if inv_match else None

    # 2. Extract any and all tokens that visually resemble a 15-character structural identifier
    # Allowing minor length variation to capture noisy characters
    all_gstin_candidates = re.findall(r"\b[A-Z0-9]{14,16}\b", text.upper())
    
    # Filter candidate tokens to see if any match standard GST tokens natively
    clean_gstins = [g for g in all_gstin_candidates if re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z\d]{1}[Z\d]{1}[A-Z\d]{1}$", g)]
    
    # Assign the first found valid pattern as the potential seller token
    extracted_company_gst = clean_gstins[0] if clean_gstins else (all_gstin_candidates[0] if all_gstin_candidates else None)

    return extracted_inv_no, extracted_company_gst, all_gstin_candidates

anchored_invoice_no, anchored_company_gst, raw_gst_pool = parse_anchored_fields(full_raw_ocr_string)


# -------- 3. DYNAMIC QWEN LLM PARSING SYSTEM --------
print(f"\n=== Sending Consolidated Text to Ollama Model ({OLLAMA_MODEL}) ===")

llm_prompt = f"""
You are an advanced, hyper-precise data extraction engine specializing in correcting noisy and structure-collapsed OCR text from various document invoices. Your task is to process the Raw OCR text and generate a perfectly valid JSON output matching the target schema structure.

Strategic Validation & Data Correction Directives:
1. "company_name": Dynamically extract the primary supplier corporate identifier header printed at the top.
2. "company_gst_no": Review the raw text and locate the primary seller tax registration token. Cross-reference with: "{anchored_company_gst}". Ensure it follows the Indian GSTIN format rules.
3. "buyer_name": Locate the customer profile context designation field (usually preceded by "To", "Bill To", "Buyer", or "Consignee"). Do not confuse it with shipping destinations.
4. "invoice_number": Assign the extracted reference identifier. Use "{anchored_invoice_no}" if it was successfully captured, otherwise resolve it cleanly from the raw text layout.
5. "buyer_gst_no": Analyze all candidate tokens discovered in the layout: {raw_gst_pool}.
   - Identify the buyer tax string by picking out tokens that match or closely match the repeating candidate pattern distinct from the company's identifier.
   - Reconstruct and clean any OCR dropout characters inside this token to strictly conform to the 15-character Indian legal standard layout formula:
     * First 2 characters: Numeric State Code.
     * Next 10 characters: Alphanumeric PAN sequence (5 letters, 4 numbers, 1 letter). Correct common character drops like reading alpha 'Q' where a numeric digit should be.
     * Character 13: Entity type code (Alpha or Numeric).
     * Character 14: Must be the literal uppercase character 'Z'.
     * Character 15: Single trailing check digit token.
6. "invoice_date": Identify the billing timestamp. Check for impossible calendar artifacts caused by layout row flips (e.g., impossible days like "87") and intelligently fix them to match standard timeline formatting templates (DD/MM/YYYY).
7. "quantity": Clean up structural metric units. Strip away text labels like "kg", "pcs", or "box" to return a pure floating-point numeric representation.
8. "amount" / "total_amount": Strip away text line clutter, symbols, and currency punctuation noise paths like "/-" or commas. Convert to pure numeric data integers or floats.

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
- Output ONLY the clean raw parseable JSON string matching this specification format.
- Absolutely DO NOT include markdown formatting block wrappers (such as ```json), introductory sentences, or summary logs.
- If any key is missing entirely from the input text, map it as null.

Raw OCR Text Data:
{full_raw_ocr_string}
"""

try:
    response = ollama.generate(model=OLLAMA_MODEL, prompt=llm_prompt)
    response_text = response['response'].strip()
    
    # Strip away markdown code block wrappers if the LLM provided them anyway
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    response_text = response_text.strip()

    # Verify formatting accuracy by loading it
    parsed_json = json.loads(response_text)
    
    # Dynamic runtime fallback validation loop
    if not parsed_json.get("invoice_number") and anchored_invoice_no:
        parsed_json["invoice_number"] = anchored_invoice_no
    if not parsed_json.get("company_gst_no") and anchored_company_gst:
        parsed_json["company_gst_no"] = anchored_company_gst
        
    with open(final_json_output_path, "w", encoding="utf-8") as json_file:
        json.dump(parsed_json, json_file, indent=2, ensure_ascii=False)
        
    print("\n=== FINAL PARSED STRUCTURED JSON RESULT ===")
    print(json.dumps(parsed_json, indent=2, ensure_ascii=False))
    print(f"\n[SUCCESS] Document structural output safely compiled into: {final_json_output_path}")

except Exception as e:
    print(f"\n[LLM Error Parsing JSON]: {e}")
    print("Fallback raw LLM payload string:")
    print(response_text if 'response_text' in locals() else "No response generated.")