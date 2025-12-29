
import unittest
from datetime import datetime
from services.message_parser import MessageParser
from models.data_models import MessageType, TextRegion, Rectangle

class TestMessageParserOptimization(unittest.TestCase):
    def setUp(self):
        self.parser = MessageParser()

    def test_xiaohongshu_text_vs_card(self):
        """Test strict distinction between text and card for Xiaohongshu."""
        
        # Case 1: Conversational Text (Should NOT be ShareCard)
        # "要看下小红书，我看有推荐的，600每周，2400一个月"
        text_content = "要看下小红书\n我看有推荐的\n600每周\n2400一个月"
        card = self.parser._extract_share_card(text_content)
        self.assertIsNone(card, "Conversational text should not be parsed as ShareCard")
        
        # Case 2: Actual Share Card
        # "装修攻略\n这是我见过的最全的装修攻略了\n小红书"
        card_content = "装修攻略\n这是我见过的最全的装修攻略了\n小红书"
        card = self.parser._extract_share_card(card_content)
        self.assertIsNotNone(card, "Actual card content should be parsed as ShareCard")
        self.assertEqual(card.platform, "小红书")
        self.assertEqual(card.title, "装修攻略")
        
    def test_bilibili_card(self):
        """Test Bilibili card parsing."""
        content = "这是一个B站视频\nUP主：某某某\n播放量：100万\n哔哩哔哩"
        card = self.parser._extract_share_card(content)
        self.assertIsNotNone(card)
        self.assertEqual(card.platform, "哔哩哔哩")
        self.assertEqual(card.up_name, "某某某")
        self.assertEqual(card.play_count, 1000000) # Assuming _parse_play_count handles "100万" -> 1000000

    def test_miniprogram_card(self):
        """Test MiniProgram card parsing."""
        content = "星巴克\n你的朋友送你一份心意礼物\n查收\n微信小程序"
        card = self.parser._extract_share_card(content)
        self.assertIsNotNone(card)
        self.assertEqual(card.source, "星巴克")

    def test_generic_card(self):
        """Test Generic card parsing."""
        content = "这是一个通用分享\n描述内容\n来源：某APP"
        # Since _is_likely_card requires keywords, I must include one.
        # "来源" is a keyword.
        card = self.parser._extract_share_card(content)
        self.assertIsNotNone(card)
        self.assertEqual(card.title, "这是一个通用分享")
        self.assertEqual(card.source, "某APP")
        self.assertEqual(card.platform, "分享")
        
    def test_not_card_strict(self):
        """Test strict rejection of non-card text."""
        content = "Hello World" # No keywords, no URL
        card = self.parser._extract_share_card(content)
        self.assertIsNone(card)
        
if __name__ == '__main__':
    unittest.main()
