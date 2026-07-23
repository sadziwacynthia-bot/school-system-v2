"""
EduTrack Branding Engine
DF Technologies

This module manages:

- School identity settings
- Logo, stamp and signature uploads
- Theme colors
- Report display options
- Branding asset retrieval and deletion

The module works with both SQLite and PostgreSQL through utils.db.
"""

import re
from typing import Any, Dict, Optional

from werkzeug.utils import secure_filename

from utils.db import fetch_one, execute_commit, is_postgres


# ============================================================
# Branding configuration
# ============================================================

MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 MB

ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}

ALLOWED_IMAGE_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp",
}

DEFAULT_PRIMARY_COLOR = "#2563EB"
DEFAULT_SECONDARY_COLOR = "#7C3AED"
DEFAULT_ACCENT_COLOR = "#F59E0B"
DEFAULT_REPORT_TEMPLATE = "classic"

VALID_REPORT_TEMPLATES = {
    "classic",
    "modern",
    "minimal",
}

ASSET_FIELDS = {
    "logo": {
        "data": "logo_data",
        "filename": "logo_filename",
        "mime_type": "logo_mime_type",
    },
    "stamp": {
        "data": "stamp_data",
        "filename": "stamp_filename",
        "mime_type": "stamp_mime_type",
    },
    "head_signature": {
        "data": "head_signature_data",
        "filename": "head_signature_filename",
        "mime_type": "head_signature_mime_type",
    },
    "bursar_signature": {
        "data": "bursar_signature_data",
        "filename": "bursar_signature_filename",
        "mime_type": "bursar_signature_mime_type",
    },
}

REPORT_OPTION_FIELDS = {
    "show_logo",
    "show_stamp",
    "show_head_signature",
    "show_bursar_signature",
    "show_position",
    "show_attendance",
    "show_conduct",
}


# ============================================================
# General helpers
# ============================================================

def row_to_dict(row: Any) -> Optional[Dict[str, Any]]:
    """
    Convert sqlite3.Row or PostgreSQL RealDictRow to a normal dictionary.
    """
    if row is None:
        return None

    if isinstance(row, dict):
        return dict(row)

    try:
        return dict(row)
    except (TypeError, ValueError):
        return None


def clean_text(value: Any, default: str = "") -> str:
    """
    Convert a submitted value into trimmed text.
    """
    if value is None:
        return default

    return str(value).strip()


def normalize_optional_date(value: Any) -> Optional[str]:
    """
    Return a date string or None when the submitted value is empty.
    """
    cleaned = clean_text(value)

    if not cleaned:
        return None

    return cleaned


def normalize_boolean(value: Any, default: bool = False) -> bool:
    """
    Convert HTML form, SQLite or PostgreSQL values into a Python boolean.
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value == 1

    normalized = str(value).strip().lower()

    return normalized in {
        "1",
        "true",
        "yes",
        "on",
        "checked",
    }


def database_boolean(value: Any):
    """
    Return the correct boolean representation for the active database.
    """
    normalized = normalize_boolean(value)

    if is_postgres():
        return normalized

    return 1 if normalized else 0


def normalize_color(value: Any, default: str) -> str:
    """
    Validate a hexadecimal color.

    Accepted format:
        #2563EB
    """
    cleaned = clean_text(value)

    if not cleaned:
        return default

    if not cleaned.startswith("#"):
        cleaned = f"#{cleaned}"

    cleaned = cleaned.upper()

    if not re.fullmatch(r"#[0-9A-F]{6}", cleaned):
        raise ValueError(
            f"Invalid color value '{value}'. "
            "Colors must use the format #RRGGBB."
        )

    return cleaned


def normalize_report_template(value: Any) -> str:
    """
    Validate the selected report template.
    """
    template = clean_text(value, DEFAULT_REPORT_TEMPLATE).lower()

    if template not in VALID_REPORT_TEMPLATES:
        return DEFAULT_REPORT_TEMPLATE

    return template


def allowed_image_extension(filename: str) -> bool:
    """
    Check whether a filename uses an accepted image extension.
    """
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_IMAGE_EXTENSIONS


# ============================================================
# Branding row management
# ============================================================

def branding_record_exists(school_id: Any) -> bool:
    """
    Check whether the school already has a school_settings record.
    """
    if not school_id:
        return False

    row = fetch_one(
        """
        SELECT id
        FROM school_settings
        WHERE school_id = ?
        """,
        (school_id,),
    )

    return row is not None


def ensure_branding_record(school_id: Any) -> None:
    """
    Create a default school_settings record if one does not exist.
    """
    if not school_id:
        raise ValueError("School ID is required.")

    if branding_record_exists(school_id):
        return

    school = fetch_one(
        """
        SELECT school_name
        FROM schools
        WHERE id = ?
        """,
        (school_id,),
    )

    school_dict = row_to_dict(school) or {}
    display_name = clean_text(
        school_dict.get("school_name"),
        "EduTrack School",
    )

    execute_commit(
        """
        INSERT INTO school_settings (
            school_id,
            display_name,
            phone,
            email,
            address,
            report_header,
            logo_url,
            motto,
            opening_date,
            closing_date,
            primary_color,
            secondary_color,
            accent_color,
            report_template,
            show_logo,
            show_stamp,
            show_head_signature,
            show_bursar_signature,
            show_position,
            show_attendance,
            show_conduct
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            school_id,
            display_name,
            "",
            "",
            "",
            "School Management System",
            "",
            "",
            None,
            None,
            DEFAULT_PRIMARY_COLOR,
            DEFAULT_SECONDARY_COLOR,
            DEFAULT_ACCENT_COLOR,
            DEFAULT_REPORT_TEMPLATE,
            database_boolean(True),
            database_boolean(True),
            database_boolean(True),
            database_boolean(True),
            database_boolean(True),
            database_boolean(True),
            database_boolean(True),
        ),
    )


