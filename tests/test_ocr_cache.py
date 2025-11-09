from PIL import Image

from models.data_models import Rectangle, OCRResult
from services.ocr_processor import OCRProcessor


def test_detect_and_process_regions_uses_cache(monkeypatch):
    ocr = OCRProcessor()
    # bypass engine check
    ocr.ocr_engine = object()

    # create two rectangles that crop to identical images
    rects = [Rectangle(x=0, y=0, width=10, height=10), Rectangle(x=10, y=10, width=10, height=10)]

    base_img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    identical_crop = Image.new("RGB", (10, 10), color=(0, 0, 0))

    # stub preprocessor
    def fake_detect_text_regions(image):
        return rects

    def fake_crop_text_region(image, region):
        # always return the same cropped image object with identical pixels
        return identical_crop.copy()

    calls = {"count": 0}

    def fake_process_image(img, preprocess=True):
        calls["count"] += 1
        return OCRResult(text="cached", confidence=0.9, bounding_boxes=[], processing_time=0.01)

    monkeypatch.setattr(ocr.preprocessor, "detect_text_regions", fake_detect_text_regions)
    monkeypatch.setattr(ocr.preprocessor, "crop_text_region", fake_crop_text_region)
    monkeypatch.setattr(ocr, "process_image", fake_process_image)

    results = ocr.detect_and_process_regions(base_img, max_regions=10)
    # process_image should be called only once due to cache hit on second region
    assert calls["count"] == 1
    assert len(results) == 2
    assert len(ocr._ocr_cache) == 1


def test_ocr_cache_respects_max_items(monkeypatch):
    ocr = OCRProcessor()
    ocr.ocr_engine = object()
    # shrink cache to small size
    ocr._cache_max_items = 2

    base_img = Image.new("RGB", (100, 100), color=(255, 255, 255))

    rects = [
        Rectangle(x=0, y=0, width=10, height=10),
        Rectangle(x=20, y=0, width=10, height=10),
        Rectangle(x=40, y=0, width=10, height=10),
    ]

    # return different crops by color to ensure unique hashes
    colors = [(10, 10, 10), (20, 20, 20), (30, 30, 30)]

    def fake_detect_text_regions(image):
        return rects

    def fake_crop_text_region(image, region):
        idx = rects.index(region)
        return Image.new("RGB", (10, 10), color=colors[idx])

    def fake_process_image(img, preprocess=True):
        return OCRResult(text="x", confidence=0.9, bounding_boxes=[], processing_time=0.01)

    monkeypatch.setattr(ocr.preprocessor, "detect_text_regions", fake_detect_text_regions)
    monkeypatch.setattr(ocr.preprocessor, "crop_text_region", fake_crop_text_region)
    monkeypatch.setattr(ocr, "process_image", fake_process_image)

    results = ocr.detect_and_process_regions(base_img, max_regions=10)
    assert len(results) == 3
    # cache should be capped at 2 items
    assert len(ocr._ocr_cache) == 2