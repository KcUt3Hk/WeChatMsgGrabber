"""
Auto scroll controller for WeChat window automation.
Handles window detection, positioning, and automated scrolling operations.
"""
import time
import threading
import logging
from typing import Optional, Tuple
import difflib
import sys
import subprocess
import os
import pygetwindow as gw
import pyautogui
from PIL import Image
import cv2
import numpy as np

from models.data_models import WindowInfo, Rectangle


class AutoScrollController:
    """Controller for automated scrolling operations in WeChat window."""
    
    def __init__(self, scroll_speed: int = 2, scroll_delay: float = 1.0, enable_macos_fallback: Optional[bool] = None, enable_watchdog: Optional[bool] = None, watchdog_interval: float = 5.0, allow_active_fallback: Optional[bool] = None, allow_title_enumeration_fallback: Optional[bool] = None):
        """
        初始化自动滚动控制器。

        函数级注释：
        - 负责基础滚动参数初始化、日志器配置、截图缓存与可选的窗口定位回退开关。
        - 新增参数 enable_macos_fallback 用于控制在 macOS 上是否启用 AppleScript 回退逻辑。
          为保证测试稳定性并避免在受限环境（如 CI、无桌面）误触发系统级调用，默认关闭；
          若在真实桌面环境需要增强定位能力，可通过构造参数或环境变量显式开启。
        - 新增可选看门狗，周期性检查窗口有效性并自动重试定位/激活，提升长时稳定性；默认不自动开启，
          可通过 enable_watchdog 或环境变量 WECHATMSGG_ENABLE_WATCHDOG 控制；watchdog_interval 控制心跳间隔秒数。
        - 新增 allow_active_fallback：是否允许在未匹配到“微信”标题时退路为当前活跃窗口；默认关闭以满足单测
          对“未找到微信窗口返回 None”的期望。可通过环境变量 WECHATMSGG_ACTIVE_WINDOW_FALLBACK 开启。
        - 新增 allow_title_enumeration_fallback：当 getWindowsWithTitle 存在但返回空时，是否允许改用全窗口枚举
          (getAllWindows) 进行标题匹配。默认关闭以满足单测期望；可通过环境变量 WECHATMSGG_ENUMERATION_FALLBACK 开启。

        Args:
            scroll_speed: 滚动速度（1-10）
            scroll_delay: 每次滚动之间的延迟（秒）
            enable_macos_fallback: 是否启用 macOS AppleScript 回退；
                - None: 默认关闭
                - True/False: 显式指定开关
            enable_watchdog: 是否启用看门狗线程（默认 None 表示通过环境变量控制）
            watchdog_interval: 看门狗心跳检查间隔（秒）
            allow_active_fallback: 未匹配到“微信”标题时是否退路为当前活跃窗口（默认 None：通过环境变量决定，默认关闭）
            allow_title_enumeration_fallback: 当存在 getWindowsWithTitle 但返回空时是否退路为 getAllWindows 枚举（默认关闭）
        """
        self.scroll_speed = scroll_speed
        self.scroll_delay = scroll_delay
        self.logger = logging.getLogger(__name__)
        self.current_window: Optional[WindowInfo] = None
        self.last_screenshot: Optional[Image.Image] = None
        # Optional overrides set by CLI for environments where window APIs are limited
        self._override_chat_area: Optional[Rectangle] = None
        self._title_override: Optional[str] = None
        # 速率限制配置：可选每分钟最大滚动次数
        self._rate_limit_max_spm: Optional[int] = None
        self._rate_window_start_ts: float = time.time()
        self._rate_count: int = 0
        # 动态速率抖动：在每分钟窗口内为上限设置一个随机子上限，模拟人类行为
        try:
            jitter_env = os.environ.get("WECHATMSGG_SPM_JITTER", "0.3").strip()
            self._rate_spm_jitter = max(0.0, min(0.9, float(jitter_env)))
        except Exception:
            self._rate_spm_jitter = 0.3
        self._rate_current_limit: Optional[int] = None
        # 可选的每分钟滚动区间（min,max），优先于单一上限
        self._rate_range_min: Optional[int] = None
        self._rate_range_max: Optional[int] = None

        # 看门狗相关
        # macOS AppleScript 回退：默认关闭，避免在测试/CI环境触发系统级调用造成不稳定。
        # 可通过构造参数或环境变量 WECHATMSGG_MACOS_FALLBACK 显式开启。
        if enable_macos_fallback is not None:
            self.enable_macos_fallback = bool(enable_macos_fallback)
        else:
            env_macos_fb = os.environ.get("WECHATMSGG_MACOS_FALLBACK", "0").lower()
            self.enable_macos_fallback = env_macos_fb in ("1", "true", "yes", "on")

        env_watchdog = os.environ.get("WECHATMSGG_ENABLE_WATCHDOG", "0").lower()
        self._watchdog_enabled = (
            bool(enable_watchdog)
            if enable_watchdog is not None
            else env_watchdog in ("1", "true", "yes", "on")
        )
        self._watchdog_interval = watchdog_interval
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_stop_event = threading.Event()
        # macOS AppleScript 回退开关：与上方保持一致（避免后续覆盖）
        # 注意：此处不再强制关闭，保持前述平台感知默认值。
        self.enable_macos_fallback = self.enable_macos_fallback
        
        # Active window 退路开关：默认关闭（与单测预期一致），可通过环境变量或构造参数显式开启。
        # 注意：之前版本在 macOS 上默认开启，导致在单元测试中即便 mock 了 getWindowsWithTitle
        # 仍可能因为活跃窗口回退而返回非 None，进而使“未找到微信窗口”的测试失败。
        # 为提高测试稳定性，这里统一设为默认关闭。
        default_active_flag = "0"
        env_active_fb = os.environ.get("WECHATMSGG_ACTIVE_WINDOW_FALLBACK", default_active_flag).lower()
        self._allow_active_fallback = (
            bool(allow_active_fallback)
            if allow_active_fallback is not None
            else env_active_fb in ("1", "true", "yes", "on")
        )

        # 标题枚举退路：默认关闭（与单测预期一致），可通过环境变量或构造参数显式开启。
        default_enum_flag = "0"
        env_enum_fb = os.environ.get("WECHATMSGG_ENUMERATION_FALLBACK", default_enum_flag).lower()
        self._enable_enumeration_fallback = (
            bool(allow_title_enumeration_fallback)
            if allow_title_enumeration_fallback is not None
            else env_enum_fb in ("1", "true", "yes", "on")
        )

        # Configure pyautogui settings
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1
    
    def locate_wechat_window(self) -> Optional[WindowInfo]:
        """
        定位并返回微信窗口信息。

        函数级注释：
        - 首选通过 pygetwindow 的标题匹配；若失败则在允许时（macOS 默认）进行全窗口枚举；
        - 在允许时（macOS 默认）可退路为“当前活动窗口”（需可见且尺寸合理）；
        - 在 macOS 平台上（默认启用），最终退路为 AppleScript 查询窗口信息；
        - 该多策略链路确保在受限环境下无需手动判断即可尽可能获取到窗口信息。

        Returns:
            找到则返回 WindowInfo，否则返回 None。
        """
        try:
            # Search for WeChat windows with common titles (or CLI-provided override)
            wechat_titles = [self._title_override] if self._title_override else ["微信", "WeChat", "wechat"]
            
            # Provide compatibility for environments where pygetwindow
            # does not expose getWindowsWithTitle by creating a graceful fallback.
            # Newer versions may only expose limited APIs, so we attempt to use
            # getWindowsWithTitle if present, otherwise default to empty list.
            for title_pattern in wechat_titles:
                windows = []
                # Prefer direct title search when available
                if hasattr(gw, 'getWindowsWithTitle'):
                    try:
                        windows = gw.getWindowsWithTitle(title_pattern)
                        if windows:
                            self.logger.debug("Found %d window(s) via getWindowsWithTitle('%s')", len(windows), title_pattern)
                    except Exception as e:
                        self.logger.debug("getWindowsWithTitle('%s') failed: %s", title_pattern, e)

                # Fallback: enumerate all windows and filter by title substring
                # 仅当：
                # - getWindowsWithTitle 不存在；或
                # - 显式允许枚举退路(self._enable_enumeration_fallback) 时
                if not windows and (
                    not hasattr(gw, 'getWindowsWithTitle') or self._enable_enumeration_fallback
                ) and hasattr(gw, 'getAllWindows'):
                    try:
                        all_windows = gw.getAllWindows()
                        for w in all_windows:
                            title = getattr(w, 'title', '') or ''
                            if title_pattern.lower() in title.lower():
                                windows.append(w)
                        if windows:
                            self.logger.debug("Found %d window(s) via getAllWindows filter for '%s'", len(windows), title_pattern)
                    except Exception as e:
                        self.logger.debug("getAllWindows() enumeration failed: %s", e)

                for window in windows:
                    if getattr(window, 'visible', True) and getattr(window, 'width', 0) > 100 and getattr(window, 'height', 0) > 100:
                        window_info = WindowInfo(
                            handle=window._hWnd if hasattr(window, '_hWnd') else 0,
                            position=Rectangle(
                                x=getattr(window, 'left', 0),
                                y=getattr(window, 'top', 0),
                                width=getattr(window, 'width', 0),
                                height=getattr(window, 'height', 0)
                            ),
                            is_active=(hasattr(gw, 'getActiveWindow') and window == gw.getActiveWindow()),
                            title=getattr(window, 'title', '')
                        )
                        self.current_window = window_info
                        self.logger.info(f"Found WeChat window: {getattr(window, 'title', '')} at ({getattr(window, 'left', 0)}, {getattr(window, 'top', 0)})")
                        return window_info
            
            # Fallback: use active window if present and reasonably sized（仅在允许时）
            active = None
            if self._allow_active_fallback:
                try:
                    active = gw.getActiveWindow()
                except Exception:
                    active = None
                # Some environments may return plain strings or unsupported types.
                if active and hasattr(active, 'width') and hasattr(active, 'height') and (
                    getattr(active, 'visible', True)
                ) and active.width > 100 and active.height > 100:
                    window_info = WindowInfo(
                        handle=active._hWnd if hasattr(active, '_hWnd') else 0,
                        position=Rectangle(
                            x=active.left,
                            y=active.top,
                            width=active.width,
                            height=active.height
                        ),
                        is_active=True,
                        title=getattr(active, 'title', '')
                    )
                    self.current_window = window_info
                    self.logger.warning(
                        "No explicit WeChat title matched; falling back to active window: '%s'. "
                        "请确保当前前台窗口是微信聊天窗口。",
                        getattr(active, 'title', '')
                    )
                    return window_info

            # If we get here, active window is unavailable or unsupported
            if active and self._allow_active_fallback:
                # Attempt: if active is a plain title string, try matching it against known WeChat patterns via getAllWindows
                if isinstance(active, str):
                    title_str = active
                    self.logger.debug("Active window title (string): '%s'", title_str)
                    patterns = wechat_titles
                    # Treat any title containing WeChat keywords as potential match
                    if any(pat.lower() in title_str.lower() for pat in patterns):
                        candidate = None
                        if hasattr(gw, 'getAllWindows'):
                            try:
                                for w in gw.getAllWindows():
                                    t = getattr(w, 'title', '') or ''
                                    if t and (t.lower() in title_str.lower() or title_str.lower() in t.lower() or any(pat.lower() in t.lower() for pat in patterns)):
                                        if getattr(w, 'visible', True) and getattr(w, 'width', 0) > 100 and getattr(w, 'height', 0) > 100:
                                            candidate = w
                                            break
                            except Exception as e:
                                self.logger.debug("Enumerating windows to resolve active title failed: %s", e)
                        if candidate:
                            window_info = WindowInfo(
                                handle=candidate._hWnd if hasattr(candidate, '_hWnd') else 0,
                                position=Rectangle(
                                    x=getattr(candidate, 'left', 0),
                                    y=getattr(candidate, 'top', 0),
                                    width=getattr(candidate, 'width', 0),
                                    height=getattr(candidate, 'height', 0)
                                ),
                                is_active=True,
                                title=getattr(candidate, 'title', title_str)
                            )
                            self.current_window = window_info
                            self.logger.info("Resolved WeChat window from active title string: %s", window_info.title)
                            return window_info
                # Log unsupported type for visibility
                self.logger.warning("Active window is unsupported type for fallback: %r", active)

            self.logger.warning("No WeChat window found")
            # macOS 专用回退：仅在启用时使用 AppleScript 通过 System Events 获取微信窗口位置
            if sys.platform == "darwin" and self.enable_macos_fallback:
                info = self._macos_resolve_wechat_window(wechat_titles)
                if info:
                    self.current_window = info
                    self.logger.info(
                        "Resolved WeChat window via macOS AppleScript fallback: '%s' at (%d, %d) size (%d x %d)",
                        info.title, info.position.x, info.position.y, info.position.width, info.position.height
                    )
                    return info
            return None
            
        except Exception as e:
            self.logger.error(f"Error locating WeChat window: {e}")
            return None
    
    def activate_window(self) -> bool:
        """
        激活并将微信窗口置于前台。

        函数级注释：
        - 优先使用 pygetwindow 执行窗口激活并校验；
        - 在 macOS 上，如常规方式失败且启用了 AppleScript 回退，则尝试调用 AppleScript 激活应用；
        - 测试环境默认不启用 AppleScript 回退，以避免不可控行为。

        Returns:
            成功激活返回 True，否则返回 False。
        """
        if not self.current_window:
            self.logger.error("No WeChat window available to activate")
            return False
        
        try:
            # Find window by title and activate it
            windows = []
            if hasattr(gw, 'getWindowsWithTitle'):
                windows = gw.getWindowsWithTitle(self.current_window.title)
            
            for window in windows:
                if (window.left == self.current_window.position.x and 
                    window.top == self.current_window.position.y):
                    
                    window.activate()
                    time.sleep(0.5)  # Wait for activation
                    
                    # Verify activation
                    active_window = gw.getActiveWindow()
                    if active_window and active_window.title == window.title:
                        self.current_window.is_active = True
                        self.logger.info("WeChat window activated successfully")
                        return True

            # 如果通过 pygetwindow 无法激活，且在 macOS 下，且启用了回退，再尝试 AppleScript 激活应用
            if sys.platform == "darwin" and self.enable_macos_fallback:
                if self._macos_activate_wechat():
                    time.sleep(0.5)
                    self.current_window.is_active = True
                    self.logger.info("WeChat window activated via macOS AppleScript")
                    return True

            self.logger.error("Failed to activate WeChat window")
            return False
            
        except Exception as e:
            self.logger.error(f"Error activating WeChat window: {e}")
            return False
    
    def is_window_valid(self) -> bool:
        """
        Check if current WeChat window is still valid and accessible.
        
        Returns:
            True if window is valid, False otherwise
        """
        if not self.current_window:
            return False
        
        try:
            # macOS AppleScript 回退：当通过 AppleScript 获得窗口矩形（handle=0）时，
            # 无法通过 pygetwindow 进行常规校验，但仍可用于屏幕截取。
            if sys.platform == "darwin" and getattr(self.current_window, "handle", 0) == 0:
                rect = self.current_window.position
                if rect and rect.width > 0 and rect.height > 0:
                    return True
            # Re-locate window to check if it still exists
            windows = []
            if hasattr(gw, 'getWindowsWithTitle'):
                windows = gw.getWindowsWithTitle(self.current_window.title)
            
            for window in windows:
                if (window.left == self.current_window.position.x and 
                    window.top == self.current_window.position.y and
                    window.visible):
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error validating window: {e}")
            return False
    
    def get_chat_area_bounds(self) -> Optional[Rectangle]:
        """
        Calculate the chat area bounds within the WeChat window.
        
        Returns:
            Rectangle representing the chat area, None if window not available
        """
        # If CLI provided override, use it directly
        if self._override_chat_area:
            return self._override_chat_area
        if not self.current_window:
            return None

        # 在 macOS 且启用了辅助功能回退时，优先尝试通过 System Events 获取聊天区域（scroll area）
        try:
            if sys.platform == "darwin" and self.enable_macos_fallback:
                rect = self._macos_get_chat_area_by_accessibility()
                if rect:
                    return rect
        except Exception as e:
            # 回退失败时继续采用估算方式，不中断流程
            self.logger.debug(f"macOS 辅助功能聊天区域解析失败，改用估算：{e}")
        
        # Estimate chat area (excluding title bar, sidebar, input area)
        # These are approximate values that may need adjustment
        title_bar_height = 30
        sidebar_width = 250
        input_area_height = 100
        margin = 10
        
        chat_x = self.current_window.position.x + sidebar_width + margin
        chat_y = self.current_window.position.y + title_bar_height + margin
        chat_width = self.current_window.position.width - sidebar_width - (margin * 2)
        # For height, only subtract top margin once as the input area already
        # accounts for the bottom space.
        chat_height = self.current_window.position.height - title_bar_height - input_area_height - margin
        
        return Rectangle(
            x=chat_x,
            y=chat_y,
            width=max(chat_width, 100),  # Ensure minimum width
            height=max(chat_height, 100)  # Ensure minimum height
        )

    def get_sidebar_area_bounds(self) -> Optional[Rectangle]:
        """
        计算微信窗口内左侧会话列表（Sidebar）的估算边界。

        函数级注释：
        - 优先基于窗口整体位置进行估算：排除标题栏高度并使用固定的侧边栏宽度；
        - 当启用 macOS 辅助功能时，sidebar 不通过 AppleScript 解析，保持估算策略（chat 区域已由辅助功能解析）；
        - 若当前窗口未知或无效，返回 None；若提供了聊天区域覆盖坐标，不强行派生 sidebar，避免坐标系不一致。

        Returns:
            Rectangle 表示侧边栏区域；无法计算时返回 None。
        """
        try:
            # 覆盖聊天区域时不派生侧边栏，交由调用方显式提供或回退
            if self._override_chat_area is not None:
                return None
            if not self.current_window or not self.is_window_valid():
                return None

            title_bar_height = 30
            sidebar_width = 250
            margin = 8

            x = self.current_window.position.x + margin
            y = self.current_window.position.y + title_bar_height + margin
            width = sidebar_width - margin * 2
            # 侧边栏通常贯穿窗口高度（除标题栏），底部可能有少量边距，这里保守减去 20 像素
            height = self.current_window.position.height - title_bar_height - margin - 20

            if width < 50 or height < 50:
                return None
            return Rectangle(x=int(x), y=int(y), width=int(width), height=int(height))
        except Exception:
            return None

    def scroll_sidebar(self, direction: str = "up") -> bool:
        """
        在侧边栏区域执行滚动（用于遍历会话列表）。

        Args:
            direction: 滚动方向（"up" 或 "down"）

        Returns:
            True 表示滚动成功；False 表示失败或无法确定侧边栏区域。

        函数级注释：
        - 使用与聊天区域一致的速率限制与滚动实现，确保行为统一；
        - 滚动中心选取侧边栏区域中心点，避免越界。
        """
        try:
            if not self.activate_window():
                return False
            sidebar = self.get_sidebar_area_bounds()
            if not sidebar:
                self.logger.warning("无法确定侧边栏区域，滚动失败")
                return False

            center_x = sidebar.x + sidebar.width // 2
            center_y = sidebar.y + sidebar.height // 2

            self.throttle_if_needed()
            scroll_amount = self.scroll_speed * 3
            if direction.lower() == "up":
                pyautogui.scroll(scroll_amount, x=center_x, y=center_y)
            elif direction.lower() == "down":
                pyautogui.scroll(-scroll_amount, x=center_x, y=center_y)
            else:
                self.logger.error(f"Invalid sidebar scroll direction: {direction}")
                return False
            time.sleep(self.scroll_delay)
            return True
        except Exception as e:
            self.logger.error(f"侧边栏滚动异常：{e}")
            return False

    def click_at(self, x: int, y: int) -> bool:
        """
        在屏幕绝对坐标 (x, y) 处执行点击。

        Args:
            x: 屏幕绝对坐标 X
            y: 屏幕绝对坐标 Y

        Returns:
            True 表示点击成功；False 表示失败。

        函数级注释：
        - 使用 pyautogui.moveTo + click，点击前激活窗口以确保事件投递至微信；
        - 对异常进行捕获，不抛出，便于上层重试。
        """
        try:
            if not self.activate_window():
                return False
            pyautogui.moveTo(x, y)
            pyautogui.click(x, y)
            time.sleep(0.15)
            return True
        except Exception as e:
            self.logger.error(f"点击失败：{e}")
            return False

    def click_session_by_text(self, title: str, ocr_processor) -> bool:
        """
        通过 OCR 在侧边栏列表中定位会话标题并点击进入会话。

        Args:
            title: 目标会话标题文本（完整或部分匹配）
            ocr_processor: OCRProcessor 实例（需已初始化）

        Returns:
            True 表示成功点击到会话；False 表示未找到或发生错误。

        函数级注释：
        - 截取侧边栏区域，调用 OCRProcessor.extract_text_regions 获取文本与边界框；
        - 文本匹配策略：先尝试大小写不敏感的包含匹配；若失败，使用 difflib 的相似度阈值（>=0.8）进行模糊匹配；
        - 点击位置取候选边界框中心点，并换算为屏幕绝对坐标：abs = sidebar_origin + bbox_relative；
        - 若当前侧边栏未找到目标，会尝试轻微滚动两次（向下/向上各一次），每次重新识别。
        """
        try:
            if not self.activate_window():
                return False
            sidebar = self.get_sidebar_area_bounds()
            if not sidebar:
                self.logger.warning("无法确定侧边栏区域，跳过点击会话")
                return False
            # 内部函数：识别并尝试点击
            def _try_once() -> bool:
                img = self.capture_region(sidebar)
                if img is None:
                    return False
                try:
                    regions = ocr_processor.extract_text_regions(img, preprocess=True)
                except Exception as e:
                    self.logger.error(f"侧边栏 OCR 识别失败：{e}")
                    return False
                # 选择最佳匹配区域
                target_lower = title.strip().lower()
                best_region = None
                best_score = 0.0
                for tr in regions:
                    txt = (tr.text or "").strip()
                    if not txt:
                        continue
                    txt_lower = txt.lower()
                    score = 0.0
                    if target_lower in txt_lower or txt_lower in target_lower:
                        score = 1.0
                    else:
                        try:
                            score = difflib.SequenceMatcher(None, target_lower, txt_lower).ratio()
                        except Exception:
                            score = 0.0
                    if score > best_score:
                        best_score = score
                        best_region = tr

                if best_region is None or best_score < 0.8:
                    return False

                # 计算绝对点击坐标（边界框中心）
                bb = best_region.bounding_box
                click_x = int(sidebar.x + bb.x + max(1, bb.width // 2))
                click_y = int(sidebar.y + bb.y + max(1, bb.height // 2))

                return self.click_at(click_x, click_y)

            # 尝试：当前视图
            if _try_once():
                return True
            # 轻微滚动以刷新视图并再次尝试（向下）
            self.scroll_sidebar(direction="down")
            if _try_once():
                return True
            # 向上滚动一次，再试
            self.scroll_sidebar(direction="up")
            return _try_once()
        except Exception as e:
            self.logger.error(f"按会话标题点击失败：{e}")
            return False

    def get_window_height(self) -> Optional[int]:
        """
        获取用于滚动的基准高度。
        
        函数级注释：
        - 优先使用已解析的聊天区域高度（覆盖坐标或辅助功能解析），更贴近实际滚动区域；
        - 若无聊天区域可用，则退回到窗口高度；
        - 若仍无法获取，则返回 None。
        
        Returns:
            高度（像素），如果无法获取则返回 None
        """
        try:
            # 1) 优先：覆盖的聊天区域高度
            if self._override_chat_area is not None:
                return int(self._override_chat_area.height)
            # 2) 次选：可解析到的聊天区域（macOS 默认启用辅助功能解析）
            chat_rect = None
            if sys.platform == "darwin" and self.enable_macos_fallback:
                try:
                    chat_rect = self._macos_get_chat_area_by_accessibility()
                except Exception:
                    chat_rect = None
            if chat_rect is None:
                try:
                    chat_rect = self.get_chat_area_bounds()
                except Exception:
                    chat_rect = None
            if chat_rect is not None and chat_rect.height > 0:
                return int(chat_rect.height)
            # 3) 最后：窗口高度
            if self.current_window:
                return int(self.current_window.position.height)
            return None
        except Exception:
            return None

    def scroll_by_window_height(self, direction: str = "down") -> bool:
        """
        按窗口高度进行滑动，提高滑动效率
        
        Args:
            direction: 滑动方向（"up" 或 "down"）
            
        Returns:
            True if scrolling successful, False otherwise
        """
        window_height = self.get_window_height()
        if not window_height:
            self.logger.warning("无法获取窗口高度，使用默认滑动方式")
            return self.start_scrolling(direction)
        
        # 计算滑动距离（窗口高度的80%，避免滑动过度）
        scroll_distance = int(window_height * 0.8)
        
        try:
            chat_area = self.get_chat_area_bounds()
            if not chat_area:
                return False
            
            # 计算滑动中心点
            scroll_x = chat_area.x + chat_area.width // 2
            scroll_y = chat_area.y + chat_area.height // 2
            
            # 执行滑动操作前进行速率限制
            self.throttle_if_needed()
            # 执行滑动操作
            try:
                pyautogui.moveTo(scroll_x, scroll_y, duration=0.1)
            except Exception:
                pass
            if direction.lower() == "down":
                pyautogui.scroll(-scroll_distance, x=scroll_x, y=scroll_y)
            elif direction.lower() == "up":
                pyautogui.scroll(scroll_distance, x=scroll_x, y=scroll_y)
            else:
                self.logger.error(f"Invalid scroll direction: {direction}")
                return False
            
            # 增加滑动后的等待时间，确保内容加载完成
            time.sleep(max(1.0, self.scroll_delay * 2))
            self.logger.info(f"按窗口高度滑动 {direction}，距离: {scroll_distance}px")
            # 键盘回退：部分环境滚轮事件不被接收时，使用 PageUp/PageDown 辅助
            try:
                if direction.lower() == "down":
                    pyautogui.press('pagedown')
                else:
                    pyautogui.press('pageup')
            except Exception:
                pass
            return True
            
        except Exception as e:
            self.logger.error(f"按窗口高度滑动失败: {e}")
            return False

    def set_override_chat_area(self, rect: Rectangle | Tuple[int, int, int, int]):
        """Set manual chat area override given a Rectangle or (x,y,w,h) tuple."""
        if isinstance(rect, tuple):
            rect = Rectangle(x=rect[0], y=rect[1], width=rect[2], height=rect[3])
        self._override_chat_area = rect
        self.logger.info("Chat area override set to (%d, %d, %d, %d)", rect.x, rect.y, rect.width, rect.height)

    def set_title_override(self, title: str | None):
        """Set window title substring override for locating the WeChat window."""
        self._title_override = title
        if title:
            self.logger.info("Window title override set to '%s'", title)

    def has_chat_area_override(self) -> bool:
        """Return True if a manual chat area override has been set."""
        return self._override_chat_area is not None
    
    def start_scrolling(self, direction: str = "up") -> bool:
        """
        Start automated scrolling in the specified direction.
        
        Args:
            direction: Scroll direction ("up" or "down")
            
        Returns:
            True if scrolling started successfully, False otherwise
        """
        # If we have a manual chat-area override, allow scrolling without a window object
        if (not self._override_chat_area) and (not self.current_window or not self.is_window_valid()):
            self.logger.error("Invalid WeChat window for scrolling")
            return False

        # Activate window only when we rely on window APIs
        if not self._override_chat_area:
            if not self.activate_window():
                return False
        
        try:
            chat_area = self.get_chat_area_bounds()
            if not chat_area:
                self.logger.error("Could not determine chat area bounds")
                return False
            
            # Calculate scroll center point
            scroll_x = chat_area.x + chat_area.width // 2
            scroll_y = chat_area.y + chat_area.height // 2
            
            # 执行滚动前进行速率限制
            self.throttle_if_needed()
            # Perform scroll operation
            scroll_amount = self.scroll_speed * 3  # Adjust scroll distance
            try:
                pyautogui.moveTo(scroll_x, scroll_y, duration=0.1)
            except Exception:
                pass
            
            if direction.lower() == "up":
                pyautogui.scroll(scroll_amount, x=scroll_x, y=scroll_y)
            elif direction.lower() == "down":
                pyautogui.scroll(-scroll_amount, x=scroll_x, y=scroll_y)
            else:
                self.logger.error(f"Invalid scroll direction: {direction}")
                return False
            
            time.sleep(self.scroll_delay)
            self.logger.debug(f"Scrolled {direction} in chat area")
            return True
            
        except Exception as e:
            self.logger.error(f"Error during scrolling: {e}")
            return False
    
    def scroll_to_position(self, x: int, y: int, direction: str = "up") -> bool:
        """
        Scroll at a specific position within the chat area.
        
        Args:
            x: X coordinate relative to chat area
            y: Y coordinate relative to chat area  
            direction: Scroll direction ("up" or "down")
            
        Returns:
            True if scroll successful, False otherwise
        """
        if (not self._override_chat_area) and (not self.current_window or not self.is_window_valid()):
            return False
        
        try:
            chat_area = self.get_chat_area_bounds()
            if not chat_area:
                return False
            
            # Convert relative coordinates to absolute
            abs_x = chat_area.x + x
            abs_y = chat_area.y + y
            
            # Ensure coordinates are within chat area
            if (abs_x < chat_area.x or abs_x > chat_area.x + chat_area.width or
                abs_y < chat_area.y or abs_y > chat_area.y + chat_area.height):
                self.logger.warning("Scroll coordinates outside chat area")
                return False
            
            scroll_amount = self.scroll_speed * 3
            
            if direction.lower() == "up":
                pyautogui.scroll(scroll_amount, x=abs_x, y=abs_y)
            else:
                pyautogui.scroll(-scroll_amount, x=abs_x, y=abs_y)
            
            time.sleep(self.scroll_delay)
            return True
            
        except Exception as e:
            self.logger.error(f"Error scrolling to position: {e}")
            return False
    
    def is_at_top(self) -> bool:
        """
        Check if chat view has reached the top (no more messages to scroll).
        
        Returns:
            True if at top, False otherwise
        """
        if (not self._override_chat_area) and (not self.current_window or not self.is_window_valid()):
            return False
        
        try:
            # Take screenshot before and after scroll attempt
            screenshot_before = self.capture_current_view()
            if not screenshot_before:
                return False
            
            # Attempt small scroll up
            original_speed = self.scroll_speed
            original_delay = self.scroll_delay
            
            self.scroll_speed = 1  # Use minimal scroll
            self.scroll_delay = 0.3
            
            scroll_success = self.start_scrolling("up")
            
            # Restore original settings
            self.scroll_speed = original_speed
            self.scroll_delay = original_delay
            
            if not scroll_success:
                return False
            
            # Take screenshot after scroll
            screenshot_after = self.capture_current_view()
            if not screenshot_after:
                return False
            
            # Compare screenshots to detect if content changed
            return self._compare_screenshots(screenshot_before, screenshot_after)
            
        except Exception as e:
            self.logger.error(f"Error checking if at top: {e}")
            return False

    def is_at_bottom(self) -> bool:
        """
        检查聊天视图是否到达底部（无法再向下滚动）。

        函数级注释：
        - 通过尝试一次极小幅度的向下滚动，并比较前后截图的相似度来判断；
        - 若两次截图在高阈值下近似相同，认为已到达底部；
        - 在提供聊天区域覆盖的情况下，允许不依赖窗口 API 进行截图与滚动。

        Returns:
            True 表示到达底部；False 表示尚可继续向下滚动或检测失败。
        """
        if (not self._override_chat_area) and (not self.current_window or not self.is_window_valid()):
            return False
        try:
            # 滚动前截图
            screenshot_before = self.capture_current_view()
            if not screenshot_before:
                return False

            # 使用极小滚动幅度
            original_speed = self.scroll_speed
            original_delay = self.scroll_delay

            self.scroll_speed = 1
            self.scroll_delay = 0.3

            scroll_success = self.start_scrolling("down")

            # 还原设置
            self.scroll_speed = original_speed
            self.scroll_delay = original_delay

            if not scroll_success:
                return False

            # 滚动后截图
            screenshot_after = self.capture_current_view()
            if not screenshot_after:
                return False

            # 若内容相似度很高，说明到达底部
            return self._compare_screenshots(screenshot_before, screenshot_after)
        except Exception as e:
            self.logger.error(f"Error checking if at bottom: {e}")
            return False
    
    def _compare_screenshots(self, img1: Image.Image, img2: Image.Image, threshold: float = 0.92) -> bool:
        """
        Compare two screenshots to determine if they are similar.
        
        Args:
            img1: First screenshot
            img2: Second screenshot
            threshold: Similarity threshold (0.0 to 1.0)
            
        Returns:
            True if images are similar (indicating no scroll movement), False otherwise
        """
        try:
            g1 = cv2.cvtColor(np.array(img1.convert('RGB')), cv2.COLOR_RGB2GRAY)
            g2 = cv2.cvtColor(np.array(img2.convert('RGB')), cv2.COLOR_RGB2GRAY)
            if g1.shape != g2.shape:
                return False
            g1 = g1.astype(np.float64)
            g2 = g2.astype(np.float64)
            kernel = (7, 7)
            mu1 = cv2.GaussianBlur(g1, kernel, 1.5)
            mu2 = cv2.GaussianBlur(g2, kernel, 1.5)
            mu1_sq = mu1 * mu1
            mu2_sq = mu2 * mu2
            mu1_mu2 = mu1 * mu2
            sigma1_sq = cv2.GaussianBlur(g1 * g1, kernel, 1.5) - mu1_sq
            sigma2_sq = cv2.GaussianBlur(g2 * g2, kernel, 1.5) - mu2_sq
            sigma12 = cv2.GaussianBlur(g1 * g2, kernel, 1.5) - mu1_mu2
            L = 255.0
            C1 = (0.01 * L) ** 2
            C2 = (0.03 * L) ** 2
            ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
            similarity = float(ssim_map.mean())
            self.logger.debug(f"Screenshot SSIM: {similarity:.3f}")
            return bool(similarity >= threshold)
            
        except Exception as e:
            self.logger.error(f"Error comparing screenshots: {e}")
            return False
    
    def capture_current_view(self) -> Optional[Image.Image]:
        """
        Capture screenshot of current WeChat chat area.
        
        Returns:
            PIL Image of chat area, None if capture failed
        """
        # 当提供聊天区域覆盖时，允许不依赖窗口API直接截图
        if not self._override_chat_area:
            # 窗口无效时尝试一次重定位/激活以提升鲁棒性
            if not self.current_window or not self.is_window_valid():
                self.logger.warning("窗口状态无效，尝试重定位/激活后再截图……")
                try:
                    self.ensure_window_ready(retries=2, delay=0.3)
                except Exception as e:
                    self.logger.error(f"窗口重定位/激活失败：{e}")
                    return None
        
        try:
            chat_area = self.get_chat_area_bounds()
            if not chat_area:
                self.logger.error("Could not determine chat area for screenshot")
                return None
            
            # Capture screenshot of chat area
            screenshot = pyautogui.screenshot(region=(
                chat_area.x,
                chat_area.y,
                chat_area.width,
                chat_area.height
            ))
            
            self.last_screenshot = screenshot
            self.logger.debug(f"Captured screenshot: {chat_area.width}x{chat_area.height}")
            return screenshot
            
        except Exception as e:
            self.logger.error(f"Error capturing screenshot: {e}")
            return None

    def ensure_window_ready(self, retries: int = 2, delay: float = 0.3) -> bool:
        """
        确保微信窗口可用于截图：若窗口未定位或失效，尝试重定位并激活。

        Args:
            retries: 最大重试次数
            delay: 每次重试之间的等待秒数

        Returns:
            True 表示窗口已就绪；False 表示仍不可用。
        """
        # 当提供聊天区域覆盖时，不依赖窗口 API，直接视为就绪。
        # 函数级注释：
        # - 在受限或无窗口 API 的环境中（例如远程/CI），通过覆盖坐标进行截图；
        # - 此时调用 ensure_window_ready 仅用于兼容既有流程，应当快速返回 True，避免无意义的窗口重试与噪声日志。
        if self._override_chat_area is not None:
            return True
        ok = False
        for i in range(max(1, retries)):
            try:
                if not self.current_window:
                    win = self.locate_wechat_window()
                    if not win:
                        time.sleep(max(0.0, delay))
                        continue
                # 尝试激活窗口
                if not self.activate_window():
                    time.sleep(max(0.0, delay))
                    continue
                if self.is_window_valid():
                    ok = True
                    break
            except Exception as e:
                self.logger.warning(f"第{i+1}次窗口就绪检查异常：{e}")
                time.sleep(max(0.0, delay))
        if not ok:
            self.logger.error("窗口仍不可用，放弃截图。")
        return ok

    def set_rate_limits(self, scroll_delay: Optional[float] = None, scroll_speed: Optional[int] = None, max_scrolls_per_minute: Optional[int] = None) -> None:
        """
        设置滚动速率限制与参数。

        函数级注释：
        - 允许在运行期间动态调整 scroll_delay、scroll_speed；
        - 可选启用每分钟最大滚动次数限制（max_scrolls_per_minute），防止长时运行过快导致不稳定；
        - 限速通过内部计数器与时间窗进行节流，实现软限速，不影响功能正确性。

        Args:
            scroll_delay: 每次滚动后的延时（秒），为 None 则保持不变
            scroll_speed: 基础滚动速度（1-10），为 None 则保持不变
            max_scrolls_per_minute: 每分钟最大滚动次数限制，None 表示关闭限速
        """
        if scroll_delay is not None:
            self.scroll_delay = max(0.0, float(scroll_delay))
        if scroll_speed is not None:
            self.scroll_speed = max(1, min(10, int(scroll_speed)))
        self._rate_limit_max_spm = max_scrolls_per_minute if (max_scrolls_per_minute is None or max_scrolls_per_minute > 0) else None
        # 重置当前窗口的动态子上限，在下一次 throttle 计算时生效
        self._rate_current_limit = None

    def set_spm_range(self, spm_min: int, spm_max: int) -> None:
        """设置每分钟滚动的动态区间（min,max），优先用于生成本分钟的目标上限。

        函数级注释：
        - 当设置了区间后，在每个60秒时间窗开始时会随机选择一个本分钟子上限；
        - 若同时设置了单一上限与区间，以区间为准；
        - 可与抖动系数配合使用，但区间更直接，抖动会作为保守下限补充。
        """
        try:
            spm_min = int(spm_min)
            spm_max = int(spm_max)
            if spm_min <= 0 or spm_max <= 0 or spm_min > spm_max:
                raise ValueError("invalid spm range")
            self._rate_range_min = spm_min
            self._rate_range_max = spm_max
            # 切换区间后立即重置本分钟子上限，使其在下一次窗口刷新时重新生成
            self._rate_current_limit = None
        except Exception:
            # 无效区间时清空
            self._rate_range_min = None
            self._rate_range_max = None
            self._rate_current_limit = None

    def throttle_if_needed(self) -> None:
        """
        根据配置进行滚动节流（每分钟最大滚动次数）。

        函数级注释：
        - 若配置了 _rate_limit_max_spm，则统计当前时间窗内的滚动次数；
        - 当达到限制时，休眠至下一分钟窗开始；
        - 每次调用视为一次滚动尝试，并更新计数。
        """
        if not self._rate_limit_max_spm:
            return
        now = time.time()
        # 新的时间窗：超过60秒则重置
        if now - self._rate_window_start_ts >= 60.0:
            self._rate_window_start_ts = now
            self._rate_count = 0
            # 在新窗口开始时，计算本分钟的动态子上限（不超过配置上限）
            try:
                import random
                # 优先使用设置的区间；否则依据单一上限与抖动系数生成
                if self._rate_range_min and self._rate_range_max:
                    low = int(self._rate_range_min)
                    high = int(self._rate_range_max)
                    self._rate_current_limit = random.randint(low, max(low, high))
                else:
                    base = int(self._rate_limit_max_spm or 0)
                    if base > 0:
                        low = max(1, int(round(base * max(0.1, 1.0 - self._rate_spm_jitter))))
                        high = base
                        self._rate_current_limit = random.randint(low, high)
                    else:
                        self._rate_current_limit = None
            except Exception:
                self._rate_current_limit = None
        if self._rate_count >= self._rate_limit_max_spm:
            # 休眠到时间窗结束
            sleep_for = max(0.0, 60.0 - (now - self._rate_window_start_ts))
            if sleep_for > 0:
                self.logger.debug(f"限速触发：休眠 {sleep_for:.2f}s 以遵守每分钟 {self._rate_limit_max_spm} 次滚动上限")
                time.sleep(sleep_for)
            # 切换到新的时间窗
            self._rate_window_start_ts = time.time()
            self._rate_count = 0
        # 若设置了动态子上限，按子上限进行软节流（比总上限更保守）
        try:
            if self._rate_current_limit and self._rate_count >= int(self._rate_current_limit):
                # 进行一次短暂停顿，模拟人类不规律的停顿
                import random
                extra = random.uniform(0.8, 2.2)
                self.logger.debug(f"动态子上限 {self._rate_current_limit} 触发：额外停顿 {extra:.2f}s")
                time.sleep(extra)
                # 重置子上限计数窗口但不重置分钟窗（保持柔性节流）
                self._rate_count = max(0, self._rate_count - int(self._rate_current_limit // 2))
        except Exception:
            pass
        # 计数一次滚动尝试
        self._rate_count += 1

    def start_watchdog(self) -> bool:
        """
        启动看门狗线程（如启用），周期性检查窗口有效性并自动重试定位/激活。

        函数级注释：
        - 该方法不会在单元测试中自动调用，避免干扰；
        - 当 _watchdog_enabled 为 True 时启动后台线程，每 watchdog_interval 秒进行一次检查；
        - 检查失败时尝试 ensure_window_ready，并记录心跳日志。
        """
        if not self._watchdog_enabled:
            return False
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return True
        self._watchdog_stop_event.clear()
        def _loop():
            while not self._watchdog_stop_event.is_set():
                try:
                    # 心跳与窗口检查
                    if (not self._override_chat_area) and (not self.current_window or not self.is_window_valid()):
                        self.logger.debug("看门狗：检测到窗口状态异常，尝试重定位/激活……")
                        try:
                            self.ensure_window_ready(retries=2, delay=0.3)
                        except Exception as e:
                            self.logger.debug(f"看门狗重试发生异常：{e}")
                    else:
                        self.logger.debug("看门狗：窗口正常")
                except Exception as e:
                    self.logger.debug(f"看门狗循环异常：{e}")
                finally:
                    time.sleep(max(0.1, self._watchdog_interval))
        self._watchdog_thread = threading.Thread(target=_loop, name="AutoScrollWatchdog", daemon=True)
        self._watchdog_thread.start()
        self.logger.info("看门狗线程已启动")
        return True

    def stop_watchdog(self) -> None:
        """
        停止看门狗线程并清理资源。

        函数级注释：
        - 通过事件通知后台循环退出，并在短时间内 join 线程；
        - 若线程不存在或已停止则忽略。
        """
        try:
            if self._watchdog_thread and self._watchdog_thread.is_alive():
                self._watchdog_stop_event.set()
                self._watchdog_thread.join(timeout=2.0)
                self.logger.info("看门狗线程已停止")
        except Exception:
            pass
    
    def capture_full_window(self) -> Optional[Image.Image]:
        """
        Capture screenshot of entire WeChat window.
        
        Returns:
            PIL Image of full window, None if capture failed
        """
        if not self.current_window or not self.is_window_valid():
            return None
        
        try:
            screenshot = pyautogui.screenshot(region=(
                self.current_window.position.x,
                self.current_window.position.y,
                self.current_window.position.width,
                self.current_window.position.height
            ))
            
            self.logger.debug("Captured full window screenshot")
            return screenshot
            
        except Exception as e:
            self.logger.error(f"Error capturing full window: {e}")
            return None
    
    def capture_region(self, region: Rectangle) -> Optional[Image.Image]:
        """
        Capture screenshot of specified region.
        
        Args:
            region: Rectangle defining the capture area
            
        Returns:
            PIL Image of specified region, None if capture failed
        """
        try:
            screenshot = pyautogui.screenshot(region=(
                region.x,
                region.y,
                region.width,
                region.height
            ))
            
            self.logger.debug(f"Captured region screenshot: {region.width}x{region.height}")
            return screenshot
            
        except Exception as e:
            self.logger.error(f"Error capturing region: {e}")
            return None
    
    def optimize_screenshot_quality(self, image: Image.Image) -> Image.Image:
        """
        Optimize screenshot quality for better OCR processing.
        
        Args:
            image: Input PIL Image
            
        Returns:
            Optimized PIL Image
        """
        try:
            # Convert to numpy array for OpenCV processing
            img_array = np.array(image)
            
            # Convert RGB to BGR for OpenCV
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Apply image enhancement techniques
            # 1. Increase contrast
            alpha = 1.2  # Contrast control
            beta = 10    # Brightness control
            enhanced = cv2.convertScaleAbs(img_bgr, alpha=alpha, beta=beta)
            
            # 2. Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(enhanced, (1, 1), 0)
            
            # 3. Sharpen the image
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(blurred, -1, kernel)
            
            # Convert back to RGB and PIL Image
            img_rgb = cv2.cvtColor(sharpened, cv2.COLOR_BGR2RGB)
            optimized_image = Image.fromarray(img_rgb)
            
            self.logger.debug("Screenshot quality optimized")
            return optimized_image
            
        except Exception as e:
            self.logger.error(f"Error optimizing screenshot: {e}")
            return image  # Return original if optimization fails
    
    def get_last_screenshot(self) -> Optional[Image.Image]:
        """
        Get the last captured screenshot.
        
        Returns:
            Last captured PIL Image, None if no screenshot available
        """
        return self.last_screenshot
    
    def clear_screenshot_cache(self):
        """Clear cached screenshot to free memory."""
        self.last_screenshot = None
        self.logger.debug("Screenshot cache cleared")
    
    def stop_scrolling(self) -> bool:
        """
        Stop any ongoing scrolling operations.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            # For this implementation, there's no continuous scrolling to stop
            # This method is here for interface compatibility
            self.logger.info("Scrolling operations stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping scrolling: {e}")
            return False
    
    def reset_controller(self):
        """Reset controller state and clear cached data."""
        self.current_window = None
        self.last_screenshot = None
        self.logger.info("Auto scroll controller reset")

    # -------------------- macOS Fallbacks (AppleScript) --------------------
    def _macos_get_chat_area_by_accessibility(self) -> Optional[Rectangle]:
        """
        通过 macOS 辅助功能（System Events）枚举微信窗口的 scroll areas，自动选择最大候选作为聊天区域。

        函数级注释：
        - 在 WeChat/微信 的窗口内，通常存在两个主要 scroll areas：左侧会话列表和右侧消息内容区；
          我们选取面积最大的区域作为聊天内容区，以适配不同分辨率与缩放；
        - AppleScript 返回的 UI 元素位置可能为相对窗口坐标或屏幕坐标，方法中会进行归一化处理并校验区域是否位于窗口范围内；
        - 若辅助功能查询失败或无有效候选，则返回 None，调用方会使用估算逻辑回退。

        Returns:
            Rectangle 若成功解析到聊天区域；否则 None。
        """
        if sys.platform != "darwin" or not self.enable_macos_fallback:
            return None
        # 若当前窗口未知，尝试定位一次（包含 AppleScript 回退）
        try:
            if not self.current_window:
                self.locate_wechat_window()
            if not self.current_window:
                return None
        except Exception:
            return None

        win_rect = self.current_window.position
        # 优先尝试英文名进程，其次中文名
        scripts = [
            r'''
            tell application "System Events"
                if exists application process "WeChat" then
                    tell application process "WeChat"
                        tell window 1
                            set rectText to ""
                            repeat with s in scroll areas
                                try
                                    set p to position of s
                                    set sz to size of s
                                    set rectText to rectText & (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of sz as text) & "," & (item 2 of sz as text) & ";"
                                end try
                            end repeat
                            return rectText
                        end tell
                    end tell
                else
                    return ""
                end if
            end tell
            ''',
            r'''
            tell application "System Events"
                if exists application process "微信" then
                    tell application process "微信"
                        tell window 1
                            set rectText to ""
                            repeat with s in scroll areas
                                try
                                    set p to position of s
                                    set sz to size of s
                                    set rectText to rectText & (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of sz as text) & "," & (item 2 of sz as text) & ";"
                                end try
                            end repeat
                            return rectText
                        end tell
                    end tell
                else
                    return ""
                end if
            end tell
            ''',
        ]

        output = ""
        for sc in scripts:
            try:
                res = subprocess.run(["osascript", "-e", sc], capture_output=True, text=True)
                if res.returncode == 0:
                    output = (res.stdout or "").strip()
                    break
            except Exception as e:
                self.logger.debug("AppleScript scroll areas query failed: %s", e)

        if not output:
            return None

        # 解析 "x,y,w,h;..." 序列
        candidates: list[Rectangle] = []
        for part in output.split(";"):
            part = part.strip()
            if not part:
                continue
            try:
                nums = [int(x.strip()) for x in part.split(",") if x.strip()]
                if len(nums) >= 4:
                    x, y, w, h = nums[0], nums[1], nums[2], nums[3]
                    # 将坐标归一化为屏幕绝对坐标：若明显小于窗口起点，视为相对窗口坐标
                    if x < win_rect.x or y < win_rect.y:
                        x += win_rect.x
                        y += win_rect.y
                    rect = Rectangle(x=x, y=y, width=w, height=h)
                    # 过滤掉不在窗口范围内或尺寸过小的区域
                    if (
                        rect.width >= 100 and rect.height >= 80 and
                        rect.x >= win_rect.x and rect.y >= win_rect.y and
                        rect.x + rect.width <= win_rect.x + win_rect.width and
                        rect.y + rect.height <= win_rect.y + win_rect.height
                    ):
                        candidates.append(rect)
            except Exception:
                continue

        if not candidates:
            return None

        # 选择面积最大者，进一步偏好宽度占比更大的区域（排除左侧窄列表）
        def area(r: Rectangle) -> int:
            return int(r.width * r.height)
        candidates.sort(key=lambda r: (area(r), r.width), reverse=True)
        best = candidates[0]

        # 若存在候选但最佳宽度占窗口的比例过低（<30%），尝试找到宽度更优者
        min_width_ratio = 0.3
        alt = max(candidates, key=lambda r: r.width / max(1, win_rect.width))
        if (best.width / max(1, win_rect.width)) < min_width_ratio and (alt.width / max(1, win_rect.width)) >= min_width_ratio:
            best = alt

        self.logger.debug(
            "macOS 辅助功能解析聊天区域：x=%d, y=%d, w=%d, h=%d (窗口 w=%d, h=%d)",
            best.x, best.y, best.width, best.height, win_rect.width, win_rect.height
        )
        return best
    def _macos_resolve_wechat_window(self, patterns: list[str]) -> Optional[WindowInfo]:
        """
        macOS 专用：通过 AppleScript/System Events 解析微信窗口信息。

        该方法在 pygetwindow 无法枚举或返回字符串 Active Window 时使用，
        直接向系统查询 WeChat/微信 应用进程的前台窗口的标题与边界。

        Args:
            patterns: 用于匹配窗口标题的关键字列表（如 ["微信", "WeChat"]).

        Returns:
            WindowInfo，如果成功获取到窗口信息；否则 None。
        """
        if sys.platform != "darwin":
            return None
        try:
            # 1) 直接查询 WeChat 的首个窗口（单行 AppleScript，避免多行解析问题）
            for app_name in ("WeChat", "微信"):
                cmd = (
                    'tell application "System Events" to tell (first application process whose name is "' + app_name + '") '
                    'to tell (first window) to get {name, position, size}'
                )
                res = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True)
                if res.returncode == 0:
                    out = res.stdout.strip()
                    # 常见返回格式：Title, {x, y}, {w, h} 或 Title, x, y, w, h
                    try:
                        normalized = out.replace("{", "").replace("}", "")
                        parts = [p.strip() for p in normalized.split(",")]
                        if len(parts) >= 5:
                            title = parts[0]
                            x, y, w, h = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                            if any(pat.lower() in title.lower() for pat in patterns):
                                return WindowInfo(
                                    handle=0,
                                    position=Rectangle(x=x, y=y, width=w, height=h),
                                    is_active=True,
                                    title=title,
                                )
                    except Exception:
                        pass

            # 2) 将微信应用置前后，查询前台应用窗口（同样使用单行 AppleScript）
            try:
                self._macos_activate_wechat()
                time.sleep(0.3)
            except Exception:
                pass

            # 同时返回前台应用进程名与窗口信息，便于确认是否为微信
            cmd_front = (
                'tell application "System Events" to '
                'tell (first application process whose frontmost is true) to '
                'get {name, name of (first window), position of (first window), size of (first window)}'
            )
            res2 = subprocess.run(["osascript", "-e", cmd_front], capture_output=True, text=True)
            if res2.returncode == 0:
                out2 = res2.stdout.strip()
                try:
                    normalized2 = out2.replace("{", "").replace("}", "")
                    parts2 = [p.strip() for p in normalized2.split(",")]
                    # 期望：procName, winTitle, x, y, w, h
                    if len(parts2) >= 6:
                        proc_name = parts2[0]
                        win_title = parts2[1]
                        x2, y2, w2, h2 = int(parts2[2]), int(parts2[3]), int(parts2[4]), int(parts2[5])
                        # 如果前台应用是微信，则直接返回，不再要求窗口标题匹配
                        if proc_name in ("WeChat", "微信") or any(pat.lower() in win_title.lower() for pat in patterns):
                            return WindowInfo(
                                handle=0,
                                position=Rectangle(x=x2, y=y2, width=w2, height=h2),
                                is_active=True,
                                title=win_title,
                            )
                except Exception:
                    pass
            return None
        except Exception as e:
            self.logger.debug("macOS AppleScript fallback failed: %s", e)
            return None

    def _macos_activate_wechat(self) -> bool:
        """
        macOS 专用：通过 AppleScript 激活 WeChat/微信 应用至前台。

        当 pygetwindow 激活失败时使用该回退，使窗口成为前台，
        有助于后续截图与滚动操作。

        Returns:
            True 表示已成功请求激活；False 表示失败或不支持。
        """
        if sys.platform != "darwin":
            return False
        try:
            # 尝试直接激活 WeChat 应用
            script_activate = r'''
                try
                    tell application "WeChat" to activate
                on error
                    tell application "System Events" to set frontmost of (first application process whose name is "WeChat") to true
                end try
            '''
            res = subprocess.run(["osascript", "-e", script_activate], capture_output=True, text=True)
            if res.returncode == 0:
                return True
            # 尝试中文名
            script_activate_cn = r'''
                try
                    tell application "微信" to activate
                on error
                    tell application "System Events" to set frontmost of (first application process whose name is "微信") to true
                end try
            '''
            res2 = subprocess.run(["osascript", "-e", script_activate_cn], capture_output=True, text=True)
            return res2.returncode == 0
        except Exception as e:
            self.logger.debug("macOS activate via AppleScript failed: %s", e)
            return False
