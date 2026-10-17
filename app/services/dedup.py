"""Deduplicación por clave natural o hash de contenido."""

import hashlib
import json


def content_hash(record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def natural_key(record: dict, keys: list[str] | None) -> str | None:
    if not keys:
        return None
    value = "|".join("" if record.get(key) is None else str(record.get(key)) for key in keys)
    return value[:500]


def advance_watermark(current: str | None, values: list) -> str | None:
    cleaned = [value for value in values if value is not None and value != ""]
    if current is not None:
        cleaned.append(current)
    if not cleaned:
        return current

    def as_number(value: str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    numbers = [as_number(str(value)) for value in cleaned]
    if all(number is not None for number in numbers):
        best = max(numbers)
        if float(best).is_integer():
            return str(int(best))
        return format(best, "f").rstrip("0").rstrip(".")
    return max(str(value) for value in cleaned)
