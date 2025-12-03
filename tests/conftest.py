"""
Pytest configuration and shared fixtures for WeChatMsgGraber tests.
"""
import pytest
import logging
import tempfile
import shutil
import os
import sys
from PIL import Image
import pygetwindow as gw
from datetime import datetime
from pathlib import Path
try:
    from pytest_html import extras as html_extras
except Exception:
    html_extras = None
from .ui_utils import get_last_page, get_last_context, clear_last_page, clear_last_context
"""
将项目根目录加入 Python 导入路径，确保在以 tests 目录为起点执行时，
可以正常导入位于项目根目录下的内部模块（如 services/*）。
这在某些 CI 或 IDE 运行环境中尤为必要。
"""
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.auto_scroll_controller import AutoScrollController


def _is_ci_env() -> bool:
    """判断当前是否为 CI 环境（如 GitHub Actions）。

    规则：当环境变量 CI=true 或 GITHUB_ACTIONS=true 时，认为是 CI 环境。
    在 CI 环境下，测试应尽量保持稳定且可复现，不依赖真实桌面窗口状态。
    """
    return str(os.environ.get('CI', '')).lower() == 'true' or str(os.environ.get('GITHUB_ACTIONS', '')).lower() == 'true'


def _get_wechat_test_mode() -> str:
    """获取 WeChat 测试模式。

    支持的模式：
    - auto（默认）：本地环境下根据真实窗口状态自适应跳过需要“微信关闭”的用例；CI 环境下不跳过；
    - force_not_found：强制模拟“未找到窗口”的场景（不跳过相关用例）。

    返回值为小写字符串，默认 'auto'。
    """
    return str(os.environ.get('WECHAT_TEST_MODE', 'auto')).lower()


def _has_wechat_window_open() -> bool:
    """检测当前系统是否存在已打开的微信窗口（通过业务逻辑复用）。

    为保证与实际定位逻辑一致，直接调用 AutoScrollController.locate_wechat_window；
    若返回非 None，视为“已打开”。任何异常均视为“未检测到”。
    """
    try:
        ctrl = AutoScrollController()
        return ctrl.locate_wechat_window() is not None
    except Exception:
        logging.getLogger(__name__).warning("通过 AutoScrollController 检测微信窗口时发生异常，默认视为未打开")
        return False


def pytest_sessionstart(session):
    """
    函数级注释：
    - 在测试会话开始时准备 reports 子目录，并根据环境变量 UI_CLEAN_REPORTS 清理旧的截图/视频/trace 文件；
    - 目录结构：reports/screenshots、reports/videos、reports/traces；
    - UI_CLEAN_REPORTS：默认开启（"1"/"true"/"yes"），若关闭则保留历史文件以便排查长期问题。
    """
    project_root = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    reports = project_root / "reports"
    clean = str(os.environ.get("UI_CLEAN_REPORTS", "1")).lower() in ("1", "true", "yes")
    for sub in ("screenshots", "videos", "traces"):
        d = reports / sub
        d.mkdir(parents=True, exist_ok=True)
        if clean:
            for p in d.iterdir():
                try:
                    if p.is_file() or p.is_symlink():
                        p.unlink()
                    elif p.is_dir():
                        shutil.rmtree(p)
                except Exception as e:
                    logging.getLogger(__name__).warning(f"清理 reports/{sub} 失败：{e}")


