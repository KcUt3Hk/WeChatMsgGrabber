
import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.getcwd())

from services.ocr_processor import OCRProcessor
import logging

def test_init():
    logging.basicConfig(level=logging.INFO)
    print("Starting OCRProcessor init...", flush=True)
    try:
        from paddleocr import PaddleOCR
        # Test if use_mp is accepted
        print("Testing PaddleOCR(use_mp=False)...", flush=True)
        try:
            ocr = PaddleOCR(use_mp=False, lang='ch')
            print("PaddleOCR(use_mp=False) success", flush=True)
        except Exception as e:
            print(f"PaddleOCR(use_mp=False) failed: {e}", flush=True)

        # Test if rec is accepted
        print("Testing PaddleOCR(rec=True)...", flush=True)
        try:
            ocr = PaddleOCR(rec=True, lang='ch')
            print("PaddleOCR(rec=True) success", flush=True)
        except Exception as e:
            print(f"PaddleOCR(rec=True) failed: {e}", flush=True)

        processor = OCRProcessor()
        success = processor.initialize_engine()
        print(f"OCRProcessor init result: {success}", flush=True)
        
        if success:
            # Try a dummy OCR
            print("Trying OCR on dummy image...", flush=True)
            import numpy as np
            from PIL import Image
            img = Image.new('RGB', (100, 100), color='white')
            # processor.process_image expects PIL image
            result = processor.process_image(img, preprocess=False)
            print(f"OCR result: {result}", flush=True)
            
    except Exception as e:
        print(f"OCRProcessor init failed: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_init()
