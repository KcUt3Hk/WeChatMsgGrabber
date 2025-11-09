#!/usr/bin/env python3
"""
测试入口脚本（run_tests.py）

提供更友好的命令行入口以运行项目测试：
- 支持模式选择：quick/full/unit/slow/integration/requires_wechat_closed
- 支持 -k 过滤关键字、显示慢测试（--durations 与 --durations-min）
- 可选生成覆盖率报告（--cov/--cov-report）
- 默认设置 WECHAT_TEST_MODE=auto，保证在本地与 CI 下的行为一致

用法示例：
  1) 快速运行常规/单元测试（排除集成与慢测）
     ./run_tests.py --mode quick

  2) 运行全部测试
     ./run_tests.py --mode full

  3) 仅运行单元测试
     ./run_tests.py --mode unit

  4) 仅运行慢速测试
     ./run_tests.py --mode slow

  5) 关键字过滤
     ./run_tests.py --mode full -k batch_processing

  6) 启用覆盖率
     ./run_tests.py --mode quick --cov services --cov-report term-missing
"""
import os
import sys
import subprocess
import argparse
import importlib.util
import cProfile
import pstats
from typing import List, Optional


def validate_interpreter() -> None:
    """
    验证当前脚本的解释器路径，并给出提示信息。

    函数级注释：
    - 优先支持通过环境变量 PYTHON_BIN 指定解释器路径；
    - 若未设置，则使用当前进程解释器 sys.executable；
    - 打印当前解释器与环境变量，便于在本地或 CI 中确认配置。
    """
    current = sys.executable
    env_pybin = os.environ.get("PYTHON_BIN", "").strip()
    print(f"🔧 当前解释器: {current}")
    if env_pybin:
        print(f"🔧 PYTHON_BIN 环境变量: {env_pybin}")
        if os.path.abspath(env_pybin) != os.path.abspath(current):
            print(
                "ℹ️ 已设置 PYTHON_BIN，与当前解释器不同。运行子进程将优先使用 PYTHON_BIN。"
            )
    else:
        print("ℹ️ 未设置 PYTHON_BIN，默认使用当前解释器运行测试。")


def build_pytest_command(
    mode: str,
    kexpr: Optional[str],
    durations: int,
    durations_min: float,
    cov: Optional[str],
    cov_report: Optional[str],
    tests_path: str,
    parallel: Optional[str] = None,
    dist: Optional[str] = None,
    maxfail: Optional[int] = None,
    junitxml: Optional[str] = None,
    use_pytest_main: bool = False,
) -> List[str]:
    """
    构建 pytest 命令行参数列表。

    参数：
    - mode: 运行模式（quick/full/unit/slow/integration/requires_wechat_closed）
    - kexpr: pytest -k 过滤表达式
    - durations: 显示最慢的 N 个测试
    - durations_min: 仅显示耗时超过该阈值（秒）的测试
    - cov: 覆盖率目标（如 'services' 或具体模块路径），不传则不启用覆盖率
    - cov_report: 覆盖率输出类型（如 'term' 或 'term-missing'）
    - tests_path: 测试路径（默认 'tests'）

    返回：
    - 当 use_pytest_main=False：返回完整的命令列表，可用于 subprocess.run
    - 当 use_pytest_main=True：返回仅包含 pytest 参数的列表，可用于 pytest.main
    """
    cmd: List[str] = [] if use_pytest_main else [sys.executable, "-m", "pytest"]

    # 通用选项（与 pytest.ini 保持一致）
    cmd += [
        "-v",
        "--tb=short",
        "--strict-markers",
        f"--durations={durations}",
        f"--durations-min={durations_min}",
    ]

    # 模式到标记表达式的映射
    mark_expr = None
    if mode == "quick":
        mark_expr = "not integration and not slow"
    elif mode == "full":
        mark_expr = None
    elif mode == "unit":
        mark_expr = "unit"
    elif mode == "slow":
        mark_expr = "slow"
    elif mode == "integration":
        mark_expr = "integration"
    elif mode == "requires_wechat_closed":
        mark_expr = "requires_wechat_closed"
    else:
        raise ValueError(f"未知模式: {mode}")

    if mark_expr:
        cmd += ["-m", mark_expr]

    if kexpr:
        cmd += ["-k", kexpr]

    # 并行化（pytest-xdist）设置（可选）
    if parallel:
        # 允许 auto 或数字（如 "4"）。
        cmd += ["-n", parallel]
        if dist:
            cmd += [f"--dist={dist}"]

    # 失败快速退出（可选）
    if maxfail is not None and maxfail > 0:
        cmd += [f"--maxfail={maxfail}"]

    # 覆盖率设置（可选）
    if cov:
        # 支持传入逗号分隔的多个目标，例如 'services,controllers'。
        for target in cov.split(","):
            target = target.strip()
            if target:
                cmd += [f"--cov={target}"]
        if cov_report:
            cmd += [f"--cov-report={cov_report}"]

    # 测试路径
    cmd.append(tests_path)
    return cmd


