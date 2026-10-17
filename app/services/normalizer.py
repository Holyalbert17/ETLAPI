"""Normalización de fechas, monedas, encoding y nulos."""

import re
from datetime import date, datetime
from decimal import Decimal

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%m/%d/%Y",
)
_CURRENCY = re.compile(
    r"^\s*(?P<symbol>[$€£]|USD|EUR|MXN|ARS)\s*(?P<amount>[+-]?\d[\d.,]*)\s*$",
    re.IGNORECASE,
)
_NULL_STRINGS = {"", "null", "none", "n/a", "na", "nil"}


def _parse_date(value: str) -> str | None:
    candidate = value.strip()
    if len(candidate) < 8 or not any(ch.isdigit() for ch in candidate):
        return None
    normalized = candidate.replace("Z", "+0000")
    if len(normalized) > 5 and normalized[-3] == ":" and normalized[-6] in "+-":
        normalized = normalized[:-3] + normalized[-2:]
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        if fmt in {"%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"}:
            return parsed.date().isoformat()
        return parsed.isoformat()
    return None


def _parse_amount(amount: str) -> str | None:
    text = amount.strip()
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        tail = text.split(",")[-1]
        text = text.replace(",", ".") if len(tail) <= 2 else text.replace(",", "")
    try:
        return format(Decimal(text), "f")
    except Exception:
        return None


def normalize_scalar(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        value = value.strip()
        if value.lower() in _NULL_STRINGS:
            return None
        parsed_date = _parse_date(value)
        if parsed_date is not None and not value.replace(".", "", 1).isdigit():
            return parsed_date
        match = _CURRENCY.match(value)
        if match:
            amount = _parse_amount(match.group("amount"))
            if amount is not None:
                return amount
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    class_name = value.__class__.__name__
    if class_name in {"ObjectId", "UUID"}:
        return str(value)
    return value


def normalize_record(record: dict) -> dict:
    return {str(key): _normalize_value(val) for key, val in record.items()}


def _normalize_value(value):
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return normalize_scalar(value)


def to_jsonable(value):
    normalized = _normalize_value(value) if not isinstance(value, dict) else normalize_record(value)
    return normalized
