"""ImageGen deep module：多厂商 failover + 落盘为 KB 相对路径。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

from app.config import Settings
from app.engine.imagegen.router import (
    NoImageProviderAvailable,
    resolve_image_candidates,
    select_image_provider,
)
from app.engine.imagegen.types import (
    ASPECT_RATIOS,
    DEFAULT_ASPECT_RATIO,
    FAILOVER_KINDS,
    AspectRatio,
    Destination,
    GeneratedImage,
    ImageGenError,
    ImageGenErrorKind,
    ImageGenRequest,
)
from app.engine.knowledge_writer import KbPathExistsError, KnowledgeWriter
from app.models.cooldown import CooldownStore, ErrorClass
from app.storage.kb_media_paths import media_generated_dir


def _to_cooldown_class(kind: ImageGenErrorKind) -> ErrorClass:
    if kind == ImageGenErrorKind.AUTH:
        return ErrorClass.AUTH
    if kind == ImageGenErrorKind.RATE_LIMIT:
        return ErrorClass.RATE_LIMIT
    if kind == ImageGenErrorKind.TRANSIENT:
        return ErrorClass.TRANSIENT
    return ErrorClass.UNKNOWN


def _auto_filename(ext: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{uuid.uuid4().hex[:8]}.{ext.lstrip('.')}"


def normalize_aspect_ratio(raw: object) -> AspectRatio:
    s = str(raw or "").strip() or DEFAULT_ASPECT_RATIO
    if s not in ASPECT_RATIOS:
        raise ImageGenError(
            f"不支持的 aspect_ratio：{s}（允许 {', '.join(sorted(ASPECT_RATIOS))}）",
            kind=ImageGenErrorKind.INVALID_REQUEST,
        )
    return s  # type: ignore[return-value]


class ImageGen:
    def __init__(
        self,
        settings: Settings,
        *,
        cooldown: CooldownStore,
        knowledge_writer: KnowledgeWriter,
    ):
        """cooldown / knowledge_writer 须与 Container 同实例（见 CONTEXT.md）。"""
        self.settings = settings
        self.cooldown = cooldown
        self.knowledge_writer = knowledge_writer
        self.provider_name: str | None = None
        self.provider_id: str | None = None

    def rebind_settings(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(resolve_image_candidates(self.settings))

    async def generate_bytes(
        self,
        request: ImageGenRequest,
        *,
        prefer_provider: str | None = None,
    ) -> GeneratedImage:
        if not self.configured:
            raise ImageGenError(
                "未配置生图提供商，请在设置中添加",
                kind=ImageGenErrorKind.INVALID_REQUEST,
            )

        attempted: set[str] = set()
        last_exc: ImageGenError | None = None
        while True:
            try:
                sel = select_image_provider(
                    self.settings,
                    self.cooldown,
                    exclude_ids=attempted,
                    prefer_provider=prefer_provider,
                )
            except NoImageProviderAvailable as e:
                if last_exc is not None:
                    raise last_exc from e
                raise ImageGenError(
                    "生图提供商均不可用（冷却或已禁用），请稍后重试或在设置中调整",
                    kind=ImageGenErrorKind.TRANSIENT,
                ) from e

            entry = sel.entry
            try:
                image = await sel.candidate.backend.generate(request)
            except ImageGenError as e:
                last_exc = e
                if e.kind in FAILOVER_KINDS:
                    self.cooldown.record_failure(
                        entry.id, _to_cooldown_class(e.kind), error=str(e)
                    )
                    attempted.add(entry.id)
                    continue
                if e.kind == ImageGenErrorKind.AUTH:
                    self.cooldown.record_failure(
                        entry.id, ErrorClass.AUTH, error=str(e)
                    )
                # safety / invalid_request / unknown：不切厂商
                raise
            except Exception as e:
                # 非 ImageGenError → unknown 且不切厂商（ADR）；CancelledError 等不捕获
                raise ImageGenError(
                    f"生图内部错误：{e}",
                    kind=ImageGenErrorKind.UNKNOWN,
                ) from e

            self.cooldown.record_success(entry.id)
            self.provider_name = entry.provider
            self.provider_id = entry.id
            return GeneratedImage(
                data=image.data,
                content_type=image.content_type,
                extension=image.extension,
                provider=entry.provider,
                provider_id=entry.id,
            )

    def persist(
        self,
        image: GeneratedImage,
        *,
        destination: Destination,
        directory: str | None = None,
        filename: str | None = None,
    ) -> str:
        if destination == "chat_attachment":
            directory = media_generated_dir()
            filename = _auto_filename(image.extension)
        elif destination == "kb":
            if not directory or not str(directory).strip():
                raise ImageGenError(
                    "destination=kb 时必须提供 directory",
                    kind=ImageGenErrorKind.INVALID_REQUEST,
                )
            if not filename or not str(filename).strip():
                raise ImageGenError(
                    "destination=kb 时必须提供 filename",
                    kind=ImageGenErrorKind.INVALID_REQUEST,
                )
            fn = str(filename).strip()
            if "." not in PurePosixPath(fn).name:
                fn = f"{fn}.{image.extension}"
            filename = fn
        else:
            raise ImageGenError(
                f"未知 destination：{destination}",
                kind=ImageGenErrorKind.INVALID_REQUEST,
            )

        # 冲突时换名重试（chat_attachment）；kb 显式路径冲突则报错
        attempts = 8 if destination == "chat_attachment" else 1
        last_err: Exception | None = None
        for _ in range(attempts):
            try:
                result = self.knowledge_writer.import_entry(
                    directory=str(directory),
                    filename=str(filename),
                    data=image.data,
                    allow_binary=True,
                )
                return str(result["rel_path"])
            except KbPathExistsError as e:
                last_err = e
                if destination != "chat_attachment":
                    raise ImageGenError(
                        f"目标已存在：{e}",
                        kind=ImageGenErrorKind.INVALID_REQUEST,
                    ) from e
                filename = _auto_filename(image.extension)
        raise ImageGenError(
            f"无法写入唯一文件名：{last_err}",
            kind=ImageGenErrorKind.UNKNOWN,
        )

    async def generate_and_persist(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio | str = DEFAULT_ASPECT_RATIO,
        destination: Destination = "chat_attachment",
        directory: str | None = None,
        filename: str | None = None,
        prefer_provider: str | None = None,
    ) -> dict:
        """工具主入口：生成并落盘，返回摘要字段。"""
        ar = normalize_aspect_ratio(aspect_ratio)
        prompt_s = (prompt or "").strip()
        if not prompt_s:
            raise ImageGenError(
                "prompt 不能为空", kind=ImageGenErrorKind.INVALID_REQUEST
            )
        image = await self.generate_bytes(
            ImageGenRequest(prompt=prompt_s, aspect_ratio=ar),
            prefer_provider=prefer_provider,
        )
        provider = image.provider or self.provider_name
        provider_id = image.provider_id or self.provider_id
        rel = self.persist(
            image,
            destination=destination,
            directory=directory,
            filename=filename,
        )
        return {
            "rel_path": rel,
            "provider": provider,
            "provider_id": provider_id,
            "aspect_ratio": ar,
            "destination": destination,
        }
