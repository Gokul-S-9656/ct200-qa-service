"""
Centralized configuration.

Everything the app needs from the environment is read once, here, so the
rest of the codebase never touches `os.environ` directly. This makes it
obvious what's configurable and keeps provider-swapping (e.g. mock -> Groq)
to a one-line change in .env.

Built on pydantic-settings rather than a plain class reading os.getenv:
a typo'd boolean, a negative timeout, or LLM_PROVIDER="grok" (vs "groq")
used to be silent until it hit the code path that broke at request time.
Pydantic validates once, at import time, so a bad .env fails the moment
the process starts (`uvicorn` refuses to boot) instead of surfacing as a
confusing 500 to whoever happens to hit the affected endpoint first.
"""
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["mock", "groq"] = "mock"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    database_url: str = "sqlite:///./ct200.db"
    tinydb_path: str = "./tinydb_generations.json"
    manual_path: str = "./data/ct200_manual.md"

    # Comma-separated list in .env, e.g. "http://localhost:3000,https://app.example.com"
    cors_allow_origins: str = ""

    max_upload_size_bytes: int = Field(default=2 * 1024 * 1024, gt=0)  # 2 MB

    @field_validator("groq_api_key")
    @classmethod
    def _strip_key(cls, value: str) -> str:
        # Defends against a trailing newline from a copy-pasted .env value,
        # which otherwise turns into an invalid Authorization header that
        # fails with a confusing error far from its actual cause.
        return value.strip()

    @model_validator(mode="after")
    def _require_key_for_groq(self) -> "Settings":
        if self.llm_provider == "groq" and not self.groq_api_key:
            raise ValueError(
                "LLM_PROVIDER=groq requires GROQ_API_KEY to be set. "
                "Get a free key at https://console.groq.com/keys, or set "
                "LLM_PROVIDER=mock."
            )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


settings = Settings()
