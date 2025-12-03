#!/usr/bin/env python3
"""
使用 AutoScrollController 根据覆盖坐标截取聊天区域并保存到文件的调试脚本。

用途：
- 在 macOS 受限环境下（窗口枚举可能失败），通过 --chat-area 直接指定聊天区域坐标。
- 调用项目内与 CLI 一致的截图逻辑（pyautogui.screenshot + AutoScrollController.get_chat_area_bounds）。
- 将截图保存为 PNG，便于与 OCR 预览脚本（scripts/preview_text_regions.py）联动验证。

示例：
python scripts/capture_chat_area.py --chat-area 200,100,900,1100 --out ./outputs/debug_current_capture.png
"""

import argparse
import logging
import os
import sys
from typing import Tuple

from PIL import Image

# 动态注入项目根路径，确保可导入 services/* 等模块
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.auto_scroll_controller import AutoScrollController  # noqa: E402


def parse_chat_area(value: str) -> Tuple[int, int, int, int]:
    """将形如 "x,y,w,h" 的字符串解析为四元组。

    参数：
    - value: 字符串坐标，示例 "200,100,900,1100"

    返回：
    - (x, y, w, h) 四元组

    异常：
    - ValueError: 当格式或数值非法时抛出
    """
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise ValueError("chat-area 必须为 'x,y,w,h' 四段")
    try:
        x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
    except Exception as e:
        raise ValueError(f"chat-area 解析失败: {e}")
    if w <= 0 or h <= 0:
        raise ValueError("chat-area 宽高必须为正数")
    return x, y, w, h


def save_image(img: Image.Image, out_path: str) -> None:
    """将 PIL Image 保存为 PNG 文件，自动创建目录。

    参数：
    - img: 待保存的图像对象
    - out_path: 输出文件路径（含文件名），例如 ./outputs/debug_current_capture.png
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, format="PNG")


def main() -> None:
    """主入口：解析参数，执行截图，并保存到目标路径。"""
    parser = argparse.ArgumentParser(description="Capture WeChat chat area using override coordinates")
    parser.add_argument("--chat-area", required=True, help="覆盖聊天区域坐标 'x,y,w,h'")
    parser.add_argument("--out", default="./outputs/debug_current_capture.png", help="输出图片路径（PNG）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    logger = logging.getLogger(__name__)

    # 解析坐标
    try:
        x, y, w, h = parse_chat_area(args.chat_area)
    except ValueError as ve:
        logger.error(str(ve))
        sys.exit(2)

    # 创建控制器并设置覆盖坐标
    ctrl = AutoScrollController()
    ctrl.set_override_chat_area((x, y, w, h))

    # 执行截图
    img = ctrl.capture_current_view()
    if img is None:
        logger.error("截图失败：请确认 macOS 已授予屏幕录制权限，并且坐标覆盖正确。")
        sys.exit(1)

    # 保存文件
    save_image(img, args.out)
    logger.info("已保存聊天区域截图到：%s", os.path.abspath(args.out))


if __name__ == "__main__":
    main()