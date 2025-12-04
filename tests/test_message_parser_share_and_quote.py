"""
针对分享卡片与引用消息识别的测试用例。
"""
from models.data_models import TextRegion, Rectangle, MessageType
from services.message_parser import MessageParser, ParseOptions


def _mk_regions(lines, start_x=100, start_y=100, dx=0, dy=12, width=240):
    """构造一组 TextRegion 便于测试分组与解析。

    函数级注释：
    - 以固定的水平/垂直间距生成文本区域，确保被归为同一聊天气泡；
    - 可通过 start_x 控制左右侧，以便覆盖 sender 推断逻辑。
    """
    regions = []
    y = start_y
    for txt in lines:
        regions.append(TextRegion(text=txt, bounding_box=Rectangle(start_x, y, width, 24), confidence=0.95))
        y += dy
        start_x += dx
    return regions


class TestShareAndQuote:
    def setup_method(self):
        self.parser = MessageParser(ParseOptions(line_grouping_vertical_gap=15, line_grouping_horizontal_gap=50))

    def test_xiaohongshu_share_card(self):
        lines = [
            "小红书",
            "秋日咖啡指南",
            "在微风里喝一杯热拿铁",
            "来源：小红书",
            "https://www.xiaohongshu.com/abc123",
        ]
        msgs = self.parser.parse(_mk_regions(lines, start_x=300))
        assert len(msgs) == 1
        m = msgs[0]
        assert m.message_type == MessageType.SHARE
        assert m.share_card is not None
        assert m.share_card.platform == "小红书"
        assert m.share_card.title == "秋日咖啡指南"
        assert (m.share_card.body or "").startswith("在微风里")
        # 来源由结构化字段提供，正文不应包含“来源：”行
        assert "来源：" not in (m.share_card.body or "")
        assert m.share_card.source == "小红书"
        assert (m.share_card.canonical_url or "").startswith("https://")

    def test_bilibili_share_card(self):
        lines = [
            "哔哩哔哩",
            "视觉之旅：穿越光影",
            "UP主：阿B",
            "播放量：12.3万",
            "来源：哔哩哔哩",
            "https://www.bilibili.com/video/BVxxxx",
        ]
        msgs = self.parser.parse(_mk_regions(lines, start_x=50))
        assert len(msgs) == 1
        m = msgs[0]
        assert m.message_type == MessageType.SHARE
        sc = m.share_card
        assert sc is not None
        assert sc.platform in ("哔哩哔哩", "bilibili")
        assert sc.title.startswith("视觉之旅")
        assert sc.up_name == "阿B"
        assert sc.play_count == 123000
        assert sc.source == "哔哩哔哩"
        assert (sc.canonical_url or "").startswith("https://")

    def test_quote_detection_and_sanitize(self):
        # 右侧（我）回复，引用对方内容
        lines = [
            "好友A🙂",
            "明天见",
            "好的",
            "12:30",
        ]
        msgs = self.parser.parse(_mk_regions(lines, start_x=280))
        assert len(msgs) == 1
        m = msgs[0]
        assert m.quote_meta is not None
        assert m.quote_meta.original_nickname.startswith("好友A")
        assert m.quote_meta.original_sender_label == "对方"
        assert m.quote_meta.quoted_text == "明天见"
        # 内容已剔除昵称与时间戳，仅保留纯文本
        assert m.content == "明天见\n好的"

    def test_quote_self_label_and_emoji_nickname(self):
        lines = [
            "我😄",
            "请查看这段",
            "13:20",
            "稍后回复",
        ]
        msgs = self.parser.parse(_mk_regions(lines, start_x=300))
        m = msgs[0]
        assert m.quote_meta is not None
        assert m.quote_meta.original_sender_label == "我"
        assert m.quote_meta.quoted_text == "请查看这段"
        assert "13:20" not in m.content

    def test_quote_long_nickname_and_escape(self):
        lines = [
            "(*^_^*)Alice🚀🚀",
            "请尽快修复",
            "昨天 05:12",
            "已修复",
        ]
        msgs = self.parser.parse(_mk_regions(lines, start_x=45))
        m = msgs[0]
        assert m.quote_meta is not None
        # 转义后应仍保留可读字符与表情，不包含尖括号
        assert "<" not in m.quote_meta.original_nickname
        assert m.quote_meta.quoted_text == "请尽快修复"
