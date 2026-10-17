from prometheus_client import Counter, Gauge, Histogram

EXTRACTIONS_TOTAL = Counter(
    "extractions_total", "Total de extracciones", ["source", "status"]
)
ROWS_EXTRACTED = Counter("rows_extracted_total", "Filas extraídas", ["source", "table"])
ROWS_INSERTED = Counter("rows_inserted_total", "Filas insertadas", ["source", "table"])
ROWS_UPDATED = Counter("rows_updated_total", "Filas actualizadas", ["source", "table"])
ROWS_DUPLICATED = Counter("rows_duplicated_total", "Filas duplicadas", ["source", "table"])
EXTRACTION_DURATION = Histogram(
    "extraction_duration_seconds", "Duración de extracción", ["source"]
)
ACTIVE_JOBS = Gauge("active_jobs", "Jobs activos")
ERRORS_TOTAL = Counter("errors_total", "Errores registrados", ["source", "stage"])
