# Añadir un origen nuevo en menos de 15 minutos

El núcleo no se toca. Hay dos caminos.

## 1. El tipo ya existe

Postgres, MySQL, MongoDB, web, CSV, Excel, JSON y API REST ya están registrados.
Basta con `POST /api/v1/sources`. Al terminar la primera extracción, `GET /data/{nombre}/{tabla}`
responde solo.

Ejemplo CSV:

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @examples/origen_csv.json
```

Excel (cada hoja es una tabla; los encabezados se normalizan a identificadores):

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @examples/origen_excel.json
```

`dedup_key` y `required_fields` usan los nombres **canónicos** (los de `canonical_mapping`).
`incremental_column` usa el nombre de la columna en el origen. Con eso, `POST /extract/{id}?mode=delta`
lee solo lo nuevo.

## 2. Un tipo que no existe

Cree `app/adapters/extractors/mi_extractor.py`:

```python
from collections.abc import Iterator
from app.domain.schemas import ColumnInfo, SourceSchema, TableInfo
from app.ports.base_extractor import BaseExtractor
from app.services.factory import register_extractor

class MiExtractor(BaseExtractor):
    def connect(self) -> None:
        self.client = open_client(self.config["url"])

    def discover_schema(self) -> SourceSchema:
        columns = [ColumnInfo(name="id", type="string", primary_key=True)]
        return SourceSchema(tables=[TableInfo(name="default", columns=columns)])

    def extract(self, table: str, batch_size: int = 500, checkpoint: dict | None = None) -> Iterator[dict]:
        skip = int((checkpoint or {}).get("skip") or 0)
        for record in self.client.read(table, offset=skip):
            yield record

    def close(self) -> None:
        self.client.close()

register_extractor("mi_tipo", MiExtractor)
```

Importe el módulo desde `app/services/factory.py` (una línea) o, si el proceso ya está vivo,
llame a `register_extractor` desde un plugin cargado al arrancar. Después:

1. `POST /sources` con `"type": "mi_tipo"`.
2. `GET /sources/{id}/schema` para ver columnas, relaciones y el diff contra el esquema anterior.
3. `POST /extract/{id}`.
4. `GET /data/{nombre}/default`.

No hay que crear rutas, modelos ni migraciones por cada estructura: el registro vive en
`dynamic_records` y el endpoint es genérico. Si el origen gana una columna, el diff queda
en `schema_snapshots` y el JSON la guarda sin cambiar el código.
