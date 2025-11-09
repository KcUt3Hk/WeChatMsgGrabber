"""
Message parsing and classification utilities.

This module converts OCR-detected text regions into structured Message
objects, applies simple heuristics to classify message types, and
groups lines that belong to the same chat bubble.
"""
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import uuid

from models.data_models import Message, MessageType, TextRegion


@dataclass
class ParseOptions:
    """Options to guide parsing behavior."""
    # Maximum vertical gap (in pixels) between lines to consider them the same bubble
    line_grouping_vertical_gap: int = 12
    # Maximum horizontal offset to still consider lines in the same bubble
    line_grouping_horizontal_gap: int = 40
    # X threshold to differentiate left vs right alignment (heuristic)
    left_right_split_x: Optional[int] = None  # If None, inferred from regions


class MessageParser:
    """Parses OCR text regions into structured messages."""

    def __init__(self, options: Optional[ParseOptions] = None):
        self.options = options or ParseOptions()

    def parse(self, regions: List[TextRegion]) -> List[Message]:
        """Parse text regions into messages.

        Args:
            regions: List of OCR-detected text regions

        Returns:
            List of Message objects
        """
        if not regions:
            return []

        # Sort regions top-to-bottom, then left-to-right for determinism
        regions_sorted = sorted(
            regions,
            key=lambda r: (r.bounding_box.y, r.bounding_box.x)
        )

        # Optionally infer left/right split from median x coordinate
        split_x = self.options.left_right_split_x
        if split_x is None:
            xs = [r.bounding_box.x for r in regions_sorted]
            split_x = int(sum(xs) / max(len(xs), 1))

        # Group lines into bubbles using simple proximity heuristics
        bubbles: List[List[TextRegion]] = []
        current_group: List[TextRegion] = []

        for region in regions_sorted:
            if not current_group:
                current_group = [region]
                continue

            last = current_group[-1]
            v_gap = abs(region.bounding_box.y - last.bounding_box.y)
            h_gap = abs(region.bounding_box.x - last.bounding_box.x)

            if v_gap <= self.options.line_grouping_vertical_gap and h_gap <= self.options.line_grouping_horizontal_gap:
                current_group.append(region)
            else:
                bubbles.append(current_group)
                current_group = [region]

        if current_group:
            bubbles.append(current_group)

        messages: List[Message] = []

        for bubble in bubbles:
            # Concatenate lines
            content = "\n".join([line.text.strip() for line in bubble if line.text.strip()])
            raw_text = " ".join([line.text for line in bubble])
            avg_conf = sum([line.confidence for line in bubble]) / max(len(bubble), 1)

            # Determine sender side by first region x position
            first_x = bubble[0].bounding_box.x
            sender = "我" if first_x > split_x else "对方"

            msg_type = self._classify_message_type(content)
            msg_id = str(uuid.uuid4())

            messages.append(
                Message(
                    id=msg_id,
                    sender=sender,
                    content=content,
                    message_type=msg_type,
                    timestamp=datetime.now(),
                    confidence_score=avg_conf,
                    raw_ocr_text=raw_text,
                )
            )

        return messages

    def _classify_message_type(self, content: str) -> MessageType:
        """Classify the message type based on content heuristics.

        This is a simple baseline classifier using keywords; a production
        implementation can combine visual cues and richer patterns.
        """
        text = content.lower()
        # Common hints (Chinese and English)
        image_hints = ["[图片]", "图片", "photo", "image", "img"]
        voice_hints = ["[语音]", "语音", "voice", "audio"]
        system_hints = ["你已添加", "已成为你的朋友", "系统消息", "joined", "left", "invited"]

        if any(hint in content for hint in image_hints):
            return MessageType.IMAGE
        if any(hint in content for hint in voice_hints):
            return MessageType.VOICE
        if any(hint in content for hint in system_hints):
            return MessageType.SYSTEM

        # Default to TEXT if content is non-empty
        if content.strip():
            return MessageType.TEXT
        return MessageType.UNKNOWN