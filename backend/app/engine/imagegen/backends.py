"""HTTP 适配器：智谱 / 百炼 / OpenAI Images → GeneratedImage。"""

from __future__ import annotations

import asyncio
import base64
import re
from typing import Protocol
import httpx

from app.engine.imagegen.providers import ImageGenProviderEntry
from app.engine.imagegen.sizes import BAILIAN_SIZE, OPENAI_SIZE, ZHIPU_SIZE, bailian_size_for
from app.engine.imagegen.types import (
    GeneratedImage,
    ImageGenError,
    ImageGenErrorKind,
    ImageGenRequest,
)
from app.engine.progress import emit_progress

_SAFETY_RE = re.compile(
    r"safety|content.?policy|content.?filter|违规|审核|敏感|blocked|moderation",
    re.I,
)


def _kind_from_http(status: int | None, body_text: str) -> ImageGenErrorKind:
    lower = (body_text or "").lower()
    if status == 401 or "invalid api key" in lower or "unauthorized" in lower:
        return ImageGenErrorKind.AUTH
    if status == 429 or "rate limit" in lower or "quota" in lower:
        return ImageGenErrorKind.RATE_LIMIT
    if _SAFETY_RE.search(body_text or ""):
        return ImageGenErrorKind.SAFETY
    if status is not None and 400 <= status < 500:
        return ImageGenErrorKind.INVALID_REQUEST
    if status is not None and status >= 500:
        return ImageGenErrorKind.TRANSIENT
    return ImageGenErrorKind.UNKNOWN


def _raise_http(resp: httpx.Response) -> None:
    text = ""
    try:
        text = resp.text
    except Exception:
        text = ""
    kind = _kind_from_http(resp.status_code, text)
    snippet = (text or "")[:300] or resp.reason_phrase or f"HTTP {resp.status_code}"
    raise ImageGenError(f"生图失败（{resp.status_code}）：{snippet}", kind=kind)


async def _download_url(client: httpx.AsyncClient, url: str) -> GeneratedImage:
    try:
        resp = await client.get(url)
    except httpx.TimeoutException as e:
        raise ImageGenError(f"下载图片超时：{e}", kind=ImageGenErrorKind.TRANSIENT) from e
    except httpx.HTTPError as e:
        raise ImageGenError(f"下载图片网络错误：{e}", kind=ImageGenErrorKind.TRANSIENT) from e
    if resp.status_code >= 400:
        _raise_http(resp)
    ctype = (resp.headers.get("content-type") or "image/png").split(";")[0].strip()
    ext = "png"
    if "jpeg" in ctype or "jpg" in ctype:
        ext = "jpg"
    elif "webp" in ctype:
        ext = "webp"
    return GeneratedImage(data=resp.content, content_type=ctype, extension=ext)


def _parse_openai_like_data(data: dict) -> tuple[str | None, str | None]:
    """返回 (url, b64)。"""
    items = data.get("data")
    if not isinstance(items, list) or not items:
        return None, None
    first = items[0] if isinstance(items[0], dict) else {}
    url = first.get("url")
    b64 = first.get("b64_json")
    return (
        str(url) if url else None,
        str(b64) if b64 else None,
    )


class ImageGenBackend(Protocol):
    async def generate(self, request: ImageGenRequest) -> GeneratedImage: ...


async def _generate_openai_like(
    *,
    entry: ImageGenProviderEntry,
    request: ImageGenRequest,
    size: str,
    label: str,
    payload_extra: dict | None = None,
    retry_drop_response_format: bool = False,
    check_body_error: bool = False,
) -> GeneratedImage:
    url = f"{entry.resolved_base_url()}/images/generations"
    payload: dict = {
        "model": entry.resolved_model(),
        "prompt": request.prompt,
        "n": 1,
        "size": size,
    }
    if payload_extra:
        payload.update(payload_extra)
    headers = {
        "Authorization": f"Bearer {entry.api_key}",
        "Content-Type": "application/json",
    }
    emit_progress(f"{label}生图中…")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                if (
                    retry_drop_response_format
                    and resp.status_code == 400
                    and "response_format" in (resp.text or "")
                ):
                    payload.pop("response_format", None)
                    resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    _raise_http(resp)
            data = resp.json()
            if check_body_error and isinstance(data, dict) and data.get("error"):
                err = data["error"]
                msg = err if isinstance(err, str) else str(err)
                raise ImageGenError(
                    f"{label}生图失败：{msg}",
                    kind=_kind_from_http(None, msg),
                )
            img_url, b64 = _parse_openai_like_data(data)
            if b64:
                return GeneratedImage(
                    data=base64.b64decode(b64),
                    content_type="image/png",
                    extension="png",
                )
            if img_url:
                return await _download_url(client, img_url)
    except ImageGenError:
        raise
    except httpx.TimeoutException as e:
        raise ImageGenError(f"{label}生图超时：{e}", kind=ImageGenErrorKind.TRANSIENT) from e
    except httpx.HTTPError as e:
        raise ImageGenError(
            f"{label}生图网络错误：{e}", kind=ImageGenErrorKind.TRANSIENT
        ) from e
    raise ImageGenError(f"{label}生图响应无图片数据", kind=ImageGenErrorKind.UNKNOWN)


