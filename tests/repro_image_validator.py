
import sys
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.image_validator import ImageValidator

def test_dark_image_validation():
    validator = ImageValidator()
    
    # Case 1: Solid Dark Bubble (Should be INVALID)
    img_solid = Image.new('RGB', (200, 200), color=(20, 20, 20))
    
    print("--- Case 1: Solid Dark Bubble ---")
    is_valid_solid = validator.is_valid_image_content(img_solid)
    print(f"is_valid_image_content: {is_valid_solid}")
    
    # Case 2: Dark Bubble with Content (Should be VALID)
    img_content = Image.new('RGB', (200, 200), color=(20, 20, 20))
    draw = ImageDraw.Draw(img_content)
    draw.ellipse((50, 50, 150, 150), fill=(200, 200, 200), outline=None)
    
    print("\n--- Case 2: Dark Bubble with Content ---")
    is_valid_content = validator.is_valid_image_content(img_content)
    print(f"is_valid_image_content: {is_valid_content}")
    
    # Case 3: Very Dark Photo (Low Contrast) (Should be VALID)
    img_dark_photo = Image.new('RGB', (200, 200), color=(30, 30, 30))
    draw = ImageDraw.Draw(img_dark_photo)
    for i in range(0, 200, 10):
        draw.line((i, 0, i, 200), fill=(40, 40, 40), width=1)
        draw.line((0, i, 200, i), fill=(40, 40, 40), width=1)
        
    print("\n--- Case 3: Very Dark Photo (Low Contrast) ---")
    
    # Debug metrics
    arr = np.array(img_dark_photo)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    std = float(np.std(gray))
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    entropy = -np.sum((hist/hist.sum()) * np.log2((hist/hist.sum()) + 1e-7))
    print(f"Std Dev (Original): {std:.4f}")
    
    # Resize to 64x64 like ImageValidator
    img_cv = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    small = cv2.resize(img_cv, (64, 64), interpolation=cv2.INTER_AREA)
    gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    std_small = float(np.std(gray_small))
    print(f"Std Dev (64x64): {std_small:.4f}")
    
    print(f"Entropy: {entropy:.4f}")
    
    is_valid_photo = validator.is_valid_image_content(img_dark_photo)
    print(f"is_valid_image_content: {is_valid_photo}")

if __name__ == "__main__":
    test_dark_image_validation()