def configure_environment(wechat_mode: str) -> None:
    """
    配置运行测试所需的环境变量。

    - WECHAT_TEST_MODE: 控制测试在本地/CI 下的行为（默认 'auto'）。
    - 在 CI 环境下，框架通常会自动设置 CI=true；此处无需强制设定。
    """
    os.environ.setdefault("WECHAT_TEST_MODE", wechat_mode)
    print(f"🌐 WECHAT_TEST_MODE={os.environ['WECHAT_TEST_MODE']}")


def enable_global_offline_patch() -> None:
    """
    启用全局网络离线补丁（测试运行级别）。

    函数级注释：
    - 在运行 pytest 之前拦截 requests.head 与 requests.Session.head/request，
      用最小响应对象替代来自 paddlex/飞桨/百度对象存储主机的 HEAD 请求，避免网络探测造成的阻塞；
    - 该补丁仅在本进程内生效，测试结束后不会持久化；
    - 适用于慢测模式（slow），帮助定位真实代码热点，减少外部网络带来的噪声。
    """
    try:
        import requests as _requests
        class _OfflineResp:
            def __init__(self):
                self.status_code = 200
                self.ok = True
                self.headers = {}
            def close(self):
                pass

        _orig_head = getattr(_requests, "head", None)
        _orig_get = getattr(_requests, "get", None)
        _orig_request = getattr(_requests, "request", None)
        def _offline_head(url, *args, **kwargs):
            try:
                u = str(url)
                if ("paddlex" in u) or ("paddlepaddle" in u) or ("bcebos.com" in u) or ("bj.bcebos.com" in u):
                    return _OfflineResp()
            except Exception:
                pass
            if _orig_head:
                return _orig_head(url, *args, **kwargs)
            return _OfflineResp()

        try:
            setattr(_requests, "head", _offline_head)
        except Exception:
            pass

        def _offline_get(url, *args, **kwargs):
            try:
                u = str(url)
                if ("paddlex" in u) or ("paddlepaddle" in u) or ("bcebos.com" in u) or ("bj.bcebos.com" in u):
                    return _OfflineResp()
            except Exception:
                pass
            if _orig_get:
                return _orig_get(url, *args, **kwargs)
            return _OfflineResp()

        try:
            setattr(_requests, "get", _offline_get)
        except Exception:
            pass

        def _offline_request(method, url, *args, **kwargs):
            try:
                m = str(method).upper()
                u = str(url)
                if m in ("HEAD", "GET") and (("paddlex" in u) or ("paddlepaddle" in u) or ("bcebos.com" in u) or ("bj.bcebos.com" in u)):
                    return _OfflineResp()
            except Exception:
                pass
            if _orig_request:
                return _orig_request(method, url, *args, **kwargs)
            return _OfflineResp()

        try:
            setattr(_requests, "request", _offline_request)
        except Exception:
            pass

        # 会话级别补丁
        _orig_s_head = getattr(_requests.Session, "head", None)
        _orig_s_request = getattr(_requests.Session, "request", None)
        _orig_s_get = getattr(_requests.Session, "get", None)

        def _offline_session_head(session_self, url, *args, **kwargs):
            try:
                u = str(url)
                if ("paddlex" in u) or ("paddlepaddle" in u) or ("bcebos.com" in u) or ("bj.bcebos.com" in u):
                    return _OfflineResp()
            except Exception:
                pass
            if _orig_s_head:
                return _orig_s_head(session_self, url, *args, **kwargs)
            if _orig_head:
                return _orig_head(url, *args, **kwargs)
            return _OfflineResp()

        def _offline_session_request(session_self, method, url, *args, **kwargs):
            try:
                m = (method.upper() if isinstance(method, str) else str(method).upper())
                if m in ("HEAD", "GET"):
                    u = str(url)
                    if ("paddlex" in u) or ("paddlepaddle" in u) or ("bcebos.com" in u) or ("bj.bcebos.com" in u):
                        return _OfflineResp()
            except Exception:
                pass
            if _orig_s_request:
                return _orig_s_request(session_self, method, url, *args, **kwargs)
            # Fallback：HEAD 请求走全局 head；其他请求直接退化为成功响应
            if isinstance(method, str) and method.upper() == "HEAD":
                if _orig_head:
                    return _orig_head(url, *args, **kwargs)
                return _OfflineResp()
            try:
                return _orig_s_request(session_self, method, url, *args, **kwargs)
            except Exception:
                return _OfflineResp()

        try:
            setattr(_requests.Session, "head", _offline_session_head)
        except Exception:
            pass
        try:
            setattr(_requests.Session, "request", _offline_session_request)
        except Exception:
            pass
        def _offline_session_get(session_self, url, *args, **kwargs):
            try:
                u = str(url)
                if ("paddlex" in u) or ("paddlepaddle" in u) or ("bcebos.com" in u) or ("bj.bcebos.com" in u):
                    return _OfflineResp()
            except Exception:
                pass
            if _orig_s_get:
                return _orig_s_get(session_self, url, *args, **kwargs)
            if _orig_get:
                return _orig_get(url, *args, **kwargs)
            return _OfflineResp()
        try:
            setattr(_requests.Session, "get", _offline_session_get)
        except Exception:
            pass

        # 适配器层：拦截所有发送，统一短路指定主机的 HEAD/GET
        try:
            from requests.adapters import HTTPAdapter as _HTTPAdapter
            _orig_send = getattr(_HTTPAdapter, "send", None)
            def _offline_send(adapter_self, request, *args, **kwargs):
                try:
                    m = str(getattr(request, "method", "")).upper()
                    u = str(getattr(request, "url", ""))
                    if m in ("HEAD", "GET") and (("paddlex" in u) or ("paddlepaddle" in u) or ("bcebos.com" in u) or ("bj.bcebos.com" in u)):
                        resp = _requests.Response()
                        resp.status_code = 200
                        resp._content = b""
                        resp.headers = {}
                        resp.url = u
                        resp.request = request
                        resp.reason = "OK"
                        resp.encoding = "utf-8"
                        return resp
                except Exception:
                    pass
                if _orig_send:
                    return _orig_send(adapter_self, request, *args, **kwargs)
                resp = _requests.Response()
                resp.status_code = 200
                resp._content = b""
                resp.headers = {}
                resp.url = str(getattr(request, "url", ""))
                resp.request = request
                resp.reason = "OK"
                resp.encoding = "utf-8"
                return resp
            try:
                setattr(_HTTPAdapter, "send", _offline_send)
            except Exception:
                pass
        except Exception:
            pass
        print("🛡️ 已启用全局离线补丁：拦截 requests.head/get/request、Session.head/get/request、HTTPAdapter.send")
    except Exception as e:
        print("⚠️ 无法启用全局离线补丁：", e)


