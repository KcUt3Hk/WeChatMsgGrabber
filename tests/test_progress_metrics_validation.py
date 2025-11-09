import logging
import time
from pathlib import Path

import pytest

from ui.progress import ProgressReporter


def _wait_for_heartbeat(duration: float = 1.0):
    """
    辅助等待函数：等待心跳线程采样若干次，默认 1.0s
    函数级注释：
    - 心跳采样间隔通常约为 0.2s，本函数等待 1.0s，以确保至少进行多次采样与写入；
    - 较长的等待时间有助于在极小文件大小阈值下快速触发相关行为（如轮转或写入）。
    """
    time.sleep(duration)


def test_configure_metrics_format_fallback_to_csv(tmp_path: Path):
    """
    验证非法格式回退：当 fmt 提供非法值时，应回退为 csv 并写入包含表头的 CSV 文件。
    步骤：
    - 提供 fmt="xml"，路径为 metrics.txt（扩展名不影响逻辑）；
    - 启动心跳、等待写入后停止；
    - 验证文件存在且首行包含 CSV 表头字段。
    """
    logger = logging.getLogger("progress-test-validation-fmt")
    logger.setLevel(logging.DEBUG)

    out_file = tmp_path / "metrics.txt"
    pr = ProgressReporter(logger=logger)
    pr.configure_metrics(output_file=str(out_file), fmt="xml")
    pr.start_heartbeat(interval_seconds=0.2)
    _wait_for_heartbeat(1.0)
    pr.stop_heartbeat()

    assert out_file.exists(), "指标文件未生成"
    lines = out_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2, "CSV 文件应包含表头与至少一条记录"
    header = lines[0]
    for col in ["timestamp", "status", "cpu_percent", "memory_mb"]:
        assert col in header, f"表头缺少列: {col}"


def test_rotation_disabled_when_nonpositive_max_size(tmp_path: Path):
    """
    验证在 max_file_size_mb<=0 时禁用轮转：即使设置了 rotate_count>0，也不应发生任何轮转。
    步骤：
    - 设置 rotate_count=2，但 max_file_size_mb=0.0；
    - 启动心跳、等待写入后停止；
    - 验证不存在 .1/.2 等轮转文件。
    """
    logger = logging.getLogger("progress-test-validation-size0")
    logger.setLevel(logging.DEBUG)

    out_file = tmp_path / "metrics.csv"
    pr = ProgressReporter(logger=logger)
    pr.configure_metrics(output_file=str(out_file), fmt="csv", max_file_size_mb=0.0, rotate_count=2)
    pr.start_heartbeat(interval_seconds=0.2)
    _wait_for_heartbeat(1.0)
    pr.stop_heartbeat()

    assert out_file.exists(), "当前指标文件应存在"
    assert not (tmp_path / "metrics.csv.1").exists(), "在禁用轮转时不应生成 .1 文件"
    assert not (tmp_path / "metrics.csv.2").exists(), "在禁用轮转时不应生成 .2 文件"


def test_rotate_count_negative_disables_rotation(tmp_path: Path):
    """
    验证 rotate_count 为负数时回退为禁用轮转（等同于 0）：即使设置了很小的大小阈值，也不应发生轮转。
    步骤：
    - 设置 rotate_count=-5，max_file_size_mb=0.00001；
    - 启动心跳、等待写入后停止；
    - 验证不存在 .1 文件。
    """
    logger = logging.getLogger("progress-test-validation-rcneg")
    logger.setLevel(logging.DEBUG)

    out_file = tmp_path / "metrics.csv"
    pr = ProgressReporter(logger=logger)
    pr.configure_metrics(output_file=str(out_file), fmt="csv", max_file_size_mb=0.00001, rotate_count=-5)
    pr.start_heartbeat(interval_seconds=0.2)
    _wait_for_heartbeat(1.0)
    pr.stop_heartbeat()

    assert out_file.exists(), "当前指标文件应存在"
    assert not (tmp_path / "metrics.csv.1").exists(), "当 rotate_count 为负数（回退为 0）时，不应生成 .1 文件"


def test_log_hint_when_rotate_unlimited_size(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """
    验证日志提示：当设置了 rotate_count>0 但未启用大小限制（max_file_size_mb<=0）时，应输出友好提示。
    步骤：
    - 捕获 INFO 日志；
    - 配置 rotate_count=3 与 max_file_size_mb=0；
    - 检查日志中是否包含提示文本。
    """
    logger_name = "progress-test-validation-log"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    caplog.set_level(logging.INFO, logger=logger_name)

    out_file = tmp_path / "metrics.csv"
    pr = ProgressReporter(logger=logger)
    pr.configure_metrics(output_file=str(out_file), fmt="csv", max_file_size_mb=0, rotate_count=3)

    # 查找提示信息
    hints = [r for r in caplog.records if ("轮转参数" in r.message and "max_file_size_mb<=0" in r.message)]
    assert len(hints) >= 1, "未捕获到禁用大小限制的轮转提示日志"