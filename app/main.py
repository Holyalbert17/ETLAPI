from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routers import auth, data, errors, jobs, schema, sources
from app.bootstrap import ensure_admin
from app.config import settings
from app.context import correlation_id_ctx
from app.database import Base, engine
from app.logging_config import setup_logging
from app.scheduler import start_scheduler, stop_scheduler

setup_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.domain.models  # noqa: F401

    if settings.AUTO_CREATE_SCHEMA:
        Base.metadata.create_all(bind=engine)
    ensure_admin()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Extractor e Integrador de Datos",
    version="1.0.0",
    description=(
        "API para registrar orígenes heterogéneos, introspectar su esquema, "
        "extraer, validar, deduplicar y exponer los datos sin cambiar el código."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_middleware(request, call_next):
    correlation_id = request.headers.get("x-correlation-id") or str(uuid4())
    token = correlation_id_ctx.set(correlation_id)
    try:
        response = await call_next(request)
    finally:
        correlation_id_ctx.reset(token)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(sources.router, prefix=API_PREFIX)
app.include_router(schema.router, prefix=API_PREFIX)
app.include_router(data.router, prefix=API_PREFIX)
app.include_router(jobs.router, prefix=API_PREFIX)
app.include_router(errors.router, prefix=API_PREFIX)

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "version": "1.0.0"}
