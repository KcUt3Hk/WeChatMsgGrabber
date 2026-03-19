"""
Tests for auto scroll controller functionality.
"""
import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from PIL import Image
import numpy as np

from services.auto_scroll_controller import AutoScrollController
import services.auto_scroll_controller as asc
from models.data_models import WindowInfo, Rectangle


class TestAutoScrollController:
    """Test cases for AutoScrollController class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.controller = AutoScrollController(scroll_speed=2, scroll_delay=0.1)
    
    def test_initialization(self):
        """Test controller initialization."""
        assert self.controller.scroll_speed == 2
        assert self.controller.scroll_delay == 0.1
        assert self.controller.current_window is None
        assert self.controller.last_screenshot is None
    
    @patch('pygetwindow.getWindowsWithTitle')
    def test_locate_wechat_window_success(self, mock_get_windows):
        """Test successful WeChat window location."""
        # Mock window object
        mock_window = Mock()
        mock_window.visible = True
        mock_window.width = 800
        mock_window.height = 600
        mock_window.left = 100
        mock_window.top = 50
        mock_window.title = "微信"
        mock_window._hWnd = 12345
        
        mock_get_windows.return_value = [mock_window]
        
        result = self.controller.locate_wechat_window()
        
        assert result is not None
        assert result.title == "微信"
        assert result.position.x == 100
        assert result.position.y == 50
        assert result.position.width == 800
        assert result.position.height == 600

    def test_locate_wechat_window_macos_fallback_success_does_not_warn(self, monkeypatch, caplog):
        """测试 macOS 回退成功时不应输出“未找到窗口”的 warning。"""
        ctrl = AutoScrollController(enable_macos_fallback=True)
        monkeypatch.setattr(asc.sys, "platform", "darwin", raising=False)
        monkeypatch.setattr(asc.gw, "getWindowsWithTitle", lambda _title: [], raising=False)

        dummy = WindowInfo(
            handle=0,
            position=Rectangle(x=2, y=31, width=897, height=1344),
            is_active=True,
            title="WeChat",
        )
        monkeypatch.setattr(ctrl, "_macos_resolve_wechat_window", lambda _patterns: dummy, raising=False)

        caplog.set_level(logging.WARNING)
        result = ctrl.locate_wechat_window()
        assert result is not None
        assert not any("No WeChat window found" in r.message for r in caplog.records)
    
    @patch('pygetwindow.getWindowsWithTitle')
    @pytest.mark.requires_wechat_closed
    def test_locate_wechat_window_not_found(self, mock_get_windows):
        """测试在当前环境下未找到微信窗口的场景。

        说明：
        - 该用例标记为 requires_wechat_closed，由 tests/conftest.py 在收集阶段根据环境
          与 WECHAT_TEST_MODE（默认 auto）自适应决定是否跳过，以保证测试稳定性与覆盖率。
        """
        
        # 模拟系统中不存在微信窗口
        mock_get_windows.return_value = []
        result = self.controller.locate_wechat_window()

        # 断言：在无窗口场景下，locate_wechat_window 应返回 None
        assert result is None
        assert self.controller.current_window is None
    
    def test_get_chat_area_bounds_no_window(self):
        """Test chat area bounds when no window is set."""
        result = self.controller.get_chat_area_bounds()
        assert result is None
    
    def test_get_chat_area_bounds_with_window(self):
        """Test chat area bounds calculation."""
        # Set up mock window
        self.controller.current_window = WindowInfo(
            handle=12345,
            position=Rectangle(x=100, y=50, width=800, height=600),
            is_active=True,
            title="微信"
        )
        
        result = self.controller.get_chat_area_bounds()
        
        assert result is not None
        assert result.x == 360  # 100 + 250 + 10
        assert result.y == 90   # 50 + 30 + 10
        assert result.width == 530  # 800 - 250 - 20
        assert result.height == 460  # 600 - 30 - 100 - 20
    
    @patch('pyautogui.screenshot')
    def test_capture_current_view_success(self, mock_screenshot):
        """Test successful screenshot capture."""
        # Set up mock window
        self.controller.current_window = WindowInfo(
            handle=12345,
            position=Rectangle(x=100, y=50, width=800, height=600),
            is_active=True,
            title="微信"
        )
        
        # Mock screenshot
        mock_image = Mock(spec=Image.Image)
        mock_screenshot.return_value = mock_image
        
        # Mock window validation
        with patch.object(self.controller, 'is_window_valid', return_value=True):
            result = self.controller.capture_current_view()
        
        assert result == mock_image
        assert self.controller.last_screenshot == mock_image
    
    @patch('pyautogui.screenshot')
    def test_capture_region(self, mock_screenshot):
        """Test region screenshot capture."""
        mock_image = Mock(spec=Image.Image)
        mock_screenshot.return_value = mock_image
        
        region = Rectangle(x=100, y=100, width=200, height=150)
        result = self.controller.capture_region(region)
        
        assert result == mock_image
        mock_screenshot.assert_called_once_with(region=(100, 100, 200, 150))
    
    def test_optimize_screenshot_quality(self):
        """Test screenshot quality optimization."""
        # Create a simple test image
        img_array = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        test_image = Image.fromarray(img_array)
        
        result = self.controller.optimize_screenshot_quality(test_image)
        
        assert isinstance(result, Image.Image)
        assert result.size == test_image.size
    
    def test_compare_screenshots_identical(self):
        """Test screenshot comparison with identical images."""
        # Create identical test images
        img_array = np.random.randint(0, 255, (50, 50, 3), dtype=np.uint8)
        img1 = Image.fromarray(img_array)
        img2 = Image.fromarray(img_array.copy())
        
        result = self.controller._compare_screenshots(img1, img2)
        assert result is True
    
    def test_compare_screenshots_different(self):
        """Test screenshot comparison with different images."""
        # Create different test images
        img_array1 = np.zeros((50, 50, 3), dtype=np.uint8)
        img_array2 = np.ones((50, 50, 3), dtype=np.uint8) * 255
        
        img1 = Image.fromarray(img_array1)
        img2 = Image.fromarray(img_array2)
        
        result = self.controller._compare_screenshots(img1, img2)
        assert result is False
    
    def test_clear_screenshot_cache(self):
        """Test screenshot cache clearing."""
        # Set a mock screenshot
        self.controller.last_screenshot = Mock(spec=Image.Image)
        
        self.controller.clear_screenshot_cache()
        
        assert self.controller.last_screenshot is None
    
    def test_reset_controller(self):
        """Test controller reset."""
        # Set some state
        self.controller.current_window = Mock()
        self.controller.last_screenshot = Mock()
        
        self.controller.reset_controller()
        
        assert self.controller.current_window is None
        assert self.controller.last_screenshot is None
