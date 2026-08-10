import os
import sys
import re
import json
import base64
import cv2
import numpy as np
from PIL import Image
from datetime import datetime, date
from dotenv import load_dotenv
from pymongo import MongoClient
from openai import OpenAI

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -------------------------------------------------------------
# 1. API KEY & CLIENT INITIALIZATION
# -------------------------------------------------------------
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("Configuration Error: OPENAI_API_KEY environment variable is not configured. Please set it in your .env file.")

base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
client = OpenAI(api_key=api_key, base_url=base_url)

# Default setting fallbacks
DEFAULT_SETTINGS = {
    "gpt4o_invoice_extraction": True,
    "organization_memory": True,
    "human_feedback_learning": True,
    "confidence_based_learning": True,
    "invoice_validation_engine": True,
    "fraud_detection_engine": True,
}

# Safe JSON Encoder to prevent serialization crashes on MongoDB date/ObjectID fields
class SafeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat() + "Z"
        try:
            from bson import ObjectId
            if isinstance(obj, ObjectId):
                return str(obj)
        except ImportError:
            pass
        return super().default(obj)

def _get_db():
    try:
        mongo_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "invoice_ocr")
        mc = MongoClient(mongo_uri)
        return mc[db_name]
    except Exception:
        return None

def _get_settings():
    db = _get_db()
    if db is None:
        return dict(DEFAULT_SETTINGS)
    try:
        settings = db["ap_settings"].find_one()
        return settings if settings else dict(DEFAULT_SETTINGS)
    except Exception:
        return dict(DEFAULT_SETTINGS)

# ==========================================
# 2. IMAGE PREPROCESSING & SLICING FUNCTIONS
# ==========================================

