import os
import re
import sys
import json
import time
import subprocess
from pathlib import Path
import pytest
from .ui_utils import (
    register_page,
    register_context,
    wait_for_server_ready,
    wait_for_selector_safe,
    wait_for_metrics_fetch,
    wait_for_text_change,
    wait_for_text_changes_n,
    pick_free_port,
    safe_click,
)

from playwright.sync_api import sync_playwright

# 选择 Python 解释器路径（优先使用用户指定路径，CI 环境下回退到 sys.executable）
# 函数级注释：
# - 若环境变量 PYTHON_BIN 存在，优先使用；
# - 否则回退到 sys.executable，确保在 CI/macOS 上可用。
_ENV_BIN = os.environ.get("PYTHON_BIN", "").strip()
PYTHON_BIN = _ENV_BIN or sys.executable

# 项目根目录（tests/ 的上一级目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _write_sample_metrics(snapshot_path: Path) -> None:
    """
    函数级注释：
    - 在项目根目录写入一个可控的 metrics.json，用于稳定的 UI 断言；
    - 命中率分别设置为 0.75、0.50、0.20，覆盖良好/告警/糟糕三类高亮场景；
    - 计数与耗时字段可为占位值，UI 将通过 safeNum 处理缺省键。
    """
    sample = {
        "latency_ms_avg": {
            "process_image": 12.34,
            "detect_regions": 45.67,
            "ocr_engine": 78.90
        },
        "cache_stats": {
            "full_image_cache": {"size": 10, "capacity": 100, "hit_rate": 0.75, "hits": 75, "misses": 25, "evictions": 5},
            "region_cache": {"size": 20, "capacity": 200, "hit_rate": 0.50, "hits": 100, "misses": 100, "evictions": 10},
            "ocr_cache": {"size": 30, "capacity": 300, "hit_rate": 0.20, "hits": 60, "misses": 240, "evictions": 30}
        },
        "counters": {
            "process_image_calls": 1,
            "detect_regions_calls": 1,
            "ocr_engine_calls": 1
        }
    }
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)


def _start_config_server(preferred_port: int = 8010) -> tuple[subprocess.Popen, int]:
    """
    函数级注释：
    - 在独立子进程中启动 web/config_server.py；
    - 优先使用 preferred_port，若端口被占用则自动选择一个空闲端口；
    - 返回 (Popen, 实际端口) 供后续页面访问与进程清理。
    """
    port = pick_free_port(preferred=preferred_port)
    cmd = [PYTHON_BIN, str(PROJECT_ROOT / "web" / "config_server.py"), "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # 稳健等待服务就绪（轮询 /api/metrics）
    try:
        wait_for_server_ready(port=port, timeout=15.0, interval=0.2)
    except Exception:
        # 若就绪检查失败，仍返回进程句柄，后续测试会显式失败并保存诊断附件
        pass
    return proc, port


def _create_page(headless: bool = None):
    """
    函数级注释：
    - 启动 Chromium（可通过环境变量 UI_HEADLESS 控制无头与否，默认无头模式），开启 accept_downloads 以捕获下载；
    - 返回 (pw, browser, context, page) 以便测试中使用与关闭。
    """
    # 根据环境变量决定是否无头运行：UI_HEADLESS=0/false 代表有头，其余视为无头
    if headless is None:
        raw = str(os.environ.get("UI_HEADLESS", "1")).lower().strip()
        headless = not (raw in ("0", "false", "no"))
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless)
    # 将视频录制保存到项目 reports/videos 下，便于 CI 上传
    videos_dir = PROJECT_ROOT / "reports" / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(
        accept_downloads=True,
        viewport={"width": 1280, "height": 800},
        record_video_dir=str(videos_dir)
    )
    # 启用 Trace 捕捉：截图、快照与源码
    try:
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
    except Exception:
        pass
    page = context.new_page()
    # 注册页面用于失败时自动截图
    register_page(page)
    # 注册上下文用于失败时保存 trace
    register_context(context)
    return pw, browser, context, page


def _close_page(pw, browser, context):
    """
    函数级注释：
    - 关闭页面上下文与浏览器，并停止 Playwright 运行时；
    - 确保资源释放，避免测试间互相影响。
    """
    try:
        context.close()
    except Exception:
        pass
    try:
        browser.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass


@pytest.mark.ui
def test_metrics_meta_display(tmp_path):
    """
    标记：UI 用例。
    功能：验证“性能指标”卡片中元信息（来源/版本/快照时间）展示正确。

    步骤：
    1) 写入受控的 metrics.json；
    2) 启动配置服务并打开 UI 预览页；
    3) 点击刷新并断言 #metrics_meta 文本包含“文件快照 (metrics.json)”与 schema 版本、时间字符串。
    """
    snapshot_path = PROJECT_ROOT / "metrics.json"
    _write_sample_metrics(snapshot_path)
    proc, port = _start_config_server(preferred_port=8010)
    try:
        pw, browser, context, page = _create_page(headless=True)
        try:
            page.goto(f"http://localhost:{port}/ui_preview.html", timeout=15000, wait_until="domcontentloaded")
            # 确保抓取一次指标并等待渲染
            wait_for_metrics_fetch(page, timeout_ms=15000)
            meta_text = page.locator("#metrics_meta").inner_text()
            assert "来源：文件快照 (metrics.json)" in meta_text
            assert "schema：" in meta_text
            assert "快照时间：" in meta_text
        finally:
            _close_page(pw, browser, context)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            snapshot_path.unlink()
        except Exception:
            pass


@pytest.mark.ui
def test_snapshot_save_and_download_filename(tmp_path):
    """
    验证“保存当前快照”“下载当前快照”按钮行为与文件名格式。

    断言点：
    - 点击“下载当前快照”可捕获下载，建议文件名匹配 metrics_snapshot_YYYY-MM-DD-HH-MM-SS[Z].json；
    - 将下载保存到临时目录，确保文件创建成功。
    """
    snapshot_path = PROJECT_ROOT / "metrics.json"
    _write_sample_metrics(snapshot_path)
    proc, port = _start_config_server(preferred_port=8010)
    try:
        pw, browser, context, page = _create_page(headless=True)
        try:
            page.goto(f"http://localhost:{port}/ui_preview.html", timeout=15000, wait_until="domcontentloaded")
            wait_for_metrics_fetch(page, timeout_ms=15000)

            # 先点击“保存当前快照（写入文件）”，并等待 API 完成
            with page.expect_response(lambda r: r.url.endswith("/api/metrics/snapshot") and r.status in (200, 204), timeout=15000):
                safe_click(page, "#btn_metrics_save_snapshot", timeout_ms=15000)

            # 期望下载文件并校验文件名
            with page.expect_download() as dl_info:
                safe_click(page, "#btn_metrics_download", timeout_ms=15000)
            download = dl_info.value
            fname = download.suggested_filename
            assert re.match(r"^metrics_snapshot_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}Z?\.json$", fname)
            save_path = tmp_path / fname
            download.save_as(str(save_path))
            assert save_path.exists()
        finally:
            _close_page(pw, browser, context)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            snapshot_path.unlink()
        except Exception:
            pass


@pytest.mark.ui
def test_threshold_highlight_effect(tmp_path):
    """
    验证命中率阈值设置（良好/告警/糟糕）对命中率高亮的影响。

    策略：
    - 使用受控指标（0.75/0.50/0.20）并通过“保存阈值”触发渲染；
    - 设置 good=0, bad=0 → 期望全部为 metric-good；
    - 设置 good=1, bad=0 → 期望全部为 metric-warn；
    - 设置 good=0.99, bad=0.90 → 期望全部为 metric-bad。
    """
    snapshot_path = PROJECT_ROOT / "metrics.json"
    _write_sample_metrics(snapshot_path)
    proc, port = _start_config_server(preferred_port=8010)
    try:
        pw, browser, context, page = _create_page(headless=True)
        try:
            page.goto(f"http://localhost:{port}/ui_preview.html", timeout=15000, wait_until="domcontentloaded")
            wait_for_metrics_fetch(page, timeout_ms=15000)

            # 场景一：全部 good
            wait_for_selector_safe(page, "#metrics_thr_good", timeout_ms=15000)
            wait_for_selector_safe(page, "#metrics_thr_bad", timeout_ms=15000)
            page.fill("#metrics_thr_good", "0")
            page.fill("#metrics_thr_bad", "0")
            safe_click(page, "text=保存阈值", timeout_ms=15000)
            wait_for_selector_safe(page, ".metric-tag.metric-good", timeout_ms=15000)
            good_count = page.locator(".metric-tag.metric-good").count()
            assert good_count >= 3

            # 场景二：全部 warn
            page.fill("#metrics_thr_good", "1")
            page.fill("#metrics_thr_bad", "0")
            safe_click(page, "text=保存阈值", timeout_ms=15000)
            wait_for_selector_safe(page, ".metric-tag.metric-warn", timeout_ms=15000)
            warn_count = page.locator(".metric-tag.metric-warn").count()
            assert warn_count >= 3

            # 场景三：全部 bad
            page.fill("#metrics_thr_good", "0.99")
            page.fill("#metrics_thr_bad", "0.90")
            safe_click(page, "text=保存阈值", timeout_ms=15000)
            wait_for_selector_safe(page, ".metric-tag.metric-bad", timeout_ms=15000)
            bad_count = page.locator(".metric-tag.metric-bad").count()
            assert bad_count >= 3
        finally:
            _close_page(pw, browser, context)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            snapshot_path.unlink()
        except Exception:
            pass


