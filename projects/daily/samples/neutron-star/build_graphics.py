"""Build the SIMULATION / ILLUSTRATION frames for the sample with Pillow.

All frames are honest schematics, stamped with their representation label
(simulation / illustration - not to scale). No photographic realism implied.
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
W, H = 1080, 1920
FONT = r"C:\Windows\Fonts\arialbd.ttf"
FONT_REG = r"C:\Windows\Fonts\arial.ttf"

BG = (5, 7, 15)


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT if bold else FONT_REG, size)


def stamp_label(img: Image.Image, text: str) -> None:
    d = ImageDraw.Draw(img)
    f = font(30)
    bbox = d.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = W - tw - 46, 40
    d.rounded_rectangle([x - 18, y - 12, x + tw + 18, y + th + 12], radius=10,
                        fill=(0, 0, 0, 140))
    d.text((x, y), text, font=f, fill=(255, 255, 255, 150))


def starfield(img: Image.Image, seed: int, n: int = 160) -> None:
    rng = random.Random(seed)
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        s = rng.choice([1, 1, 2])
        a = rng.randint(60, 200)
        d.ellipse([x, y, x + s, y + s], fill=(255, 255, 255, a))


def sphere(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color: tuple) -> None:
    for i in range(14, 0, -1):
        rr = r * (i / 14)
        alpha = int(150 * (i / 14))
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                  fill=(color[0], color[1], color[2], alpha))


def collapse_frames() -> None:
    radii = [430, 230, 95]
    colors = [(255, 170, 60), (255, 200, 90), (180, 220, 255)]
    for i, (r, c) in enumerate(zip(radii, colors), start=1):
        img = Image.new("RGBA", (W, H), BG + (255,))
        starfield(img, 7 + i)
        d = ImageDraw.Draw(img)
        sphere(d, W // 2, H // 2 - 140, r, c)
        if i == 1:
            note = "a giant star"
        elif i == 2:
            note = "fuel gone - core collapsing"
        else:
            note = "20 km in under a second"
        f = font(44)
        tw = d.textbbox((0, 0), note, font=f)[2]
        d.text((W // 2 - tw // 2, H // 2 - 140 + r + 90), note, font=f,
               fill=(220, 230, 255, 220))
        stamp_label(img, "SIMULATION")
        img.convert("RGB").save(os.path.join(ASSETS, f"collapse_{i}.png"))


def neutron_sea_frames() -> None:
    # frame 1: atoms (nucleus + electron rings)
    img = Image.new("RGBA", (W, H), BG + (255,))
    starfield(img, 21)
    d = ImageDraw.Draw(img)
    for k, (cx, cy, r) in enumerate([(300, 700, 150), (760, 1080, 190), (330, 1450, 120)]):
        d.ellipse([cx - 34, cy - 34, cx + 34, cy + 34], fill=(255, 200, 90, 255))
        for t in range(0, 360, 45):
            x2 = cx + r * math.cos(math.radians(t))
            y2 = cy + r * math.sin(math.radians(t))
            d.ellipse([x2 - 8, y2 - 8, x2 + 8, y2 + 8], fill=(120, 200, 255, 220))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(120, 200, 255, 120), width=4)
    f = font(48)
    note = "ordinary matter: electrons orbit a nucleus"
    tw = d.textbbox((0, 0), note, font=f)[2]
    d.text((W // 2 - tw // 2, 1650), note, font=f, fill=(220, 230, 255, 220))
    stamp_label(img, "SIMULATION")
    img.convert("RGB").save(os.path.join(ASSETS, "neutron_sea_1.png"))

    # frame 2: packed sea of neutrons
    img = Image.new("RGBA", (W, H), BG + (255,))
    starfield(img, 22)
    d = ImageDraw.Draw(img)
    rng = random.Random(5)
    for y in range(620, 1560, 62):
        for x in range(140, 940, 62):
            jx = rng.randint(-10, 10)
            jy = rng.randint(-10, 10)
            d.ellipse([x + jx - 16, y + jy - 16, x + jx + 16, y + jy + 16],
                      fill=(160, 210, 255, 230))
    f = font(48)
    note = "gravity crushes them into a sea of neutrons"
    tw = d.textbbox((0, 0), note, font=f)[2]
    d.text((W // 2 - tw // 2, 1650), note, font=f, fill=(220, 230, 255, 220))
    stamp_label(img, "SIMULATION")
    img.convert("RGB").save(os.path.join(ASSETS, "neutron_sea_2.png"))


def sun_city_comparison() -> None:
    img = Image.new("RGBA", (W, H), BG + (255,))
    starfield(img, 33)
    d = ImageDraw.Draw(img)

    cx1, cy1, r1 = 300, 760, 380
    sphere(d, cx1, cy1, r1, (255, 190, 70))
    f = font(64)
    l1 = "2 SUNS' WORTH"
    tw = d.textbbox((0, 0), l1, font=f)[2]
    d.text((cx1 - tw // 2, cy1 - r1 - 120), l1, font=f, fill=(255, 235, 200, 255))
    l1b = "a star's whole mass"
    f2 = font(40)
    tw = d.textbbox((0, 0), l1b, font=f2)[2]
    d.text((cx1 - tw // 2, cy1 - r1 - 40), l1b, font=f2, fill=(200, 210, 235, 220))

    cx2, cy2, r2 = 800, 620, 46
    sphere(d, cx2, cy2, r2, (170, 215, 255))
    # city skyline silhouette under the small sphere
    rng = random.Random(9)
    x = 520
    while x < 1000:
        bw = rng.randint(30, 90)
        bh = rng.randint(90, 330)
        d.rectangle([x, cy2 + 120, x + bw, cy2 + 120 + bh], fill=(120, 150, 200, 120))
        x += bw + rng.randint(6, 20)
    l2 = "20 KM - A CITY"
    tw = d.textbbox((0, 0), l2, font=f)[2]
    d.text((cx2 - tw // 2, cy2 + 520), l2, font=f, fill=(200, 225, 255, 255))

    # arrow from sun to sphere
    d.line([cx1 + r1 + 20, cy1, cx2 - r2 - 20, cy2], fill=(255, 255, 255, 160), width=6)
    d.polygon([(cx2 - r2 - 20, cy2 - 18), (cx2 - r2 + 24, cy2), (cx2 - r2 - 20, cy2 + 18)],
              fill=(255, 255, 255, 200))

    stamp_label(img, "ILLUSTRATION - NOT TO SCALE")
    img.convert("RGB").save(os.path.join(ASSETS, "sun_city_comparison.png"))


def spoon_crop() -> None:
    src = Image.open(os.path.join(ASSETS, "spoon_full.jpg"))
    w, h = src.size
    box = (int(w * 0.18), int(h * 0.12), int(w * 0.82), int(h * 0.9))
    crop = src.crop(box)
    crop = crop.resize((1080, int(crop.size[1] * 1080 / crop.size[0])), Image.LANCZOS)
    crop.save(os.path.join(ASSETS, "spoon_crop.jpg"), quality=92)


def label_pulsar() -> None:
    img = Image.open(os.path.join(ASSETS, "pulsar_art.png")).convert("RGBA")
    d = ImageDraw.Draw(img)
    text = "ARTIST'S IMPRESSION (NASA)"
    f = font(56)
    bbox = d.textbbox((0, 0), text, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w, h = img.size
    x, y = w - tw - 90, 80
    d.rounded_rectangle([x - 30, y - 20, x + tw + 30, y + th + 20], radius=14,
                        fill=(0, 0, 0, 150))
    d.text((x, y), text, font=f, fill=(255, 255, 255, 200))
    img.convert("RGB").save(os.path.join(ASSETS, "pulsar_labeled.png"))


if __name__ == "__main__":
    collapse_frames()
    neutron_sea_frames()
    sun_city_comparison()
    spoon_crop()
    label_pulsar()
    print("graphics built")
    for f in sorted(os.listdir(ASSETS)):
        p = os.path.join(ASSETS, f)
        if os.path.isfile(p):
            print(f, os.path.getsize(p))