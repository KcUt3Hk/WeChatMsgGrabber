from datetime import datetime

from models.data_models import Message, MessageType


def test_message_stable_key_uses_id_when_present():
    m = Message(
        id="abc",
        sender="Alice",
        content="Hello",
        message_type=MessageType.TEXT,
        timestamp=datetime(2024, 10, 1, 12, 0, 0),
        confidence_score=0.9,
        raw_ocr_text="Hello",
    )
    assert m.stable_key() == "abc"


def test_message_stable_key_fallback_when_id_missing():
    m = Message(
        id="",
        sender="Bob",
        content="  Hi  ",
        message_type=MessageType.TEXT,
        timestamp=datetime(2024, 10, 2, 8, 30, 0),
        confidence_score=0.8,
        raw_ocr_text="Hi",
    )
    expect = f"Bob|{m.timestamp.isoformat()}|Hi"
    assert m.stable_key() == expect