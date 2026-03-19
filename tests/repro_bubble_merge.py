import unittest
import numpy as np
from PIL import Image, ImageDraw
from services.image_preprocessor import ImagePreprocessor
from models.data_models import Rectangle

class TestBubbleMerge(unittest.TestCase):
    def setUp(self):
        self.preprocessor = ImagePreprocessor()

    def test_bubble_merge(self):
        # Create a dark background image
        bg_color = (25, 25, 25)
        w, h = 400, 400
        image = Image.new('RGB', (w, h), bg_color)
        draw = ImageDraw.Draw(image)

        # 1. Draw a Sticker (Red Square)
        sticker_x, sticker_y = 100, 100
        sticker_w, sticker_h = 100, 100
        draw.rectangle([sticker_x, sticker_y, sticker_x + sticker_w, sticker_y + sticker_h], fill=(200, 0, 0))

        # 2. Draw a Green Bubble very close below it (5px gap)
        # Green Bubble color: #95EC69 -> (149, 236, 105)
        bubble_x, bubble_y = 100, sticker_y + sticker_h + 5
        bubble_w, bubble_h = 200, 60
        draw.rectangle([bubble_x, bubble_y, bubble_x + bubble_w, bubble_y + bubble_h], fill=(149, 236, 105))
        
        # Add text inside bubble (black text)
        draw.text((bubble_x + 10, bubble_y + 10), "This is a message", fill=(0, 0, 0))

        # Run detection
        regions = self.preprocessor.detect_text_regions(image)
        
        print(f"Detected {len(regions)} regions")
        for i, r in enumerate(regions):
            print(f"Region {i}: {r}")

        # Analysis
        # If they are merged, we will see 1 large region covering both
        # y_min approx 100, y_max approx 100 + 100 + 5 + 60 = 265
        
        merged_region = None
        sticker_only = None
        bubble_only = None
        
        for r in regions:
            # Check if it covers both sticker top and bubble bottom
            if r.y <= sticker_y + 10 and r.y + r.height >= bubble_y + bubble_h - 10:
                merged_region = r
            # Check if it covers only sticker
            elif r.y <= sticker_y + 10 and r.y + r.height <= sticker_y + sticker_h + 10:
                sticker_only = r
            # Check if it covers only bubble
            elif r.y >= bubble_y - 10 and r.y + r.height >= bubble_y + bubble_h - 10:
                bubble_only = r
                
        if merged_region:
            print(f"MERGED DETECTED: {merged_region}")
        if sticker_only:
            print(f"STICKER DETECTED: {sticker_only}")
        if bubble_only:
            print(f"BUBBLE DETECTED: {bubble_only}")
            
        # We WANT separate regions
        self.assertIsNone(merged_region, "Sticker and Bubble should NOT be merged")
        self.assertIsNotNone(sticker_only, "Sticker should be detected separately")
        self.assertIsNotNone(bubble_only, "Bubble should be detected separately")

if __name__ == "__main__":
    unittest.main()