def get_branding(school_id: Any) -> Optional[Dict[str, Any]]:
    """
    Retrieve all branding settings for a school.

    The returned dictionary contains normalized colors, report options
    and asset availability fields.
    """
    if not school_id:
        return None

    ensure_branding_record(school_id)

    row = fetch_one(
        """
        SELECT *
        FROM school_settings
        WHERE school_id = ?
        """,
        (school_id,),
    )

    branding = row_to_dict(row)

    if not branding:
        return None

    branding["display_name"] = clean_text(
        branding.get("display_name"),
        "EduTrack School",
    )

    branding["motto"] = clean_text(branding.get("motto"))
    branding["phone"] = clean_text(branding.get("phone"))
    branding["email"] = clean_text(branding.get("email"))
    branding["address"] = clean_text(branding.get("address"))

    branding["report_header"] = clean_text(
        branding.get("report_header"),
        "School Management System",
    )

    branding["logo_url"] = clean_text(branding.get("logo_url"))

    branding["primary_color"] = normalize_color(
        branding.get("primary_color"),
        DEFAULT_PRIMARY_COLOR,
    )

    branding["secondary_color"] = normalize_color(
        branding.get("secondary_color"),
        DEFAULT_SECONDARY_COLOR,
    )

    branding["accent_color"] = normalize_color(
        branding.get("accent_color"),
        DEFAULT_ACCENT_COLOR,
    )

    branding["report_template"] = normalize_report_template(
        branding.get("report_template")
    )

    for option_name in REPORT_OPTION_FIELDS:
        branding[option_name] = normalize_boolean(
            branding.get(option_name),
            default=True,
        )

    for asset_name, fields in ASSET_FIELDS.items():
        branding[f"has_{asset_name}"] = bool(
            branding.get(fields["data"])
        )

    return branding


# ============================================================
# School identity
# ============================================================

def save_school_identity(
    school_id: Any,
    display_name: Any,
    motto: Any = "",
    phone: Any = "",
    email: Any = "",
    address: Any = "",
    report_header: Any = "",
    logo_url: Any = "",
    opening_date: Any = None,
    closing_date: Any = None,
) -> None:
    """
    Save school identity and contact information.
    """
    if not school_id:
        raise ValueError("School ID is required.")

    ensure_branding_record(school_id)

    cleaned_display_name = clean_text(display_name)

    if not cleaned_display_name:
        raise ValueError("School display name is required.")

    execute_commit(
        """
        UPDATE school_settings
        SET
            display_name = ?,
            motto = ?,
            phone = ?,
            email = ?,
            address = ?,
            report_header = ?,
            logo_url = ?,
            opening_date = ?,
            closing_date = ?
        WHERE school_id = ?
        """,
        (
            cleaned_display_name,
            clean_text(motto),
            clean_text(phone),
            clean_text(email),
            clean_text(address),
            clean_text(
                report_header,
                "School Management System",
            ),
            clean_text(logo_url),
            normalize_optional_date(opening_date),
            normalize_optional_date(closing_date),
            school_id,
        ),
    )


# ============================================================
# Image validation and storage
# ============================================================

