from PIL import Image
import numpy as np
from services.auto_scroll_controller import AutoScrollController


class TestSSIMSimilarity:
    def test_ssim_compare_similar(self):
        ctrl = AutoScrollController()
        arr = np.random.randint(0, 255, (400, 300, 3), dtype=np.uint8)
        img1 = Image.fromarray(arr)
        # add small gaussian noise
        noise = (np.random.randn(400, 300, 3) * 3).astype(np.int16)
        arr2 = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        img2 = Image.fromarray(arr2)
        assert ctrl._compare_screenshots(img1, img2, threshold=0.9)

    def test_ssim_compare_different(self):
        ctrl = AutoScrollController()
        arr1 = np.zeros((400, 300, 3), dtype=np.uint8)
        arr2 = np.ones((400, 300, 3), dtype=np.uint8) * 255
        img1 = Image.fromarray(arr1)
        img2 = Image.fromarray(arr2)
        assert not ctrl._compare_screenshots(img1, img2, threshold=0.95)

