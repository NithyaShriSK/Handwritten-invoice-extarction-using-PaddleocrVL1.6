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
import httpx
client = OpenAI(api_key=api_key, base_url=base_url, http_client=httpx.Client(verify=False))

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
            "header_vendor_info": (0.0, 0.0, 0.36, 1.0),
            "products_table": (0.30, 0.0, 0.75, 1.0),
            "tax_and_totals": (0.66, 0.0, 1.0, 1.0)
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
        # Save as PNG with optimal quality (lossless) to preserve handwritten details
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

DIGIT_MAP = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "S": "5", "B": "8", "Z": "2", "G": "6"}
LETTER_MAP = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B"}


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


def parse_to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            cleaned = "".join(c for c in v if c.isdigit() or c == '.' or c == '-')
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def filter_supplier_profiles(profiles, extracted_data=None):
    """
    Optimizes supplier profile database tokens by selecting only the most relevant profile
    or a small subset.
    """
    if not profiles:
        return None
        
    if extracted_data:
        gst = extracted_data.get("company_gst_no")
        name = extracted_data.get("company_name")
        matched = []
        
        profiles_list = []
        if isinstance(profiles, list):
            profiles_list = profiles
        elif isinstance(profiles, dict):
            if "profiles" in profiles:
                profiles_list = profiles["profiles"]
            else:
                profiles_list = [profiles]
                
        for profile in profiles_list:
            p_gst = profile.get("company_gst_no")
            p_name = profile.get("company_name")
            if gst and p_gst and re.sub(r"[^A-Z0-9]", "", str(gst).upper()) == re.sub(r"[^A-Z0-9]", "", str(p_gst).upper()):
                matched.append(profile)
            elif name and p_name and str(name).strip().lower() in str(p_name).strip().lower():
                matched.append(profile)
                
        if matched:
            print(f"[MEMORY] Supplier profile matched locally: {matched[0].get('company_name')}")
            return matched
            
    # Fallback to returning only the first 3 to minimize vision tokens
    if isinstance(profiles, list):
        return profiles[:3]
    return profiles


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


def validate_invoice_math(data):
    products = data.get("products_list", [])

    for product in products:
        quantity = product.get("quantity")
        rate = product.get("rate")
        amount = product.get("amount")

        q_num = parse_to_float(quantity)
        r_num = parse_to_float(rate)
        a_num = parse_to_float(amount)

        if q_num is not None and r_num is not None and a_num is not None:
            expected = q_num * r_num
            if abs(expected - a_num) > 0.05:
                product["_calculation_warning"] = True

    return data


def validate_totals(data):
    total = data.get("total_amount")
    cgst = data.get("cgst_amount") or 0
    sgst = data.get("sgst_amount") or 0
    igst = data.get("igst_amount") or 0

    total_num = parse_to_float(total)
    cgst_num = parse_to_float(cgst)
    sgst_num = parse_to_float(sgst)
    igst_num = parse_to_float(igst)

    products = data.get("products_list", [])
    product_total = 0.0

    for p in products:
        amount = p.get("amount")
        amount_num = parse_to_float(amount)
        product_total += amount_num or 0.0

    data["_validation"] = {
        "product_total": product_total,
        "tax_total": cgst_num + sgst_num + igst_num,
        "extracted_total": total_num
    }

    return data


# ==========================================
# 7. SMART SUSPICIOUS-REGION DETECTOR
# ==========================================

