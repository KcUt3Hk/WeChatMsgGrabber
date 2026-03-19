from datetime import datetime

from services.storage_manager import StorageManager
from models.config import OutputConfig
from models.data_models import Message, MessageType


def _dup_messages():
    # Two identical messages (same id) should be considered duplicates when deduplication is enabled
    m1 = Message(
        id="same",
        sender="Alice",
        content="Hello",
        message_type=MessageType.TEXT,
        timestamp=datetime(2024, 10, 1, 12, 0, 0),
        confidence_score=0.9,
        raw_ocr_text="Hello",
    )
    m2 = Message(
        id="same",
        sender="Alice",
        content="Hello",
        message_type=MessageType.TEXT,
        timestamp=datetime(2024, 10, 1, 12, 0, 0),
        confidence_score=0.9,
        raw_ocr_text="Hello",
    )
    return [m1, m2]


def test_save_with_dedup_enabled_reduces_duplicates(tmp_path):
    cfg = OutputConfig(format="txt", directory=str(tmp_path), enable_deduplication=True)
    storage = StorageManager(cfg)
    path = storage.save_messages(_dup_messages(), filename_prefix="dedup_on")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # duplicates removed


def test_save_with_dedup_disabled_keeps_duplicates(tmp_path):
    cfg = OutputConfig(format="txt", directory=str(tmp_path), enable_deduplication=False)
    storage = StorageManager(cfg)
    path = storage.save_messages(_dup_messages(), filename_prefix="dedup_off")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # duplicates kept