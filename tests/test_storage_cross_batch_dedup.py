import json
from datetime import datetime

from services.storage_manager import StorageManager
from models.config import OutputConfig
from models.data_models import Message, MessageType


def test_cross_batch_dedup_json(tmp_path):
    cfg = OutputConfig(format="json", directory=str(tmp_path), enable_deduplication=True)
    sm = StorageManager(cfg)

    m1 = Message(id="m1", sender="A", content="hello", message_type=MessageType.TEXT,
                 timestamp=datetime.now(), confidence_score=0.9, raw_ocr_text="hello")
    m2 = Message(id="m2", sender="B", content="world", message_type=MessageType.TEXT,
                 timestamp=datetime.now(), confidence_score=0.9, raw_ocr_text="world")
    m3 = Message(id="m3", sender="C", content="!", message_type=MessageType.TEXT,
                 timestamp=datetime.now(), confidence_score=0.9, raw_ocr_text="!")

    path1 = sm.save_messages([m1, m2, m3], filename_prefix="batch1")
    assert path1.exists()

    # Second batch contains duplicates and one new item
    m4 = Message(id="m4", sender="D", content="new", message_type=MessageType.TEXT,
                 timestamp=datetime.now(), confidence_score=0.9, raw_ocr_text="new")
    path2 = sm.save_messages([m2, m3, m4], filename_prefix="batch2")
    assert path2.exists()

    data2 = json.loads(path2.read_text(encoding="utf-8"))
    ids2 = [d["id"] for d in data2]
    # Only the new message should be present due to cross-batch dedup
    assert ids2 == ["m4"]

    # Verify dedup index created and contains all ids
    index_path = tmp_path / ".dedup_index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert set(index) >= {"m1", "m2", "m3", "m4"}