#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成应用图标：对话气泡（语音）+ 文字行 + 字幕条，输出 PNG 与多尺寸 ICO。

用法: python make_icon.py
输出: icon.png (512x512) / icon.ico (含 16~256 多尺寸)
"""

from pathlib import Path

from PIL import Image, ImageDraw

SS = 2048          # 超采样画布尺寸，最后缩小到 512 得到平滑边缘
FINAL = 512

# 配色
BG_TOP = (20, 30, 48)       # 深蓝
BG_BOTTOM = (36, 59, 85)    # 蓝灰
BUBBLE = (255, 255, 255)    # 对话气泡
TEXT_LINE = (36, 59, 85)    # 气泡内的文字行
ACCENT = (0, 229, 255)      # 青色字幕条


def draw_background() -> Image.Image:
    """垂直渐变背景。"""
    img = Image.new("RGB", (SS, SS), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(SS):
        t = y / (SS - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
        d.line([(0, y), (SS, y)], fill=color)
    return img


def main():
    img = draw_background()
    d = ImageDraw.Draw(img, "RGBA")

    # 对话气泡（左上到右下的圆角矩形）+ 左下小尾巴
    bubble = (352, 400, 1696, 1296)
    d.rounded_rectangle(bubble, radius=170, fill=BUBBLE)
    d.polygon([(560, 1260), (560, 1500), (830, 1260)], fill=BUBBLE)

    # 气泡内三条"文字"横线，长短错落
    line_h, line_r = 92, 46
    d.rounded_rectangle((544, 620, 1504, 620 + line_h), radius=line_r, fill=TEXT_LINE)
    d.rounded_rectangle((544, 802, 1248, 802 + line_h), radius=line_r, fill=TEXT_LINE)
    d.rounded_rectangle((544, 984, 1408, 984 + line_h), radius=line_r, fill=TEXT_LINE)

    # 底部青色字幕条：一条高亮 + 两条短白条，模拟双行字幕
    d.rounded_rectangle((352, 1600, 1696, 1744), radius=72, fill=ACCENT)
    d.rounded_rectangle((352, 1832, 1152, 1936), radius=52, fill=(255, 255, 255, 200))
    d.rounded_rectangle((352, 1832, 1696, 1836), radius=2, fill=(0, 0, 0, 0))

    # 收尾：缩放到最终尺寸，导出 PNG 与多尺寸 ICO
    img = img.resize((FINAL, FINAL), Image.LANCZOS)
    out_dir = Path(__file__).parent
    img.save(out_dir / "icon.png")

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(out_dir / "icon.ico", sizes=ico_sizes)
    print(f"已生成 {out_dir / 'icon.png'} 和 {out_dir / 'icon.ico'}")


if __name__ == "__main__":
    main()
