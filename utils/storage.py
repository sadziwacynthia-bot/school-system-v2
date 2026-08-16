import os
import uuid

import requests
from werkzeug.utils import secure_filename


def _get_supabase_settings():
    supabase_url = (
        os.getenv("SUPABASE_URL") or ""
    ).strip().rstrip("/")

    service_key = (
        os.getenv("SUPABASE_SERVICE_KEY") or ""
    ).strip()

    bucket = (
        os.getenv("SUPABASE_BUCKET") or "school-files"
    ).strip()

    if not supabase_url:
        raise RuntimeError(
            "SUPABASE_URL is missing."
        )

    if not service_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY is missing."
        )

    if not bucket:
        raise RuntimeError(
            "SUPABASE_BUCKET is missing."
        )

    return (
        supabase_url,
        service_key,
        bucket
    )


def upload_to_supabase(file_obj, folder="uploads"):
    """
    Upload a file to Supabase Storage.

    Returns:
        {
            "url": public_url,
            "path": storage_path,
            "filename": stored_filename,
            "original_filename": original_filename
        }
    """

    supabase_url, service_key, bucket = (
        _get_supabase_settings()
    )

    # -------------------------------------------------
    # VALIDATE FILE
    # -------------------------------------------------

    if not file_obj:
        raise ValueError(
            "No file was provided."
        )

    if not file_obj.filename:
        raise ValueError(
            "No file was selected."
        )

    original_filename = secure_filename(
        file_obj.filename
    )

    if not original_filename:
        raise ValueError(
            "The selected filename is invalid."
        )

    # -------------------------------------------------
    # GENERATE SAFE UNIQUE FILENAME
    # -------------------------------------------------

    if "." in original_filename:
        extension = (
            original_filename
            .rsplit(".", 1)[1]
            .lower()
        )
    else:
        extension = ""

    unique_id = uuid.uuid4().hex

    if extension:
        unique_name = (
            f"{unique_id}.{extension}"
        )
    else:
        unique_name = unique_id

    # -------------------------------------------------
    # BUILD STORAGE PATH
    # -------------------------------------------------

    clean_folder = (
        folder
        .strip()
        .strip("/")
    )

    if clean_folder:
        storage_path = (
            f"{clean_folder}/{unique_name}"
        )
    else:
        storage_path = unique_name

    # -------------------------------------------------
    # READ FILE
    # -------------------------------------------------

    try:
        file_bytes = file_obj.read()
    except Exception as error:
        raise RuntimeError(
            "EduTrack could not read the selected file."
        ) from error

    if not file_bytes:
        raise ValueError(
            "The selected file is empty."
        )

    # -------------------------------------------------
    # CONTENT TYPE
    # -------------------------------------------------

    content_type = (
        file_obj.content_type
        or "application/octet-stream"
    )

    # -------------------------------------------------
    # SUPABASE UPLOAD URL
    # -------------------------------------------------

    upload_url = (
        f"{supabase_url}"
        f"/storage/v1/object/"
        f"{bucket}/"
        f"{storage_path}"
    )

    headers = {
        "Authorization": (
            f"Bearer {service_key}"
        ),
        "apikey": service_key,
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    # -------------------------------------------------
    # UPLOAD FILE
    # -------------------------------------------------

    try:
        response = requests.post(
            upload_url,
            headers=headers,
            data=file_bytes,
            timeout=(10, 30),
        )

    except requests.exceptions.ConnectTimeout as error:
        raise RuntimeError(
            "Connection to Supabase Storage timed out."
        ) from error

    except requests.exceptions.ReadTimeout as error:
        raise RuntimeError(
            "The upload took too long to complete. "
            "Please try again."
        ) from error

    except requests.exceptions.ConnectionError as error:
        raise RuntimeError(
            "EduTrack could not connect to "
            "Supabase Storage."
        ) from error

    except requests.RequestException as error:
        raise RuntimeError(
            f"Supabase Storage request failed: {error}"
        ) from error

    # -------------------------------------------------
    # CHECK RESPONSE
    # -------------------------------------------------

    if response.status_code not in (
        200,
        201
    ):
        raise RuntimeError(
            "Supabase upload failed. "
            f"Status: {response.status_code}. "
            f"Response: {response.text}"
        )

    # -------------------------------------------------
    # PUBLIC FILE URL
    # -------------------------------------------------

    public_url = (
        f"{supabase_url}"
        f"/storage/v1/object/public/"
        f"{bucket}/"
        f"{storage_path}"
    )

    # -------------------------------------------------
    # RESULT
    # -------------------------------------------------

    return {
        "url": public_url,
        "path": storage_path,
        "filename": unique_name,
        "original_filename": (
            original_filename
        ),
    }