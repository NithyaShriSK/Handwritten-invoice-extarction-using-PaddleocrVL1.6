import os
import re
import uuid
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# FastAPI and Starlette imports for Flask compatibility layer
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import File, UploadFile
from contextvars import ContextVar

# Import the OCR pipeline from the black-box file
from ocr_engine import run_ocr_pipeline

from werkzeug.utils import secure_filename
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId
import jwt
from functools import wraps
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

load_dotenv()

# Initialize ContextVar to store active request
_request_ctx_var = ContextVar("request")

class UploadFileWrapper:
    def __init__(self, upload_file):
        self.upload_file = upload_file
        self.filename = upload_file.filename
        
    def save(self, destination):
        self.upload_file.file.seek(0)
        with open(destination, "wb") as f:
            f.write(self.upload_file.file.read())

class RequestProxy:
    def __getattr__(self, name):
        req = _request_ctx_var.get()
        if name == "args":
            return req.query_params
        elif name == "files":
            return getattr(req.state, "files", {})
        elif name == "json":
            return getattr(req.state, "body_json", None)
        return getattr(req, name)
        
    def __setattr__(self, name, value):
        req = _request_ctx_var.get()
        if name == "user":
            req.state.user = value
        else:
            setattr(req, name, value)

    def get_json(self, force=False, silent=False):
        return getattr(_request_ctx_var.get().state, "body_json", None)

# Instantiate request proxy to replace Flask's thread-local request proxy
request = RequestProxy()

# Monkeypatch Starlette's Request to support request.user as a property
@property
def request_user_property(self):
    return getattr(self.state, "user", None)

@request_user_property.setter
def request_user_property(self, value):
    self.state.user = value

Request.user = request_user_property

def jsonify(*args, **kwargs):
    if args:
        if len(args) == 1:
            return JSONResponse(args[0])
        return JSONResponse(list(args))
    return JSONResponse(kwargs)

def send_from_directory(directory, filename):
    file_path = os.path.join(directory, filename)
    return FileResponse(file_path)

app = FastAPI()

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.config = {}

def translate_flask_path(path: str) -> str:
    translated = re.sub(r"<path:([^>]+)>", r"{\1:path}", path)
    translated = re.sub(r"<string:([^>]+)>", r"{\1}", translated)
    translated = re.sub(r"<([^>]+)>", r"{\1}", translated)
    return translated

import inspect
from functools import wraps
from fastapi.responses import Response as FastAPIResponse

def process_flask_response(res):
    if isinstance(res, tuple) and len(res) == 2:
        val, status_code = res
        if isinstance(val, FastAPIResponse):
            val.status_code = status_code
            return val
        elif isinstance(val, (dict, list, str, int, float, bool)) or val is None:
            if isinstance(val, dict):
                return JSONResponse(content=val, status_code=status_code)
            elif isinstance(val, str):
                return Response(content=val, media_type="text/plain", status_code=status_code)
            else:
                return JSONResponse(content=val, status_code=status_code)
    return res

def wrap_flask_handler(f):
    if inspect.iscoroutinefunction(f):
        @wraps(f)
        async def async_inner(*args, **kwargs):
            res = await f(*args, **kwargs)
            return process_flask_response(res)
        return async_inner
    else:
        @wraps(f)
        def sync_inner(*args, **kwargs):
            res = f(*args, **kwargs)
            return process_flask_response(res)
        return sync_inner

def custom_route(rule, **options):
    translated_rule = translate_flask_path(rule)
    def decorator(f):
        wrapped = wrap_flask_handler(f)
        route_decorator = app.api_route(translated_rule, **options)
        return route_decorator(wrapped)
    return decorator

app.route = custom_route

@app.middleware("http")
async def request_context_middleware(req: Request, call_next):
    # 1. Pre-parse JSON body if content-type is application/json
    body_json = None
    if "application/json" in req.headers.get("content-type", "").lower():
        try:
            body_json = await req.json()
        except Exception:
            pass
    req.state.body_json = body_json

    # 2. Pre-parse files if content-type is multipart/form-data
    files_dict = {}
    content_type = req.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type:
        try:
            form_data = await req.form()
            print(f"[MULTIPART DEBUG] Content-Type: {content_type}, Form keys: {list(form_data.keys())}")
            for key, val in form_data.items():
                if hasattr(val, "filename") and val.filename:
                    files_dict[key] = UploadFileWrapper(val)
                    print(f"[MULTIPART DEBUG] Added file field: {key}, Filename: {val.filename}")
                else:
                    print(f"[MULTIPART DEBUG] Ignored non-file field: {key}, Type: {type(val)}")
        except Exception as e:
            print(f"[MULTIPART PARSE ERROR] {e}")
    req.state.files = files_dict

    # 3. Store in context variable
    token = _request_ctx_var.set(req)
    try:
        response = await call_next(req)
    finally:
        _request_ctx_var.reset(token)
    return response

IS_VERCEL = "VERCEL" in os.environ
UPLOAD_FOLDER = "/tmp/uploads" if IS_VERCEL else os.environ.get("UPLOAD_FOLDER", "uploads")
REPORTS_DIRECTORY = "/tmp/reports" if IS_VERCEL else os.environ.get("REPORTS_DIRECTORY", "reports")
SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable is not configured in the environment variables.")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB limit
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

# Ensure uploads and reports directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORTS_DIRECTORY, exist_ok=True)

# MongoDB Connection
MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "invoice_ocr")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "invoices")

mongo_error = None
db = None
collection = None
users_collection = None
logs_collection = None
reports_collection = None

def migrate_existing_invoices(col):
    try:
        # Find all documents without user_id
        query = {"user_id": {"$exists": False}}
        now_str = datetime.utcnow().isoformat() + "Z"
        result = col.update_many(
            query,
            {
                "$set": {
                    "user_id": "system",
                    "user_email": "system@invoiceocr.com",
                    "uploaded_by": "System Migration",
                    "uploaded_at": now_str,
                    "last_modified_by": "System Migration",
                    "last_modified_at": now_str
                }
            }
        )
        if result.modified_count > 0:
            print(f"[OK] Migrated {result.modified_count} existing invoices to system owner.")
    except Exception as e:
        print(f"[ERROR] Existing invoices migration failed: {e}")

def cleanup_orphaned_reports(rep_col):
    try:
        reports_dir = os.environ.get("REPORTS_DIRECTORY", "reports")
        orphans = []
        for r in rep_col.find():
            filename = r.get("pdf_filename")
            if not filename:
                orphans.append(r["_id"])
                continue
            if ".." in filename or "/" in filename or "\\" in filename:
                orphans.append(r["_id"])
                continue
            file_path = os.path.join(reports_dir, filename)
            if not os.path.exists(file_path):
                orphans.append(r["_id"])
        
        if orphans:
            rep_col.delete_many({"_id": {"$in": orphans}})
            print(f"[OK] Cleaned up {len(orphans)} orphaned report records from database.")
    except Exception as e:
        print(f"[WARNING] Startup orphaned report validation failed: {e}")

