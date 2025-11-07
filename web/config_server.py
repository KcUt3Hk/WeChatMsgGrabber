#!/Users/pankkkk/Projects/Setting/python_envs/bin/python3.12
"""
项目：微信聊天导出助手（WeChat Chat Exporter）

简易配置服务（本地）：提供 Web 页面交互保存/加载 UI 配置到项目根目录。

功能与说明：
- 基于 http.server 实现，统一在同一端口提供静态页面与 API 服务；
- 静态页面目录：docs/（例如 ui_preview.html）；
- API：
  - POST /api/save-config  将页面参数保存为 ui_config.json，并生成 CLI 可读取的 config.json；
  - GET  /api/load-config  从项目根目录读取 ui_config.json 并返回给页面；

使用：
- 在项目根目录运行：
  /Users/pankkkk/Projects/Setting/python_envs/bin/python3.12 web/config_server.py --port 8003
- 打开浏览器访问：http://localhost:8003/ui_preview.html

注意：
- 该服务仅用于本地开发与配置管理；
- 页面与服务同源时无需 CORS，若跨域访问已添加基本的 CORS 头部。
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import datetime
import subprocess


# 项目根目录与静态目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")

# 为了能够复用 scripts/ 中的逻辑，这里将项目根目录加入 sys.path，便于 import
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    # 尝试复用脚本中的工具函数，以保持行为一致
    from scripts.list_latest_exports import get_project_root as _scripts_get_root
    from scripts.list_latest_exports import collect_files as _scripts_collect
    from scripts.list_latest_exports import describe_file as _scripts_describe
except Exception:
    _scripts_get_root = None
    _scripts_collect = None
    _scripts_describe = None


def _map_ui_to_cli_config(ui_data: dict) -> dict:
    """将 UI 配置（ui_config.json 格式）映射为 CLI 的 config.json 结构。

    参数：
      - ui_data: 从页面提交的 UI 配置字典

    返回：
      - config.json 对应的结构化字典（app/ocr/output）
    """
    # 选择主导出格式（若多选，取首个勾选的，否则 json）
    formats_dict = ui_data.get("formats", {}) or {}
    chosen_formats = [name for name, flag in formats_dict.items() if bool(flag)]
    primary_format = chosen_formats[0] if chosen_formats else "json"

    # scroll_delay 解析为 float
    sd_raw = str(ui_data.get("scroll_delay", "")).strip()
    try:
        scroll_delay_val = float(sd_raw) if sd_raw else 1.0
    except Exception:
        scroll_delay_val = 1.0

    # 输出目录
    outdir = str(ui_data.get("output_dir", "")).strip() or os.path.join(PROJECT_ROOT, "output")

    return {
        "app": {
            "scroll_speed": 2,
            "scroll_delay": scroll_delay_val,
            "max_retry_attempts": 3,
        },
        "ocr": {
            "language": str(ui_data.get("ocr_lang", "ch")).strip() or "ch",
            "confidence_threshold": 0.7,
        },
        "output": {
            "format": primary_format,
            "directory": outdir,
            "enable_deduplication": True,
            "formats": chosen_formats,
        }
    }


class ConfigHandler(SimpleHTTPRequestHandler):
    """自定义请求处理器：同时提供静态文件与配置 API。

    函数级注释：
    - 继承 SimpleHTTPRequestHandler，保留静态文件服务能力（docs/目录）；
    - 增加 API 路由：/api/save-config 与 /api/load-config；
    - 统一注入基本 CORS 头部，便于跨源调试；
    - 错误均返回 JSON，携带顶层 message 字段，同时提供结构化 error {code,message,hint,details}，并设置合理的 HTTP 状态码。
    """

    def end_headers(self):
        """在响应头末尾统一注入 CORS 头部"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        """响应预检请求（CORS）"""
        self.send_response(200)
        self.end_headers()

    def _send_json(self, obj: dict, code: int = 200):
        """发送 JSON 响应"""
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _send_error(self, err_code: str, message: str, http_status: int = 400, hint: str | None = None, details: dict | None = None):
        """统一发送错误响应。

        函数级注释：
        - 保持兼容：顶层仍包含 ok=False 与 message 字段；
        - 增加结构化 error 对象，包含 code/message/hint/details，便于前端或脚本统一处理；
        - 使用 http_status 设置 HTTP 状态码（如 400/403/404/500）；
        - 不改变成功响应的结构，避免破坏现有页面逻辑。

        参数：
          - err_code: 业务错误码（大写蛇形），如 UI_CONFIG_NOT_FOUND;
          - message: 人类可读的错误描述；
          - http_status: HTTP 状态码；
          - hint: 处理建议或指引；
          - details: 附加详情字典（例如路径、动作等）。
        """
        payload = {
            "ok": False,
            "message": message,
            "error": {
                "code": err_code,
                "message": message,
                "hint": hint,
                "details": details or {},
            }
        }
        self._send_json(payload, code=http_status)

    def do_GET(self):
        """处理 GET：
        - /api/load-config：返回 ui_config.json 内容；
        - /api/latest-exports：返回最新导出文件列表（output/ 与 outputs/）。
        - 其他路径：回退到静态文件服务。
        """
        parsed = urlparse(self.path)
        if parsed.path == "/api/load-config":
            ui_cfg_path = os.path.join(PROJECT_ROOT, "ui_config.json")
            if not os.path.exists(ui_cfg_path):
                self._send_error(
                    err_code="UI_CONFIG_NOT_FOUND",
                    message="未找到 ui_config.json",
                    http_status=404,
                    hint="请先在网页“保存配置”，或检查项目根目录下是否存在 ui_config.json。",
                    details={"path": ui_cfg_path}
                )
                return
            try:
                with open(ui_cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._send_json({"ok": True, "data": data})
            except Exception as e:
                self._send_error(
                    err_code="UI_CONFIG_READ_FAILED",
                    message=f"读取失败: {e}",
                    http_status=500,
                    hint="检查文件格式是否为合法 JSON。",
                    details={"path": ui_cfg_path}
                )
        elif parsed.path == "/api/latest-exports":
            # 最新导出列表：支持可选查询参数 limit（默认20）
            try:
                q = parse_qs(parsed.query)
                limit = int(q.get("limit", [20])[0])
                if limit <= 0:
                    limit = 20
            except Exception:
                limit = 20

            try:
                # 允许复用脚本中的工具函数，若不可用则使用本地实现
                root = Path(_scripts_get_root()) if _scripts_get_root else Path(PROJECT_ROOT)

                def _collect(dir_path: Path, n: int):
                    """收集指定目录的文件（倒序取前 n 条）。

                    函数级注释：
                    - 若已成功导入 scripts.list_latest_exports，则复用其中的 collect_files；
                    - 否则，本地实现按修改时间倒序排序并截取。
                    """
                    if _scripts_collect:
                        try:
                            return _scripts_collect(dir_path, n)
                        except Exception:
                            pass
                    if not dir_path.exists() or not dir_path.is_dir():
                        return []
                    files = [p for p in dir_path.iterdir() if p.is_file()]
                    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    return files[:n]

                def _describe(p: Path):
                    """返回文件描述信息字典。

                    函数级注释：
                    - 统一为 JSON 友好结构：name/path/mtime/dir；
                    - mtime 使用人类可读格式和时间戳两种；
                    - 兼容文件不存在的情况。
                    """
                    try:
                        mtime = p.stat().st_mtime
                        mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    except FileNotFoundError:
                        mtime = None
                        mtime_str = "<not found>"
                    return {
                        "name": p.name,
                        "path": str(p.resolve()),
                        "dir": str(p.parent.resolve()),
                        "mtime": mtime,
                        "mtime_str": mtime_str,
                    }

                targets = [root / "output", root / "outputs"]
                data = {}
                for t in targets:
                    key = t.name  # "output" 或 "outputs"
                    files = _collect(t, limit)
                    data[key] = [_describe(Path(p)) for p in files]

                self._send_json({"ok": True, "limit": limit, "data": data, "root": str(root)})
            except Exception as e:
                self._send_error(
                    err_code="LATEST_EXPORTS_QUERY_FAILED",
                    message=f"查询失败: {e}",
                    http_status=500,
                    hint="检查 output/ 与 outputs/ 目录是否存在且可读。",
                    details={"root": str(Path(PROJECT_ROOT).resolve())}
                )
        else:
            # 若是 /api/ 前缀但未匹配的路由，返回统一 JSON 错误；否则交由静态文件处理
            if parsed.path.startswith("/api/"):
                self._send_error(
                    err_code="API_NOT_FOUND",
                    message="未找到 API 路由",
                    http_status=404,
                    hint="请检查请求路径是否正确。",
                    details={"path": parsed.path}
                )
            else:
                # 静态文件：交由父类处理
                super().do_GET()

    def do_POST(self):
        """处理 POST：
        - /api/save-config：保存 ui_config.json 并生成 config.json。
        - /api/open-path：在 macOS 上调用 Finder 显示或打开文件（仅限项目根内的 output/ 与 outputs/）。
        """
        parsed = urlparse(self.path)
        if parsed.path == "/api/save-config":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8"))
            except Exception as e:
                self._send_error(
                    err_code="BAD_REQUEST_BODY",
                    message=f"请求体解析失败: {e}",
                    http_status=400,
                    hint="确保请求 Content-Type 为 application/json，且 JSON 格式正确。"
                )
                return

            # 保存 UI 配置
            ui_cfg_path = os.path.join(PROJECT_ROOT, "ui_config.json")
            try:
                with open(ui_cfg_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self._send_error(
                    err_code="UI_CONFIG_SAVE_FAILED",
                    message=f"保存 UI 配置失败: {e}",
                    http_status=500,
                    hint="检查写入权限或磁盘空间。",
                    details={"path": ui_cfg_path}
                )
                return

            # 生成 CLI 配置
            try:
                config_data = _map_ui_to_cli_config(payload)
                cfg_path = os.path.join(PROJECT_ROOT, "config.json")
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self._send_error(
                    err_code="CLI_CONFIG_GEN_FAILED",
                    message=f"生成 CLI 配置失败: {e}",
                    http_status=500,
                    hint="请检查 UI 配置中字段是否有效。",
                    details={"path": os.path.join(PROJECT_ROOT, "config.json")}
                )
                return

            self._send_json({"ok": True, "message": "配置已保存", "paths": {"ui": ui_cfg_path, "cli": os.path.join(PROJECT_ROOT, "config.json")}})
        elif parsed.path == "/api/open-path":
            # 仅允许在 macOS 上运行
            if not sys.platform.startswith("darwin"):
                self._send_error(
                    err_code="NON_MACOS",
                    message="仅支持在 macOS 上运行",
                    http_status=400,
                    hint="该操作依赖 macOS Finder。"
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8"))
            except Exception as e:
                self._send_error(
                    err_code="BAD_REQUEST_BODY",
                    message=f"请求体解析失败: {e}",
                    http_status=400,
                    hint="确保请求 Content-Type 为 application/json，且 JSON 格式正确。"
                )
                return

            target_path = str(payload.get("path", "")).strip()
            action = str(payload.get("action", "reveal")).strip()  # reveal | open
            if not target_path:
                self._send_error(
                    err_code="PATH_EMPTY",
                    message="path 不能为空",
                    http_status=400,
                    hint="请传入要显示或打开的绝对路径。"
                )
                return

            # 路径安全校验：必须位于项目根目录且在 output/ 或 outputs/ 下
            root = Path(PROJECT_ROOT).resolve()
            p = Path(target_path).resolve()
            try:
                p.relative_to(root)
            except Exception:
                self._send_error(
                    err_code="PATH_OUTSIDE_ROOT",
                    message="拒绝访问项目根目录之外的路径",
                    http_status=403,
                    hint="仅允许访问项目根目录下的 output/ 与 outputs/。",
                    details={"root": str(root), "path": str(p)}
                )
                return
            allowed_dirs = {root / "output", root / "outputs"}
            if not any(str(p).startswith(str(d)) for d in allowed_dirs):
                self._send_error(
                    err_code="PATH_NOT_ALLOWED",
                    message="仅允许操作 output/ 与 outputs/ 目录内的文件",
                    http_status=403,
                    hint="请确认目标路径以 output/ 或 outputs/ 开头。",
                    details={"path": str(p)}
                )
                return

            # 具体操作
            try:
                if action == "reveal":
                    # Finder 中显示指定文件
                    subprocess.check_call(["open", "-R", str(p)])
                elif action == "open":
                    # 打开文件或目录
                    subprocess.check_call(["open", str(p)])
                else:
                    self._send_error(
                        err_code="ACTION_UNSUPPORTED",
                        message="action 仅支持 reveal 或 open",
                        http_status=400,
                        hint="reveal: 访达高亮显示；open: 打开文件或目录。",
                        details={"action": action}
                    )
                    return
                self._send_json({"ok": True, "message": "已在访达中处理", "path": str(p), "action": action})
            except subprocess.CalledProcessError as e:
                self._send_error(
                    err_code="SYSTEM_CMD_FAILED",
                    message=f"系统命令失败: {e}",
                    http_status=500,
                    hint="请检查文件是否存在、是否有权限或 Finder 是否可用。",
                    details={"path": str(p), "action": action}
                )
            except Exception as e:
                self._send_error(
                    err_code="PROCESSING_FAILED",
                    message=f"处理失败: {e}",
                    http_status=500,
                    hint="未知错误，请查看终端日志。",
                    details={"path": str(p), "action": action}
                )
        else:
            self._send_error(
                err_code="API_NOT_FOUND",
                message="未找到 API 路由",
                http_status=404,
                hint="请检查请求路径是否正确。",
                details={"path": parsed.path}
            )


def run_server(port: int = 8003) -> int:
    """启动配置服务与静态页面服务。

    参数：
      - port: 监听端口（默认 8003）

    返回：
      - 进程退出码：0 表示成功；1 表示端口占用或启动失败。

    函数级注释：
      - 将工作目录切换到 docs 以复用父类的静态文件处理能力；
      - 在绑定端口时捕获 OSError（如 macOS 的 Errno 48），并输出友好提示与处理建议；
      - 返回非零退出码以便外部脚本/CI 检测失败原因。
    """
    # 将工作目录切换到 docs，便于父类处理静态文件
    os.chdir(DOCS_DIR)
    handler_cls = ConfigHandler
    try:
        httpd = HTTPServer(("", port), handler_cls)
    except OSError as e:
        # 常见错误：地址已被占用（macOS: Errno 48，Linux: Errno 98）
        err = getattr(e, "errno", None)
        print(f"[ERROR] 端口 {port} 绑定失败：{e} (errno={err})")
        print("提示：该端口可能已被占用。可尝试：")
        print("  1) 使用 --port 指定备用端口，例如 --port 8004")
        print("  2) 停止占用该端口的进程后重试")
        print(f"示例：/Users/pankkkk/Projects/Setting/python_envs/bin/python3.12 web/config_server.py --port 8004")
        return 1

    print(f"Serving config server at http://localhost:{port}/ (docs dir: {DOCS_DIR})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        httpd.server_close()
    return 0


def parse_args(argv: list[str]) -> int:
    """解析命令行参数并启动服务。

    参数：
      - argv: 命令行参数（不含程序名）

    返回：
      - 进程退出码 0 表示成功
    """
    import argparse
    parser = argparse.ArgumentParser(description="本地配置服务：提供保存/加载 UI 配置的 API")
    parser.add_argument("--port", type=int, default=8003, help="服务端口（默认 8003）")
    args = parser.parse_args(argv)
    return run_server(port=args.port)


def main() -> int:
    """程序入口：启动本地配置服务"""
    return parse_args(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())