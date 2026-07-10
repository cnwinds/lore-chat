from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

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

    # Agent
    agent_max_tool_calls: int = 100
    agent_parallel_tools: bool = True
    agent_max_parallel: int = 4
    fetch_url_timeout: int = 15
    fetch_url_max_bytes: int = 102400

    # Web search（配哪个用哪个）
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    brave_search_api_key: str | None = None
    search_provider_order: str = "tavily,serper,brave"


def get_settings() -> "Settings":
    return Settings()
