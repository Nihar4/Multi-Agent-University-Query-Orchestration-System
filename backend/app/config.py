"""Application configuration loaded from environment variables (or .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# .env lives at the repo root (one level above backend/)
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: str = "development"

    # SQLite by default — a single file at repo root.
    DATABASE_URL: str = f"sqlite:///{_REPO_ROOT / 'university_mock.db'}"

    # JWT
    JWT_SECRET: str = "change-me-in-prod-please"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # LLM (NVIDIA NIM is OpenAI-compatible)
    LLM_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    LLM_MODEL: str = "openai/gpt-oss-120b"
    LLM_API_KEY: str = ""

    # Auto-seed dummy data on startup if true
    AUTO_SEED: bool = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
