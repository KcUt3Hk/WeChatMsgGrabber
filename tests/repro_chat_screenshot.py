import unittest
import numpy as np
from PIL import Image, ImageDraw
from services.image_preprocessor import ImagePreprocessor
from models.data_models import Rectangle

class TestChatScreenshotDetection(unittest.TestCase):
    def setUp(self):
        self.processor = ImagePreprocessor()

    def create_chat_screenshot(self, width=400, height=600):
        # Background: Light Gray
        img = Image.new('RGB', (width, height), (240, 240, 240))
        draw = ImageDraw.Draw(img)
        
        # Draw some bubbles
        # Bubble 1: White (Left)
        draw.rectangle([50, 50, 250, 150], fill=(255, 255, 255))
        draw.text((60, 60), "Hello there!", fill=(0, 0, 0))
        # Avatar 1
        draw.rectangle([10, 50, 40, 80], fill=(100, 100, 100))
        
        # Bubble 2: Green (Right)
        draw.rectangle([150, 200, 350, 300], fill=(149, 236, 105))
        draw.text((160, 210), "Hi! How are you?", fill=(0, 0, 0))
        # Avatar 2
        draw.rectangle([360, 200, 390, 230], fill=(200, 100, 100))

        # Bubble 3: White (Left)
        draw.rectangle([50, 350, 300, 550], fill=(255, 255, 255))
        draw.text((60, 360), "Long message...\n\n\n\nEnd.", fill=(0, 0, 0))
        # Avatar 1
        draw.rectangle([10, 350, 40, 380], fill=(100, 100, 100))
        
        return img

    def test_chat_screenshot_preservation(self):
        # This simulates a screenshot of a chat conversation sent as an image.
        # It SHOULD be detected as an "Image" (Region), and NOT filtered out.
        img = self.create_chat_screenshot()
        
        # The detect_text_regions works on the whole image.
        # If the whole image is passed, it might find sub-regions (the bubbles).
        # But if the input IS the region (e.g. user selected it), we want to know if it passes "is_solid_background".
        
        # Let's test is_solid_background directly on this image
        # Also check color count
        img_small = img.resize((80, 80))
        img_quantized = img_small.quantize(colors=32)
        # Count non-zero histogram bins
        hist = img_quantized.histogram()
        # Histogram has 32 entries (if Palette mode)
        # But PIL histogram for P mode might be just counts of indices 0-31?
        # Let's check
        non_zero_bins = sum(1 for x in hist if x > 0)
        print(f"Non-zero bins (max 32): {non_zero_bins}")
        
        # Calculate top 3 ratios
        total_pixels = img_small.width * img_small.height
        sorted_counts = sorted(hist, reverse=True)
        top_3 = [c / total_pixels for c in sorted_counts[:3]]
        print(f"Top 3 ratios: {top_3}")
        
        is_text_bubble = self.processor.is_text_bubble(img)
        print(f"\nChat Screenshot Text Bubble Check: {is_text_bubble}")
        
        # We expect False (it's complex enough, not just a text bubble)
        self.assertFalse(is_text_bubble, "Chat screenshot should NOT be classified as text bubble")
        
        # Also run detect_text_regions on a larger canvas containing this screenshot
        # to see if it picks it up as a single block or splits it.
        # If it splits it into bubbles, and filters them, that's fine (because they ARE text bubbles).
        # But if the user meant "I sent a screenshot of a chat", they want the WHOLE thing.
        # The algorithm usually splits by connectivity.
        # If the bubbles are far apart, it splits.
        # If the screenshot has a border or is pasted on a background, it might be one region.
        
        # Let's try to see if the whole image passes.
        
if __name__ == '__main__':
    unittest.main()
