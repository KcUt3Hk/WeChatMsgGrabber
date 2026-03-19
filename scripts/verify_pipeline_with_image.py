import sys
import os
from PIL import Image
from unittest.mock import MagicMock
import logging

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from controllers.main_controller import MainController
from services.config_manager import ConfigManager

def test_pipeline():
    print("=== Pipeline Verification Start ===")
    
    # 1. Load the debug image
    img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "debug_capture_verify.png")
    if not os.path.exists(img_path):
        print(f"Error: Debug image not found at {img_path}")
        return

    try:
        img = Image.open(img_path)
        print(f"Loaded image: {img.size}")
    except Exception as e:
        print(f"Failed to load image: {e}")
        return

    # 2. Initialize Controller
    print("Initializing MainController...")
    try:
        controller = MainController()
        
        # Mock the scroll controller to return our image
        controller.scroll = MagicMock()
        controller.scroll.has_chat_area_override.return_value = True
        controller.scroll.capture_current_view.return_value = img
        controller.scroll.optimize_screenshot_quality.side_effect = lambda x: x # Pass through
        controller.scroll._compare_screenshots.return_value = False # No duplicate
        
        # Ensure OCR is ready
        if not controller.ocr.initialize_engine():
            print("OCR Init failed")
            return
            
    except Exception as e:
        print(f"Controller init failed: {e}")
        return

    # 3. Run run_once
    print("Running controller.run_once()...")
    try:
        messages = controller.run_once()
        print(f"Result: {len(messages)} messages found.")
        
        for i, m in enumerate(messages):
            print(f"Msg[{i}]: {m.content[:50]}...")
            
        if len(messages) == 0:
            print("WARNING: Pipeline produced 0 messages from the debug image.")
            # Debug: Try direct OCR to see what parser missed
            print("Debugging raw OCR regions...")
            regions = controller.ocr.extract_text_regions(img)
            print(f"Raw OCR found {len(regions)} regions.")
            for r in regions[:5]:
                print(f" - {r.text} (conf={r.confidence})")
                
    except Exception as e:
        print(f"Execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pipeline()
