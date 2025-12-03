from models.data_models import TextRegion, Rectangle, MessageType
from services.message_parser import MessageParser, ParseOptions


class TestTimeSeparatorClassification:
    def setup_method(self):
        self.parser = MessageParser(ParseOptions(line_grouping_vertical_gap=15, line_grouping_horizontal_gap=50))

    def test_weekday_time_separator(self):
        regions = [TextRegion(text="星期五 23:53", bounding_box=Rectangle(240, 300, 180, 26), confidence=0.95)]
        msgs = self.parser.parse(regions)
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.SYSTEM
        assert msgs[0].sender == "系统"

    def test_compact_weekday_time_separator(self):
        regions = [TextRegion(text="星期五23:53", bounding_box=Rectangle(240, 320, 180, 26), confidence=0.95)]
        msgs = self.parser.parse(regions)
        assert len(msgs) == 1
        assert msgs[0].message_type == MessageType.SYSTEM
        assert msgs[0].sender == "系统"