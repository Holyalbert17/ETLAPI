from app.adapters.extractors.sql_extractor import SQLAlchemyExtractor


class PostgresExtractor(SQLAlchemyExtractor):
    """config: dsn, schema (default public), tables opcionales, incremental vía el origen."""

    quote_style = "ansi"
    default_schema = "public"
