"""Lore wordmark: Outfit L/re with the spiral year-ring as the letter o."""
from __future__ import annotations

import math
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

root = Path(__file__).parent
font_path = root / "_fonts" / "Outfit-SemiBold.ttf"
if not font_path.exists():
    raise SystemExit(f"Missing {font_path}. Download Outfit 600 TTF into docs/brand/_fonts/.")

font = TTFont(font_path)
gs = font.getGlyphSet()
cmap = font.getBestCmap()
upem = font["head"].unitsPerEm
os2 = font["OS/2"]
CAP = os2.sCapHeight
X_HEIGHT = os2.sxHeight


def glyph_d(ch: str) -> str:
    pen = SVGPathPen(gs)
    gs[cmap[ord(ch)]].draw(pen)
    return pen.getCommands()


def glyph_meta(ch: str) -> tuple[str, float, tuple[float, float, float, float]]:
    name = cmap[ord(ch)]
    pen = BoundsPen(gs)
    gs[name].draw(pen)
    return glyph_d(ch), float(gs[name].width), pen.bounds


L_d, L_w, L_b = glyph_meta("L")
o_d, o_w, o_b = glyph_meta("o")
r_d, r_w, r_b = glyph_meta("r")
e_d, e_w, e_b = glyph_meta("e")


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


pts = spiral_pts()
spiral_d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
ex, ey = pts[-1]
stroke_w, node_r, gold_r = 5.6, 5.8, 2.4
pad_s = stroke_w / 2
# Fit the ring (stroke included) to the letter o; gold node may peek as the growing tip.
xs = [p[0] for p in pts]
ys = [p[1] for p in pts]
sminx, smaxx = min(xs) - pad_s, max(xs) + pad_s
sminy, smaxy = min(ys) - pad_s, max(ys) + pad_s

FONTS = "Outfit, Inter, Segoe UI, system-ui, sans-serif"
SLOGAN = "让每次对话，长成你的知识与能力。"


def letter(
    d: str,
    x: float,
    baseline: float,
    s: float,
    fill: str,
    *,
    outline: str | None = None,
    outline_w: float = 40,
) -> str:
    stroke = ""
    if outline:
        stroke = (
            f' stroke="{outline}" stroke-width="{outline_w:.0f}" '
            f'stroke-linecap="round" stroke-linejoin="round" paint-order="stroke fill"'
        )
    return (
        f'<g transform="translate({x:.2f} {baseline:.2f}) scale({s:.5f} {-s:.5f})">'
        f'<path d="{d}" fill="{fill}"{stroke}/></g>'
    )


def spiral_at(
    tx: float,
    ty: float,
    sc: float,
    stroke: str,
    node: str,
    gold: str,
    *,
    outline: str | None = None,
) -> str:
    halo_path = ""
    halo_node = ""
    if outline:
        halo_w = stroke_w + 4.0
        halo_r = node_r + 1.6
        halo_path = (
            f'      <path d="{spiral_d}" fill="none" stroke="{outline}" '
            f'stroke-width="{halo_w}" stroke-linecap="round" stroke-linejoin="round"/>\n'
        )
        halo_node = f'      <circle cx="{ex:.2f}" cy="{ey:.2f}" r="{halo_r}" fill="{outline}"/>\n'
    return f'''<g transform="translate({tx:.2f} {ty:.2f}) scale({sc:.5f})">
{halo_path}      <path d="{spiral_d}" fill="none" stroke="{stroke}" stroke-width="{stroke_w}" stroke-linecap="round" stroke-linejoin="round"/>
{halo_node}      <circle cx="{ex:.2f}" cy="{ey:.2f}" r="{node_r}" fill="{node}"/>
      <circle cx="{ex:.2f}" cy="{ey:.2f}" r="{gold_r}" fill="{gold}"/>
    </g>'''


def wordmark_parts(
    font_size: float,
    origin_x: float,
    baseline: float,
    ink: str,
    spiral: str,
    gold: str,
    *,
    outline: str | None = None,
) -> tuple[str, float]:
    """Return SVG internals and the x after the last letter."""
    s = font_size / upem
    tracking = -0.03 * font_size
    # Spiral is larger than a plain o; keep it off L's foot and r's stem.
    lo_kern = 0.02 * font_size
    or_kern = 0.05 * font_size

    x = origin_x
    parts = [letter(L_d, x, baseline, s, ink, outline=outline)]
    x += L_w * s + tracking + lo_kern

    o_slot = x
    o_cx = o_slot + (o_b[0] + o_b[2]) / 2 * s
    o_cy = baseline - (o_b[1] + o_b[3]) / 2 * s
    o_h = (o_b[3] - o_b[1]) * s
    # Slightly larger than a plain o so the year-ring reads as the mark.
    target_h = o_h * 1.14
    sc = target_h / (smaxy - sminy)
    sp_cx, sp_cy = (sminx + smaxx) / 2, (sminy + smaxy) / 2
    parts.append(
        spiral_at(
            o_cx - sp_cx * sc,
            o_cy - sp_cy * sc,
            sc,
            spiral,
            spiral,
            gold,
            outline=outline,
        )
    )
    x += o_w * s + tracking + or_kern

    parts.append(letter(r_d, x, baseline, s, ink, outline=outline))
    x += r_w * s + tracking
    parts.append(letter(e_d, x, baseline, s, ink, outline=outline))
    x += e_w * s
    return "\n    ".join(parts), x


