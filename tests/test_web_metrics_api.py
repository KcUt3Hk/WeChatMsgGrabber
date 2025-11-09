import os
import sys
import time
import json
import socket
import subprocess
from urllib.request import urlopen, Request
from .ui_utils import pick_free_port


def _wait_port_open(port: int, host: str = "127.0.0.1", timeout_sec: float = 15.0) -> bool:
    """
    等待指定端口在给定超时时间内变为可连接。

    参数：
    - port: 目标端口
    - host: 目标主机（默认 127.0.0.1）
    - timeout_sec: 总超时时间（秒，默认 15s；CI 环境下启动略慢更稳妥）

    返回：
    - bool: 端口是否在超时前打开

    函数级注释：
    - 使用 socket 进行连接测试，避免依赖第三方库；
    - 每 100ms 重试一次，最长等待 timeout_sec；
    - 将默认等待由 5s 提升至 15s，以适配 GitHub Actions/macOS 等环境偶发的慢启动。
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        s = socket.socket()
        s.settimeout(0.2)
        try:
            s.connect((host, port))
            s.close()
            return True
        except Exception:
            s.close()
            time.sleep(0.1)
    return False


def _start_server(preferred_port: int | None = None) -> tuple[subprocess.Popen, int]:
    """
    启动本地配置服务，返回子进程对象。

    参数：
    - preferred_port: 期望监听端口（可为空以自动选择可用端口）

    返回：
    - (subprocess.Popen, int): 正在运行的服务进程与实际端口

    函数级注释：
    - 优先使用用户指定的 Python 解释器路径；如果不存在则回退到 sys.executable；
    - 工作目录设置为项目根，便于服务定位 docs 与其他文件；
    - 不使用 shell，避免注入风险。
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 优先使用环境变量 PYTHON_BIN 指定的解释器路径；否则回退到当前进程解释器。
    env_pybin = os.environ.get("PYTHON_BIN", "").strip()
    pybin = env_pybin if (env_pybin and os.path.exists(env_pybin)) else sys.executable
    port = pick_free_port(preferred=preferred_port)
    cmd = [pybin, os.path.join(project_root, "web", "config_server.py"), "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=project_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert _wait_port_open(port), f"server not responding on port {port}"
    return proc, port


def _stop_server(proc: subprocess.Popen) -> None:
    """
    停止服务子进程。

    参数：
    - proc: 由 _start_server 返回的子进程对象

    函数级注释：
    - 发送 SIGINT（等价于 Ctrl+C）以触发优雅退出；
    - 若 1 秒内未退出，则调用 terminate 作为后备方案。
    """
    try:
        proc.send_signal(2)  # SIGINT
        for _ in range(10):
            if proc.poll() is not None:
                return
            time.sleep(0.1)
        proc.terminate()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _http_json(url: str, method: str = "GET", body: dict | None = None) -> dict:
    """
    简易 HTTP JSON 请求封装。

    参数：
    - url: 完整 URL
    - method: 请求方法（GET/POST）
    - body: POST JSON 请求体（字典）

    返回：
    - dict: 解析后的 JSON 响应

    函数级注释：
    - 使用标准库 urllib，避免额外依赖；
    - 在 POST 情况下自动设置 Content-Type 与编码；
    - 若响应非 200 或无法解析 JSON，将抛出异常以便测试失败可见。
    """
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    else:
        req = Request(url, method=method)
    with urlopen(req, timeout=5) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def test_metrics_api_basic_structure():
    """
    基础结构校验：确保 /api/metrics 返回包含 latency_ms_avg、cache_stats 与 counters 的对象。
    同时兼容旧字段名（detect_and_process_regions 与 ocr_engine_call）。
    """
    proc, port = _start_server(preferred_port=8010)
    base = f"http://127.0.0.1:{port}"
    try:
        data = _http_json(base + "/api/metrics", "GET")
        assert data.get("ok"), "ok flag missing"
        m = data.get("data", {})
        assert "latency_ms_avg" in m and isinstance(m["latency_ms_avg"], dict)
        assert "cache_stats" in m and isinstance(m["cache_stats"], dict)
        assert "counters" in m and isinstance(m["counters"], dict)

        lat = m["latency_ms_avg"]
        # 兼容新旧键名
        assert ("detect_regions" in lat) or ("detect_and_process_regions" in lat)
        assert ("ocr_engine" in lat) or ("ocr_engine_call" in lat)
    finally:
        _stop_server(proc)


def test_metrics_reset_and_file_source():
    """
    重置快照后再次请求应返回来源为 file 的指标数据。
    """
    proc, port = _start_server(preferred_port=8011)
    base = f"http://127.0.0.1:{port}"
    try:
        r = _http_json(base + "/api/metrics/reset", method="POST", body={})
        assert r.get("ok"), "reset failed"
        d = _http_json(base + "/api/metrics", method="GET")
        assert d.get("ok"), "metrics get failed"
        assert d.get("source") == "file", "expected source=file after reset"
        m = d.get("data", {})
        assert "latency_ms_avg" in m and isinstance(m["latency_ms_avg"], dict)
        assert "cache_stats" in m and isinstance(m["cache_stats"], dict)
        assert "counters" in m and isinstance(m["counters"], dict)
    finally:
        _stop_server(proc)


def test_metrics_snapshot_endpoint():
    """
    保存当前快照后再次请求应返回来源为 file，并且包含增强字段 schema_version 与 timestamp。
    """
    proc, port = _start_server(preferred_port=8012)
    base = f"http://127.0.0.1:{port}"
    try:
        r = _http_json(base + "/api/metrics/snapshot", method="POST", body={})
        assert r.get("ok"), "snapshot failed"
        assert isinstance(r.get("path"), str)

        d = _http_json(base + "/api/metrics", method="GET")
        assert d.get("ok"), "metrics get failed"
        assert d.get("source") == "file", "expected source=file after snapshot"
        assert "schema_version" in d
        assert "timestamp" in d
        m = d.get("data", {})
        assert isinstance(m, dict)
    finally:
        _stop_server(proc)