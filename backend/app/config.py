from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kb_path: Path = Path("./knowledge")

    openai_api_key: str = "sk-none"
    openai_base_url: str = "https://api.openai.com/v1"

    small_model: str = "gpt-4o-mini"
    big_model: str = "gpt-4o"
    embed_model: str = "text-embedding-3-small"

    small_base_url: str | None = None
    small_api_key: str | None = None
    big_base_url: str | None = None
    big_api_key: str | None = None
    embed_base_url: str | None = None
    embed_api_key: str | None = None


def get_settings() -> "Settings":
    return Settings()
