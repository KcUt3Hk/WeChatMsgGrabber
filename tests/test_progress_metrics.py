import json
import logging
import time
from pathlib import Path

import pytest

from ui.progress import ProgressReporter

# 检查系统环境是否安装了 psutil：用于阈值告警测试的判断
try:
    import psutil  # type: ignore
except Exception:
    psutil = None


def _wait_for_heartbeat(duration: float = 0.6):
    """
    辅助等待函数：等待心跳线程采样若干次，默认 0.6s
    说明：心跳采样间隔通常为 0.2s 左右，0.6s 能保证至少 2 次采样，降低测试不稳定性。
    """
    time.sleep(duration)


def test_metrics_csv_write(tmp_path: Path):
    """
    测试 ProgressReporter 在启用心跳时能够写入 CSV 指标文件：
    - 启动心跳线程，等待采样
    - 停止心跳后检查 CSV 文件是否存在
    - 校验至少包含表头与一条记录（行数 >= 2）
    """
    logger = logging.getLogger("progress-test-csv")
    logger.setLevel(logging.DEBUG)

    out_file = tmp_path / "metrics.csv"
    pr = ProgressReporter(logger=logger)
    pr.configure_metrics(output_file=str(out_file), fmt="csv")
    pr.start_heartbeat(interval_seconds=0.2)
    _wait_for_heartbeat(0.6)
    pr.stop_heartbeat()

    assert out_file.exists(), "CSV 指标文件未生成"
    lines = out_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2, f"期望至少 2 行（表头 + 记录），实际为 {len(lines)} 行"
    # 简单校验表头字段
    header = lines[0]
    for col in ["timestamp", "status", "cpu_percent", "memory_mb"]:
        assert col in header, f"表头缺少列: {col}"


def test_metrics_json_write(tmp_path: Path):
    """
    测试 ProgressReporter 在启用心跳时能够写入 JSON 指标文件：
    - 启动心跳线程，等待采样
    - 停止心跳后检查 JSON 文件是否存在
    - 逐行解析 JSON，校验关键字段存在
    """
    logger = logging.getLogger("progress-test-json")
    logger.setLevel(logging.DEBUG)

    out_file = tmp_path / "metrics.json"
    pr = ProgressReporter(logger=logger)
    pr.configure_metrics(output_file=str(out_file), fmt="json")
    pr.start_heartbeat(interval_seconds=0.2)
    _wait_for_heartbeat(0.6)
    pr.stop_heartbeat()

    assert out_file.exists(), "JSON 指标文件未生成"
    lines = out_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1, "期望至少 1 条 JSON 记录"
    rec = json.loads(lines[-1])
    for key in ["timestamp", "status", "attempts", "messages", "cpu_percent", "memory_mb"]:
        assert key in rec, f"JSON 记录缺少字段: {key}"


def test_threshold_warnings(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """
    测试阈值告警逻辑：
    - 若 psutil 可用，则设置 CPU/内存阈值为 0，确保触发告警
    - 捕获日志，检查是否出现“达到阈值”的警告信息
    注：若 psutil 不可用，则跳过该测试用例。
    """
    if psutil is None:
        pytest.skip("psutil 不可用，跳过阈值告警测试")

    logger = logging.getLogger("progress-test-threshold")
    logger.setLevel(logging.DEBUG)
    caplog.set_level(logging.WARNING, logger="progress-test-threshold")

    out_file = tmp_path / "metrics_threshold.csv"
    pr = ProgressReporter(logger=logger)
    pr.configure_metrics(output_file=str(out_file), fmt="csv", cpu_threshold=0.0, mem_threshold_mb=0.0)
    pr.start_heartbeat(interval_seconds=0.2)
    _wait_for_heartbeat(0.6)
    pr.stop_heartbeat()

    # 至少应出现一条阈值相关警告日志
    warnings = [r for r in caplog.records if ("阈值" in r.message or "达到阈值" in r.message)]
    assert len(warnings) >= 1, "未捕获到阈值告警日志"