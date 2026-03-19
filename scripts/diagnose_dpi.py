
import logging
import platform
import sys
from PIL import ImageGrab
import pyautogui

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DPIDiagnostic")

def diagnose_dpi():
    logger.info(f"System: {platform.system()} {platform.release()}")
    logger.info(f"Python: {sys.version}")

    try:
        # 获取逻辑屏幕尺寸
        screen_w, screen_h = pyautogui.size()
        logger.info(f"Logical Screen Size (pyautogui): {screen_w}x{screen_h}")

        # 获取物理截图尺寸
        screenshot = ImageGrab.grab()
        img_w, img_h = screenshot.size
        logger.info(f"Physical Screenshot Size (ImageGrab): {img_w}x{img_h}")

        # 计算缩放因子
        scale_x = img_w / screen_w
        scale_y = img_h / screen_h
        logger.info(f"Scale Factor: x={scale_x:.2f}, y={scale_y:.2f}")

        if scale_x > 1.1 or scale_y > 1.1:
            logger.warning("Retina/High-DPI display detected!")
            logger.info("NOTE: Coordinates from GUI tools (logical) need to be multiplied by scale factor for ImageGrab (physical).")
        else:
            logger.info("Standard DPI display detected.")

        # 测试带 bbox 的截图
        # 截取屏幕中心 100x100 的区域
        center_x, center_y = screen_w // 2, screen_h // 2
        bbox_logical = (center_x - 50, center_y - 50, center_x + 50, center_y + 50)
        logger.info(f"Attempting capture with logical bbox: {bbox_logical}")
        
        try:
            # 尝试直接使用逻辑坐标
            img_logical = ImageGrab.grab(bbox=bbox_logical)
            logger.info(f"Capture with logical bbox result size: {img_logical.size}")
            
            # 尝试使用物理坐标
            bbox_physical = tuple(int(c * scale_x) for c in bbox_logical)
            logger.info(f"Attempting capture with physical bbox: {bbox_physical}")
            img_physical = ImageGrab.grab(bbox=bbox_physical)
            logger.info(f"Capture with physical bbox result size: {img_physical.size}")
            
        except Exception as e:
            logger.error(f"Error during bbox capture test: {e}")

    except Exception as e:
        logger.error(f"DPI Diagnosis failed: {e}")

if __name__ == "__main__":
    diagnose_dpi()
