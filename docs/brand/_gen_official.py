"""Promote O3 spiral-year-ring to official Lore brand files."""
from __future__ import annotations

import math
from pathlib import Path

root = Path(__file__).parent


def spiral_pts():
    cx, cy = 64.0, 66.0
    a, b, t0 = 9.6, 1.48, 0.7
    t1 = math.radians(48) + 4 * math.pi
    n = 160
    pts = []
    for i in range(n + 1):
        t = t0 + (t1 - t0) * i / n
        rr = a + b * t
        pts.append((cx + rr * math.cos(t), cy - rr * math.sin(t)))
    return pts


def path_d(pts) -> str:
    d = [f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"]
    d += [f"L {x:.2f} {y:.2f}" for x, y in pts[1:]]
    return " ".join(d)


pts = spiral_pts()
d = path_d(pts)
ex, ey = pts[-1]
stroke_w = 5.6
node_r = 5.8
gold_r = 2.4

# optical center including stroke / node
xs = [p[0] for p in pts] + [ex - node_r, ex + node_r]
ys = [p[1] for p in pts] + [ey - node_r, ey + node_r]
pad = stroke_w / 2
minx, maxx = min(xs) - pad, max(xs) + pad
miny, maxy = min(ys) - pad, max(ys) + pad
sx = 64 - (minx + maxx) / 2
sy = 64 - (miny + maxy) / 2
shift = f"translate({sx:.2f} {sy:.2f})"


def mark(stroke: str, fill: str, gold: str | None) -> str:
    gold_el = (
        f'\n    <circle cx="{ex:.2f}" cy="{ey:.2f}" r="{gold_r}" fill="{gold}"/>'
        if gold
        else ""
    )
    return f'''  <g transform="{shift}">
    <path d="{d}" fill="none" stroke="{stroke}" stroke-width="{stroke_w}" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="{ex:.2f}" cy="{ey:.2f}" r="{node_r}" fill="{fill}"/>{gold_el}
  </g>'''


def svg(view: str, inner: str, title: str = "Lore") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" fill="none" '
        f'role="img" aria-label="{title}">\n  <title>{title}</title>\n{inner}\n</svg>\n'
    )


icon = svg(
    "0 0 128 128",
    f'''  <defs>
    <linearGradient id="lore-plate" x1="18" y1="6" x2="110" y2="122" gradientUnits="userSpaceOnUse">
      <stop stop-color="#4A47C8"/>
      <stop offset="1" stop-color="#7B7BF0"/>
    </linearGradient>
    <radialGradient id="lore-sheen" cx="38" cy="26" r="78" gradientUnits="userSpaceOnUse">
      <stop stop-color="#FFFFFF" stop-opacity="0.2"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="url(#lore-plate)"/>
  <rect width="128" height="128" rx="28" fill="url(#lore-sheen)"/>
{mark("#FFFFFF", "#FFFFFF", "#F0C14B")}''',
)

(root / "lore-icon.svg").write_text(icon, encoding="utf-8")
(root / "lore-mark.svg").write_text(
    svg("0 0 128 128", mark("#5B5BD6", "#5B5BD6", "#E8B84A")), encoding="utf-8"
)
(root / "lore-mark-mono.svg").write_text(
    svg(
        "0 0 128 128",
        mark("currentColor", "currentColor", None).replace(
            'stroke="currentColor"', 'stroke="currentColor"'
        ),
    ),
    encoding="utf-8",
)

print("shift", shift, "end", ex, ey)
print("PATH", d[:80], "...")
