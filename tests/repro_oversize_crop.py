
import unittest
import numpy as np
import cv2
from PIL import Image, ImageDraw
from services.image_preprocessor import ImagePreprocessor, Rectangle

class TestOversizeCrop(unittest.TestCase):
    def setUp(self):
        self.preprocessor = ImagePreprocessor()

    def test_noise_prevents_split(self):
        """
        Test that a single noise pixel in the gap prevents splitting if threshold is too strict.
        And verify that increasing threshold fixes it.
        """
        # Create a large blank image (simulate chat background)
        w, h = 400, 600
        image = Image.new('RGB', (w, h), (30, 30, 30)) # Dark mode background
        draw = ImageDraw.Draw(image)
        
        # Draw two message bubbles (rectangles)
        # Top bubble
        draw.rectangle([50, 50, 350, 200], fill=(200, 200, 200))
        # Bottom bubble
        draw.rectangle([50, 250, 350, 400], fill=(200, 200, 200))
        
        # This leaves a gap from y=200 to y=250 (50px).
        
        # Add a "noise" line or dots in the gap
        # Canny might pick this up.
        # Let's manually inject noise into the Canny edges by drawing a thin line in the image
        # that is just barely visible/contrast enough to be an edge but not real content.
        # Or simpler: we can just mock the behavior by knowing how Canny works.
        # But for an integration test, let's draw a faint line.
        draw.line([100, 225, 300, 225], fill=(35, 35, 35), width=1)
        
        # Convert to edges manually to see what happens, or just run detect_text_regions
        # We suspect detect_text_regions will merge them due to dilation, 
        # and then check_and_split_region will fail to split due to the line.
        
        regions = self.preprocessor.detect_text_regions(image, min_area=100)
        
        print(f"Detected {len(regions)} regions")
        for r in regions:
            print(f"Region: {r.x}, {r.y}, {r.width}, {r.height}")
            
        # We expect 2 regions. If we get 1 giant region covering ~50 to ~400, it failed.
        
        # Check if any region covers both (height > 300)
        merged_region = next((r for r in regions if r.height > 300), None)
        
        if merged_region:
            print("FAILURE: Regions were merged and not split.")
        else:
            print("SUCCESS: Regions were correctly identified as separate.")
            
        self.assertIsNone(merged_region, "Should not have merged regions")

if __name__ == '__main__':
    unittest.main()
