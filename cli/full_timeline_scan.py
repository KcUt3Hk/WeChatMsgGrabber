#!/usr/bin/env python3
"""
全量时间线扫描 CLI：从微信聊天窗口的最早消息开始，按时间顺序获取到最新消息，
并在尾部进行实时新消息监控与增量抓取，确保严格顺序与唯一性校验。

使用说明：
- 先滚动到顶部，执行向下渐进式扫描，收集消息；
- 扫描完成后，进入尾部实时监控阶段，周期性拉取并增量保存最新消息；
- 所有消息经过 StorageManager 的去重与排序，确保最终导出严格按时间顺序；

依赖模块：
- controllers.main_controller.MainController: 负责窗口定位、截图、OCR与消息解析
- services.advanced_scroll_controller.AdvancedScrollController: 负责渐进式滚动与终止条件
- services.storage_manager.StorageManager: 负责消息去重、排序与多格式导出
- models.data_models.Message: 消息数据结构与 stable_key 唯一性校验

注意：
- 需要确保微信客户端已打开，目标聊天会话处于前台并可滚动查看历史；
- 根据机器性能与聊天长度，建议合理设置滚动步长、延迟与最大滚动次数；
"""

import os
import sys
import time
import json
import signal
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

# 保证包导入在项目根目录结构下生效
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from controllers.main_controller import MainController
from services.advanced_scroll_controller import AdvancedScrollController
from services.storage_manager import StorageManager
from models.config import OutputConfig
from models.data_models import Message


