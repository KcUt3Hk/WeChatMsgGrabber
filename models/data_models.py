"""
Core data models for WeChatMsgGraber.
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
    STICKER = "sticker"  # 新增：表情包/贴纸消息类型（可能包含文字叠加）
    VOICE = "voice"
    SYSTEM = "system"
    SHARE = "share"
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
    # 消息发生时间（从界面时间戳推断），格式建议 ISO 8601
    message_time: Optional[datetime] = None
    # 结构化扩展：分享卡片与引用元信息（可选）
    # - share_card: 若消息为“分享”类型（小红书/哔哩哔哩等），提供结构化字段以便统一渲染与导出；
    # - quote_meta: 若消息包含“引用气泡”，保留原始昵称与身份标签，并提取纯文本内容以供 UI 渲染。
    share_card: Optional["ShareCard"] = None
    quote_meta: Optional["QuoteMeta"] = None
    # 原始区域信息（用于图片/视频消息的后续处理，如截图保存或点击交互）
    original_region: Optional["Rectangle"] = None

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
            return str(self.id)

        return f"{self.sender}|{self.timestamp.isoformat()}|{self.content.strip()}"


@dataclass
class ShareCard:
    """Structured share card information.

    函数级注释：
    - 用于统一“分享”类内容（如小红书、哔哩哔哩），方便 UI 按规范化样式渲染；
    - 不同平台字段可能不同，未命中字段保持为 None；
    - canonical_url 便于后续跳转或导出。
    """
    platform: str  # 平台标识："小红书" / "哔哩哔哩" / "bilibili" / 其他
    title: str
    body: Optional[str] = None
    source: Optional[str] = None
    up_name: Optional[str] = None
    play_count: Optional[int] = None
    canonical_url: Optional[str] = None


@dataclass
class QuoteMeta:
    """Metadata for a quoted message bubble within a message.

    函数级注释：
    - original_nickname：被引用消息的昵称（进行简单转义处理以避免渲染异常）；
    - original_sender_label：统一标注为“我”或“对方”，便于 UI 左上角小字展示；
    - quoted_text：引用气泡内的纯文本（剔除昵称、时间戳等元信息）。
    """
    original_nickname: str
    original_sender_label: str  # "我" / "对方" / "未知"
    quoted_text: str


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
    type: str = "text"  # "text" or "image"
