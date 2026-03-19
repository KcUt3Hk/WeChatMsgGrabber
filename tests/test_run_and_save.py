import json
from datetime import datetime

from controllers.main_controller import MainController
from models.config import AppConfig
from models.data_models import Message, MessageType


def test_run_and_save_json(tmp_path, monkeypatch):
    mc = MainController()

    # Prepare a successful message batch
    msg = Message(
        id="m1",
        sender="Tester",
        content="Hello",
        message_type=MessageType.TEXT,
        timestamp=datetime.now(),
        confidence_score=0.95,
        raw_ocr_text="Hello",
    )
    monkeypatch.setattr(mc, "run_with_retry", lambda max_attempts=3, delay_seconds=0.5: [msg])

    # Provide config via a dummy ConfigManager
    class DummyCfgMgr:
        def __init__(self, *args, **kwargs):
            pass

        def get_config(self):
            cfg = AppConfig(
                output_format="json",
                output_directory=str(tmp_path),
                enable_deduplication=True,
            )
            return cfg

    import controllers.main_controller as mc_mod
    monkeypatch.setattr(mc_mod, "ConfigManager", DummyCfgMgr)

    messages = mc.run_and_save(filename_prefix="test_save", use_retry=True)

    # Verify messages returned
    assert len(messages) == 1

    # Verify a JSON file is written
    files = list(tmp_path.glob("test_save_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["id"] == "m1"