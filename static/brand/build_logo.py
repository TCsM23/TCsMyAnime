"""Build the TCsM (The Cat's Meow) cat mark + TCsMyAnime wordmark as SVG."""
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

OUT = Path(sys.argv[1])
FONT = Path(__file__).parent / "fs/package/files/lilita-one-latin-400-normal.woff"

# Mood board palette
INK, DKRED, RED, VAN, NAVY, SKY = "#050309", "#780000", "#c1121f", "#fdf0d5", "#003049", "#669bbc"

# ---------- the cat (designed on a 512 x 512 canvas) ----------
CAT = f"""
<g stroke="{INK}" stroke-linejoin="round" stroke-linecap="round">
  <!-- ears -->
  <path d="M138 236 L116 92 Q114 70 134 80 L236 158 Z" fill="{RED}" stroke-width="14"/>
  <path d="M374 236 L396 92 Q398 70 378 80 L276 158 Z" fill="{RED}" stroke-width="14"/>
  <path d="M152 206 L140 116 L206 162 Z" fill="{VAN}" stroke="none"/>
  <path d="M360 206 L372 116 L306 162 Z" fill="{VAN}" stroke="none"/>
  <!-- head -->
  <path d="M100 302 C100 200 168 148 256 148 C344 148 412 200 412 302 C412 388 342 430 256 430
           C170 430 100 388 100 302 Z" fill="{RED}" stroke-width="14"/>
  <!-- forehead stripes -->
  <path d="M256 162 L256 196 M226 166 L232 192 M286 166 L280 192" stroke="{DKRED}" stroke-width="9" fill="none"/>
  <!-- muzzle -->
  <path d="M256 318 C218 300 170 318 172 356 C174 392 222 406 256 384 C290 406 338 392 340 356
           C342 318 294 300 256 318 Z" fill="{VAN}" stroke="none"/>
  <!-- open eye -->
  <ellipse cx="190" cy="270" rx="34" ry="38" fill="{VAN}" stroke-width="10"/>
  <circle cx="198" cy="276" r="21" fill="{NAVY}" stroke="none"/>
  <circle cx="198" cy="276" r="9" fill="{INK}" stroke="none"/>
  <circle cx="208" cy="264" r="7" fill="{VAN}" stroke="none"/>
  <!-- winking eye -->
  <path d="M290 278 Q322 246 354 278" fill="none" stroke-width="12"/>
  <path d="M296 252 L284 240 M348 252 L360 240" fill="none" stroke-width="8"/>
  <!-- nose + mouth -->
  <path d="M240 326 L272 326 Q268 342 256 346 Q244 342 240 326 Z" fill="{DKRED}" stroke-width="7"/>
  <path d="M256 346 L256 356" fill="none" stroke-width="8"/>
  <path d="M228 356 Q242 374 256 356 Q270 374 284 356" fill="none" stroke-width="8"/>
  <path d="M247 366 Q256 386 265 366" fill="{RED}" stroke-width="6"/>
  <!-- whiskers -->
  <path d="M168 344 L70 330 M170 364 L74 376 M344 344 L442 330 M342 364 L438 376" fill="none" stroke-width="8"/>
</g>
"""


def badge(size=512):
    """Cat on a navy disc with a sky-blue ring: the main mark / app icon."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="{size}" height="{size}" role="img" aria-label="TCsM cat logo">
  <title>TCsM — The Cat's Meow</title>
  <circle cx="256" cy="256" r="244" fill="{NAVY}" stroke="{SKY}" stroke-width="16"/>
  <g transform="translate(256 262) scale(0.86) translate(-256 -290)">{CAT}</g>
</svg>"""


def cat_only(size=512):
    """Just the cat, transparent background (for stickers, loading screens, etc.)."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="56 60 400 384" width="{size}" height="{int(size * 384 / 400)}" role="img" aria-label="TCsM cat">
  <title>TCsM — The Cat's Meow</title>{CAT}
</svg>"""


def text_path(text, font, size):
    """Turn a string into one SVG path using the font's glyph outlines. Returns (d, width)."""
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    scale = size / upm
    hmtx = font["hmtx"]
    pen = SVGPathPen(gs)
    x = 0
    for ch in text:
        name = cmap[ord(ch)]
        tpen = TransformPen(pen, (scale, 0, 0, -scale, x, 0))  # flip y: fonts are y-up
        gs[name].draw(tpen)
        x += hmtx[name][0] * scale
    return pen.getCommands(), x


def wordmark_logo(font, on_dark=True):
    """Horizontal lockup: badge + 'TCsMyAnime' + 'THE CAT'S MEOW' tagline."""
    main = VAN if on_dark else INK
    d1, w1 = text_path("TCs", font, 132)
    d2, w2 = text_path("MyAnime", font, 132)
    d3, w3 = text_path("THE CAT'S MEOW", font, 40)
    tx = 290  # text starts right of the 256-wide badge
    width = int(tx + w1 + w2 + 30)
    stroke = f' stroke="{INK}" stroke-width="10" stroke-linejoin="round" paint-order="stroke"' if not on_dark else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 280" width="{width}" height="280" role="img" aria-label="TCsMyAnime">
  <title>TCsMyAnime by TCsM — The Cat's Meow</title>
  <g transform="translate(12 12) scale(0.5)">
    <circle cx="256" cy="256" r="244" fill="{NAVY}" stroke="{SKY}" stroke-width="16"/>
    <g transform="translate(256 262) scale(0.86) translate(-256 -290)">{CAT}</g>
  </g>
  <path transform="translate({tx} 168)" d="{d1}" fill="{RED}"{stroke}/>
  <path transform="translate({tx + w1} 168)" d="{d2}" fill="{main}"/>
  <path transform="translate({tx + 4} 228)" d="{d3}" fill="{SKY}" letter-spacing="4"/>
</svg>"""


font = TTFont(FONT)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "tcsm-mark.svg").write_text(badge())
(OUT / "tcsm-cat.svg").write_text(cat_only())
(OUT / "tcsmyanime-logo.svg").write_text(wordmark_logo(font, on_dark=True))
(OUT / "tcsmyanime-logo-light.svg").write_text(wordmark_logo(font, on_dark=False))
print("written:", *sorted(p.name for p in OUT.iterdir()))


def favicon():
    """Rounded navy square, cat filling the frame: stays readable at 16-32 px."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="TCsM">
  <rect width="512" height="512" rx="112" fill="{NAVY}"/>
  <g transform="translate(256 270) scale(1.12) translate(-256 -290)">{CAT}</g>
</svg>"""


(OUT / "tcsm-favicon.svg").write_text(favicon())
