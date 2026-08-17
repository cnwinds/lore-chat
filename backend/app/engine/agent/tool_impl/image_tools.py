from __future__ import annotations

from typing import cast

from app.engine.imagegen import ImageGen, ImageGenError
from app.engine.imagegen.types import DEFAULT_ASPECT_RATIO, Destination


class ImageGenTools:
    def __init__(self, image_gen: ImageGen | None = None) -> None:
        self.image_gen = image_gen

    async def generate_image(self, args: dict) -> dict:
        if self.image_gen is None or not self.image_gen.configured:
            return {
                "summary": "未配置生图模型，请在设置 → 模型中添加生图模型",
                "sources": [],
                "error": "imagegen_not_configured",
            }
        prompt = args.get("prompt")
        raw_dest = str(args.get("destination") or "chat_attachment").strip()
        if raw_dest not in ("chat_attachment", "kb"):
            return {
                "summary": f"无效 destination：{raw_dest}",
                "sources": [],
                "error": "invalid_destination",
            }
        destination = cast(Destination, raw_dest)
        prefer = args.get("provider")
        prefer_s = str(prefer).strip() if prefer else None
        try:
            result = await self.image_gen.generate_and_persist(
                prompt=str(prompt or ""),
                aspect_ratio=args.get("aspect_ratio") or DEFAULT_ASPECT_RATIO,
                destination=destination,
                directory=args.get("directory"),
                filename=args.get("filename"),
                prefer_provider=prefer_s,
            )
        except ImageGenError as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": e.kind.value,
            }
        except Exception as e:
            return {
                "summary": f"生图失败：{e}",
                "sources": [],
                "error": str(e),
            }

        rel = result["rel_path"]
        provider = result.get("provider") or "unknown"
        dest = result.get("destination")
        summary = f"已生成图片 → {rel}（{provider}"
        if dest == "kb":
            summary += "，已写入知识库）"
        else:
            summary += "）"
        out: dict = {
            "summary": summary,
            "sources": [{"type": "kb", "path": rel}],
            "rel_path": rel,
            "provider": provider,
            "aspect_ratio": result.get("aspect_ratio"),
            "destination": dest,
        }
        # 仅聊天附件进时间线预览；kb 落盘供写 Markdown，不挂 attachments
        if dest == "chat_attachment":
            out["attachments"] = [rel]
        return out
