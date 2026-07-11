"""
Centralized configuration.

Everything the app needs from the environment is read once, here, so the
rest of the codebase never touches `os.environ` directly. This makes it
obvious what's configurable and keeps provider-swapping (e.g. mock -> Groq)
to a one-line change in .env.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./ct200.db")
    tinydb_path: str = os.getenv("TINYDB_PATH", "./tinydb_generations.json")
    manual_path: str = os.getenv("MANUAL_PATH", "./data/ct200_manual.md")


settings = Settings()
