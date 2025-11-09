"""
UI 辅助工具：
- 提供 Playwright 页面注册/获取/清理接口（用于失败自动截图/trace 保存）；
- 提供服务就绪检查与更稳健的等待/点击辅助函数，提升 UI 测试稳定性。
"""
from typing import Optional
import time
import json
import socket
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from contextlib import closing

_LAST_PAGE = None
_LAST_CONTEXT = None


def register_page(page) -> None:
    """
    函数级注释：
    - 注册当前正在测试的 Playwright 页面对象；
    - 在测试失败时，conftest.py 的钩子可通过 get_last_page() 获取并截图；
    - 多次调用将覆盖为最新页面。
    """
    global _LAST_PAGE
    _LAST_PAGE = page


def register_context(context) -> None:
    """
    函数级注释：
    - 注册当前 Playwright 上下文对象，用于失败时停止并保存 trace；
    - 与 register_page 配套使用，保证在用例失败阶段能访问到上下文。
    """
    global _LAST_CONTEXT
    _LAST_CONTEXT = context


def get_last_page() -> Optional[object]:
    """
    函数级注释：
    - 返回最近一次注册的 Playwright 页面对象；
    - 若尚未注册或已清理，返回 None。
    """
    return _LAST_PAGE


def get_last_context() -> Optional[object]:
    """
    函数级注释：
    - 返回最近一次注册的 Playwright 上下文对象；
    - 若尚未注册或已清理，返回 None。
    """
    return _LAST_CONTEXT


def clear_last_page() -> None:
    """
    函数级注释：
    - 清理已注册的页面引用，避免测试间串扰；
    - 建议在每个用例的 finally 或 teardown 阶段调用。
    """
    global _LAST_PAGE
    _LAST_PAGE = None


def clear_last_context() -> None:
    """
    函数级注释：
    - 清理已注册的上下文引用，避免测试间串扰；
    - 建议在每个用例的 teardown 阶段调用。
    """
    global _LAST_CONTEXT
    _LAST_CONTEXT = None


# ---------------- 稳定性增强辅助函数 ----------------

def wait_for_server_ready(port: int, timeout: float = 10.0, interval: float = 0.2) -> None:
    """
    函数级注释：
    - 轮询本地配置服务的 /api/metrics 端点，直到返回 200 且 JSON 解析成功，或超时；
    - 用于替代固定 sleep，避免因服务未完全启动导致的偶发失败；
    - 若超时未就绪，抛出 RuntimeError 以便测试显式失败并提供诊断信息。

    参数：
    - port: 本地服务端口（如 8010/8011/8012）；
    - timeout: 最大等待秒数；
    - interval: 轮询间隔秒数。
    """
    deadline = time.monotonic() + timeout
    url = f"http://localhost:{port}/api/metrics"
    last_err = None
    while time.monotonic() < deadline:
        try:
            req = Request(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=1.5) as resp:
                if resp.getcode() == 200:
                    raw = resp.read().decode("utf-8", errors="ignore")
                    try:
                        obj = json.loads(raw)
                        # 只要能解析 JSON 即认为服务就绪（不强制 ok 字段）
                        return
                    except Exception as e:
                        last_err = e
        except (URLError, HTTPError, socket.error) as e:
            last_err = e
        time.sleep(interval)
    raise RuntimeError(f"配置服务未在 {timeout}s 内就绪: {url}; last_err={last_err}")


def wait_for_selector_safe(page, selector: str, timeout_ms: int = 15000) -> None:
    """
    函数级注释：
    - 等待选择器出现且可见，失败时抛出更友好的错误信息；
    - 封装 page.wait_for_selector 的常用场景，便于统一时间参数与诊断。"""
    try:
        page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
    except Exception as e:
        raise AssertionError(f"等待选择器可见失败: selector={selector}, timeout_ms={timeout_ms}, err={e}")


