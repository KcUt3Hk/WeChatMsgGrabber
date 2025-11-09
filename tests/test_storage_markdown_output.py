import os
from datetime import datetime

from services.storage_manager import StorageManager
from models.config import OutputConfig
from models.data_models import Message, MessageType


def test_storage_manager_saves_markdown(tmp_path):
    cfg = OutputConfig(format="md", directory=str(tmp_path), enable_deduplication=False)
    storage = StorageManager(cfg)

    messages = [
        Message(
            id="a",
            sender="Alice",
            content="Hello",
            message_type=MessageType.TEXT,
            timestamp=datetime(2024, 10, 1, 10, 0, 0),
            confidence_score=0.9,
            raw_ocr_text="Hello",
        ),
        Message(
            id="b",
            sender="Bob",
            content="World",
            message_type=MessageType.TEXT,
            timestamp=datetime(2024, 10, 1, 10, 1, 0),
            confidence_score=0.9,
            raw_ocr_text="World",
        ),
    ]

    path = storage.save_messages(messages, filename_prefix="md_test")
    assert path.suffix == ".md"
    text = path.read_text(encoding="utf-8")
    assert "# WeChat Chat Export" in text
    assert "Alice" in text and "Bob" in text
    assert "Hello" in text and "World" in text