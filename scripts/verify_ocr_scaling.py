import os
import sys
import logging
from PIL import Image, ImageDraw, ImageFont
import unittest.mock
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.ocr_processor import OCRProcessor, OCRConfig

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("VerifyOCRScaling")

def create_large_test_image(width=3000, height=2000):
    """Create a large image with text at specific coordinates."""
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Draw a box at (2000, 1500) size 200x100
    # Text inside
    text = "TEST_SCALING"
    try:
        font = ImageFont.load_default()
        # Scale font if possible or use default
    except:
        font = None
    
    # We'll simulate OCR finding this text.
    # Since we can't easily rely on real OCR to be pixel perfect or installed in this test env without full setup,
    # we might mock the engine.ocr call to return scaled-down coordinates, 
    # and verify that process_image scales them back up.
    
    return img

def test_scaling_logic():
    logger.info("Testing OCR scaling logic...")
    
    # 1. Setup OCRProcessor with a mock engine
    config = OCRConfig()
    config.preprocess_max_side = 1000 # Force downscaling for 2000x2000 image
    processor = OCRProcessor(config)
    
    # Mock the engine
    processor.ocr_engine = MagicMock()
    
    # 2. Create a large image
    original_w, original_h = 2000, 2000
    img = Image.new('RGB', (original_w, original_h), color='white')
    
    # 3. Define what the Mock engine returns.
    # The processor will resize the image to max_side=1000.
    # Scale factor = 2000 / 1000 = 2.0.
    # If the real text is at (1000, 1000) with size 100x100 in ORIGINAL image,
    # it would be at (500, 500) size 50x50 in RESIZED image.
    # The engine runs on RESIZED image, so it returns [[500, 500], [550, 500], [550, 550], [500, 550]] (approx).
    
    # PaddleOCR format: [[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], ("text", conf)]]
    mock_bbox = [[500.0, 500.0], [550.0, 500.0], [550.0, 550.0], [500.0, 550.0]]
    mock_result = [[mock_bbox, ("TEST_TEXT", 0.99)]]
    
    # Configure mock to return this
    processor.ocr_engine.ocr.return_value = [mock_result] # .ocr() returns a list of results (one per image)
    
    # 4. Run process_image
    result = processor.process_image(img, preprocess=True)
    
    # 5. Check results
    if not result.bounding_boxes:
        logger.error("No bounding boxes returned!")
        return
    
    bbox = result.bounding_boxes[0]
    logger.info(f"Returned BBox: x={bbox.x}, y={bbox.y}, w={bbox.width}, h={bbox.height}")
    
    # Expected: x=1000, y=1000, w=100, h=100 (approx)
    # The input to OCR was scaled down by 2.0.
    # So output from OCR (500) should be multiplied by 2.0 -> 1000.
    
    expected_x = 1000
    expected_y = 1000
    tolerance = 2 # Allow small rounding diffs
    
    if abs(bbox.x - expected_x) <= tolerance and abs(bbox.y - expected_y) <= tolerance:
        logger.info("✅ Scaling fix verified! Coordinates restored to original scale.")
    else:
        logger.error(f"❌ Scaling fix FAILED. Expected around {expected_x}, got {bbox.x}")
        # If it returned 500, it means scaling was NOT applied.

if __name__ == "__main__":
    test_scaling_logic()
