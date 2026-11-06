"""Draw the Shop icons of the draft packs (issue #27). The client's cache has no draft pictures (FO3 ID
loaded them from Garena's CDN), so these are drawn here in the style of its player pack icons: a dark
starred disc, a player with a tick, the season tag and the number of players to pick.
The server serves assets/externalAssets/shop/<icon>.png before the client's own images.

Usage: python tools/draft_icons.py                      the built-in draft packs' icons
       python tools/draft_icons.py <icon> <tag> <picks>  one more, e.g. 9900014 "'14" 3
Needs Pillow (only to draw them; the server just sends the PNGs)."""
import math, os, sys
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "externalAssets", "shop")
W, H, S = 170, 120, 4  # the client's shop image size; drawn 4x then scaled down (smooth edges)
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "ariblk.ttf")  # Arial Black
TAGS = {  # season tag: (top colour, bottom colour, text colour)
    "'06": ("#4aa3ff", "#1a4fb0", "white"),
    "'17": ("#36c48a", "#0b6b4a", "white"),
    "WL": ("#ffe08a", "#b8861c", "#3a2600"),
}
BUILT_IN = ((9900006, "'06", 3), (9900088, "'17", 5), (9900093, "WL", 3))  # http_config PACKS


def font(px):
    try:
        return ImageFont.truetype(FONT, px * S)
    except OSError:
        return ImageFont.load_default(px * S)


def fill(img, mask, top, bottom):
    """Paint a vertical gradient through a mask."""
    col = Image.new("RGB", (1, 2))
    col.putpixel((0, 0), Image.new("RGB", (1, 1), top).getpixel((0, 0)))
    col.putpixel((0, 1), Image.new("RGB", (1, 1), bottom).getpixel((0, 0)))
    img.paste(col.resize(img.size, Image.BILINEAR), (0, 0), mask)


def star(d, cx, cy, r, colour):
    d.polygon([(cx + (r if i % 2 == 0 else r * 0.45) * math.sin(i * math.pi / 5),
                cy - (r if i % 2 == 0 else r * 0.45) * math.cos(i * math.pi / 5)) for i in range(10)], fill=colour)


def draw(tag, picks):
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = lambda *v: [x * S for x in v]
    cx, cy, r = 84, 50, 44
    # a ribbon behind the disc, then the disc with its starred rim
    d.polygon(s(98, 0, 122, 0, 82, 96, 58, 96), fill="#1d6b45")
    d.ellipse(s(cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3), fill="#30343b")
    disc = Image.new("L", img.size)
    ImageDraw.Draw(disc).ellipse(s(cx - r, cy - r, cx + r, cy + r), fill=255)
    fill(img, disc, "#24364b", "#06080c")
    for i in range(16):
        a = i * math.pi / 8
        star(d, *s(cx + (r - 4) * math.sin(a), cy - (r - 4) * math.cos(a), 2.6), "#f4c64e" if i % 2 else "#e8ecf2")
    # the player (head + shoulders, cut off at the bottom) and the tick
    body = Image.new("L", img.size)
    b = ImageDraw.Draw(body)
    b.ellipse(s(cx - 12, 22, cx + 10, 44), fill=255)
    b.ellipse(s(cx - 25, 47, cx + 23, 92), fill=255)
    b.rectangle(s(0, 74, W, H), fill=0)
    fill(img, body, "#8fe2ff", "#1a7fc8")
    tick = s(cx + 4, 58, cx + 12, 67, cx + 30, 44)
    d.line(tick, fill="#0d1a08", width=10 * S, joint="curve")
    d.line(tick, fill="#9be04e", width=6 * S, joint="curve")
    # the number of players to pick, white with a dark edge
    f, at = font(34), s(cx + 12, 110)
    d.text(at, str(picks), font=f, anchor="ms", fill="#111317", stroke_width=3 * S, stroke_fill="#111317")
    num = Image.new("L", img.size)
    ImageDraw.Draw(num).text(at, str(picks), font=f, anchor="ms", fill=255)
    fill(img, num, "#ffffff", "#b9c3cf")
    # the season tag, on two cards behind it like the client's own ('06 on its '06 packs)
    top, bottom, ink = TAGS.get(tag, ("#9aa4b1", "#4a525c", "white"))
    x, y, w, h = 14, 78, 48, 26
    for k, shade in ((6, "#20242a"), (3, "#3a4048")):
        d.rounded_rectangle(s(x + k, y - k, x + w + k, y + h - k), radius=5 * S, fill=shade, outline="#11151a", width=S)
    d.rounded_rectangle(s(x - 1, y - 1, x + w + 1, y + h + 1), radius=6 * S, fill="#f2f5f8")
    box = Image.new("L", img.size)
    ImageDraw.Draw(box).rounded_rectangle(s(x + 1, y + 1, x + w - 1, y + h - 1), radius=5 * S, fill=255)
    fill(img, box, top, bottom)
    d.text(s(x + w / 2, y + h / 2 + 1), tag, font=font(16 if len(tag) < 3 else 14), anchor="mm", fill=ink)
    return img.resize((W, H), Image.LANCZOS)


def main(args):
    jobs = [(int(args[0]), args[1], int(args[2]))] if args else BUILT_IN
    os.makedirs(OUT, exist_ok=True)
    for icon, tag, picks in jobs:
        path = os.path.join(OUT, f"{icon}.png")
        draw(tag, picks).save(path, optimize=True)
        print(path)


if __name__ == "__main__":
    main(sys.argv[1:])