def preprocess_image(image_path, save_path):
    """
    Applies grayscale, contrast enhancement (CLAHE).
    Saves and returns the path to the preprocessed image.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found at: {image_path}")
    
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    
    # 1. Convert to Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Adaptive Contrast Enhancement (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    
    # 3. Save Preprocessed Image
    cv2.imwrite(save_path, enhanced)
    print(f"[Saved] Preprocessed image: {save_path}")
    return save_path


def slice_image_regions(image_path, output_folder, regions=None):
    """
    Crops specified regions of an image and saves them to disk.
    Regions can be percentages (0.0 to 1.0) of [ymin, xmin, ymax, xmax].
    """
    pil_img = Image.open(image_path)
    width, height = pil_img.size

    if regions is None:
        regions = {
            "header_vendor_info": (0.0, 0.0, 0.32, 1.0),
            "products_table": (0.30, 0.0, 0.75, 1.0),
            "tax_and_totals": (0.72, 0.0, 1.0, 1.0)
        }

    saved_slices = {}
    for name, (ymin, xmin, ymax, xmax) in regions.items():
        box = (
            int(xmin * width),
            int(ymin * height),
            int(xmax * width),
            int(ymax * height)
        )
        cropped_img = pil_img.crop(box)
        slice_path = os.path.join(output_folder, f"{name}.png")
        cropped_img.save(slice_path)
        saved_slices[name] = slice_path
        print(f"[Saved] Sliced region '{name}': {slice_path}")

    return saved_slices


def encode_image_to_base64(image_path):
    """Encodes local image to base64 data URL string."""
    with open(image_path, "rb") as f:
        encoded_string = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded_string}"


# ==========================================
# 3. PYTHON-SIDE DETERMINISTIC CLEANUP
# ==========================================

DIGIT_MAP = {}
LETTER_MAP = {}


def clean_invoice_number(val):
    if val is None or isinstance(val, (int, float)):
        return val
    val_str = str(val).strip()
    mapped = "".join(DIGIT_MAP.get(char, char) for char in val_str.upper())
    cleaned = re.sub(r"[^0-9]", "", mapped)
    return cleaned if cleaned else val_str


def clean_numeric_value(val):
    if val is None or isinstance(val, (int, float)):
        return val

    val_str = str(val).strip()
    match = re.match(r"^([\dOQDIL\|SBZG.,]+)\s*([A-Za-z]+)?$", val_str, re.IGNORECASE)
    if not match:
        cleaned = re.sub(r"[^0-9.]", "", val_str)
        try:
            return float(cleaned) if "." in cleaned else int(cleaned)
        except ValueError:
            return val_str

    num_part, unit_part = match.groups()
    cleaned_num = "".join(DIGIT_MAP.get(char, char) for char in num_part.upper())
    cleaned_num = re.sub(r"[^0-9.]", "", cleaned_num)

    try:
        num_final = float(cleaned_num) if "." in cleaned_num else int(cleaned_num)
        return f"{num_final} {unit_part}".strip() if unit_part else num_final
    except ValueError:
        return val_str


def validate_gstin(gstin):
    if not gstin or not isinstance(gstin, str):
        return None

    gstin = re.sub(r"[^A-Z0-9]", "", gstin.upper())

    if len(gstin) != 15:
        return None

    return gstin


# ==========================================
# 4. SAVE TXT & JSON REPRESENTATION
# ==========================================

def save_page_txt_representation(data, file_obj, page_num):
    """
    Writes a clean, formatted text file of the extracted fields for auditing/review to a file object.
    """
    file_obj.write(f"INVOICE EXTRACTION REPORT - PAGE {page_num}\n")
    file_obj.write("=" * 50 + "\n")
    file_obj.write(f"Company Name:          {data.get('company_name') or 'N/A'}\n")
    file_obj.write(f"Company GSTIN:         {data.get('company_gst_no') or 'N/A'}\n")
    file_obj.write(f"Invoice Number:        {data.get('invoice_number') or 'N/A'}\n")
    file_obj.write(f"Invoice Date:          {data.get('invoice_date') or 'N/A'}\n")
    file_obj.write(f"State Code:            {data.get('state_code') or 'N/A'}\n")
    file_obj.write(f"Vehicle Number:        {data.get('vehicle_number') or 'N/A'}\n")
    file_obj.write(f"Transportation Mode:   {data.get('transportation_mode') or 'N/A'}\n")
    file_obj.write(f"Buyer Name:            {data.get('buyer_name') or 'N/A'}\n")
    file_obj.write(f"Buyer GSTIN:           {data.get('buyer_gst_no') or 'N/A'}\n")
    file_obj.write(f"Purchase Order Number: {data.get('purchase_order_number') or 'N/A'}\n")
    file_obj.write("-" * 50 + "\n")
    file_obj.write("PRODUCTS LIST:\n")
    
    products = data.get("products_list") or []
    if isinstance(products, list):
        for idx, p in enumerate(products):
            file_obj.write(f"  {idx + 1}. Product: {p.get('product_name') or 'N/A'}\n")
            file_obj.write(f"     HSN Code: {p.get('hsn_code') or 'N/A'} | Qty: {p.get('quantity') or 0} | Rate: {p.get('rate') or 0} | Amount: {p.get('amount') or 0}\n")
    else:
        file_obj.write("  No products found.\n")
        
    file_obj.write("-" * 50 + "\n")
    file_obj.write(f"CGST Amount:           {data.get('cgst_amount') or 0}\n")
    file_obj.write(f"SGST Amount:           {data.get('sgst_amount') or 0}\n")
    file_obj.write(f"IGST Amount:           {data.get('igst_amount') or 0}\n")
    file_obj.write(f"Total Amount:          {data.get('total_amount') or 0}\n")
    file_obj.write(f"Total Amount in Words: {data.get('total_amount_in_words') or 'N/A'}\n")
    file_obj.write(f"Bank Account No:       {data.get('bank_account_no') or 'N/A'}\n")
    file_obj.write(f"Bank IFSC:             {data.get('bank_ifsc') or 'N/A'}\n")
    file_obj.write(f"Bank Name:             {data.get('bank_name') or 'N/A'}\n")
    file_obj.write("=" * 50 + "\n")

def save_page_txt_to_file(data, txt_path, page_num):
    with open(txt_path, "w", encoding="utf-8") as f:
        save_page_txt_representation(data, f, page_num)


# ==========================================
# 5. MULTI-PAGE PDF CONVERSION UTILITY
# ==========================================

def convert_pdf_to_images(pdf_path, temp_folder, dpi=150):
    """
    Renders PDF pages into temporary PNG files using PyMuPDF (fitz).
    Returns list of page image paths.
    """
    import fitz  # PyMuPDF
    print(f"[PDF] Opening document: {pdf_path} (DPI: {dpi})")
    doc = fitz.open(pdf_path)
    page_images = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=dpi)
        img_filename = os.path.join(temp_folder, f"page_{page_num + 1}.png")
        pix.save(img_filename)
        page_images.append(img_filename)
        print(f"[PDF] Converted Page {page_num + 1} -> {img_filename}")
        
    return page_images


# ==========================================
# ==========================================
# 6. CORE EXTRACTION ROUTE
# ==========================================

def cleanup_old_temp_files(temp_dir_parent, age_seconds=3600):
    """
    Deletes subdirectories inside temp_dir_parent that are older than age_seconds.
    """
    if not os.path.exists(temp_dir_parent):
        return
    import shutil
    import time
    now = time.time()
    for item in os.listdir(temp_dir_parent):
        item_path = os.path.join(temp_dir_parent, item)
        if os.path.isdir(item_path):
            try:
                mtime = os.path.getmtime(item_path)
                if now - mtime > age_seconds:
                    shutil.rmtree(item_path)
                    print(f"[Cleanup] Deleted old temp folder: {item_path}")
            except Exception as e:
                print(f"[Cleanup Warning] Failed to delete {item_path}: {e}")


def verify_invoice_with_gpt(image_path, extracted_data):
    base64_image = encode_image_to_base64(image_path)

    verification_prompt = f"""
