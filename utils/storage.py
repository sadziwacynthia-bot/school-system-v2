import os
import uuid
from werkzeug.utils import secure_filename
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = (os.getenv("SUPABASE_BUCKET") or "school-files").strip()


def get_supabase_client():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase environment variables are missing.")

    return create_client(SUPABASE_URL.strip(), SUPABASE_SERVICE_KEY.strip())


def upload_to_supabase(file_obj, folder="uploads"):
    if not file_obj or not file_obj.filename:
        raise ValueError("No file selected.")

    original_filename = secure_filename(file_obj.filename)
    ext = original_filename.rsplit(".", 1)[1].lower() if "." in original_filename else ""
    unique_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex

    folder = folder.strip().strip("/")
    path = f"{folder}/{unique_name}"

    file_bytes = file_obj.read()
    content_type = file_obj.content_type or "application/octet-stream"

    print("SUPABASE DEBUG URL:", SUPABASE_URL)
    print("SUPABASE DEBUG BUCKET:", SUPABASE_BUCKET)
    print("SUPABASE DEBUG PATH:", path)

    supabase = get_supabase_client()

    result = supabase.storage.from_(SUPABASE_BUCKET).upload(
        path=path,
        file=file_bytes,
        file_options={
            "content-type": content_type,
            "upsert": "true"
        }
    )

    public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(path)

    return {
        "url": public_url,
        "path": path,
        "filename": unique_name,
        "original_filename": original_filename
    }