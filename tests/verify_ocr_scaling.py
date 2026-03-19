import unittest
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.ocr_processor import OCRProcessor
from models.config import OCRConfig

class TestOCRScaling(unittest.TestCase):
    def setUp(self):
        self.config = OCRConfig()
        # Force downsampling
        self.config.preprocess_max_side = 500
        self.ocr = OCRProcessor(config=self.config)
        
        # Mock engine to avoid actual OCR loading and return predictable results
        self.ocr.ocr_engine = MagicMock()
        
    def test_coordinate_scaling(self):
        # 1. Create a large image (1000x1000)
        # Text at (800, 800) size 100x50
        original_width = 1000
        original_height = 1000
        image = Image.new('RGB', (original_width, original_height), color='white')
        
        # 2. Mock OCR engine result
        # Since max_side is 500, the image will be resized to 500x500 (scale=0.5)
        # The text at 800,800 in original should be at 400,400 in resized image
        # So the mock engine should receive a 500x500 image and return coordinates around 400
        
        # We mock the return value of ocr_engine.ocr()
        # Format: [[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], ("text", conf)]]
        # Box at 400,400 width 50 height 25 (scaled down from 100x50)
        mock_bbox = [
            [400, 400], [450, 400], [450, 425], [400, 425]
        ]
        mock_result = [[mock_bbox, ("test_text", 0.99)]]
        
        # Mock the ocr method
        self.ocr.ocr_engine.ocr.return_value = [mock_result]
        # Also mock predict just in case
        self.ocr.ocr_engine.predict = MagicMock(return_value=mock_result)

        # 3. Run process_image
        # process_image should:
        # a) Resize 1000x1000 -> 500x500 (scale factor 0.5)
        # b) Call engine with 500x500 image
        # c) Receive bbox at 400,400
        # d) Scale bbox back by 1/0.5 = 2.0 -> 800,800
        
        result = self.ocr.process_image(image, preprocess=True)
        
        # 4. Verify results
        self.assertTrue(len(result.bounding_boxes) > 0, "Should detect at least one region")
        bbox = result.bounding_boxes[0]
        
        print(f"Original Image Size: {original_width}x{original_height}")
        print(f"Config Max Side: {self.config.preprocess_max_side}")
        print(f"Result BBox: x={bbox.x}, y={bbox.y}, w={bbox.width}, h={bbox.height}")
        
        # Check coordinates (allow small rounding error)
        # Expected x around 800
        self.assertTrue(790 <= bbox.x <= 810, f"X coordinate {bbox.x} should be around 800")
        self.assertTrue(790 <= bbox.y <= 810, f"Y coordinate {bbox.y} should be around 800")
        # Expected width around 100 (50 * 2)
        self.assertTrue(90 <= bbox.width <= 110, f"Width {bbox.width} should be around 100")
        
if __name__ == '__main__':
    unittest.main()
