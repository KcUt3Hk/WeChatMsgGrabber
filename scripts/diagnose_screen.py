import sys
import os
from PIL import Image, ImageGrab
import logging

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.ocr_processor import OCRProcessor
from services.config_manager import ConfigManager

def diagnose():
    print("=== Diagnostic Start ===")
    
    # 1. Capture Full Screen
    print("Capturing full screen...")
    try:
        img = ImageGrab.grab()
        print(f"Screen captured: {img.size}")
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
        os.makedirs(output_dir, exist_ok=True)
        img_path = os.path.join(output_dir, "debug_full_screen.png")
        img.save(img_path)
        print(f"Saved full screen to: {img_path}")
    except Exception as e:
        print(f"Screen capture failed: {e}")
        return

    # 2. Initialize OCR
    print("Initializing OCR...")
    try:
        cfg = ConfigManager().get_config()
        ocr = OCRProcessor(cfg.ocr)
        if not ocr.initialize_engine():
            print("OCR Engine initialization failed")
            return
        print("OCR Engine initialized")
    except Exception as e:
        print(f"OCR init failed: {e}")
        return

    # 3. Run OCR on full screen
    print("Running OCR on full screen (this may take a moment)...")
    try:
        # Scale down if too large to speed up
        w, h = img.size
        if w > 2000:
            scale = 2000 / w
            img_small = img.resize((int(w * scale), int(h * scale)))
            print(f"Resized for OCR: {img_small.size}")
        else:
            img_small = img
            
        results = ocr.extract_text_regions(img_small)
        print(f"Found {len(results)} text regions")
        
        found_wechat = False
        print("\n--- Detected Text (First 20) ---")
        for i, r in enumerate(results):
            text = r.text.strip()
            if i < 20:
                print(f"[{i}] {text}")
            if "微信" in text or "WeChat" in text:
                found_wechat = True
        
        if found_wechat:
            print("\nSUCCESS: Found '微信' or 'WeChat' keyword in screen text.")
        else:
            print("\nWARNING: Did not find '微信' or 'WeChat' keyword in screen text.")
            
    except Exception as e:
        print(f"OCR execution failed: {e}")

if __name__ == "__main__":
    diagnose()
