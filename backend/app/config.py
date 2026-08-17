from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.engine.disclosure import (
    DEFAULT_DISCLOSURE_CHARS,
    DEEP_DISCLOSURE_CHARS,
    MAX_DISCLOSURE_CHARS,
)
from app.engine.web.limits import FETCH_URL_HTML_MAX_BYTES, FETCH_URL_PDF_MAX_BYTES

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

    # Skill 固定目录：与系统层同级，侧栏排在「系统」之下；可检索、可附加，不受系统层保护
    skills_dir: str = "技能"

    openai_api_key: str = "sk-none"
    # 仅作旧配置迁移源；运行时不回退。默认可空，避免新安装被注入 api.openai.com。
    openai_base_url: str = ""

    # Legacy 别名：迁移后与 chat/utility 链首同步；新配置以 *_models 为准
    small_model: str = "gpt-4o-mini"
    big_model: str = "gpt-4o"
    embed_model: str = "text-embedding-3-small"

    small_base_url: str | None = None
    small_api_key: str | None = None
    big_base_url: str | None = None
    big_api_key: str | None = None
    embed_base_url: str | None = None
    embed_api_key: str | None = None

    # chat = 对话/Agent；utility = 辅助（记忆抽取等）；embed = 向量；列表顺序即优先级
    chat_models: list[dict[str, Any]] = []
    utility_models: list[dict[str, Any]] = []
    embed_models: list[dict[str, Any]] = []

    # Agnes 等 url_only 识图：签名附件 URL 的公网可达前缀（必填才启用 URL 识图）
    public_base_url: str | None = None

    @field_validator("chat_models", "utility_models", "embed_models", mode="before")
    @classmethod
    def _parse_model_lists(cls, v: Any) -> list:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            import json

            return json.loads(v)
        return v

    # 渐进式披露：spot 默认窗 / deep 默认窗 / 单次硬上限（防一次灌爆上下文）
    read_disclosure_chars: int = DEFAULT_DISCLOSURE_CHARS
    read_disclosure_deep_chars: int = DEEP_DISCLOSURE_CHARS
    read_disclosure_max_chars: int = MAX_DISCLOSURE_CHARS

    # Agent
    agent_max_tool_calls: int = 25
    agent_parallel_tools: bool = True
    agent_max_parallel: int = 4
    fetch_url_timeout: int = 15
    fetch_url_max_bytes: int = FETCH_URL_HTML_MAX_BYTES
    fetch_url_pdf_max_bytes: int = FETCH_URL_PDF_MAX_BYTES

    # 向量检索余弦相似度下限
    min_vector_score: float = 0.45

    # Web search：有序链（列表顺序即优先级）；None=未配置链（可从旧三密钥迁移）
    search_providers: list[dict[str, Any]] | None = None
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    brave_search_api_key: str | None = None
    search_provider_order: str = "tavily,serper,brave"

    @field_validator("search_providers", mode="before")
    @classmethod
    def _parse_search_providers(cls, v: Any) -> list | None:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            import json

            return json.loads(v)
        return v

    # 生图：有序链；[]=显式未配置；默认 []
    image_providers: list[dict[str, Any]] = []

    @field_validator("image_providers", mode="before")
    @classmethod
    def _parse_image_providers(cls, v: Any) -> list:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            import json

            return json.loads(v)
        return v

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
    memory_session_idle_hours: float = 24.0

    # OpenSandbox 执行 Runtime（可选；默认关闭，见 docker-compose.sandbox.yml）
    sandbox_enabled: bool = False
    opensandbox_domain: str = "127.0.0.1:18090"
    opensandbox_protocol: str = "http"
    opensandbox_api_key: str | None = None
    opensandbox_use_server_proxy: bool = False
    opensandbox_workspace_volume: str = "lorechat-sandbox-workspace"
    # 沙箱业务镜像（工具链）；execd 由 OpenSandbox config.toml 的 execd_image 注入
    sandbox_image: str = "lorechat-sandbox-agent:local"
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
        "sandbox_image",
    }
)

SECRET_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "openai_api_key",
        "small_api_key",
        "big_api_key",
        "embed_api_key",
        "opensandbox_api_key",
    }
)

# 旧三搜索密钥：仅迁移/回写兼容，public API 仍脱敏；新配置以 search_providers 为准
LEGACY_SEARCH_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "tavily_api_key",
        "serper_api_key",
        "brave_search_api_key",
    }
)

# 嵌套在 chat_models / utility_models / embed_models[].api_key 内，由 SettingsStore 单独脱敏
CHAIN_MODEL_SETTING_KEYS: frozenset[str] = frozenset(
    {"chat_models", "utility_models", "embed_models"}
)

# 嵌套在 search_providers[].api_key 内
CHAIN_SEARCH_SETTING_KEYS: frozenset[str] = frozenset({"search_providers"})

# 嵌套在 image_providers[].api_key 内
CHAIN_IMAGE_SETTING_KEYS: frozenset[str] = frozenset({"image_providers"})


def get_settings() -> "Settings":
    return Settings()
