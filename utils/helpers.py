import random
import string
from datetime import datetime


CLASS_OPTIONS = [
    "Form 1 Grey", "Form 1 Blue",
    "Form 2 Grey", "Form 2 Blue",
    "Form 3 Grey", "Form 3 Blue",
    "Form 4 Grey", "Form 4 Blue",
    "Form 5", "Form 6"
]


def generate_student_number():
    return (
        "STU"
        + "".join(random.choices(string.ascii_uppercase, k=2))
        + "".join(random.choices(string.digits, k=4))
    )


def generate_teacher_id():
    return "TCH" + "".join(random.choices(string.digits, k=3))


def row_get(row, key, default=None):
    try:
        if row is None:
            return default
        if isinstance(row, dict):
            return row.get(key, default)
        if hasattr(row, "keys") and key not in row.keys():
            return default
        return row[key]
    except Exception:
        return default


def parse_date_safe(date_str):
    if not date_str:
        return None

    try:
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except Exception:
        return None


def get_next_class(class_name):
    promotion_map = {
        "Form 1 Grey": "Form 2 Grey",
        "Form 1 Blue": "Form 2 Blue",
        "Form 2 Grey": "Form 3 Grey",
        "Form 2 Blue": "Form 3 Blue",
        "Form 3 Grey": "Form 4 Grey",
        "Form 3 Blue": "Form 4 Blue",
        "Form 4 Grey": "Form 5",
        "Form 4 Blue": "Form 5",
        "Form 5": "Form 6",
        "Form 6": "Graduated"
    }

    return promotion_map.get(class_name, class_name)