def validate_uploaded_image(uploaded_file) -> Dict[str, Any]:
    """
    Validate a Flask FileStorage image and return its safe contents.

    Returns:
        {
            "data": bytes,
            "filename": str,
            "mime_type": str
        }
    """
    if uploaded_file is None:
        raise ValueError("No image was selected.")

    original_filename = clean_text(
        getattr(uploaded_file, "filename", "")
    )

    if not original_filename:
        raise ValueError("No image was selected.")

    safe_filename = secure_filename(original_filename)

    if not safe_filename:
        raise ValueError("The uploaded image filename is invalid.")

    if not allowed_image_extension(safe_filename):
        raise ValueError(
            "Please upload a PNG, JPG, JPEG or WEBP image."
        )

    mime_type = clean_text(
        getattr(uploaded_file, "mimetype", "")
    ).lower()

    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError(
            "Please upload a PNG, JPG, JPEG or WEBP image."
        )

    image_data = uploaded_file.read()

    if not image_data:
        raise ValueError("The uploaded image is empty.")

    if len(image_data) > MAX_IMAGE_SIZE:
        raise ValueError(
            "Branding images must be smaller than 2 MB."
        )

    try:
        uploaded_file.stream.seek(0)
    except (AttributeError, OSError):
        pass

    return {
        "data": image_data,
        "filename": safe_filename,
        "mime_type": mime_type,
    }


def save_branding_asset(
    school_id: Any,
    asset_name: str,
    uploaded_file,
) -> Dict[str, Any]:
    """
    Save one branding image.

    Valid asset names:
        logo
        stamp
        head_signature
        bursar_signature
    """
    if not school_id:
        raise ValueError("School ID is required.")

    if asset_name not in ASSET_FIELDS:
        raise ValueError("Invalid branding asset type.")

    ensure_branding_record(school_id)

    validated = validate_uploaded_image(uploaded_file)
    fields = ASSET_FIELDS[asset_name]

    query = f"""
        UPDATE school_settings
        SET
            {fields["data"]} = ?,
            {fields["filename"]} = ?,
            {fields["mime_type"]} = ?
        WHERE school_id = ?
    """

    execute_commit(
        query,
        (
            validated["data"],
            validated["filename"],
            validated["mime_type"],
            school_id,
        ),
    )

    return {
        "asset_name": asset_name,
        "filename": validated["filename"],
        "mime_type": validated["mime_type"],
        "size": len(validated["data"]),
    }


