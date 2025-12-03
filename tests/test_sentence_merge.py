from models.data_models import TextRegion, Rectangle, MessageType
from services.message_parser import MessageParser, ParseOptions


def _mk_regions(lines, start_x=280, start_y=120, dy=12, w=280):
    regs = []
    y = start_y
    for t in lines:
        regs.append(TextRegion(text=t, bounding_box=Rectangle(start_x, y, w, 24), confidence=0.95))
        y += dy
    return regs


class TestSentenceMerge:
    def setup_method(self):
        self.parser = MessageParser(ParseOptions(line_grouping_vertical_gap=15, line_grouping_horizontal_gap=50))

    def test_merge_two_bubbles_into_one_text(self):
        # 模拟同侧紧邻的两段文本构成一句话
        lines1 = ["哈哈哈，但是公司还是抠啊，要3年/5年/10年的是"]
        lines2 = ["黄金，小年的是其他礼品"]
        regs = _mk_regions(lines1) + _mk_regions(lines2, start_y=150)
        msgs = self.parser.parse(regs)
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.TEXT
        assert "黄金，小年的是其他礼品" in msgs[0].content