def run(cmd: List[str]) -> bool:
    """
    执行 pytest 命令并打印输出。

    返回：
    - True: 测试进程退出码为 0（全部通过）
    - False: 测试失败或出现错误
    """
    print("🧪 运行命令:")
    print(" ", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print("\n✅ 测试执行完成")
        return True
    except subprocess.CalledProcessError as e:
        print("\n❌ 测试失败：")
        print(e.stdout)
        print(e.stderr)
        return False


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    返回：
    - argparse.Namespace，包含用户指定的各项选项
    """
    parser = argparse.ArgumentParser(description="项目测试快捷入口")
    parser.add_argument(
        "--mode",
        choices=[
            "quick",
            "full",
            "unit",
            "slow",
            "integration",
            "requires_wechat_closed",
        ],
        default="quick",
        help="选择运行模式：quick(排除集成与慢测)/full(全部)/unit/slow/integration/requires_wechat_closed",
    )
    parser.add_argument("-k", dest="kexpr", default=None, help="pytest -k 过滤表达式")
    parser.add_argument("--durations", type=int, default=10, help="显示最慢的 N 个测试")
    parser.add_argument(
        "--durations-min",
        type=float,
        default=1.0,
        help="仅显示耗时超过该阈值（秒）的测试",
    )
    parser.add_argument(
        "--cov",
        type=str,
        default=None,
        help="覆盖率目标（如 'services' 或 'services,controllers'），不传则不启用覆盖率",
    )
    parser.add_argument(
        "--cov-report",
        type=str,
        default=None,
        help="覆盖率输出类型（如 'term' 或 'term-missing'）",
    )
    parser.add_argument(
        "--tests-path",
        type=str,
        default="tests",
        help="测试路径（默认 'tests'）",
    )
    parser.add_argument(
        "--wechat-mode",
        type=str,
        default="auto",
        help="设置 WECHAT_TEST_MODE 环境变量，默认 'auto'",
    )
    parser.add_argument(
        "--parallel",
        type=str,
        default=None,
        help="并行运行测试（需要 pytest-xdist），可选值：'auto' 或具体并发数（例如 '4'）",
    )
    parser.add_argument(
        "--dist",
        type=str,
        choices=["load", "loadfile", "worksteal"],
        default=None,
        help="pytest-xdist 的分发策略（与 --parallel 搭配使用）",
    )
    parser.add_argument(
        "--maxfail",
        type=int,
        default=None,
        help="达到指定失败次数后立即停止（例如 1）",
    )
    parser.add_argument(
        "--junitxml",
        type=str,
        default=None,
        help="输出 JUnit XML 报告到指定路径（例如 'reports/junit.xml'）",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="启用 cProfile 对测试执行进行性能分析，并生成 .prof 报告",
    )
    parser.add_argument(
        "--profile-out",
        type=str,
        default="profiles/pytest.prof",
        help="cProfile 报告输出路径（默认 'profiles/pytest.prof'）",
    )
    parser.add_argument(
        "--profile-report",
        type=str,
        default=None,
        help="可选：生成人类可读的文本报告（例如 'profiles/pytest.txt'）",
    )
    parser.add_argument(
        "--profile-sort",
        type=str,
        choices=["cumulative", "time", "calls"],
        default="cumulative",
        help="cProfile 报告排序键（默认 'cumulative'）",
    )
    parser.add_argument(
        "--profile-limit",
        type=int,
        default=50,
        help="cProfile 文本报告显示的函数条目数量（默认 50）",
    )
    return parser.parse_args()


def run_with_profile(pytest_args: List[str], profile_out: str, profile_report: Optional[str], sort_key: str, limit: int) -> bool:
    """
    使用 cProfile 对 pytest.main 执行过程进行性能分析。

    参数：
    - pytest_args: 传递给 pytest.main 的参数列表（不包含解释器与 -m pytest）
    - profile_out: 二进制性能报告输出路径（.prof 文件）
    - profile_report: 可选的人类可读文本报告输出路径（.txt 文件），不传则仅打印关键摘要到终端
    - sort_key: 报告排序键（cumulative/time/calls）
    - limit: 文本报告中显示的函数条目数量

    返回：
    - True：pytest 返回码为 0（测试通过）
    - False：pytest 返回非 0（测试失败）
    """
    import pytest  # 局部导入，避免脚本启动时不必要的依赖加载
    # 确保输出目录存在
    out_dir = os.path.dirname(profile_out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    if profile_report:
        rep_dir = os.path.dirname(profile_report)
        if rep_dir:
            os.makedirs(rep_dir, exist_ok=True)

    print("🧪 使用 cProfile 进行性能分析，输出：", profile_out)
    profiler = cProfile.Profile()
    exit_code = profiler.runcall(pytest.main, pytest_args)
    profiler.dump_stats(profile_out)

    # 打印摘要并可选保存文本报告
    stats = pstats.Stats(profile_out)
    stats.sort_stats(sort_key)
    # 将摘要打印到终端
    print("\n📊 cProfile 统计摘要（排序：", sort_key, ")")
    stats.print_stats(limit)

    if profile_report:
        # 将完整报告写入文本文件
        with open(profile_report, "w", encoding="utf-8") as f:
            from io import StringIO
            s = StringIO()
            stats.stream = s
            stats.print_stats(limit)
            f.write(s.getvalue())
        print("📝 文本报告已保存：", profile_report)

    print("✅ 性能分析完成，报告：", profile_out)
    return exit_code == 0


def check_xdist_available() -> bool:
    """
    检查 pytest-xdist 插件是否已安装。

    返回：
    - True：可用
    - False：不可用（未安装插件）
    """
    return importlib.util.find_spec("xdist") is not None


def main() -> int:
    """
    主入口函数：解析参数、构建命令、配置环境并执行测试。

    返回：
    - 进程退出码（0 表示成功，非 0 表示失败）
    """
    print("WeChatMsgGrabber - 测试快捷入口")
    print("=" * 60)

    # 检查项目路径与解释器路径
    if not os.path.exists("services/ocr_processor.py"):
        print("❌ 错误：请在项目根目录运行本脚本（未找到 services/ocr_processor.py）")
        return 1

    validate_interpreter()
    args = parse_args()
    configure_environment(args.wechat_mode)

    # 模式与并行化的兼容性提示
    if args.parallel:
        if not check_xdist_available():
            print(
                "⚠️ 未检测到 pytest-xdist，已回退为串行执行。\n"
                "   请安装依赖：pip install pytest-xdist 或使用 requirements.txt 安装。"
            )
            args.parallel = None
        elif args.mode in {"integration", "slow", "requires_wechat_closed"}:
            print(
                "⚠️ 提示：当前为集成/慢测模式，启用并行可能导致资源竞争或不稳定。\n"
                "   建议仅在 quick/unit 模式下使用 --parallel。"
            )

    # 构建命令或参数
    use_api = bool(args.profile)
    # 在慢测模式下，为了排除网络探测噪声，先启用一次全局离线补丁（仅影响当前进程）
    if args.mode == "slow":
        enable_global_offline_patch()
    cmd_or_args = build_pytest_command(
        mode=args.mode,
        kexpr=args.kexpr,
        durations=args.durations,
        durations_min=args.durations_min,
        cov=args.cov,
        cov_report=args.cov_report,
        tests_path=args.tests_path,
        parallel=args.parallel,
        dist=args.dist,
        maxfail=args.maxfail,
        junitxml=args.junitxml,
        use_pytest_main=use_api,
    )

    if use_api:
        ok = run_with_profile(
            pytest_args=cmd_or_args,
            profile_out=args.profile_out,
            profile_report=args.profile_report,
            sort_key=args.profile_sort,
            limit=args.profile_limit,
        )
    else:
        ok = run(cmd_or_args)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
    # 测试报告（JUnit XML）
    if junitxml:
        cmd += [f"--junitxml={junitxml}"]