# -*- coding: utf-8 -*-
"""开发用：用 PrintWindow 给指定的窗口"拍证件照"（被别的窗口挡住也能拍）。

用法：python tools/capture_window.py <窗口标题关键字> <输出图片>
"""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PIL import Image

# 进程先声明"我懂高 DPI"，否则在 125%/150% 缩放下 GetWindowRect 拿到的是被虚拟化过的
# 逻辑尺寸，而 PrintWindow 画出来的是物理像素，结果就是截图右边和下边被裁掉。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)      # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

PW_RENDERFULLCONTENT = 0x00000002


def find_windows(keyword: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value
            if keyword in title and user32.IsWindowVisible(hwnd):
                found.append((hwnd, title))
        return True

    user32.EnumWindows(EnumProc(callback), 0)
    return found


def capture(hwnd: int, out_path: Path) -> tuple[int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top

    window_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0

    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
    image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
    image.convert("RGB").save(out_path)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)
    return width, height


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    keyword, out_path = sys.argv[1], Path(sys.argv[2])
    windows = find_windows(keyword)
    if not windows:
        print(f"没找到标题包含「{keyword}」的可见窗口")
        return 1
    for hwnd, title in windows:
        size = capture(hwnd, out_path)
        print(f"hwnd={hwnd} title={title} size={size} -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
