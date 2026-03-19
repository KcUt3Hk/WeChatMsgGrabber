import unittest
import numpy as np
import cv2
from PIL import Image
from services.image_validator import ImageValidator

class TestChatUIDetection(unittest.TestCase):
    def test_dark_mode_ui_detection(self):
        """Test detection of WeChat dark mode UI characteristics."""
        # Create an image that simulates a chat screenshot (RGB)
        # Background: (25, 25, 25) - Standard WeChat Dark Mode BG
        width, height = 300, 500
        img_np = np.full((height, width, 3), (25, 25, 25), dtype=np.uint8)
        
        # Add some bubbles (Grey) - (44, 44, 44)
        cv2.rectangle(img_np, (20, 50), (200, 100), (44, 44, 44), -1)
        cv2.rectangle(img_np, (20, 120), (250, 180), (44, 44, 44), -1)
        
        # Add a green bubble (Self) - (149, 236, 105)
        # Note: PIL uses RGB.
        cv2.rectangle(img_np, (100, 200), (280, 250), (149, 236, 105), -1)
        
        # Add some white text
        cv2.putText(img_np, "Hello", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        img = Image.fromarray(img_np)
        
        # The current ImageValidator might reject this due to low entropy/color count.
        # But we want to ensure it is SPECIFICALLY rejected as a UI screenshot if possible,
        # or at least rejected.
        
        is_valid = ImageValidator.is_valid_image_content(img)
        self.assertFalse(is_valid, "Chat UI screenshot should be rejected")

    def test_light_mode_ui_detection(self):
        """Test detection of WeChat light mode UI characteristics."""
        width, height = 300, 500
        # Light BG #F5F5F5 (245, 245, 245)
        img_np = np.full((height, width, 3), (245, 245, 245), dtype=np.uint8)
        
        # Add White Bubbles #FFFFFF
        cv2.rectangle(img_np, (20, 50), (200, 100), (255, 255, 255), -1)
        cv2.rectangle(img_np, (20, 120), (250, 180), (255, 255, 255), -1)
        
        # Add Green Bubble (Self)
        cv2.rectangle(img_np, (100, 200), (280, 250), (149, 236, 105), -1)
        
        # Add Black Text
        cv2.putText(img_np, "Hello", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        
        img = Image.fromarray(img_np)
        
        is_valid = ImageValidator.is_valid_image_content(img)
        self.assertFalse(is_valid, "Light Mode Chat UI screenshot should be rejected")

    def test_real_photo_with_dark_colors(self):
        """Test that a real photo with dark colors is NOT rejected."""
        # Create a gradient image (dark but varied)
        img_np = np.zeros((100, 100, 3), dtype=np.uint8)
        for i in range(100):
            for j in range(100):
                # Varied dark colors
                img_np[i, j] = [20 + i//5, 20 + j//5, 30] 
        
        img = Image.fromarray(img_np)
        
        # This has low variance potentially, let's make it noisier
        noise = np.random.randint(0, 50, (100, 100, 3), dtype=np.uint8)
        img_np = cv2.add(img_np, noise)
        img = Image.fromarray(img_np)

        # Should be accepted (high entropy, not UI palette dominant)
        is_valid = ImageValidator.is_valid_image_content(img)
        self.assertTrue(is_valid, "Dark photo should be accepted")

if __name__ == '__main__':
    unittest.main()