You are a second-pass invoice verification system.

The invoice image is provided below.

The first extraction produced this JSON:

{json.dumps(extracted_data, indent=2, ensure_ascii=False)}

Your task is to independently re-check EVERY field against the actual
invoice image.

For every field:

1. Look at the original handwriting.
2. Compare difficult characters with handwriting elsewhere on the invoice.
3. Check numbers character-by-character.
4. Check product names carefully.
5. Check quantity, rate and amount separately.
6. Check GSTIN character-by-character.
7. Check invoice number character-by-character.
8. Check bank account and IFSC character-by-character.
9. Do not guess unreadable information.
10. Do not change a value unless the image provides evidence.
11. Do not modify values simply to make mathematical calculations work.
12. Check total_amount carefully: it MUST represent the grand total (final payable amount at the bottom of the invoice, inclusive of all taxes like CGST, SGST, IGST, round-offs, etc.), NOT the taxable subtotal of the products.

If the first extraction is correct, keep it unchanged.

Return ONLY the corrected JSON using exactly the same structure.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """
You are a highly accurate handwritten invoice verification system.
Accuracy is more important than completeness.
Never guess unreadable characters.
"""
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": verification_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": base64_image
                        }
                    }
                ]
            }
        ]
    )

    return json.loads(
        response.choices[0].message.content.strip()
    )


def validate_invoice_math(data):
    products = data.get("products_list", [])

    for product in products:
        quantity = product.get("quantity")
        rate = product.get("rate")
        amount = product.get("amount")

        q_num = None
        r_num = None
        a_num = None

        if isinstance(quantity, (int, float)):
            q_num = quantity
        elif isinstance(quantity, str):
            try:
                q_num = float(quantity.split()[0].replace(",", ""))
            except (ValueError, IndexError):
                pass

        if isinstance(rate, (int, float)):
            r_num = rate
        elif isinstance(rate, str):
            try:
                r_num = float(rate.split()[0].replace(",", ""))
            except (ValueError, IndexError):
                pass

        if isinstance(amount, (int, float)):
            a_num = amount
        elif isinstance(amount, str):
            try:
                a_num = float(amount.split()[0].replace(",", ""))
            except (ValueError, IndexError):
                pass

        if q_num is not None and r_num is not None and a_num is not None:
            expected = q_num * r_num
            if abs(expected - a_num) > 0.01:
                product["_calculation_warning"] = True

    return data


def validate_totals(data):
    total = data.get("total_amount")
    cgst = data.get("cgst_amount") or 0
    sgst = data.get("sgst_amount") or 0
    igst = data.get("igst_amount") or 0

    def parse_to_float(v):
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                cleaned = re.sub(r"[^0-9.]", "", v)
                return float(cleaned) if cleaned else 0.0
            except ValueError:
                return 0.0
        return 0.0

    total_num = parse_to_float(total)
    cgst_num = parse_to_float(cgst)
    sgst_num = parse_to_float(sgst)
    igst_num = parse_to_float(igst)

    products = data.get("products_list", [])
    product_total = 0.0

    for p in products:
        amount = p.get("amount")
        amount_num = parse_to_float(amount)
        product_total += amount_num

    data["_validation"] = {
        "product_total": product_total,
        "tax_total": cgst_num + sgst_num + igst_num,
        "extracted_total": total_num
    }

    return data


