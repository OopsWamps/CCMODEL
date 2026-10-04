#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染 GUI 并通过 PrintWindow 离屏截图（不抢焦点、不受遮挡影响）。"""

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "subtitle-assistant-gui"))

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

from PIL import Image

import subtitle_gui

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BMPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


app = subtitle_gui.SubtitleApp()
app.update()
time.sleep(0.6)  # 等首次绘制完成
app.update()

hwnd = user32.GetParent(app.winfo_id())
rect = RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
w, h = rect.right - rect.left, rect.bottom - rect.top

hdc = user32.GetWindowDC(hwnd)
memdc = gdi32.CreateCompatibleDC(hdc)
bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
gdi32.SelectObject(memdc, bmp)
user32.PrintWindow(hwnd, memdc, 2)  # PW_RENDERFULLCONTENT

buf = ctypes.create_string_buffer(w * h * 4)
bmi = BMPINFOHEADER()
bmi.biSize = ctypes.sizeof(BMPINFOHEADER)
bmi.biWidth, bmi.biHeight = w, -h
bmi.biPlanes, bmi.biBitCount, bmi.biCompression = 1, 32, 0
gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)

img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
img.convert("RGB").save(Path(__file__).parent / "ui_preview.png")

gdi32.DeleteObject(bmp)
gdi32.DeleteDC(memdc)
user32.ReleaseDC(hwnd, hdc)
app.destroy()
print(f"saved ui_preview.png ({w}x{h})")
