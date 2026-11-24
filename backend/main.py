"""The voiceover API. Run from backend/: uvicorn main:app --port 8000"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import router
from jobs import runner
from voiceover.core import config
from voiceover.core.exceptions import AppError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    runner.recover()
    yield


# The interactive docs are endpoints without the API key: only on when API_DOCS=on (local development).
docs = config.API_DOCS
app = FastAPI(
    title="voiceover-engine",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.exception_handler(AppError)
async def app_error(_: Request, error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"detail": str(error), "code": error.code or None})


app.include_router(router)
