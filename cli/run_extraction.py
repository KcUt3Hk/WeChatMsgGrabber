import argparse
import logging

from controllers.main_controller import MainController
from services.config_manager import ConfigManager
from services.logging_manager import LoggingManager
from ui.progress import ProgressReporter


def _apply_cli_filters(messages, args):
    """Apply sender, time range, type and content filters based on CLI args.

    Note: This helper must be defined BEFORE calling main() to avoid NameError
    when the module is executed directly.
    """
    if not messages:
        return messages
    from datetime import datetime
    from services.message_filters import filter_messages
    from models.data_models import MessageType

    start = None
    end = None
    if args.start:
        try:
            start = datetime.fromisoformat(args.start)
        except Exception:
            logging.getLogger(__name__).warning(f"Invalid --start datetime: {args.start}")
    if args.end:
        try:
            end = datetime.fromisoformat(args.end)
        except Exception:
            logging.getLogger(__name__).warning(f"Invalid --end datetime: {args.end}")

    types = None
    if args.types:
        try:
            types_list = [t.strip().upper() for t in args.types.split(",") if t.strip()]
            types = []
            for t in types_list:
                types.append(MessageType[t])
        except Exception:
            logging.getLogger(__name__).warning(f"Invalid --types value: {args.types}")
            types = None

    return filter_messages(
        messages,
        sender=args.sender,
        start=start,
        end=end,
        types=types,
        contains=args.contains,
        min_confidence=args.min_confidence,
    )