def get_branding_asset(
    school_id: Any,
    asset_name: str,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve one branding image from the database.
    """
    if not school_id:
        return None

    if asset_name not in ASSET_FIELDS:
        raise ValueError("Invalid branding asset type.")

    fields = ASSET_FIELDS[asset_name]

    query = f"""
        SELECT
            {fields["data"]} AS asset_data,
            {fields["filename"]} AS asset_filename,
            {fields["mime_type"]} AS asset_mime_type
        FROM school_settings
        WHERE school_id = ?
    """

    row = fetch_one(query, (school_id,))
    asset = row_to_dict(row)

    if not asset or not asset.get("asset_data"):
        return None

    asset_data = asset["asset_data"]

    if not isinstance(asset_data, bytes):
        asset_data = bytes(asset_data)

    return {
        "data": asset_data,
        "filename": (
            asset.get("asset_filename")
            or f"{asset_name}.png"
        ),
        "mime_type": (
            asset.get("asset_mime_type")
            or "image/png"
        ),
    }


def delete_branding_asset(
    school_id: Any,
    asset_name: str,
) -> None:
    """
    Remove one branding asset from a school.
    """
    if not school_id:
        raise ValueError("School ID is required.")

    if asset_name not in ASSET_FIELDS:
        raise ValueError("Invalid branding asset type.")

    ensure_branding_record(school_id)

    fields = ASSET_FIELDS[asset_name]

    query = f"""
        UPDATE school_settings
        SET
            {fields["data"]} = NULL,
            {fields["filename"]} = NULL,
            {fields["mime_type"]} = NULL
        WHERE school_id = ?
    """

    execute_commit(query, (school_id,))


# ============================================================
# Convenience image functions
# ============================================================

def save_logo(school_id: Any, uploaded_file):
    return save_branding_asset(
        school_id,
        "logo",
        uploaded_file,
    )


def save_stamp(school_id: Any, uploaded_file):
    return save_branding_asset(
        school_id,
        "stamp",
        uploaded_file,
    )


def save_head_signature(school_id: Any, uploaded_file):
    return save_branding_asset(
        school_id,
        "head_signature",
        uploaded_file,
    )


def save_bursar_signature(school_id: Any, uploaded_file):
    return save_branding_asset(
        school_id,
        "bursar_signature",
        uploaded_file,
    )


def get_logo(school_id: Any):
    return get_branding_asset(school_id, "logo")


def get_stamp(school_id: Any):
    return get_branding_asset(school_id, "stamp")


def get_head_signature(school_id: Any):
    return get_branding_asset(
        school_id,
        "head_signature",
    )


def get_bursar_signature(school_id: Any):
    return get_branding_asset(
        school_id,
        "bursar_signature",
    )


def delete_logo(school_id: Any):
    delete_branding_asset(school_id, "logo")


def delete_stamp(school_id: Any):
    delete_branding_asset(school_id, "stamp")


def delete_head_signature(school_id: Any):
    delete_branding_asset(
        school_id,
        "head_signature",
    )


def delete_bursar_signature(school_id: Any):
    delete_branding_asset(
        school_id,
        "bursar_signature",
    )


# ============================================================
# Theme settings
# ============================================================

def save_theme(
    school_id: Any,
    primary_color: Any,
    secondary_color: Any,
    accent_color: Any,
) -> Dict[str, str]:
    """
    Save the school's interface and document theme colors.
    """
    if not school_id:
        raise ValueError("School ID is required.")

    ensure_branding_record(school_id)

    primary = normalize_color(
        primary_color,
        DEFAULT_PRIMARY_COLOR,
    )

    secondary = normalize_color(
        secondary_color,
        DEFAULT_SECONDARY_COLOR,
    )

    accent = normalize_color(
        accent_color,
        DEFAULT_ACCENT_COLOR,
    )

    execute_commit(
        """
        UPDATE school_settings
        SET
            primary_color = ?,
            secondary_color = ?,
            accent_color = ?
        WHERE school_id = ?
        """,
        (
            primary,
            secondary,
            accent,
            school_id,
        ),
    )

    return {
        "primary_color": primary,
        "secondary_color": secondary,
        "accent_color": accent,
    }


def reset_theme(school_id: Any) -> Dict[str, str]:
    """
    Reset theme colors to EduTrack defaults.
    """
    return save_theme(
        school_id,
        DEFAULT_PRIMARY_COLOR,
        DEFAULT_SECONDARY_COLOR,
        DEFAULT_ACCENT_COLOR,
    )


# ============================================================
# Report settings
# ============================================================

def save_report_options(
    school_id: Any,
    report_template: Any = DEFAULT_REPORT_TEMPLATE,
    show_logo: Any = False,
    show_stamp: Any = False,
    show_head_signature: Any = False,
    show_bursar_signature: Any = False,
    show_position: Any = False,
    show_attendance: Any = False,
    show_conduct: Any = False,
) -> Dict[str, Any]:
    """
    Save report layout and visibility options.

    HTML checkboxes that are not selected are normally absent from
    request.form, so their route values should default to False.
    """
    if not school_id:
        raise ValueError("School ID is required.")

    ensure_branding_record(school_id)

    template = normalize_report_template(report_template)

    options = {
        "show_logo": normalize_boolean(show_logo),
        "show_stamp": normalize_boolean(show_stamp),
        "show_head_signature": normalize_boolean(
            show_head_signature
        ),
        "show_bursar_signature": normalize_boolean(
            show_bursar_signature
        ),
        "show_position": normalize_boolean(show_position),
        "show_attendance": normalize_boolean(show_attendance),
        "show_conduct": normalize_boolean(show_conduct),
    }

    execute_commit(
        """
        UPDATE school_settings
        SET
            report_template = ?,
            show_logo = ?,
            show_stamp = ?,
            show_head_signature = ?,
            show_bursar_signature = ?,
            show_position = ?,
            show_attendance = ?,
            show_conduct = ?
        WHERE school_id = ?
        """,
        (
            template,
            database_boolean(options["show_logo"]),
            database_boolean(options["show_stamp"]),
            database_boolean(
                options["show_head_signature"]
            ),
            database_boolean(
                options["show_bursar_signature"]
            ),
            database_boolean(options["show_position"]),
            database_boolean(options["show_attendance"]),
            database_boolean(options["show_conduct"]),
            school_id,
        ),
    )

    return {
        "report_template": template,
        **options,
    }


def get_report_options(school_id: Any) -> Optional[Dict[str, Any]]:
    """
    Return only report-related branding settings.
    """
    branding = get_branding(school_id)

    if not branding:
        return None

    return {
        "report_template": branding["report_template"],
        "show_logo": branding["show_logo"],
        "show_stamp": branding["show_stamp"],
        "show_head_signature": branding[
            "show_head_signature"
        ],
        "show_bursar_signature": branding[
            "show_bursar_signature"
        ],
        "show_position": branding["show_position"],
        "show_attendance": branding["show_attendance"],
        "show_conduct": branding["show_conduct"],
    }