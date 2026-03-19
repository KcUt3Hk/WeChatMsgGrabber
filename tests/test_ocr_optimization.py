import unittest
from unittest.mock import MagicMock, patch
import os
import sys
from PIL import Image
import numpy as np

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.image_preprocessor import ImagePreprocessor

class TestOCROptimization(unittest.TestCase):
    def setUp(self):
        self.preprocessor = ImagePreprocessor()
        self.test_image = Image.new('RGB', (100, 100), color=(200, 200, 200))

    def test_padding_application(self):
        """Test if padding is correctly applied."""
        padding = 10
        processed = self.preprocessor.preprocess_for_ocr(
            self.test_image,
            enhance_quality=False,
            reduce_noise_flag=False,
            convert_grayscale=False,
            padding=padding
        )
        
        expected_size = (100 + 2*padding, 100 + 2*padding)
        self.assertEqual(processed.size, expected_size)
        
        # Check background color (should be white/255)
        # Top-left pixel should be padding (white)
        self.assertEqual(processed.getpixel((0, 0)), (255, 255, 255))

    @patch('services.image_preprocessor.ImagePreprocessor.calculate_image_quality_score')
    @patch('services.image_preprocessor.ImagePreprocessor.enhance_local_contrast')
    def test_adaptive_enhancement_trigger(self, mock_clahe, mock_score):
        """Test if CLAHE is triggered for low quality images."""
        # Case 1: Low quality score -> Trigger CLAHE
        mock_score.return_value = 0.4
        mock_clahe.return_value = self.test_image # Return same image
        
        self.preprocessor.preprocess_for_ocr(
            self.test_image,
            enhance_quality=True
        )
        
        mock_clahe.assert_called_once()
        
        # Case 2: High quality score -> No CLAHE
        mock_score.return_value = 0.8
        mock_clahe.reset_mock()
        
        self.preprocessor.preprocess_for_ocr(
            self.test_image,
            enhance_quality=True
        )
        
        mock_clahe.assert_not_called()

    def test_grayscale_and_padding_integration(self):
        """Test integration of grayscale conversion and padding."""
        processed = self.preprocessor.preprocess_for_ocr(
            self.test_image,
            enhance_quality=False,
            reduce_noise_flag=False,
            convert_grayscale=True,
            padding=5
        )
        
        self.assertEqual(processed.mode, 'L')
        self.assertEqual(processed.size, (110, 110))
        # Padding for L mode should be 255 (white)
        self.assertEqual(processed.getpixel((0, 0)), 255)

if __name__ == '__main__':
    unittest.main()
