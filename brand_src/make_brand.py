"""Generate the Powerbill Forecast brand images (icon, logo, dark variants) from the artwork.

Put the square artwork into brand_src/ as a .jpg or .png (any name); this script renders the
PNG sizes Home Assistant needs plus the README logo. The brand workflow runs it on every change.
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "custom_components" / "powerbill_forecast" / "brand"
DOCS = ROOT / "docs" / "images"

sources = sorted(p for p in HERE.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
if not sources:
    print("no artwork in brand_src yet - nothing to render")
    raise SystemExit(0)

art = Image.open(sources[0]).convert("RGBA")
side = min(art.size)
left = (art.width - side) // 2
top = (art.height - side) // 2
art = art.crop((left, top, left + side, top + side))


def rounded(im: Image.Image, radius_frac: float) -> Image.Image:
    """Transparent rounded corners, drawn at 4x and scaled down for smooth edges."""
    w, h = im.size
    big = Image.new("L", (w * 4, h * 4), 0)
    r = int(min(w, h) * radius_frac * 4)
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], radius=r, fill=255)
    out = im.copy()
    out.putalpha(big.resize((w, h), Image.LANCZOS))
    return out


OUT.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)
for suffix, size in (("", 256), ("@2x", 512)):
    img = rounded(art.resize((size, size), Image.LANCZOS), 0.18)
    for base in ("icon", "logo", "dark_icon", "dark_logo"):
        img.save(OUT / f"{base}{suffix}.png", optimize=True)
rounded(art.resize((320, 320), Image.LANCZOS), 0.18).save(DOCS / "logo.png", optimize=True)
print("brand images written from", sources[0].name)
