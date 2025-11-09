"""
Utilities to filter Message objects by sender, time range, type and content.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Sequence

from models.data_models import Message, MessageType


def filter_messages(
    messages: Iterable[Message],
    sender: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    types: Optional[Sequence[MessageType]] = None,
    contains: Optional[str] = None,
    min_confidence: Optional[float] = None,
) -> List[Message]:
    """Filter messages by criteria.

    - sender: case-insensitive substring match in Message.sender
    - start/end: inclusive datetime bounds on Message.timestamp
    - types: allowed MessageType sequence
    - contains: case-insensitive substring match in Message.content
    """
    sender_q = sender.lower() if sender else None
    contains_q = contains.lower() if contains else None
    type_set = set(types) if types else None

    out: List[Message] = []
    for m in messages:
        if sender_q and (m.sender or "").lower().find(sender_q) == -1:
            continue
        if start and m.timestamp < start:
            continue
        if end and m.timestamp > end:
            continue
        if type_set and m.message_type not in type_set:
            continue
        if contains_q and (m.content or "").lower().find(contains_q) == -1:
            continue
        if (min_confidence is not None) and (m.confidence_score < float(min_confidence)):
            continue
        out.append(m)
    return out