class FullTimelineScanner:
    """全量时间线扫描器：实现从顶部到最新与尾部实时监控。

    属性：
    - output_dir: 输出目录
    - realtime_tail_monitor: 是否在尾部开启实时增量监控
    - tail_poll_interval: 尾部监控轮询间隔（秒）
    - max_scrolls_initial: 初始阶段最大滚动次数（防止异常循环）
    - scroll_params: 渐进式滚动参数（方向、惯性、延迟等）
    - logger: 日志记录器
    - main_controller: 主控制器实例
    - adv_scroll: 高级滚动控制器实例
    - storage: 存储管理器实例
    """

    def __init__(
        self,
        output_dir: str = "output",
        realtime_tail_monitor: bool = True,
        tail_poll_interval: float = 2.0,
        max_scrolls_initial: int = 500,
        scroll_direction: str = "down",
        inertia_enabled: bool = True,
        delay_between_scrolls: float = 0.25,
        similarity_threshold: float = 0.985,
        verbose: bool = False,
        title_override: Optional[str] = None,
        chat_area_override: Optional[tuple[int, int, int, int]] = None,
    ):
        """初始化扫描器并配置日志、控制器与存储。

        参数：
        - output_dir: 输出目录
        - realtime_tail_monitor: 是否进行尾部实时监控
        - tail_poll_interval: 尾部监控的轮询间隔（秒）
        - max_scrolls_initial: 初始扫描阶段的最大滚动次数
        - scroll_direction: 初始扫描的滚动方向（默认向下，从顶部向最新）
        - inertia_enabled: 是否启用滚动惯性效果
        - delay_between_scrolls: 每次滚动后的延迟（秒）
        - similarity_threshold: 内容相似度阈值，用于终止与重复页面检测
        - verbose: 是否启用详细日志
        """
        self.output_dir = output_dir
        self.realtime_tail_monitor = realtime_tail_monitor
        self.tail_poll_interval = tail_poll_interval
        self.max_scrolls_initial = max_scrolls_initial
        self.scroll_params = {
            "direction": scroll_direction,
            "inertia": inertia_enabled,
            "delay": delay_between_scrolls,
            "similarity_threshold": similarity_threshold,
        }

        self.logger = logging.getLogger("FullTimelineScanner")
        self._setup_logging(verbose)

        # 控制器与存储初始化
        self.main_controller = MainController()
        # 高级滚动控制器参数与存储配置修正：
        # - AdvancedScrollController 不支持 delay_between_scrolls/similarity_threshold 等关键字参数；
        #   使用 scroll_delay 与 inertial_effect 对应配置；
        # - StorageManager 构造函数接收 OutputConfig，用于控制目录、格式与去重。
        self.adv_scroll = AdvancedScrollController(
            scroll_speed=2,
            scroll_delay=delay_between_scrolls,
            inertial_effect=inertia_enabled,
        )

        # 应用窗口标题与聊天区域坐标覆盖（若提供）：同时同步到主控制器与高级滚动控制器
        try:
            if title_override:
                # 函数级注释：
                # - set_title_override 用于窗口定位失败时，强制按标题子串匹配候选窗口；
                # - 同步设置到两层控制器，提升在不同定位路径下的鲁棒性。
                self.main_controller.scroll.set_title_override(title_override)
                self.adv_scroll.set_title_override(title_override)
                self.logger.info("窗口标题覆盖: %s", title_override)
        except Exception as e:
            self.logger.warning("应用窗口标题覆盖失败: %s", e)
        try:
            if chat_area_override:
                self.main_controller.scroll.set_override_chat_area(chat_area_override)
                self.adv_scroll.set_override_chat_area(chat_area_override)
                x, y, w, h = chat_area_override
                self.logger.info("聊天区域覆盖: (%d,%d,%d,%d)", x, y, w, h)
        except Exception as e:
            self.logger.warning("聊天区域覆盖失败: %s", e)

        output_cfg = OutputConfig(
            # 函数级注释：
            # - directory: 导出目录；
            # - format: save_messages 的默认格式（此 CLI 主要使用 save_messages_multiple 手动指定多格式）；
            # - enable_deduplication: 开启批次内与跨批次的稳定键去重；
            # - exclude_time_only: 过滤纯时间/日期分隔消息；
            # - aggressive_dedup: 额外的内容级去重，进一步减少重复；
            directory=self.output_dir,
            format="json",
            enable_deduplication=True,
            exclude_time_only=True,
            aggressive_dedup=True,
            exclude_fields=[],
        )
        self.storage = StorageManager(output_config=output_cfg)

        # 状态缓存
        self._stop_flag = False
        self._last_saved_keyset: set[str] = set()

    def _setup_logging(self, verbose: bool):
        """配置日志输出格式与级别。

        参数：
        - verbose: 是否设置为 DEBUG 级别
        """
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    def run(self) -> bool:
        """运行完整扫描：从顶部到最新，然后尾部实时监控（可选）。

        返回：
        - True 表示执行成功，False 表示失败或中断
        """
        try:
            self.logger.info("启动全量时间线扫描，将在 5 秒后开始，请将目标聊天窗口置于前台…")
            time.sleep(5)

            # 1) 定位并确认当前选中的微信聊天窗口
            if not self._ensure_window_ready():
                return False

            # 2) 先滚动到顶部，再向下渐进扫描直到最新
            if not self._scan_from_top_to_latest():
                return False

            # 3) 尾部实时增量监控
            if self.realtime_tail_monitor:
                self._tail_realtime_monitor_loop()

            self.logger.info("扫描流程结束")
            return True
        except KeyboardInterrupt:
            self.logger.warning("收到中断信号，正在收尾保存…")
            self._stop_flag = True
            return True
        except Exception as e:
            self.logger.error(f"扫描失败: {e}")
            return False

    def _ensure_window_ready(self) -> bool:
        """定位并确认当前选中的微信聊天窗口可用。

        步骤：
        - 请求 MainController 定位窗口
        - 激活窗口并准备截图上下文
        返回：True 表示成功
        """
        try:
            # 通过底层滚动控制器定位与激活窗口
            win = self.main_controller.scroll.locate_wechat_window()
            if not win:
                self.logger.error("未能定位到微信聊天窗口，请确认微信已打开并在前台")
                return False
            if not self.main_controller.scroll.activate_window():
                self.logger.error("窗口激活失败，请将微信聊天窗口置于前台")
                return False
            # 进行一次就绪检查以提升鲁棒性
            if not self.main_controller.scroll.ensure_window_ready(retries=2, delay=0.3):
                self.logger.error("窗口未就绪，无法进行截图")
                return False
            self.logger.info("已定位并激活微信聊天窗口")
            return True
        except Exception as e:
            self.logger.error(f"窗口定位失败: {e}")
            return False

    def _scan_from_top_to_latest(self) -> bool:
        """从聊天记录顶部开始向下扫描，直到到达当前最新消息。

        关键点：
        - 调用 MainController.scroll_to_top() 保证从最早开始
        - 使用 AdvancedScrollController.progressive_scroll(direction='down') 渐进滚动
        - 每页进行 OCR 解析并累积消息，交由 StorageManager 去重与排序
        返回：True 表示成功
        """
        try:
            self.logger.info("开始执行顶部定位与向下扫描")
            # 先滚动到顶部，确保从最早开始
            # 顶部定位：MainController.scroll_to_top 无返回值，内部将自动进行截图对比判断
            self.main_controller.scroll_to_top()
            self.logger.info("已尝试滚动至聊天记录顶部，准备向下渐进扫描…")

            # 同步窗口上下文优先于高级滚动控制器的就绪检查，避免因独立定位失败导致初始定位异常
            if getattr(self.main_controller, "scroll", None) and getattr(self.main_controller.scroll, "current_window", None):
                try:
                    # 1) 同步已定位的窗口信息
                    self.adv_scroll.current_window = self.main_controller.scroll.current_window
                    # 2) 同步标题覆盖，提高后续枚举鲁棒性
                    self.adv_scroll.set_title_override(self.main_controller.scroll.current_window.title)
                    # 3) 复用主控制器解析出的聊天区域（如可用），确保 _locate_initial_position 能成功
                    chat_area = self.main_controller.scroll.get_chat_area_bounds()
                    if chat_area:
                        self.adv_scroll.set_override_chat_area(chat_area)
                        self.logger.debug("已复用主控制器聊天区域坐标作为覆盖，确保初始定位成功")
                    else:
                        # 若主控制器未能解析聊天区域，尝试使用高级滚动控制器基于窗口的估算逻辑
                        est = self.adv_scroll.get_chat_area_bounds()
                        if est:
                            self.adv_scroll.set_override_chat_area(est)
                            self.logger.debug("主控制器未提供聊天区域，已使用高级滚动控制器估算坐标作为覆盖")
                        else:
                            self.logger.debug("尚未获取到聊天区域坐标，后续将依赖高级滚动控制器的定位流程")
                except Exception as e:
                    self.logger.debug(f"同步窗口上下文失败：{e}")

            # 在同步上下文后再进行就绪检查：若已存在聊天区域覆盖，ensure_window_ready 将快速返回 True
            if not self.adv_scroll.ensure_window_ready(retries=2, delay=0.3):
                self.logger.error("高级滚动控制器窗口未就绪，无法执行渐进扫描")
                return False

            # 渐进式向下滚动，采集每页内容
            results = self.adv_scroll.progressive_scroll(
                direction=self.scroll_params["direction"],
                max_scrolls=self.max_scrolls_initial,
                target_content=None,
                stop_at_edges=True,
                max_duration=None,
            )

            if not results:
                # 函数级注释：
                # 渐进扫描可能因初始位置定位失败或边缘误判导致空结果。
                # 在此插入重试与降级策略：
                # 1) 进行一次/两次窗口高度步进的向下预热滚动，解除“在顶部仍被判到底部”的边缘误判；
                # 2) 关闭边缘终止(stop_at_edges=False)进行一次降级渐进扫描；
                # 3) 若仍为空，退路为“手动步进 + run_once 解析”的快照收集。
                self.logger.error("渐进扫描未返回任何结果，启动重试与降级策略…")

                # Step 1: 预热滚动，避免边缘误判
                try:
                    self.logger.info("执行降级预热滚动以解除边缘误判…")
                    for j in range(2):
                        ok = self.adv_scroll.scroll_by_window_height("down")
                        time.sleep(self.scroll_params["delay"])  # 小睡以等待界面稳定
                        self.logger.debug("预热滚动 %d/%d，结果=%s", j + 1, 2, ok)
                except Exception as e:
                    self.logger.debug("预热滚动过程异常：%s", e)

                # Step 2: 关闭边缘终止进行一次降级渐进扫描
                try:
                    self.logger.info("尝试关闭边缘终止的降级渐进扫描…")
                    results = self.adv_scroll.progressive_scroll(
                        direction=self.scroll_params["direction"],
                        max_scrolls=max(50, self.max_scrolls_initial // 2),
                        target_content=None,
                        stop_at_edges=False,
                        max_duration=None,
                    )
                except Exception as e:
                    self.logger.debug("降级渐进扫描异常：%s", e)

                # Step 3: 手动快照收集作为最后退路
                if not results:
                    self.logger.warning("降级渐进扫描仍为空，退路为手动步进快照收集…")
                    manual_states: List[Dict[str, Any]] = []
                    try:
                        max_manual_pages = 6
                        for idx in range(max_manual_pages):
                            # 执行一次 OCR 与消息解析
                            page_msgs = self.main_controller.run_once()
                            if page_msgs:
                                manual_states.append({
                                    "messages": page_msgs,
                                    "message_count": len(page_msgs),
                                    "timestamp": time.time(),
                                })
                                self.logger.debug("手动快照第 %d 页识别到 %d 条消息", idx + 1, len(page_msgs))
                            else:
                                self.logger.debug("手动快照第 %d 页未识别到消息", idx + 1)

                            # 步进滚动到下一页
                            try:
                                ok = self.adv_scroll.scroll_by_window_height("down")
                                self.logger.debug("手动步进滚动（向下）结果=%s", ok)
                            except Exception:
                                pass
                            time.sleep(self.scroll_params["delay"])  # 等待界面稳定后下一次识别

                        if manual_states:
                            results = manual_states
                    except Exception as e:
                        self.logger.error("手动快照收集退路失败：%s", e)

                if not results:
                    self.logger.error("所有重试与降级策略均未获取到内容，终止扫描")
                    return False

            # 解析与保存
            parsed_messages: List[Message] = self._parse_results_to_messages(results)
            self._save_messages_ordered(parsed_messages, label="initial_full_timeline")

            # 输出预览与统计
            self._print_preview(parsed_messages, max_items=10)
            self._print_storage_stats()
            return True
        except Exception as e:
            self.logger.error(f"从顶部到最新扫描失败: {e}")
            return False

    def _parse_results_to_messages(self, scroll_results: List[Dict[str, Any]]) -> List[Message]:
        """将滚动结果解析为 Message 列表。

        说明：
        - 每个滚动结果应包括截图 OCR 文本与解析出的消息集合；
        - 此处通过 MainController 的 run_once 进行当前视图的 OCR 与消息提取；
        - 若 AdvancedScrollController 已内置解析，可在 results 中直接读取。
        返回：Message 列表（可能包含重复，后续由存储层去重）。
        """
        messages: List[Message] = []
        try:
            for idx, page in enumerate(scroll_results):
                # 若 page 已包含消息列表，优先使用
                page_messages: List[Message] = []
                if isinstance(page, dict) and "messages" in page and page["messages"]:
                    page_messages = page["messages"]
                else:
                    # 回退：对当前屏幕执行一次 OCR 与解析（run_once 返回 List[Message]）
                    page_messages = self.main_controller.run_once()

                if not page_messages:
                    self.logger.debug(f"第 {idx+1} 页未识别到消息，跳过")
                    continue

                messages.extend(page_messages)
            return messages
        except Exception as e:
            self.logger.error(f"解析滚动结果为消息失败: {e}")
            return messages

    def _save_messages_ordered(self, messages: List[Message], label: str = "batch"):
        """按时间顺序保存消息到多种格式，并更新去重索引。

        步骤：
        - StorageManager.save_messages_multiple 负责排序与去重
        - 排除空白与仅时间标记内容（由存储层实现）
        - 将新增的稳定键加入本地缓存，便于尾部增量去重
        参数：
        - messages: 待保存的消息列表
        - label: 保存批次标签，用于输出文件命名或日志标识
        """
        if not messages:
            self.logger.info("没有可保存的消息")
            return

        # 触发存储层的排序与去重，并输出到多格式
        self.logger.info(f"开始保存批次 {label}，消息数: {len(messages)}")
        # 通过多格式导出（共享一次去重与索引过滤）
        try:
            paths = self.storage.save_messages_multiple(
                messages,
                filename_prefix=label,
                formats=["json", "csv"],
            )
            if paths:
                for p in paths:
                    self.logger.info(f"已生成文件: {p}")
        except Exception as e:
            self.logger.error(f"保存消息失败：{e}")

        # 更新本地已保存键集合（用于尾部增量去重）
        try:
            for msg in messages:
                key = msg.stable_key()
                if key:
                    self._last_saved_keyset.add(key)
        except Exception:
            pass

    def _tail_realtime_monitor_loop(self):
        """在尾部进行实时监控，增量抓取并保存新消息。

        机制：
        - 保持滚动到底部（先进一次 scroll_direction='down' 到尾部，可选）
        - 周期性执行 run_once() 提取当前视图消息
        - 对比本地稳定键集合与存储层去重，找到新增消息并保存
        - 保证保存顺序：增量消息仍通过存储层排序
        可通过 Ctrl+C 终止监控。
        """
        self.logger.info("进入尾部实时监控阶段，按 Ctrl+C 终止…")
        # 注册信号处理
        signal.signal(signal.SIGINT, self._handle_sigint)
        signal.signal(signal.SIGTERM, self._handle_sigint)

        while not self._stop_flag:
            try:
                # 单次提取当前视图的消息列表
                new_msgs: List[Message] = self.main_controller.run_once()
                if not new_msgs:
                    time.sleep(self.tail_poll_interval)
                    continue

                # 仅保留稳定键未出现过的消息进行增量保存
                incremental: List[Message] = []
                for m in new_msgs:
                    key = m.stable_key()
                    if not key:
                        # 无稳定键的消息也交由存储层去重处理，但这里谨慎跳过，避免不稳定记录
                        continue
                    if key not in self._last_saved_keyset:
                        incremental.append(m)

                if incremental:
                    self.logger.info(f"检测到新消息 {len(incremental)} 条，执行增量保存…")
                    self._save_messages_ordered(incremental, label="tail_incremental")
                else:
                    self.logger.debug("暂无新增消息")

                time.sleep(self.tail_poll_interval)
            except KeyboardInterrupt:
                self._stop_flag = True
            except Exception as e:
                self.logger.warning(f"尾部监控循环出现异常：{e}")
                time.sleep(self.tail_poll_interval)

    def _handle_sigint(self, signum, frame):
        """信号处理：设置停止标记便于循环退出。"""
        self.logger.info("收到停止信号，正在安全退出…")
        self._stop_flag = True

    def _print_preview(self, messages: List[Message], max_items: int = 10):
        """输出预览：按时间顺序展示前若干条消息的简要信息。"""
        try:
            # 由存储层排序，这里仅本地排序预览
            msgs_sorted = sorted(messages, key=lambda m: (m.timestamp or datetime.min))
            self.logger.info("消息预览（最多显示 %d 条）：", max_items)
            for i, m in enumerate(msgs_sorted[:max_items]):
                ts = m.timestamp.isoformat() if isinstance(m.timestamp, datetime) else str(m.timestamp)
                self.logger.info(f"[{i+1}] {ts} | {m.sender}: {m.content}")
        except Exception:
            pass

    def _print_storage_stats(self):
        """打印存储统计信息，便于确认排序与去重效果。"""
        try:
            stats = self.storage.get_statistics() if hasattr(self.storage, "get_statistics") else {}
            if stats:
                self.logger.info(f"存储统计: {json.dumps(stats, ensure_ascii=False)}")
        except Exception:
            pass


def main():
    """CLI 入口：解析参数并运行全量时间线扫描。"""
    import argparse

    parser = argparse.ArgumentParser(description="微信聊天全量时间线扫描，并尾部实时监控")
    parser.add_argument("--output", "-o", default="output", help="输出目录")
    parser.add_argument("--no-tail", action="store_true", help="禁用尾部实时监控")
    parser.add_argument("--tail-interval", type=float, default=2.0, help="尾部监控轮询间隔（秒）")
    parser.add_argument("--max-scrolls", type=int, default=500, help="初始阶段最大滚动次数")
    parser.add_argument("--delay", type=float, default=0.25, help="每次滚动后延迟（秒）")
    parser.add_argument("--similarity", type=float, default=0.985, help="相似度阈值")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志模式")
    parser.add_argument("--window-title", dest="title_override", help="窗口标题覆盖（用于窗口定位失败时，例如 '微信' 或 'WeChat'）")
    parser.add_argument("--chat-area", help="聊天区域坐标覆盖，格式 x,y,width,height")
    parser.add_argument("--ocr-lang", help="OCR 语言覆盖（默认从配置读取，例如 ch）")

    args = parser.parse_args()

    # 创建扫描器
    # 解析聊天区域坐标覆盖
    chat_area_tuple = None
    if args.chat_area:
        try:
            parts = [p.strip() for p in args.chat_area.split(',')]
            if len(parts) != 4:
                raise ValueError("chat-area 必须为 'x,y,width,height'")
            chat_area_tuple = tuple(map(int, parts))  # type: ignore
        except Exception as e:
            print(f"聊天区域覆盖解析失败: {e}")

    scanner = FullTimelineScanner(
        output_dir=args.output,
        realtime_tail_monitor=(not args.no_tail),
        tail_poll_interval=args.tail_interval,
        max_scrolls_initial=args.max_scrolls,
        delay_between_scrolls=args.delay,
        similarity_threshold=args.similarity,
        verbose=args.verbose,
        title_override=args.title_override,
        chat_area_override=chat_area_tuple,
    )

    # 可选：应用 OCR 语言覆盖到主控制器
    if args.ocr_lang:
        try:
            scanner.main_controller.ocr.config.language = args.ocr_lang.strip()
            logging.getLogger("FullTimelineScanner").info("使用 CLI 指定的 OCR 语言: %s", scanner.main_controller.ocr.config.language)
        except Exception as e:
            logging.getLogger("FullTimelineScanner").warning("应用 OCR 语言失败: %s", e)

    success = scanner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()