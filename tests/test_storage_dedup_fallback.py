from datetime import datetime

from services.storage_manager import StorageManager
from models.config import OutputConfig
from models.data_models import Message, MessageType


def _dup_messages_without_id():
    ts = datetime(2024, 10, 1, 12, 0, 0)
    m1 = Message(
        id="",
        sender="Alice",
        content="Hello",
        message_type=MessageType.TEXT,
        timestamp=ts,
        confidence_score=0.9,
        raw_ocr_text="Hello",
    )
    m2 = Message(
        id="",
        sender="Alice",
        content="Hello",
        message_type=MessageType.TEXT,
        timestamp=ts,
        confidence_score=0.9,
        raw_ocr_text="Hello",
    )
    return [m1, m2]


def test_dedup_with_fallback_key_removes_duplicates(tmp_path):
    cfg = OutputConfig(format="txt", directory=str(tmp_path), enable_deduplication=True)
    storage = StorageManager(cfg)
    path = storage.save_messages(_dup_messages_without_id(), filename_prefix="fallback_on")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # duplicates removed via fallback key


def test_no_dedup_keeps_duplicates_without_id(tmp_path):
    cfg = OutputConfig(format="txt", directory=str(tmp_path), enable_deduplication=False)
    storage = StorageManager(cfg)
    path = storage.save_messages(_dup_messages_without_id(), filename_prefix="fallback_off")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # duplicates kept when dedup disabled