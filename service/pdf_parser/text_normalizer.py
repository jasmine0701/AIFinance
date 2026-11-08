import re
import math

def normalize_number(text_val: str) -> float:
    if not text_val or not isinstance(text_val, str):
        return 0.0

    text_val = text_val.strip()
    is_negative = False

    if text_val.startswith("(") and text_val.endswith(")"):
        is_negative = True
        text_val = text_val[1:-1]
    elif text_val.startswith("-"):
        is_negative = True
        text_val = text_val[1:]

    text_val = text_val.replace(" ", "").replace("\xa0", "")

    if "." in text_val and "," in text_val:
        if text_val.rfind(".") > text_val.rfind(","):
            text_val = text_val.replace(",", "")
        else:
            text_val = text_val.replace(".", "").replace(",", ".")
    elif "," in text_val:
        parts = text_val.split(",")
        if len(parts[-1]) == 3:
            text_val = text_val.replace(",", "")
        else:
            text_val = text_val.replace(",", ".")
    elif "." in text_val:
        parts = text_val.split(".")
        # ИСПРАВЛЕНИЕ: Если после точки ровно 3 цифры, считаем ее разделителем тысяч (254.749 -> 254749)
        if len(parts[-1]) == 3:
            text_val = text_val.replace(".", "")

    try:
        val = float(text_val)
        return -val if is_negative else val
    except ValueError:
        return 0.0