class OpenAIImagesBackend:
    def __init__(self, entry: ImageGenProviderEntry):
        self._entry = entry

    async def generate(self, request: ImageGenRequest) -> GeneratedImage:
        return await _generate_openai_like(
            entry=self._entry,
            request=request,
            size=OPENAI_SIZE[request.aspect_ratio],
            label="OpenAI",
            payload_extra={"response_format": "b64_json"},
            retry_drop_response_format=True,
        )


class ZhipuImagesBackend:
    def __init__(self, entry: ImageGenProviderEntry):
        self._entry = entry

    async def generate(self, request: ImageGenRequest) -> GeneratedImage:
        return await _generate_openai_like(
            entry=self._entry,
            request=request,
            size=ZHIPU_SIZE[request.aspect_ratio],
            label="智谱",
            check_body_error=True,
        )


def _bailian_uses_multimodal(model: str) -> bool:
    """qwen-image* / wan2.* 走 multimodal（messages）；旧 wanx 走 text2image 异步。"""
    m = (model or "").strip().lower()
    return m.startswith("qwen-image") or m.startswith("wan2.")


def _extract_dashscope_image_url(data: dict) -> str | None:
    """从 DashScope 同步/异步成功响应中取图片 URL。"""
    output = data.get("output") if isinstance(data.get("output"), dict) else {}
    choices = output.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            msg = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            content = msg.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("image"):
                        return str(item["image"])
            elif isinstance(content, dict) and content.get("image"):
                return str(content["image"])
    results = output.get("results")
    if isinstance(results, list) and results:
        first = results[0] if isinstance(results[0], dict) else {}
        if first.get("url"):
            return str(first["url"])
    if output.get("url"):
        return str(output["url"])
    return None