def pytest_collection_modifyitems(config, items):
    """在测试收集阶段根据环境对标记为 requires_wechat_closed 的用例进行自适应跳过。

    策略：
    - CI 环境：不跳过，始终验证逻辑，避免受本地桌面影响；
    - 本地环境（默认模式 auto）：若检测到微信窗口已打开，则跳过需要“微信关闭”的用例；
    - 本地环境（强制模式 force_not_found）：不跳过。
    """
    is_ci = _is_ci_env()
    mode = _get_wechat_test_mode()
    should_skip = (not is_ci) and (mode != 'force_not_found') and _has_wechat_window_open()

    if should_skip:
        skip_reason = "检测到当前有 WeChat 活动窗口，跳过标记为 requires_wechat_closed 的用例。"
        skip_marker = pytest.mark.skip(reason=skip_reason)
        for item in items:
            if item.get_closest_marker("requires_wechat_closed"):
                item.add_marker(skip_marker)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    函数级注释：
    - 在测试阶段生成测试报告节点（call 阶段）后，若用例失败且带有 ui 标记，
      自动从最近注册的 Playwright 页面抓取截图并附加到 pytest-html 报告；
    - 截图路径：reports/screenshots/<sanitized-nodeid>.png。
    """
    outcome = yield
    rep = outcome.get_result()
    if rep.when != "call":
        return

    # 仅对 UI 用例在失败时尝试截图与保存 trace
    if not item.get_closest_marker("ui"):
        return
    if not rep.failed:
        return

    # 需要 pytest-html 插件与已注册的页面对象
    if html_extras is None:
        return
    if not item.config.pluginmanager.hasplugin("html"):
        return

    project_root = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    nodeid = item.nodeid.replace(os.sep, "_").replace(":", "_")
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    # 截图
    page = get_last_page()
    if page is not None:
        screenshots_dir = project_root / "reports" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshots_dir / f"{nodeid}_{timestamp}.png"
        try:
            page.screenshot(path=str(screenshot_path))
        except Exception as e:
            logging.getLogger(__name__).warning(f"UI 失败截图保存失败：{e}")
        else:
            extra = getattr(rep, "extra", [])
            extra.append(html_extras.image(str(screenshot_path), mime_type="image/png"))
            rep.extra = extra

    # 保存 Playwright trace
    context = get_last_context()
    if context is not None:
        traces_dir = project_root / "reports" / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        trace_path = traces_dir / f"{nodeid}_{timestamp}.zip"
        try:
            context.tracing.stop(path=str(trace_path))
        except Exception as e:
            logging.getLogger(__name__).warning(f"UI 失败 Trace 保存失败：{e}")
        else:
            extra = getattr(rep, "extra", [])
            # 将 trace 以链接形式附加，避免过大内嵌
            extra.append(html_extras.link(str(trace_path), name="Playwright Trace"))
            rep.extra = extra


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    """
    函数级注释：
    - 在 UI 用例的 teardown 阶段尝试保存并附加视频；随后清理注册的 page/context，避免串扰；
    - 视频文件保存在 reports/videos 下，并以规范化文件名复制一份便于查阅。
    """
    outcome = yield
    rep = outcome.get_result() if hasattr(outcome, 'get_result') else None

    if not item.get_closest_marker("ui"):
        # 非 UI 用例仅清理引用
        clear_last_page()
        clear_last_context()
        return

    project_root = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    nodeid = item.nodeid.replace(os.sep, "_").replace(":", "_")
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    page = get_last_page()
    if page is not None and getattr(page, "video", None):
        try:
            # 复制视频到规范化路径
            videos_dir = project_root / "reports" / "videos"
            videos_dir.mkdir(parents=True, exist_ok=True)
            video_out = videos_dir / f"{nodeid}_{timestamp}.webm"
            try:
                page.video.save_as(str(video_out))
            except Exception:
                # 某些情况下 video.path 可用，退化为链接原路径
                orig_path = page.video.path()
                if orig_path:
                    # 创建一个同名的软链接或复制
                    try:
                        import shutil
                        shutil.copy2(orig_path, video_out)
                    except Exception:
                        video_out = Path(orig_path)
            # 附加到报告（若启用 pytest-html）
            if html_extras is not None and item.config.pluginmanager.hasplugin("html"):
                extra = getattr(rep, "extra", []) if rep else []
                extra.append(html_extras.link(str(video_out), name="UI Failure Video"))
                if rep:
                    rep.extra = extra
        except Exception as e:
            logging.getLogger(__name__).warning(f"UI 失败视频保存失败：{e}")

    # 清理注册引用
    clear_last_page()
    clear_last_context()


@pytest.fixture(scope="session")
def test_data_dir():
    """Create temporary directory for test data."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture(autouse=True)
def setup_logging():
    """Setup logging for tests."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

# Ensure project root is on sys.path at import time so tests can import local packages
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Provide a compatibility shim for pygetwindow in environments where
# getWindowsWithTitle may not be available so that tests can patch it.
if not hasattr(gw, 'getWindowsWithTitle'):
    def _empty_getWindowsWithTitle(title_pattern):
        return []
    gw.getWindowsWithTitle = _empty_getWindowsWithTitle


@pytest.fixture
def sample_config_dict():
    """Sample configuration dictionary for testing."""
    return {
        "app": {
            "scroll_speed": 2,
            "scroll_delay": 1.0,
            "max_retry_attempts": 3,
        },
        "ocr": {
            "language": "chi_sim",
            "confidence_threshold": 0.7,
            "use_gpu": False,
        },
        "output": {
            "format": "json",
            "directory": "./output",
            "enable_deduplication": True,
        }
    }