"""
Main controller orchestrating window automation, OCR, and message parsing.
"""
import logging
import time
from typing import List, Optional

from models.data_models import Message, MessageType
from datetime import datetime
import uuid
from services.auto_scroll_controller import AutoScrollController
from services.advanced_scroll_controller import AdvancedScrollController
from services.image_preprocessor import ImagePreprocessor
from services.ocr_processor import OCRProcessor
from services.message_parser import MessageParser
from services.config_manager import ConfigManager
from services.storage_manager import StorageManager
from models.config import AppConfig, OutputConfig
from ui.progress import ProgressReporter


class MainController:
    """Coordinates the overall extraction workflow."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.scroll = AutoScrollController()
        self.pre = ImagePreprocessor()
        self.ocr = OCRProcessor()
        self.parser = MessageParser()
        self.last_scroll_stats: dict | None = None

    def run_once(self) -> List[Message]:
        """Run a single extraction cycle on current chat view.

        Returns:
            List of parsed Message objects.
        """
        messages: List[Message] = []

        # 当提供了聊天区域覆盖时，直接跳过窗口定位与激活流程，避免在受限环境下阻塞截图
        if self.scroll.has_chat_area_override():
            window = None
            self.logger.debug("已提供聊天区域覆盖，跳过窗口定位与激活。")
        else:
            window = self.scroll.locate_wechat_window()
            if not window:
                self.logger.warning("WeChat窗口未找到，且未提供聊天区域覆盖，跳过本次提取。")
                return messages

        # 仅当依赖窗口API时才尝试激活窗口；覆盖坐标场景直接截图
        if window:
            if not self.scroll.activate_window():
                self.logger.warning("无法激活窗口，跳过本次提取。")
                return messages

        img = self.scroll.capture_current_view()
        if not img:
            self.logger.warning("截图失败，跳过本次提取。")
            return messages

        optimized = self.scroll.optimize_screenshot_quality(img)
        preprocessed = self.pre.preprocess_for_ocr(optimized)

        # Ensure OCR engine is ready
        if not self.ocr.is_engine_ready():
            if not self.ocr.initialize_engine():
                self.logger.warning("OCR引擎初始化失败。")
                return messages

        # Region-based OCR for better mapping to messages
        region_results = self.ocr.detect_and_process_regions(preprocessed)
        text_regions = [tr for tr, _ in region_results]
        self.logger.info(f"区域识别文本区域数量：{len(text_regions)}")

        # Fallback: if region-based detection produced no regions, try full-image OCR on preprocessed image
        if not text_regions:
            self.logger.info("区域识别未检测到文本，尝试对整张截图进行OCR以回退。")
            try:
                full_image_regions = self.ocr.extract_text_regions(preprocessed)
                self.logger.info(f"整图OCR（预处理后）文本区域数量：{len(full_image_regions)}")
                text_regions = full_image_regions
            except Exception as e:
                self.logger.warning(f"整图OCR回退失败：{e}")

        # Second fallback: try OCR on optimized (raw) screenshot if still empty
        if not text_regions:
            self.logger.info("整图OCR（预处理后）仍为空，尝试对优化后的原始截图进行OCR回退。")
            try:
                raw_regions = self.ocr.extract_text_regions(optimized, preprocess=False)
                self.logger.info(f"整图OCR（原始优化）文本区域数量：{len(raw_regions)}")
                text_regions = raw_regions
            except Exception as e:
                self.logger.warning(f"整图OCR（原始优化）回退失败：{e}")

        # Parse text regions into messages
        messages = self.parser.parse(text_regions)

        return messages

    def run_with_retry(self, max_attempts: int = 3, delay_seconds: float = 0.5) -> List[Message]:
        """Run extraction with retry on failures or empty results.

        Attempts up to max_attempts times, waiting delay_seconds between attempts.
        Returns the first non-empty list of messages, or empty list if all attempts fail.
        """
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                messages = self.run_once()
                if messages:
                    if attempt > 1:
                        self.logger.info(f"提取在第{attempt}次尝试成功，得到{len(messages)}条消息。")
                    return messages
                else:
                    self.logger.debug(f"第{attempt}次尝试未获取到消息（空结果）。")
            except Exception as e:
                last_error = e
                self.logger.error(f"第{attempt}次提取异常：{e}")
            if attempt < max_attempts:
                time.sleep(max(0.0, delay_seconds))
        if last_error:
            self.logger.warning(f"多次尝试仍失败，最后错误：{last_error}")
        return []

    def run_with_progress(self, reporter: ProgressReporter, max_attempts: int = 3, delay_seconds: float = 0.5) -> List[Message]:
        """Run extraction with progress reporting for CLI UI."""
        reporter.start()
        # Provide a small pre-focus delay so user can bring WeChat to foreground
        try:
            self.logger.info("开始前等待1.5秒以便前置微信窗口聚焦，请确保微信聊天窗口处于前台。")
            time.sleep(1.5)
        except Exception:
            pass
        messages: List[Message] = []
        for attempt in range(1, max_attempts + 1):
            reporter.update(status=f"尝试第{attempt}次", attempts_delta=1)
            try:
                batch = self.run_once()
                if batch:
                    messages.extend(batch)
                    reporter.update(messages_parsed_delta=len(batch), status="解析成功")
                    reporter.finish(success=True)
                    return messages
                else:
                    self.logger.debug(f"第{attempt}次尝试未获取到消息（空结果）。")
                    reporter.update(status="无消息，准备重试")
            except Exception as e:
                self.logger.error(f"第{attempt}次提取异常：{e}")
                reporter.update(status="异常发生", error=str(e))
            if attempt < max_attempts:
                time.sleep(max(0.0, delay_seconds))
        reporter.finish(success=False)
        return messages

    def scan_chat_history(
        self,
        max_messages: int = 1000,
        enable_deduplication: bool = True,
        max_batches: Optional[int] = None,
        direction: str = "up",
        reporter: Optional[ProgressReporter] = None,
    ) -> List[Message]:
        """
        扫描聊天历史记录，支持方向控制、批次限制与进度上报，并保持向后兼容。

        参数说明：
        - max_messages: 目标最大消息数量（向后兼容旧接口）
        - enable_deduplication: 是否对解析结果进行批内去重（默认开启）
        - max_batches: 最大批次数（每个批次一次截图+解析+滚动），可用于测试或受限环境
        - direction: 滚动方向，"up" 表示向上，"down" 表示向下（默认向上）
        - reporter: 进度上报器，可为空；若提供则在每批次更新解析进度

        返回值：
        - 已解析的消息列表（可能为空）
        """
        self.logger.info(
            f"开始扫描聊天历史记录（方向={direction}，max_messages={max_messages}，max_batches={max_batches}，dedup={enable_deduplication}）"
        )

        messages: List[Message] = []
        seen_keys = set()
        consecutive_misses = 0
        max_consecutive_misses = 3
        batches_done = 0

        # 方向初始化：默认向上滚动，先到顶部；向下滚动则直接从当前位置开始
        try:
            if direction.lower() == "up":
                self.logger.info("初始化到顶部以便按时间顺序扫描……")
                self.scroll_to_top()
            else:
                self.logger.info("按请求方向为向下，不做顶部初始化。")
        except Exception as e:
            self.logger.warning(f"初始化滚动方向失败：{e}")

        # 心跳与稳定性统计
        start_ts = time.time()
        last_heartbeat_ts = start_ts

        while len(messages) < max_messages:
            # 若指定了批次限制，达到后退出
            if max_batches is not None and batches_done >= max_batches:
                self.logger.info(f"达到最大批次限制：{max_batches}，停止扫描。")
                break

            # 捕获聊天区域截图（若失败尝试一次窗口重定位/激活再重试）
            screenshot = self.scroll.capture_current_view()
            if not screenshot:
                self.logger.warning("首次截图失败，尝试重定位/激活窗口后重试……")
                try:
                    window = self.scroll.locate_wechat_window()
                    if window:
                        self.scroll.activate_window()
                        time.sleep(0.3)
                        screenshot = self.scroll.capture_current_view()
                except Exception as e:
                    self.logger.error(f"重试截图时异常：{e}")
            if not screenshot:
                self.logger.warning("无法捕获聊天区域截图，结束扫描。")
                break

            optimized = self.scroll.optimize_screenshot_quality(screenshot)
            preprocessed = self.pre.preprocess_for_ocr(optimized)

            # 确保OCR引擎就绪
            if not self.ocr.is_engine_ready():
                if not self.ocr.initialize_engine():
                    self.logger.warning("OCR引擎初始化失败，结束扫描。")
                    break

            # 区域识别与解析
            try:
                region_results = self.ocr.detect_and_process_regions(preprocessed)
                text_regions = [tr for tr, _ in region_results]
            except Exception as e:
                self.logger.error(f"区域识别失败：{e}")
                text_regions = []

            # Fallback: 整图 OCR（预处理后）
            if not text_regions:
                try:
                    text_regions = self.ocr.extract_text_regions(preprocessed)
                except Exception as e:
                    self.logger.warning(f"整图OCR回退失败：{e}")

            # Second fallback: 整图 OCR（原始优化，无预处理）
            if not text_regions:
                try:
                    text_regions = self.ocr.extract_text_regions(optimized, preprocess=False)
                except Exception as e:
                    self.logger.warning(f"整图OCR（原始优化）回退失败：{e}")

            # 解析文本区域为消息
            try:
                new_messages = self.parser.parse(text_regions)
            except Exception as e:
                self.logger.error(f"消息解析失败：{e}")
                new_messages = []

            # 批次去重控制
            batch_messages: List[Message] = []
            if enable_deduplication:
                for m in new_messages:
                    key = m.stable_key()
                    if key not in seen_keys:
                        batch_messages.append(m)
                        seen_keys.add(key)
            else:
                batch_messages = list(new_messages)

            # 统计与日志
            batches_done += 1
            if batch_messages:
                messages.extend(batch_messages)
                self.logger.info(
                    f"第{batches_done}批提取到 {len(batch_messages)} 条新消息，总计: {len(messages)}"
                )
                consecutive_misses = 0
            else:
                consecutive_misses += 1
                self.logger.info(f"第{batches_done}批未找到新消息，连续失败次数: {consecutive_misses}")
                if consecutive_misses >= max_consecutive_misses:
                    self.logger.info("连续失败次数过多，停止扫描。")
                    break

            # 命中率用于自适应滚动
            hit_rate = len(batch_messages) / len(new_messages) if new_messages else 0.0

            # 截图相似度用于边缘检测
            prev_screenshot = screenshot

            # 方向滚动（优先按窗口高度）
            success = self.scroll.scroll_by_window_height(direction.lower())
            if not success:
                self.logger.warning("按窗口高度滚动失败，回退到默认滚动方式。")
                self.scroll.start_scrolling(direction.lower())

            # 适当休眠（带抖动，提升稳定性）
            jitter = 0.03
            time.sleep(max(0.0, self.scroll.scroll_delay + jitter))

            current_screenshot = self.scroll.capture_current_view()
            if prev_screenshot and current_screenshot:
                similar = self.scroll._compare_screenshots(
                    prev_screenshot, current_screenshot, threshold=0.95
                )
                if similar:
                    # 非常相似：可能到达边缘
                    self.logger.info("检测到内容高度相似，可能已到达边缘，尝试再滚动一次确认。")
                    confirm = self.scroll.scroll_by_window_height(direction.lower())
                    time.sleep(max(0.0, self.scroll.scroll_delay))
                    confirm_screenshot = self.scroll.capture_current_view()
                    if confirm and confirm_screenshot:
                        similar2 = self.scroll._compare_screenshots(
                            current_screenshot, confirm_screenshot, threshold=0.97
                        )
                        if similar2:
                            self.logger.info("确认到达聊天记录边缘，停止扫描。")
                            break

            # 自适应滚动速度
            if hit_rate < 0.3:  # 低命中率，滚动更快
                self.scroll.scroll_speed = min(10, self.scroll.scroll_speed + 1)
                self.scroll.scroll_delay = max(0.2, self.scroll.scroll_delay - 0.1)
            elif hit_rate > 0.7:  # 高命中率，滚动更慢以提高精度
                self.scroll.scroll_speed = max(1, self.scroll.scroll_speed - 1)
                self.scroll.scroll_delay = min(2.0, self.scroll.scroll_delay + 0.1)

            # 进度上报与心跳日志（每5秒）
            if reporter:
                reporter.update(
                    status=f"扫描中：第{batches_done}批，命中率 {hit_rate:.2f}",
                    messages_parsed_delta=len(batch_messages),
                )
            now_ts = time.time()
            if now_ts - last_heartbeat_ts >= 5.0:
                self.logger.info(
                    f"心跳：已运行 {(now_ts - start_ts):.1f}s，累计批次 {batches_done}，累计消息 {len(messages)}，速度 {self.scroll.scroll_speed}，延迟 {self.scroll.scroll_delay:.2f}"
                )
                last_heartbeat_ts = now_ts

        self.scroll.stop_scrolling()
        return messages
    
    def scroll_to_top(self) -> None:
        """
        滑动到聊天记录顶部
        """
        self.logger.info("正在滑动到顶部...")
        
        # 先快速向上滑动几次确保到达顶部
        for i in range(5):
            self.scroll.start_scrolling("up")
            time.sleep(0.5)
        
        # 检查是否真正到达顶部
        max_checks = 10
        for i in range(max_checks):
            prev_screenshot = self.scroll.capture_current_view()
            self.scroll.start_scrolling("up")
            time.sleep(0.5)
            current_screenshot = self.scroll.capture_current_view()
            
            if prev_screenshot and current_screenshot:
                similarity = self.scroll._compare_screenshots(prev_screenshot, current_screenshot, threshold=0.98)
                if similarity:  # 截图几乎相同，说明已到达顶部
                    self.logger.info("已到达聊天记录顶部")
                    return
            
            time.sleep(0.5)
        
        self.logger.info("滑动到顶部完成")

    def _fill_message_times(self, messages: List[Message], direction: str = "up") -> None:
        """Post-process messages to fill in 'message_time' based on System timestamps.
        
        Logic:
        1. Sort messages in chronological order (Oldest -> Newest).
           - If direction='up' (scanning history), the captured list is [Newest...Oldest]. So reverse it.
           - If direction='down' (scanning new), the captured list is [Oldest...Newest]. Keep it.
           - Actually, let's rely on capture timestamp if available? 
             Capture timestamp for 'up' scan: Index 0 (Newest) has EARLIEST capture time? 
             Wait, if we scroll UP, we capture Newest first.
             So Index 0 is Newest. Index N is Oldest.
             So Index 0 was captured at T0. Index N captured at T1.
             So T0 < T1.
             So Capture Time: Index 0 (Oldest timestamp) -> Index N (Newest timestamp).
             BUT Semantic Time: Index 0 (Newest Msg) -> Index N (Oldest Msg).
             So Capture Time is INVERSE to Semantic Time for 'up' scan.
        
        2. Iterate Oldest -> Newest.
        3. Maintain current context date/time.
        4. If System msg with time found, update context.
        5. Assign context to subsequent messages.
        """
        if not messages:
            return

        # Determine processing order to be Old -> New
        # If direction is 'up' (default), messages are [Newest ... Oldest].
        # So we need to process in REVERSE order to go Old -> New.
        # If direction is 'down', messages are [Oldest ... Newest].
        
        # However, advanced_scan_chat_history might return them in capture order.
        # Let's assume the list `messages` is in Capture Order.
        # If direction='up': Capture Order = New -> Old.
        # If direction='down': Capture Order = Old -> New.
        
        ordered_indices = range(len(messages))
        if direction == "up":
            ordered_indices = range(len(messages) - 1, -1, -1)
        
        current_time = datetime.now()
        # Initial guess: Scan start time? Or just use Now.
        # Better: Scan backwards (New->Old) to find the FIRST system timestamp?
        # No, System timestamps appear ABOVE messages (Old side).
        # So we must traverse Old -> New.
        
        # We need a reference date. Usually Today.
        scan_date = datetime.now()
        current_context_time = scan_date
        
        # Traverse Old -> New
        for i in ordered_indices:
            msg = messages[i]
            if msg.message_type == MessageType.SYSTEM:
                # Try to parse
                parsed = MessageParser.parse_wechat_time(msg.content, scan_date)
                # If parsed time is different from reference (meaning it found a time), update context
                # Note: parse_wechat_time returns reference_date if failure.
                # But we might have "Yesterday 10:00".
                # To detect if it WAS parsed, we can check if it's different OR check content pattern again?
                # The parser logic already handles this.
                # But wait, if we pass scan_date, and it returns scan_date, we don't know if it parsed "Today Now" or failed.
                # But "System" messages usually contain time.
                # Let's assume if it's System, we update context.
                # But sometimes System msg is "You recalled a message".
                # We should only update if it looks like time.
                
                # Check if it looks like time (using the parser's internal helper would be nice, but it's private)
                # We'll just trust parse_wechat_time to return a reasonable time.
                # To be safe, let's only update if the content looks like time.
                # Re-implement simple check? Or make `_is_timestamp_line` public?
                # I'll rely on the fact that if it parses, it's good.
                # But we need to distinguish "Failed to parse" (returned ref date) from "Parsed Today".
                # We can check if content matches time patterns.
                
                is_time = False
                import re
                pats = [r"\d{1,2}:\d{2}", r"昨天", r"今天", r"星期", r"年.+月.+日"]
                if any(re.search(p, msg.content) for p in pats):
                    parsed = MessageParser.parse_wechat_time(msg.content, scan_date)
                    current_context_time = parsed
                    msg.message_time = current_context_time
            else:
                # Assign current context time
                msg.message_time = current_context_time

    def advanced_scan_chat_history(
        self,
        max_scrolls: int = 100,
        direction: str = "up",
        target_content: Optional[str] = None,
        stop_at_edges: bool = True,
        reporter: ProgressReporter | None = None,
        # 速率与滚动参数（可选，若未提供则使用默认值）
        scroll_speed: Optional[int] = None,
        scroll_delay: Optional[float] = None,
        scroll_distance_range: Optional[tuple] = None,
        scroll_interval_range: Optional[tuple] = None,
        max_scrolls_per_minute: Optional[int] = None,
        spm_range: Optional[tuple] = None,
    ) -> List[Message]:
        """
        高级聊天历史扫描 - 使用渐进式滑动和智能终止检测
        
        Args:
            max_scrolls: 最大滚动次数
            direction: 滚动方向 ("up" 或 "down")
            target_content: 目标内容关键词
            stop_at_edges: 是否在到达边缘时停止
            reporter: 进度报告器
            scroll_speed: 滚动速度（平台相关，可选覆盖）
            scroll_delay: 每次滚动后的延迟秒数（可选覆盖）
            scroll_distance_range: 每次滚动距离范围（像素，形如 (min,max)）
            scroll_interval_range: 渐进式滚动的时间间隔范围（秒，形如 (min,max)）
            max_scrolls_per_minute: 每分钟滚动上限（速率限制）
            
        Returns:
            解析得到的消息列表（去重后）
        """
        from typing import Optional
        
        messages: List[Message] = []
        seen_keys = set()

        # 初始化高级滚动控制器（允许 CLI/调用方覆盖滚动参数）
        advanced_scroll = AdvancedScrollController(
            scroll_speed=(scroll_speed if scroll_speed is not None else 2),
            scroll_delay=(scroll_delay if scroll_delay is not None else 1.0),
            scroll_distance_range=(scroll_distance_range if scroll_distance_range is not None else (200, 300)),
            scroll_interval_range=(scroll_interval_range if scroll_interval_range is not None else (0.3, 0.5)),
            inertial_effect=True
        )
        # 动态速率限制（若提供上限）
        try:
            if max_scrolls_per_minute is not None:
                advanced_scroll.set_rate_limits(scroll_delay=scroll_delay, scroll_speed=scroll_speed, max_scrolls_per_minute=max_scrolls_per_minute)
            # 若提供 spm 区间，优先生效
            if spm_range is not None and len(spm_range) == 2:
                mn, mx = spm_range
                advanced_scroll.set_spm_range(int(mn), int(mx))
        except Exception:
            pass

        # 覆盖坐标场景：跳过窗口定位与激活
        # 函数级注释：
        # - 当基础 AutoScrollController（self.scroll）已设置聊天区域覆盖时，
        #   需要将该覆盖坐标同步到高级滚动控制器 advanced_scroll，
        #   否则 advanced_scroll 在定位初始位置时会因缺少聊天区域而失败；
        # - 该同步仅复制 Rectangle 坐标信息，避免依赖窗口 API 的环境阻塞。
        if self.scroll.has_chat_area_override():
            try:
                rect = self.scroll.get_chat_area_bounds()
                if rect:
                    advanced_scroll.set_override_chat_area(rect)
                    self.logger.debug("已将聊天区域覆盖同步到高级滚动控制器：%s", rect)
            except Exception as sync_e:
                self.logger.debug("同步聊天区域覆盖到高级滚动控制器失败：%s", sync_e)
            window = None
            self.logger.debug("已提供聊天区域覆盖，跳过窗口定位与激活（高级扫描模式）。")
        else:
            window = advanced_scroll.locate_wechat_window()
            if not window:
                self.logger.warning("无法定位微信窗口，且未提供聊天区域覆盖，高级扫描终止。")
                return messages
            if window and not advanced_scroll.activate_window():
                self.logger.warning("无法激活微信窗口，高级扫描终止。")
                return messages

        if reporter:
            reporter.start()

        # 确保OCR引擎就绪
        if not self.ocr.is_engine_ready():
            if not self.ocr.initialize_engine():
                self.logger.warning("OCR引擎初始化失败，高级扫描终止。")
                if reporter:
                    reporter.finish(success=False)
                return messages

        # 执行渐进式滚动扫描
        try:
            scroll_results = advanced_scroll.progressive_scroll(
                direction=direction,
                max_scrolls=max_scrolls,
                target_content=target_content,
                stop_at_edges=stop_at_edges
            )

            # 处理扫描结果
            for result in scroll_results:
                if "messages" in result and result["messages"]:
                    for msg in result["messages"]:
                        # 转换为标准消息格式并去重
                        if isinstance(msg, dict):
                            # 从字典创建Message对象（统一类型与必填字段）
                            # 函数级注释：
                            # - message_type 支持字符串或枚举，统一转换为 MessageType；
                            # - timestamp 支持 datetime 或 ISO 字符串，默认使用当前时间；
                            # - id 缺失时自动生成 UUID；
                            # - confidence_score/raw_ocr_text 缺失时给出合理默认，保证 Message 构造完整。
                            mtype_raw = msg.get('message_type', MessageType.TEXT)
                            if isinstance(mtype_raw, MessageType):
                                mtype = mtype_raw
                            else:
                                try:
                                    mtype = MessageType(mtype_raw)
                                except Exception:
                                    mtype = MessageType.TEXT

                            ts_raw = msg.get('timestamp')
                            if isinstance(ts_raw, datetime):
                                ts = ts_raw
                            elif isinstance(ts_raw, str):
                                try:
                                    ts = datetime.fromisoformat(ts_raw)
                                except Exception:
                                    ts = datetime.now()
                            else:
                                ts = datetime.now()

                            message_obj = Message(
                                id=msg.get('id') or str(uuid.uuid4()),
                                sender=msg.get('sender', '未知'),
                                content=msg.get('content', ''),
                                message_type=mtype,
                                timestamp=ts,
                                confidence_score=float(msg.get('confidence_score', 0.0)),
                                raw_ocr_text=msg.get('raw_ocr_text', msg.get('content', ''))
                            )
                        else:
                            # 假设已经是Message对象
                            message_obj = msg
                        
                        key = message_obj.stable_key()
                        if key not in seen_keys:
                            seen_keys.add(key)
                            messages.append(message_obj)

                # 更新进度
                if reporter:
                    reporter.update(
                        status=f"扫描中: 已处理 {len(messages)} 条消息",
                        messages_parsed_delta=len(result.get("messages", []))
                    )

            self.logger.info(f"高级扫描完成，共提取 {len(messages)} 条唯一消息")
            
            # Post-process to fill message times
            self._fill_message_times(messages, direction=direction)
            
            try:
                self.last_scroll_stats = advanced_scroll.get_scroll_statistics()
            except Exception:
                self.last_scroll_stats = None

        except KeyboardInterrupt:
            self.logger.info("用户中断高级扫描")
        except Exception as e:
            self.logger.error(f"高级扫描失败: {e}")

        if reporter:
            reporter.finish(success=bool(messages))

        return messages

    def get_last_scroll_stats(self) -> dict | None:
        return self.last_scroll_stats

    def scan_multiple_chats(
        self,
        chat_titles: List[str],
        per_chat_max_messages: int = 500,
        direction: str = "up",
        deduplicate_global: bool = True,
        formats: Optional[List[str]] = None,
        filename_prefix: Optional[str] = None,
        output_dir: Optional[str] = None,
        reporter: Optional[ProgressReporter] = None,
    ) -> List[Message]:
        """
        批量扫描指定会话标题列表，并进行聚合导出。

        函数级注释：
        - 通过侧边栏 OCR 模糊匹配点击会话（AutoScrollController.click_session_by_text），支持滚动尝试；
        - 每个会话在扫描结果中插入一条系统分隔消息（MessageType.SYSTEM），便于后续人工或程序分割；
        - 支持全局去重（基于 Message.stable_key），避免跨会话重复内容；
        - 保存阶段支持多格式导出（StorageManager.save_messages_multiple），若未指定 formats 则回退到配置；
        - 该方法假设微信窗口可见且侧边栏与聊天区域布局稳定；如已设置聊天区域覆盖（override），仍可运行但点击会话可能依赖窗口 API。

        参数：
        - chat_titles: 需要批量扫描的会话标题列表（支持模糊匹配，如“产品群”可匹配“产品讨论群(1)”）；
        - per_chat_max_messages: 每个会话最多提取的消息条数；
        - direction: 每个会话内的滚动方向（"up"/"down"）；
        - deduplicate_global: 是否对聚合后的所有消息进行全局去重；
        - formats: 保存的格式列表，例如 ["json","csv"]；None 时使用配置中的 formats 或单一 format；
        - filename_prefix: 导出文件名前缀；None 时使用批量时间戳前缀；
        - reporter: 进度上报器，可为 None。

        返回：
        - 聚合后的消息列表（可能为空）。
        """
        aggregated: List[Message] = []
        seen_keys = set()

        # 初始化配置与存储
        cfg_mgr = ConfigManager()
        app_cfg: AppConfig = cfg_mgr.get_config()
        # 若指定了输出目录，则覆盖当前配置的输出目录
        if output_dir:
            try:
                app_cfg.output.directory = output_dir
            except Exception:
                self.logger.debug("覆盖输出目录失败，使用默认配置目录。")

        # 确保窗口与OCR就绪
        try:
            self.scroll.ensure_window_ready()
        except Exception:
            pass
        if not self.ocr.is_engine_ready():
            if not self.ocr.initialize_engine():
                self.logger.warning("OCR引擎初始化失败，批量扫描终止。")
                return aggregated

        if reporter:
            reporter.start()

        # 文件名前缀与导出格式解析
        batch_prefix = filename_prefix or f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        formats_to_save: List[str] = []
        try:
            if formats:
                formats_to_save = [f.strip() for f in formats if f and f.strip()]
            elif getattr(app_cfg.output, "formats", None):
                formats_to_save = list(app_cfg.output.formats)
            else:
                formats_to_save = [app_cfg.output.format]
        except Exception:
            formats_to_save = ["json"]

        # 逐会话扫描
        for idx, title in enumerate(chat_titles, start=1):
            safe_title = str(title).strip()
            if not safe_title:
                continue
            if reporter:
                reporter.update(status=f"定位会话({idx}/{len(chat_titles)}): {safe_title}")

            # 尝试点击侧边栏会话（支持模糊匹配与滚动）
            clicked = False
            try:
                clicked = self.scroll.click_session_by_text(safe_title, self.ocr)
            except Exception as e:
                self.logger.warning(f"点击会话 '{safe_title}' 时异常：{e}")

            if not clicked:
                self.logger.info(f"未找到会话或点击失败：{safe_title}，跳过该会话。")
                if reporter:
                    reporter.update(status=f"跳过未找到的会话：{safe_title}")
                continue

            # 轻微等待让内容稳定
            time.sleep(0.5)

            # 插入系统分隔消息（自定义非UUID id，以确保稳定主键参与去重）
            try:
                sys_msg = Message(
                    id=f"SYS-{safe_title}-{int(time.time())}",
                    sender="系统",
                    content=f"=== 会话：{safe_title} ===",
                    message_type=MessageType.SYSTEM,
                    timestamp=datetime.now(),
                    confidence_score=1.0,
                    raw_ocr_text=f"=== 会话：{safe_title} ===",
                )
                key = sys_msg.stable_key()
                if not deduplicate_global or key not in seen_keys:
                    aggregated.append(sys_msg)
                    if deduplicate_global:
                        seen_keys.add(key)
            except Exception:
                pass

            # 扫描当前会话聊天记录
            if reporter:
                reporter.update(status=f"扫描会话：{safe_title}")
            try:
                msgs = self.scan_chat_history(
                    max_messages=per_chat_max_messages,
                    enable_deduplication=True,
                    max_batches=None,
                    direction=direction,
                    reporter=reporter,
                )
            except Exception as e:
                self.logger.error(f"扫描会话 '{safe_title}' 失败：{e}")
                msgs = []

            # 全局聚合与去重
            if msgs:
                for m in msgs:
                    if deduplicate_global:
                        k = m.stable_key()
                        if k in seen_keys:
                            continue
                        seen_keys.add(k)
                    aggregated.append(m)
            else:
                self.logger.info(f"会话 '{safe_title}' 未提取到消息。")

        # 保存聚合结果
        if aggregated:
            try:
                storage = StorageManager(output_config=app_cfg.output)
                if formats_to_save and len(formats_to_save) > 1:
                    paths = storage.save_messages_multiple(aggregated, filename_prefix=batch_prefix, formats=formats_to_save)
                    for p in paths:
                        self.logger.info(f"批量结果已保存到: {p}")
                else:
                    # 单一格式保存
                    path = storage.save_messages(aggregated, filename_prefix=batch_prefix)
                    self.logger.info(f"批量结果已保存到: {path}")
            except Exception as e:
                self.logger.error(f"保存批量结果失败：{e}")

        if reporter:
            reporter.finish(success=bool(aggregated))

        return aggregated

    def run_and_save(
        self,
        filename_prefix: str = "extraction",
        use_retry: bool = True,
        max_attempts: int = 3,
        delay_seconds: float = 0.5,
        reporter: ProgressReporter | None = None,
        messages: List[Message] | None = None,
        output_override: OutputConfig | None = None,
    ) -> List[Message]:
        """
        Run extraction (optionally with retry and progress), then save results according to OutputConfig.

        Returns the list of messages parsed (empty if none).
        """
        # Load application config
        cfg_mgr = ConfigManager()
        app_cfg: AppConfig = cfg_mgr.get_config()
        out_cfg: OutputConfig = output_override or app_cfg.output

        # Execute extraction only if messages were not provided
        if messages is None:
            if use_retry:
                if reporter is not None:
                    messages = self.run_with_progress(reporter, max_attempts=max_attempts, delay_seconds=delay_seconds)
                else:
                    messages = self.run_with_retry(max_attempts=max_attempts, delay_seconds=delay_seconds)
            else:
                messages = self.run_once()

        # Save if we have results
        if messages:
            storage = StorageManager(output_config=out_cfg)
            try:
                # 如果配置了多格式，则一次性导出多个文件
                if getattr(out_cfg, "formats", None):
                    paths = storage.save_messages_multiple(messages, filename_prefix=filename_prefix, formats=out_cfg.formats)
                    for p in paths:
                        self.logger.info(f"结果已保存到: {p}")
                else:
                    path = storage.save_messages(messages, filename_prefix=filename_prefix)
                    self.logger.info(f"结果已保存到: {path}")
            except Exception as e:
                self.logger.error(f"保存失败: {e}")
        else:
            self.logger.info("无可保存的消息结果。")
        return messages
