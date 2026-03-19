import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from models.data_models import Message, MessageType
from models.config import OutputConfig
from services.storage_manager import StorageManager


def make_messages():
    base_time = datetime(2024, 1, 1, 12, 0, 0)
    msgs = [
        Message(
            id="m1",
            sender="Alice",
            content="你好，这是第一条消息",
            message_type=MessageType.TEXT,
            timestamp=base_time,
            confidence_score=0.95,
            raw_ocr_text="你好，这是第一条消息",
        ),
        Message(
            id="m1",  # duplicate id
            sender="Alice",
            content="你好，这是第一条消息",
            message_type=MessageType.TEXT,
            timestamp=base_time,
            confidence_score=0.95,
            raw_ocr_text="你好，这是第一条消息",
        ),
        Message(
            id="m2",
            sender="Bob",
            content="我收到了，谢谢！",
            message_type=MessageType.TEXT,
            timestamp=base_time + timedelta(minutes=1),
            confidence_score=0.9,
            raw_ocr_text="我收到了，谢谢！",
        ),
    ]
    return msgs


@pytest.mark.unit
def test_save_messages_json(tmp_path: Path):
    out_dir = tmp_path / "out_json"
    cfg = OutputConfig(format="json", directory=str(out_dir), enable_deduplication=True)
    storage = StorageManager(cfg)

    path = storage.save_messages(make_messages(), filename_prefix="testjson")
    assert path.exists()
    assert path.suffix == ".json"

    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    # dedup: only two unique ids
    assert len(data) == 2
    assert {d["id"] for d in data} == {"m1", "m2"}
    # check fields
    for d in data:
        assert set(d.keys()) == {
            "id", "sender", "content", "message_type", "timestamp", "confidence_score", "raw_ocr_text"
        }


@pytest.mark.unit
def test_save_messages_csv(tmp_path: Path):
    out_dir = tmp_path / "out_csv"
    cfg = OutputConfig(format="csv", directory=str(out_dir), enable_deduplication=True)
    storage = StorageManager(cfg)

    path = storage.save_messages(make_messages(), filename_prefix="testcsv")
    assert path.exists()
    assert path.suffix == ".csv"

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    # header + 2 rows after deduplication
    assert len(lines) == 3
    header = lines[0].split(",")
    assert header == [
        "id", "sender", "content", "message_type", "timestamp", "confidence_score", "raw_ocr_text"
    ]


@pytest.mark.unit
def test_save_messages_txt(tmp_path: Path):
    out_dir = tmp_path / "out_txt"
    cfg = OutputConfig(format="txt", directory=str(out_dir), enable_deduplication=True)
    storage = StorageManager(cfg)

    path = storage.save_messages(make_messages(), filename_prefix="testtxt")
    assert path.exists()
    assert path.suffix == ".txt"

    content = path.read_text(encoding="utf-8").strip().splitlines()
    # dedup: 2 lines
    assert len(content) == 2
    assert "Alice" in content[0] or "Bob" in content[0]
    assert "Alice" in content[1] or "Bob" in content[1]


@pytest.mark.unit
def test_output_dir_created(tmp_path: Path):
    out_dir = tmp_path / "nested" / "dir" / "structure"
    cfg = OutputConfig(format="json", directory=str(out_dir), enable_deduplication=False)
    storage = StorageManager(cfg)
    assert Path(cfg.directory).exists()
    path = storage.save_messages(make_messages(), filename_prefix="create_dir")
    assert path.exists()