
import sys
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ocr_processor import OCRProcessor
from services.image_preprocessor import ImagePreprocessor
from models.data_models import Rectangle

def test_dark_bubble_detection():
    # Initialize processor (mock config if needed, but defaults are fine)
    processor = OCRProcessor()
    
    # Mock typical text metrics (width, height, area)
    typical = (100.0, 40.0, 4000.0)
    img_size = (1000, 2000)
    
    # Case 1: Solid Dark Bubble (Should be REJECTED)
    # 200x200 black square
    img_solid = Image.new('RGB', (200, 200), color=(20, 20, 20))
    rect_solid = Rectangle(0, 0, 200, 200)
    
    print("--- Case 1: Solid Dark Bubble ---")
    is_solid = processor.preprocessor.is_solid_background(img_solid, threshold=0.85)
    print(f"is_solid_background(0.85): {is_solid}")
    result_solid = processor._is_likely_media_bubble(rect_solid, img_size, typical, img_solid)
    print(f"is_likely_media_bubble: {result_solid}")
    
    # Case 2: Dark Bubble with some content (Should be ACCEPTED)
    # 200x200 dark square with a white circle (simulating an icon/image)
    img_content = Image.new('RGB', (200, 200), color=(20, 20, 20))
    draw = ImageDraw.Draw(img_content)
    draw.ellipse((50, 50, 150, 150), fill=(200, 200, 200), outline=None)
    rect_content = Rectangle(0, 0, 200, 200)
    
    print("\n--- Case 2: Dark Bubble with Content ---")
    is_solid_c = processor.preprocessor.is_solid_background(img_content, threshold=0.85)
    print(f"is_solid_background(0.85): {is_solid_c}")
    
    # Check edge density manually to see what's happening
    arr = np.array(img_content)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    density = float(np.count_nonzero(edges)) / float(edges.size)
    print(f"Edge density: {density:.4f}")
    
    result_content = processor._is_likely_media_bubble(rect_content, img_size, typical, img_content)
    print(f"is_likely_media_bubble: {result_content}")

    # Case 3: Very Dark Photo (Low contrast but high detail)
    # 200x200 dark gray with slightly lighter lines
    img_dark_photo = Image.new('RGB', (200, 200), color=(30, 30, 30))
    draw = ImageDraw.Draw(img_dark_photo)
    for i in range(0, 200, 10):
        draw.line((i, 0, i, 200), fill=(40, 40, 40), width=1)
        draw.line((0, i, 200, i), fill=(40, 40, 40), width=1)
    rect_photo = Rectangle(0, 0, 200, 200)
    
    print("\n--- Case 3: Very Dark Photo (Low Contrast) ---")
    is_solid_p = processor.preprocessor.is_solid_background(img_dark_photo, threshold=0.85)
    print(f"is_solid_background(0.85): {is_solid_p}")
    
    arr_p = np.array(img_dark_photo)
    gray_p = cv2.cvtColor(arr_p, cv2.COLOR_RGB2GRAY)
    edges_p = cv2.Canny(gray_p, 50, 150)
    density_p = float(np.count_nonzero(edges_p)) / float(edges_p.size)
    print(f"Edge density: {density_p:.4f}")
    
    result_photo = processor._is_likely_media_bubble(rect_photo, img_size, typical, img_dark_photo)
    print(f"is_likely_media_bubble: {result_photo}")

    print("\n--- Case 3: Very Dark Photo (Low Contrast) - Lower Canny ---")
    edges_p_low = cv2.Canny(gray_p, 30, 100)
    density_p_low = float(np.count_nonzero(edges_p_low)) / float(edges_p_low.size)
    std_p = float(np.std(gray_p))
    print(f"Edge density (30, 100): {density_p_low:.4f}")
    print(f"Std Dev: {std_p:.4f}")

    # Case 4: Dark Photo with Garbage Text (Simulate Reclassification Check)
    print("\n--- Case 4: Dark Photo with Garbage Text (Simulate Reclassification Check) ---")
    # Simulate OCRProcessor logic:
    # 1. Clean text is short/garbage (e.g. "...")
    # 2. should_reclassify = True
    # 3. Check is_solid_background(threshold=0.95) + std dev < 3.0
    
    is_solid = processor.preprocessor.is_solid_background(img_dark_photo, threshold=0.95)
    print(f"is_solid_background(0.95): {is_solid}")
    
    arr = np.array(img_dark_photo.convert('L'))
    std = float(np.std(arr))
    print(f"Std Dev: {std:.4f}")
    
    should_reclassify = True
    if is_solid:
        if std < 3.0:
            should_reclassify = False
            
    if should_reclassify:
        print("Result: Reclassification ALLOWED (Fixed!)")
    else:
        print("Result: Reclassification PREVENTED (Still broken)")

if __name__ == "__main__":
    test_dark_bubble_detection()
