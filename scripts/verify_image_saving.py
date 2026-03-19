
import sys
import os
import unittest
from unittest.mock import MagicMock
from PIL import Image
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.advanced_scroll_controller import AdvancedScrollController
from models.data_models import MessageType

class MockMessage:
    def __init__(self, msg_id, rect, msg_type=MessageType.IMAGE):
        self.id = msg_id
        self.rect = rect
        self.type = msg_type
        self.content = ""

class MockRect:
    def __init__(self, x, y, w, h):
        self.x = x
        self.y = y
        self.width = w
        self.height = h

class TestImageSaving(unittest.TestCase):
    def setUp(self):
        self.controller = AdvancedScrollController()
        # Mock logger to avoid clutter
        self.controller.logger = MagicMock()
        
        # Setup output directory
        self.output_dir = os.path.join(os.getcwd(), "output", "images")
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def test_save_image_filtering(self):
        # Create a mock screenshot (1000x1000 white)
        screenshot = Image.new('RGB', (1000, 1000), color='white')
        
        # Case 1: Valid Image (100x100)
        msg_valid = MockMessage("valid_img_001", MockRect(100, 100, 100, 100))
        
        # Case 2: Invalid Image (40x40) - Should be filtered out
        msg_small = MockMessage("small_img_002", MockRect(300, 300, 40, 40))
        
        # Case 3: Edge Case (51x51) - Should be saved
        msg_edge = MockMessage("edge_img_003", MockRect(500, 500, 51, 51))
        
        messages = [msg_valid, msg_small, msg_edge]
        
        print("Testing _save_image_messages with mixed valid/invalid sizes...")
        self.controller._save_image_messages(messages, screenshot)
        
        # Verify files
        valid_path = os.path.join(self.output_dir, "valid_img_001.png")
        small_path = os.path.join(self.output_dir, "small_img_002.png")
        edge_path = os.path.join(self.output_dir, "edge_img_003.png")
        
        self.assertTrue(os.path.exists(valid_path), "Valid image (100x100) should be saved")
        self.assertFalse(os.path.exists(small_path), "Small image (40x40) should NOT be saved")
        self.assertTrue(os.path.exists(edge_path), "Edge case image (51x51) should be saved")
        
        # Verify content update
        self.assertEqual(msg_valid.content, valid_path, "Message content should update to file path")
        self.assertNotEqual(msg_small.content, small_path, "Small message content should NOT update")
        
        print("Verification Passed: 50x50 filter logic works correctly.")

if __name__ == "__main__":
    unittest.main()
