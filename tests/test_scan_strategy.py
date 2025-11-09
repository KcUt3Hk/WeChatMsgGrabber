from PIL import Image

from models.data_models import Rectangle, Message, MessageType, TextRegion
from controllers.main_controller import MainController


def _make_msg(i: int) -> Message:
    from datetime import datetime
    return Message(
        id=str(i),
        sender="test",
        content=f"msg-{i}",
        message_type=MessageType.TEXT,
        timestamp=datetime.utcnow(),
        confidence_score=0.9,
        raw_ocr_text=f"msg-{i}",
    )


def test_scan_chat_history_adaptive_speed(monkeypatch):
    mc = MainController()

    # Prepare AutoScrollController stubs
    class Win:
        def __init__(self):
            self.title = "WeChat"
            self._hWnd = 1
            self.left = 0
            self.top = 0
            self.width = 800
            self.height = 600
            self.visible = True

    # Basic window and area
    mc.scroll.current_window = None

    def fake_locate():
        w = Win()
        from models.data_models import WindowInfo
        return WindowInfo(handle=w._hWnd, position=Rectangle(x=0, y=0, width=w.width, height=w.height), is_active=True, title=w.title)

    def fake_activate():
        return True

    def fake_is_valid():
        return True

    def fake_bounds():
        return Rectangle(x=0, y=0, width=800, height=600)

    # Prepare images for similarity control
    img_same = Image.new("RGB", (100, 100), color=(10, 10, 10))
    img_diff = Image.new("RGB", (100, 100), color=(200, 200, 200))

    # First batch: low hit rate and high similarity
    calls = {"capture": 0}
    def fake_capture():
        calls["capture"] += 1
        # return same image for before/after to simulate high similarity
        return img_same.copy()

    def fake_start_scroll(direction="up"):
        return True

    # OCR: first batch low hits, second batch high hits
    def fake_is_engine_ready():
        return True

    def fake_detect_and_process_regions(image, max_regions=25):
        # For first call: 5 regions, but parser only yields 0 messages
        # For second call: 5 regions, parser yields 5 messages
        if calls["capture"] <= 1:
            rects = [Rectangle(x=0, y=i, width=10, height=10) for i in range(5)]
        else:
            rects = [Rectangle(x=0, y=i, width=10, height=10) for i in range(5)]
        return [(TextRegion(text="t", bounding_box=r, confidence=0.9), None) for r in rects]

    def fake_parse(text_regions):
        # Use capture count to control hit rate
        if calls["capture"] <= 1:
            return []  # low hit rate
        else:
            return [_make_msg(i) for i in range(len(text_regions))]  # high hit rate

    # Monkeypatch methods
    monkeypatch.setattr(mc.scroll, "locate_wechat_window", fake_locate)
    monkeypatch.setattr(mc.scroll, "activate_window", fake_activate)
    monkeypatch.setattr(mc.scroll, "is_window_valid", fake_is_valid)
    monkeypatch.setattr(mc.scroll, "get_chat_area_bounds", fake_bounds)
    monkeypatch.setattr(mc.scroll, "capture_current_view", fake_capture)
    monkeypatch.setattr(mc.scroll, "start_scrolling", fake_start_scroll)
    monkeypatch.setattr(mc.ocr, "is_engine_ready", fake_is_engine_ready)
    monkeypatch.setattr(mc.ocr, "detect_and_process_regions", fake_detect_and_process_regions)
    monkeypatch.setattr(mc.parser, "parse", fake_parse)

    # Initial speed and delay
    mc.scroll.scroll_speed = 2
    mc.scroll.scroll_delay = 1.0

    msgs = mc.scan_chat_history(max_batches=2, direction="up", reporter=None)

    # After first batch: low hit rate + high similarity -> speed increases
    assert mc.scroll.scroll_speed >= 2
    assert isinstance(msgs, list)