#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "assets/img/og-card.png"
W, H = 1200, 630
paper = (244, 240, 231)
ink = (20, 34, 45)
navy = (16, 43, 59)
burgundy = (122, 46, 52)
brass = (179, 138, 69)
muted = (64, 81, 92)

img = Image.new("RGB", (W, H), paper)
d = ImageDraw.Draw(img)

# System fonts; fallback to Pillow default if unavailable.
def font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()

serif = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
serif_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
sans = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
sans_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Framing and archival grid.
d.rectangle((25, 25, W - 25, H - 25), outline=brass, width=2)
for y in range(45, H, 34):
    d.line((45, y, W - 45, y), fill=(232, 226, 214), width=1)

# Right visual field.
d.rectangle((820, 0, W, H), fill=navy)
d.ellipse((875, 90, 1135, 350), outline=brass, width=3)
d.ellipse((910, 125, 1100, 315), outline=(216, 189, 134), width=1)
d.text((1005, 205), "AD", anchor="mm", fill=paper, font=font(serif_bold, 70))
d.text((1005, 275), "PRAGUE", anchor="mm", fill=(216, 189, 134), font=font(sans_bold, 17))

# Data lines.
pts1 = [(845, 470), (890, 450), (935, 475), (980, 405), (1025, 430), (1070, 365), (1115, 385), (1160, 330)]
pts2 = [(845, 535), (890, 515), (935, 490), (980, 505), (1025, 465), (1070, 480), (1115, 440), (1160, 452)]
d.line(pts1, fill=(216, 189, 134), width=6)
d.line(pts2, fill=(199, 98, 106), width=5)

# Text block.
d.text((70, 75), "ECONOMIC HISTORIAN · PRAGUE", fill=burgundy, font=font(sans_bold, 17))
d.text((70, 135), "Adam", fill=ink, font=font(serif, 76))
d.text((70, 215), "Dittrich", fill=ink, font=font(serif_bold, 92))
d.line((72, 335, 735, 335), fill=(160, 151, 136), width=2)

lines = [
    "Monetary & financial history",
    "Interwar Central Europe",
    "Historical data & economic thought",
]
y = 375
for line in lines:
    d.text((72, y), line, fill=muted, font=font(sans, 25))
    y += 42

d.rectangle((70, 535, 545, 580), fill=burgundy)
d.text((92, 557), "ARCHIVES  →  DATA  →  ARGUMENT", anchor="lm", fill=paper, font=font(sans_bold, 15))

img.save(out, quality=95)
print(out)
