import unittest
from PIL import Image, ImageDraw, ImageFont
import sys
import os
import logging
import numpy as np
import cv2

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.image_preprocessor import ImagePreprocessor

class TestMemeVsText(unittest.TestCase):
    def setUp(self):
        self.preprocessor = ImagePreprocessor()
        # Enable debug logging
        logging.basicConfig(level=logging.DEBUG)
        self.preprocessor.logger.setLevel(logging.DEBUG)

    def create_text_bubble(self, lines=3):
        # Create a white image with standard text
        img = Image.new('RGB', (300, 100), color='white')
        d = ImageDraw.Draw(img)
        # Simulate text lines
        for i in range(lines):
            # Draw a sentence
            text = "This is a sample text line for testing " + str(i)
            d.text((10, 10 + i * 20), text, fill='black')
        return img

    def create_panda_meme(self):
        # Create a B&W meme (Panda face style)
        img = Image.new('RGB', (200, 200), color='white')
        d = ImageDraw.Draw(img)
        
        # Draw face outline (circle)
        d.ellipse([10, 10, 190, 190], outline='black', width=3)
        
        # Draw eyes (filled black circles)
        d.ellipse([50, 60, 80, 90], fill='black')
        d.ellipse([120, 60, 150, 90], fill='black')
        
        # Draw nose (small triangle)
        d.polygon([(100, 100), (90, 110), (110, 110)], fill='black')
        
        # Draw mouth (line)
        d.arc([70, 100, 130, 140], 0, 180, fill='black', width=3)
        
        # Add some meme text at bottom (larger, bolder)
        d.text((50, 160), "SO SAD", fill='black')
        
        return img

    def create_chart_image(self):
        # Simple bar chart
        img = Image.new('RGB', (200, 150), color='white')
        d = ImageDraw.Draw(img)
        d.rectangle([20, 100, 40, 140], fill='black')
        d.rectangle([50, 80, 70, 140], fill='black')
        d.rectangle([80, 40, 100, 140], fill='black')
        return img

    def test_distinguish_bubble_from_meme(self):
        print("\n--- Testing Distinction ---")
        
        # Helper to debug
        def check(name, img):
            # Temporarily inject print into the logic or just run it
            is_bubble = self.preprocessor.is_text_bubble(img)
            print(f"{name}: {is_bubble}")
            
            # Manually run structure check logic to see stats
            # (Copy-paste logic for debugging)
            w, h = img.size
            if w * h > 40000:
                scale = 200.0 / max(w, h)
                img_small = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            else:
                img_small = img
            
            if img_small.mode != 'L':
                gray = img_small.convert('L')
            else:
                gray = img_small
            arr = np.array(gray)
            block_size = 11
            binary = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block_size, 2)
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
            
            valid_components = []
            img_area = arr.shape[0] * arr.shape[1]
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area > 5:
                    valid_components.append(stats[i])
            
            if valid_components:
                num_comps = len(valid_components)
                heights = [c[cv2.CC_STAT_HEIGHT] for c in valid_components]
                avg_height = np.mean(heights)
                std_height = np.std(heights)
                cv = std_height / avg_height if avg_height > 0 else 0
                max_area = max([c[cv2.CC_STAT_AREA] for c in valid_components])
                max_area_ratio = max_area / img_area
                print(f"  Stats: Num={num_comps}, CV={cv:.3f}, MaxAreaRatio={max_area_ratio:.3f}")

        check("Text Bubble", self.create_text_bubble())
        check("Panda Meme", self.create_panda_meme())
        check("Chart", self.create_chart_image())

if __name__ == '__main__':
    unittest.main()
