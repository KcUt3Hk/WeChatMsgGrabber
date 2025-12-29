import unittest
import os
import shutil
from PIL import Image, ImageDraw
import numpy as np
from services.image_deduplicator import ImageDeduplicator

class TestImageDeduplicationAndOCR(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_dedup_images"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        self.deduplicator = ImageDeduplicator()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def create_test_image(self, color, size=(100, 100), pattern=None):
        img = Image.new('RGB', size, color=color)
        if pattern:
            draw = ImageDraw.Draw(img)
            # Draw a simple pattern based on the 'pattern' string
            if pattern == "circle":
                draw.ellipse((20, 20, 80, 80), fill="white")
            elif pattern == "rect":
                draw.rectangle((20, 20, 80, 80), fill="white")
            elif pattern == "line":
                draw.line((0, 0, 100, 100), fill="white", width=5)
        return img

    def test_deduplication_exact_match(self):
        # Create an image
        img1 = self.create_test_image("red", pattern="circle")
        img1_path = os.path.join(self.test_dir, "img1.png")
        img1.save(img1_path)

        # Add to deduplicator
        self.deduplicator.add_image(img1, img1_path)

        # Create identical image
        img2 = self.create_test_image("red", pattern="circle")
        
        # Should be duplicate
        self.assertTrue(self.deduplicator.is_duplicate(img2), "Identical images should be detected as duplicate")

    def test_deduplication_similar_match(self):
        # Create an image
        img1 = self.create_test_image("blue", pattern="rect")
        img1_path = os.path.join(self.test_dir, "img1.png")
        img1.save(img1_path)
        
        self.deduplicator.add_image(img1, img1_path)

        # Create slightly modified image (e.g., small pixel change or jpeg compression artifact simulation)
        # Here we just change a pixel
        img2 = self.create_test_image("blue", pattern="rect")
        pixels = img2.load()
        pixels[50, 50] = (0, 0, 0) # Change one pixel
        
        # Should still be duplicate (dHash is robust)
        self.assertTrue(self.deduplicator.is_duplicate(img2), "Slightly modified image should be detected as duplicate")

    def test_deduplication_different(self):
        # Create image 1
        img1 = self.create_test_image("green", pattern="line")
        img1_path = os.path.join(self.test_dir, "img1.png")
        img1.save(img1_path)
        
        self.deduplicator.add_image(img1, img1_path)

        # Create image 2 (different pattern)
        img2 = self.create_test_image("green", pattern="circle")
        
        # Should NOT be duplicate
        self.assertFalse(self.deduplicator.is_duplicate(img2), "Different images should not be detected as duplicate")

    def test_ocr_reclassification_logic(self):
        """
        Simulate the logic in detect_and_process_regions 
        where we decide whether to reclassify text as image.
        We can't easily run the full OCR pipeline without the engine, 
        so we'll simulate the condition check logic.
        """
        # Simulation of the logic I added to ocr_processor.py
        def should_reclassify(text, confidence):
            clean_txt = text.strip()
            reclassify = False
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in clean_txt)
            
            # Logic from ocr_processor.py
            if confidence < 0.6:
                # Long text protection (>= 5 chars)
                if len(clean_txt) >= 5:
                    if has_chinese:
                        if confidence < 0.2:
                            reclassify = True
                    else:
                        if confidence < 0.4:
                            reclassify = True
                # Short text
                else:
                    if has_chinese:
                        # "搞好了" (conf~0.5) -> Should NOT reclassify (threshold 0.3)
                        if confidence < 0.3:
                            reclassify = True
                    else:
                        reclassify = True
            
            # Garbage check
            else:
                if len(clean_txt) <= 2 and not clean_txt.isdigit() and not has_chinese:
                    reclassify = True
                elif len(clean_txt) < 5 and not has_chinese and not clean_txt.isalnum():
                    reclassify = True
                
            return reclassify

        # Test Case 1: "搞好了" (Chinese, short, confidence 0.5) -> Should NOT reclassify
        self.assertFalse(should_reclassify("搞好了", 0.5), "Short Chinese text with medium confidence should NOT be reclassified")
        
        # Test Case 2: "搞好了" (Chinese, short, confidence 0.2) -> Should reclassify (too low)
        self.assertTrue(should_reclassify("搞好了", 0.2), "Short Chinese text with very low confidence SHOULD be reclassified")

        # Test Case 3: Random garbage "x^" (confidence 0.8) -> Should reclassify
        self.assertTrue(should_reclassify("x^", 0.8), "Short garbage text should be reclassified even with high confidence")

        # Test Case 4: Long Chinese text (confidence 0.3) -> Should NOT reclassify (protected)
        self.assertFalse(should_reclassify("这是一段测试文本", 0.3), "Long Chinese text should be protected")

        # Test Case 5: Valid English word "Hello" (confidence 0.5) -> Should reclassify (English short < 0.6)
        # Wait, "Hello" len=5. So it hits >= 5 branch.
        # len("Hello") == 5. 
        # has_chinese = False.
        # confidence < 0.4? No (0.5).
        # So False.
        self.assertFalse(should_reclassify("Hello", 0.5), "Medium confidence English word should be kept")
        
        # Test Case 6: Short English "Hi" (confidence 0.5) -> Should reclassify (short < 0.6 -> reclassify=True)
        self.assertTrue(should_reclassify("Hi", 0.5), "Short English text with medium confidence should be reclassified")

    def test_solid_background_detection(self):
        from services.image_preprocessor import ImagePreprocessor
        preprocessor = ImagePreprocessor()
        
        # 1. Solid green image (Simulate Green Bubble)
        green_img = self.create_test_image((149, 236, 105)) # WeChat Green
        self.assertTrue(preprocessor.is_solid_background(green_img), "Solid green image should be detected as solid background")
        
        # 2. Green image with some text (black lines)
        green_text_img = self.create_test_image((149, 236, 105))
        draw = ImageDraw.Draw(green_text_img)
        # Simple line drawing to simulate text structure
        draw.line((10, 10, 90, 10), fill="black", width=2)
        draw.line((10, 30, 70, 30), fill="black", width=2)
        self.assertTrue(preprocessor.is_solid_background(green_text_img), "Green image with text-like lines should still be detected as solid background")
        
        # 3. Complex image (Random Noise)
        # Generate random noise image
        arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        noise_img = Image.fromarray(arr)
        self.assertFalse(preprocessor.is_solid_background(noise_img), "Random noise image should NOT be detected as solid background")

if __name__ == '__main__':
    unittest.main()
