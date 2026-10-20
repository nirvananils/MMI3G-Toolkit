#!/usr/bin/env python3
"""Generate the dinosaur app icon (assets/icon.ico + assets/icon.png).

Draws a simple, bold cartoon dinosaur that stays legible when scaled down to
16x16, using Pillow. Re-run after changing the design:

    python packaging/make_icon.py
"""

import os

from PIL import Image, ImageDraw

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO_ROOT, "assets")

BODY = (76, 175, 80, 255)    # #4caf50
DARK = (27, 94, 32, 255)     # #1b5e20
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
CHEEK = (255, 138, 128, 255)  # rosy cheek
TONGUE = (229, 57, 53, 255)   # cheeky tongue


def draw_dino(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # rounded green background disc for contrast at small sizes
    d.ellipse([6, 6, size - 6, size - 6], fill=(232, 247, 232, 255),
              outline=DARK, width=4)

    ow = 3
    # tail
    d.polygon([(40, 165), (120, 130), (120, 180)], fill=BODY, outline=DARK)
    # body
    d.ellipse([95, 105, 200, 190], fill=BODY, outline=DARK, width=ow)
    # neck
    d.polygon([(170, 130), (200, 55), (228, 66), (200, 150)],
              fill=BODY, outline=DARK)
    # head
    d.ellipse([196, 44, 246, 90], fill=BODY, outline=DARK, width=ow)
    # rosy cheek
    d.ellipse([210, 70, 224, 82], fill=CHEEK)
    # eye (googly, looking up for a goofy look)
    d.ellipse([222, 54, 238, 70], fill=WHITE, outline=DARK)
    d.ellipse([227, 56, 235, 64], fill=BLACK)
    # cheeky grin + sticking-out tongue
    d.arc([206, 70, 238, 92], start=10, end=150, fill=DARK, width=3)
    d.ellipse([214, 84, 226, 96], fill=TONGUE, outline=DARK)
    # back spikes
    for sx in range(112, 188, 18):
        d.polygon([(sx, 108), (sx + 14, 108), (sx + 7, 88)], fill=DARK)
    # legs
    for lx in (110, 140, 165, 186):
        d.rectangle([lx, 180, lx + 13, 214], fill=BODY, outline=DARK)
    return img


def main():
    os.makedirs(ASSETS, exist_ok=True)
    base = draw_dino(256)
    png_path = os.path.join(ASSETS, "icon.png")
    ico_path = os.path.join(ASSETS, "icon.ico")
    base.save(png_path)
    base.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                               (64, 64), (128, 128), (256, 256)])
    print(f"wrote {png_path}")
    print(f"wrote {ico_path}")


if __name__ == "__main__":
    main()