def needs_verification(data):
    """
    Analyzes extracted invoice data locally using deterministic Python checks.
    Returns which regions are suspicious and require targeted second-pass GPT verification.
    """
    suspicious_fields = []
    suspicious_regions = set()
    
    # Mapping of fields to region slices
    field_to_region = {
        # Header Fields
        "company_name": "header",
        "company_gst_no": "header",
        "invoice_number": "header",
        "invoice_date": "header",
        "state_code": "header",
        "vehicle_number": "header",
        "transportation_mode": "header",
        "buyer_name": "header",
        "buyer_gst_no": "header",
        "purchase_order_number": "header",
        # Products List
        "products_list": "products",
        # Totals/Bank Fields
        "cgst_amount": "totals",
        "sgst_amount": "totals",
        "igst_amount": "totals",
        "total_amount": "totals",
        "total_amount_in_words": "totals",
        "bank_account_no": "totals",
        "bank_ifsc": "totals",
        "bank_name": "totals"
    }

    def check_gstin_suspicious(gstin):
        if not gstin or not isinstance(gstin, str):
            return True
        gst_clean = re.sub(r"[^A-Z0-9]", "", gstin.upper())
        if len(gst_clean) != 15:
            return True
        if not gst_clean[:2].isdigit():
            return True
        return False

    # A. GSTIN Validation
    company_gst = data.get("company_gst_no")
    if not company_gst or check_gstin_suspicious(company_gst):
        suspicious_fields.append("company_gst_no")
        suspicious_regions.add("header")

    buyer_gst = data.get("buyer_gst_no")
    if buyer_gst and check_gstin_suspicious(buyer_gst):
        suspicious_fields.append("buyer_gst_no")
        suspicious_regions.add("header")

    # B. Invoice Number Validation
    inv_num = data.get("invoice_number")
    if not inv_num or not str(inv_num).strip():
        suspicious_fields.append("invoice_number")
        suspicious_regions.add("header")

    # C. Date Check
    inv_date = data.get("invoice_date")
    if not inv_date or not str(inv_date).strip():
        suspicious_fields.append("invoice_date")
        suspicious_regions.add("header")
    else:
        date_str = str(inv_date).strip()
        if not re.match(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{2}[/-]\d{2})$", date_str):
            suspicious_fields.append("invoice_date")
            suspicious_regions.add("header")

    # E. Missing Critical Header Fields
    for key in ["company_name", "buyer_name"]:
        if not data.get(key) or not str(data.get(key)).strip():
            suspicious_fields.append(key)
            suspicious_regions.add(field_to_region[key])

    # C/E. Product calculations and line checks
    products = data.get("products_list", [])
    if not isinstance(products, list) or len(products) == 0:
        suspicious_fields.append("products_list")
        suspicious_regions.add("products")
    else:
        for idx, product in enumerate(products):
            qty = product.get("quantity")
            rate = product.get("rate")
            amt = product.get("amount")
            p_name = product.get("product_name")

            if not p_name or not str(p_name).strip():
                suspicious_fields.append(f"products_list[{idx}].product_name")
                suspicious_regions.add("products")

            q_num = parse_to_float(qty)
            r_num = parse_to_float(rate)
            a_num = parse_to_float(amt)

            if q_num is not None and r_num is not None and a_num is not None:
                expected = q_num * r_num
                if abs(expected - a_num) > 0.05:
                    suspicious_fields.append(f"products_list[{idx}].amount")
                    suspicious_regions.add("products")
            else:
                if q_num is None:
                    suspicious_fields.append(f"products_list[{idx}].quantity")
                if r_num is None:
                    suspicious_fields.append(f"products_list[{idx}].rate")
                if a_num is None:
                    suspicious_fields.append(f"products_list[{idx}].amount")
                suspicious_regions.add("products")

    # F. IFSC basic structural check
    ifsc = data.get("bank_ifsc")
    if ifsc:
        ifsc_str = str(ifsc).strip().upper()
        if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc_str):
            suspicious_fields.append("bank_ifsc")
            suspicious_regions.add("totals")

    # D/G. Totals validation
    total = data.get("total_amount")
    cgst = data.get("cgst_amount") or 0
    sgst = data.get("sgst_amount") or 0
    igst = data.get("igst_amount") or 0

    total_num = parse_to_float(total)
    cgst_num = parse_to_float(cgst)
    sgst_num = parse_to_float(sgst)
    igst_num = parse_to_float(igst)

    if total_num is None or total_num <= 0:
        suspicious_fields.append("total_amount")
        suspicious_regions.add("totals")

    product_total = 0.0
    if isinstance(products, list):
        for p in products:
            product_total += parse_to_float(p.get("amount")) or 0.0

    expected_grand_total = product_total + cgst_num + sgst_num + igst_num
    if total_num is not None:
        if abs(expected_grand_total - total_num) > 1.0:
            suspicious_fields.append("total_amount")
            suspicious_regions.add("totals")

    return {
        "needs_verification": len(suspicious_regions) > 0,
        "regions": list(suspicious_regions),
        "fields": suspicious_fields
    }


def get_current_values_for_region(data, region_name):
    if region_name == "header":
        fields = ["company_name", "company_gst_no", "invoice_number", "invoice_date", "state_code", "vehicle_number", "transportation_mode", "buyer_name", "buyer_gst_no", "purchase_order_number"]
        return {f: data.get(f) for f in fields}
    elif region_name == "products":
        return {"products_list": data.get("products_list", [])}
    elif region_name == "totals":
        fields = ["cgst_amount", "sgst_amount", "igst_amount", "total_amount", "total_amount_in_words", "bank_account_no", "bank_ifsc", "bank_name"]
        return {f: data.get(f) for f in fields}
    return {}


