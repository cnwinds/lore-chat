#!/usr/bin/env bash
# 从 public/lore.svg 生成 PWA 用 PNG（需 pip install cairosvg）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SVG="$ROOT/public/lore.svg"
python3 - <<PY
import cairosvg
from pathlib import Path
svg = Path("$SVG").read_bytes()
root = Path("$ROOT/public")
for size in (180, 192, 512):
    out = root / f"pwa-icon-{size}.png"
    cairosvg.svg2png(bytestring=svg, write_to=str(out), output_width=size, output_height=size)
    print("wrote", out)
PY
