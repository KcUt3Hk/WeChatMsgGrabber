import Quartz
import Cocoa

def list_windows():
    # Get all windows (including those off-screen or from other apps)
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    
    print(f"Found {len(window_list)} windows.")
    
    wechat_windows = []
    
    for window in window_list:
        owner = window.get('kCGWindowOwnerName', '')
        name = window.get('kCGWindowName', '')
        bounds = window.get('kCGWindowBounds', {})
        
        # Filter for WeChat
        if 'WeChat' in owner or '微信' in owner:
            print(f"FOUND WECHAT WINDOW: Owner={owner}, Name={name}, Bounds={bounds}")
            wechat_windows.append(window)
        elif 'WeChat' in str(name) or '微信' in str(name):
             print(f"POSSIBLE MATCH: Owner={owner}, Name={name}, Bounds={bounds}")

    if not wechat_windows:
        print("No WeChat windows found in Quartz list.")
        # Print first 10 for debug
        print("\nTop 10 Windows:")
        for i, w in enumerate(window_list[:10]):
            print(f"{i}: {w.get('kCGWindowOwnerName')} - {w.get('kCGWindowName')}")

if __name__ == "__main__":
    list_windows()
