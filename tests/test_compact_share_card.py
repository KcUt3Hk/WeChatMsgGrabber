from models.data_models import TextRegion, Rectangle, MessageType
from services.message_parser import MessageParser, ParseOptions


def _regions_compact(lines, x=260, y=100, dy=10, w=240, h=24):
    regs = []
    cy = y
    for t in lines:
        regs.append(TextRegion(text=t, bounding_box=Rectangle(x, cy, w, h), confidence=0.95))
        cy += dy
    return regs


class TestCompactShareCard:
    def setup_method(self):
        self.parser = MessageParser(ParseOptions(line_grouping_vertical_gap=15, line_grouping_horizontal_gap=50))

    def test_compact_wechat_mini_program_share(self):
        lines = [
            "微信小程序",
            "查收这份咖啡礼物",
            "来源：星巴克",
            "https://miniapp.example/abc",
        ]
        msgs = self.parser.parse(_regions_compact(lines))
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.SHARE

    def test_compact_bilibili_share(self):
        lines = [
            "哔哩哔哩",
            "视觉之旅：穿越光影",
            "UP主：阿B",
            "播放量：12.3万",
            "https://www.bilibili.com/video/BVxxxx",
        ]
        msgs = self.parser.parse(_regions_compact(lines, x=80))
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.SHARE

