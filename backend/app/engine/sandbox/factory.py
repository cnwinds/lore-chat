"""按 Settings 构造 RoleSandboxPool（或单测用的单 runtime）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import Settings
from app.engine.roles import DEFAULT_ROLE_ID
from app.engine.sandbox.naming import DEFAULT_WORKSPACE_VOLUME

_log = logging.getLogger(__name__)

_MIRROR_ENV_PREFIXES = ("PIP_", "UV_", "npm_", "LORECHAT_MIRROR")


def apply_sandbox_settings(
    settings: Settings,
    *,
    runtime: Any = None,
    sandbox_tools: Any = None,
    pool: Any = None,
) -> None:
    """热更新信任模式与软件源（供 build / rebind 共用）。"""
    if sandbox_tools is not None:
        sandbox_tools.trust_mode = bool(settings.sandbox_trust_mode)
    target_pool = pool
    if target_pool is None and sandbox_tools is not None:
        target_pool = getattr(sandbox_tools, "pool", None)
    if target_pool is not None and hasattr(target_pool, "apply_settings"):
        target_pool.apply_settings(
            mirror_region=settings.sandbox_mirror_region,
            max_roles=getattr(settings, "sandbox_max_roles", 4),
            idle_ttl_sec=float(getattr(settings, "sandbox_idle_ttl_sec", 3600) or 0),
            destroy_volume_on_role_delete=bool(
                getattr(settings, "sandbox_destroy_volume_on_role_delete", False)
            ),
        )
        return
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


def _opensandbox_ready() -> None:
    try:
        import opensandbox  # noqa: F401
    except ImportError as e:
        _log.error("SANDBOX_ENABLED=true 但未安装 opensandbox：%s", e)
        raise RuntimeError(
            "sandbox_enabled 需要安装 opensandbox 包（pip install opensandbox）"
        ) from e


def _runtime_kwargs(settings: Settings) -> dict:
    from app.engine.sandbox.mirrors import mirror_env, normalize_mirror_region
    from app.engine.sandbox.opensandbox_runtime import sandbox_proxy_env_from_host

    sandbox_env = sandbox_proxy_env_from_host()
    mirror_region = normalize_mirror_region(settings.sandbox_mirror_region)
    sandbox_env = {**sandbox_env, **mirror_env(mirror_region)}
    if sandbox_env:
        _log.info(
            "sandbox will inherit env keys=%s mirror=%s",
            ",".join(sorted(sandbox_env)),
            mirror_region,
        )
    return {
        "kb_path": Path(settings.kb_path),
        "domain": settings.opensandbox_domain,
        "protocol": settings.opensandbox_protocol,
        "api_key": settings.opensandbox_api_key,
        "use_server_proxy": settings.opensandbox_use_server_proxy,
        "image": settings.sandbox_image,
        "sandbox_env": sandbox_env,
        "mirror_region": mirror_region,
    }


def build_opensandbox_runtime(
    settings: Settings,
    *,
    role_id: str = DEFAULT_ROLE_ID,
    workspace_volume: str | None = None,
):
    """构造单个 OpenSandboxRuntime（池内每角色一把）。"""
    from app.engine.sandbox.opensandbox_runtime import OpenSandboxRuntime

    kwargs = _runtime_kwargs(settings)
    volume = workspace_volume or settings.opensandbox_workspace_volume
    return OpenSandboxRuntime(
        **kwargs,
        workspace_volume=volume,
        role_id=role_id,
    )


def build_sandbox_pool(settings: Settings):
    """sandbox_enabled=False 时返回 None；否则返回 RoleSandboxPool。"""
    if not settings.sandbox_enabled:
        return None
    _opensandbox_ready()

    from app.engine.sandbox.mirrors import normalize_mirror_region
    from app.engine.sandbox.role_pool import RoleSandboxPool

    default_volume = (
        settings.opensandbox_workspace_volume or DEFAULT_WORKSPACE_VOLUME
    )
    kwargs = _runtime_kwargs(settings)

    def factory(role_id: str, slot: dict):
        from app.engine.sandbox.opensandbox_runtime import OpenSandboxRuntime

        volume = slot.get("volume_name") or default_volume
        return OpenSandboxRuntime(
            **kwargs,
            workspace_volume=volume,
            role_id=role_id,
        )

    return RoleSandboxPool(
        kb_path=Path(settings.kb_path),
        runtime_factory=factory,
        default_volume=default_volume,
        mirror_region=normalize_mirror_region(settings.sandbox_mirror_region),
        max_roles=getattr(settings, "sandbox_max_roles", 4),
        idle_ttl_sec=float(getattr(settings, "sandbox_idle_ttl_sec", 3600) or 0),
        destroy_volume_on_role_delete=bool(
            getattr(settings, "sandbox_destroy_volume_on_role_delete", False)
        ),
    )


def build_sandbox_runtime(settings: Settings):
    """兼容：单默认角色 runtime。生产路径请用 build_sandbox_pool。"""
    if not settings.sandbox_enabled:
        return None
    _opensandbox_ready()
    return build_opensandbox_runtime(settings)
