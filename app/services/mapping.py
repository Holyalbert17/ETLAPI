"""Mapeo dinámico de campos del origen al esquema canónico."""


def apply_mapping(record: dict, mapping: dict[str, str] | None) -> dict:
    if not mapping:
        return dict(record)
    mapped: dict = {}
    consumed: set[str] = set()
    for source_field, canonical_field in mapping.items():
        if source_field in record:
            mapped[canonical_field] = record[source_field]
            consumed.add(source_field)
    for key, value in record.items():
        if key not in consumed and key not in mapped:
            mapped[key] = value
    return mapped


def output_field_names(columns: list[str], mapping: dict[str, str] | None) -> list[str]:
    mapping = mapping or {}
    names: list[str] = []
    seen: set[str] = set()
    for column in columns:
        name = mapping.get(column, column)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names
