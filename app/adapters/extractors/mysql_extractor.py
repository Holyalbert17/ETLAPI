from app.adapters.extractors.sql_extractor import SQLAlchemyExtractor


class MySQLExtractor(SQLAlchemyExtractor):
    """config: {"dsn": "mysql+pymysql://user:pass@host:3306/db", "schema": "db"}."""

    quote_style = "mysql"
    default_schema = None
