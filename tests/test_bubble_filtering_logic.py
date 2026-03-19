
import unittest
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from services.image_preprocessor import ImagePreprocessor

class TestBubbleFiltering(unittest.TestCase):
    def setUp(self):
        self.processor = ImagePreprocessor()
        
    def create_text_bubble(self, text="Hello", bg_color=(152, 225, 101), text_color=(0, 0, 0)):
        # Create a solid background image
        w, h = 200, 100
        img = Image.new('RGB', (w, h), (245, 245, 245)) # Chat background
        draw = ImageDraw.Draw(img)
        
        # Draw bubble
        bubble_rect = [20, 20, 180, 80]
        draw.rectangle(bubble_rect, fill=bg_color)
        
        # Draw text
        try:
            # Try to use a default font
            font = ImageFont.load_default()
        except:
            font = None
            
        if font:
            draw.text((30, 30), text, fill=text_color, font=font)
        
        return img

    def test_filter_enabled(self):
        # Green bubble (text only)
        img = self.create_text_bubble()
        
        # Should be filtered out by default (True)
        regions = self.processor.detect_text_regions(img, filter_text_bubbles=True)
        
        # Since the image is simple, Adaptive/Canny might detect the bubble outline.
        # But our filter should remove it if it looks like a text bubble.
        # Note: detect_text_regions returns regions. If filtered, it should return fewer or none.
        # Wait, if it detects the *text* inside the bubble, that's fine.
        # But if it detects the *bubble itself* as a "Media Region", that's what we want to filter.
        
        # Let's verify that the *whole bubble* is not returned as a region.
        # The filter checks the *cropped region*.
        
        # For this test, we assume detect_text_regions without filter would find the bubble.
        regions_unfiltered = self.processor.detect_text_regions(img, filter_text_bubbles=False)
        regions_filtered = self.processor.detect_text_regions(img, filter_text_bubbles=True)
        
        print(f"Unfiltered count: {len(regions_unfiltered)}")
        print(f"Filtered count: {len(regions_filtered)}")
        
        # We expect filtered to have fewer regions OR be empty if the only thing was the bubble
        self.assertLess(len(regions_filtered), len(regions_unfiltered) + 1)
        
        # Specifically, check if the large bubble region is present
        # Calculate max area
        max_area_filtered = 0
        if regions_filtered:
            max_area_filtered = max([r.width * r.height for r in regions_filtered])
            
        max_area_unfiltered = 0
        if regions_unfiltered:
            max_area_unfiltered = max([r.width * r.height for r in regions_unfiltered])
            
        print(f"Max Area Filtered: {max_area_filtered}, Unfiltered: {max_area_unfiltered}")
        
        # If the bubble was detected as a region in unfiltered, it should be gone or smaller in filtered
        if max_area_unfiltered > 2000: # 200x100 image, bubble is ~160x60=9600
             self.assertTrue(max_area_filtered < max_area_unfiltered or max_area_filtered == 0)

    def test_filter_disabled(self):
        # Green bubble
        img = self.create_text_bubble()
        
        # With filter=False, we should see regions
        regions = self.processor.detect_text_regions(img, filter_text_bubbles=False)
        self.assertTrue(len(regions) > 0)

if __name__ == '__main__':
    unittest.main()
