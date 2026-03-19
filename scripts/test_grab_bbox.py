import sys
from PIL import Image, ImageGrab

def test_bbox():
    print("Testing ImageGrab bbox...")
    
    # 1. Grab full screen to get size
    full = ImageGrab.grab()
    w, h = full.size
    print(f"Full screen size: {w}x{h}")
    
    # 2. Grab a central region using bbox
    box = (w//4, h//4, w//2 + w//4, h//2 + h//4)
    print(f"Requesting bbox: {box}")
    
    try:
        region = ImageGrab.grab(bbox=box)
        print(f"Region size: {region.size}")
        
        # Verify size matches
        expected_w = box[2] - box[0]
        expected_h = box[3] - box[1]
        if region.size == (expected_w, expected_h):
            print("SUCCESS: Region size matches expected.")
        else:
            print(f"FAILURE: Region size mismatch! Expected {expected_w}x{expected_h}")
            
        # 3. Compare content (approx)
        # crop from full
        cropped = full.crop(box)
        # We can't easily compare pixels as screen changes, but sizes should match
        print(f"Cropped from full size: {cropped.size}")
        
    except Exception as e:
        print(f"Bbox grab failed: {e}")

if __name__ == "__main__":
    test_bbox()
