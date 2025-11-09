"""
Simple progress reporter for CLI/console UI.
Provides start/stop hooks, status updates, and optional resource heartbeat for long-running tasks.

函数级注释：
- ProgressReporter 提供基础的开始/更新/结束接口；
- 可选启用心跳线程，周期性采集资源使用（CPU/内存）并输出日志，便于监控长时间运行任务；
- 资源采集优先使用 psutil，如不可用则降级仅输出心跳日志；
- 所有接口均为非侵入式扩展，保持与既有测试和调用方的兼容性。
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ProgressState:
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str = "idle"
    messages_parsed: int = 0
    attempts: int = 0
    last_error: Optional[str] = None
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None


class ProgressReporter:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.state = ProgressState()
        self._hb_thread: Optional[threading.Thread] = None
        self._hb_stop = threading.Event()
        self._hb_interval = 5.0
        self._hb_enabled = False
        # 指标采集与写入配置
        self._metrics_file_path: Optional[str] = None
        self._metrics_format: str = "csv"  # 支持 csv 或 json
        self._metrics_header_written: bool = False
        self._cpu_threshold: Optional[float] = None  # 百分比，例如 90.0
        self._mem_threshold_mb: Optional[float] = None  # MB，例如 1024.0
        # 文件轮转控制
        self._max_file_size_mb: Optional[float] = None
        self._rotate_count: int = 0

    def start(self) -> None:
        self.state = ProgressState()
        self.state.started_at = datetime.now()
        self.state.status = "running"
        self.logger.info("提取任务已开始")

    def update(self, messages_parsed_delta: int = 0, status: Optional[str] = None, attempts_delta: int = 0, error: Optional[str] = None) -> None:
        if messages_parsed_delta:
            self.state.messages_parsed += max(0, messages_parsed_delta)
        if status:
            self.state.status = status
        if attempts_delta:
            self.state.attempts += max(0, attempts_delta)
        if error:
            self.state.last_error = error
            self.logger.warning(f"状态更新，错误：{error}")
        self.logger.debug(f"状态：{self.state.status}，消息数：{self.state.messages_parsed}，尝试次数：{self.state.attempts}")

    def finish(self, success: bool = True) -> None:
        self.state.finished_at = datetime.now()
        self.state.status = "success" if success else "failed"
        duration = (self.state.finished_at - self.state.started_at).total_seconds() if self.state.started_at else 0.0
        self.logger.info(f"提取任务已结束，状态：{self.state.status}，耗时：{duration:.2f}s，共解析消息：{self.state.messages_parsed}")
        # 自动停止心跳线程
        if self._hb_enabled:
            self.stop_heartbeat()

    def start_heartbeat(self, interval_seconds: float = 5.0) -> None:
        """
        启动资源心跳线程（可选）。

        函数级注释：
        - 每 interval_seconds 采集一次 CPU/内存并更新到状态；
        - 优先使用 psutil 获取真实数据，若不可用则仅输出心跳日志；
        - 心跳线程会在 finish() 或 stop_heartbeat() 时自动停止。
        - 若通过 configure_metrics() 配置了指标写入，则在每次心跳时将采样写入文件（CSV/JSON），
          并在超过阈值（CPU/内存）时输出告警日志。
        """
        if self._hb_enabled:
            return
        self._hb_interval = max(1.0, float(interval_seconds))
        self._hb_stop.clear()
        self._hb_enabled = True

        def _loop():
            psutil = None
            try:
                import psutil as _ps
                psutil = _ps
            except Exception:
                psutil = None
            # 首次心跳提示
            self.logger.debug("资源心跳已启动，间隔 %.1fs", self._hb_interval)
            while not self._hb_stop.is_set():
                try:
                    cpu = None
                    mem_mb = None
                    if psutil:
                        cpu = psutil.cpu_percent(interval=None)
                        process = psutil.Process()
                        mem_mb = process.memory_info().rss / (1024 * 1024)
                        self.state.cpu_percent = float(cpu)
                        self.state.memory_mb = float(mem_mb)
                        self.logger.debug("心跳：CPU %.1f%%, 内存 %.1fMB, 状态 %s, 消息数 %d",
                                          self.state.cpu_percent or 0.0,
                                          self.state.memory_mb or 0.0,
                                          self.state.status,
                                          self.state.messages_parsed)
                        # 阈值告警
                        try:
                            if self._cpu_threshold is not None and self.state.cpu_percent is not None and self.state.cpu_percent >= self._cpu_threshold:
                                self.logger.warning("CPU 使用率达到阈值 %.1f%%（当前 %.1f%%）", self._cpu_threshold, self.state.cpu_percent)
                            if self._mem_threshold_mb is not None and self.state.memory_mb is not None and self.state.memory_mb >= self._mem_threshold_mb:
                                self.logger.warning("内存占用达到阈值 %.1fMB（当前 %.1fMB）", self._mem_threshold_mb, self.state.memory_mb)
                        except Exception:
                            pass
                    else:
                        # 无 psutil 时仅输出心跳
                        self.logger.debug("心跳：状态 %s, 消息数 %d", self.state.status, self.state.messages_parsed)

                    # 指标写入（若已配置）
                    try:
                        if self._metrics_file_path:
                            # 在写入之前检查是否需要进行文件轮转
                            if self._metrics_format.lower() == "csv":
                                # 写入 CSV：timestamp,status,messages,attempts,cpu,memory
                                import csv
                                # 延迟打开：每次心跳以追加方式写入，避免长时持有文件句柄
                                with open(self._metrics_file_path, "a", newline="") as f:
                                    writer = csv.writer(f)
                                    if not self._metrics_header_written:
                                        writer.writerow(["timestamp","status","messages","attempts","cpu_percent","memory_mb"])
                                        self._metrics_header_written = True
                                    writer.writerow([
                                        datetime.now().isoformat(timespec="seconds"),
                                        self.state.status,
                                        int(self.state.messages_parsed or 0),
                                        int(self.state.attempts or 0),
                                        float(self.state.cpu_percent or 0.0),
                                        float(self.state.memory_mb or 0.0),
                                    ])
                                # 写入后进行文件大小检查与轮转
                                self._metrics_rotate_if_needed()
                            elif self._metrics_format.lower() == "json":
                                import json
                                rec = {
                                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                                    "status": self.state.status,
                                    "messages": int(self.state.messages_parsed or 0),
                                    "attempts": int(self.state.attempts or 0),
                                    "cpu_percent": float(self.state.cpu_percent or 0.0),
                                    "memory_mb": float(self.state.memory_mb or 0.0),
                                }
                                with open(self._metrics_file_path, "a") as f:
                                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                                # 写入后进行文件大小检查与轮转
                                self._metrics_rotate_if_needed()
                    except Exception as e:
                        self.logger.debug("指标写入失败：%s", e)
                except Exception as e:
                    self.logger.debug("资源心跳采集异常：%s", e)
                finally:
                    # 使用 Event.wait 以便在 stop 时能快速返回
                    self._hb_stop.wait(self._hb_interval)

        self._hb_thread = threading.Thread(target=_loop, name="ProgressHeartbeat", daemon=True)
        self._hb_thread.start()

    def stop_heartbeat(self) -> None:
        """
        停止资源心跳线程（如果已启用）。

        函数级注释：
        - 通过事件通知线程退出并等待其结束；
        - 线程设计为 daemon，若调用方提前退出进程也不会阻塞关机；
        - 停止后会重置相关标志以便再次启动。
        """
        if not self._hb_enabled:
            return
        try:
            self._hb_stop.set()
            if self._hb_thread and self._hb_thread.is_alive():
                self._hb_thread.join(timeout=3.0)
        finally:
            self._hb_enabled = False
            self._hb_thread = None
            self._hb_stop.clear()

    def configure_metrics(self, output_file: Optional[str] = None, fmt: str = "csv", cpu_threshold: Optional[float] = None, mem_threshold_mb: Optional[float] = None, max_file_size_mb: Optional[float] = None, rotate_count: int = 0) -> None:
        """
        配置心跳指标写入与阈值告警。

        函数级注释：
        - 当提供 output_file 时，心跳线程会在每次采样后将数据追加写入该文件；
        - fmt 支持 "csv" 或 "json"，默认 csv；
        - 当设置 cpu_threshold 或 mem_threshold_mb 时，超过阈值将输出告警日志；
        - 当设置 max_file_size_mb 与 rotate_count 时，达到大小阈值将进行简单的文件轮转（base -> .1 -> .2 ...）；
        - 该方法仅更新配置，需配合 start_heartbeat() 开启心跳线程。

        Args:
            output_file: 指标写入的文件路径；None 表示不写入，仅输出日志
            fmt: 写入格式（csv 或 json）
            cpu_threshold: CPU 使用率阈值（百分比，例如 90.0）
            mem_threshold_mb: 内存占用阈值（MB，例如 1024.0）
            max_file_size_mb: 指标文件的最大大小（MB），达到后触发轮转；None 或 <=0 时禁用轮转
            rotate_count: 轮转保留的文件个数（例如 3 则保留 .1、.2、.3）；<=0 时不保留历史
        """
        try:
            # 路径与格式
            self._metrics_file_path = output_file
            fmt_norm = (fmt or "csv").lower().strip()
            if fmt_norm not in ("csv", "json"):
                self.logger.warning("未知的指标格式 '%s'，已回退为 csv", fmt)
                fmt_norm = "csv"
            self._metrics_format = fmt_norm

            # 阈值设置（允许 None 表示禁用告警）
            self._cpu_threshold = cpu_threshold if cpu_threshold is None else float(cpu_threshold)
            self._mem_threshold_mb = mem_threshold_mb if mem_threshold_mb is None else float(mem_threshold_mb)

            # 轮转参数校验与标准化
            if max_file_size_mb is None:
                self._max_file_size_mb = None
            else:
                try:
                    msz = float(max_file_size_mb)
                except Exception:
                    msz = 0.0
                # 非正数禁用轮转
                self._max_file_size_mb = msz if msz > 0 else 0.0

            try:
                rc = int(rotate_count or 0)
            except Exception:
                rc = 0
            # 负数回退为 0
            self._rotate_count = rc if rc > 0 else 0

            # 每次重新配置后，下次 CSV 写入需重写表头
            self._metrics_header_written = False

            if output_file:
                limit_str = "未限制" if (self._max_file_size_mb is None or (isinstance(self._max_file_size_mb, (int,float)) and self._max_file_size_mb <= 0)) else f"{float(self._max_file_size_mb):.2f}"
                self.logger.info("已配置指标写入文件：%s（格式：%s，最大大小：%sMB，轮转保留：%d）", output_file, self._metrics_format, limit_str, self._rotate_count)
                if self._rotate_count > 0 and (self._max_file_size_mb is None or (isinstance(self._max_file_size_mb, (int,float)) and self._max_file_size_mb <= 0)):
                    self.logger.info("轮转参数 rotate_count=%d 已设置，但未启用大小限制（max_file_size_mb<=0），轮转将不会发生。", self._rotate_count)

            if cpu_threshold is not None:
                self.logger.info("CPU 阈值：%.1f%%", float(cpu_threshold))
            if mem_threshold_mb is not None:
                self.logger.info("内存阈值：%.1fMB", float(mem_threshold_mb))
        except Exception as e:
            self.logger.warning("配置指标写入失败：%s", e)

    def _metrics_rotate_if_needed(self) -> None:
        """
        在写入指标前检查并执行简单的日志文件轮转。

        函数级注释：
        - 当设置了最大文件大小与轮转计数时，达到大小阈值会将当前文件重命名为 .1，
          现有的 .1、.2 ... 按序递增保留至 rotate_count；随后重置表头写入标记。
        - 轮转采用原子性的 os.replace，避免在并发场景下出现部分写入；
        - 若未设置大小限制或轮转计数为 0，则不会进行轮转操作。
        """
        try:
            if not self._metrics_file_path:
                return
            # 轮转开关条件
            if self._max_file_size_mb is None or (isinstance(self._max_file_size_mb, (int, float)) and self._max_file_size_mb <= 0):
                return
            if self._rotate_count <= 0:
                return
            import os
            if not os.path.exists(self._metrics_file_path):
                return
            limit_bytes = int(float(self._max_file_size_mb) * 1024 * 1024)
            try:
                current_size = os.path.getsize(self._metrics_file_path)
            except Exception:
                current_size = 0
            if current_size < limit_bytes:
                return
            # 从最大的序号开始向后移动，避免覆盖
            for i in range(self._rotate_count - 1, 0, -1):
                old = f"{self._metrics_file_path}.{i}"
                new = f"{self._metrics_file_path}.{i+1}"
                if os.path.exists(old):
                    try:
                        os.replace(old, new)
                    except Exception:
                        pass
            # 将当前文件移动到 .1
            try:
                os.replace(self._metrics_file_path, f"{self._metrics_file_path}.1")
            except Exception:
                # 如果替换失败，尽量不要影响后续写入
                pass
            # 新文件将重新写入表头
            self._metrics_header_written = False
        except Exception as e:
            self.logger.debug("指标文件轮转失败：%s", e)