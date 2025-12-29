import unittest
import numpy as np
from PIL import Image, ImageDraw
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.image_preprocessor import ImagePreprocessor
from models.data_models import Rectangle

class TestSmartROI(unittest.TestCase):
    def setUp(self):
        self.preprocessor = ImagePreprocessor()

    def test_smart_roi_detection(self):
        """Test detection of chat area with clear boundaries"""
        w, h = 1000, 800
        img = Image.new('RGB', (w, h), color='#F5F5F5')
        draw = ImageDraw.Draw(img)
        
        # 1. Sidebar (Left 250px)
        draw.rectangle([0, 0, 250, h], fill='#EBEBEB')
        draw.line([250, 0, 250, h], fill='#D6D6D6', width=2)
        
        # 2. Header (Top 60px)
        draw.rectangle([250, 0, w, 60], fill='#F5F5F5')
        # Use a darker color for the line to ensure edge detection picks it up in test environment
        draw.line([250, 60, w, 60], fill='#808080', width=2)
        
        # 3. Input Box (Bottom 150px)
        input_y = h - 150
        draw.rectangle([250, input_y, w, h], fill='#F5F5F5')
        draw.line([250, input_y, w, input_y], fill='#808080', width=2)
        
        # Expected ROI: x=250, y=60, w=750, h=590
        # (With padding adjustment in code: x+2, y+2, w-padding, h-padding)
        # Let's allow for some tolerance
        
        roi = self.preprocessor.detect_chat_area_smart(img)
        
        # Expected X start ~ 250
        self.assertAlmostEqual(roi.x, 250, delta=10)
        # Expected Y start ~ 60
        self.assertAlmostEqual(roi.y, 60, delta=10)
        # Expected Y end ~ 650 (800 - 150) -> Height ~ 590
        self.assertAlmostEqual(roi.height, 590, delta=10)
        
    def test_dark_mode(self):
        """Test detection in dark mode colors"""
        w, h = 1000, 800
        # Dark background
        img = Image.new('RGB', (w, h), color='#191919')
        draw = ImageDraw.Draw(img)
        
        # Structure (Dark Sidebar)
        draw.rectangle([0, 0, 250, h], fill='#111111')
        # Dark divider
        draw.line([250, 0, 250, h], fill='#000000', width=2)
        
        # Header (Dark)
        draw.rectangle([250, 0, w, 60], fill='#1F1F1F')
        # Dark header divider
        draw.line([250, 60, w, 60], fill='#333333', width=2)
        
        # Input Box (Dark)
        input_y = h - 150
        draw.rectangle([250, input_y, w, h], fill='#1F1F1F')
        # Dark input divider
        draw.line([250, input_y, w, input_y], fill='#333333', width=2)
        
        roi = self.preprocessor.detect_chat_area_smart(img)
        
        self.assertAlmostEqual(roi.x, 250, delta=10)
        self.assertAlmostEqual(roi.y, 60, delta=10)
        self.assertAlmostEqual(roi.height, 590, delta=10)

    def test_low_contrast_separators(self):
        """Test detection when separators have low contrast against background."""
        w, h = 1100, 900
        img = Image.new('RGB', (w, h), color='#F2F2F2')
        draw = ImageDraw.Draw(img)

        draw.rectangle([0, 0, 280, h], fill='#ECECEC')
        draw.line([280, 0, 280, h], fill='#E0E0E0', width=2)

        draw.rectangle([280, 0, w, 70], fill='#F2F2F2')
        draw.line([280, 70, w, 70], fill='#E0E0E0', width=2)

        input_y = h - 170
        draw.rectangle([280, input_y, w, h], fill='#F2F2F2')
        draw.line([280, input_y, w, input_y], fill='#E0E0E0', width=2)

        roi = self.preprocessor.detect_chat_area_smart(img)
        self.assertAlmostEqual(roi.x, 280, delta=12)
        self.assertAlmostEqual(roi.y, 70, delta=12)
        self.assertAlmostEqual(roi.height, h - 170 - 70, delta=15)

    def test_dashed_separators(self):
        """Test detection when separators are dashed/broken lines."""
        w, h = 1000, 800
        img = Image.new('RGB', (w, h), color='#F5F5F5')
        draw = ImageDraw.Draw(img)

        draw.rectangle([0, 0, 250, h], fill='#EBEBEB')
        for y in range(0, h, 12):
            draw.line([250, y, 250, min(h, y + 6)], fill='#909090', width=2)

        draw.rectangle([250, 0, w, 60], fill='#F5F5F5')
        for x in range(250, w, 20):
            draw.line([x, 60, min(w, x + 10), 60], fill='#909090', width=2)

        input_y = h - 150
        draw.rectangle([250, input_y, w, h], fill='#F5F5F5')
        for x in range(250, w, 20):
            draw.line([x, input_y, min(w, x + 10), input_y], fill='#909090', width=2)

        roi = self.preprocessor.detect_chat_area_smart(img)
        self.assertAlmostEqual(roi.x, 250, delta=12)
        self.assertAlmostEqual(roi.y, 60, delta=12)
        self.assertAlmostEqual(roi.height, 590, delta=15)

    def test_detect_content_roi_prefers_chat_area(self):
        """Test detect_content_roi prioritizes chat layout ROI over generic edges."""
        w, h = 1000, 800
        img = Image.new('RGB', (w, h), color='#F5F5F5')
        draw = ImageDraw.Draw(img)

        draw.rectangle([0, 0, 250, h], fill='#EBEBEB')
        draw.line([250, 0, 250, h], fill='#C8C8C8', width=2)
        draw.rectangle([250, 0, w, 60], fill='#F5F5F5')
        draw.line([250, 60, w, 60], fill='#C8C8C8', width=2)
        input_y = h - 150
        draw.rectangle([250, input_y, w, h], fill='#F5F5F5')
        draw.line([250, input_y, w, input_y], fill='#C8C8C8', width=2)

        roi = self.preprocessor.detect_content_roi(img, padding=0)
        self.assertAlmostEqual(roi.x, 250, delta=12)
        self.assertAlmostEqual(roi.y, 60, delta=12)
        self.assertAlmostEqual(roi.height, 590, delta=15)

if __name__ == '__main__':
    unittest.main()
