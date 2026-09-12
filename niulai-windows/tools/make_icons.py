# -*- coding: utf-8 -*-
"""从 niulai.jpg 生成托盘图标和 Windows 应用图标。

牛来原图是一张 640x640 的照片风梗图：JPEG 没有透明通道，底部还压着
"找一车牛来弄你"的大字，整张缩进任务栏托盘会糊成一团。所以这里裁出
最前面那只牛的头，再套一个圆形遮罩（圆外全透明），导出 PNG 和 ICO。

用法：python tools/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "niulai.jpg"

# 最前面那只牛的头，按原图 640x640 量出来的比例（换分辨率也会自动跟着缩放）
CROP_RATIO = (0.0625, 0.0781, 0.6563, 0.6719)


def head_crop(source: Path) -> Image.Image:
    """裁出最前面那只牛的头。"""
    image = Image.open(source).convert("RGBA")
    width, height = image.size
    left, top, right, bottom = CROP_RATIO
    box = (round(width * left), round(height * top),
           round(width * right), round(height * bottom))
    return image.crop(box)


def circle_icon(image: Image.Image, size: int) -> Image.Image:
    """方形图 -> 圆形图标，圆外完全透明。"""
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))

    # 先放大 4 倍再画圆，缩回目标尺寸时圆边更顺滑（16x16 也不毛刺）
    big = size * 4
    scaled = canvas.resize((big, big), Image.LANCZOS)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    scaled.putalpha(mask)
    return scaled.resize((size, size), Image.LANCZOS)


def main() -> None:
    head = head_crop(SOURCE)

    tray = circle_icon(head, 256)
    tray.save(ASSETS / "niulai_tray.png")
    print(f"写出 {ASSETS / 'niulai_tray.png'}")

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon = circle_icon(head, 256)
    icon.save(ASSETS / "niulai.ico", sizes=sizes)
    print(f"写出 {ASSETS / 'niulai.ico'}")


if __name__ == "__main__":
    main()
