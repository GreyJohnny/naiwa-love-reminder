# -*- coding: utf-8 -*-
"""从 laugh2.png 生成托盘图标和 Windows 应用图标。

原版素材是 RGB（没有透明通道）的奶蛙图，直接拿来做托盘图标会是一个白色方块，
这里用洪水填充把四周连成片的浅色背景抠成透明，再导出 PNG 和 ICO。

用法：python tools/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "laugh2.png"

TOLERANCE = 42          # 背景是浅灰白带噪点，紧一点免得啃到奶蛙的黄皮
PAD_RATIO = 0.06        # 缩放到方形画布时留的边距


def keyed_out(source: Path, tolerance: int = TOLERANCE) -> Image.Image:
    """把四周连成片的背景色抠成透明。"""
    image = Image.open(source).convert("RGBA")
    width, height = image.size
    for seed in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        ImageDraw.floodfill(image, seed, (0, 0, 0, 0), thresh=tolerance)
    return image


def square_icon(image: Image.Image, size: int, pad_ratio: float = PAD_RATIO) -> Image.Image:
    """裁到内容、居中贴到方形画布、按尺寸缩放、留边距。"""
    box = image.getbbox()
    if box:
        image = image.crop(box)
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2), image)
    pad = int(side * pad_ratio)
    inner = canvas.resize((size - 2 * pad, size - 2 * pad), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(inner, (pad, pad), inner)
    return out


def main() -> None:
    keyed = keyed_out(SOURCE)

    tray = square_icon(keyed, 256)
    tray.save(ASSETS / "naiwa_tray.png")
    print(f"写出 {ASSETS / 'naiwa_tray.png'}")

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon = square_icon(keyed, 256)
    icon.save(ASSETS / "naiwa.ico", sizes=sizes)
    print(f"写出 {ASSETS / 'naiwa.ico'}")


if __name__ == "__main__":
    main()
