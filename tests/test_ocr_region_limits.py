from PIL import Image

from models.data_models import Rectangle, OCRResult, TextRegion
from services.ocr_processor import OCRProcessor


def test_detect_and_process_regions_limits_top_n(monkeypatch):
    ocr = OCRProcessor()
    # bypass engine check
    ocr.ocr_engine = object()

    # generate 100 rectangles of varying sizes
    rects = [Rectangle(x=0, y=i, width=i + 10, height=i + 5) for i in range(100)]

    # stub preprocessor methods
    def fake_detect_text_regions(image):
        return rects

    def fake_crop_text_region(image, region):
        return Image.new("RGB", (10, 10))

    # stub process_image to always return text
    def fake_process_image(img, preprocess=True):
        return OCRResult(text="x", confidence=0.9, bounding_boxes=[], processing_time=0.01)

    monkeypatch.setattr(ocr.preprocessor, "detect_text_regions", fake_detect_text_regions)
    monkeypatch.setattr(ocr.preprocessor, "crop_text_region", fake_crop_text_region)
    monkeypatch.setattr(ocr, "process_image", fake_process_image)

    img = Image.new("RGB", (100, 100))
    results = ocr.detect_and_process_regions(img, max_regions=25)
    assert len(results) == 25