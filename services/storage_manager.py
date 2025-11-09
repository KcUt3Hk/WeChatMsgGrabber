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
        """Serialize Message to a JSON-friendly dict."""
        base = {
            "id": msg.id,
            "sender": msg.sender,
            "content": msg.content,
            "message_type": msg.message_type.value if isinstance(msg.message_type, MessageType) else str(msg.message_type),
            "timestamp": msg.timestamp.isoformat(),
            "confidence_score": float(msg.confidence_score),
            "raw_ocr_text": msg.raw_ocr_text,
        }
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
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for m in messages:
                    writer.writerow(self._message_to_dict(m))
            self.logger.info(f"Saved {len(messages)} messages to {path}")
            return path

        if fmt == "txt":
            path = self._generate_filename(filename_prefix, "txt")
            with path.open("w", encoding="utf-8") as f:
                for m in messages:
                    line = f"[{m.timestamp.isoformat()}] {m.sender} ({m.message_type.value}): {m.content}"
                    f.write(line + "\n")
            self.logger.info(f"Saved {len(messages)} messages to {path}")
            return path

        # markdown format
        path = self._generate_filename(filename_prefix, "md")
        with path.open("w", encoding="utf-8") as f:
            f.write(f"# WeChat Chat Export\n\n")
            for m in messages:
                f.write(f"- [{m.timestamp.isoformat()}] **{m.sender}** ({m.message_type.value}): {m.content}\n")
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