def cleanup_duplicate_users(users_col):
    deleted_count = 0
    try:
        # 1. Clean up duplicate emails (keep first, delete the rest)
        email_pipeline = [
            {"$match": {"email": {"$type": "string", "$ne": ""}}},
            {"$group": {"_id": "$email", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
            {"$match": {"count": {"$gt": 1}}}
        ]
        email_duplicates = list(users_col.aggregate(email_pipeline))
        for dup in email_duplicates:
            ids_to_delete = dup["ids"][1:]
            res = users_col.delete_many({"_id": {"$in": ids_to_delete}})
            deleted_count += res.deleted_count

        # 2. Clean up duplicate google_ids (keep first, delete the rest)
        gid_pipeline = [
            {"$match": {"google_id": {"$type": "string", "$gt": ""}}},
            {"$group": {"_id": "$google_id", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
            {"$match": {"count": {"$gt": 1}}}
        ]
        gid_duplicates = list(users_col.aggregate(gid_pipeline))
        for dup in gid_duplicates:
            ids_to_delete = dup["ids"][1:]
            res = users_col.delete_many({"_id": {"$in": ids_to_delete}})
            deleted_count += res.deleted_count

        if deleted_count > 0:
            print(f"[INFO] Cleaned up {deleted_count} duplicate users records.")
    except Exception as e:
        print(f"[WARNING] Pre-index user cleanup failed: {e}")
    return deleted_count

if not MONGO_URI:
    print("[WARNING] MONGODB_URI is not set. Database integration will fail.")
    mongo_error = "MONGODB_URI environment variable is not set."
else:
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        users_collection = db["users"]
        logs_collection = db["activity_logs"]
        reports_collection = db["reports"]
        print(f"[OK] Connected to MongoDB Atlas. DB: {DB_NAME}")
        
        # Create indexes for invoices
        for field, direction in [
            ("edited_invoice_data.company_name", 1),
            ("edited_invoice_data.invoice_number", 1),
            ("edited_invoice_data.buyer_name", 1),
            ("edited_invoice_data.buyer_gst_no", 1),
            ("edited_invoice_data.invoice_date", 1),
            ("created_at", -1),
            ("is_deleted", 1),
            ("user_id", 1),
            ("uploaded_at", 1),
            ("last_modified_at", 1),
        ]:
            try:
                collection.create_index([(field, direction)])
            except Exception as e:
                print(f"[WARNING] Failed to create index for invoices on ({field}, {direction}): {e}")
        
        # Create indexes for users
        # 1. Unique Email index
        try:
            users_collection.create_index([("email", 1)], unique=True)
        except Exception as e:
            print(f"[WARNING] Failed to create unique email index for users: {e}")

        # 2. Unique sparse google_id index
        try:
            users_collection.create_index(
                [("google_id", 1)],
                unique=True,
                partialFilterExpression={"google_id": {"$type": "string", "$gt": ""}}
            )
        except Exception as e:
            print(f"[WARNING] Failed to create google_id index for users: {e}")

        # 3. Role index
        try:
            users_collection.create_index([("role", 1)])
        except Exception as e:
            print(f"[WARNING] Failed to create role index for users: {e}")
        
        # Create indexes for activity_logs
        for field, direction in [
            ("user_id", 1),
            ("timestamp", 1),
            ("action", 1)
        ]:
            try:
                logs_collection.create_index([(field, direction)])
            except Exception as e:
                print(f"[WARNING] Failed to create index for activity_logs on ({field}, {direction}): {e}")
        
        # Create indexes for reports
        try:
            reports_collection.create_index([("user_id", 1)])
            reports_collection.create_index([("generated_at", -1)])
        except Exception as e:
            print(f"[WARNING] Failed to create index for reports: {e}")

        # Run migration for existing invoices
        try:
            migrate_existing_invoices(collection)
        except Exception as e:
            print(f"[WARNING] Failed to run startup invoice migrations: {e}")
            
        # Run startup clean of orphaned report entries
        try:
            cleanup_orphaned_reports(reports_collection)
        except Exception as e:
            print(f"[WARNING] Failed to run startup reports validation: {e}")
            
    except Exception as e:
        print(f"[ERROR] MongoDB connection failed: {e}")
        mongo_error = str(e)


# Helpers for response formatting
def make_success(message, data=None):
    return jsonify({
        "success": True,
        "message": message,
        "data": data or {}
    }), 200

def make_failure(message, errors=None, status_code=400):
    return jsonify({
        "success": False,
        "message": message,
        "errors": errors or []
    }), status_code


# Auth Decorators and Utilities
def get_current_user():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except Exception as e:
        print(f"[AUTH ERROR] Token decode failed: {e}")
        return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return make_failure("Unauthorized access. Token invalid or missing.", status_code=401)
            
        if users_collection is None:
            return make_failure("Database connection unavailable.", status_code=500)
            
        # Verify user exists and is active
        db_user = users_collection.find_one({"_id": ObjectId(user["id"])})
        if not db_user:
            return make_failure("User account not found.", status_code=401)
            
        if not db_user.get("is_active", True):
            return make_failure("User account is disabled. Contact admin.", status_code=403)
            
        # Attach user info to request context
        request.user = {
            "id": str(db_user["_id"]),
            "email": db_user["email"],
            "name": db_user.get("name", ""),
            "role": db_user.get("role", "user")
        }
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return make_failure("Unauthorized access. Token invalid or missing.", status_code=401)
            
        if users_collection is None:
            return make_failure("Database connection unavailable.", status_code=500)
            
        # Verify user exists, is active, and is admin
        db_user = users_collection.find_one({"_id": ObjectId(user["id"])})
        if not db_user:
            return make_failure("User account not found.", status_code=401)
            
        if not db_user.get("is_active", True):
            return make_failure("User account is disabled. Contact admin.", status_code=403)
            
        if db_user.get("role") != "admin":
            return make_failure("Forbidden. Admin access required.", status_code=403)
            
        # Attach user info to request context
        request.user = {
            "id": str(db_user["_id"]),
            "email": db_user["email"],
            "name": db_user.get("name", ""),
            "role": db_user.get("role", "admin")
        }
        return f(*args, **kwargs)
    return decorated

def log_activity(action, invoice_id=None, metadata=None):
    if logs_collection is None or not hasattr(request, "user"):
        return
    try:
        user = request.user
        log_doc = {
            "user_id": user["id"],
            "user_email": user["email"],
            "action": action,
            "invoice_id": str(invoice_id) if invoice_id else None,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow()
        }
        logs_collection.insert_one(log_doc)
    except Exception as e:
        print(f"[ERROR] Failed to log activity '{action}': {e}")


# Helpers for file validation
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Frontend & Backend Data Validation
def validate_invoice_fields(data):
    errors = []
    
    # Required Fields Validation
    required_fields = ["company_name", "invoice_number", "invoice_date", "buyer_name", "total_amount"]
    for f in required_fields:
        if not data.get(f):
            errors.append(f"Field '{f}' is required.")
            
    # GST Validation (if provided)
    gst_pattern = re.compile(r"^[0-9]{2}[A-Z0-9]{13}$")
    for gst_field in ["company_gst_no", "buyer_gst_no"]:
        val = data.get(gst_field)
        if val:
            val_clean = val.replace(" ", "").upper()
            if not gst_pattern.match(val_clean):
                errors.append(f"'{gst_field}' must be a valid 15-character GSTIN format.")
                
    # Invoice Date Validation (DD/MM/YYYY or YYYY-MM-DD or standard format)
    # Check if date format has at least some delimiters
    date_val = data.get("invoice_date")
    if date_val:
        date_pattern = re.compile(r"^\d{1,4}[./-]\d{1,2}[./-]\d{2,4}$")
        if not date_pattern.match(str(date_val).strip()):
            errors.append("'invoice_date' should follow DD/MM/YYYY or YYYY-MM-DD format.")
            
    # Numeric Validation for Tax Amounts and Total
    for num_field in ["cgst_amount", "sgst_amount", "igst_amount", "total_amount"]:
        val = data.get(num_field)
        if val is not None and val != "":
            try:
                float(val)
            except ValueError:
                errors.append(f"'{num_field}' must be a numeric value.")
                
    # Product Table Validations
    products = data.get("products_list", [])
    if not isinstance(products, list):
        errors.append("'products_list' must be an array.")
    else:
        for idx, prod in enumerate(products):
            if not prod.get("product_name"):
                errors.append(f"Product at row {idx+1} is missing a Product Name.")
            
            # Numeric checks on quantity and rate
            q = prod.get("quantity")
            r = prod.get("rate")
            if q is not None and q != "":
                try:
                    float(q)
                except ValueError:
                    errors.append(f"Quantity at product row {idx+1} must be numeric.")
            if r is not None and r != "":
                try:
                    float(r)
                except ValueError:
                    errors.append(f"Rate at product row {idx+1} must be numeric.")
                    
    return errors


# Health Check Endpoints
@app.route("/api/health", methods=["GET"])
def api_health_check():
    return jsonify({"status": "ok"}), 200


@app.route("/health", methods=["GET"])
def health_check():
    mongo_status = "disconnected"
    if collection is not None:
        try:
            # Ping admin database
            client.admin.command('ping')
            mongo_status = "connected"
        except Exception:
            mongo_status = "error"
            
    return jsonify({
        "success": True,
        "mongodb": mongo_status,
        "ocr_engine": "ready"
    }), 200


# POST /api/auth/google
@app.route("/api/auth/google", methods=["POST"])
def auth_google():
    if users_collection is None:
        return make_failure("Database connection unavailable.", status_code=500)
        
    try:
        payload = request.json or {}
        token = payload.get("token")
        if not token:
            return make_failure("Missing ID token in request.")
            
        GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
        if not GOOGLE_CLIENT_ID:
            return make_failure("Google Client ID is not configured on server.", status_code=500)
            
        # Verify using official google-auth library
        try:
            import requests as py_requests
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            session = py_requests.Session()
            session.verify = False
            custom_transport = google_requests.Request(session=session)
            
            idinfo = id_token.verify_oauth2_token(token, custom_transport, GOOGLE_CLIENT_ID)
        except ValueError as e:
            return make_failure(f"Token verification failed: {str(e)}", status_code=400)
            
        # Verify issuer
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            return make_failure("Wrong issuer.", status_code=400)
            
        google_id = idinfo['sub']
        email = idinfo['email']
        name = idinfo.get('name', '')
        picture = idinfo.get('picture', '')
        
        login_type = payload.get("login_type", "user")
        if login_type not in ["user", "admin"]:
            return make_failure("Invalid login type.", status_code=400)
            
        # Check users collection for existing user by google_id or email
        db_user = users_collection.find_one({"$or": [{"google_id": google_id}, {"email": email}]})
        
        # Enforce role validation based on portal used
        if login_type == "admin":
            if not db_user or db_user.get("role") != "admin":
                return make_failure("You do not have administrator access.", status_code=403)
        elif login_type == "user":
            if db_user and db_user.get("role") != "user":
                return make_failure("Please use the Administrator Login portal.", status_code=403)
                
        now = datetime.utcnow()
        
        if not db_user:
            # Create user document (only allowed for standard user path)
            new_user = {
                "google_id": google_id,
                "name": name,
                "email": email,
                "picture": picture,
                "role": "user",  # Default role
                "is_active": True,
                "created_at": now,
                "last_login": now
            }
            result = users_collection.insert_one(new_user)
            db_user = users_collection.find_one({"_id": result.inserted_id})
        else:
            # Check status
            if not db_user.get("is_active", True):
                return make_failure("User account is disabled. Contact your administrator.", status_code=403)
                
            # Update user information and login timestamp
            users_collection.update_one(
                {"_id": db_user["_id"]},
                {
                    "$set": {
                        "google_id": google_id,
                        "name": name,
                        "picture": picture,
                        "last_login": now
                    }
                }
            )
            db_user = users_collection.find_one({"_id": db_user["_id"]})
            
        # Sign JWT
        jwt_payload = {
            "id": str(db_user["_id"]),
            "email": db_user["email"],
            "role": db_user["role"],
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        token_str = jwt.encode(jwt_payload, SECRET_KEY, algorithm="HS256")
        
        # Log login event
        request.user = {
            "id": str(db_user["_id"]),
            "email": db_user["email"]
        }
        log_activity("login")
        
        return jsonify({
            "success": True,
            "message": "Authentication successful",
            "token": token_str,
            "user": {
                "id": str(db_user["_id"]),
                "name": db_user["name"],
                "email": db_user["email"],
                "picture": db_user["picture"],
                "role": db_user["role"]
            }
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return make_failure(f"Auth server error: {str(e)}", status_code=500)

# POST /api/auth/logout
@app.route("/api/auth/logout", methods=["POST"])
@login_required
def auth_logout():
    log_activity("logout")
    return make_success("Logout successful")


# Serve static files from UPLOAD_FOLDER
@app.route("/uploads/<path:filename>")
def serve_uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# POST /api/extract
@app.route("/api/extract", methods=["POST"])
@login_required
def extract_invoice():
    if "file" not in request.files:
        return make_failure("No file provided in request.")
    
    file = request.files["file"]
    if file.filename == "":
        return make_failure("Empty filename provided.")
    
    if not allowed_file(file.filename):
        return make_failure("Unsupported file type. Please upload a PNG, JPG, JPEG, or PDF file.")
        
    try:
        # Validate file size via content length if possible, or read size
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        
        if size > app.config["MAX_CONTENT_LENGTH"]:
            return make_failure("File is too large. Maximum allowed size is 10MB.")
            
        # Generate unique filename to avoid collision: YYYYMMDD_HHMMSS_<rand>.<ext>
        ext = file.filename.rsplit(".", 1)[1].lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rand_id = uuid.uuid4().hex[:6]
        unique_name = f"{timestamp}_{rand_id}.{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        
        # Save image
        file.save(save_path)
        
        # Run black box OCR pipeline
        print("[OCR] Starting pipeline")
        ocr_response = run_ocr_pipeline(save_path)
        print("[OCR] Extraction successful", ocr_response)
        
        # Extract flat OCR result and correct visual page image path
        if isinstance(ocr_response, dict) and "pages" in ocr_response and len(ocr_response["pages"]) > 0:
            ocr_result = ocr_response["pages"][0]["ocr_result"]
            image_url = ocr_response["pages"][0]["image_path"]
            is_multipage = ocr_response.get("is_multipage", False)
            pages = ocr_response.get("pages", [])
        else:
            ocr_result = ocr_response
            image_url = f"/uploads/{unique_name}"
            is_multipage = False
            pages = []
        
        response_data = {
            "ocr_result": ocr_result,
            "invoice_image_path": image_url,
            "is_multipage": is_multipage,
            "pages": pages
        }
        
        # Log activity
        log_activity("invoice_uploaded", metadata={"filename": file.filename})
        
        return make_success("Invoice extraction completed successfully", response_data)
        
    except Exception as e:
        print(f"[ERROR] OCR Extraction failed: {e}")
        return make_failure(f"OCR extraction failed: {str(e)}", errors=[str(e)], status_code=500)


# GET /api/check-duplicate
@app.route("/api/check-duplicate", methods=["GET"])
@login_required
def check_duplicate():
    if collection is None:
        return make_failure(f"Database connection unavailable: {mongo_error}", status_code=500)
        
    company_gst_no = request.args.get("company_gst_no", "").strip()
    invoice_number = request.args.get("invoice_number", "").strip()
    
    if not company_gst_no or not invoice_number:
        return make_failure("Missing company_gst_no or invoice_number query parameters.")
        
    # Check if duplicate exists (exclude soft-deleted)
    duplicate = collection.find_one({
        "edited_invoice_data.company_gst_no": company_gst_no,
        "edited_invoice_data.invoice_number": invoice_number,
        "is_deleted": {"$ne": True}
    })
    
    if duplicate:
        return make_success("Duplicate found", {"duplicate": True})
    else:
        return make_success("No duplicate found", {"duplicate": False})


def is_value_different(v, orig_v):
    if isinstance(v, (dict, list)) or isinstance(orig_v, (dict, list)):
        return v != orig_v

    # Try converting both to float if they look like numbers
    try:
        if v is not None and orig_v is not None:
            if str(v).strip() != "" and str(orig_v).strip() != "":
                if float(v) == float(orig_v):
                    return False
    except (ValueError, TypeError):
        pass
    
    v_str = "" if v is None else str(v).strip()
    orig_v_str = "" if orig_v is None else str(orig_v).strip()
    return v_str != orig_v_str

def is_products_list_different(v, orig_v):
    if not isinstance(v, list):
        v = []
    if not isinstance(orig_v, list):
        orig_v = []
    if len(v) != len(orig_v):
        return True
    
    for item, orig_item in zip(v, orig_v):
        if not isinstance(item, dict) or not isinstance(orig_item, dict):
            if item != orig_item:
                return True
            continue
            
        all_keys = set(item.keys()).union(set(orig_item.keys()))
        for pk in all_keys:
            if pk in ("quantity", "rate", "amount"):
                if is_value_different(item.get(pk), orig_item.get(pk)):
                    return True
            else:
                v_str = "" if item.get(pk) is None else str(item.get(pk)).strip()
                orig_v_str = "" if orig_item.get(pk) is None else str(orig_item.get(pk)).strip()
                if v_str != orig_v_str:
                    return True
    return False

def compute_history_and_status(original, old_edited, new_edited, existing_history, user_email, now_str):
    if not isinstance(original, dict):
        original = {}
    if not isinstance(old_edited, dict):
        old_edited = {}
    if not isinstance(new_edited, dict):
        new_edited = {}
    if not isinstance(existing_history, list):
        existing_history = []

    # 1. Determine if there are differences between original and new_edited
    is_edited = False
    for k, v in new_edited.items():
        if k.startswith("_"):
            continue
        orig_v = original.get(k)
        if k == "products_list":
            if is_products_list_different(v, orig_v):
                is_edited = True
                break
        else:
            if is_value_different(v, orig_v):
                is_edited = True
                break

    if not is_edited:
        # Reverted or has no difference from original -> Review status is Reviewed, history is empty
        return [], "Reviewed"

    # 2. If it is edited, review_status is "Corrected"
    new_history = list(existing_history)

    # If existing history has no entries, we populate it comparing original vs new_edited
    if not new_history:
        for k, v in new_edited.items():
            if k.startswith("_"):
                continue
            orig_v = original.get(k)
            if k == "products_list":
                if is_products_list_different(v, orig_v):
                    new_history.append({
                        "field_name": "products_list",
                        "original_value": json.dumps(orig_v),
                        "edited_value": json.dumps(v),
                        "modified_by": user_email,
                        "modified_at": now_str
                    })
            else:
                if is_value_different(v, orig_v):
                    new_history.append({
                        "field_name": k,
                        "original_value": "" if orig_v is None else str(orig_v).strip(),
                        "edited_value": "" if v is None else str(v).strip(),
                        "modified_by": user_email,
                        "modified_at": now_str
                    })
    else:
        # If history exists, we append new changes comparing old_edited vs new_edited
        for k, v in new_edited.items():
            if k.startswith("_"):
                continue
            old_v = old_edited.get(k)
            if k == "products_list":
                if is_products_list_different(v, old_v):
                    new_history.append({
                        "field_name": "products_list",
                        "original_value": json.dumps(old_v),
                        "edited_value": json.dumps(v),
                        "modified_by": user_email,
                        "modified_at": now_str
                    })
            else:
                if is_value_different(v, old_v):
                    new_history.append({
                        "field_name": k,
                        "original_value": "" if old_v is None else str(old_v).strip(),
                        "edited_value": "" if v is None else str(v).strip(),
                        "modified_by": user_email,
                        "modified_at": now_str
                    })

    # Validate length > 0 constraint for Corrected status
    if not new_history:
        return [], "Reviewed"

    return new_history, "Corrected"


# POST /api/save
@app.route("/api/save", methods=["POST"])
@login_required
def save_invoice():
    import traceback
    try:
        if collection is None:
            return make_failure(f"Database connection unavailable: {mongo_error}", status_code=500)
            
        payload = request.json or {}
        print("Received Save Payload:", request.json)
        
        original = payload.get("original_extracted_data")
        edited = payload.get("edited_invoice_data")
        image_path = payload.get("invoice_image_path", "")
        force_save = payload.get("force_save", False)
        
        if original is None or edited is None:
            return make_failure("Missing original_extracted_data or edited_invoice_data in request body.")
            
        if not isinstance(original, dict):
            original = {}
        if not isinstance(edited, dict):
            return make_failure("edited_invoice_data must be a JSON object.")
            
        # Validation checks
        validation_errors = validate_invoice_fields(edited)
        if validation_errors:
            return make_failure("Validation failed", errors=validation_errors)
            
        # Duplicate Detection
        gst_no = edited.get("company_gst_no", "").strip() if edited.get("company_gst_no") else ""
        inv_no = edited.get("invoice_number", "").strip() if edited.get("invoice_number") else ""
        
        existing = None
        if gst_no and inv_no:
            existing = collection.find_one({
                "edited_invoice_data.company_gst_no": gst_no,
                "edited_invoice_data.invoice_number": inv_no,
                "is_deleted": {"$ne": True}
            })
            
        if existing and not force_save:
            return make_failure("Invoice may already exist.", errors=["DUPLICATE_WARNING"], status_code=409)
                
        now = datetime.utcnow()
        now_str = now.isoformat() + "Z"
        
        # Calculate history and review_status dynamically using safe helper
        change_history, review_status = compute_history_and_status(
            original=original,
            old_edited={},
            new_edited=edited,
            existing_history=[],
            user_email=request.user["email"],
            now_str=now_str
        )
        
        # Add temporary debug logging
        print("[PAGE SAVE DEBUG] Request Payload received:")
        print(f"  source_filename: {edited.get('source_filename')}")
        print(f"  source_page_number: {edited.get('source_page_number')}")
        print(f"  total_pages: {edited.get('total_pages')}")
        print(f"  document_type: {edited.get('document_type')}")
        print(f"  invoice_number: {edited.get('invoice_number')}")
        print(f"  buyer_name: {edited.get('buyer_name')}")
        print(f"  products: {edited.get('products_list')}")

        document = {
            "original_extracted_data": original,
            "edited_invoice_data": edited,
            "invoice_image_path": image_path,
            "review_status": review_status,
            "ocr_source": "GPT-4o",
            "source_filename": edited.get("source_filename"),
            "source_page_number": edited.get("source_page_number"),
            "total_pages": edited.get("total_pages"),
            "document_type": edited.get("document_type"),
            "user_id": request.user["id"],
            "user_email": request.user["email"],
            "uploaded_by": request.user["email"],
            "uploaded_at": now_str,
            "last_modified_by": request.user["email"],
            "last_modified_at": now_str,
            "change_history": change_history,
            "is_deleted": False,
            "deleted_at": None,
            "created_at": now,
            "updated_at": now
        }
        
        if existing and force_save:
            document["_id"] = existing["_id"]
            document["uploaded_at"] = existing.get("uploaded_at", now_str)
            document["created_at"] = existing.get("created_at", now)
            collection.replace_one({"_id": existing["_id"]}, document)
            invoice_id = existing["_id"]
            document["_id"] = str(existing["_id"])
            print(f"[PAGE SAVE] Overwrote existing document: {existing['_id']}")
        else:
            result = collection.insert_one(document)
            invoice_id = result.inserted_id
            document["_id"] = str(result.inserted_id)
            
        # Log activity
        log_activity(
            "invoice_saved",
            invoice_id=invoice_id,
            metadata={
                "invoice_number": edited.get("invoice_number"),
                "company_name": edited.get("company_name"),
                "overwritten": True if (existing and force_save) else False
            }
        )
        
        # Convert datetimes to iso strings for response
        document["created_at"] = document["created_at"].isoformat() + "Z"
        document["updated_at"] = document["updated_at"].isoformat() + "Z"
        return make_success("Invoice saved successfully", document)
    except Exception as e:
        traceback.print_exc()
        return make_failure(f"Database error: {str(e)}", status_code=500)


# GET /api/invoices (supports search, paging, filters, sorts)
@app.route("/api/invoices", methods=["GET"])
@login_required
def get_invoices():
    if collection is None:
        return make_failure(f"Database connection unavailable: {mongo_error}", status_code=500)
        
    try:
        # Query params
        search_query = request.args.get("search", "").strip()
        review_status = request.args.get("review_status", "").strip()
        start_date_str = request.args.get("start_date", "").strip()
        end_date_str = request.args.get("end_date", "").strip()
        
        sort_by = request.args.get("sort_by", "created_at").strip()
        sort_order = request.args.get("sort_order", "desc").strip()
        
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 10))
        
        # Build Filter Query
        query = {"is_deleted": {"$ne": True}}
        
        # Enforce RBAC ownership isolation
        if request.user.get("role") != "admin":
            query["user_id"] = request.user["id"]
        
        if search_query:
            # Case insensitive regex match on Company, Buyer, Invoice Number, and GST
            regex_query = {"$regex": search_query, "$options": "i"}
            query["$or"] = [
                {"edited_invoice_data.company_name": regex_query},
                {"edited_invoice_data.buyer_name": regex_query},
                {"edited_invoice_data.invoice_number": regex_query},
                {"edited_invoice_data.company_gst_no": regex_query},
                {"edited_invoice_data.buyer_gst_no": regex_query}
            ]
            
        if review_status:
            query["review_status"] = review_status
            
        # Date Filters
        if start_date_str or end_date_str:
            date_filter = {}
            if start_date_str:
                try:
                    date_filter["$gte"] = datetime.strptime(start_date_str, "%Y-%m-%d")
                except ValueError:
                    pass
            if end_date_str:
                try:
                    date_filter["$lte"] = datetime.strptime(end_date_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
            if date_filter:
                query["created_at"] = date_filter

        # Sort Logic
        sort_fields = {
            "invoice_date": "edited_invoice_data.invoice_date",
            "created_at": "created_at",
            "total_amount": "edited_invoice_data.total_amount"
        }
        db_sort_field = sort_fields.get(sort_by, "created_at")
        db_sort_order = DESCENDING if sort_order == "desc" else ASCENDING
        
        # Pagination calculations
        skip = (page - 1) * limit
        
        # Query DB
        cursor = collection.find(query).sort(db_sort_field, db_sort_order).skip(skip).limit(limit)
        total_count = collection.count_documents(query)
        
        invoices = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            if isinstance(doc.get("created_at"), datetime):
                doc["created_at"] = doc["created_at"].isoformat() + "Z"
            if isinstance(doc.get("updated_at"), datetime):
                doc["updated_at"] = doc["updated_at"].isoformat() + "Z"
            if isinstance(doc.get("deleted_at"), datetime):
                doc["deleted_at"] = doc["deleted_at"].isoformat() + "Z"
            invoices.append(doc)
            
        data = {
            "invoices": invoices,
            "total": total_count,
            "page": page,
            "limit": limit,
            "pages": (total_count + limit - 1) // limit
        }
        
        return make_success("Invoices fetched successfully", data)
        
    except Exception as e:
        return make_failure(f"Failed to fetch invoices: {str(e)}", status_code=500)


# GET /api/invoice/<id>
@app.route("/api/invoice/<string:invoice_id>", methods=["GET"])
@login_required
def get_invoice(invoice_id):
    if collection is None:
        return make_failure(f"Database connection unavailable: {mongo_error}", status_code=500)
        
    try:
        doc = collection.find_one({"_id": ObjectId(invoice_id), "is_deleted": {"$ne": True}})
        if not doc:
            return make_failure("Invoice not found or has been deleted.", status_code=404)
            
        # Enforce RBAC ownership isolation
        if request.user.get("role") != "admin" and doc.get("user_id") != request.user.get("id"):
            return make_failure("Access forbidden. You do not own this invoice.", status_code=403)
            
        doc["_id"] = str(doc["_id"])
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat() + "Z"
        if isinstance(doc.get("updated_at"), datetime):
            doc["updated_at"] = doc["updated_at"].isoformat() + "Z"
            
        return make_success("Invoice retrieved successfully", doc)
    except Exception as e:
        return make_failure(f"Invalid invoice ID format or DB error: {str(e)}", status_code=500)


# PUT /api/invoice/<id>
@app.route("/api/invoice/<string:invoice_id>", methods=["PUT"])
@login_required
def update_invoice(invoice_id):
    if collection is None:
        return make_failure(f"Database connection unavailable: {mongo_error}", status_code=500)
        
    try:
        oid = ObjectId(invoice_id)
        current_doc = collection.find_one({"_id": oid, "is_deleted": {"$ne": True}})
        if not current_doc:
            return make_failure("Invoice not found or deleted.", status_code=404)
            
        # Enforce RBAC ownership isolation
        if request.user.get("role") != "admin" and current_doc.get("user_id") != request.user.get("id"):
            return make_failure("Access forbidden. You do not own this invoice.", status_code=403)
            
        payload = request.json or {}
        new_edited = payload.get("edited_invoice_data")
        
        if not new_edited:
            return make_failure("Missing edited_invoice_data in payload.")
            
        # Validation checks
        validation_errors = validate_invoice_fields(new_edited)
        if validation_errors:
            return make_failure("Validation failed", errors=validation_errors)
            
        # Track Audit Trail History
        old_edited = current_doc.get("edited_invoice_data", {})
        original_ocr = current_doc.get("original_extracted_data", {})
        history = current_doc.get("change_history", [])
        
        now = datetime.utcnow()
        now_str = now.isoformat() + "Z"
        
        # Calculate history and review_status dynamically using safe helper
        history, review_status = compute_history_and_status(
            original=original_ocr,
            old_edited=old_edited,
            new_edited=new_edited,
            existing_history=history,
            user_email=request.user["email"],
            now_str=now_str
        )
        
        # Perform DB Update
        update_data = {
            "edited_invoice_data": new_edited,
            "review_status": review_status,
            "change_history": history,
            "last_modified_by": request.user["email"],
            "last_modified_at": now_str,
            "updated_at": now
        }
        
        if "invoice_image_path" in payload:
            update_data["invoice_image_path"] = payload["invoice_image_path"]
            
        # Copy page-level metadata to root document
        if new_edited.get("source_filename"):
            update_data["source_filename"] = new_edited["source_filename"]
        if new_edited.get("source_page_number"):
            update_data["source_page_number"] = new_edited["source_page_number"]
        if new_edited.get("total_pages"):
            update_data["total_pages"] = new_edited["total_pages"]
        if new_edited.get("document_type"):
            update_data["document_type"] = new_edited["document_type"]
            
        collection.update_one({"_id": oid}, {"$set": update_data})
        
        # Log activity
        log_activity(
            "invoice_corrected" if review_status == "Corrected" else "invoice_saved",
            invoice_id=invoice_id,
            metadata={
                "invoice_number": new_edited.get("invoice_number"),
                "company_name": new_edited.get("company_name")
            }
        )
        
        # Retrieve updated doc
        updated_doc = collection.find_one({"_id": oid})
        updated_doc["_id"] = str(updated_doc["_id"])
        updated_doc["created_at"] = updated_doc["created_at"].isoformat() + "Z"
        updated_doc["updated_at"] = updated_doc["updated_at"].isoformat() + "Z"
        
        return make_success("Invoice updated successfully", updated_doc)
        
    except Exception as e:
        return make_failure(f"Update failed: {str(e)}", status_code=500)


# DELETE /api/invoice/<id> (Soft delete)
@app.route("/api/invoice/<string:invoice_id>", methods=["DELETE"])
@login_required
def delete_invoice(invoice_id):
    if collection is None:
        return make_failure(f"Database connection unavailable: {mongo_error}", status_code=500)
        
    try:
        oid = ObjectId(invoice_id)
        current = collection.find_one({"_id": oid, "is_deleted": {"$ne": True}})
        if not current:
            return make_failure("Invoice not found or already deleted.", status_code=404)
            
        # Enforce RBAC ownership isolation
        if request.user.get("role") != "admin" and current.get("user_id") != request.user.get("id"):
            return make_failure("Access forbidden. You do not own this invoice.", status_code=403)
            
        now = datetime.utcnow()
        collection.update_one(
            {"_id": oid},
            {"$set": {
                "is_deleted": True,
                "deleted_at": now,
                "updated_at": now
            }}
        )
        
        # Log activity
        log_activity("invoice_deleted", invoice_id=invoice_id)
        
        return make_success("Invoice soft-deleted successfully", {"_id": invoice_id})
    except Exception as e:
        return make_failure(f"Delete failed: {str(e)}", status_code=500)


# GET /api/analytics
@app.route("/api/analytics", methods=["GET"])
@login_required
def get_analytics():
    if collection is None:
        return make_failure(f"Database connection unavailable: {mongo_error}", status_code=500)
        
    try:
        match_query = {"is_deleted": {"$ne": True}}
        
        # Enforce RBAC ownership isolation
        if request.user.get("role") != "admin":
            match_query["user_id"] = request.user.get("id")
            
        # Date range filtering
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        if start_date or end_date:
            date_filter = {}
            if start_date:
                try:
                    date_filter["$gte"] = datetime.strptime(start_date.strip(), "%Y-%m-%d")
                except ValueError:
                    pass
            if end_date:
                try:
                    date_filter["$lte"] = datetime.strptime(end_date.strip() + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
            if date_filter:
                match_query["created_at"] = date_filter
            
        total_invoices = collection.count_documents(match_query)
        
        status_pipeline = [
            {"$match": match_query},
            {"$group": {"_id": "$review_status", "count": {"$sum": 1}}}
        ]
        status_counts = {
            "Pending Review": 0,
            "Reviewed": 0,
            "Corrected": 0
        }
        for item in collection.aggregate(status_pipeline):
            status_counts[item["_id"]] = item["count"]
            
        company_pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": "$edited_invoice_data.company_name",
                "total_value": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"total_value": -1}},
            {"$limit": 5}
        ]
        top_companies = []
        for item in collection.aggregate(company_pipeline):
            top_companies.append({
                "company_name": item["_id"] or "Unknown Company",
                "total_value": round(item["total_value"], 2),
                "count": item["count"]
            })
            
        buyer_pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": "$edited_invoice_data.buyer_name",
                "total_value": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"total_value": -1}},
            {"$limit": 5}
        ]
        top_buyers = []
        for item in collection.aggregate(buyer_pipeline):
            top_buyers.append({
                "buyer_name": item["_id"] or "Unknown Buyer",
                "total_value": round(item["total_value"], 2),
                "count": item["count"]
            })
            
        summary_pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": None,
                "total_value": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}},
                "unique_companies": {"$addToSet": "$edited_invoice_data.company_gst_no"},
                "unique_buyers": {"$addToSet": "$edited_invoice_data.buyer_gst_no"}
            }}
        ]
        summary_res = list(collection.aggregate(summary_pipeline))
        total_revenue = round(summary_res[0]["total_value"], 2) if summary_res else 0.0
        unique_companies_count = len(summary_res[0]["unique_companies"]) if summary_res else 0
        unique_buyers_count = len(summary_res[0]["unique_buyers"]) if summary_res else 0
        
        monthly_pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": {
                    "year": {"$year": "$created_at"},
                    "month": {"$month": "$created_at"}
                },
                "count": {"$sum": 1},
                "revenue": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}}
            }},
            {"$sort": {"_id.year": 1, "_id.month": 1}},
            {"$limit": 6}
        ]
        monthly_data = []
        months_list = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for item in collection.aggregate(monthly_pipeline):
            y = item["_id"]["year"]
            m = item["_id"]["month"]
            label = f"{months_list[m]} {y}"
            monthly_data.append({
                "label": label,
                "count": item["count"],
                "revenue": round(item["revenue"], 2)
            })
            
        gst_pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id": None,
                "total_cgst": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.cgst_amount", 0]}}},
                "total_sgst": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.sgst_amount", 0]}}},
                "total_igst": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.igst_amount", 0]}}}
            }}
        ]
        gst_res = list(collection.aggregate(gst_pipeline))
        gst_distribution = {
            "CGST": round(gst_res[0]["total_cgst"], 2) if gst_res else 0.0,
            "SGST": round(gst_res[0]["total_sgst"], 2) if gst_res else 0.0,
            "IGST": round(gst_res[0]["total_igst"], 2) if gst_res else 0.0
        }
        
        now = datetime.utcnow()
        current_month_start = datetime(now.year, now.month, 1)
        if now.month == 1:
            prev_month_start = datetime(now.year - 1, 12, 1)
            prev_month_end = datetime(now.year, 1, 1)
        else:
            prev_month_start = datetime(now.year, now.month - 1, 1)
            prev_month_end = datetime(now.year, now.month, 1)
            
        curr_month_count = collection.count_documents({"created_at": {"$gte": current_month_start}, "is_deleted": {"$ne": True}})
        prev_month_count = collection.count_documents({"created_at": {"$gte": prev_month_start, "$lt": prev_month_end}, "is_deleted": {"$ne": True}})
        
        count_trend = 0.0
        if prev_month_count > 0:
            count_trend = round(((curr_month_count - prev_month_count) / prev_month_count) * 100, 1)
        elif curr_month_count > 0:
            count_trend = 100.0
            
        curr_rev_pipeline = [
            {"$match": {"created_at": {"$gte": current_month_start}, "is_deleted": {"$ne": True}}},
            {"$group": {"_id": None, "total": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}}}}
        ]
        curr_rev_res = list(collection.aggregate(curr_rev_pipeline))
        curr_revenue = curr_rev_res[0]["total"] if curr_rev_res else 0.0
        
        prev_rev_pipeline = [
            {"$match": {"created_at": {"$gte": prev_month_start, "$lt": prev_month_end}, "is_deleted": {"$ne": True}}},
            {"$group": {"_id": None, "total": {"$sum": {"$toDouble": {"$ifNull": ["$edited_invoice_data.total_amount", 0]}}}}}
        ]
        prev_rev_res = list(collection.aggregate(prev_rev_pipeline))
        prev_revenue = prev_rev_res[0]["total"] if prev_rev_res else 0.0
        
        revenue_trend = 0.0
        if prev_revenue > 0:
            revenue_trend = round(((curr_revenue - prev_revenue) / prev_revenue) * 100, 1)
        elif curr_revenue > 0:
            revenue_trend = 100.0
            
        analytics_data = {
            "total_invoices": total_invoices,
            "total_revenue": total_revenue,
            "unique_companies_count": unique_companies_count,
            "unique_buyers_count": unique_buyers_count,
            "status_counts": status_counts,
            "top_companies": top_companies,
            "top_buyers": top_buyers,
            "monthly_data": monthly_data,
            "gst_distribution": gst_distribution,
            "trends": {
                "count_trend": count_trend,
                "revenue_trend": revenue_trend,
                "current_month_count": curr_month_count,
                "previous_month_count": prev_month_count,
                "current_month_revenue": round(curr_revenue, 2),
                "previous_month_revenue": round(prev_revenue, 2)
            }
        }
        
        return make_success("Analytics data computed successfully", analytics_data)
        
    except Exception as e:
        return make_failure(f"Failed to generate analytics: {str(e)}", status_code=500)


