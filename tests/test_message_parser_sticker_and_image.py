"""
贴图/emoji 与大图识别的单元测试。
"""
from models.data_models import TextRegion, Rectangle, MessageType
from services.message_parser import MessageParser, ParseOptions


def _mk_region(text: str, x=280, y=120, w=220, h=40, conf=0.95):
    return TextRegion(text=text, bounding_box=Rectangle(x, y, w, h), confidence=conf)


class TestStickerAndImage:
    def setup_method(self):
        # 开启默认解析器，允许外部额外关键词为空
        self.parser = MessageParser(ParseOptions(line_grouping_vertical_gap=15, line_grouping_horizontal_gap=50))

    def test_sticker_short_phrase(self):
        regions = [_mk_region("晚安呀", x=300)]
        msgs = self.parser.parse(regions)
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.STICKER

    def test_sticker_laughter_phrase(self):
        regions = [_mk_region("哈哈哈哈", x=50)]
        msgs = self.parser.parse(regions)
        assert msgs[0].message_type == MessageType.STICKER

    def test_sticker_emoji_only(self):
        regions = [_mk_region("😄", w=120, h=120, x=280, y=200)]
        msgs = self.parser.parse(regions)
        assert msgs[0].message_type == MessageType.STICKER

    def test_large_image_empty_text(self):
        # 无文字但包围盒较大，倾向识别为图片而非贴图
        regions = [TextRegion(text="", bounding_box=Rectangle(100, 100, 300, 300), confidence=0.9)]
        msgs = self.parser.parse(regions)
        assert msgs[0].message_type == MessageType.IMAGE

    def test_upstream_sticker_flag_empty_text(self):
        regions = [
            TextRegion(
                text="",
                bounding_box=Rectangle(120, 160, 140, 140),
                confidence=0.2,
                type="sticker",
            )
        ]
        msgs = self.parser.parse(regions)
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.STICKER

    def test_upstream_image_flag_empty_text(self):
        regions = [
            TextRegion(
                text="",
                bounding_box=Rectangle(120, 160, 220, 160),
                confidence=0.2,
                type="image",
            )
        ]
        msgs = self.parser.parse(regions)
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.IMAGE
