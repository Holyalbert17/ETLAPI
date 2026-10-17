"""Validación de tipos, obligatorios, rangos y formatos."""

import re
from typing import Any

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ValidationError(Exception):
    pass


def validate_record(
    record: dict,
    *,
    required_fields: list[str] | None = None,
    constraints: dict[str, dict[str, Any]] | None = None,
) -> dict:
    if not isinstance(record, dict):
        raise ValidationError("El registro no es un objeto")
    if not record:
        raise ValidationError("El registro está vacío")

    missing = [
        field
        for field in (required_fields or [])
        if field not in record or record[field] is None or record[field] == ""
    ]
    if missing:
        raise ValidationError(f"Faltan campos requeridos: {missing}")

    for field, rules in (constraints or {}).items():
        if field not in record or record[field] is None:
            continue
        _check_field(field, record[field], rules)
    return record


def _check_field(field: str, value: Any, rules: dict[str, Any]) -> None:
    fmt = rules.get("format")
    if fmt == "email":
        if not isinstance(value, str) or not _EMAIL.match(value):
            raise ValidationError(f"Formato de email inválido en {field}")
    elif fmt == "number":
        try:
            float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field} no es numérico") from exc
    elif fmt == "date":
        if not isinstance(value, str) or len(value) < 8:
            raise ValidationError(f"Fecha inválida en {field}")

    if "min" in rules or "max" in rules:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field} no es comparable por rango") from exc
        if "min" in rules and number < float(rules["min"]):
            raise ValidationError(f"{field} por debajo del mínimo {rules['min']}")
        if "max" in rules and number > float(rules["max"]):
            raise ValidationError(f"{field} por encima del máximo {rules['max']}")

    if "regex" in rules and isinstance(value, str):
        if re.search(rules["regex"], value) is None:
            raise ValidationError(f"{field} no cumple el patrón")

    if "enum" in rules and value not in rules["enum"]:
        raise ValidationError(f"{field} fuera de los valores permitidos")