# GET /api/admin/users
@app.route("/api/admin/users", methods=["GET"])
@admin_required
def admin_get_users():
    if users_collection is None or collection is None:
        return make_failure("Database connection unavailable.", status_code=500)
    try:
        users = list(users_collection.find())
        user_list = []
        for u in users:
            uid_str = str(u["_id"])
            total_inv = collection.count_documents({"user_id": uid_str, "is_deleted": {"$ne": True}})
            corrected_inv = collection.count_documents({"user_id": uid_str, "review_status": "Corrected", "is_deleted": {"$ne": True}})
            corr_rate = round((corrected_inv / total_inv) * 100, 1) if total_inv > 0 else 0.0
            
            user_list.append({
                "id": uid_str,
                "name": u.get("name", "Unknown"),
                "email": u.get("email", ""),
                "picture": u.get("picture", ""),
                "role": u.get("role", "user"),
                "is_active": u.get("is_active", True),
                "created_at": u.get("created_at").isoformat() + "Z" if isinstance(u.get("created_at"), datetime) else None,
                "last_login": u.get("last_login").isoformat() + "Z" if isinstance(u.get("last_login"), datetime) else None,
                "total_invoices": total_inv,
                "total_corrections": corrected_inv,
                "correction_rate": corr_rate
            })
        return make_success("Users retrieved successfully", user_list)
    except Exception as e:
        return make_failure(f"Failed to fetch users: {str(e)}", status_code=500)

