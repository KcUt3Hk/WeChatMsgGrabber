#!/usr/bin/env python3
"""
简单预览脚本：根据给定的矩形坐标 (x, y, w, h) 截取屏幕区域并保存为 PNG。

用途：
- 用于快速验证 --chat-area 覆盖坐标是否对准微信聊天区。

运行示例：
- python3 scripts/capture_rect_preview.py --rect "260,65,873,1211" --out ./debug_chat_area.png
"""

import argparse
import sys
from pathlib import Path

import pyautogui
from PIL import Image


def parse_rect(rect_str: str) -> tuple[int, int, int, int]:
    """
    解析矩形字符串为整数元组 (x, y, w, h)。

    参数：
    - rect_str: 形如 "x,y,w,h" 的字符串。

    返回：
    - (x, y, w, h) 整数元组。
    """
    parts = [p.strip() for p in rect_str.split(',')]
    if len(parts) != 4:
        raise ValueError("--rect 必须为 'x,y,w,h' 形式")
    x, y, w, h = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
    if w <= 0 or h <= 0:
        raise ValueError("宽或高必须为正数")
    return x, y, w, h


def capture_rect(x: int, y: int, w: int, h: int) -> Image.Image:
    """
    截取屏幕上的指定矩形区域并返回 PIL Image。

    参数：
    - x, y, w, h: 截图区域的左上角坐标与宽高。

    返回：
    - PIL Image 对象，表示该区域的截图。
    """
    return pyautogui.screenshot(region=(x, y, w, h))


def main(argv: list[str]) -> int:
    """
    主函数：读取参数，执行截图并保存到指定路径。

    参数：
    - argv: 命令行参数列表（不含程序名）。

    返回：
    - 进程退出码：0 表示成功，非 0 表示失败。
    """
    parser = argparse.ArgumentParser(description="Capture a screen rectangle and save to PNG")
    parser.add_argument("--rect", required=True, help="截图矩形 'x,y,w,h'，例如 '260,65,873,1211'")
    parser.add_argument("--out", default="./debug_chat_area.png", help="输出 PNG 路径（默认 ./debug_chat_area.png）")
    args = parser.parse_args(argv)

    try:
        x, y, w, h = parse_rect(args.rect)
        img = capture_rect(x, y, w, h)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        print(f"Saved preview to: {out_path}")
        return 0
    except Exception as e:
        print(f"Capture failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
