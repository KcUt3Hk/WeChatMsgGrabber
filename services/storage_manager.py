"""
Storage manager for exporting parsed messages to files.
Supports JSON, CSV, and TXT formats with optional deduplication.
"""
import json
import csv
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from models.data_models import Message, MessageType
from models.config import OutputConfig
import re


class StorageManager:
    """
    Handles persistence of Message objects to disk.
    """

    def __init__(self, output_config: Optional[OutputConfig] = None):
        self.logger = logging.getLogger(__name__)
        self.config = output_config or OutputConfig()
        self._ensure_output_dir()
        # Persistent deduplication index across saves
        self._dedup_index_path = Path(self.config.directory) / ".dedup_index.json"

    def _ensure_output_dir(self) -> None:
        """Create output directory if it does not exist."""
        try:
            out_dir = Path(self.config.directory)
            out_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Output directory ready: {out_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create output directory: {e}")
            raise

    def _generate_filename(self, prefix: str, ext: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{ts}.{ext}"
        return Path(self.config.directory) / filename

    def _message_to_dict(self, msg: Message) -> dict:
        """Serialize Message to a JSON-friendly dict.

        函数级注释：
        - 基础字段保持与现有测试兼容（id/sender/content/message_type/timestamp/confidence_score/raw_ocr_text）；
        - 当存在结构化扩展（share_card/quote_meta）时，序列化为嵌套字典，便于下游消费；
        - 支持通过 OutputConfig.exclude_fields 排除顶层字段（包含 share_card/quote_meta 顶层键）。
        """
        base = {
            "id": msg.id,
            "sender": msg.sender,
            "content": msg.content,
            "message_type": msg.message_type.value if isinstance(msg.message_type, MessageType) else str(msg.message_type),
            "timestamp": msg.timestamp.isoformat(),
            "confidence_score": float(msg.confidence_score),
            "raw_ocr_text": msg.raw_ocr_text,
        }
        # 消息发生时间（若存在）
        if msg.message_time:
            base["message_time"] = msg.message_time.isoformat()

        # 扩展结构：分享卡片与引用气泡元信息
        try:
            if getattr(msg, "share_card", None) is not None:
                base["share_card"] = asdict(msg.share_card)
        except Exception:
            pass
        try:
            if getattr(msg, "quote_meta", None) is not None:
                base["quote_meta"] = asdict(msg.quote_meta)
        except Exception:
            pass
        # 根据 OutputConfig.exclude_fields 进行字段排除（CSV/JSON 共用）
        try:
            exclude = set((self.config and getattr(self.config, 'exclude_fields', []) ) or [])
        except Exception:
            exclude = set()
        for k in list(base.keys()):
            if k in exclude:
                base.pop(k, None)
        return base

    def _deduplicate(self, messages: List[Message]) -> List[Message]:
        """Remove duplicate messages.

        Priority key: message.id; fallback: sender + timestamp + content.
        """
        seen = set()
        unique: List[Message] = []
        aggressive = bool(getattr(self.config, 'aggressive_dedup', False))

        # 次级键：基于发送方 + 内容（去空白、统一小写），用于更强去重
        def secondary_key(msg: Message) -> str:
            return f"{(msg.sender or '').strip().lower()}|{(msg.content or '').strip().lower()}"

        seen_secondary = set()
        for m in messages:
            key = self._get_message_key(m)
            sec = secondary_key(m)
            if key in seen:
                continue
            if aggressive and sec in seen_secondary:
                # 激进模式：内容级重复直接跳过
                continue
            seen.add(key)
            if aggressive:
                seen_secondary.add(sec)
            unique.append(m)
        return unique

    @staticmethod
    def _get_message_key(m: Message) -> str:
        # Use centralized key generation from Message
        return m.stable_key()

    def _load_dedup_index(self) -> set:
        """Load persistent deduplication index from disk."""
        try:
            if self._dedup_index_path.exists():
                with self._dedup_index_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return set(data)
                    self.logger.warning("Dedup index file malformed, resetting.")
            return set()
        except Exception as e:
            self.logger.warning(f"Failed to load dedup index: {e}")
            return set()

    def _save_dedup_index(self, index: set) -> None:
        """Persist deduplication index to disk."""
        try:
            with self._dedup_index_path.open("w", encoding="utf-8") as f:
                json.dump(sorted(index), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save dedup index: {e}")

    def clear_dedup_index(self) -> None:
        """Clear persistent deduplication index file if it exists."""
        try:
            if self._dedup_index_path.exists():
                self._dedup_index_path.unlink()
                self.logger.info(f"Cleared dedup index: {self._dedup_index_path}")
        except Exception as e:
            self.logger.warning(f"Failed to clear dedup index: {e}")

    def _write_messages(self, messages: List[Message], fmt: str, filename_prefix: str) -> Path:
        """Write messages to a single file in the given format.

        参数:
        - messages: 已完成去重与索引过滤后的消息列表
        - fmt: 输出格式（json/csv/txt/md）
        - filename_prefix: 文件名前缀

        返回: 写入文件的路径
        """
        fmt = (fmt or "json").lower()
        if fmt not in {"json", "csv", "txt", "md"}:
            raise ValueError(f"Unsupported output format: {fmt}")

        if fmt == "json":
            path = self._generate_filename(filename_prefix, "json")
            data = [self._message_to_dict(m) for m in messages]
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Saved {len(messages)} messages to {path}")
            return path

        if fmt == "csv":
            path = self._generate_filename(filename_prefix, "csv")
            # 动态移除被排除的字段
            default_fields = ["id", "sender", "content", "message_type", "timestamp", "confidence_score", "raw_ocr_text"]
            try:
                exclude = set((self.config and getattr(self.config, 'exclude_fields', []) ) or [])
            except Exception:
                exclude = set()
            fieldnames = [f for f in default_fields if f not in exclude]
            with path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for m in messages:
                    writer.writerow(self._message_to_dict(m))
            self.logger.info(f"Saved {len(messages)} messages to {path}")
            return path

        if fmt == "txt":
            path = self._generate_filename(filename_prefix, "txt")
            with path.open("w", encoding="utf-8") as f:
                for m in messages:
                    f.write(self._format_txt_message(m) + "\n")
            self.logger.info(f"Saved {len(messages)} messages to {path}")
            return path

        # markdown format
        path = self._generate_filename(filename_prefix, "md")
        with path.open("w", encoding="utf-8") as f:
            f.write(f"# WeChat Chat Export\n\n")
            for m in messages:
                f.write(self._format_markdown_message(m) + "\n")
        self.logger.info(f"Saved {len(messages)} messages to {path}")
        return path

    def save_messages(self, messages: List[Message], filename_prefix: str = "extraction") -> Path:
        """Save messages to disk according to configured format.

        Returns the path of the written file.
        """
        # 可选：在写入前过滤掉仅包含时间/日期的分隔消息
        try:
            if getattr(self.config, 'exclude_time_only', False):
                messages = [m for m in messages if not self._is_time_only_content(m.content)]
        except Exception:
            pass

        if self.config.enable_deduplication:
            # First deduplicate within this batch
            messages = self._deduplicate(messages)
            # Then filter out messages already saved in previous runs
            index = self._load_dedup_index()
            filtered: List[Message] = []
            for m in messages:
                key = self._get_message_key(m)
                if key not in index:
                    filtered.append(m)
                    index.add(key)
            messages = filtered
            # Persist updated index
            self._save_dedup_index(index)
        fmt = (self.config.format or "json").lower()
        return self._write_messages(messages, fmt, filename_prefix)

    def save_messages_multiple(self, messages: List[Message], filename_prefix: str, formats: List[str]) -> List[Path]:
        """Save messages to multiple formats in one pass, sharing a single deduplication step.

        参数:
        - messages: 待保存的消息列表
        - filename_prefix: 文件名前缀
        - formats: 输出格式列表（如 ["json", "csv", "txt", "md"]）

        返回: 所有生成文件的路径列表
        """
        # 规范化并去重格式顺序，保留用户传入顺序
        allowed = {"json", "csv", "txt", "md"}
        norm_formats: List[str] = []
        for f in (formats or []):
            lf = (f or "").lower()
            if lf and lf not in norm_formats:
                norm_formats.append(lf)
        if not norm_formats:
            # 回退到单一格式配置
            norm_formats = [(self.config.format or "json").lower()]

        invalid = [f for f in norm_formats if f not in allowed]
        if invalid:
            raise ValueError(f"Unsupported output formats: {', '.join(invalid)}")

        # 可选：在写入前过滤掉仅包含时间/日期的分隔消息
        try:
            if getattr(self.config, 'exclude_time_only', False):
                messages = [m for m in messages if not self._is_time_only_content(m.content)]
        except Exception:
            pass

        # 去重与索引过滤仅执行一次
        if self.config.enable_deduplication:
            messages = self._deduplicate(messages)
            index = self._load_dedup_index()
            filtered: List[Message] = []
            for m in messages:
                key = self._get_message_key(m)
                if key not in index:
                    filtered.append(m)
                    index.add(key)
            messages = filtered
            self._save_dedup_index(index)

        # 逐格式写入
        paths: List[Path] = []
        for fmt in norm_formats:
            path = self._write_messages(messages, fmt, filename_prefix)
            paths.append(path)
        return paths

    def append_messages_to_file(self, messages: List[Message], file_path: Path, fmt: str) -> None:
        """Append messages to an existing file.
        
        Args:
            messages: List of messages to append.
            file_path: Path to the target file.
            fmt: Output format (json, csv, txt, md).
        """
        if not messages:
            return

        fmt = (fmt or "json").lower()
        if fmt not in {"json", "csv", "txt", "md"}:
            raise ValueError(f"Unsupported output format: {fmt}")

        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # For JSON, we use JSON Lines (one JSON object per line) for appendability
        # Standard JSON array cannot be easily appended to without reading the whole file.
        if fmt == "json":
            with file_path.open("a", encoding="utf-8") as f:
                for m in messages:
                    # Compact JSON line
                    json.dump(self._message_to_dict(m), f, ensure_ascii=False)
                    f.write("\n")
            return

        if fmt == "csv":
            # 动态移除被排除的字段
            default_fields = ["id", "sender", "content", "message_type", "timestamp", "message_time", "confidence_score", "raw_ocr_text"]
            try:
                exclude = set((self.config and getattr(self.config, 'exclude_fields', []) ) or [])
            except Exception:
                exclude = set()
            fieldnames = [f for f in default_fields if f not in exclude]
            
            # Check if file exists and is empty to write header
            write_header = not file_path.exists() or file_path.stat().st_size == 0
            
            with file_path.open("a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()
                for m in messages:
                    writer.writerow(self._message_to_dict(m))
            return

        if fmt == "txt":
            with file_path.open("a", encoding="utf-8") as f:
                for m in messages:
                    f.write(self._format_txt_message(m) + "\n")
            return

        if fmt == "md":
            # Check if file exists and is empty to write header
            write_header = not file_path.exists() or file_path.stat().st_size == 0
            
            with file_path.open("a", encoding="utf-8") as f:
                if write_header:
                    f.write(f"# WeChat Chat Export\n\n")
                for m in messages:
                    f.write(self._format_markdown_message(m) + "\n")
            return

    def _is_time_only_content(self, text: str) -> bool:
        """Detect if content is a pure time/date marker (e.g., chat separators).

        函数级注释：
        - 识别常见的微信时间分隔格式，如“10月21日23:47”、“18:15”、“星期四”、“昨天 23:47”等；
        - 仅当整段文本完全匹配这些模式时才判定为“纯时间”，避免误伤包含实际内容的消息。
        - 支持通过 OutputConfig.time_only_patterns 注入用户自定义正则，扩展匹配范围；
          当提供自定义模式时，会在内置模式之后追加匹配。
        """
        if not text:
            return False
        s = str(text).strip()
        if not s:
            return False
        patterns = [
            # 日期（可选年份，可选时间）示例：2024年10月21日、10月21日 23:47、2024年10月21日23:47
            r"^(?:\d{4}年)?\s*\d{1,2}月\s*\d{1,2}日\s*(?:\d{1,2}:\d{2}(?::\d{2})?)?\s*$",
            # 纯时间（24小时制）示例：18:15、08:05:12
            r"^\d{1,2}:\d{2}(?::\d{2})?$",
            # 星期（中文）示例：星期四、星期天
            r"^星期[一二三四五六日天]$",
            # 星期（中文简写）示例：周一、周日
            r"^周[一二三四五六日天]$",
            # 相对日期 + 时间 示例：昨天 23:47、今天 08:30、前天 12:00
            r"^(?:昨天|今天|前天)\s*\d{1,2}:\d{2}(?::\d{2})?$",
            # 仅相对日期（部分客户端可能出现）示例：昨天、今天、前天
            r"^(?:昨天|今天|前天)$",
            # 上下午时间（中文）示例：下午 3:05、上午9:15、中午 12:00、凌晨 1:20、晚间 7:30、傍晚 6:45
            r"^(?:上午|下午|中午|凌晨|傍晚|晚间)\s*\d{1,2}:\d{2}(?::\d{2})?$",
            # AM/PM 英文示例：AM 10:05、PM 3:25
            r"^(?:AM|PM)\s*\d{1,2}:\d{2}(?::\d{2})?$",
        ]
        # 追加用户自定义模式（若提供）
        try:
            extra = (getattr(self.config, 'time_only_patterns', None) or [])
            for pat in extra:
                if isinstance(pat, str) and pat:
                    patterns.append(pat)
        except Exception:
            pass
        for pat in patterns:
            if re.match(pat, s):
                return True
        # 仅由数字、冒号、空格与中文日期单位构成的文本（无其它字母/汉字）
        if re.match(r"^[0-9\s:年/月日.-]+$", s):
            # 必须包含至少一个日期单位或时间冒号
            if any(ch in s for ch in ["年", "月", "日", ":"]):
                return True
        return False

    def _format_markdown_message(self, m: Message) -> str:
        """Format a single message into Markdown.

        函数级注释：
        - 普通消息：以列表项形式展示 "- [timestamp] **sender** (type): content"；
        - 分享消息（MessageType.SHARE）：在主行之后追加缩进的细节（平台/标题/正文/来源/UP主/播放量/链接）；
        - 引用气泡：在主行之前以 Markdown 引用块（>）展示原始昵称与引用正文，保留“我/对方”标签。
        """
        # STICKER/IMAGE：当内容为空时，给出明确备注，避免被误认为丢失
        if m.message_type == MessageType.STICKER and not (m.content and str(m.content).strip()):
            display_content = "表情包未识别出文字"
        elif m.message_type == MessageType.IMAGE and not (m.content and str(m.content).strip()):
            display_content = "图片未识别出文字"
        else:
            display_content = m.content
        
        time_str = m.timestamp.isoformat()
        if m.message_time:
            time_str = f"{m.message_time.isoformat()} (Capture: {time_str})"
            
        header = f"- [{time_str}] **{m.sender}** ({m.message_type.value}): {display_content}"
        lines = [header]

        # 引用气泡（优先在主行之前给出上下文）
        try:
            if getattr(m, "quote_meta", None):
                qm = m.quote_meta
                # 使用 Markdown 引用块
                lines.insert(0, f"> 引用（{qm.original_sender_label}）：{qm.original_nickname}")
                if qm.quoted_text:
                    lines.insert(1, f"> {qm.quoted_text}")
        except Exception:
            pass

        # 分享卡片详情（追加在主行之后）
        try:
            if m.message_type == MessageType.SHARE and getattr(m, "share_card", None):
                sc = m.share_card
                detail: list[str] = []
                if sc.platform:
                    detail.append(f"  - 平台：{sc.platform}")
                if sc.title:
                    detail.append(f"  - 标题：{sc.title}")
                if sc.body:
                    # 将正文每行以额外缩进呈现，避免过长换行
                    for ln in str(sc.body).splitlines():
                        if ln.strip():
                            detail.append(f"  - 正文：{ln.strip()}")
                if sc.source:
                    detail.append(f"  - 来源：{sc.source}")
                if sc.up_name:
                    detail.append(f"  - UP主：{sc.up_name}")
                if sc.play_count is not None:
                    detail.append(f"  - 播放量：{sc.play_count}")
                if sc.canonical_url:
                    detail.append(f"  - 链接：{sc.canonical_url}")
                lines.extend(detail)
        except Exception:
            pass

        return "\n".join(lines)

    def _format_txt_message(self, m: Message) -> str:
        """Format a single message into human-readable TXT line(s).

        函数级注释：
        - 普通消息：单行输出 "[timestamp] sender (type): content"；
        - 分享消息：追加若干行细节（平台/标题/正文/来源/UP主/播放量/链接）；
        - 引用气泡：在主行之前追加前缀为 "引用> " 的上下文两行。
        """
        # STICKER/IMAGE：当内容为空时，给出明确备注，避免被误认为丢失
        if m.message_type == MessageType.STICKER and not (m.content and str(m.content).strip()):
            display_content = "表情包未识别出文字"
        elif m.message_type == MessageType.IMAGE and not (m.content and str(m.content).strip()):
            display_content = "图片未识别出文字"
        else:
            display_content = m.content
        
        time_str = m.timestamp.isoformat()
        if m.message_time:
            time_str = f"{m.message_time.isoformat()}"
            
        header = f"[{time_str}] {m.sender} ({m.message_type.value}): {display_content}"
        lines = [header]

        # 引用气泡
        try:
            if getattr(m, "quote_meta", None):
                qm = m.quote_meta
                lines.insert(0, f"引用> {qm.original_sender_label}：{qm.original_nickname}")
                if qm.quoted_text:
                    lines.insert(1, f"引用> {qm.quoted_text}")
        except Exception:
            pass

        # 分享卡片
        try:
            if m.message_type == MessageType.SHARE and getattr(m, "share_card", None):
                sc = m.share_card
                detail: list[str] = []
                if sc.platform:
                    detail.append(f"平台：{sc.platform}")
                if sc.title:
                    detail.append(f"标题：{sc.title}")
                if sc.body:
                    for ln in str(sc.body).splitlines():
                        if ln.strip():
                            detail.append(f"正文：{ln.strip()}")
                if sc.source:
                    detail.append(f"来源：{sc.source}")
                if sc.up_name:
                    detail.append(f"UP主：{sc.up_name}")
                if sc.play_count is not None:
                    detail.append(f"播放量：{sc.play_count}")
                if sc.canonical_url:
                    detail.append(f"链接：{sc.canonical_url}")
                lines.extend(detail)
        except Exception:
            pass

        return "\n".join(lines)
