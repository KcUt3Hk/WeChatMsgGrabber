import argparse
import json
import os
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
METRICS_PATH = PROJECT_ROOT / "metrics.json"
UI_PATH = Path(__file__).resolve().parent / "ui_preview.html"
SCHEMA_VERSION = 1


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _download_filename() -> str:
    return datetime.now(timezone.utc).strftime("metrics_snapshot_%Y-%m-%d-%H-%M-%SZ.json")


def _default_metrics() -> dict:
    return {
        "latency_ms_avg": {
            "process_image": 0.0,
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


def _read_metrics() -> tuple[dict, str]:
    if METRICS_PATH.exists():
        try:
            return json.loads(METRICS_PATH.read_text(encoding="utf-8")), "file"
        except Exception:
            return _default_metrics(), "file"
    return _default_metrics(), "memory"


def _write_metrics(metrics: dict) -> None:
    METRICS_PATH.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


class _Handler(BaseHTTPRequestHandler):
    server_version = "wechatmsgg-config-server"

    def _send_json(self, payload: dict, status: int = 200, headers: dict | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _read_body_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except Exception:
            length = 0
        if length <= 0:
            return {}
        data = self.rfile.read(length)
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/api/metrics":
            metrics, source = _read_metrics()
            self._send_json(
                {
                    "ok": True,
                    "source": source,
                    "schema_version": SCHEMA_VERSION,
                    "timestamp": _utc_timestamp(),
                    "data": metrics,
                }
            )
            return

        if self.path == "/api/metrics/download":
            metrics, source = _read_metrics()
            payload = {
                "schema_version": SCHEMA_VERSION,
                "timestamp": _utc_timestamp(),
                "source": source,
                "data": metrics,
            }
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            fname = _download_filename()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return

        if self.path == "/ui_preview.html":
            try:
                html = UI_PATH.read_bytes()
            except Exception:
                html = b"<!doctype html><meta charset='utf-8'><title>ui_preview</title><body>missing ui_preview.html</body>"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html)
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"not found")

    def do_POST(self):
        if self.path == "/api/metrics/reset":
            _ = self._read_body_json()
            metrics = _default_metrics()
            _write_metrics(metrics)
            self._send_json({"ok": True, "path": str(METRICS_PATH)})
            return

        if self.path == "/api/metrics/snapshot":
            _ = self._read_body_json()
            metrics, _source = _read_metrics()
            fname = _download_filename()
            out_path = PROJECT_ROOT / fname
            payload = {
                "schema_version": SCHEMA_VERSION,
                "timestamp": _utc_timestamp(),
                "source": "file" if METRICS_PATH.exists() else _source,
                "data": metrics,
            }
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self._send_json({"ok": True, "path": str(out_path)})
            return

        self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args):
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    port = int(args.port)
    host = "127.0.0.1"
    httpd = HTTPServer((host, port), _Handler)
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

