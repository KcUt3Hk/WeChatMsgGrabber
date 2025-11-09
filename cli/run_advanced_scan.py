#!/usr/bin/env python3
"""
高级扫描命令行接口 - 支持渐进式滑动和智能终止检测
"""

import argparse
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controllers.main_controller import MainController
from services.config_manager import ConfigManager
from services.logging_manager import LoggingManager
from services.storage_manager import StorageManager
from ui.progress import ProgressReporter
from models.config import OutputConfig
import logging

def setup_logging(app_cfg):
    """配置日志

    函数级注释：
    - 使用项目的 LoggingManager 按 AppConfig.logging 配置统一日志格式与输出（控制台 + 轮转文件）。
    - 保持与 run_extraction CLI 一致的日志行为，避免重复配置导致的处理器堆叠。
    """
    LoggingManager().setup(app_cfg)

def main():
    """主函数

    函数级注释：
    - 统一通过 OutputConfig 控制输出格式/目录/去重，避免直接传递裸目录参数导致的配置漂移。
    - 与 MainController.run_and_save 对齐保存流程，保证测试用例中的去重与格式要求一致。
    - 支持窗口标题与聊天区域覆盖，以兼容 Mac 受限环境（无窗口 API 时直接截图）。
    - 保持参数风格与基础提取 CLI 一致，提升易用性与一致性。
    """
    parser = argparse.ArgumentParser(description='微信聊天记录高级扫描工具')
    parser.add_argument('--prefix', default='extraction', help='输出文件名前缀')
    parser.add_argument('--max-scrolls', type=int, default=50, help='最大滚动次数 (默认: 50)')
    parser.add_argument('--direction', choices=['up', 'down'], default='up', help='滚动方向 (默认: up)')
    parser.add_argument('--target-content', help='目标内容关键词，检测到该内容时停止扫描')
    parser.add_argument('--no-stop-at-edges', action='store_false', dest='stop_at_edges', help='不在聊天记录边缘停止扫描')
    # 覆盖项（窗口/区域/OCR）
    parser.add_argument('--window-title', help='自定义窗口标题子串（Mac 受限环境定位窗口）')
    parser.add_argument('--chat-area', help='聊天区域覆盖坐标(格式: x,y,w,h)')
    parser.add_argument('--ocr-lang', help='OCR语言覆盖 (e.g. ch, en, japan, korean)')
    # 滚动与速率参数
    parser.add_argument('--scroll-speed', type=int, help='滚动速度（平台相关，留空使用默认）')
    parser.add_argument('--scroll-delay', type=float, help='连续滚动之间的延迟秒数（留空使用默认）')
    parser.add_argument('--scroll-distance-range', help="滚动距离范围(像素)，格式: min,max")
    parser.add_argument('--scroll-interval-range', help="滚动时间间隔范围(秒)，格式: min,max")
    parser.add_argument('--max-scrolls-per-minute', type=int, help='每分钟滚动上限（速率限制）')
    # 输出与去重控制（统一通过 OutputConfig）
    parser.add_argument('--format', choices=['json','csv','txt','md'], help='输出格式覆盖')
    parser.add_argument('--formats', help='同时导出多种格式（逗号分隔），例如: json,csv；提供时覆盖 --format')
    parser.add_argument('--outdir', help='输出目录覆盖')
    parser.add_argument('--dry-run', action='store_true', help='仅运行扫描并展示统计，不保存文件')
    parser.add_argument('--no-dedup', action='store_true', help='禁用本次运行的去重')
    parser.add_argument('--skip-empty', action='store_true', help='当消息为空时不保存')
    parser.add_argument('--clear-dedup-index', action='store_true', help='在运行前清空持久化去重索引')
    parser.add_argument('--exclude-time-only', action='store_true', help='过滤仅包含时间/日期的系统分隔消息，不参与导出')
    parser.add_argument('--exclude-fields', help='从导出中排除的字段（逗号分隔），例如: confidence_score,raw_ocr_text')
    parser.add_argument('--aggressive-dedup', action='store_true', help='启用更激进的内容级去重（sender+content）')
    # 过滤器（与基础提取 CLI 保持一致）
    parser.add_argument('--sender', help='按发送方过滤（不区分大小写子串）')
    parser.add_argument('--start', help='ISO 开始时间，例如 2024-10-01 或 2024-10-01T10:00:00')
    parser.add_argument('--end', help='ISO 结束时间，例如 2024-10-31 或 2024-10-31T18:00:00')
    parser.add_argument('--types', help='包含的消息类型，逗号分隔，例如 TEXT,IMAGE')
    parser.add_argument('--contains', help='按内容子串过滤（不区分大小写）')
    parser.add_argument('--min-confidence', type=float, help='最低置信度阈值（0.0-1.0）')
    # 指标采集输出
    parser.add_argument('--metrics-file', help='心跳指标写入文件（CSV/JSON）')
    parser.add_argument('--metrics-format', choices=['csv','json'], default='csv', help='指标写入格式（默认 csv）')
    parser.add_argument('--cpu-threshold', type=float, help='CPU 使用率阈值（超过则告警，单位：%）')
    parser.add_argument('--mem-threshold', type=float, help='内存使用阈值（超过则告警，单位：MB）')
    parser.add_argument('--metrics-max-size-mb', type=float, help='指标文件最大大小（MB），需与 --metrics-rotate-count 配合；当 >0 时达到后进行轮转，<=0 时禁用轮转')
    parser.add_argument('--metrics-rotate-count', type=int, help='指标文件轮转保留个数（例如 3 则保留 .1、.2、.3；<=0 表示不保留历史且禁用轮转；仅当 --metrics-max-size-mb>0 时生效）')

    args = parser.parse_args()

    # 加载应用配置并设置日志
    cfg_mgr = ConfigManager()
    app_cfg = cfg_mgr.get_config()
    setup_logging(app_cfg)
    logger = logging.getLogger(__name__)

    try:
        # 可选：清除持久化去重索引
        if args.clear_dedup_index:
            StorageManager(app_cfg.output).clear_dedup_index()
            logger.info("已清空持久化去重索引文件")

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
            logger.warning("应用 OCR 语言覆盖失败: %s", e)

        # 应用窗口标题与聊天区域覆盖，以兼容受限环境
        if args.window_title:
            try:
                controller.scroll.set_title_override(args.window_title)
            except Exception:
                logger.warning("应用 --window-title 覆盖失败: %s", args.window_title)
        if args.chat_area:
            try:
                parts = [p.strip() for p in args.chat_area.split(',')]
                if len(parts) != 4:
                    raise ValueError("chat-area 必须为 'x,y,w,h'")
                x, y, w, h = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
                controller.scroll.set_override_chat_area((x, y, w, h))
                logger.info("已设置聊天区域覆盖: (%d,%d,%d,%d)", x, y, w, h)
            except Exception as e:
                logger.warning("--chat-area 值无效 '%s': %s", args.chat_area, e)

        # 创建进度报告器
        reporter = ProgressReporter(logging.getLogger("progress"))
        # 开启资源心跳，用于长时间扫描的监控
        try:
            # 配置指标写入与阈值与轮转
            if args.metrics_file or args.cpu_threshold is not None or args.mem_threshold is not None:
                # 关闭内存阈值限制：不论是否通过 CLI 传入 mem-threshold，这里都按禁用处理
                # 原因：在部分环境中内存采集的瞬时峰值会导致误告警，影响体验
                # 如需恢复，改为传递 args.mem_threshold 即可
                reporter.configure_metrics(output_file=args.metrics_file,
                                           fmt=(args.metrics_format or 'csv'),
                                           cpu_threshold=args.cpu_threshold,
                                           mem_threshold_mb=None,
                                           max_file_size_mb=args.metrics_max_size_mb,
                                           rotate_count=(args.metrics_rotate_count or 0))
            reporter.start_heartbeat(interval_seconds=5.0)
        except Exception:
            logger.debug("未能启动资源心跳，继续执行扫描")

        logger.info("开始高级扫描...")
        logger.info("滚动方向: %s", args.direction)
        logger.info("最大滚动次数: %d", args.max_scrolls)
        if args.target_content:
            logger.info("目标内容: %s", args.target_content)

        # 执行高级扫描
        # 解析滚动范围参数
        def _parse_range(val, cast=float):
            if not val:
                return None
            try:
                a, b = [cast(v.strip()) for v in val.split(',')]
                return (a, b)
            except Exception:
                logger.warning("范围参数无效: %s", val)
                return None

        scroll_distance_range = _parse_range(args.scroll_distance_range, cast=int)
        scroll_interval_range = _parse_range(args.scroll_interval_range, cast=float)

        messages = controller.advanced_scan_chat_history(
            max_scrolls=args.max_scrolls,
            direction=args.direction,
            target_content=args.target_content,
            stop_at_edges=args.stop_at_edges,
            reporter=reporter,
            scroll_speed=args.scroll_speed,
            scroll_delay=args.scroll_delay,
            scroll_distance_range=scroll_distance_range,
            scroll_interval_range=scroll_interval_range,
            max_scrolls_per_minute=args.max_scrolls_per_minute,
        )

        # 应用过滤器（若提供）
        def _apply_cli_filters(messages_list):
            """
            应用发送方、时间范围、类型、内容与最低置信度过滤。

            函数级注释：
            - 与 run_extraction.py 的过滤逻辑保持一致，确保两套 CLI 行为统一；
            - 提前解析 ISO 时间与类型枚举，异常时给出警告并忽略对应过滤；
            - 对于 min-confidence，保留分数不低于该值的消息。
            """
            if not messages_list:
                return messages_list
            from datetime import datetime
            from services.message_filters import filter_messages
            from models.data_models import MessageType

            start_dt = None
            end_dt = None
            if args.start:
                try:
                    start_dt = datetime.fromisoformat(args.start)
                except Exception:
                    logger.warning("无效的 --start 时间：%s", args.start)
            if args.end:
                try:
                    end_dt = datetime.fromisoformat(args.end)
                except Exception:
                    logger.warning("无效的 --end 时间：%s", args.end)

            types_sel = None
            if args.types:
                try:
                    types_list = [t.strip().upper() for t in args.types.split(',') if t.strip()]
                    types_sel = [MessageType[t] for t in types_list]
                except Exception:
                    logger.warning("无效的 --types 值：%s", args.types)
                    types_sel = None

            return filter_messages(
                messages_list,
                sender=args.sender,
                start=start_dt,
                end=end_dt,
                types=types_sel,
                contains=args.contains,
                min_confidence=args.min_confidence,
            )

        messages = _apply_cli_filters(messages)

        # 统一保存逻辑：通过 OutputConfig 覆盖控制输出与去重
        if args.dry_run:
            logger.info("Dry-run: 扫描到 %d 条消息，不进行保存。", len(messages))
        else:
            if args.skip_empty and not messages:
                logger.info("Skip-empty 已启用，消息为空，跳过保存。")
            else:
                # 解析 --formats（若提供则覆盖单一 --format），并进行顺序去重
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
                        logger.warning("解析 --formats 失败: %s", args.formats)
                        formats_list = []

                override = OutputConfig(
                    format=(args.format or app_cfg.output.format),
                    directory=(args.outdir or app_cfg.output.directory),
                    enable_deduplication=(False if args.no_dedup else app_cfg.output.enable_deduplication),
                    formats=formats_list,
                    exclude_fields=( [f.strip() for f in (args.exclude_fields.split(',') if args.exclude_fields else []) if f.strip()] ),
                    exclude_time_only=bool(args.exclude_time_only),
                    aggressive_dedup=bool(args.aggressive_dedup),
                )
                # 使用 MainController.run_and_save 以确保行为与测试一致
                messages = controller.run_and_save(
                    filename_prefix=args.prefix,
                    use_retry=False,
                    reporter=None,
                    messages=messages,
                    output_override=override,
                )

                logger.info("扫描完成！共提取 %d 条消息", len(messages))
                # 显示部分结果预览
                print("\n=== 扫描结果预览 ===")
                for i, msg in enumerate(messages[:5]):
                    print(f"{i+1}. [{msg.sender}] {msg.content[:50]}{'...' if len(msg.content) > 50 else ''}")
                if len(messages) > 5:
                    print(f"... 还有 {len(messages) - 5} 条消息")

        if not messages:
            logger.warning("未提取到任何消息")

        # 结束资源心跳
        try:
            reporter.stop_heartbeat()
        except Exception:
            pass

    except KeyboardInterrupt:
        logger.info("用户中断扫描")
    except Exception as e:
        logger.error(f"扫描失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()