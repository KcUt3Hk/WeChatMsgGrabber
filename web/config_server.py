"""
本地配置服务（简化版）：
- 提供 UI 预览页（GET /ui_preview.html），页面文件位于 docs/ui_preview.html；
- 提供性能指标相关接口：
  * GET  /api/metrics         返回当前指标（优先读取项目根目录 metrics.json）
  * POST /api/metrics/reset   将指标重置为零值并写入 metrics.json
  * POST /api/metrics/snapshot 将当前指标写入 metrics.json（生成快照元信息）

设计目标：满足 tests/test_web_metrics_api.py 与 tests/test_ui_preview_playwright.py 的断言与交互需求；
实现尽量依赖标准库，避免额外依赖，便于在 CI/macOS 环境稳定运行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import subprocess


# 项目根目录：web/ 的上一级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 指标快照文件路径（tests 会在项目根写入 metrics.json，服务需读取此文件）
METRICS_FILE = os.path.join(PROJECT_ROOT, "metrics.json")
# UI 预览页实际存放位置
UI_PREVIEW_PATH = os.path.join(PROJECT_ROOT, "docs", "ui_preview.html")


def _utc_now_iso() -> str:
    """
    函数级注释：
    - 返回当前 UTC 时间的 ISO8601 字符串，末尾附加 'Z'；
    - 用于响应中的 timestamp 字段，便于页面展示“快照时间”。
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_metrics() -> dict:
    """
    函数级注释：
    - 生成一个结构完整的零值指标对象，满足页面与测试的键结构要求；
    - 命中率设为 0.0，以便在重置后页面显示为“metric-bad”。
    """
    return {
        "latency_ms_avg": {
            "process_image": 0.0,
            # 保留新键名；旧键名在测试中仅为兼容检查之一
            "detect_regions": 0.0,
            "ocr_engine": 0.0,
        },
        "cache_stats": {
            "full_image_cache": {"size": 0, "capacity": 0, "hit_rate": 0.0, "hits": 0, "misses": 0, "evictions": 0},
            "region_cache": {"size": 0, "capacity": 0, "hit_rate": 0.0, "hits": 0, "misses": 0, "evictions": 0},
            "ocr_cache": {"size": 0, "capacity": 0, "hit_rate": 0.0, "hits": 0, "misses": 0, "evictions": 0},
        },
        "counters": {
            "process_image_calls": 0,
            "detect_regions_calls": 0,
            "ocr_engine_calls": 0,
        },
    }


def _read_metrics_from_file() -> dict | None:
    """
    函数级注释：
    - 若 metrics.json 存在则读取并解析；失败时返回 None；
    - 只做轻量校验：须可解析为 dict，且包含核心键（latency_ms_avg/cache_stats/counters）。
    """
    if not os.path.exists(METRICS_FILE):
        return None
    try:
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return None
        # 允许数据直接是核心结构，或包裹在 {data:{...}} 中（更宽松以兼容不同来源）
        data = obj.get("data", obj)
        if not (isinstance(data, dict) and "latency_ms_avg" in data and "cache_stats" in data and "counters" in data):
            return None
        return data
    except Exception:
        return None


def _write_metrics_to_file(data: dict) -> str:
    """
    函数级注释：
    - 将给定指标数据写入 metrics.json（项目根目录），并返回文件路径；
    - 写入格式：顶层对象包含 schema_version、timestamp 与 data（实际指标）。
    """
    payload = {
        "schema_version": "1.0",
        "timestamp": _utc_now_iso(),
        "data": data,
    }
    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return METRICS_FILE


