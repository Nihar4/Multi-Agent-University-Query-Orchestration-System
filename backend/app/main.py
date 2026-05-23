"""FastAPI app entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, chat, tickets
from .config import get_settings
from .seed import seed_if_empty

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create tables and seed if empty (idempotent).
    if settings.AUTO_SEED:
        seed_if_empty()
    yield


app = FastAPI(
    title="University Multi-Agent Backend",
    version="0.1.0",
    description="Multi-agent orchestration with department-specific LLM agents.",
    lifespan=lifespan,
)

# CORS — wide-open for development. Tighten in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(tickets.router)


@app.get("/", tags=["health"])
def root():
    return {
        "service": "university-multi-agent",
        "env": settings.APP_ENV,
        "model": settings.LLM_MODEL,
        "status": "ok",
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
