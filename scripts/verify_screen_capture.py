import sys
import os
import logging
from PIL import Image
import numpy as np

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.auto_scroll_controller import AutoScrollController
from models.data_models import Rectangle

def verify_capture():
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("VerifyCapture")
    
    print("=== Screen Capture Verification Start ===")
    
    try:
        controller = AutoScrollController()
        
        # Use the coordinates from the user's log
        # (278, 100, 722, 1011) -> x, y, w, h
        # Note: log said (278, 100, 722, 1011). Is 722 width or x2?
        # The log says: Chat area override set to (278, 100, 722, 1011)
        # In auto_scroll_controller.py: set_override_chat_area((x, y, w, h))
        # So it is x=278, y=100, w=722, h=1011.
        
        override_rect = Rectangle(x=278, y=100, width=722, height=1011)
        controller.set_override_chat_area(override_rect)
        print(f"Set override chat area: {override_rect}")
        
        print("Capturing screenshot...")
        img = controller.capture_current_view()
        
        if img:
            print(f"Capture successful. Size: {img.size}, Mode: {img.mode}")
            
            output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
            os.makedirs(output_dir, exist_ok=True)
            save_path = os.path.join(output_dir, "debug_capture_verify.png")
            img.save(save_path)
            print(f"Saved capture to: {save_path}")
            
            # Check content statistics
            arr = np.array(img)
            mean_val = np.mean(arr)
            std_val = np.std(arr)
            min_val = np.min(arr)
            max_val = np.max(arr)
            
            print(f"Image Stats - Mean: {mean_val:.2f}, Std: {std_val:.2f}, Min: {min_val}, Max: {max_val}")
            
            if std_val < 5:
                print("WARNING: Image seems to be solid color (blank/white/black)!")
            else:
                print("Image content seems valid (has variation).")
                
        else:
            print("Capture failed (returned None).")
            
    except Exception as e:
        print(f"Exception during capture: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_capture()
