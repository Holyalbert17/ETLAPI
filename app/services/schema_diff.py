"""Diff estructural entre el esquema previo y el recién introspectado."""

from typing import Any


def diff_schemas(previous: dict | None, current: dict) -> dict[str, Any]:
    prev_tables = {table["name"]: table for table in (previous or {}).get("tables", [])}
    curr_tables = {table["name"]: table for table in current.get("tables", [])}
    added = sorted(set(curr_tables) - set(prev_tables))
    removed = sorted(set(prev_tables) - set(curr_tables))
    added_columns: dict[str, list[str]] = {}
    removed_columns: dict[str, list[str]] = {}
    type_changes: dict[str, list[dict]] = {}

    for name, table in curr_tables.items():
        if name not in prev_tables:
            continue
        prev_cols = {col["name"]: col for col in prev_tables[name].get("columns", [])}
        curr_cols = {col["name"]: col for col in table.get("columns", [])}
        added_cols = sorted(set(curr_cols) - set(prev_cols))
        removed_cols = sorted(set(prev_cols) - set(curr_cols))
        changes = []
        for col_name, info in curr_cols.items():
            if col_name in prev_cols and str(prev_cols[col_name].get("type")) != str(info.get("type")):
                changes.append(
                    {
                        "column": col_name,
                        "from": prev_cols[col_name].get("type"),
                        "to": info.get("type"),
                    }
                )
        if added_cols:
            added_columns[name] = added_cols
        if removed_cols:
            removed_columns[name] = removed_cols
        if changes:
            type_changes[name] = changes

    changed = bool(added or removed or added_columns or removed_columns or type_changes)
    return {
        "changed": changed,
        "added_tables": added,
        "removed_tables": removed,
        "added_columns": added_columns,
        "removed_columns": removed_columns,
        "type_changes": type_changes,
    }


def allowed_columns(source_schema: dict | None, table: str, mapping: dict | None) -> set[str] | None:
    """None significa que todavía no hay esquema guardado y solo aplica la regex."""
    if not source_schema:
        return None
    mapping = mapping or {}
    for item in source_schema.get("tables", []):
        if item.get("name") != table:
            continue
        names = {mapping.get(col["name"], col["name"]) for col in item.get("columns", [])}
        for target in mapping.values():
            names.add(target)
        return names
    return set()
