from datetime import datetime, timedelta

from services.message_filters import filter_messages
from models.data_models import Message, MessageType


def _mk_msg(sender, content, ts, t=MessageType.TEXT):
    return Message(
        id=None,
        sender=sender,
        content=content,
        message_type=t,
        timestamp=ts,
        confidence_score=0.9,
        raw_ocr_text=content,
    )


def test_filter_by_sender_and_contains():
    base = datetime.now()
    msgs = [
        _mk_msg("Alice", "Hello Bob", base),
        _mk_msg("Bob", "Hi Alice", base + timedelta(seconds=1)),
        _mk_msg("Carol", "Other", base + timedelta(seconds=2)),
    ]

    out = filter_messages(msgs, sender="ali", contains="hi")
    # sender contains 'ali' => Alice; content contains 'hi' => 'Hello Bob' doesn't contain; so expect empty
    assert out == []

    out2 = filter_messages(msgs, sender="bob")
    assert len(out2) == 1 and out2[0].sender.lower() == "bob"


def test_filter_by_time_range_and_types():
    base = datetime.now()
    msgs = [
        _mk_msg("A", "t0", base, t=MessageType.TEXT),
        _mk_msg("A", "i1", base + timedelta(seconds=1), t=MessageType.IMAGE),
        _mk_msg("A", "t2", base + timedelta(seconds=2), t=MessageType.TEXT),
    ]

    start = base + timedelta(seconds=1)
    end = base + timedelta(seconds=2)

    out = filter_messages(msgs, start=start, end=end, types=[MessageType.TEXT])
    # only include t2 which is TEXT within [start, end]
    assert len(out) == 1 and out[0].content == "t2"