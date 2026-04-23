from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./serivenext.db"
    secret_key: str = "dev-secret-change-me"

    ai_provider: str = "rule"  # "rule" | "openai"
    ai_base_url: str = "http://localhost:11434/v1"
    ai_api_key: str = "ollama"
    ai_model: str = "llama3.1:8b"
    ai_auto_resolve_threshold: float = 0.85


@lru_cache
def get_settings() -> Settings:
    return Settings()