def main():
    """
    基础提取 CLI 入口。

    函数级注释：
    - 支持基础提取与可选重试、滚动扫描；
    - 输出控制支持单一格式 (--format) 或多格式 (--formats)；
    - 新增存储层控制选项：
        * --exclude-fields 用于在 JSON/CSV 导出中移除指定字段（如 confidence_score, raw_ocr_text）
        * --exclude-time-only 过滤纯时间/日期分隔消息（例如 “10月21日23:47”、“星期四” 等）
        * --aggressive-dedup 启用激进去重（基于 sender+content 的内容级去重）
    - 过滤器支持按发件人、时间范围、类型、内容包含、最小置信度等。
    """
    parser = argparse.ArgumentParser(description="WeChatMsgGrabber")
    parser.add_argument("--prefix", default="extraction", help="filename prefix for output")
    parser.add_argument("--retry", action="store_true", help="use retry mechanism")
    parser.add_argument("--attempts", type=int, default=3, help="max retry attempts")
    parser.add_argument("--delay", type=float, default=0.5, help="delay between attempts")
    parser.add_argument("--no-progress", action="store_true", help="disable progress reporter")
    parser.add_argument("--scan", action="store_true", help="enable multi-batch scan with adaptive scrolling")
    parser.add_argument("--batches", type=int, default=5, help="max batches to scan when --scan enabled")
    parser.add_argument("--direction", choices=["up","down"], default="up", help="scroll direction for scan")
    parser.add_argument("--window-title", help="custom window title substring to locate WeChat window (fallback on macOS)")
    parser.add_argument("--chat-area", help="manual chat area override as 'x,y,w,h' (use when window detection is limited)")
    # OCR overrides
    parser.add_argument("--ocr-lang", help="override OCR language code (e.g. ch, en, japan, korean)")
    parser.add_argument("--clear-dedup-index", action="store_true", help="clear persistent dedup index before extraction")
    # Output overrides
    parser.add_argument("--format", choices=["json","csv","txt","md"], help="override output format (json/csv/txt/md)")
    parser.add_argument("--formats", help="multi formats output, comma-separated, e.g. json,csv,md")
    parser.add_argument("--outdir", help="override output directory")
    parser.add_argument("--dry-run", action="store_true", help="run extraction and show stats without saving")
    parser.add_argument("--no-dedup", action="store_true", help="disable deduplication for this run")
    parser.add_argument("--skip-empty", action="store_true", help="do not save when there are zero messages")
    parser.add_argument("--exclude-fields", help="exclude fields for JSON/CSV output, comma-separated (e.g. confidence_score,raw_ocr_text)")
    parser.add_argument("--exclude-time-only", action="store_true", help="filter out pure time/date separator messages before saving")
    parser.add_argument("--aggressive-dedup", action="store_true", help="enable aggressive content-level deduplication (sender+content)")
    # Filters
    parser.add_argument("--sender", help="filter by sender (case-insensitive substring)")
    parser.add_argument("--start", help="ISO datetime start bound, e.g. 2024-10-01 or 2024-10-01T10:00:00")
    parser.add_argument("--end", help="ISO datetime end bound, e.g. 2024-10-31 or 2024-10-31T18:00:00")
    parser.add_argument("--types", help="comma-separated message types to include, e.g. TEXT,IMAGE")
    parser.add_argument("--contains", help="filter by substring in content (case-insensitive)")
    parser.add_argument("--min-confidence", type=float, help="minimum confidence score threshold (0.0-1.0)")
    args = parser.parse_args()

    cfg_mgr = ConfigManager()
    app_cfg = cfg_mgr.get_config()

    # Setup logging
    LoggingManager().setup(app_cfg)

    reporter = None if args.no_progress else ProgressReporter(logging.getLogger("progress"))

    # Optionally clear persistent dedup index
    if args.clear_dedup_index:
        from services.storage_manager import StorageManager
        StorageManager(app_cfg.output).clear_dedup_index()

    controller = MainController()
    # Apply OCR language from CLI or config
    try:
        if args.ocr_lang:
            controller.ocr.config.language = args.ocr_lang.strip()
            logging.getLogger(__name__).info("Using OCR language from CLI: %s", controller.ocr.config.language)
        else:
            controller.ocr.config.language = app_cfg.ocr.language
            logging.getLogger(__name__).info("Using OCR language from config: %s", controller.ocr.config.language)
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to apply OCR language override: %s", e)
    # Apply optional window/chat-area overrides for limited environments
    if args.window_title:
        try:
            controller.scroll.set_title_override(args.window_title)
        except Exception:
            logging.getLogger(__name__).warning("Failed to apply --window-title override: %s", args.window_title)
    if args.chat_area:
        try:
            parts = [p.strip() for p in args.chat_area.split(',')]
            if len(parts) != 4:
                raise ValueError("chat-area must be 'x,y,w,h'")
            x, y, w, h = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]))
            controller.scroll.set_override_chat_area((x, y, w, h))
        except Exception as e:
            logging.getLogger(__name__).warning("Invalid --chat-area value '%s': %s", args.chat_area, e)
    if args.scan:
        # Use adaptive multi-batch scanning
        messages = controller.scan_chat_history(max_batches=args.batches, direction=args.direction, reporter=reporter)
        # Apply filters if any
        messages = _apply_cli_filters(messages, args)
        if args.dry_run:
            logging.getLogger(__name__).info(f"Dry-run: scanned {len(messages)} messages, no file saved.")
        else:
            if args.skip_empty and not messages:
                logging.getLogger(__name__).info("Skip-empty is enabled and there are zero messages. Nothing will be saved.")
            else:
                # Save scanned messages directly
                from models.config import OutputConfig
                # 解析多格式与字段排除
                multi_formats = None
                if args.formats:
                    multi_formats = [f.strip().lower() for f in args.formats.split(',') if f.strip()]
                exclude_fields = [f.strip() for f in (args.exclude_fields.split(',') if args.exclude_fields else []) if f.strip()]

                override = OutputConfig(
                    format=(args.format or app_cfg.output.format),
                    directory=(args.outdir or app_cfg.output.directory),
                    enable_deduplication=(False if args.no_dedup else app_cfg.output.enable_deduplication),
                    formats=multi_formats,
                    exclude_fields=exclude_fields,
                    exclude_time_only=bool(args.exclude_time_only or app_cfg.output.exclude_time_only),
                    aggressive_dedup=bool(args.aggressive_dedup or app_cfg.output.aggressive_dedup),
                )
                messages = controller.run_and_save(
                    filename_prefix=args.prefix,
                    use_retry=False,
                    reporter=None,
                    messages=messages,
                    output_override=override,
                )
    else:
        # Perform extraction first to allow filtering
        if args.retry:
            if reporter is not None:
                messages = controller.run_with_progress(
                    reporter,
                    max_attempts=args.attempts,
                    delay_seconds=args.delay,
                )
            else:
                messages = controller.run_with_retry(
                    max_attempts=args.attempts,
                    delay_seconds=args.delay,
                )
        else:
            messages = controller.run_once()

        # Apply filters if any
        messages = _apply_cli_filters(messages, args)

        if args.dry_run:
            logging.getLogger(__name__).info(f"Dry-run: extracted {len(messages)} messages, no file saved.")
        else:
            if args.skip_empty and not messages:
                logging.getLogger(__name__).info("Skip-empty is enabled and there are zero messages. Nothing will be saved.")
            else:
                # Save filtered messages
                from models.config import OutputConfig
                multi_formats = None
                if args.formats:
                    multi_formats = [f.strip().lower() for f in args.formats.split(',') if f.strip()]
                exclude_fields = [f.strip() for f in (args.exclude_fields.split(',') if args.exclude_fields else []) if f.strip()]
                override = OutputConfig(
                    format=(args.format or app_cfg.output.format),
                    directory=(args.outdir or app_cfg.output.directory),
                    enable_deduplication=(False if args.no_dedup else app_cfg.output.enable_deduplication),
                    formats=multi_formats,
                    exclude_fields=exclude_fields,
                    exclude_time_only=bool(args.exclude_time_only or app_cfg.output.exclude_time_only),
                    aggressive_dedup=bool(args.aggressive_dedup or app_cfg.output.aggressive_dedup),
                )
                messages = controller.run_and_save(
                    filename_prefix=args.prefix,
                    use_retry=False,
                    reporter=None,
                    messages=messages,
                    output_override=override,
                )

    logging.getLogger(__name__).info(f"Extraction finished, messages: {len(messages)}")


if __name__ == "__main__":
    main()