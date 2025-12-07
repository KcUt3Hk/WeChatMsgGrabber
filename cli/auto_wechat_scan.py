#!/usr/bin/env python3
"""
一键自动化微信聊天窗口 OCR 扫描脚本

功能概述：
- 自动定位并激活微信窗口（支持标题覆盖与聊天区域坐标覆盖）。
- 模拟真实用户滚动（自然距离与时间间隔、速率限制、方向可选）。
- 对聊天区域进行 OCR 识别，适配多分辨率、不同字体大小与颜色。
- 将识别结果格式化输出（含时间戳、发送者、文本与表情字符），保存为结构化文件。

使用场景：直接在终端运行，适合快速抓取当前会话的聊天内容并导出。
"""

import argparse
import sys
import os
import logging

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.config_manager import ConfigManager
from services.logging_manager import LoggingManager
from controllers.main_controller import MainController
from ui.progress import ProgressReporter
from models.config import OutputConfig


def setup_logging(app_cfg):
    """配置日志输出

    函数级注释：
    - 使用项目中的 LoggingManager 按 AppConfig.logging 设置统一日志格式（控制台 + 文件）。
    - 避免重复添加处理器导致日志重复输出。
    """
    LoggingManager().setup(app_cfg)


def compute_natural_scroll_params(window_height: int, direction: str):
    """根据窗口高度与方向估算自然滚动参数范围

    函数级注释：
    - 通过窗口高度简单估计每次滚动距离与间隔范围，使滚动更贴近真实用户行为；
    - 对于较高窗口，增加滚动距离并适度降低停顿；较低窗口则相反；
    - 返回 (distance_range, interval_range) 元组，供高级扫描函数使用。
    """
    # 基于窗口高度的简易估算（像素和秒）
    if window_height is None or window_height <= 0:
        return (180, 260), (0.25, 0.45)

    base = max(600, min(window_height, 1400))  # 截断到合理范围
    # 距离范围：窗口高度的 18%-26%
    d_min = int(base * 0.18)
    d_max = int(base * 0.26)
    # 时间间隔范围：0.25-0.45 秒，较高窗口略微降低停顿（更顺畅）
    i_min = 0.22 if base > 1000 else 0.27
    i_max = 0.38 if base > 1000 else 0.48
    # 方向对距离影响（向下滚动时适度减少距离以提升信息密度）
    if direction == "down":
        d_min = int(d_min * 0.85)
        d_max = int(d_max * 0.85)
    return (d_min, d_max), (i_min, i_max)


def parse_cli_args():
    """解析命令行参数

    函数级注释：
    - 提供窗口定位、滚动控制、OCR 语言与输出格式等常用选项；
    - 保持参数命名与项目其它 CLI 一致以减少学习成本。
    """
    parser = argparse.ArgumentParser(description="一键自动化微信聊天 OCR 扫描")
    parser.add_argument('--direction', choices=['up', 'down'], default='up', help='滚动方向')
    parser.add_argument('--max-scrolls', type=int, default=60, help='最大滚动次数')
    parser.add_argument('--max-scrolls-per-minute', type=int, default=40, help='每分钟滚动上限')
    parser.add_argument('--spm-range', help='每分钟滚动数量区间，格式: min,max（优先生效）')
    parser.add_argument('--full-fetch', action='store_true', help='尽可能一次性抓取全部聊天内容（大幅提高滚动上限并在到达边缘时停止）')
    parser.add_argument('--go-top-first', action='store_true', help='扫描前先滚动到聊天记录顶部（配合 direction=down 可自顶向下全量覆盖）')
    parser.add_argument('--scroll-delay', type=float, help='滚动延迟秒数（留空自动估算）')
    parser.add_argument('--window-title', dest='title_override', help='窗口标题覆盖（用于窗口定位失败时）')
    parser.add_argument('--chat-area', help='聊天区域坐标覆盖，格式 x,y,width,height')
    parser.add_argument('--ocr-lang', help='OCR 语言（默认取配置文件，例如 ch）')
    parser.add_argument('--formats', help='导出格式，逗号分隔，例如 json,csv,txt,md')
    parser.add_argument('--output', help='输出目录（覆盖配置文件目录）')
    parser.add_argument('--filename-prefix', default='auto_wechat_scan', help='输出文件名前缀')
    parser.add_argument('--dry-run', action='store_true', help='仅打印统计，不保存文件')
    parser.add_argument('--skip-empty', action='store_true', help='当结果为空时跳过保存')
    parser.add_argument('--verbose', action='store_true', help='详细日志模式')
    return parser.parse_args()


