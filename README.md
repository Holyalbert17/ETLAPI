# Extractor e Integrador de Datos

API para registrar orígenes heterogéneos, leer su estructura, extraer los datos en forma completa o incremental, validarlos, llevarlos a un esquema canónico, quitar duplicados y publicarlos por HTTP. Un archivo o una base con columnas distintas se da de alta con una petición: no hace falta una ruta ni una tabla nueva por cada origen.

Orígenes incluidos: PostgreSQL, MySQL, MongoDB, páginas web, CSV, Excel (`.xlsx`), JSON y API REST.

Documentación interactiva: [http://localhost:8000/docs](http://localhost:8000/docs)

## Qué hace

- Registra cada origen con su tipo, su configuración y, si hace falta, un mapeo de columnas.
- Descubre tablas, columnas y tipos, y guarda la diferencia contra el esquema anterior.
- Extrae por lotes. El modo `full` lee todo. El modo `delta` continúa desde la marca de agua de `incremental_column`.
- Normaliza fechas, montos (`$ 1.200,50`, `€ 8,50`) y valores nulos.
- Valida obligatorios, formato (email, número, fecha), rango, expresión regular y lista de valores.
- Deduplica con clave natural o con el hash del contenido. Políticas: `skip`, `update`, `upsert` y `flag`.
- Guarda el registro crudo y el registro procesado. La consulta es la misma para todos los orígenes: `GET /api/v1/data/{origen}/{tabla}`.
- Protege el acceso con JWT, cifra credenciales y deja auditoría cuando el origen marca datos personales.
- Programa extracciones con cron o con un intervalo, y reintenta un job fallido desde el último lote confirmado.
- Publica métricas para Prometheus y logs en JSON.

## Arquitectura

El núcleo no conoce PostgreSQL, Excel ni HTML. Habla con tres puertos: `BaseExtractor`, `BaseLoader` y `BaseRepository`. Cada origen es un adaptador registrado en la fábrica (`app/services/factory.py`). Los registros procesados viven en la tabla `dynamic_records` como JSON, así que una columna nueva no exige una migración.

```
origen  ->  extractor  ->  normalizar  ->  mapear  ->  validar  ->  deduplicar  ->  dynamic_records
                                                                                      |
                                                                              GET /data/{origen}/{tabla}
```

El diagrama de clases está en [docs/diagrama-clases.md](docs/diagrama-clases.md). La guía para sumar un tipo que todavía no existe está en [docs/NUEVO_ORIGEN.md](docs/NUEVO_ORIGEN.md).

## Requisitos

- Python 3.13
- Opcional: Docker y Docker Compose, si se quiere PostgreSQL, Redis y el worker en contenedores

## Arranque con Docker

```bash
cp .env.example .env
docker compose up --build
```

En Windows, si `cp` no está disponible: `copy .env.example .env`.

Eso levanta PostgreSQL 16, Redis, la API y un worker de RQ. La API escucha en el puerto 8000.

- Documentación: http://localhost:8000/docs
- Salud: http://localhost:8000/health
- Métricas: http://localhost:8000/metrics

El primer arranque crea el usuario administrador si `ADMIN_USERNAME` y `ADMIN_PASSWORD` están definidos. En `.env.example` son `admin` y `admin123`. Cámbielos antes de publicar el servicio.

Con `REDIS_URL` definido, la API encola el trabajo en la cola `extraction` y el worker lo ejecuta. Sin esa variable, la API procesa el job al terminar la petición. Así corren las pruebas y el arranque local en Windows.

## Arranque local

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
$env:DATABASE_URL = "sqlite:///./dev.db"
$env:ENABLE_SCHEDULER = "false"
$env:REDIS_URL = ""
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "admin123"
uvicorn app.main:app --reload
```

macOS o Linux:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
export DATABASE_URL="sqlite:///./dev.db"
export ENABLE_SCHEDULER=false
export REDIS_URL=
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=admin123
uvicorn app.main:app --reload
```

SQLite sirve para probar. Para PostgreSQL, deje el `DATABASE_URL` de `.env.example`, cree la base y aplique el esquema:

```bash
alembic upgrade head
```

Si `AUTO_CREATE_SCHEMA=true` (el valor por defecto), la API también crea las tablas al arrancar.

## Variables de entorno

| Variable | Para qué sirve |
| --- | --- |
| `DATABASE_URL` | Cadena SQLAlchemy. PostgreSQL en Docker; SQLite en local. |
| `REDIS_URL` | Cola RQ. Vacía: el job corre en el proceso de la API. |
| `SECRET_KEY` | Firma del JWT. |
| `ENCRYPTION_KEY` | Clave Fernet de DSN, contraseñas y tokens. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Vida del token. Por defecto, 60. |
| `BATCH_SIZE` | Filas por lote. Por defecto, 500. |
| `MAX_RETRIES` | Reintentos de conexión. |
| `RETRY_BACKOFF` | Espera entre reintentos, en segundos. |
| `USER_AGENT` | Identidad del scraper. |
| `LOG_LEVEL` | Nivel de log. |
| `ENABLE_SCHEDULER` | `true` en una sola réplica. El resto en `false`. |
| `AUTO_CREATE_SCHEMA` | Crea las tablas al arrancar. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL` | Usuario inicial. |
| `ERROR_WEBHOOK_URL` | Aviso HTTP cuando un error es crítico. |
| `CORS_ORIGINS` | Orígenes permitidos, separados por coma. |

Copie `.env.example` y no suba el `.env` al repositorio. Ya está en `.gitignore`.

## Primer uso

Entre y guarde el token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login -d "username=admin&password=admin123"
```

Registre el CSV de ejemplo, descubra el esquema, extraiga y consulte. En PowerShell puede reemplazar las barras de continuación por una sola línea.

```bash
curl -X POST http://localhost:8000/api/v1/sources \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d @examples/origen_csv.json

curl http://localhost:8000/api/v1/sources/1/schema -H "Authorization: Bearer TOKEN"
curl -X POST http://localhost:8000/api/v1/extract/1 -H "Authorization: Bearer TOKEN"
curl "http://localhost:8000/api/v1/data/clientes_csv/default?limit=50" -H "Authorization: Bearer TOKEN"
```

El mismo camino vale para los otros ejemplos:

```bash
curl -X POST http://localhost:8000/api/v1/sources -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" -d @examples/origen_excel.json
curl -X POST http://localhost:8000/api/v1/sources -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" -d @examples/origen_json.json
```

`examples/ventas.xlsx` tiene las hojas `clientes` y `pedidos`. Cada hoja es una tabla. `examples/ciudades.json` se publica como la tabla `ciudades`.

`dedup_key`, los filtros y `required_fields` usan el nombre canónico, el de después de `canonical_mapping`. `incremental_column` usa el nombre de la columna en el origen. `POST /api/v1/extract/{id}?mode=delta` lee solo lo nuevo. Un job `failed` o `partial` se reanuda con `POST /api/v1/jobs/{id}/retry`: el punto de control guarda la tabla y las filas ya confirmadas.

## API

Todas las rutas de negocio cuelgan de `/api/v1` y piden `Authorization: Bearer`. El alta pública crea usuarios con rol `user`. Extraer, reintentar y ver la auditoría piden rol `admin`.

| Método | Ruta | Qué hace |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Crea un usuario. |
| `POST` | `/api/v1/auth/login` | Devuelve el JWT. |
| `GET` | `/api/v1/auth/me` | Devuelve el usuario del token. |
| `GET` | `/api/v1/sources/types` | Lista los tipos registrados. |
| `GET` | `/api/v1/sources` | Lista los orígenes. Las credenciales salen como `***`. |
| `POST` | `/api/v1/sources` | Registra un origen. |
| `GET` | `/api/v1/sources/{id}` | Detalle de un origen. |
| `PATCH` | `/api/v1/sources/{id}` | Actualiza configuración, mapeo, horario o estado. |
| `DELETE` | `/api/v1/sources/{id}` | Borra el origen y sus registros. |
| `GET` | `/api/v1/sources/{id}/schema` | Introspección y diferencia contra el esquema guardado. |
| `POST` | `/api/v1/extract/{id}?mode=full\|delta` | Encola o ejecuta una extracción. Responde `202`. |
| `GET` | `/api/v1/jobs` | Lista ejecuciones. Acepta `source_id`. |
| `GET` | `/api/v1/jobs/{id}` | Estado, conteos y punto de control. |
| `POST` | `/api/v1/jobs/{id}/retry` | Reanuda un job fallido o parcial. |
| `GET` | `/api/v1/data/{origen}/tables` | Tablas descubiertas y ya cargadas. |
| `GET` | `/api/v1/data/{origen}/{tabla}` | Filas. Acepta `limit`, `offset`, `order_by` y `filter` (`campo:valor`). |
| `POST` | `/api/v1/data/{origen}/query` | Consulta con columnas, filtros y orden. |
| `GET` | `/api/v1/errors` | Errores de extracción. El stack queda reservado al admin. |
| `GET` | `/api/v1/audit` | Auditoría. Solo admin. |
| `GET` | `/health` | Salud del proceso. |
| `GET` | `/metrics` | Métricas Prometheus. |
| `GET` | `/docs` | Swagger. |

El contrato versionado está en `openapi.yaml`. La especificación viva es `GET /openapi.json`.

## Orígenes

| Tipo | Qué hace falta en `config` |
| --- | --- |
| `postgres` | `dsn`. Opcional: `schema`, `tables`. |
| `mysql` | `dsn` con la forma `mysql+pymysql://...`. Opcional: `schema`, `tables`. |
| `mongodb` | `uri` y `database`. |
| `csv` | `path`. Opcional: `delimiter`. |
| `excel` | `path` de un `.xlsx`. Opcional: `sheets`, `header_row` (empieza en 1). |
| `json` | `path`. Opcional: `records_path`, `table`. |
| `web` | `url`, `item_selector`, `fields`. Paginación con `next_selector` o `pagination`. |
| `api` | `url`. Opcional: `data_path`, `pagination`, cabeceras. |

En Excel, el nombre de la hoja y los encabezados se convierten en identificadores (`Hoja 1` pasa a `Hoja_1`, `precio lista` pasa a `precio_lista`). Una fila vacía se salta. Las fechas y los montos se normalizan al extraer.

El scraper envía un `User-Agent` identificable, lee `robots.txt` y espera `rate_limit` segundos entre páginas. La paginación y el enlace "siguiente" cubren listados HTML. Un scroll que solo existe en JavaScript necesita una URL de página o de "cargar más".

En `config` también pueden ir `required_fields` y `constraints`. Un constraint acepta `format` (`email`, `number`, `date`), `min`, `max`, `regex` y `enum`.

El horario (`schedule`) admite una expresión cron o un intervalo `@every 300s`.

## Duplicados

| Política | Efecto |
| --- | --- |
| `skip` | Si la clave ya existe, deja la fila anterior. |
| `update` | Actualiza la fila existente y no inserta claves nuevas. |
| `upsert` | Inserta o actualiza. Es el valor por defecto. |
| `flag` | Guarda la fila y la marca como duplicada. |

Sin `dedup_key`, la clave es el hash del contenido. Volver a ejecutar un job no duplica filas ya procesadas.

## Estructura del repositorio

```
app/
  main.py                 API, CORS, métricas y ciclo de vida
  api/routers/            auth, orígenes, esquema, datos, jobs, errores
  domain/                 modelos y esquemas Pydantic
  ports/                  BaseExtractor, BaseLoader, BaseRepository
  adapters/extractors/    postgres, mysql, mongodb, web, csv, excel, json, api
  adapters/loaders/       escritura en dynamic_records y raw_records
  services/               fábrica, extracción, validación, mapeo, deduplicación
  worker.py               tarea RQ
  scheduler.py            APScheduler
  cli.py                  comandos administrativos
examples/                 CSV, Excel, JSON y los cuerpos para registrarlos
docs/                     diagrama de clases y guía de un origen nuevo
alembic/                  migración inicial
tests/                    suite con SQLite
openapi.yaml              contrato HTTP
```

## Línea de comandos

Con el mismo entorno que la API:

```bash
python -m app.cli sources types
python -m app.cli sources list
python -m app.cli jobs list
python -m app.cli extract 1 --mode full
```

`extract` corre el job en el proceso actual, sin pasar por la cola.

## Pruebas

```bash
pytest
ruff check app tests
```

La suite usa SQLite y exige al menos 80 % de cobertura. Cubre autenticación, cifrado, CSV, Excel, JSON, mapeo, validación, deduplicación, punto de control, diferencia de esquema y los adaptadores de Postgres, web y API con dobles de prueba.

## Seguridad

- Las contraseñas se guardan con bcrypt. El acceso usa JWT en `Authorization: Bearer`.
- DSN, URI, contraseñas, tokens y cabeceras de autorización se cifran con Fernet antes de persistirse y la API los muestra como `***`.
- Los logs y los mensajes de error tapan credenciales escritas dentro de una URL.
- Filtros, orden y columnas pasan por una lista blanca de identificadores. El texto del cliente no se concatena en SQL.
- `contains_pii=true` escribe una entrada de auditoría en cada lectura.
- Borrar un origen borra sus registros.

## Despliegue

Una sola réplica debe tener `ENABLE_SCHEDULER=true`. Las demás APIs pueden dejarlo en `false` y compartir Redis. Los workers de RQ se escalan aparte. En Windows el worker de RQ no aplica: use `REDIS_URL` vacío o ejecute el worker dentro de Docker. Las extracciones son idempotentes: un reintento sigue en el punto de control y `upsert` no duplica.

## Documentación relacionada

- [Añadir un origen en menos de 15 minutos](docs/NUEVO_ORIGEN.md)
- [Diagrama de clases](docs/diagrama-clases.md)
- [Contrato OpenAPI](openapi.yaml)
