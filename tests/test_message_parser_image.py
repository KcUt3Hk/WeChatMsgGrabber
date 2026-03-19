import unittest
from unittest.mock import MagicMock
from services.message_parser import MessageParser, ParseOptions
from models.data_models import TextRegion, Rectangle, MessageType

class TestMessageParserImageDetection(unittest.TestCase):
    def setUp(self):
        self.parser = MessageParser()

    def test_image_detection_large_font(self):
        """Test detection based on large font height (Poster title)."""
        # Create regions with one very large line
        regions = [
            TextRegion(
                text="BIG TITLE", 
                confidence=0.95, 
                bounding_box=Rectangle(x=10, y=10, width=200, height=60) # Height > 50
            ),
            TextRegion(
                text="subtitle", 
                confidence=0.9, 
                bounding_box=Rectangle(x=10, y=80, width=100, height=30)
            )
        ]
        # Parse
        # Note: The vertical gap is 80 - (10+60) = 10px. 
        # Default line_grouping_vertical_gap is 12. So these should be grouped.
        messages = self.parser.parse(regions)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].message_type, MessageType.IMAGE)
        
    def test_image_detection_sparse_layout(self):
        """Test detection based on sparse layout (large total height, few lines)."""
        # Create regions with large gap. 
        # We test _is_likely_image_with_text directly because parse() might split them 
        # if vertical gap is too large (default 12px, aggregate 60px).
        # Here we simulate a bubble that HAS been grouped (e.g. by custom options or other logic)
        # to verify the detection heuristic works.
        regions = [
            TextRegion(
                text="Top Text", 
                confidence=0.9, 
                bounding_box=Rectangle(x=10, y=10, width=100, height=30)
            ),
            TextRegion(
                text="Bottom Text", 
                confidence=0.9, 
                bounding_box=Rectangle(x=10, y=300, width=100, height=30)
            )
        ]
        # Total height = 300 - 10 + 30 = 320. 
        # Lines = 2. Avg space = 320 / 2 = 160 > 60.
        
        result = self.parser._is_likely_image_with_text(regions, "Top Text Bottom Text")
        self.assertTrue(result, "Should be detected as image due to sparse layout")

    def test_image_detection_keywords(self):
        """Test detection based on keywords + size."""
        regions = [
            TextRegion(
                text="USDT Bonus", 
                confidence=0.9, 
                bounding_box=Rectangle(x=10, y=10, width=200, height=30)
            ),
            TextRegion(
                text=("L" + "Bank"), 
                confidence=0.9, 
                bounding_box=Rectangle(x=10, y=120, width=100, height=30)
            )
        ]
        # Gap = 120 - 40 = 80px.
        # This exceeds default grouping (12) and agg (60).
        # So parse() would split this into two.
        # But here we test the detection logic on the set of regions assuming they form a unit.
        # To test parse(), we'd need them closer or better grouping.
        # Let's adjust y to be closer to ensure they group for the test if we used parse(),
        # OR just test the private method. 
        # The heuristic requires total_h > 100.
        # If I set y=60: Gap=20. Grouped? 20 > 12 (split) -> Agg check: 20 < 60 (merged!).
        # So let's try y=60.
        
        regions_close = [
            TextRegion(
                text="USDT Bonus", 
                confidence=0.9, 
                bounding_box=Rectangle(x=10, y=10, width=200, height=30)
            ),
            TextRegion(
                text=("L" + "Bank"), 
                confidence=0.9, 
                bounding_box=Rectangle(x=10, y=60, width=100, height=30)
            )
        ]
        # Total H = 60+30 - 10 = 80 < 100. Won't trigger heuristic (needs > 100).
        # So we need them far apart to trigger heuristic, but close enough to group.
        # Agg gap is 60. Max gap allowed is 60.
        # y=10, h=30 -> bottom=40. Next top=100 (gap=60). Bottom=130. Total H=120 > 100.
        # Gap=60. <= 60? Yes.
        
        regions_valid = [
            TextRegion(
                text="USDT Bonus", 
                confidence=0.9, 
                bounding_box=Rectangle(x=10, y=10, width=200, height=30)
            ),
            TextRegion(
                text=("L" + "Bank"), 
                confidence=0.9, 
                # Align center x to be similar to first one (center=110)
                # First: x=10, w=200 -> center 110.
                # Second: x=60, w=100 -> center 110.
                bounding_box=Rectangle(x=60, y=100, width=100, height=30)
            )
        ]
        # Gap = 100 - 40 = 60. Should merge.
        # Total H = 130 - 10 = 120 > 100.
        
        messages = self.parser.parse(regions_valid)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].message_type, MessageType.IMAGE)

    def test_normal_text(self):
        """Test normal text is NOT detected as image."""
        regions = [
            TextRegion(
                text="Hello world", 
                confidence=0.99, 
                bounding_box=Rectangle(x=10, y=10, width=100, height=30)
            ),
            TextRegion(
                text="How are you?", 
                confidence=0.99, 
                bounding_box=Rectangle(x=10, y=45, width=100, height=30)
            )
        ]
        # Gap is 5px.
        messages = self.parser.parse(regions)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].message_type, MessageType.TEXT)

    def test_low_confidence_flagging(self):
        """Test that low confidence text is flagged (via confidence_score)."""
        regions = [
            TextRegion(
                text="Unclear text", 
                confidence=0.5, 
                bounding_box=Rectangle(x=10, y=10, width=100, height=30)
            )
        ]
        messages = self.parser.parse(regions)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].message_type, MessageType.TEXT)
        self.assertLess(messages[0].confidence_score, 0.9)

if __name__ == '__main__':
    unittest.main()
