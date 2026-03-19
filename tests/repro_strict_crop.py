
import unittest
import cv2
import numpy as np
from PIL import Image, ImageDraw
from services.image_preprocessor import ImagePreprocessor
from models.data_models import Rectangle

class TestStrictCrop(unittest.TestCase):
    def setUp(self):
        self.preprocessor = ImagePreprocessor()

    def test_strict_crop_dark_mode(self):
        # Create a dark background image (simulating WeChat dark mode)
        bg_color = (25, 25, 25) # Dark gray
        w, h = 400, 400
        image = Image.new('RGB', (w, h), bg_color)
        draw = ImageDraw.Draw(image)

        # Draw a simulated "sticker" or "image"
        # It should be a distinct rectangle
        sticker_x, sticker_y = 100, 100
        sticker_w, sticker_h = 100, 100
        # Sticker content: some random noise or pattern, but let's make it a solid color for simplicity first, 
        # or a pattern to ensure edges are detected.
        # Let's draw a red square with a blue circle inside
        draw.rectangle([sticker_x, sticker_y, sticker_x + sticker_w, sticker_y + sticker_h], fill=(200, 0, 0))
        draw.ellipse([sticker_x + 10, sticker_y + 10, sticker_x + 90, sticker_y + 90], fill=(0, 0, 200))

        # Run detection
        regions = self.preprocessor.detect_text_regions(image)
        
        # We expect one main region corresponding to the sticker
        # Find the region that overlaps with our sticker
        sticker_rect = Rectangle(sticker_x, sticker_y, sticker_w, sticker_h)
        
        found_rect = None
        for r in regions:
            # Check overlap
            if (r.x < sticker_x + sticker_w and r.x + r.width > sticker_x and
                r.y < sticker_y + sticker_h and r.y + r.height > sticker_y):
                found_rect = r
                break
        
        self.assertIsNotNone(found_rect, "Should detect the sticker")
        
        # Check tightness
        # The detected region should be close to 100x100
        # Allow some small margin due to morphology (e.g. +10px)
        print(f"Original: {sticker_rect}")
        print(f"Detected: {found_rect}")
        
        # Calculate margin
        margin_x = abs(found_rect.width - sticker_w)
        margin_y = abs(found_rect.height - sticker_h)
        
        print(f"Margin X: {margin_x}, Margin Y: {margin_y}")
        
        # User wants "Minimum bounding box" and "No extra chat background"
        # Let's say tolerance is 10 pixels total (5px each side)
        self.assertLess(margin_x, 15, "Crop width is too loose")
        self.assertLess(margin_y, 15, "Crop height is too loose")

    def test_trim_logic(self):
        # Create an image with a solid background and a centered object
        bg_color = (30, 30, 30)
        w, h = 100, 100
        img = Image.new('RGB', (w, h), bg_color)
        draw = ImageDraw.Draw(img)
        
        # Object in center, 50x50, at 25,25
        obj_x, obj_y, obj_w, obj_h = 25, 25, 50, 50
        draw.rectangle([obj_x, obj_y, obj_x + obj_w - 1, obj_y + obj_h - 1], fill=(200, 200, 200))
        
        # Use actual implementation with padding=10
        padding = 10
        refined_rect = self.preprocessor.refine_crop(img, padding=padding)
        
        print(f"Refined with padding={padding}: {refined_rect}")
        
        # Expected values
        expected_x = max(0, obj_x - padding)
        expected_y = max(0, obj_y - padding)
        expected_w = min(w - expected_x, obj_w + 2 * padding)
        expected_h = min(h - expected_y, obj_h + 2 * padding)
        
        self.assertEqual(refined_rect.x, expected_x)
        self.assertEqual(refined_rect.y, expected_y)
        self.assertEqual(refined_rect.width, expected_w)
        self.assertEqual(refined_rect.height, expected_h)

if __name__ == "__main__":
    unittest.main()
