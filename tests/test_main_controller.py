from datetime import datetime

import numpy as np
from PIL import Image

from models.data_models import Message, MessageType
from models.data_models import Rectangle
from controllers.main_controller import MainController


def test_run_with_retry_success_after_failures(monkeypatch):
    mc = MainController()

    calls = {"count": 0}

    def fake_run_once():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("temporary failure")
        return [
            Message(
                id="ok1",
                sender="Tester",
                content="成功消息",
                message_type=MessageType.TEXT,
                timestamp=datetime.now(),
                confidence_score=0.99,
                raw_ocr_text="成功消息",
            )
        ]

    monkeypatch.setattr(mc, "run_once", fake_run_once)

    messages = mc.run_with_retry(max_attempts=3, delay_seconds=0.0)
    assert len(messages) == 1
    assert messages[0].id == "ok1"


def test_run_with_retry_all_empty(monkeypatch):
    mc = MainController()

    def fake_run_once_empty():
        return []

    monkeypatch.setattr(mc, "run_once", fake_run_once_empty)
    messages = mc.run_with_retry(max_attempts=2, delay_seconds=0.0)
    assert messages == []


def test_run_once_window_not_found(monkeypatch):
    mc = MainController()

    # Mock scroll to return no window
    class DummyScroll:
        def locate_wechat_window(self):
            return None

        def activate_window(self):
            return False

        def has_chat_area_override(self):
            return False

        def capture_current_view(self):
            return None

        def optimize_screenshot_quality(self, img):
            return img

    mc.scroll = DummyScroll()

    messages = mc.run_once()
    assert messages == []


def test_advanced_scan_saves_images_to_output_dir(tmp_path, monkeypatch):
    mc = MainController()

    class DummyScroll:
        def has_chat_area_override(self):
            return True

        def get_chat_area_bounds(self):
            return Rectangle(x=0, y=0, width=200, height=200)

    mc.scroll = DummyScroll()

    class DummyOCR:
        def is_engine_ready(self):
            return True

    mc.ocr = DummyOCR()

    class DummyAdvancedScroll:
        def __init__(
            self,
            scroll_speed,
            scroll_delay,
            scroll_distance_range,
            scroll_interval_range,
            inertial_effect,
            on_state_captured,
        ):
            self.on_state_captured = on_state_captured

        def set_override_chat_area(self, rect):
            return None

        def locate_wechat_window(self):
            return None

        def activate_window(self):
            return True

        def progressive_scroll(self, direction, max_scrolls, target_content, stop_at_edges):
            ts = datetime(2024, 10, 1, 9, 0, 0)
            msg = Message(
                id="img1",
                sender="Tester",
                content="",
                message_type=MessageType.IMAGE,
                timestamp=ts,
                confidence_score=0.9,
                raw_ocr_text="",
                original_region=Rectangle(x=50, y=50, width=80, height=80),
            )

            arr = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
            screenshot = Image.fromarray(arr, mode="RGB")

            state = {"messages": [msg], "screenshot": screenshot}
            self.on_state_captured(state)
            return None

        def get_scroll_statistics(self):
            return {}

    import controllers.main_controller as mc_mod

    monkeypatch.setattr(mc_mod, "AdvancedScrollController", DummyAdvancedScroll)

    messages = mc.advanced_scan_chat_history(
        max_scrolls=1,
        direction="up",
        stop_at_edges=True,
        reporter=None,
        output_dir=str(tmp_path),
    )

    assert len(messages) == 1
    expected = tmp_path / "images" / "img1_20241001090000.png"
    assert expected.exists()
    assert messages[0].content == str(expected)


def test_save_image_messages_rejects_text_bubble(tmp_path):
    mc = MainController()
    mc._images_output_dir = str(tmp_path)

    ts = datetime(2024, 10, 1, 9, 0, 0)
    msg = Message(
        id="bubble1",
        sender="Tester",
        content="",
        message_type=MessageType.IMAGE,
        timestamp=ts,
        confidence_score=0.9,
        raw_ocr_text="",
        original_region=Rectangle(x=20, y=30, width=260, height=120),
    )

    screenshot = Image.new("RGB", (300, 200), color=(245, 245, 245))
    import PIL.ImageDraw as ImageDraw

    d = ImageDraw.Draw(screenshot)
    d.rectangle((20, 30, 280, 150), fill=(255, 255, 255))
    for i in range(4):
        d.text((35, 45 + 22 * i), f"line {i}", fill=(0, 0, 0))

    mc._save_image_messages([msg], screenshot)
    assert msg.message_type == MessageType.UNKNOWN
    images_dir = tmp_path / "images"
    assert not any(images_dir.glob("*.png"))
