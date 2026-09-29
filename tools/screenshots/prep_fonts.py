"""Writes screenshot-only font copies named after the Windows fonts WPF asks for.

WPF under Wine finds fonts through DirectWrite, by family name, and the Windows
fonts (Segoe UI, Tahoma, Arial) are not redistributable. Open-source stand-ins
are renamed to those families so layout and fallback behave as on Windows:
Selawik (Microsoft's metric-compatible Segoe UI stand-in) for Segoe UI and for
Tahoma (Wine's default UI font, which Windows replaces with Segoe UI), the
Liberation fonts for Arial, Times New Roman and Courier New, and DejaVu Sans for
Segoe UI Symbol. Cascadia Code is the real font.

Usage: prep_fonts.py <source dir> <output dir>
Prints the registry lines that register the output files.
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

# (source file under <source dir>, family it stands in for, style)
MAP = [
    ("selawik/selawk.ttf", "Segoe UI", "Regular"),
    ("selawik/selawkb.ttf", "Segoe UI", "Bold"),
    ("selawik/selawksb.ttf", "Segoe UI Semibold", "Regular"),
    ("selawik/selawkl.ttf", "Segoe UI Light", "Regular"),
    ("selawik/selawk.ttf", "Tahoma", "Regular"),
    ("selawik/selawkb.ttf", "Tahoma", "Bold"),
    ("liberation/LiberationSans-Regular.ttf", "Arial", "Regular"),
    ("liberation/LiberationSans-Bold.ttf", "Arial", "Bold"),
    ("liberation/LiberationSerif-Regular.ttf", "Times New Roman", "Regular"),
    ("liberation/LiberationMono-Regular.ttf", "Courier New", "Regular"),
    ("dejavu/DejaVuSans.ttf", "Segoe UI Symbol", "Regular"),
    ("cascadia/ttf/static/CascadiaCode-Regular.ttf", "Cascadia Code", "Regular"),
    ("cascadia/ttf/static/CascadiaCode-Bold.ttf", "Cascadia Code", "Bold"),
]


def main(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for rel, family, style in MAP:
        font = TTFont(src / rel)
        full = family if style == "Regular" else f"{family} {style}"
        ps = full.replace(" ", "")
        for rec in font["name"].names:
            if rec.nameID in (1, 16):
                rec.string = family
            elif rec.nameID in (2, 17):
                rec.string = style
            elif rec.nameID == 4:
                rec.string = full
            elif rec.nameID == 6:
                rec.string = ps
            elif rec.nameID == 3:
                rec.string = f"{ps}-screenshots"
        font.save(dst / f"{ps}.ttf")
        print(f'"{full} (TrueType)"="{ps}.ttf"')


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
