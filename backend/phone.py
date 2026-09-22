# /markbook/backend/phone.py
"""Phone numbers are stored in E.164 form (+255712345678) so they are ready for SMS/WhatsApp automation later."""
from __future__ import annotations

import re

from .config import get_config


class PhoneError(ValueError):
    pass


def normalize_phone(raw: str | None, country_code: str | None = None) -> str | None:
    """Accepts '0712 345 678', '712345678', '255712345678', '+255 712-345-678'. Returns '+255712345678' or None if blank."""
    if raw is None or not str(raw).strip():
        return None
    cc = (country_code or get_config().default_country_code).lstrip("+")
    text = str(raw).strip()
    if text.endswith(".0"):                      # numbers read from Excel as floats
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if text.startswith("+"):
        full = digits
    elif digits.startswith("00"):
        full = digits[2:]
    elif digits.startswith(cc) and len(digits) > len(cc) + 6:
        full = digits
    elif digits.startswith("0"):
        full = cc + digits[1:]
    else:
        full = cc + digits
    if not 8 <= len(full) <= 15:
        raise PhoneError(f"'{raw}' is not a valid phone number")
    if full.startswith("255") and not re.fullmatch(r"255[67]\d{8}", full):
        raise PhoneError(f"'{raw}' is not a valid Tanzanian mobile number (expected 07XX XXX XXX or 06XX XXX XXX)")
    return "+" + full


def display_phone(e164: str | None) -> str:
    """+255712345678 -> +255 712 345 678"""
    if not e164:
        return ""
    d = e164.lstrip("+")
    if d.startswith("255") and len(d) == 12:
        return f"+255 {d[3:6]} {d[6:9]} {d[9:]}"
    return e164