"""Akasha banner — YouTube güvenli alanına (1546×423) sığacak şekilde yeniden üret.
Başlık otomatik küçülür: genişlik ≤ 1300px (1546 güvenli alanın içinde rahat).
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import math, random

W, H = 2560, 1440
cx, cy = W // 2, H // 2
# YouTube güvenli alan (tüm cihazlarda görünen): 1546×423 ortalı
SAFE_W = 1546
HEDEF_METIN_W = 1300  # güvenli alanın içinde kenar payı bırak

img = Image.new("RGB", (W, H), (8, 6, 22))
px = img.load()
max_r = ((W // 2) ** 2 + (H // 2) ** 2) ** 0.5
for y in range(H):
    for x in range(0, W, 4):
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        t = min(d / max_r, 1.0)
        r = int(60 * (1 - t) + 10 * t)
        g = int(35 * (1 - t) + 7 * t)
        b = int(95 * (1 - t) + 25 * t)
        for dx in range(4):
            if x + dx < W:
                px[x + dx, y] = (r, g, b)

draw = ImageDraw.Draw(img)
rng = random.Random(108)
for _ in range(180):
    x = rng.randint(0, W - 1); y = rng.randint(0, H - 1)
    sz = rng.choice([1, 2, 3, 4])
    renk = (212, 175, 55) if rng.random() < 0.35 else (220, 220, 240)
    if sz >= 3:
        draw.ellipse([x-sz*2, y-sz*2, x+sz*2, y+sz*2], fill=(renk[0]//4, renk[1]//4, renk[2]//4))
    draw.ellipse([x-sz, y-sz, x+sz, y+sz], fill=renk)

# Mandala — güvenli alana sığsın diye yarıçapları küçülttüm (max 200)
for ring in [200, 160, 120, 80]:
    draw.ellipse([cx-ring, cy-ring, cx+ring, cy+ring], outline=(212, 175, 55), width=2)
for i in range(8):
    a = i * math.pi / 4
    x1, y1 = cx + int(80*math.cos(a)), cy + int(80*math.sin(a))
    x2, y2 = cx + int(200*math.cos(a)), cy + int(200*math.sin(a))
    draw.line([(x1, y1), (x2, y2)], fill=(212, 175, 55), width=1)
    draw.ellipse([x2-5, y2-5, x2+5, y2+5], fill=(212, 175, 55))

img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
draw = ImageDraw.Draw(img)

FONT = "/System/Library/Fonts/HelveticaNeue.ttc"
marka = "Aydınlanmanın Doruk Noktası"
# Otomatik küçült: başlık genişliği ≤ HEDEF_METIN_W
boyut = 150
while boyut > 60:
    f = ImageFont.truetype(FONT, boyut, index=1)
    bb = draw.textbbox((0, 0), marka, font=f)
    if (bb[2]-bb[0]) <= HEDEF_METIN_W:
        break
    boyut -= 4
f_marka = ImageFont.truetype(FONT, boyut, index=1)
bb = draw.textbbox((0, 0), marka, font=f_marka)
mw, mh = bb[2]-bb[0], bb[3]-bb[1]
mx, my = cx - mw//2, cy - mh//2 - 25
for off in range(6, 0, -2):
    draw.text((mx+off, my+off), marka, font=f_marka, fill=(120, 95, 20))
draw.text((mx, my), marka, font=f_marka, fill=(248, 245, 230))
print(f"başlık font {boyut}pt, genişlik {mw}px (güvenli alan {SAFE_W})")

# Tagline — başlığın %42'si kadar font
tag = "ego'nun ötesinde sen kimsin?"
ft = ImageFont.truetype(FONT, max(40, int(boyut*0.42)), index=2)
bbt = draw.textbbox((0, 0), tag, font=ft)
draw.text((cx - (bbt[2]-bbt[0])//2, my + mh + 30), tag, font=ft, fill=(212, 175, 55))

img.save("str(__import__("pathlib").Path(__file__).parent / "banner.png")", "PNG", optimize=True)
print("✓ banner kaydedildi")
