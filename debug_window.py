#!/usr/bin/env python3
"""
调试窗口定位问题的脚本
"""
import os
import sys
import logging

# 添加项目根目录到路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

from services.auto_scroll_controller import AutoScrollController

def test_window_location():
    """测试窗口定位功能"""
    print("=== 测试窗口定位功能 ===")
    
    scroll = AutoScrollController()
    
    # 测试窗口定位
    print("\n1. 尝试定位微信窗口...")
    window = scroll.locate_wechat_window()
    
    if window:
        print(f"✅ 成功定位到窗口: {window.title}")
        print(f"   位置: ({window.position.x}, {window.position.y})")
        print(f"   大小: {window.position.width}x{window.position.height}")
        
        # 测试窗口激活
        print("\n2. 尝试激活窗口...")
        activated = scroll.activate_window()
        if activated:
            print("✅ 窗口激活成功")
        else:
            print("❌ 窗口激活失败")
            
        # 测试截图
        print("\n3. 尝试截图...")
        screenshot = scroll.capture_current_view()
        if screenshot:
            print(f"✅ 截图成功: {screenshot.size}")
            screenshot.save("/tmp/debug_screenshot.png")
            print("截图已保存到 /tmp/debug_screenshot.png")
        else:
            print("❌ 截图失败")
    else:
        print("❌ 无法定位微信窗口")
        
        # 测试macOS专用回退
        print("\n尝试macOS专用回退方法...")
        if hasattr(scroll, '_macos_resolve_wechat_window'):
            info = scroll._macos_resolve_wechat_window(["微信", "WeChat", "wechat"])
            if info:
                print(f"✅ macOS回退成功: {info.title}")
                print(f"   位置: ({info.position.x}, {info.position.y})")
                print(f"   大小: {info.position.width}x{info.position.height}")
            else:
                print("❌ macOS回退也失败")

def test_pygetwindow():
    """测试pygetwindow功能"""
    print("\n=== 测试pygetwindow功能 ===")
    
    try:
        import pygetwindow as gw
        
        print("1. 测试getAllWindows...")
        if hasattr(gw, 'getAllWindows'):
            windows = gw.getAllWindows()
            print(f"找到 {len(windows)} 个窗口")
            for i, w in enumerate(windows[:5]):  # 只显示前5个
                title = getattr(w, 'title', '未知')
                print(f"  {i+1}. {title}")
        else:
            print("getAllWindows方法不存在")
            
        print("\n2. 测试getWindowsWithTitle...")
        if hasattr(gw, 'getWindowsWithTitle'):
            wechat_windows = gw.getWindowsWithTitle("微信")
            print(f"找到 {len(wechat_windows)} 个包含'微信'的窗口")
            
            wechat_windows2 = gw.getWindowsWithTitle("WeChat")
            print(f"找到 {len(wechat_windows2)} 个包含'WeChat'的窗口")
        else:
            print("getWindowsWithTitle方法不存在")
            
        print("\n3. 测试getActiveWindow...")
        if hasattr(gw, 'getActiveWindow'):
            active = gw.getActiveWindow()
            if active:
                title = getattr(active, 'title', '未知')
                print(f"当前活动窗口: {title}")
            else:
                print("没有活动窗口")
        else:
            print("getActiveWindow方法不存在")
            
    except Exception as e:
        print(f"pygetwindow测试失败: {e}")

if __name__ == "__main__":
    test_pygetwindow()
    test_window_location()