"""Copies the screenshots the README, proxmox-setup.md and linux-setup.md show from a
run.sh output directory into docs/screenshots/, and builds the theme grid from the per-theme captures.

Usage: readme_images.py <run.sh output dir> <docs/screenshots dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

src, dest = Path(sys.argv[1]), Path(sys.argv[2])
dest.mkdir(parents=True, exist_ok=True)

COPIES = {
    "windows-main.png": "windows-main.png",
    "linux-main.png": "linux-main.png",
    "windows-state-multiselect.png": "multi-select.png",
    "windows-state-ungrouped.png": "flat-list.png",
    "linux-settings.png": "linux-settings.png",
    # proxmox-setup.md, App Setup
    "windows-add-cluster.png": "windows-add-cluster.png",
    "linux-add-cluster.png": "linux-add-cluster.png",
    "linux-export-desktop.png": "linux-export-desktop.png",
    "windows-add-cluster-password.png": "windows-add-cluster-password.png",
    "linux-add-cluster-password.png": "linux-add-cluster-password.png",
    "windows-password-prompt.png": "windows-password-prompt.png",
    "linux-password-prompt.png": "linux-password-prompt.png",
    # linux-setup.md
    "linux-prereqs-fedora.png": "linux-prereqs-fedora.png",
    "linux-prereqs-debian.png": "linux-prereqs-debian.png",
    "linux-icon-picker.png": "linux-icon-picker.png",
}


def save(image, name):
    # Palette PNGs are a fraction of the size and look the same for flat UI colours
    image.convert("RGB").quantize(256, method=Image.Quantize.MEDIANCUT,
                                  dither=Image.Dither.NONE).save(dest / name, optimize=True)
    print(f"wrote {dest / name}")


for source, name in COPIES.items():
    save(Image.open(src / source), name)

# Theme grid: each theme's main window, scaled down and labelled
THEMES = ["Catppuccin Mocha", "Catppuccin Latte", "Nord", "Dracula", "OLED Dark"]
COLS, SCALE, GAP, LABEL = 3, 0.5, 16, 34
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
tiles = [(theme, Image.open(src / f"windows-main-{theme.lower().replace(' ', '-')}.png"))
         for theme in THEMES]
# The sixth cell shows the Appearance flyout where themes and accents are picked
flyout = Image.open(src / "linux-appearance.png")
tiles.append(("Appearance flyout (Linux)", flyout))
w = round(tiles[0][1].width * SCALE)
h = round(tiles[0][1].height * SCALE)
rows = -(-len(tiles) // COLS)
grid = Image.new("RGB", (COLS * w + (COLS + 1) * GAP, rows * (h + LABEL) + (rows + 1) * GAP),
                 (17, 17, 27))
draw = ImageDraw.Draw(grid)
for i, (label, image) in enumerate(tiles):
    x = GAP + (i % COLS) * (w + GAP)
    y = GAP + (i // COLS) * (h + LABEL + GAP)
    draw.text((x, y + 4), label, font=font, fill=(205, 214, 244))
    grid.paste(ImageOps.fit(image.convert("RGB"), (w, h), Image.Resampling.LANCZOS), (x, y + LABEL))
save(grid, "themes.png")
