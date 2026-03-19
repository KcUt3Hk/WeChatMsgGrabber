import json
from datetime import datetime

from controllers.main_controller import MainController
from models.config import AppConfig
from models.data_models import Message, MessageType


def test_run_and_save_with_preprovided_messages(tmp_path, monkeypatch):
    mc = MainController()

    # Prepare a message batch to pass directly
    msg1 = Message(
        id="x1",
        sender="Tester",
        content="Hello",
        message_type=MessageType.TEXT,
        timestamp=datetime.now(),
        confidence_score=0.95,
        raw_ocr_text="Hello",
    )
    msg2 = Message(
        id="x2",
        sender="Tester",
        content="World",
        message_type=MessageType.TEXT,
        timestamp=datetime.now(),
        confidence_score=0.95,
        raw_ocr_text="World",
    )

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

    messages = mc.run_and_save(
        filename_prefix="preprovided",
        use_retry=False,  # should be ignored when messages provided
        reporter=None,
        messages=[msg1, msg2],
    )

    # Verify messages returned
    assert len(messages) == 2

    # Verify a JSON file is written
    files = list(tmp_path.glob("preprovided_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 2
    ids = {d["id"] for d in data}
    assert ids == {"x1", "x2"}