def verify_suspicious_region(slice_path, region_name, current_values, supplier_profiles=None, settings=None):
    """
    Executes a targeted second-pass GPT-4o verification call on a single slice.
    """
    base64_slice = encode_image_to_base64(slice_path)
    
    prompt = f"""You are verifying specific invoice OCR fields against the provided {region_name.upper()} slice image.

Check ONLY these fields:
{json.dumps(current_values, indent=2, ensure_ascii=False)}

Rules:
- Compare these fields against the visual evidence in the image.
- Do not modify a value unless the image provides clear visual evidence.
- Do not guess unreadable characters.
- Return ONLY the corrected fields inside a valid JSON object matching the input structure.
"""

    system_prompt = f"You are a highly accurate invoice verification assistant. Verify the provided {region_name} slice."
    if supplier_profiles and settings and settings.get("organization_memory", True):
        matched_profiles = filter_supplier_profiles(supplier_profiles, current_values)
        if matched_profiles:
            system_prompt += f"\n\n[ORGANIZATION MEMORY] Matched Supplier Profile:\n{json.dumps(matched_profiles, indent=2, cls=SafeJSONEncoder)}"
        
    model_name = os.environ.get("OPENAI_MODEL", "gpt-4o")
    print(f"[GPT] Targeted verification: {region_name.upper()} only")
    
    response = client.chat.completions.create(
        model=model_name,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": base64_slice}}
                ]
            }
        ]
    )
    
    usage = getattr(response, "usage", None)
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = usage.total_tokens if usage else 0
    
    corrected_data = json.loads(response.choices[0].message.content.strip())
    return corrected_data, prompt_tokens, completion_tokens, total_tokens