def run_ocr_pipeline(target_file_path, supplier_profiles=None):
    """
    Core pipeline entry point.
    Determines file type (Image/PDF), processes page visual OCR, runs deterministic cleanups,
    saves page-specific JSON/TXT files, and returns page-by-page structured results.
    """
    # Run automatic cleanup of temporary folders older than 1 hour
    cleanup_old_temp_files(os.path.join(UPLOAD_FOLDER, "temp"), age_seconds=3600)

    settings = _get_settings()
    filename_base = os.path.basename(target_file_path).rsplit(".", 1)[0]
    ext = target_file_path.lower().split(".")[-1]
    
    # 1. Create main output folder under uploads/output/<filename_base>
    output_base_dir = os.path.join(UPLOAD_FOLDER, "output", filename_base)
    os.makedirs(output_base_dir, exist_ok=True)
    
    # Create subdirectories for preprocessed and sliced images
    preprocessed_dir = os.path.join(output_base_dir, "preprocessed_images")
    sliced_dir = os.path.join(output_base_dir, "sliced_images")
    os.makedirs(preprocessed_dir, exist_ok=True)
    os.makedirs(sliced_dir, exist_ok=True)
    
    # Create temp folder for fitz PDF-to-image conversion
    temp_folder = os.path.join(UPLOAD_FOLDER, "temp", filename_base)
    os.makedirs(temp_folder, exist_ok=True)
    
    is_pdf = target_file_path.lower().endswith(".pdf")
    image_paths_to_process = []
    
    # Read environment configurations
    try:
        max_pdf_pages = int(os.environ.get("MAX_PDF_PAGES", "15"))
    except ValueError:
        max_pdf_pages = 15
        
    try:
        pdf_render_dpi = int(os.environ.get("PDF_RENDER_DPI", "150"))
    except ValueError:
        pdf_render_dpi = 150
    
    if is_pdf:
        # Strict pre-validation: check page count before any rendering/conversion
        import fitz
        try:
            doc = fitz.open(target_file_path)
            if doc.is_encrypted:
                doc.close()
                raise ValueError("PDF file is password-protected.")
            page_count = len(doc)
            doc.close()
        except Exception as e:
            if "password-protected" in str(e):
                raise e
            raise ValueError(f"Invalid or corrupted PDF file: {str(e)}")
            
        if page_count > max_pdf_pages:
            raise ValueError(f"PDF contains {page_count} pages. The maximum allowed is {max_pdf_pages} pages.")
            
        try:
            image_paths_to_process = convert_pdf_to_images(target_file_path, temp_folder, dpi=pdf_render_dpi)
        except Exception as pdf_err:
            print(f"[ERROR] PDF page conversion failed: {pdf_err}")
            raise ValueError(f"Failed to process PDF pages: {str(pdf_err)}")
    else:
        image_paths_to_process = [target_file_path]
        
    pages_results = []
    combined_txt_lines = []
    combined_json_data = {}
    
    for idx, raw_image in enumerate(image_paths_to_process):
        print(f"\n--- Processing Page {idx + 1}/{len(image_paths_to_process)} ---")
        
        page_num = idx + 1
        page_name = f"page{page_num}"
        
        # Save preprocessed image named like page1.png, page2.png
        preprocessed_path = os.path.join(preprocessed_dir, f"{page_name}.png")
        
        # Step 2.1: Preprocess CLAHE Contrast
        preprocess_image(raw_image, preprocessed_path)
        
        # Step 2.2: Slice sections to uploads/output/<filename>/sliced_images/page{X}
        page_sliced_dir = os.path.join(sliced_dir, page_name)
        os.makedirs(page_sliced_dir, exist_ok=True)
        
        custom_slices = {
            "header_vendor_info": (0.0, 0.0, 0.32, 1.0),
            "products_table": (0.30, 0.0, 0.75, 1.0),
            "tax_and_totals": (0.72, 0.0, 1.0, 1.0)
        }
        slice_image_regions(preprocessed_path, page_sliced_dir, custom_slices)
        
        # Base64 encode the crops to pass to GPT
        header_slice_path = os.path.join(page_sliced_dir, "header_vendor_info.png")
        products_slice_path = os.path.join(page_sliced_dir, "products_table.png")
        totals_slice_path = os.path.join(page_sliced_dir, "tax_and_totals.png")
        
        base64_header = encode_image_to_base64(header_slice_path)
        base64_products = encode_image_to_base64(products_slice_path)
        base64_totals = encode_image_to_base64(totals_slice_path)
        
        # Step 2.3: Encode base64 data URL (Pass 1 uses the original raw image)
        base64_image = encode_image_to_base64(raw_image)
        
        # Step 2.4: Call GPT Vision completion
        model_name = os.environ.get("OPENAI_MODEL", "gpt-4o")
        print(f"[GPT-4o OCR] Sending visual API request to {base_url}/chat/completions (model: {model_name})...")
        
        system_prompt = """
You are an expert handwritten invoice document extraction system.

Your primary goal is HIGH ACCURACY.

Carefully inspect the invoice image before extracting any information.

IMPORTANT RULES:

1. Extract information directly from the image.
2. This invoice may contain handwritten text.
3. Carefully inspect individual handwritten characters.
4. Compare difficult characters with other characters written by the
   same person elsewhere in the invoice.
5. Do NOT guess unreadable characters.
6. Do NOT invent missing characters.
7. If a value cannot be reliably determined from the image, return null.
8. Do NOT modify a value just because another value appears more likely.
9. Preserve names and product names as they appear.
10. Preserve invoice numbers exactly as written.
11. Preserve GSTIN characters exactly as visually observed.
12. Preserve bank account numbers exactly as visually observed.
13. Preserve IFSC codes exactly as visually observed.
14. Preserve quantities, rates and amounts carefully.
15. Preserve decimal points.
16. Preserve units such as KG, PCS, ML, LTR, etc.
17. Keep every product row separate.
18. Carefully distinguish quantity, rate and amount.
19. Re-check every extracted field against the image before returning.
20. Never "fix" handwriting merely to make the invoice mathematically correct.

Pay special attention to commonly confused handwritten characters:

0 / O
1 / I / L
2 / Z
5 / S
6 / G
8 / B

Only choose between ambiguous characters when the visual evidence supports
the choice.

Return ONLY valid JSON.
"""

        user_prompt_text = """
Extract the following information from the invoice image.

Return exactly this JSON structure:

{
    "company_name": null,
    "company_gst_no": null,
    "invoice_number": null,
    "invoice_date": null,
    "state_code": null,
    "vehicle_number": null,
    "transportation_mode": null,
    "buyer_name": null,
    "buyer_gst_no": null,
    "purchase_order_number": null,

    "products_list": [
        {
            "product_name": null,
            "hsn_code": null,
            "quantity": null,
            "rate": null,
            "amount": null
        }
    ],

    "cgst_amount": null,
    "sgst_amount": null,
    "igst_amount": null,
    "total_amount": null,
    "total_amount_in_words": null,

    "bank_account_no": null,
    "bank_ifsc": null,
    "bank_name": null
}

EXTRACTION REQUIREMENTS:

- Read the complete invoice before answering.
- Carefully inspect handwritten text.
- Preserve the exact visible spelling of names.
- Preserve invoice numbers exactly.
- Preserve GSTIN exactly as written.
- Preserve bank account numbers exactly.
- Preserve IFSC exactly as written.
- Preserve product names exactly as visible.
- Preserve quantity, rate and amount separately.
- Preserve decimal values.
- Preserve units.
- total_amount MUST represent the grand total (final payable amount at the bottom of the invoice, inclusive of all taxes like CGST, SGST, IGST, round-offs, etc.), NOT the taxable subtotal of the products.
- Do not invent values.
- If a value is genuinely unreadable, return null.
- Do not use surrounding business knowledge to invent missing information.
- Do not change a number simply because another number would make the
  arithmetic work.

For total_amount_in_words:
- Transcribe what is visible.
- Do not generate it from total_amount if handwriting is unclear.

Before returning the JSON, perform a second visual check of every field.
"""
        
        if supplier_profiles and settings.get("organization_memory", True):
            system_prompt += f"\n\n[ORGANIZATION MEMORY] Known Supplier Profiles:\n{json.dumps(supplier_profiles, indent=2, cls=SafeJSONEncoder)}\n"
            system_prompt += "If the supplier matches one of these profiles, verify your layout extraction rules using the registered numbering schemes, typical rates, or bank details."
            
        try:
            response = client.chat.completions.create(
                model=model_name,
                temperature=0.0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt_text},
                            {"type": "image_url", "image_url": {"url": base64_image}},
                            {"type": "image_url", "image_url": {"url": base64_header}},
                            {"type": "image_url", "image_url": {"url": base64_products}},
                            {"type": "image_url", "image_url": {"url": base64_totals}}
                        ]
                    }
                ]
            )
            
            page_data = json.loads(
                response.choices[0].message.content.strip()
            )
            
            # SECOND PASS VERIFICATION (using preprocessed enhanced image)
            page_data = verify_invoice_with_gpt(
                preprocessed_path,
                page_data
            )
            
            # Step 2.5: Apply page-specific cleanups
            if page_data.get("invoice_number"):
                page_data["invoice_number"] = clean_invoice_number(page_data["invoice_number"])
            if page_data.get("company_gst_no"):
                page_data["company_gst_no"] = validate_gstin(page_data["company_gst_no"])
            if page_data.get("buyer_gst_no"):
                page_data["buyer_gst_no"] = validate_gstin(page_data["buyer_gst_no"])

            if not page_data.get("state_code") and page_data.get("company_gst_no"):
                gst_str = str(page_data["company_gst_no"])
                if len(gst_str) >= 2 and gst_str[:2].isdigit():
                    page_data["state_code"] = gst_str[:2]

            for key in ["cgst_amount", "sgst_amount", "igst_amount", "total_amount"]:
                if key in page_data:
                    page_data[key] = clean_numeric_value(page_data[key])

            if "products_list" in page_data and isinstance(page_data["products_list"], list):
                for item in page_data["products_list"]:
                    item["quantity"] = clean_numeric_value(item.get("quantity"))
                    item["rate"] = clean_numeric_value(item.get("rate"))
                    item["amount"] = clean_numeric_value(item.get("amount"))
            
            # Apply mathematical and total validations (detected warnings, not auto-correcting values)
            page_data = validate_invoice_math(page_data)
            page_data = validate_totals(page_data)
            
            # Compile page-level text representation in string buffer
            from io import StringIO
            string_buffer = StringIO()
            save_page_txt_representation(page_data, string_buffer, page_num)
            page_txt_content = string_buffer.getvalue().strip()
            combined_txt_lines.append(f"{page_name}: {page_txt_content}")
            
            # Save individual page JSON and TXT files (e.g. page1.json, page1.txt) in the output folder
            page_json_filename = f"{page_name}.json"
            page_txt_filename = f"{page_name}.txt"
            page_json_path = os.path.join(output_base_dir, page_json_filename)
            page_txt_path = os.path.join(output_base_dir, page_txt_filename)
            
            with open(page_json_path, "w", encoding="utf-8") as f:
                json.dump(page_data, f, indent=2, cls=SafeJSONEncoder, ensure_ascii=False)
                
            with open(page_txt_path, "w", encoding="utf-8") as f:
                f.write(page_txt_content)
                
            print(f"[Saved Individual] Page {page_num} JSON: {page_json_path}")
            print(f"[Saved Individual] Page {page_num} TXT:  {page_txt_path}")
            
            # Collect JSON details
            combined_json_data[page_name] = page_data
            
            # Structure for the frontend response
            # Visual path is relative web URL path
            web_image_path = f"/uploads/temp/{filename_base}/page_{page_num}.png" if is_pdf else f"/uploads/{filename_base}.{ext}"
            
            pages_results.append({
                "page_number": page_num,
                "ocr_result": page_data,
                "image_path": web_image_path,
                "json_file": f"/uploads/output/{filename_base}/{page_json_filename}",
                "txt_file": f"/uploads/output/{filename_base}/{page_txt_filename}"
            })
            
        except Exception as api_err:
            print(f"[ERROR] API request failed on Page {page_num}: {api_err}")
            raise api_err
            
    # Save combined outputs
    combined_txt_path = os.path.join(output_base_dir, "extracted_text.txt")
    with open(combined_txt_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(combined_txt_lines))
        
    combined_json_path = os.path.join(output_base_dir, "extracted_data.json")
    with open(combined_json_path, "w", encoding="utf-8") as f:
        json.dump(combined_json_data, f, indent=2, cls=SafeJSONEncoder, ensure_ascii=False)
        
    print(f"[Saved Combined] JSON: {combined_json_path}")
    print(f"[Saved Combined] TXT:  {combined_txt_path}")
    
    # Wrap results
    return {
        "is_multipage": is_pdf and len(pages_results) > 1,
        "pages": pages_results
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_ocr_pipeline(sys.argv[1])
    else:
        print("Please provide a test image/PDF path.")