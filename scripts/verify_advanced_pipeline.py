
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.advanced_scroll_controller import AdvancedScrollController
from models.data_models import MessageType, Message

def test_advanced_pipeline():
    print("=== Advanced Pipeline Verification Start ===")
    
    # 1. Load the debug image
    img_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "debug_capture_verify.png")
    if not os.path.exists(img_path):
        print(f"Error: Debug image not found at {img_path}")
        return

    try:
        real_img = Image.open(img_path)
        print(f"Loaded image: {real_img.size}")
    except Exception as e:
        print(f"Failed to load image: {e}")
        return

    # 2. Initialize Controller with mocks
    print("Initializing AdvancedScrollController...")
    
    # Mock pyautogui to prevent actual scrolling/mouse movement
    with patch('services.advanced_scroll_controller.pyautogui') as mock_pyautogui:
        controller = AdvancedScrollController()
        
        # Mock window/scroll related methods
        controller.ensure_window_ready = MagicMock(return_value=True)
        controller._locate_initial_position = MagicMock(return_value=True)
        controller.get_chat_area_bounds = MagicMock(return_value=MagicMock(x=0, y=0, width=real_img.width, height=real_img.height))
        
        # Mock capture to return our real image
        # We need to return a COPY because the controller might modify/close it or it might be used multiple times
        controller.capture_current_view = MagicMock(side_effect=lambda: real_img.copy())
        
        # Mock _execute_progressive_scroll to just "succeed" without moving mouse
        controller._execute_progressive_scroll = MagicMock(return_value=True)
        
        # Mock OCR/Parser (Optional: we can use real ones to test integration, but might be slow)
        # Let's use REAL OCR to verify the text extraction logic I changed!
        # This is critical to verify "region detection vs full OCR" change.
        
        print("Running progressive_scroll (1 loop)...")
        # Run for just 1 scroll to verify parsing
        results = controller.progressive_scroll(max_scrolls=1, stop_at_edges=False)
        
        print(f"Pipeline finished. Captured {len(results)} states.")
        
        total_messages = 0
        for i, state in enumerate(results):
            msgs = state.get("messages", [])
            total_messages += len(msgs)
            print(f"State {i}: Found {len(msgs)} messages.")
            for m in msgs:
                print(f"  - [{m.sender}] {m.content[:30]}... (Type: {m.message_type})")
                if m.message_type == MessageType.IMAGE:
                    print(f"    -> Image Content: {m.content}")

        if total_messages > 0:
            print("SUCCESS: Pipeline extracted messages.")
        else:
            print("WARNING: Pipeline extracted 0 messages. Check OCR/Image quality.")

if __name__ == "__main__":
    test_advanced_pipeline()
