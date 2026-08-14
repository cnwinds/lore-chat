"""宽高比 → 各厂商 size 字符串。"""

from __future__ import annotations

from app.engine.imagegen.types import AspectRatio

# OpenAI dall-e-3 仅三档；4:3/3:4 映射到最接近的横/竖图（非方图）
OPENAI_SIZE: dict[AspectRatio, str] = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "4:3": "1792x1024",
    "3:4": "1024x1792",
}

# 智谱 CogView 推荐枚举
ZHIPU_SIZE: dict[AspectRatio, str] = {
    "1:1": "1024x1024",
    "16:9": "1440x720",
    "9:16": "720x1440",
    "4:3": "1152x864",
    "3:4": "864x1152",
}

# 百炼万相旧接口（wanx-v1 / wanx2.1-t2i 等）：宽*高
BAILIAN_SIZE: dict[AspectRatio, str] = {
    "1:1": "1024*1024",
    "16:9": "1280*720",
    "9:16": "720*1280",
    "4:3": "1024*768",
    "3:4": "768*1024",
}

# qwen-image-2.0 / 3.0 系列推荐分辨率
BAILIAN_QWEN20_SIZE: dict[AspectRatio, str] = {
    "1:1": "2048*2048",
    "16:9": "2688*1536",
    "9:16": "1536*2688",
    "4:3": "2368*1728",
    "3:4": "1728*2368",
}

# qwen-image / plus / max 固定档位
BAILIAN_QWEN_PLUS_SIZE: dict[AspectRatio, str] = {
    "1:1": "1328*1328",
    "16:9": "1664*928",
    "9:16": "928*1664",
    "4:3": "1472*1104",
    "3:4": "1104*1472",
}

# wan2.x：文生图用像素宽高（1K/2K/4K 档位仅出方图）
BAILIAN_WAN27_SIZE: dict[AspectRatio, str] = {
    "1:1": "2048*2048",
    "16:9": "2560*1440",
    "9:16": "1440*2560",
    "4:3": "2304*1728",
    "3:4": "1728*2304",
}

# Agnes：官方推荐 size 档位 + ratio；项目宽高比均在其支持列表内
AGNES_SIZE_TIER = "1K"
AGNES_RATIO: dict[AspectRatio, str] = {
    "1:1": "1:1",
    "16:9": "16:9",
    "9:16": "9:16",
    "4:3": "4:3",
    "3:4": "3:4",
}


def bailian_size_for(model: str, aspect_ratio: AspectRatio) -> str:
    """按模型族选择百炼 size 字符串。"""
    m = (model or "").strip().lower()
    if m.startswith("wan2."):
        return BAILIAN_WAN27_SIZE[aspect_ratio]
    if m.startswith("qwen-image-2") or m.startswith("qwen-image-3"):
        return BAILIAN_QWEN20_SIZE[aspect_ratio]
    if m.startswith("qwen-image"):
        return BAILIAN_QWEN_PLUS_SIZE[aspect_ratio]
    return BAILIAN_SIZE[aspect_ratio]