# ==========================================
# 8. MAIN OCR PIPELINE
# ==========================================

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
    
    # Cumulative tokens counters
    cumulative_initial_prompt = 0
    cumulative_initial_completion = 0
    cumulative_initial_total = 0
    cumulative_verification_prompt = 0
    cumulative_verification_completion = 0
    cumulative_verification_total = 0
    cumulative_final_total = 0
    
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
            "header_vendor_info": (0.0, 0.0, 0.36, 1.0),
            "products_table": (0.30, 0.0, 0.75, 1.0),
            "tax_and_totals": (0.66, 0.0, 1.0, 1.0)
        }
        slice_image_regions(preprocessed_path, page_sliced_dir, custom_slices)
        
        # Log slice creation
        header_slice_path = os.path.join(page_sliced_dir, "header_vendor_info.png")
        products_slice_path = os.path.join(page_sliced_dir, "products_table.png")
        totals_slice_path = os.path.join(page_sliced_dir, "tax_and_totals.png")
        
        print(f"[SLICE] Header created: {header_slice_path}")
        print(f"[SLICE] Products created: {products_slice_path}")
        print(f"[SLICE] Totals created: {totals_slice_path}")
        
        # Base64 encode the crops to pass to GPT
        base64_header = encode_image_to_base64(header_slice_path)
        base64_products = encode_image_to_base64(products_slice_path)
        base64_totals = encode_image_to_base64(totals_slice_path)
        
        # Step 2.3: Call GPT Vision completion with exactly the 3 slices (Pass 1)
        model_name = os.environ.get("OPENAI_MODEL", "gpt-4o")
        print(f"[GPT] Initial extraction using 3 slices")
        print(f"[GPT-4o OCR] Sending visual API request to {base_url}/chat/completions (model: {model_name})...")
        
        system_prompt = """You are an expert accounts payable agent. You extract invoice data directly from invoice slices.
Image 1 is the header/vendor/customer region.
Image 2 is the product table region.
Image 3 is the tax/totals/bank region.

Correct typos in names/addresses.
Ensure 'total_amount_in_words' is transcribed exactly as written.
Do not guess unreadable characters. Return null when a value cannot be determined.
Return ONLY valid JSON.
"""

        user_prompt_text = """Extract data from the three provided invoice slices into JSON with these exact fields:
company_name, company_gst_no, invoice_number, invoice_date, state_code, vehicle_number, transportation_mode, products_list[{product_name, hsn_code, quantity, rate, amount}], cgst_amount, sgst_amount, igst_amount, total_amount, buyer_name, buyer_gst_no, total_amount_in_words, bank_account_no, bank_ifsc, bank_name, purchase_order_number.

Rules:
- Preserve handwritten text, invoice numbers, bank account numbers, IFSC, and GSTIN character-by-character.
- Preserve units (e.g. KG, PCS) and decimal points in product quantity/rate/amount.
- Keep every product row separate. Do not merge rows.
- total_amount must be the final payable grand total, not the taxable subtotal.
- Return null for fields not visibly present or completely unreadable.
"""
        
        # Filter and inject matched organization memory supplier profiles if any
        if supplier_profiles and settings.get("organization_memory", True):
            filtered_profiles = filter_supplier_profiles(supplier_profiles)
            if filtered_profiles:
                system_prompt += f"\n\n[ORGANIZATION MEMORY] Matchable Supplier Profiles:\n{json.dumps(filtered_profiles, indent=2, cls=SafeJSONEncoder)}\n"
                system_prompt += "Verify layout extraction logic against these known template definitions if applicable."
            
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
                            {"type": "image_url", "image_url": {"url": base64_header}},
                            {"type": "image_url", "image_url": {"url": base64_products}},
                            {"type": "image_url", "image_url": {"url": base64_totals}}
                        ]
                    }
                ]
            )
            
            # Extract initial tokens count
            usage = getattr(response, "usage", None)
            initial_prompt_tokens = usage.prompt_tokens if usage else 0
            initial_completion_tokens = usage.completion_tokens if usage else 0
            initial_total_tokens = usage.total_tokens if usage else 0
            
            page_data = json.loads(
                response.choices[0].message.content.strip()
            )
            
            # Step 2.4: Apply page-specific cleanups on initial data
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
            
            # Apply mathematical and total validations
            page_data = validate_invoice_math(page_data)
            page_data = validate_totals(page_data)
            
            # Step 2.5: SMART TARGETED SECOND-PASS VERIFICATION (if suspicious)
            check_results = needs_verification(page_data)
            verification_prompt_tokens = 0
            verification_completion_tokens = 0
            verification_total_tokens = 0
            verified_regions_list = []
            
            if check_results["needs_verification"]:
                print(f"[VALIDATION] Suspicious regions detected: {check_results['regions']}")
                print(f"[VALIDATION] Suspicious fields: {check_results['fields']}")
                
                # Perform targeted verification one region at a time
                verification_updates = {}
                for region in check_results["regions"]:
                    slice_map = {
                        "header": header_slice_path,
                        "products": products_slice_path,
                        "totals": totals_slice_path
                    }
                    slice_path = slice_map.get(region)
                    if slice_path and os.path.exists(slice_path):
                        current_vals = get_current_values_for_region(page_data, region)
                        print(f"[VALIDATION] Suspicious region: {region.upper()}")
                        print(f"[VALIDATION] Suspicious fields in region: {list(current_vals.keys())}")
                        
                        corrected, p_tok, c_tok, t_tok = verify_suspicious_region(
                            slice_path,
                            region,
                            current_vals,
                            supplier_profiles=supplier_profiles,
                            settings=settings
                        )
                        
                        verification_prompt_tokens += p_tok
                        verification_completion_tokens += c_tok
                        verification_total_tokens += t_tok
                        verified_regions_list.append(region)
                        
                        # Accumulate corrections
                        verification_updates.update(corrected)
                
                # Merge verification updates
                if verification_updates:
                    print(f"[GPT] Merging corrected fields: {list(verification_updates.keys())}")
                    for key, val in verification_updates.items():
                        if key in page_data:
                            page_data[key] = val
                            
                    # Re-run cleanups and validations post-verification updates
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
                    page_data = validate_invoice_math(page_data)
                    page_data = validate_totals(page_data)
            else:
                # Log passing validations
                print(f"[VALIDATION] GSTIN: PASS")
                print(f"[VALIDATION] Product math: PASS")
                print(f"[VALIDATION] Totals: PASS")
                
            page_total_tokens = initial_total_tokens + verification_total_tokens
            
            # Print page summary statistics
            print(f"\nInitial GPT calls: 1")
            print(f"Verification calls: {len(verified_regions_list)}")
            print(f"Verified regions: {', '.join(verified_regions_list) if verified_regions_list else 'none'}")
            
            # Log token usage per page
            print(f"[TOKENS] Page {page_num} usage:")
            print(f"  Initial Prompt: {initial_prompt_tokens}, Completion: {initial_completion_tokens}, Total: {initial_total_tokens}")
            print(f"  Verification Prompt: {verification_prompt_tokens}, Completion: {verification_completion_tokens}, Total: {verification_total_tokens}")
            print(f"  Page Total: {page_total_tokens}")
            
            # Update cumulative totals
            cumulative_initial_prompt += initial_prompt_tokens
            cumulative_initial_completion += initial_completion_tokens
            cumulative_initial_total += initial_total_tokens
            cumulative_verification_prompt += verification_prompt_tokens
            cumulative_verification_completion += verification_completion_tokens
            cumulative_verification_total += verification_total_tokens
            cumulative_final_total += page_total_tokens
            
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
    
    # Print cumulative totals summary
    print(f"\n[TOKENS CUMULATIVE] Entire PDF/Image Pipeline Run:")
    print(f"  Total Initial: {cumulative_initial_total} (Prompt: {cumulative_initial_prompt}, Completion: {cumulative_initial_completion})")
    print(f"  Total Verification: {cumulative_verification_total} (Prompt: {cumulative_verification_prompt}, Completion: {cumulative_verification_completion})")
    print(f"  Grand Total: {cumulative_final_total}")
    
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