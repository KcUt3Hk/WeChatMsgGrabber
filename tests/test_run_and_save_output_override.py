import os
from datetime import datetime

from controllers.main_controller import MainController
from models.config import OutputConfig
from models.data_models import Message, MessageType


def _sample_messages():
    return [
        Message(
            id="m1",
            sender="Alice",
            content="Hello",
            message_type=MessageType.TEXT,
            timestamp=datetime(2024, 10, 1, 9, 0, 0),
            confidence_score=0.95,
            raw_ocr_text="Hello",
        ),
        Message(
            id="m2",
            sender="Bob",
            content="World",
            message_type=MessageType.TEXT,
            timestamp=datetime(2024, 10, 1, 9, 1, 0),
            confidence_score=0.93,
            raw_ocr_text="World",
        ),
    ]


def test_run_and_save_respects_output_override_format_and_directory(tmp_path):
    controller = MainController()
    messages = _sample_messages()

    out_dir = tmp_path / "override_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    override = OutputConfig(
        format="txt",
        directory=str(out_dir),
        enable_deduplication=True,
    )

    controller.run_and_save(
        filename_prefix="override_test",
        use_retry=False,
        reporter=None,
        messages=messages,
        output_override=override,
    )

    # Verify a .txt file exists in the override directory
    files = os.listdir(out_dir)
    assert any(f.startswith("override_test") and f.endswith(".txt") for f in files), f"No .txt output found in {out_dir}: {files}"