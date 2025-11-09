from datetime import datetime

from models.data_models import Message, MessageType
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