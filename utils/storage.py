import os
import uuid
import requests
from werkzeug.utils import secure_filename

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
SUPABASE_SERVICE_KEY = (os.getenv("SUPABASE_SERVICE_KEY") or "").strip()
SUPABASE_BUCKET = (os.getenv("SUPABASE_BUCKET") or "school-files").strip()


def upload_to_supabase(file_obj, folder="uploads"):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase environment variables are missing.")

    if not file_obj or not file_obj.filename:
        raise ValueError("No file selected.")

    original_filename = secure_filename(file_obj.filename)
    ext = original_filename.rsplit(".", 1)[1].lower() if "." in original_filename else ""
    unique_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex

    folder = folder.strip().strip("/")
    path = f"{folder}/{unique_name}"

    file_bytes = file_obj.read()
    content_type = file_obj.content_type or "application/octet-stream"

    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{path}"

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    print("SUPABASE DEBUG URL:", SUPABASE_URL)
    print("SUPABASE DEBUG BUCKET:", SUPABASE_BUCKET)
    print("SUPABASE DEBUG PATH:", path)

    response = requests.post(upload_url, headers=headers, data=file_bytes)

    if response.status_code not in [200, 201]:
        raise RuntimeError(f"Supabase upload failed: {response.status_code} - {response.text}")

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{path}"

    return {
        "url": public_url,
        "path": path,
        "filename": unique_name,
        "original_filename": original_filename
    }