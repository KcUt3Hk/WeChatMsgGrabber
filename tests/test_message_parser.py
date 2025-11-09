"""
Tests for message parsing and classification.
"""
from datetime import datetime
from models.data_models import TextRegion, Rectangle, MessageType
from services.message_parser import MessageParser, ParseOptions


class TestMessageParser:
    def setup_method(self):
        self.parser = MessageParser(ParseOptions(line_grouping_vertical_gap=15, line_grouping_horizontal_gap=50))

    def test_empty_input(self):
        assert self.parser.parse([]) == []

    def test_single_text_region(self):
        regions = [
            TextRegion(text="你好", bounding_box=Rectangle(100, 120, 200, 40), confidence=0.9)
        ]
        messages = self.parser.parse(regions)
        assert len(messages) == 1
        assert messages[0].content == "你好"
        assert messages[0].message_type == MessageType.TEXT
        assert messages[0].confidence_score == 0.9

    def test_grouping_multiple_lines_in_bubble(self):
        regions = [
            TextRegion(text="第一行", bounding_box=Rectangle(300, 200, 240, 30), confidence=0.8),
            TextRegion(text="第二行", bounding_box=Rectangle(305, 210, 240, 30), confidence=0.85),
            # New bubble far away
            TextRegion(text="另外一条消息", bounding_box=Rectangle(50, 320, 240, 30), confidence=0.92),
        ]
        messages = self.parser.parse(regions)
        assert len(messages) == 2
        assert messages[0].content == "第一行\n第二行"
        assert messages[1].content == "另外一条消息"

    def test_sender_side_inference(self):
        # Configure split at x=200
        parser = MessageParser(ParseOptions(left_right_split_x=200))
        regions = [
            TextRegion(text="对方消息", bounding_box=Rectangle(50, 100, 200, 30), confidence=0.9),
            TextRegion(text="我的消息", bounding_box=Rectangle(260, 110, 200, 30), confidence=0.9),
        ]
        messages = parser.parse(regions)
        assert len(messages) == 2
        assert messages[0].sender == "对方"
        assert messages[1].sender == "我"

    def test_type_classification_keywords(self):
        regions = [
            TextRegion(text="[图片]", bounding_box=Rectangle(100, 100, 120, 30), confidence=0.95),
            TextRegion(text="[语音] 15秒", bounding_box=Rectangle(120, 150, 120, 30), confidence=0.9),
            TextRegion(text="你已添加为好友", bounding_box=Rectangle(100, 200, 200, 30), confidence=0.85),
            TextRegion(text="普通文本消息", bounding_box=Rectangle(100, 250, 200, 30), confidence=0.9),
        ]
        messages = self.parser.parse(regions)
        assert messages[0].message_type == MessageType.IMAGE
        assert messages[1].message_type == MessageType.VOICE
        assert messages[2].message_type == MessageType.SYSTEM
        assert messages[3].message_type == MessageType.TEXT