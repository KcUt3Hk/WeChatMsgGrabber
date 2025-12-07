"""
高级滚动控制器 - 实现微信聊天界面的自动化操作流程
支持渐进式滑动、惯性效果、位置监控和智能终止条件检测
"""
import time
import random
import logging
from typing import Optional, Tuple, List, Dict, Any
import pyautogui
from PIL import Image
import numpy as np

from models.data_models import WindowInfo, Rectangle
from services.auto_scroll_controller import AutoScrollController
from services.image_preprocessor import ImagePreprocessor


class AdvancedScrollController(AutoScrollController):
    """高级滚动控制器，支持渐进式滑动、惯性效果和智能终止检测"""
    
    def __init__(self, 
                 scroll_speed: int = 2, 
                 scroll_delay: float = 1.0,
                 scroll_distance_range: Tuple[int, int] = (200, 300),
                 scroll_interval_range: Tuple[float, float] = (0.3, 0.5),
                 inertial_effect: bool = True,
                 enable_watchdog: Optional[bool] = None,
                 watchdog_interval: float = 5.0):
        """
        初始化高级滚动控制器
        
        Args:
            scroll_speed: 基础滚动速度 (1-10)
            scroll_delay: 滚动延迟时间
            scroll_distance_range: 每次滑动距离范围 (像素)
            scroll_interval_range: 滑动间隔时间范围 (秒)
            inertial_effect: 是否启用滑动惯性效果
            enable_watchdog: 是否启用看门狗线程（默认通过环境变量控制）
            watchdog_interval: 看门狗心跳检查间隔（秒）
        """
        # 传递看门狗配置到父类，父类将基于环境变量或参数决定是否开启
        super().__init__(scroll_speed, scroll_delay, enable_macos_fallback=None, enable_watchdog=enable_watchdog, watchdog_interval=watchdog_interval)
        self.scroll_distance_range = scroll_distance_range
        self.scroll_interval_range = scroll_interval_range
        self.inertial_effect = inertial_effect
        self.logger = logging.getLogger(__name__)
        
        # 初始化图像预处理器
        self.pre = ImagePreprocessor()
        
        # 滚动状态跟踪
        self.scroll_history: List[Dict[str, Any]] = []
        self.current_position: Optional[Tuple[int, int]] = None
        self.start_time: Optional[float] = None
        
        # 配置pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1

    def progressive_scroll(self, 
                         direction: str = "up", 
                         max_scrolls: int = 50,
                         target_content: Optional[str] = None,
                         stop_at_edges: bool = True,
                         max_duration: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        执行渐进式滚动操作
        
        Args:
            direction: 滚动方向 ("up" 或 "down")
            max_scrolls: 最大滚动次数
            target_content: 目标内容关键词，检测到则停止
            stop_at_edges: 是否在到达边缘时停止
            max_duration: 最大运行时长（秒），达到后触发超时告警并停止
            
        Returns:
            滚动过程中捕获的消息和状态信息列表
        """
        results = []
        self.scroll_history = []
        self.start_time = time.time()
        # 如启用看门狗则启动后台心跳线程
        self.start_watchdog()
        
        # 定位初始位置
        if not self._locate_initial_position():
            self.logger.error("无法定位初始滚动位置")
            return results
        
        scroll_count = 0
        consecutive_no_change = 0
        
        while scroll_count < max_scrolls:
            scroll_count += 1
            # 心跳日志与资源监控
            self._heartbeat_log(scroll_count)
            # 可选的超时检测
            if max_duration is not None and (time.time() - self.start_time) > max_duration:
                self.logger.warning(f"达到最大运行时长 {max_duration}s，停止滚动")
                break
            # 滚动前确保窗口就绪
            self.ensure_window_ready(retries=1, delay=0.2)
            
            # 记录当前状态
            current_state = self._capture_scroll_state(scroll_count)
            
            # 检查终止条件（依据方向进行边缘判断）
            # 函数级注释：
            # - 当 direction="up" 时，边缘检测使用 is_at_top；
            # - 当 direction="down" 时，边缘检测使用 is_at_bottom；
            # - 这样在 CLI 从顶部开始向下扫描的场景下，不会因为“已在顶部”而误触发终止。
            if self._check_stop_conditions(current_state, target_content, stop_at_edges, direction):
                self.logger.info(f"满足终止条件，停止滚动 (第{scroll_count}次滚动)")
                break
            
            # 执行渐进式滚动
            scroll_success = self._execute_progressive_scroll(direction, scroll_count)
            if not scroll_success:
                self.logger.warning(f"第{scroll_count}次滚动失败，尝试窗口重试并再次滚动")
                # 尝试窗口重试
                if self.ensure_window_ready(retries=2, delay=0.3):
                    # 再次尝试一次滚动
                    if not self._execute_progressive_scroll(direction, scroll_count):
                        self.logger.warning(f"第{scroll_count}次滚动二次尝试失败")
                        break
                else:
                    break
            
            # 添加随机延迟
            delay = random.uniform(*self.scroll_interval_range)
            time.sleep(delay)

            # 偶发微暂停：模拟人为停顿，降低固定节律风险
            try:
                if random.random() < 0.12:  # 约每8-9次触发一次
                    extra_pause = random.uniform(1.2, 2.6)
                    self.logger.debug(f"微暂停 {extra_pause:.2f}s 以降低节律")
                    time.sleep(extra_pause)
            except Exception:
                pass
            
            # 更新状态
            results.append(current_state)
            
            # 检查内容变化
            if len(self.scroll_history) >= 2:
                last_state = self.scroll_history[-2]
                if self._compare_content(last_state["screenshot"], current_state["screenshot"]):
                    consecutive_no_change += 1
                    if consecutive_no_change >= 3:
                        self.logger.info("连续3次滚动内容无变化，停止滚动")
                        break
                else:
                    consecutive_no_change = 0

            # 内存管理：仅保留最近若干次滚动的截图，释放历史截图以避免长时间滚动出现内存压力
            # 函数级注释：
            # - 该策略避免在 max_scrolls 较大（例如 1000+）时占用过多内存；
            # - 保留最近 3 次以保障内容比较（last vs current），并兼容后续扩展；
            # - 同时清理截图缓存，减少驻留内存对象。
            self._prune_history_images(keep_last=3)
            self.clear_screenshot_cache()
        
        # 停止看门狗
        self.stop_watchdog()
        return results

    def set_spm_range(self, spm_min: int, spm_max: int) -> None:
        """设置滚动速率的每分钟区间（min,max），委托给基础控制器。"""
        try:
            super().set_spm_range(spm_min, spm_max)
        except Exception:
            pass

    def _locate_initial_position(self) -> bool:
        """定位初始滚动位置"""
        try:
            # 获取聊天区域边界
            chat_area = self.get_chat_area_bounds()
            if not chat_area:
                return False
            
            # 计算初始滚动位置（聊天区域中心）
            self.current_position = (
                chat_area.x + chat_area.width // 2,
                chat_area.y + chat_area.height // 2
            )
            
            self.logger.info(f"初始滚动位置: {self.current_position}")
            return True
            
        except Exception as e:
            self.logger.error(f"定位初始位置失败: {e}")
            return False

    def _capture_scroll_state(self, scroll_count: int) -> Dict[str, Any]:
        """捕获当前滚动状态"""
        state = {
            "scroll_count": scroll_count,
            "timestamp": time.time(),
            "position": self.current_position,
            # 为降低内存占用，对截图进行可选降采样（保持足够的 OCR 与比较质量）
            # 函数级注释：
            # - 原始截图可能为高分辨率，长时间运行会导致内存压力；
            # - 通过 _maybe_downscale_image 限制最大宽度来降低内存；
            # - 若 capture 失败则保持 None，后续流程具备容错。
            "screenshot": self._maybe_downscale_image(self.capture_current_view(), max_width=1400),
            "window_info": self.current_window,
            "scroll_speed": self.scroll_speed,
            "scroll_delay": self.scroll_delay
        }
        
        # 提取当前可视内容
        if state["screenshot"]:
            try:
                # 使用OCR提取当前内容
                from services.ocr_processor import OCRProcessor
                from services.message_parser import MessageParser
                
                ocr = OCRProcessor()
                parser = MessageParser()
                
                if not ocr.is_engine_ready():
                    ocr.initialize_engine()
                
                # 预处理图像
                optimized = self.optimize_screenshot_quality(state["screenshot"])
                preprocessed = self.pre.preprocess_for_ocr(optimized)
                
                # 提取文本区域
                text_regions = ocr.extract_text_regions(preprocessed)
                messages = parser.parse(text_regions)
                
                state["messages"] = messages
                state["message_count"] = len(messages)
                state["content_summary"] = self._summarize_content(messages)
                
            except Exception as e:
                self.logger.warning(f"内容提取失败: {e}")
                state["messages"] = []
                state["message_count"] = 0
                state["content_summary"] = ""
        
        self.scroll_history.append(state)
        return state

    def _execute_progressive_scroll(self, direction: str, scroll_count: int) -> bool:
        """执行渐进式滚动"""
        try:
            # 计算滚动距离（渐进式调整）
            base_distance = random.randint(*self.scroll_distance_range)
            
            # 根据滚动次数调整距离（避免固定模式）
            if scroll_count % 5 == 0:
                # 每5次滚动进行一次较大距离滚动
                scroll_distance = base_distance * 1.5
            else:
                scroll_distance = base_distance
            
            # 添加惯性效果
            if self.inertial_effect:
                scroll_distance = self._apply_inertial_effect(scroll_distance, direction)
            
            # 执行滚动
            scroll_amount = int(scroll_distance * self.scroll_speed / 2)
            # 执行前进行节流
            self.throttle_if_needed()
            # 若窗口失效则进行快速重试
            if not self._override_chat_area and (not self.current_window or not self.is_window_valid()):
                self.ensure_window_ready(retries=1, delay=0.2)
            
            if direction.lower() == "up":
                pyautogui.scroll(scroll_amount, x=self.current_position[0], y=self.current_position[1])
            else:
                pyautogui.scroll(-scroll_amount, x=self.current_position[0], y=self.current_position[1])
            
            self.logger.debug(f"第{scroll_count}次滚动: {direction} {scroll_amount}像素")
            
            # 更新位置估计（模拟真实滑动效果）
            self._update_position_estimate(direction, scroll_distance)
            
            return True
            
        except Exception as e:
            self.logger.error(f"滚动执行失败: {e}")
            return False

    def _heartbeat_log(self, scroll_count: int) -> None:
        """
        输出心跳日志，包括滚动计数与可选资源占用（CPU/内存）信息。

        函数级注释：
        - 使用 psutil（若可用）获取系统 CPU 使用率与当前进程内存占用；
        - 若不可用则仅输出基础心跳信息；
        - 该方法在 progressive_scroll 循环中调用，用于长时运行可观测性增强。
        """
        cpu_info = "N/A"
        mem_info = "N/A"
        try:
            import psutil  # 类型: 忽略依赖，若不存在则走 except
            cpu_info = f"{psutil.cpu_percent(interval=None)}%"
            process = psutil.Process()
            mem = process.memory_info()
            mem_info = f"RSS={mem.rss/1024/1024:.1f}MB VMS={mem.vms/1024/1024:.1f}MB"
        except Exception:
            pass
        self.logger.debug(f"心跳: 第{scroll_count}次滚动 | CPU={cpu_info} | MEM={mem_info}")

    def _prune_history_images(self, keep_last: int = 2) -> None:
        """裁剪滚动历史中的截图，仅保留最近的若干次，释放旧截图以降低内存占用。

        函数级注释：
        - keep_last 指定需要保留的最近条目数（建议 2-3，用于相邻内容比较与容错）；
        - 对更早的历史条目，将其 screenshot 字段置为 None，以提示 GC 释放图像内存；
        - 该方法不会影响其他统计字段（如 message_count、content_summary）。
        """
        try:
            if keep_last <= 0:
                keep_last = 1
            # 仅当历史长度超过保留数量时进行裁剪
            if len(self.scroll_history) > keep_last:
                cutoff = len(self.scroll_history) - keep_last
                for i in range(cutoff):
                    state = self.scroll_history[i]
                    if state.get("screenshot") is not None:
                        state["screenshot"] = None
        except Exception as e:
            # 内存裁剪属于增强策略，失败不影响主流程
            self.logger.debug(f"历史截图裁剪异常：{e}")

    def _maybe_downscale_image(self, image: Optional[Image.Image], max_width: int = 1200) -> Optional[Image.Image]:
        """在不显著影响 OCR 的情况下，对截图进行可选降采样以减小内存占用。

        函数级注释：
        - 若 image 为 None 或宽度不超过 max_width，则原样返回；
        - 使用按比例缩放保持纵横比，避免引入几何失真；
        - 缩放后的图像仍可用于内容比较与 OCR 预处理。"""
        try:
            if image is None:
                return None
            w, h = image.size
            if w <= max_width:
                return image
            scale = max(0.1, float(max_width) / float(w))
            new_w = int(w * scale)
            new_h = max(1, int(h * scale))
            return image.resize((new_w, new_h))
        except Exception:
            # 若缩放失败，返回原始图像以保证流程不中断
            return image

    def _apply_inertial_effect(self, base_distance: int, direction: str) -> int:
        """应用滑动惯性效果"""
        if len(self.scroll_history) < 2:
            return base_distance
        
        # 计算最近几次滚动的平均速度
        recent_distances = []
        for i in range(min(3, len(self.scroll_history))):
            state = self.scroll_history[-(i+1)]
            # 这里可以基于实际滚动效果调整
            recent_distances.append(base_distance)
        
        avg_distance = sum(recent_distances) / len(recent_distances)
        
        # 添加随机波动模拟惯性
        inertia_factor = random.uniform(0.8, 1.2)
        adjusted_distance = int(avg_distance * inertia_factor)
        
        return max(self.scroll_distance_range[0], 
                  min(adjusted_distance, self.scroll_distance_range[1] * 2))

    def _update_position_estimate(self, direction: str, distance: int):
        """更新位置估计（模拟真实滑动后的位置变化）"""
        if not self.current_position:
            return
        
        # 简单的位置估计模型
        x, y = self.current_position
        
        if direction.lower() == "up":
            # 向上滚动，位置向下移动
            y += distance // 2
        else:
            # 向下滚动，位置向上移动
            y -= distance // 2
        
        # 确保位置在聊天区域内
        chat_area = self.get_chat_area_bounds()
        if chat_area:
            y = max(chat_area.y + 50, min(y, chat_area.y + chat_area.height - 50))
            x = max(chat_area.x + 50, min(x, chat_area.x + chat_area.width - 50))
        
        self.current_position = (x, y)

    def _check_stop_conditions(self, 
                             current_state: Dict[str, Any], 
                             target_content: Optional[str],
                             stop_at_edges: bool,
                             direction: str = "up") -> bool:
        """
        检查终止条件。

        函数级注释：
        - 如果提供了 target_content，则在当前摘要包含该内容时终止；
        - 当 stop_at_edges 为 True 时，根据滚动方向进行边缘检测：
          * direction="up" 使用 is_at_top()
          * direction="down" 使用 is_at_bottom()
        - 另外检测用户通过将鼠标移动到屏幕角落的方式进行的 FAILSAFE 中断。
        """
        # 检查目标内容
        if target_content and current_state.get("content_summary"):
            if target_content.lower() in current_state["content_summary"].lower():
                self.logger.info(f"检测到目标内容: {target_content}")
                return True
        
        # 检查是否到达边缘
        if stop_at_edges and self._is_at_edge(direction):
            self.logger.info("检测到到达聊天记录边缘")
            return True
        
        # 检查用户中断（通过pyautogui的FAILSAFE机制）
        try:
            # 检查鼠标是否移动到屏幕角落（用户中断）
            mouse_x, mouse_y = pyautogui.position()
            screen_width, screen_height = pyautogui.size()
            
            if (mouse_x <= 10 and mouse_y <= 10) or \
               (mouse_x >= screen_width - 10 and mouse_y <= 10) or \
               (mouse_x <= 10 and mouse_y >= screen_height - 10) or \
               (mouse_x >= screen_width - 10 and mouse_y >= screen_height - 10):
                self.logger.info("检测到用户中断（鼠标移动到屏幕角落）")
                return True
                
        except:
            pass
        
        return False

    def _is_at_edge(self, direction: str) -> bool:
        """
        检查是否到达聊天记录边缘（随滚动方向）。

        函数级注释：
        - 对于向上滚动，边缘即顶部，使用 is_at_top() 判断；
        - 对于向下滚动，边缘即底部，使用 is_at_bottom() 判断；
        - 对于未知方向，返回 False，不进行边缘终止。
        """
        try:
            dirn = (direction or "").lower()
            if dirn == "up":
                return self.is_at_top()
            elif dirn == "down":
                return self.is_at_bottom()
            else:
                return False
        except Exception as e:
            self.logger.debug(f"边缘检测异常（direction={direction}）：{e}")
            return False

    def _compare_content(self, img1: Image.Image, img2: Image.Image) -> bool:
        """比较两个截图的内容相似度"""
        try:
            return self._compare_screenshots(img1, img2, threshold=0.98)
        except:
            return False

    def _summarize_content(self, messages: List[Any]) -> str:
        """汇总消息内容"""
        if not messages:
            return ""
        
        # 提取前几条消息的内容
        content_lines = []
        for msg in messages[:5]:  # 只取前5条消息
            if hasattr(msg, 'content'):
                content_lines.append(str(msg.content))
            elif isinstance(msg, dict) and 'content' in msg:
                content_lines.append(str(msg['content']))
        
        return " ".join(content_lines)

    def get_scroll_statistics(self) -> Dict[str, Any]:
        """获取滚动统计信息"""
        if not self.scroll_history:
            return {}
        
        total_messages = sum(state.get("message_count", 0) for state in self.scroll_history)
        end_ts = time.time()
        start_ts = self.start_time or end_ts
        total_time = max(0.0, end_ts - start_ts)
        per_minute = (len(self.scroll_history) / (total_time / 60.0)) if total_time > 0 else 0.0
        
        return {
            "start_time": start_ts,
            "end_time": end_ts,
            "total_scrolls": len(self.scroll_history),
            "total_messages": total_messages,
            "total_time": total_time,
            "avg_messages_per_scroll": total_messages / len(self.scroll_history) if self.scroll_history else 0,
            "scrolls_per_minute": per_minute,
            "scroll_speed": self.scroll_speed,
            "scroll_delay": self.scroll_delay
        }

    def reset_scroll_state(self):
        """重置滚动状态"""
        self.scroll_history = []
        self.current_position = None
        self.start_time = None
