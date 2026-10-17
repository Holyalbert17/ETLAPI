from typing import Any

from app.domain.schemas import ColumnInfo


def infer_columns(records: list[dict], *, primary_keys: set[str] | None = None) -> list[ColumnInfo]:
    primary_keys = primary_keys or {"id", "_id"}
    ordered: dict[str, str] = {}
    nullables: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        present = set(record)
        for name in ordered:
            if name not in present or record.get(name) is None:
                nullables.add(name)
        for key, value in record.items():
            if key not in ordered:
                ordered[key] = type(value).__name__ if value is not None else "null"
                if value is None:
                    nullables.add(key)
    if not ordered:
        return [ColumnInfo(name="id", type="string", nullable=True, primary_key=False)]
    return [
        ColumnInfo(
            name=name,
            type=kind,
            nullable=name in nullables,
            primary_key=name in primary_keys,
        )
        for name, kind in ordered.items()
    ]


def dig(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
