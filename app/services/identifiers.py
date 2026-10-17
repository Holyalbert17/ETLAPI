import re

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class UnsafeIdentifier(ValueError):
    pass


def validate_ident(name: str, *, what: str = "identificador") -> str:
    if not isinstance(name, str) or not IDENT_RE.match(name):
        raise UnsafeIdentifier(f"{what} no permitido: {name!r}")
    return name


def quote_ident(name: str, style: str = "ansi") -> str:
    validate_ident(name)
    if style == "mysql":
        return f"`{name}`"
    return f'"{name}"'


def qualified_name(schema: str | None, table: str, style: str = "ansi") -> str:
    table_sql = quote_ident(table, style)
    if schema:
        return f"{quote_ident(schema, style)}.{table_sql}"
    return table_sql