@pytest.mark.ui
def test_auto_refresh_updates_last_fetch(tmp_path):
    """
    验证“自动刷新”功能会周期性更新“上次拉取时间”显示。

    策略：
    - 设置刷新间隔为 1 秒并启用自动刷新；
    - 观察 #metrics_last_fetch 文本在 6 秒内至少发生两次变化。
    """
    snapshot_path = PROJECT_ROOT / "metrics.json"
    _write_sample_metrics(snapshot_path)
    proc, port = _start_config_server(preferred_port=8011)
    try:
        pw, browser, context, page = _create_page(headless=True)
        try:
            page.goto(f"http://localhost:{port}/ui_preview.html", timeout=15000, wait_until="domcontentloaded")
            # 选择 1 秒刷新间隔并启用自动刷新
            wait_for_selector_safe(page, "#metrics_refresh_interval", timeout_ms=15000)
            page.select_option("#metrics_refresh_interval", "1000")
            wait_for_selector_safe(page, "#metrics_autorefresh", timeout_ms=15000)
            page.check("#metrics_autorefresh")

            # 使用更稳健的多次变化等待（目标总耗时 ≤ 5s）
            changes = wait_for_text_changes_n(page, "#metrics_last_fetch", min_changes=2, timeout_ms=5000, interval_ms=150)
            assert len(changes) >= 2
            # 文本应当每次不同
            assert len(set(changes)) == len(changes)
        finally:
            _close_page(pw, browser, context)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            snapshot_path.unlink()
        except Exception:
            pass


@pytest.mark.ui
def test_reset_metrics_sets_zero_and_bad_tags(tmp_path):
    """
    验证“重置计数（写入快照）”将快照写为零值，并在 UI 中将命中率渲染为 0.0%（metric-bad）。

    断言点：
    - 点击“重置计数（写入快照）”后刷新，页面中三处命中率标签均为 metric-bad；
    - 命中率文本均为 0.0%；
    - 快照文件的修改时间发生变化（写入成功）。
    """
    snapshot_path = PROJECT_ROOT / "metrics.json"
    _write_sample_metrics(snapshot_path)
    before_mtime = snapshot_path.stat().st_mtime
    proc, port = _start_config_server(preferred_port=8012)
    try:
        pw, browser, context, page = _create_page(headless=True)
        try:
            page.goto(f"http://localhost:{port}/ui_preview.html", timeout=15000, wait_until="domcontentloaded")
            wait_for_metrics_fetch(page, timeout_ms=15000)

            # 触发重置并等待 API 完成，然后刷新并等待指标返回
            with page.expect_response(lambda r: r.url.endswith("/api/metrics/reset") and r.status in (200, 204), timeout=15000):
                safe_click(page, "#btn_metrics_reset", timeout_ms=15000)
            wait_for_metrics_fetch(page, timeout_ms=15000)

            # 三处命中率应为 metric-bad，文本为 0.0%
            bad_count = page.locator(".metric-tag.metric-bad").count()
            assert bad_count >= 3
            texts = [t.strip() for t in page.locator(".metric-tag").all_inner_texts()]
            assert len(texts) >= 3
            assert set(texts) == {"0.0%"}

            # 快照文件修改时间应更新
            after_mtime = snapshot_path.stat().st_mtime
            assert after_mtime > before_mtime
        finally:
            _close_page(pw, browser, context)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            snapshot_path.unlink()
        except Exception:
            pass