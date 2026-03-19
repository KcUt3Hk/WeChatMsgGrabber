import json
from datetime import datetime

from services.storage_manager import StorageManager
from models.config import OutputConfig
from models.data_models import Message, MessageType


def test_clear_dedup_index(tmp_path):
    cfg = OutputConfig(format="json", directory=str(tmp_path), enable_deduplication=True)
    sm = StorageManager(cfg)

    m1 = Message(id="c1", sender="A", content="hello", message_type=MessageType.TEXT,
                 timestamp=datetime.now(), confidence_score=0.9, raw_ocr_text="hello")

    # First save creates index
    sm.save_messages([m1], filename_prefix="clear1")
    index_path = tmp_path / ".dedup_index.json"
    assert index_path.exists()

    # Clear index
    sm.clear_dedup_index()
    assert not index_path.exists()

    # Save again; index should be recreated and contain the id
    sm.save_messages([m1], filename_prefix="clear2")
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert "c1" in set(index)