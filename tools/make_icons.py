"""Generate the PNG app icons from the brand mark. Run: python tools/make_icons.py"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "web" / "assets" / "icons"
START, END = (30, 58, 138), (56, 189, 248)  # #1e3a8a -> #38bdf8, the brand gradient
STAR = [(32, 12), (37.5, 26.5), (52, 32), (37.5, 37.5), (32, 52), (26.5, 37.5), (12, 32), (26.5, 26.5)]


def gradient(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            pixels[x, y] = tuple(round(START[i] + (END[i] - START[i]) * t) for i in range(3))
    return image


def icon(size: int, *, maskable: bool) -> Image.Image:
    scale = 2  # draw at 2x and shrink for smooth edges
    big = size * scale
    image = gradient(big)
    # Maskable icons keep the mark inside the central safe zone; others use more of the canvas.
    fraction = 0.50 if maskable else 0.62
    span = big * fraction
    offset = (big - span) / 2
    points = [(offset + (x - 12) / 40 * span, offset + (y - 12) / 40 * span) for x, y in STAR]
    ImageDraw.Draw(image).polygon(points, fill="white")
    if not maskable:  # rounded corners; maskable icons must be full-bleed
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.22), fill=255)
        image = image.convert("RGBA")
        image.putalpha(mask)
    return image.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192, maskable=False).save(OUT / "icon-192.png")
    icon(512, maskable=False).save(OUT / "icon-512.png")
    icon(512, maskable=True).save(OUT / "maskable-512.png")
    icon(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png")
    print("icons written to", OUT)
