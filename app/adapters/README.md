# Adaptadores

Cada tipo de origen implementa `BaseExtractor`. El loader `PostgresLoader` escribe el crudo
en `raw_records` y el registro normalizado en `dynamic_records`. `SqlRepository` resuelve
las consultas de la API con columnas en lista blanca.
