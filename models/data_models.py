"""
Core data models for WeChatMsgGrabber.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional
import uuid
import re


class MessageType(Enum):
    """Enumeration of supported message types."""
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class Rectangle:
    """Represents a rectangular region with position and dimensions."""
    x: int
    y: int
    width: int
    height: int


@dataclass
class SenderInfo:
    """Information about message sender."""
    name: str
    avatar_region: Optional[Rectangle]
    is_self: bool


@dataclass
class Message:
    """Core message data structure."""
    id: str
    sender: str
    content: str
    message_type: MessageType
    timestamp: datetime
    confidence_score: float
    raw_ocr_text: str

    def stable_key(self) -> str:
        """Return a stable deduplication key for this message.

        Priority: explicit id (非随机 UUID)。
        Fallback: sender|rounded_timestamp|trimmed content

        函数级注释：
        - 历史实现优先使用 id 作为去重键，但在实际扫描中 id 多为临时生成的 uuid4，导致跨帧重复无法去重；
        - 为兼容测试与业务期望，这里仅当 id 不是随机 UUID（例如来自上游系统的稳定主键）时才使用；
        - 否则回退到 sender + 秒级时间戳 + 去空白后的 content，以提升同一轮扫描内的稳定性。
        """
        if self.id:
            # 忽略临时生成的随机 UUID，避免阻断内容级去重
            try:
                u = uuid.UUID(str(self.id))
                # 当为 v4（典型的随机 UUID）时，视为不稳定主键，改用内容回退键
                if u.version != 4:
                    return str(self.id)
            except Exception:
                # 非 UUID 字符串（如业务主键），直接使用
                return str(self.id)
        
        # 降低时间戳精度到秒级别，避免微秒级差异导致重复
        rounded_timestamp = self.timestamp.replace(microsecond=0).isoformat()
        return f"{self.sender}|{rounded_timestamp}|{self.content.strip()}"


@dataclass
class OCRResult:
    """Result from OCR processing."""
    text: str
    confidence: float
    bounding_boxes: List[Rectangle]
    processing_time: float


@dataclass
class WindowInfo:
    """Information about application window."""
    handle: int
    position: Rectangle
    is_active: bool
    title: str


@dataclass
class TextRegion:
    """Represents a text region detected in image."""
    text: str
    bounding_box: Rectangle
    confidence: float