import json
from datetime import datetime

from services.storage_manager import StorageManager
from models.config import OutputConfig
from models.data_models import Message, MessageType, ShareCard, QuoteMeta


def test_markdown_share_card_rendering(tmp_path):
    """验证 Markdown 导出对分享卡片的渲染（平台/标题/正文/来源/UP主/播放量/链接）。"""
    cfg = OutputConfig(format="md", directory=str(tmp_path), enable_deduplication=False)
    storage = StorageManager(cfg)

    msg = Message(
        id="share_001",
        sender="我",
        content="分享一个视频",
        message_type=MessageType.SHARE,
        timestamp=datetime(2024, 10, 1, 10, 0, 0),
        confidence_score=0.98,
        raw_ocr_text="分享一个视频",
        share_card=ShareCard(
            platform="哔哩哔哩",
            title="测试视频标题",
            body="这是视频的简介内容",
            source="哔哩哔哩",
            up_name="UP测试",
            play_count=12345,
            canonical_url="https://www.bilibili.com/video/BV1xxxxxx"
        )
    )

    path = storage.save_messages([msg], filename_prefix="md_share")
    text = path.read_text(encoding="utf-8")
    assert "# WeChat Chat Export" in text
    assert "平台：哔哩哔哩" in text
    assert "标题：测试视频标题" in text
    assert "正文：这是视频的简介内容" in text
    assert "来源：哔哩哔哩" in text
    assert "UP主：UP测试" in text
    assert "播放量：12345" in text
    assert "链接：https://www.bilibili.com/video/BV1xxxxxx" in text


def test_markdown_quote_meta_rendering(tmp_path):
    """验证 Markdown 导出对引用气泡的渲染（引用昵称与引用正文采用 Markdown 引用块）。"""
    cfg = OutputConfig(format="md", directory=str(tmp_path), enable_deduplication=False)
    storage = StorageManager(cfg)

    msg = Message(
        id="quote_001",
        sender="对方",
        content="主消息正文",
        message_type=MessageType.TEXT,
        timestamp=datetime(2024, 10, 1, 10, 2, 0),
        confidence_score=0.96,
        raw_ocr_text="主消息正文",
        quote_meta=QuoteMeta(
            original_nickname="小明",
            original_sender_label="对方",
            quoted_text="引用的文本"
        )
    )

    path = storage.save_messages([msg], filename_prefix="md_quote")
    md = path.read_text(encoding="utf-8")
    assert "> 引用（对方）：小明" in md
    assert "> 引用的文本" in md
    assert "主消息正文" in md


def test_json_includes_share_and_quote(tmp_path):
    """验证 JSON 导出包含 share_card 与 quote_meta 嵌套结构。"""
    cfg = OutputConfig(format="json", directory=str(tmp_path), enable_deduplication=False)
    storage = StorageManager(cfg)

    share_msg = Message(
        id="share_json",
        sender="我",
        content="分享一个视频",
        message_type=MessageType.SHARE,
        timestamp=datetime(2024, 10, 1, 11, 0, 0),
        confidence_score=0.99,
        raw_ocr_text="分享一个视频",
        share_card=ShareCard(
            platform="小红书",
            title="旅行笔记",
            body="一段小红书的正文",
            source="小红书",
            canonical_url="https://www.xiaohongshu.com/notes/xxxx"
        )
    )

    quote_msg = Message(
        id="quote_json",
        sender="对方",
        content="包含引用的消息",
        message_type=MessageType.TEXT,
        timestamp=datetime(2024, 10, 1, 11, 1, 0),
        confidence_score=0.95,
        raw_ocr_text="包含引用的消息",
        quote_meta=QuoteMeta(
            original_nickname="老王",
            original_sender_label="对方",
            quoted_text="被引用的内容"
        )
    )

    path = storage.save_messages([share_msg, quote_msg], filename_prefix="json_share_quote")
    data = json.loads(path.read_text(encoding="utf-8"))
    # 两条消息
    assert len(data) == 2
    # 分享消息包含 share_card
    share_obj = next(d for d in data if d["id"] == "share_json")
    assert "share_card" in share_obj
    assert share_obj["share_card"]["platform"] == "小红书"
    assert share_obj["share_card"]["title"] == "旅行笔记"
    # 引用消息包含 quote_meta
    quote_obj = next(d for d in data if d["id"] == "quote_json")
    assert "quote_meta" in quote_obj
    assert quote_obj["quote_meta"]["original_nickname"] == "老王"
    assert quote_obj["quote_meta"]["quoted_text"] == "被引用的内容"