def safe_click(page, selector: str, timeout_ms: int = 15000) -> None:
    """
    函数级注释：
    - 先等待元素可见再执行点击，减少由于渲染/布局未完成导致的点击失败；
    - 保留 Playwright 的 actionability 校验。"""
    wait_for_selector_safe(page, selector, timeout_ms=timeout_ms)
    page.click(selector)


def wait_for_metrics_fetch(page, timeout_ms: int = 15000):
    """
    函数级注释：
    - 点击“刷新指标”按钮并等待 /api/metrics 响应返回 200；
    - 随后等待 #metrics_meta 出现，确保页面已渲染最新快照；
    - 返回捕获的 Response 对象，便于调试或进一步断言。
    """
    wait_for_selector_safe(page, "#btn_metrics_refresh", timeout_ms=timeout_ms)
    with page.expect_response(lambda r: r.url.endswith("/api/metrics") and r.status == 200, timeout=timeout_ms) as resp_info:
        page.click("#btn_metrics_refresh")
    resp = resp_info.value
    wait_for_selector_safe(page, "#metrics_meta", timeout_ms=timeout_ms)
    return resp


def wait_for_text_change(page, selector: str, old_text: str | None, timeout_ms: int = 3000, interval_ms: int = 120) -> str:
    """
    函数级注释：
    - 轮询指定元素的文本，直到其与给定旧文本不同或达到超时；
    - 用于“自动刷新”等需要观察 UI 文本变化的场景；
    - 返回最终捕获到的文本（若超时仍相同则抛出 AssertionError）。

    参数：
    - selector: 目标元素选择器；
    - old_text: 之前的文本（None 表示不比较，直接返回首次非空文本）；
    - timeout_ms: 最大等待毫秒；
    - interval_ms: 轮询间隔毫秒。
    """
    wait_for_selector_safe(page, selector, timeout_ms=timeout_ms)
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        cur = (page.text_content(selector) or "").strip()
        if old_text is None:
            if cur:
                return cur
        else:
            if cur != (old_text or ""):
                return cur
        page.wait_for_timeout(interval_ms)
    raise AssertionError(f"文本未在 {timeout_ms}ms 内发生变化: selector={selector}, old_text={old_text}")


def wait_for_text_changes_n(page, selector: str, min_changes: int = 2, timeout_ms: int = 6000, interval_ms: int = 120) -> list[str]:
    """
    函数级注释：
    - 轮询指定元素文本，直到其发生至少 min_changes 次变化或达到超时；
    - 返回每次变化后的文本列表，便于进行更丰富的断言；
    - 适用于“自动刷新”等需要验证重复更新的 UI 场景。

    参数：
    - selector: 目标元素选择器；
    - min_changes: 至少需要捕获的变化次数；
    - timeout_ms: 最大等待毫秒；
    - interval_ms: 轮询间隔毫秒。
    """
    wait_for_selector_safe(page, selector, timeout_ms=timeout_ms)
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    changes: list[str] = []
    prev = (page.text_content(selector) or "").strip()
    while time.monotonic() < deadline:
        cur = (page.text_content(selector) or "").strip()
        if cur and cur != prev:
            changes.append(cur)
            prev = cur
            if len(changes) >= min_changes:
                return changes
        page.wait_for_timeout(interval_ms)
    raise AssertionError(f"文本未在 {timeout_ms}ms 内发生至少 {min_changes} 次变化: selector={selector}, changes={len(changes)}")


def pick_free_port(preferred: int | None = None, min_port: int = 8000, max_port: int = 9000) -> int:
    """
    函数级注释：
    - 寻找一个当前未被占用的本地 TCP 端口用于启动测试服务；
    - 若提供 preferred，则优先尝试该端口；若不可用则自动回退到系统分配的临时端口；
    - 通过临时绑定并释放的方式检测端口可用性，尽量降低端口冲突概率。

    返回：
    - 可用端口号（int）。
    """
    # 优先尝试用户偏好端口
    if preferred is not None:
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", preferred))
                return preferred
        except OSError:
            pass

    # 退回到系统分配的临时端口
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]