def svg(view_w: float, view_h: float, body: str, label: str = "Lore") -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_w:.0f} {view_h:.0f}" fill="none" role="img" aria-label="{label}">
  <title>{label}</title>
  {body}
</svg>
'''


# --- compact wordmark ---
FS = 120
PAD_X, PAD_TOP = 28, 36
baseline = PAD_TOP + CAP * (FS / upem)
wm, right = wordmark_parts(FS, PAD_X, baseline, "#14161c", "#5B5BD6", "#E8B84A")
wm_w = right + PAD_X
wm_h = baseline + 18 + 20
wordmark = svg(wm_w, wm_h, wm)

wm_dark, _ = wordmark_parts(FS, PAD_X, baseline, "#F4F3EF", "#9B9BF0", "#E8B84A")
wordmark_dark_inner = wm_dark

# --- signature: wordmark + slogan ---
slogan_y = baseline + 48
logo_h = slogan_y + 40
logo_w = wm_w
logo_body = f'''{wm}
  <text x="{PAD_X:.0f}" y="{slogan_y:.0f}" fill="#5c6370" font-family="{FONTS}" font-size="15" font-weight="450">{SLOGAN}</text>'''
logo = svg(logo_w, logo_h, logo_body)

logo_dark_body = f'''<rect width="{logo_w:.0f}" height="{logo_h:.0f}" rx="28" fill="#0F1117"/>
    {wordmark_dark_inner}
  <text x="{PAD_X:.0f}" y="{slogan_y:.0f}" fill="#9AA3B0" font-family="{FONTS}" font-size="15" font-weight="450">{SLOGAN}</text>'''
logo_dark = svg(logo_w, logo_h, logo_dark_body)

# --- stacked: wordmark + centered slogan ---
cx = logo_w / 2
# Center the wordmark in the wider canvas
shift = (logo_w - wm_w) / 2
stacked_wm, _ = wordmark_parts(FS, PAD_X + shift, baseline, "#14161c", "#5B5BD6", "#E8B84A")
stacked_body = f'''{stacked_wm}
  <text x="{cx:.1f}" y="{slogan_y:.0f}" text-anchor="middle" fill="#5c6370" font-family="{FONTS}" font-size="15" font-weight="450">{SLOGAN}</text>'''
stacked = svg(logo_w, logo_h, stacked_body)

# --- small lockup (nav): same wordmark, tighter padding ---
FS2 = 64
PAD2, TOP2 = 8, 14
base2 = TOP2 + CAP * (FS2 / upem)
lock, lock_r = wordmark_parts(FS2, PAD2, base2, "#14161c", "#5B5BD6", "#E8B84A")
lock_w, lock_h = lock_r + PAD2, base2 + 12
lockup = svg(lock_w, lock_h, lock)

# GitHub README: white fill + black outline so the mark stays readable on dark pages.
wm_gh, _ = wordmark_parts(FS, PAD_X, baseline, "#FFFFFF", "#5B5BD6", "#E8B84A", outline="#0B0D12")
wordmark_gh = svg(wm_w, wm_h, wm_gh)

root.joinpath("lore-wordmark.svg").write_text(wordmark, encoding="utf-8")
root.joinpath("lore-wordmark-gh.svg").write_text(wordmark_gh, encoding="utf-8")
root.joinpath("lore-logo.svg").write_text(logo, encoding="utf-8")
root.joinpath("lore-logo-dark.svg").write_text(logo_dark, encoding="utf-8")
root.joinpath("lore-logo-stacked.svg").write_text(stacked, encoding="utf-8")
root.joinpath("lore-lockup.svg").write_text(lockup, encoding="utf-8")
print(f"wordmark {wm_w:.0f}x{wm_h:.0f}  logo {logo_w:.0f}x{logo_h:.0f}  lockup {lock_w:.0f}x{lock_h:.0f}")
print(f"baseline {baseline:.1f}  right {right:.1f}")