# PUT /api/admin/user/<string:user_id>/role
@app.route("/api/admin/user/<string:user_id>/role", methods=["PUT"])
@admin_required
def admin_update_user_role(user_id):
    if users_collection is None:
        return make_failure("Database connection unavailable.", status_code=500)
    try:
        payload = request.json or {}
        role = payload.get("role")
        if role not in ["user", "admin"]:
            return make_failure("Invalid role value. Must be 'user' or 'admin'.", status_code=400)
            
        result = users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"role": role}}
        )
        if result.matched_count == 0:
            return make_failure("User not found.", status_code=404)
            
        return make_success("User role updated successfully")
    except Exception as e:
        return make_failure(f"Failed to update role: {str(e)}", status_code=500)

# PUT /api/admin/user/<string:user_id>/status
@app.route("/api/admin/user/<string:user_id>/status", methods=["PUT"])
@admin_required
def admin_update_user_status(user_id):
    if users_collection is None:
        return make_failure("Database connection unavailable.", status_code=500)
    try:
        payload = request.json or {}
        is_active = payload.get("is_active")
        if not isinstance(is_active, bool):
            return make_failure("Invalid status value. Must be a boolean.", status_code=400)
            
        result = users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": is_active}}
        )
        if result.matched_count == 0:
            return make_failure("User not found.", status_code=404)
            
        return make_success("User status updated successfully")
    except Exception as e:
        return make_failure(f"Failed to update status: {str(e)}", status_code=500)

