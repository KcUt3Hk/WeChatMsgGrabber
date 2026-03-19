import os
import time
import logging

from ui.progress import ProgressReporter


def test_metrics_rotation_csv(tmp_path):
    """
    测试 CSV 指标文件在达到大小阈值后执行轮转。

    函数级注释：
    - 配置 ProgressReporter 在心跳时写入 CSV 指标，并设置极小的文件大小阈值与轮转保留数量；
    - 通过短时间的高频心跳写入触发轮转；
    - 若当前文件存在则断言其含有表头，至少存在一个历史轮转文件且不为空。
    """
    metrics_path = tmp_path / "rot_metrics.csv"
    logger = logging.getLogger("rotation_test")
    reporter = ProgressReporter(logger)
    # 阈值设置为约 0.00001 MB（约 10 字节），确保快速触发轮转
    reporter.configure_metrics(output_file=str(metrics_path), fmt="csv", max_file_size_mb=0.00001, rotate_count=2)
    reporter.start_heartbeat(interval_seconds=0.05)
    # 允许产生若干心跳记录
    time.sleep(1.0)
    reporter.stop_heartbeat()

    # 基础断言：若当前文件存在则应包含表头（可能在最后一次心跳后已轮转，导致当前文件被移动为 .1）
    base_exists = metrics_path.exists()
    if base_exists:
        with open(metrics_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            assert "timestamp,status,messages,attempts,cpu_percent,memory_mb" in first_line, "CSV 文件应包含表头"

    # 至少一个轮转文件存在且不为空
    rotated_exists = False
    for i in (1, 2):
        rot = tmp_path / f"rot_metrics.csv.{i}"
        if rot.exists() and os.path.getsize(rot) > 0:
            rotated_exists = True
            break
    assert rotated_exists, "应至少存在一个非空的轮转文件 (.1 或 .2)"


def test_metrics_rotation_json(tmp_path):
    """
    测试 JSON 指标文件在达到大小阈值后执行轮转。

    函数级注释：
    - 配置 ProgressReporter 在心跳时写入 JSON 指标，并设置极小的文件大小阈值与轮转保留数量；
    - 心跳写入若干记录以触发轮转；
    - 若当前文件存在则断言其包含 JSON 行，至少存在一个历史轮转文件且不为空。
    """
    metrics_path = tmp_path / "rot_metrics.json"
    logger = logging.getLogger("rotation_test_json")
    reporter = ProgressReporter(logger)
    reporter.configure_metrics(output_file=str(metrics_path), fmt="json", max_file_size_mb=0.00001, rotate_count=2)
    reporter.start_heartbeat(interval_seconds=0.05)
    time.sleep(1.0)
    reporter.stop_heartbeat()

    base_exists = metrics_path.exists()
    if base_exists:
        with open(metrics_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            assert first_line.startswith("{"), "JSON 指标文件应为逐行 JSON 记录"

    rotated_exists = False
    for i in (1, 2):
        rot = tmp_path / f"rot_metrics.json.{i}"
        if rot.exists() and os.path.getsize(rot) > 0:
            rotated_exists = True
            break
    assert rotated_exists, "应至少存在一个非空的 JSON 轮转文件 (.1 或 .2)"