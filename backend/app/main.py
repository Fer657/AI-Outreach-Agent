"""FastAPI application entrypoint.

Run (from the `backend/` directory):
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.config import get_settings
from app.errors import AppError
from app.logging_config import configure_logging, get_logger
from app.rag.retriever import RagRetriever
from app.storage.db import Database

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    logger.info(
        "Starting %s v%s (mode=%s, llm=%s)",
        settings.app_name,
        settings.app_version,
        settings.research_mode,
        settings.llm_provider,
    )

    database = Database(settings.sqlite_path)
    database.init_schema()

    app.state.settings = settings
    app.state.db = database
    app.state.rag = RagRetriever(settings)

    yield

    logger.info("Shutting down.")


app = FastAPI(
    title="Northstar Labs Sales Intelligence API",
    version=__version__,
    description="Phase 2: research + signals + knowledge + problem evaluation + solution matching + outreach.",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    logger.warning("%s: %s", exc.code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "message": exc.message,
            "detail": exc.detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "The request body was invalid.",
            "detail": exc.errors(),
        },
    )


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"app": "Northstar Labs Sales Intelligence API", "docs": "/docs"}