# GET /api/admin/activity-logs
@app.route("/api/admin/activity-logs", methods=["GET"])
@admin_required
def admin_get_activity_logs():
    if logs_collection is None:
        return make_failure("Database connection unavailable.", status_code=500)
    try:
        limit = int(request.args.get("limit", 100))
        logs = list(logs_collection.find().sort("timestamp", -1).limit(limit))
        
        log_list = []
        for log in logs:
            log_list.append({
                "id": str(log["_id"]),
                "user_id": log.get("user_id"),
                "user_email": log.get("user_email"),
                "action": log.get("action"),
                "invoice_id": log.get("invoice_id"),
                "metadata": log.get("metadata", {}),
                "timestamp": log.get("timestamp").isoformat() + "Z" if isinstance(log.get("timestamp"), datetime) else None
            })
        return make_success("Activity logs retrieved successfully", log_list)
    except Exception as e:
        return make_failure(f"Failed to fetch logs: {str(e)}", status_code=500)

# GET /api/admin/user/<string:user_id>/invoices
@app.route("/api/admin/user/<string:user_id>/invoices", methods=["GET"])
@admin_required
def admin_get_user_invoices(user_id):
    if collection is None:
        return make_failure("Database connection unavailable.", status_code=500)
    try:
        invoices = list(collection.find({"user_id": user_id, "is_deleted": {"$ne": True}}).sort("created_at", -1))
        res_list = []
        for inv in invoices:
            inv["_id"] = str(inv["_id"])
            if isinstance(inv.get("created_at"), datetime):
                inv["created_at"] = inv["created_at"].isoformat() + "Z"
            if isinstance(inv.get("updated_at"), datetime):
                inv["updated_at"] = inv["updated_at"].isoformat() + "Z"
            res_list.append(inv)
        return make_success("User invoices fetched successfully", res_list)
    except Exception as e:
        return make_failure(f"Failed to fetch user invoices: {str(e)}", status_code=500)

