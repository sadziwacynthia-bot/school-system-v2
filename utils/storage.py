import os
import uuid

import requests
from werkzeug.utils import secure_filename


def _get_supabase_settings():
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = (os.getenv("SUPABASE_SERVICE_KEY") or "").strip()
    bucket = (os.getenv("SUPABASE_BUCKET") or "school-files").strip()

    if not supabase_url:
        raise RuntimeError("SUPABASE_URL is missing.")

    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_KEY is missing.")

    if not bucket:
        raise RuntimeError("SUPABASE_BUCKET is missing.")

    return supabase_url, service_key, bucket


def upload_to_supabase(file_obj, folder="uploads"):
    supabase_url, service_key, bucket = _get_supabase_settings()

    if not file_obj or not file_obj.filename:
        raise ValueError("No file selected.")

    original_filename = secure_filename(file_obj.filename)

    if not original_filename:
        raise ValueError("Invalid filename.")

    extension = (
        original_filename.rsplit(".", 1)[1].lower()
        if "." in original_filename
        else ""
    )

    unique_name = (
        f"{uuid.uuid4().hex}.{extension}"
        if extension
        else uuid.uuid4().hex
    )

    clean_folder = folder.strip().strip("/")
    path = f"{clean_folder}/{unique_name}"

    file_bytes = file_obj.read()

    if not file_bytes:
        raise ValueError("The selected file is empty.")

    content_type = file_obj.content_type or "application/octet-stream"

    upload_url = (
        f"{supabase_url}/storage/v1/object/"
        f"{bucket}/{path}"
    )

    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    try:
        response = requests.post(
            upload_url,
            headers=headers,
            data=file_bytes,
            timeout=45,
        )
    except requests.RequestException as error:
        raise RuntimeError(
            f"Could not connect to Supabase Storage: {error}"
        ) from error

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Supabase upload failed: "
            f"{response.status_code} - {response.text}"
        )

    public_url = (
        f"{supabase_url}/storage/v1/object/public/"
        f"{bucket}/{path}"
    )

    return {
        "url": public_url,
        "path": path,
        "filename": unique_name,
        "original_filename": original_filename,
    }