def main():
    """主入口：执行窗口准备、自然滚动扫描、OCR 识别与结果保存

    函数级注释：
    - 初始化配置与日志，应用可选覆盖（OCR 语言、窗口标题、聊天区域）；
    - 根据窗口高度估算自然滚动参数，调用 MainController.advanced_scan_chat_history 执行扫描；
    - 使用 MainController.run_and_save 统一保存输出，支持多格式与去重；
    - 在 verbose 模式下输出进度与预览，便于快速核验。
    """
    args = parse_cli_args()

    # 加载配置并初始化日志
    cfg_mgr = ConfigManager()
    app_cfg = cfg_mgr.get_config()
    setup_logging(app_cfg)
    logger = logging.getLogger(__name__)

    controller = MainController()

    # 应用 OCR 语言覆盖
    try:
        if args.ocr_lang:
            controller.ocr.config.language = args.ocr_lang.strip()
            logger.info("使用 CLI 指定的 OCR 语言: %s", controller.ocr.config.language)
        else:
            controller.ocr.config.language = app_cfg.ocr.language
            logger.info("使用配置中的 OCR 语言: %s", controller.ocr.config.language)
    except Exception as e:
        logger.warning("应用 OCR 语言失败: %s", e)

    # 应用窗口标题与聊天区域覆盖
    if args.title_override:
        try:
            controller.scroll.set_title_override(args.title_override)
            logger.info("窗口标题覆盖: %s", args.title_override)
        except Exception:
            logger.warning("应用窗口标题覆盖失败: %s", args.title_override)

    if args.chat_area:
        try:
            parts = [p.strip() for p in args.chat_area.split(',')]
            if len(parts) != 4:
                raise ValueError("chat-area 必须为 'x,y,width,height'")
            x, y, w, h = map(int, parts)
            controller.scroll.set_override_chat_area((x, y, w, h))
            logger.info("聊天区域覆盖: (%d,%d,%d,%d)", x, y, w, h)
        except Exception as e:
            logger.warning("聊天区域覆盖失败 '%s': %s", args.chat_area, e)

    # 进度报告器（不设置内存阈值，避免误告警）
    reporter = ProgressReporter(logging.getLogger("progress"))
    try:
        reporter.configure_metrics(output_file=None, fmt="csv", cpu_threshold=None, mem_threshold_mb=None)
        reporter.start_heartbeat(interval_seconds=5.0)
    except Exception:
        logger.debug("未能启动资源心跳，继续执行")

    # 在扫描前确保窗口尽可能就绪，避免启动后因窗口未激活而中断
    try:
        ready = controller.scroll.ensure_window_ready(retries=3, delay=0.4)
        if ready:
            logger.info("窗口已就绪，准备开始滚动与识别")
        else:
            logger.warning("窗口未就绪，将尝试在高级扫描过程中依赖覆盖坐标或内部定位逻辑继续执行")
    except Exception as e:
        logger.warning("窗口就绪检查异常：%s", e)

    # 可选：扫描前先滚动到聊天记录顶部（配合向下扫描可一次性覆盖完整时间线）
    # 函数级注释：
    # - 在确保窗口就绪后调用 MainController.scroll_to_top()，将视图定位到最早消息位置；
    # - 建议与参数 --direction down 联用，以严格从最早到最新的顺序进行扫描；
    # - 若滚动到顶失败（例如窗口临时不可滚动），继续采用当前视图起点进行扫描。
    if args.go_top_first:
        try:
            controller.scroll_to_top()
            logger.info("已尝试滚动至聊天记录顶部（准备按 %s 方向扫描）", args.direction)
        except Exception as e:
            logger.warning("滚动至顶部失败：%s（将继续当前视图起点）", e)

    # 估算自然滚动参数
    window_height = None
    try:
        window_height = controller.scroll.get_window_height()  # 若窗口未就绪可能返回 None
    except Exception:
        pass
    distance_range, interval_range = compute_natural_scroll_params(window_height or 900, args.direction)
    if args.scroll_delay is not None:
        # 若用户提供 scroll-delay，则覆盖自动估算的间隔下界（更贴近可控停顿）
        interval_range = (max(0.05, float(args.scroll_delay)), max(interval_range[1], float(args.scroll_delay) + 0.1))

    # full-fetch 模式：尽可能一次性抓取全部聊天内容
    # 函数级注释：
    # - 将最大滚动次数提升至较大值（例如 2000），并保持 stop_at_edges=True，直至到达顶部/底部；
    # - 在极长聊天记录下，速率限制（max-scrolls-per-minute）仍然生效，以避免过快滚动导致不稳定；
    # - 该模式不会强制退出，若出现小异常会重试一次并继续保存已识别内容。
    if args.full_fetch:
        args.max_scrolls = max(args.max_scrolls, 2000)
        logger.info("已启用 full-fetch 模式，最大滚动次数提升为 %d", args.max_scrolls)

    logger.info("滚动方向: %s", args.direction)
    logger.info("最大滚动次数: %d", args.max_scrolls)
    logger.info("自然滚动参数：距离范围=%s，间隔范围=%s，速率上限=%s/min", distance_range, interval_range, args.max_scrolls_per_minute)

    # 执行高级扫描
    # 执行高级扫描（必要时进行一次轻量重试以避免偶发中断）
    messages = []
    # 解析 spm-range
    spm_range = None
    try:
        if args.spm_range:
            parts = [p.strip() for p in args.spm_range.split(',')]
            if len(parts) == 2:
                spm_range = (int(parts[0]), int(parts[1]))
    except Exception:
        spm_range = None
    attempts = 1 if not args.full_fetch else 2
    for attempt in range(attempts):
        try:
            msgs = controller.advanced_scan_chat_history(
                max_scrolls=args.max_scrolls,
                direction=args.direction,
                target_content=None,
                stop_at_edges=True,
                reporter=reporter if args.verbose else None,
                scroll_speed=None,
                scroll_delay=None,  # 使用间隔范围而非固定延迟
                scroll_distance_range=distance_range,
                scroll_interval_range=interval_range,
                max_scrolls_per_minute=args.max_scrolls_per_minute,
                spm_range=spm_range,
            )
            # 合并并去重（基于 stable_key）
            seen = {m.stable_key() for m in messages}
            for m in msgs:
                k = m.stable_key()
                if k not in seen:
                    messages.append(m)
                    seen.add(k)
            if msgs:
                logger.info("第 %d 次扫描获取 %d 条消息，累计 %d 条", attempt + 1, len(msgs), len(messages))
            else:
                logger.info("第 %d 次扫描未获取到新消息，累计 %d 条", attempt + 1, len(messages))
        except Exception as e:
            logger.warning("第 %d 次扫描出现异常：%s（将继续）", attempt + 1, e)
            continue

    # 保存输出（多格式与目录覆盖）
    if args.dry_run:
        logger.info("Dry-run: 扫描到 %d 条消息，不保存文件。", len(messages))
    else:
        if args.skip_empty and not messages:
            logger.info("Skip-empty 已启用，消息为空，跳过保存。")
        else:
            formats_list = []
            if args.formats:
                try:
                    cand = [f.strip().lower() for f in args.formats.split(',') if f.strip()]
                    seen = set()
                    for f in cand:
                        if f not in seen:
                            seen.add(f)
                            formats_list.append(f)
                except Exception:
                    logging.getLogger("progress").warning("解析 --formats 失败: %s", args.formats)
                    formats_list = []

            override = OutputConfig(
                format=(formats_list[0] if formats_list else app_cfg.output.format),
                directory=(args.output or app_cfg.output.directory),
                enable_deduplication=app_cfg.output.enable_deduplication,
                formats=formats_list,
                exclude_fields=app_cfg.output.exclude_fields,
                exclude_time_only=app_cfg.output.exclude_time_only,
                aggressive_dedup=app_cfg.output.aggressive_dedup,
            )
            messages = controller.run_and_save(
                filename_prefix=args.filename_prefix,
                use_retry=False,
                reporter=None,
                messages=messages,
                output_override=override,
            )

    # 预览前几条结果
    if args.verbose:
        print("\n=== 扫描结果预览 ===")
        for i, msg in enumerate(messages[:5]):
            short = (msg.content or "")
            short = short[:60] + ('...' if len(short) > 60 else '')
            print(f"{i+1}. [{msg.sender}] {short}")

    # 任务总结
    try:
        from datetime import datetime, timezone
        stats = controller.get_last_scroll_stats() or {}
        start_ts = stats.get("start_time")
        end_ts = stats.get("end_time") or (start_ts or datetime.now().timestamp())
        # 允许没有统计时的回退
        if start_ts and isinstance(start_ts, (int, float)):
            start_dt = datetime.fromtimestamp(start_ts)
        else:
            start_dt = datetime.now()
        if end_ts and isinstance(end_ts, (int, float)):
            end_dt = datetime.fromtimestamp(end_ts)
        else:
            end_dt = datetime.now()
        elapsed_sec = int(max(0.0, (end_dt - start_dt).total_seconds()))
        hh = elapsed_sec // 3600
        mm = (elapsed_sec % 3600) // 60
        ss = elapsed_sec % 60
        total_scrolls = int(stats.get("total_scrolls", 0))
        spm = float(stats.get("scrolls_per_minute", 0.0))

        # 消息统计
        def _date(d):
            try:
                return d.date()
            except Exception:
                return None
        dates = sorted({ _date(m.timestamp) for m in messages if _date(m.timestamp) })
        msg_days = ( (dates[-1] - dates[0]).days + 1 ) if dates else 0
        # 连续与间隔
        longest_streak = 0
        longest_gap = 0
        if dates:
            streak = 1
            for i in range(1, len(dates)):
                diff = (dates[i] - dates[i-1]).days
                if diff == 1:
                    streak += 1
                else:
                    longest_streak = max(longest_streak, streak)
                    streak = 1
                    longest_gap = max(longest_gap, diff-1)
            longest_streak = max(longest_streak, streak)
        my_count = sum(1 for m in messages if (m.sender or "") == "我")
        other_count = sum(1 for m in messages if (m.sender or "") == "对方")

        print("\n=== 任务总结 ===")
        print(f"开始时间：{start_dt.strftime('%m月%d日%H:%M')} ")
        print(f"结束时间：{end_dt.strftime('%m月%d日%H:%M')} ")
        print(f"耗时：{hh}小时{mm}分钟{ss}秒")
        print(f"累计滚动次数：{total_scrolls}次")
        print(f"每分钟滚动次数：{spm:.1f}次")
        print(f"消息时长：{msg_days}天")
        print(f"最长连续：{longest_streak}天")
        print(f"最长间隔：{longest_gap}天")
        print(f"累计消息数：{len(messages)}条")
        print(f"我的消息数：{my_count}条")
        print(f"对方消息数：{other_count}条")

        # 同步写入日志文件（通过 LoggingManager 的文件处理器）
        lg = logging.getLogger(__name__)
        lg.info("=== 任务总结 ===")
        lg.info("开始时间：%s", start_dt.strftime('%m月%d日%H:%M'))
        lg.info("结束时间：%s", end_dt.strftime('%m月%d日%H:%M'))
        lg.info("耗时：%d小时%d分钟%d秒", hh, mm, ss)
        lg.info("累计滚动次数：%d次", total_scrolls)
        lg.info("每分钟滚动次数：%.1f次", spm)
        lg.info("消息时长：%d天", msg_days)
        lg.info("最长连续：%d天", longest_streak)
        lg.info("最长间隔：%d天", longest_gap)
        lg.info("累计消息数：%d条", len(messages))
        lg.info("我的消息数：%d条", my_count)
        lg.info("对方消息数：%d条", other_count)
    except Exception as e:
        logging.getLogger(__name__).debug(f"任务总结生成失败：{e}")

    try:
        reporter.stop_heartbeat()
    except Exception:
        pass

    logger.info("完成！共提取 %d 条消息", len(messages))


if __name__ == "__main__":
    main()