# GET /api/admin/analytics
@app.route("/api/admin/analytics", methods=["GET"])
@admin_required
def admin_get_analytics():
    if collection is None or users_collection is None or logs_collection is None:
        return make_failure("Database connection unavailable.", status_code=500)
    try:
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        month_start = datetime(now.year, now.month, 1)
        
        # User counts (excluding admins)
        total_users = users_collection.count_documents({"role": "user"})
        active_users = users_collection.count_documents({"role": "user", "is_active": True})
        
        # Base aggregation matching standard users only
        # We check if user_id is a 24-character string first to safely convert it to ObjectId
        base_user_invoices_pipeline = [
            {"$match": {"is_deleted": {"$ne": True}}},
            {"$match": {"user_id": {"$ne": "system"}}},
            {"$addFields": {
                "user_obj_id": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$eq": [{"$type": "$user_id"}, "string"]},
                                {"$eq": [{"$strLenCP": "$user_id"}, 24]}
                            ]
                        },
                        "then": {"$toObjectId": "$user_id"},
                        "else": None
                    }
                }
            }},
            {"$lookup": {
                "from": "users",
                "localField": "user_obj_id",
                "foreignField": "_id",
                "as": "user_info"
            }},
            {"$unwind": "$user_info"},
            {"$match": {"user_info.role": "user"}}
        ]
        
        def get_pipeline_count(pipeline):
            res = list(collection.aggregate(pipeline + [{"$count": "count"}]))
            return res[0]["count"] if res else 0
            
        total_invoices = get_pipeline_count(base_user_invoices_pipeline)
        invoices_today = get_pipeline_count(base_user_invoices_pipeline + [{"$match": {"created_at": {"$gte": today_start}}}])
        invoices_month = get_pipeline_count(base_user_invoices_pipeline + [{"$match": {"created_at": {"$gte": month_start}}}])
        
        # Overall Correction Rate
        corrected_count = get_pipeline_count(base_user_invoices_pipeline + [{"$match": {"review_status": "Corrected"}}])
        overall_correction_rate = round((corrected_count / total_invoices) * 100, 1) if total_invoices > 0 else 0.0
        
        # Overall Acceptance Rate
        accepted_count = get_pipeline_count(base_user_invoices_pipeline + [{"$match": {"review_status": "Reviewed"}}])
        overall_acceptance_rate = round((accepted_count / total_invoices) * 100, 1) if total_invoices > 0 else 0.0
        
        # Top Uploaders (standard users only)
        uploader_pipeline = base_user_invoices_pipeline + [
            {"$group": {
                "_id": "$user_id",
                "email": {"$first": "$user_email"},
                "uploaded_by": {"$first": "$uploaded_by"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        top_uploaders = []
        for item in collection.aggregate(uploader_pipeline):
            uname = item["uploaded_by"]
            if item["_id"] != "system":
                try:
                    u_doc = users_collection.find_one({"_id": ObjectId(item["_id"])})
                    if u_doc:
                        uname = u_doc.get("name", u_doc["email"])
                except Exception:
                    pass
            top_uploaders.append({
                "user_id": item["_id"],
                "email": item["email"],
                "name": uname,
                "count": item["count"]
            })
            
        # User Correction rates per user (standard users only)
        all_users = list(users_collection.find({"role": "user"}))
        user_correction_rates = []
        total_rates_sum = 0
        valid_user_rates_count = 0
        for u in all_users:
            uid_str = str(u["_id"])
            user_inv_count = collection.count_documents({"user_id": uid_str, "is_deleted": {"$ne": True}})
            user_corr_count = collection.count_documents({"user_id": uid_str, "review_status": "Corrected", "is_deleted": {"$ne": True}})
            rate = round((user_corr_count / user_inv_count) * 100, 1) if user_inv_count > 0 else 0.0
            
            user_correction_rates.append({
                "name": u.get("name", "Unknown"),
                "email": u.get("email"),
                "total_invoices": user_inv_count,
                "corrected_invoices": user_corr_count,
                "correction_rate": rate
            })
            if user_inv_count > 0:
                total_rates_sum += rate
                valid_user_rates_count += 1
                
        average_correction_rate = round(total_rates_sum / valid_user_rates_count, 1) if valid_user_rates_count > 0 else 0.0
        top_users_correction = sorted(user_correction_rates, key=lambda x: x["correction_rate"], reverse=True)[:5]
        
        # Most Corrected Invoices (standard users only)
        corrected_invoices_pipeline = [
            {"$match": {"is_deleted": {"$ne": True}, "change_history": {"$exists": True}}},
            {"$match": {"user_id": {"$ne": "system"}}},
            {"$addFields": {
                "user_obj_id": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$eq": [{"$type": "$user_id"}, "string"]},
                                {"$eq": [{"$strLenCP": "$user_id"}, 24]}
                            ]
                        },
                        "then": {"$toObjectId": "$user_id"},
                        "else": None
                    }
                }
            }},
            {"$lookup": {
                "from": "users",
                "localField": "user_obj_id",
                "foreignField": "_id",
                "as": "user_info"
            }},
            {"$unwind": "$user_info"},
            {"$match": {"user_info.role": "user"}},
            {"$project": {
                "_id": 1,
                "user_email": 1,
                "uploaded_by": 1,
                "last_modified_at": 1,
                "edited_invoice_data.invoice_number": 1,
                "edited_invoice_data.company_name": 1,
                "correction_count": {"$size": "$change_history"}
            }},
            {"$sort": {"correction_count": -1}},
            {"$limit": 10}
        ]
        most_corrected_invoices = []
        for item in collection.aggregate(corrected_invoices_pipeline):
            most_corrected_invoices.append({
                "invoice_id": str(item["_id"]),
                "invoice_number": item.get("edited_invoice_data", {}).get("invoice_number", "N/A"),
                "company_name": item.get("edited_invoice_data", {}).get("company_name", "N/A"),
                "uploaded_by": item.get("user_email", item.get("uploaded_by", "Unknown")),
                "correction_count": item.get("correction_count", 0),
                "last_modified_at": item.get("last_modified_at")
            })
            
        # Upload trend by month (last 6 months, standard users only)
        monthly_pipeline = base_user_invoices_pipeline + [
            {"$group": {
                "_id": {
                    "year": {"$year": "$created_at"},
                    "month": {"$month": "$created_at"}
                },
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id.year": 1, "_id.month": 1}},
            {"$limit": 6}
        ]
        upload_trend_by_month = []
        months_list = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for item in collection.aggregate(monthly_pipeline):
            y = item["_id"]["year"]
            m = item["_id"]["month"]
            upload_trend_by_month.append({
                "label": f"{months_list[m]} {y}",
                "count": item["count"]
            })
            
        # Most Active Users (by activity logs, standard users only)
        activity_pipeline = [
            {"$match": {"user_id": {"$ne": "system"}}},
            {"$addFields": {
                "user_obj_id": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$eq": [{"$type": "$user_id"}, "string"]},
                                {"$eq": [{"$strLenCP": "$user_id"}, 24]}
                            ]
                        },
                        "then": {"$toObjectId": "$user_id"},
                        "else": None
                    }
                }
            }},
            {"$lookup": {
                "from": "users",
                "localField": "user_obj_id",
                "foreignField": "_id",
                "as": "user_info"
            }},
            {"$unwind": "$user_info"},
            {"$match": {"user_info.role": "user"}},
            {"$group": {"_id": "$user_id", "email": {"$first": "$user_email"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        most_active_users = []
        for item in logs_collection.aggregate(activity_pipeline):
            uname = item["email"]
            if item["_id"] != "system":
                try:
                    u_doc = users_collection.find_one({"_id": ObjectId(item["_id"])})
                    if u_doc:
                        uname = u_doc.get("name", u_doc["email"])
                except Exception:
                    pass
            most_active_users.append({
                "user_id": item["_id"],
                "email": item["email"],
                "name": uname,
                "count": item["count"]
            })

        # Most Active Admins (by activity logs, admins only)
        admin_activity_pipeline = [
            {"$match": {"user_id": {"$ne": "system"}}},
            {"$addFields": {
                "user_obj_id": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$eq": [{"$type": "$user_id"}, "string"]},
                                {"$eq": [{"$strLenCP": "$user_id"}, 24]}
                            ]
                        },
                        "then": {"$toObjectId": "$user_id"},
                        "else": None
                    }
                }
            }},
            {"$lookup": {
                "from": "users",
                "localField": "user_obj_id",
                "foreignField": "_id",
                "as": "user_info"
            }},
            {"$unwind": "$user_info"},
            {"$match": {"user_info.role": "admin"}},
            {"$group": {"_id": "$user_id", "email": {"$first": "$user_email"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        most_active_admins = []
        for item in logs_collection.aggregate(admin_activity_pipeline):
            uname = item["email"]
            if item["_id"] != "system":
                try:
                    u_doc = users_collection.find_one({"_id": ObjectId(item["_id"])})
                    if u_doc:
                        uname = u_doc.get("name", u_doc["email"])
                except Exception:
                    pass
            most_active_admins.append({
                "user_id": item["_id"],
                "email": item["email"],
                "name": uname,
                "count": item["count"]
            })
            
        # Daily User Activity Trend (last 7 days, standard users only)
        activity_trend_pipeline = [
            {"$match": {"user_id": {"$ne": "system"}}},
            {"$addFields": {
                "user_obj_id": {
                    "$cond": {
                        "if": {
                            "$and": [
                                {"$eq": [{"$type": "$user_id"}, "string"]},
                                {"$eq": [{"$strLenCP": "$user_id"}, 24]}
                            ]
                        },
                        "then": {"$toObjectId": "$user_id"},
                        "else": None
                    }
                }
            }},
            {"$lookup": {
                "from": "users",
                "localField": "user_obj_id",
                "foreignField": "_id",
                "as": "user_info"
            }},
            {"$unwind": "$user_info"},
            {"$match": {"user_info.role": "user"}},
            {"$group": {
                "_id": {
                    "year": {"$year": "$timestamp"},
                    "month": {"$month": "$timestamp"},
                    "day": {"$dayOfMonth": "$timestamp"}
                },
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id.year": -1, "_id.month": -1, "_id.day": -1}},
            {"$limit": 7}
        ]
        user_activity_trend = []
        for item in logs_collection.aggregate(activity_trend_pipeline):
            y = item["_id"]["year"]
            m = item["_id"]["month"]
            d = item["_id"]["day"]
            user_activity_trend.append({
                "label": f"{d}/{m}",
                "count": item["count"]
            })
        user_activity_trend.reverse()
        
        # Saved Reports Count
        reports_count = reports_collection.count_documents({})
        
        return jsonify({
            "success": True,
            "data": {
                "total_users": total_users,
                "active_users": active_users,
                "total_invoices": total_invoices,
                "invoices_uploaded_today": invoices_today,
                "invoices_uploaded_this_month": invoices_month,
                "correction_rate": overall_correction_rate,
                "acceptance_rate": overall_acceptance_rate,
                "average_correction_rate": average_correction_rate,
                "top_uploaders": top_uploaders,
                "upload_trend_by_month": upload_trend_by_month,
                "most_active_users": most_active_users,
                "most_active_admins": most_active_admins,
                "user_activity_trend": user_activity_trend,
                "top_users_correction": top_users_correction,
                "most_corrected_invoices": most_corrected_invoices,
                "reports_count": reports_count
            }
        }), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return make_failure(f"Failed to fetch admin analytics: {str(e)}", status_code=500)


# POST /api/extract-multiple
@app.route("/api/extract-multiple", methods=["POST"])
@login_required
def extract_multiple_placeholder():
    return make_failure("Bulk processing is a planned enterprise feature and not implemented in this version.", status_code=501)


# Report-related endpoints
REPORTS_DIRECTORY = os.environ.get("REPORTS_DIRECTORY", "reports")
os.makedirs(REPORTS_DIRECTORY, exist_ok=True)

import threading
active_reports_lock = threading.Lock()
active_user_reports = set()

@app.route("/api/reports", methods=["GET"])
@login_required
def get_reports():
    try:
        user_id = request.user["id"]
        role = request.user["role"]
        
        if role == "admin":
            query = {}
        else:
            query = {"user_id": user_id}
            
        reports = list(reports_collection.find(query).sort("generated_at", DESCENDING))
        
        data = []
        for r in reports:
            data.append({
                "id": str(r["_id"]),
                "user_id": r["user_id"],
                "user_email": r.get("user_email", ""),
                "report_type": r.get("report_type", ""),
                "report_title": r.get("report_title", ""),
                "pdf_filename": r.get("pdf_filename", ""),
                "pdf_path": r.get("pdf_path", ""),
                "generated_at": r["generated_at"].isoformat() if isinstance(r["generated_at"], datetime) else r["generated_at"],
                "created_by": r.get("created_by", ""),
                "is_scheduled": r.get("is_scheduled", False),
                "schedule_type": r.get("schedule_type", None),
                "next_run": r.get("next_run").isoformat() if isinstance(r.get("next_run"), datetime) else r.get("next_run", None)
            })
            
        return jsonify({
            "success": True,
            "data": data
        }), 200
    except Exception as e:
        return make_failure(f"Failed to fetch reports: {str(e)}", status_code=500)

@app.route("/api/reports/<report_id>", methods=["GET"])
@login_required
def get_report_by_id(report_id):
    try:
        try:
            oid = ObjectId(report_id)
        except Exception:
            return make_failure("Invalid report ID format.", status_code=400)
            
        report = reports_collection.find_one({"_id": oid})
        if not report:
            return make_failure("Report not found.", status_code=404)
            
        # Ownership validation
        user_id = request.user["id"]
        role = request.user["role"]
        if role != "admin" and report.get("user_id") != user_id:
            return make_failure("Access denied. You do not own this report.", status_code=403)
            
        return jsonify({
            "success": True,
            "data": {
                "id": str(report["_id"]),
                "user_id": report["user_id"],
                "user_email": report.get("user_email", ""),
                "report_type": report.get("report_type", ""),
                "report_title": report.get("report_title", ""),
                "pdf_filename": report.get("pdf_filename", ""),
                "download_url": f"/reports/{report.get('pdf_filename')}",
                "generated_at": report["generated_at"].isoformat() if isinstance(report["generated_at"], datetime) else report["generated_at"],
                "created_by": report.get("created_by", ""),
                "is_scheduled": report.get("is_scheduled", False),
                "schedule_type": report.get("schedule_type", None),
                "next_run": report.get("next_run").isoformat() if isinstance(report.get("next_run"), datetime) else report.get("next_run", None)
            }
        }), 200
    except Exception as e:
        return make_failure(f"Failed to fetch report details: {str(e)}", status_code=500)

@app.route("/api/reports/<report_id>", methods=["DELETE"])
@login_required
def delete_report(report_id):
    try:
        try:
            oid = ObjectId(report_id)
        except Exception:
            return make_failure("Invalid report ID format.", status_code=400)
            
        report = reports_collection.find_one({"_id": oid})
        if not report:
            return make_failure("Report not found.", status_code=404)
            
        # Ownership validation
        user_id = request.user["id"]
        role = request.user["role"]
        if role != "admin" and report.get("user_id") != user_id:
            return make_failure("Access denied. You do not own this report.", status_code=403)
            
        # Delete local file
        pdf_filename = report.get("pdf_filename")
        if pdf_filename:
            if ".." in pdf_filename or "/" in pdf_filename or "\\" in pdf_filename:
                return make_failure("Invalid file path stored in report record.", status_code=400)
            file_path = os.path.join(REPORTS_DIRECTORY, pdf_filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as fe:
                    print(f"[ERROR] Failed to delete report file {file_path}: {fe}")
                    
        # Delete database record
        reports_collection.delete_one({"_id": oid})
        
        # Log deletion in activity logs
        log_activity(
            "report_deleted",
            metadata={
                "report_id": report_id,
                "report_title": report.get("report_title", ""),
                "report_type": report.get("report_type", "")
            }
        )
        
        return jsonify({
            "success": True,
            "message": "Report deleted successfully."
        }), 200
    except Exception as e:
        return make_failure(f"Failed to delete report: {str(e)}", status_code=500)

@app.route("/reports/<filename>", methods=["GET"])
@login_required
def serve_report_file(filename):
    try:
        # Path traversal checks
        if ".." in filename or "/" in filename or "\\" in filename:
            return make_failure("Access denied. Invalid filename format.", status_code=400)
            
        # Query DB to verify report exists and is registered
        report = reports_collection.find_one({"pdf_filename": filename})
        if not report:
            return make_failure("Report file not registered in database.", status_code=404)
            
        # Verify ownership permissions
        user_id = request.user["id"]
        role = request.user["role"]
        if role != "admin" and report.get("user_id") != user_id:
            return make_failure("Access denied. You do not own this report.", status_code=403)
            
        # Log download action in activity logs
        log_activity(
            "report_downloaded",
            metadata={
                "report_id": str(report["_id"]),
                "report_title": report.get("report_title", ""),
                "report_type": report.get("report_type", "")
            }
        )
        
        return send_from_directory(REPORTS_DIRECTORY, filename)
    except Exception as e:
        return make_failure(f"Failed to download report file: {str(e)}", status_code=500)


@app.route("/api/chat/query", methods=["POST"])
@login_required
def chat_query():
    try:
        body = request.get_json() or {}
        question = body.get("question", "").strip()
        if not question:
            return make_failure("Question prompt cannot be empty.", status_code=400)
            
        user_id = request.user["id"]
        user_email = request.user["email"]
        role = request.user["role"]
        
        from chatbot_service import handle_chatbot_query
        res = handle_chatbot_query(user_id, user_email, role, question)
        
        if not res.get("success", False):
            return make_failure(res.get("answer", "Failed to run chatbot query."), status_code=500)
            
        return jsonify(res), 200
    except Exception as e:
        return make_failure(f"Chatbot query processing failed: {str(e)}", status_code=500)

@app.route("/api/chat/report", methods=["POST"])
@login_required
def chat_report():
    try:
        body = request.get_json() or {}
        question = body.get("question", "").strip()
        if not question:
            return make_failure("Question prompt cannot be empty.", status_code=400)
            
        user_id = request.user["id"]
        user_email = request.user["email"]
        role = request.user["role"]
        is_admin = (role == "admin")
        
        # 1. Routing & check
        from intent_router import classify_intent
        intent, refusal_msg = classify_intent(question, is_admin=is_admin)
        if intent == "unsupported":
            return jsonify({
                "success": False,
                "message": refusal_msg
            }), 400
            
        # Duplicate Request Protection Check
        active_key = f"{user_id}:{intent}"
        with active_reports_lock:
            if active_key in active_user_reports:
                return jsonify({
                    "success": False,
                    "message": "Report generation already in progress."
                }), 409
            active_user_reports.add(active_key)
            
        try:
            # 2. Run query
            from analytics_queries import run_analytics_query
            analytics_data = run_analytics_query(intent, user_id, is_admin, question)
            if "error" in analytics_data:
                return make_failure("Database analytics execution failed.", status_code=500)
                
            total_invoices = analytics_data.get("total_invoices_in_period", 0)
            if total_invoices == 0:
                return jsonify({
                    "success": False,
                    "message": "Insufficient invoice data is available to generate this report."
                }), 400
                
            # 3. Generate summary text
            from report_generator import generate_text_summary
            summary_text = generate_text_summary(intent, analytics_data)
            error_signatures = [
                "temporarily unavailable",
                "cannot connect to Ollama",
                "exceeded the configured timeout",
                "could not be found"
            ]
            if any(sig in summary_text for sig in error_signatures):
                status_code = 503
                if "exceeded the configured timeout" in summary_text:
                    status_code = 504
                elif "could not be found" in summary_text:
                    status_code = 404
                return make_failure(summary_text, status_code=status_code)
                
            # 4. Generate PDF Report
            from pdf_generator import generate_pdf_report
            period_label = analytics_data.get("period", "Current Period")
            report_title = f"{period_label} Business Intelligence Report"
            
            # Determine creator name
            creator_name = request.user.get("name") or user_email.split("@")[0].capitalize()
            
            # Format structured data for PDF
            pdf_data = {}
            if "total_revenue" in analytics_data:
                pdf_data["Total Revenue"] = analytics_data["total_revenue"]
                pdf_data["Average Invoice Value"] = analytics_data.get("average_invoice_value", 0.0)
            if "gst_summary" in analytics_data:
                pdf_data["CGST Total"] = analytics_data["gst_summary"].get("cgst", 0.0)
                pdf_data["SGST Total"] = analytics_data["gst_summary"].get("sgst", 0.0)
                pdf_data["IGST Total"] = analytics_data["gst_summary"].get("igst", 0.0)
                pdf_data["Total GST Collected"] = analytics_data["gst_summary"].get("total_gst", 0.0)
            if "ocr_metrics" in analytics_data:
                pdf_data["OCR Scan Count"] = analytics_data["ocr_metrics"].get("total_invoices", 0)
                pdf_data["OCR Acceptance Rate"] = f"{analytics_data['ocr_metrics'].get('acceptance_rate_percent', 0.0)}%"
                pdf_data["OCR Correction Rate"] = f"{analytics_data['ocr_metrics'].get('correction_rate_percent', 0.0)}%"
                
            pdf_filename, absolute_path = generate_pdf_report(
                report_title=report_title,
                period_name=period_label,
                user_name=creator_name,
                summary_text=summary_text,
                structured_data=pdf_data,
                output_dir=REPORTS_DIRECTORY
            )
            
            # 5. Save report metadata in Reports collection
            report_doc = {
                "user_id": user_id,
                "user_email": user_email,
                "report_type": intent,
                "report_title": report_title,
                "pdf_filename": pdf_filename,
                "pdf_path": absolute_path,
                "generated_at": datetime.utcnow(),
                "created_by": user_email,
                "is_scheduled": False,
                "schedule_type": None,
                "next_run": None
            }
            
            insert_res = reports_collection.insert_one(report_doc)
            report_id = str(insert_res.inserted_id)
            
            # Log generation in activity_logs
            log_activity(
                "report_generated",
                metadata={
                    "report_id": report_id,
                    "report_title": report_title,
                    "report_type": intent
                }
            )
            
            return jsonify({
                "success": True,
                "pdf_url": f"/reports/{pdf_filename}"
            }), 200
        finally:
            with active_reports_lock:
                active_user_reports.discard(active_key)
                
    except Exception as e:
        return make_failure(f"Report generation failed: {str(e)}", status_code=500)


@app.route("/api/chat/config", methods=["GET"])
@login_required
def get_chat_config():
    try:
        return jsonify({
            "success": True,
            "chat_max_history": int(os.environ.get("CHAT_MAX_HISTORY", 50))
        }), 200
    except Exception as e:
        return make_failure(f"Failed to fetch chat config: {str(e)}", status_code=500)


@app.route("/api/admin/reports/cleanup", methods=["POST"])
@admin_required
def admin_cleanup_reports():
    try:
        retention_days = int(os.environ.get("REPORT_RETENTION_DAYS", 180))
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        # Find reports older than REPORT_RETENTION_DAYS
        old_reports = list(reports_collection.find({"generated_at": {"$lt": cutoff_date}}))
        
        deleted_reports_count = len(old_reports)
        deleted_files_count = 0
        
        # Perform check of files that will be deleted
        for report in old_reports:
            pdf_filename = report.get("pdf_filename")
            if pdf_filename and ".." not in pdf_filename and "/" not in pdf_filename and "\\" not in pdf_filename:
                file_path = os.path.join(REPORTS_DIRECTORY, pdf_filename)
                if os.path.exists(file_path):
                    deleted_files_count += 1
        
        # 9. Final Audit Enhancement: Log exactly one cleanup event per cleanup operation BEFORE deleting
        log_activity(
            "reports_cleanup",
            metadata={
                "deleted_reports": deleted_reports_count,
                "deleted_files": deleted_files_count,
                "retention_days": retention_days
            }
        )
        
        # Now delete files and records
        for report in old_reports:
            pdf_filename = report.get("pdf_filename")
            if pdf_filename and ".." not in pdf_filename and "/" not in pdf_filename and "\\" not in pdf_filename:
                file_path = os.path.join(REPORTS_DIRECTORY, pdf_filename)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as fe:
                        print(f"[ERROR] Failed to delete report file {file_path}: {fe}")
            reports_collection.delete_one({"_id": report["_id"]})
            
        return jsonify({
            "success": True,
            "deleted_reports": deleted_reports_count,
            "deleted_files": deleted_files_count
        }), 200
    except Exception as e:
        return make_failure(f"Admin reports cleanup failed: {str(e)}", status_code=500)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("backend_app:app", host="0.0.0.0", port=port, reload=False)
