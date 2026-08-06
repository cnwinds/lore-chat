"""按 Settings 构造 SandboxRuntime。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import Settings

_log = logging.getLogger(__name__)

_MIRROR_ENV_PREFIXES = ("PIP_", "UV_", "npm_", "LORECHAT_MIRROR")


def apply_sandbox_settings(
    settings: Settings,
    *,
    runtime: Any = None,
    sandbox_tools: Any = None,
) -> None:
    """热更新信任模式与软件源（供 build / rebind 共用）。"""
    if sandbox_tools is not None:
        sandbox_tools.trust_mode = bool(settings.sandbox_trust_mode)
    if runtime is None or not hasattr(runtime, "mirror_region"):
        return
    from app.engine.sandbox.mirrors import mirror_env, normalize_mirror_region

    region = normalize_mirror_region(settings.sandbox_mirror_region)
    runtime.mirror_region = region
    base = {
        k: v
        for k, v in (getattr(runtime, "sandbox_env", None) or {}).items()
        if not k.startswith(_MIRROR_ENV_PREFIXES)
    }
    runtime.sandbox_env = {**base, **mirror_env(region)}


def build_sandbox_runtime(settings: Settings):
    """sandbox_enabled=False 时返回 None；否则返回 OpenSandboxRuntime。"""
    if not settings.sandbox_enabled:
        return None
    try:
        import opensandbox  # noqa: F401
    except ImportError as e:
        _log.error(
            "SANDBOX_ENABLED=true 但未安装 opensandbox：%s",
            e,
        )
        raise RuntimeError(
            "sandbox_enabled 需要安装 opensandbox 包（pip install opensandbox）"
        ) from e

    from app.engine.sandbox.mirrors import mirror_env, normalize_mirror_region
    from app.engine.sandbox.opensandbox_runtime import (
        OpenSandboxRuntime,
        sandbox_proxy_env_from_host,
    )

    sandbox_env = sandbox_proxy_env_from_host()
    mirror_region = normalize_mirror_region(settings.sandbox_mirror_region)
    sandbox_env = {**sandbox_env, **mirror_env(mirror_region)}
    if sandbox_env:
        _log.info(
            "sandbox will inherit env keys=%s mirror=%s",
            ",".join(sorted(sandbox_env)),
            mirror_region,
        )

    return OpenSandboxRuntime(
        kb_path=Path(settings.kb_path),
        domain=settings.opensandbox_domain,
        protocol=settings.opensandbox_protocol,
        api_key=settings.opensandbox_api_key,
        use_server_proxy=settings.opensandbox_use_server_proxy,
        workspace_volume=settings.opensandbox_workspace_volume,
        sandbox_env=sandbox_env,
        mirror_region=mirror_region,
    )
