import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.auto_scroll_controller import AutoScrollController
from services.logging_manager import LoggingManager

def verify_window_detection():
    # Setup simple logging
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger = logging.getLogger("VerifyWindow")
    
    print("=== Window Detection Verification Start ===")
    
    try:
        controller = AutoScrollController()
        print("AutoScrollController initialized.")
        
        print("Attempting to locate WeChat window...")
        
        # Debug Quartz directly
        try:
            import Quartz
            print("Quartz imported successfully.")
            # options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
            # Try ALL windows
            options = Quartz.kCGWindowListExcludeDesktopElements
            window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
            print(f"Quartz found {len(window_list)} windows (including off-screen).")
            for i, w in enumerate(window_list):
                owner = w.get('kCGWindowOwnerName', '')
                name = w.get('kCGWindowName', '')
                bounds = w.get('kCGWindowBounds', {})
                if 'WeChat' in str(owner) or '微信' in str(owner):
                    print(f"MATCH CANDIDATE {i}: Owner='{owner}', Name='{name}', Bounds={bounds}")
                # Print a few others just to be sure
                if i < 5:
                    print(f"Window {i}: Owner='{owner}', Name='{name}'")
        except ImportError:
            print("Quartz import failed in debug script.")
        except Exception as e:
            print(f"Quartz debug error: {e}")

        # Force macOS platform check in case it's needed (though controller does it)
        window = controller.locate_wechat_window()
        
        if window:
            print(f"SUCCESS: WeChat window found!")
            print(f"Title: {window.title}")
            print(f"Position: {window.position}")
            print(f"Is Active: {window.is_active}")
            
            # Optional: Check if we can get bounds specifically
            bounds = controller.get_chat_area_bounds()
            print(f"Calculated Chat Area Bounds: {bounds}")

            # Try to activate the window
            print("Attempting to activate window...")
            if controller.activate_window():
                print("SUCCESS: Window activated.")
            else:
                print("FAILURE: Window activation failed.")
        else:
            print("FAILURE: WeChat window NOT found.")
            print("Please ensure WeChat is running and visible (not minimized/hidden).")
            
    except Exception as e:
        print(f"ERROR: Exception during verification: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_window_detection()