class BailianImagesBackend:
    """DashScope 文生图。

    - qwen-image* / wan2.*：异步 image-generation（messages）+ 轮询
    - 旧 wanx*：异步 text2image/image-synthesis + 轮询
    """

    def __init__(self, entry: ImageGenProviderEntry):
        self._entry = entry

    def _api_root(self) -> str:
        return self._entry.resolved_base_url().rstrip("/")

    async def generate(self, request: ImageGenRequest) -> GeneratedImage:
        model = self._entry.resolved_model()
        if _bailian_uses_multimodal(model):
            return await self._generate_multimodal(request, model)
        return await self._generate_legacy_wanx(request, model)

    def _auth_headers(self, *, async_mode: bool = False) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._entry.api_key}",
            "Content-Type": "application/json",
        }
        if async_mode:
            headers["X-DashScope-Async"] = "enable"
        return headers

    def _raise_dashscope_body(self, data: dict, *, status: int | None = None) -> None:
        code = data.get("code")
        if not code:
            return
        msg = str(data.get("message") or code)
        raise ImageGenError(
            f"百炼生图失败：{msg}",
            kind=_kind_from_http(status, msg),
        )

    async def _generate_multimodal(
        self, request: ImageGenRequest, model: str
    ) -> GeneratedImage:
        """qwen-image* / wan2.*：异步 image-generation（messages）+ 轮询。

        同步 multimodal-generation 对本账号/新模型常长时间无响应，故统一异步。
        """
        create_url = (
            f"{self._api_root()}/api/v1/services/aigc/image-generation/generation"
        )
        size = bailian_size_for(model, request.aspect_ratio)
        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": request.prompt}],
                    }
                ]
            },
            "parameters": {
                "size": size,
                "n": 1,
                "watermark": False,
            },
        }
        headers = self._auth_headers(async_mode=True)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(create_url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    _raise_http(resp)
                data = resp.json()
                if not isinstance(data, dict):
                    raise ImageGenError(
                        "百炼响应非 JSON 对象", kind=ImageGenErrorKind.UNKNOWN
                    )
                self._raise_dashscope_body(data, status=resp.status_code)
                # 少数环境仍可能同步返回图
                img_url = _extract_dashscope_image_url(data)
                if img_url:
                    return await _download_url(client, img_url)
                output = data.get("output") if isinstance(data.get("output"), dict) else {}
                task_id = output.get("task_id") or data.get("task_id")
                if not task_id:
                    raise ImageGenError(
                        "百炼未返回 task_id", kind=ImageGenErrorKind.UNKNOWN
                    )
                emit_progress("百炼任务已创建，等待出图…")
                return await self._poll(
                    client, str(task_id), headers, max_attempts=120, interval_sec=2.0
                )
        except ImageGenError:
            raise
        except httpx.TimeoutException as e:
            raise ImageGenError(f"百炼生图超时：{e}", kind=ImageGenErrorKind.TRANSIENT) from e
        except httpx.HTTPError as e:
            raise ImageGenError(
                f"百炼生图网络错误：{e}", kind=ImageGenErrorKind.TRANSIENT
            ) from e

    async def _generate_legacy_wanx(
        self, request: ImageGenRequest, model: str
    ) -> GeneratedImage:
        create_url = (
            f"{self._api_root()}/api/v1/services/aigc/text2image/image-synthesis"
        )
        payload = {
            "model": model,
            "input": {"prompt": request.prompt},
            "parameters": {
                "size": BAILIAN_SIZE[request.aspect_ratio],
                "n": 1,
            },
        }
        headers = self._auth_headers(async_mode=True)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(create_url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    _raise_http(resp)
                data = resp.json()
                if not isinstance(data, dict):
                    raise ImageGenError(
                        "百炼响应非 JSON 对象", kind=ImageGenErrorKind.UNKNOWN
                    )
                self._raise_dashscope_body(data, status=resp.status_code)
                output = data.get("output") if isinstance(data.get("output"), dict) else {}
                task_id = output.get("task_id") or data.get("task_id")
                if not task_id:
                    raise ImageGenError(
                        "百炼未返回 task_id", kind=ImageGenErrorKind.UNKNOWN
                    )
                emit_progress("百炼任务已创建，等待出图…")
                return await self._poll(client, str(task_id), headers)
        except ImageGenError:
            raise
        except httpx.TimeoutException as e:
            raise ImageGenError(f"百炼生图超时：{e}", kind=ImageGenErrorKind.TRANSIENT) from e
        except httpx.HTTPError as e:
            raise ImageGenError(
                f"百炼生图网络错误：{e}", kind=ImageGenErrorKind.TRANSIENT
            ) from e

    async def _poll(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        headers: dict[str, str],
        *,
        max_attempts: int = 60,
        interval_sec: float = 2.0,
    ) -> GeneratedImage:
        task_url = f"{self._api_root()}/api/v1/tasks/{task_id}"
        get_headers = {"Authorization": headers["Authorization"]}
        progress_tick = 0
        for i in range(max_attempts):
            resp = await client.get(task_url, headers=get_headers, timeout=30.0)
            if resp.status_code >= 400:
                _raise_http(resp)
            data = resp.json()
            if not isinstance(data, dict):
                raise ImageGenError(
                    "百炼轮询响应非 JSON 对象", kind=ImageGenErrorKind.UNKNOWN
                )
            self._raise_dashscope_body(data, status=resp.status_code)
            output = data.get("output") if isinstance(data.get("output"), dict) else {}
            status = str(output.get("task_status") or data.get("task_status") or "")
            if status in ("SUCCEEDED", "SUCCESS"):
                url = _extract_dashscope_image_url(data)
                if not url:
                    raise ImageGenError(
                        "百炼任务成功但无图片 URL", kind=ImageGenErrorKind.UNKNOWN
                    )
                return await _download_url(client, str(url))
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                msg = str(
                    output.get("message")
                    or data.get("message")
                    or f"task_status={status}"
                )
                raise ImageGenError(
                    f"百炼生图失败：{msg}",
                    kind=_kind_from_http(None, msg),
                )
            if i % 3 == 0:
                progress_tick += 1
                dots = "." * min(progress_tick, 20)
                line = f"百炼生成中（{status or 'PENDING'}）{dots}"
                # 同一行覆盖更新（progress_log 支持 \\r），避免刷屏多行
                emit_progress(line if progress_tick == 1 else f"\r{line}")
            await asyncio.sleep(interval_sec)
        raise ImageGenError("百炼生图轮询超时", kind=ImageGenErrorKind.TRANSIENT)


_PROVIDER_CLS: dict[str, type] = {
    "openai": OpenAIImagesBackend,
    "zhipu": ZhipuImagesBackend,
    "bailian": BailianImagesBackend,
}


def build_backend(entry: ImageGenProviderEntry) -> ImageGenBackend:
    cls = _PROVIDER_CLS[entry.provider]
    assert entry.api_key
    return cls(entry)
