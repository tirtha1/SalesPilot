from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    app_name: str = "SalesPilot API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://salespilot:salespilot@localhost:5432/salespilot"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    frontend_origin: str = "http://localhost:5173"
    max_audio_bytes: int = 26_214_400


@lru_cache
def get_settings() -> Settings:
    return Settings()

