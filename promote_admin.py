import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

# Load env variables from root path .env file
load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "invoice_ocr")

if not MONGO_URI:
    print("[ERROR] MONGODB_URI environment variable is not defined in the root .env file.")
    sys.exit(1)

def promote_user(email):
    print(f"Connecting to database: {DB_NAME}...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    users_col = db["users"]
    
    # Check if user exists by email address
    user = users_col.find_one({"email": email})
    if not user:
        print(f"[WARNING] User with email '{email}' was not found in the users database collection.")
        # Ask to pre-register admin role
        confirm = input("Would you like to pre-register this email as an administrator? (y/n): ")
        if confirm.lower() == 'y':
            from datetime import datetime
            result = users_col.insert_one({
                "google_id": "", # Will be filled automatically during their first OAuth login
                "name": email.split("@")[0].capitalize(),
                "email": email,
                "picture": "",
                "role": "admin",
                "is_active": True,
                "created_at": datetime.utcnow(),
                "last_login": None
            })
            print(f"[SUCCESS] Pre-registered admin user: {email} (ID: {result.inserted_id})")
        else:
            print("Operation cancelled.")
            sys.exit(0)
    else:
        # Check current role
        if user.get("role") == "admin":
            print(f"[INFO] User '{email}' already has the 'admin' role.")
            sys.exit(0)
            
        # Update user to admin role and ensure active status
        users_col.update_one(
            {"_id": user["_id"]},
            {"$set": {"role": "admin", "is_active": True}}
        )
        print(f"[SUCCESS] User '{email}' successfully promoted to 'admin' role.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python promote_admin.py <user_email>")
        print("Example: python promote_admin.py admin@invoiceocr.com")
        sys.exit(1)
    
    email_to_promote = sys.argv[1].strip()
    promote_user(email_to_promote)
