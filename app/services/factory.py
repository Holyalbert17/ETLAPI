from app.adapters.extractors.api_extractor import APIExtractor
from app.adapters.extractors.csv_extractor import CSVExtractor
from app.adapters.extractors.excel_extractor import ExcelExtractor
from app.adapters.extractors.json_extractor import JSONExtractor
from app.adapters.extractors.mongodb_extractor import MongoDBExtractor
from app.adapters.extractors.mysql_extractor import MySQLExtractor
from app.adapters.extractors.postgres_extractor import PostgresExtractor
from app.adapters.extractors.web_extractor import WebExtractor
from app.ports.base_extractor import BaseExtractor

REGISTRY: dict[str, type[BaseExtractor]] = {}


def register_extractor(name: str, cls: type[BaseExtractor]) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError("El nombre del adaptador es obligatorio")
    if not isinstance(cls, type) or not issubclass(cls, BaseExtractor):
        raise TypeError("El adaptador debe heredar de BaseExtractor")
    REGISTRY[name] = cls


def get_extractor(source_type: str, config: dict) -> BaseExtractor:
    cls = REGISTRY.get(source_type)
    if cls is None:
        available = ", ".join(sorted(REGISTRY)) or "(ninguno)"
        raise ValueError(f"Tipo de origen no soportado: {source_type}. Disponibles: {available}")
    return cls(config)


def list_extractors() -> list[str]:
    return sorted(REGISTRY)


register_extractor("postgres", PostgresExtractor)
register_extractor("mysql", MySQLExtractor)
register_extractor("mongodb", MongoDBExtractor)
register_extractor("web", WebExtractor)
register_extractor("csv", CSVExtractor)
register_extractor("excel", ExcelExtractor)
register_extractor("json", JSONExtractor)
register_extractor("api", APIExtractor)
