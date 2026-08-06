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

    # CORS：逗号分隔的允许来源列表，本地 Vite 开发默认 5173
    cors_origins: str = "http://localhost:5173"

    # 系统控制层：驻留知识库、可见可编辑、不参与检索、每轮注入为系统提示词
    system_layer_dir: str = "系统"
    precepts_filename: str = "戒律.md"
    soul_filename: str = "心法.md"

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

    # 渐进式披露：读取/抓取默认单次最多注入上下文的字符数
    read_disclosure_chars: int = 3000

    # Agent
    agent_max_tool_calls: int = 25
    agent_parallel_tools: bool = True
    agent_max_parallel: int = 4
    fetch_url_timeout: int = 15
    fetch_url_max_bytes: int = 102400

    # 向量检索余弦相似度下限
    min_vector_score: float = 0.45

    # Web search（配哪个用哪个）
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    brave_search_api_key: str | None = None
    search_provider_order: str = "tavily,serper,brave"

    # edit_doc 局部编辑
    edit_doc_max_edits: int = 10
    edit_doc_max_patch_chars: int = 8192
    edit_doc_require_read: bool = True
    reindex_full_threshold: int = 4000

    conversation_chunk_chars: int = 1000
    conversation_chunk_overlap_chars: int = 150
    conversation_context_max_chars: int = 12000
    summarize_segment_chars: int = 28000

    rrf_k: int = 60
    lane_candidate_k: int = 20

    memory_decay_stale_days: int = 90
    memory_decay_inferred_days: int = 180
    memory_decay_candidate_days: int = 180
    memory_maintenance_interval_hours: int = 24

    # OpenSandbox 执行 Runtime（可选；默认关闭，见 docker-compose.sandbox.yml）
    sandbox_enabled: bool = False
    opensandbox_domain: str = "127.0.0.1:18090"
    opensandbox_protocol: str = "http"
    opensandbox_api_key: str | None = None
    opensandbox_use_server_proxy: bool = False
    opensandbox_workspace_volume: str = "lorechat-sandbox-workspace"
    # 信任模式：跳过 sandbox_run 确认门（可经设置 UI 热改；默认开启）
    sandbox_trust_mode: bool = True
    # 沙箱软件源：cn=国内镜像（阿里云/npmmirror），global=官方源
    sandbox_mirror_region: str = "cn"


EDITABLE_SETTING_KEYS: frozenset[str] = frozenset(
    name
    for name in Settings.model_fields
    if name
    not in {
        "kb_path",
        # 部署级能力开关：勿经 UI 热改，避免与 Compose 编排脱节
        "sandbox_enabled",
        "opensandbox_domain",
        "opensandbox_protocol",
        "opensandbox_api_key",
        "opensandbox_use_server_proxy",
        "opensandbox_workspace_volume",
    }
)

SECRET_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "openai_api_key",
        "small_api_key",
        "big_api_key",
        "embed_api_key",
        "tavily_api_key",
        "serper_api_key",
        "brave_search_api_key",
        "opensandbox_api_key",
    }
)


def get_settings() -> "Settings":
    return Settings()
