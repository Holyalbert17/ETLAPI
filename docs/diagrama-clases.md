# Diagrama de clases

```mermaid
classDiagram
    class DataSource {
        +id
        +name
        +type
        +config
        +canonical_mapping
        +dedup_key
        +dedup_policy
        +schedule
        +incremental_column
        +discovered_schema
        +watermarks
    }
    class ExtractionJob {
        +id
        +source_id
        +status
        +mode
        +checkpoint
        +rows_extracted
        +bytes_read
        +http_status
    }
    class ErrorLog {
        +job_id
        +stage
        +message
        +stack_trace
        +payload
    }
    class DynamicRecord {
        +source_id
        +table_name
        +data
        +content_hash
        +natural_key
        +duplicate_flag
    }
    class RawRecord {
        +source_id
        +job_id
        +table_name
        +data
    }
    class SchemaSnapshot {
        +schema_json
        +diff_json
    }
    class User {
        +username
        +role
    }
    class AuditLog {
        +username
        +action
        +resource
    }

    DataSource "1" --> "*" ExtractionJob
    ExtractionJob "1" --> "*" ErrorLog
    DataSource "1" --> "*" DynamicRecord
    DataSource "1" --> "*" RawRecord
    DataSource "1" --> "*" SchemaSnapshot

    class BaseExtractor {
        <<interface>>
        +connect()
        +discover_schema()
        +extract(table, batch_size, checkpoint)
        +close()
    }
    class BaseLoader {
        <<interface>>
        +upsert(source_id, table, records, key)
    }
    class BaseRepository {
        <<interface>>
        +get_source()
        +save_job()
        +log_error()
        +query_dynamic()
    }

    BaseExtractor <|.. PostgresExtractor
    BaseExtractor <|.. MySQLExtractor
    BaseExtractor <|.. MongoDBExtractor
    BaseExtractor <|.. WebExtractor
    BaseExtractor <|.. CSVExtractor
    BaseExtractor <|.. ExcelExtractor
    BaseExtractor <|.. JSONExtractor
    BaseExtractor <|.. APIExtractor
    BaseLoader <|.. PostgresLoader
    BaseRepository <|.. SqlRepository

    class ExtractorService
    class SchemaDiscoveryService
    ExtractorService --> BaseExtractor
    ExtractorService --> BaseLoader
    SchemaDiscoveryService --> DataSource
```

`PostgresExtractor` y `MySQLExtractor` comparten `SQLAlchemyExtractor`.
Un adaptador nuevo hereda `BaseExtractor` y se registra con `register_extractor`.
La API no conoce el tipo concreto: `GET /data/{source}/{table}` lee `dynamic_records`.
