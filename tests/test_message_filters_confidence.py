from datetime import datetime

from services.message_filters import filter_messages
from models.data_models import Message, MessageType


def mk(sender, content, ts, conf):
    return Message(
        id=None,
        sender=sender,
        content=content,
        message_type=MessageType.TEXT,
        timestamp=ts,
        confidence_score=conf,
        raw_ocr_text=content,
    )


def test_min_confidence_filters_low_scores():
    base = datetime.now()
    msgs = [
        mk("A", "low", base, 0.3),
        mk("B", "mid", base, 0.8),
        mk("C", "high", base, 0.95),
    ]

    out = filter_messages(msgs, min_confidence=0.85)
    assert [m.content for m in out] == ["high"]


def test_min_confidence_boundary_inclusive():
    base = datetime.now()
    msgs = [mk("A", "exact", base, 0.9), mk("B", "below", base, 0.89)]

    out = filter_messages(msgs, min_confidence=0.9)
    assert [m.content for m in out] == ["exact"]