class _Handler(BaseHTTPRequestHandler):
    """
    函数级注释：
    - 处理 UI 预览页与指标相关 API；
    - 所有响应均尽量提供明确的 Content-Type 并使用 UTF-8 编码；
    - 关闭默认日志中的客户端地址输出，避免 CI 日志过于冗长。
    """

    server_version = "WXMsgGrabberConfigServer/0.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A003 (shadow-builtin)
        """
        函数级注释：
        - 精简服务日志输出，保留必要信息；
        - 避免在 CI 上产生日志噪音。
        """
        sys.stdout.write((format % args) + "\n")

    def _write_json(self, obj: dict, status: int = 200) -> None:
        """
        函数级注释：
        - 将对象以 JSON 格式写回客户端；
        - 设置 Content-Type 为 application/json；
        - 统一使用 UTF-8 编码。
        """
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        """
        函数级注释：
        - 读取并解析请求体为 JSON；当无内容或解析失败时返回空 dict；
        - 仅支持 application/json，其他 Content-Type 也尝试解析，保持宽容。
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _write_html_file(self, path: str) -> None:
        """
        函数级注释：
        - 读取并返回本地 HTML 文件内容；不存在时返回 404。
        """
        if not os.path.exists(path):
            self.send_error(404, "Not Found")
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._write_json({"ok": False, "error": str(e)}, status=500)

    def do_GET(self) -> None:  # noqa: N802 (mixedCase)
        """
        函数级注释：
        - 路由：/ui_preview.html、/api/metrics、/api/latest-exports、/api/load-config；
        - /api/metrics：优先读取 metrics.json；不存在则返回零值并标记来源为 generated。
        """
        parsed = urlparse(self.path)
        if parsed.path == "/ui_preview.html":
            return self._write_html_file(UI_PREVIEW_PATH)

        if parsed.path == "/api/metrics":
            data = _read_metrics_from_file()
            source = "file" if data is not None else "generated"
            if data is None:
                data = _default_metrics()
            resp = {
                "ok": True,
                "source": source,
                "schema_version": "1.0",
                "timestamp": _utc_now_iso(),
                "data": data,
            }
            return self._write_json(resp)

        if parsed.path == "/api/latest-exports":
            """
            函数级注释：
            - 返回项目根目录下可能的导出文件列表（示例实现：扫描 exports/ 与 tmp/）；
            - 结构：{ ok, files: [{path, mtime}] }，UI 可用于展示“最新导出”。
            """
            candidates = []
            for d in (os.path.join(PROJECT_ROOT, "exports"), os.path.join(PROJECT_ROOT, "tmp")):
                if not os.path.isdir(d):
                    continue
                try:
                    for name in os.listdir(d):
                        p = os.path.join(d, name)
                        if os.path.isfile(p):
                            try:
                                stat = os.stat(p)
                                candidates.append({"path": p, "mtime": int(stat.st_mtime)})
                            except Exception:
                                pass
                except Exception:
                    pass
            candidates.sort(key=lambda x: x["mtime"], reverse=True)
            return self._write_json({"ok": True, "files": candidates})

        if parsed.path == "/api/load-config":
            """
            函数级注释：
            - 读取项目根目录 config.json（若不存在则返回默认配置）；
            - 结构：{ ok, config }，其中 config 仅为示例字段，供 UI 表单回填使用。
            """
            cfg_path = os.path.join(PROJECT_ROOT, "config.json")
            default_cfg = {
                "python_path": "",
                "auto_refresh": True,
                "thresholds": {
                    "latency.high_ms": 2000,
                    "cache.hit_rate.bad": 0.5,
                },
            }
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        default_cfg.update(loaded)
                except Exception:
                    pass
            return self._write_json({"ok": True, "config": default_cfg})

        # 其余路径：简单 404
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802 (mixedCase)
        """
        函数级注释：
        - 路由：/api/metrics/reset、/api/metrics/snapshot、/api/save-config、/api/open-path；
        - reset：写入零值指标并返回 ok/path；
        - snapshot：读取当前或默认指标，写入文件并返回 ok/path。
        """
        parsed = urlparse(self.path)
        if parsed.path == "/api/metrics/reset":
            path = _write_metrics_to_file(_default_metrics())
            return self._write_json({"ok": True, "path": path})

        if parsed.path == "/api/metrics/snapshot":
            cur = _read_metrics_from_file()
            data = cur if cur is not None else _default_metrics()
            path = _write_metrics_to_file(data)
            return self._write_json({"ok": True, "path": path})

        if parsed.path == "/api/save-config":
            """
            函数级注释：
            - 接收 JSON 配置并写入项目根目录 config.json；
            - 返回 { ok, path } 以便页面提示保存位置。
            """
            cfg = self._read_json_body()
            cfg_path = os.path.join(PROJECT_ROOT, "config.json")
            try:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                return self._write_json({"ok": True, "path": cfg_path})
            except Exception as e:
                return self._write_json({"ok": False, "error": str(e)}, status=500)

        if parsed.path == "/api/open-path":
            """
            函数级注释：
            - 在 macOS 上尝试通过 `open` 命令打开指定路径；
            - 为安全起见，仅允许打开位于项目根目录下的路径；
            - 返回 { ok, opened }。
            """
            body = self._read_json_body()
            p = body.get("path", "")
            if not p:
                return self._write_json({"ok": False, "error": "missing path"}, status=400)
            # 归一化并限制到项目根目录
            try:
                ap = os.path.abspath(p)
                if not ap.startswith(PROJECT_ROOT):
                    return self._write_json({"ok": False, "error": "path not under project root"}, status=403)
                # 在 CI/headless 环境下，忽略实际打开失败，不抛错
                try:
                    subprocess.run(["open", ap], check=False)
                    opened = True
                except Exception:
                    opened = False
                return self._write_json({"ok": True, "opened": opened, "path": ap})
            except Exception as e:
                return self._write_json({"ok": False, "error": str(e)}, status=500)

        # 其余未实现的接口返回 404（按需扩展）
        self.send_error(404, "Not Found")


def run_server(port: int) -> None:
    """
    函数级注释：
    - 启动线程化 HTTP 服务器并在指定端口监听；
    - 支持 Ctrl+C（SIGINT）优雅退出；
    - 在 stdout 打印启动提示，便于调试与 CI 日志查看。
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"配置服务已启动：http://localhost:{port}/ui_preview.html")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.server_close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    """
    函数级注释：
    - 解析命令行参数并启动服务器；
    - 支持 --port 设置监听端口（默认 8003）。
    """
    parser = argparse.ArgumentParser(description="WeChatMsgGrabber 本地配置服务")
    parser.add_argument("--port", type=int, default=8003, help="监听端口（默认 8003）")
    args = parser.parse_args(argv)
    run_server(args.port)
    return 0


if __name__ == "__main__":
    # 允许通过用户指定的解释器路径运行；不强制 sys.executable，保持测试的灵活性。
    sys.exit(main())