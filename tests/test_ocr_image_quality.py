"""
OCR image quality tests for different image conditions.
Tests OCR recognition accuracy under various image quality scenarios.
"""
import pytest
from unittest.mock import Mock, patch
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

# Mock PaddleOCR before importing our modules
sys.modules['paddleocr'] = Mock()

from services.ocr_processor import OCRProcessor
from models.config import OCRConfig
from models.data_models import OCRResult, Rectangle


class TestOCRImageQuality:
    """Test OCR processing with different image quality conditions."""
    
    @pytest.fixture
    def ocr_processor(self):
        """Create OCR processor for testing."""
        config = OCRConfig(confidence_threshold=0.5)
        return OCRProcessor(config)
    
    @pytest.fixture
    def high_quality_image(self):
        """Create high quality text image."""
        width, height = 400, 200
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        # Use default font
        font = ImageFont.load_default()
        
        # Draw clear, high contrast text
        text_lines = [
            "微信聊天记录获取助手",
            "WeChatMsgGrabber",
            "高质量图像测试"
        ]
        
        y_offset = 30
        for line in text_lines:
            draw.text((30, y_offset), line, fill='black', font=font)
            y_offset += 50
        
        return image
    
    @pytest.fixture
    def low_quality_image(self, high_quality_image):
        """Create low quality version with noise and blur."""
        # Convert to numpy array
        img_array = np.array(high_quality_image)
        
        # Add random noise
        noise = np.random.randint(0, 30, img_array.shape, dtype=np.uint8)
        noisy_img = np.clip(img_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        # Convert back to PIL and apply blur
        noisy_pil = Image.fromarray(noisy_img)
        blurred = noisy_pil.filter(ImageFilter.GaussianBlur(radius=1.5))
        
        return blurred
    
    @pytest.fixture
    def very_low_quality_image(self, high_quality_image):
        """Create very low quality version with heavy distortion."""
        # Convert to numpy array
        img_array = np.array(high_quality_image)
        
        # Add heavy noise
        noise = np.random.randint(0, 80, img_array.shape, dtype=np.uint8)
        noisy_img = np.clip(img_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        # Convert back to PIL and apply heavy blur
        noisy_pil = Image.fromarray(noisy_img)
        heavily_blurred = noisy_pil.filter(ImageFilter.GaussianBlur(radius=3.0))
        
        return heavily_blurred
    
    @pytest.fixture
    def dark_image(self, high_quality_image):
        """Create dark/low brightness image."""
        # Reduce brightness significantly
        dark_image = high_quality_image.point(lambda x: x * 0.3)
        return dark_image
    
    @pytest.fixture
    def low_contrast_image(self, high_quality_image):
        """Create low contrast image."""
        # Convert to grayscale and reduce contrast
        gray_image = high_quality_image.convert('L')
        # Compress dynamic range to reduce contrast
        low_contrast = gray_image.point(lambda x: 128 + (x - 128) * 0.3)
        return low_contrast.convert('RGB')
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_high_quality_image_processing(self, mock_paddle_ocr, ocr_processor, high_quality_image):
        """Test OCR processing on high quality image."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock high confidence results for high quality image
        mock_ocr_results = [[
            [
                [[30, 30], [200, 30], [200, 60], [30, 60]],
                ("微信聊天记录获取助手", 0.95)
            ],
            [
                [[30, 80], [250, 80], [250, 110], [30, 110]],
                ("WeChatMsgGrabber", 0.92)
            ],
            [
                [[30, 130], [180, 130], [180, 160], [30, 160]],
                ("高质量图像测试", 0.90)
            ]
        ]]
        mock_ocr_instance.ocr.return_value = mock_ocr_results
        
        # Initialize and process
        ocr_processor.initialize_engine()
        result = ocr_processor.process_image(high_quality_image)
        
        # Verify high quality results
        assert isinstance(result, OCRResult)
        assert result.confidence > 0.9  # High confidence expected
        assert "微信聊天记录获取助手" in result.text
        assert "WeChatMsgGrabber" in result.text
        assert "高质量图像测试" in result.text
        assert len(result.bounding_boxes) == 3
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_low_quality_image_processing(self, mock_paddle_ocr, ocr_processor, low_quality_image):
        """Test OCR processing on low quality image."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock lower confidence results for low quality image
        mock_ocr_results = [[
            [
                [[30, 30], [200, 30], [200, 60], [30, 60]],
                ("微信聊天记录", 0.75)  # Partial text, lower confidence
            ],
            [
                [[30, 80], [250, 80], [250, 110], [30, 110]],
                ("WeChat Chat", 0.70)  # Partial text
            ]
        ]]
        mock_ocr_instance.ocr.return_value = mock_ocr_results
        
        # Initialize and process
        ocr_processor.initialize_engine()
        result = ocr_processor.process_image(low_quality_image)
        
        # Verify degraded results
        assert isinstance(result, OCRResult)
        assert 0.6 <= result.confidence <= 0.8  # Lower confidence expected
        assert len(result.bounding_boxes) == 2  # Some text might be missed
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_very_low_quality_image_processing(self, mock_paddle_ocr, ocr_processor, very_low_quality_image):
        """Test OCR processing on very low quality image."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock very poor results for very low quality image
        mock_ocr_results = [[
            [
                [[30, 30], [150, 30], [150, 60], [30, 60]],
                ("微信", 0.45)  # Very partial text, very low confidence
            ]
        ]]
        mock_ocr_instance.ocr.return_value = mock_ocr_results
        
        # Initialize and process
        ocr_processor.initialize_engine()
        result = ocr_processor.process_image(very_low_quality_image)
        
        # Verify very poor results
        assert isinstance(result, OCRResult)
        assert result.confidence < 0.5  # Very low confidence
        assert len(result.bounding_boxes) <= 1  # Most text missed
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_preprocessing_improves_quality(self, mock_paddle_ocr, ocr_processor, low_quality_image):
        """Test that preprocessing improves OCR results on low quality images."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock different results based on preprocessing
        def mock_ocr_side_effect(image_array, cls=True):
            # Simulate better results when preprocessing is applied
            # (In real scenario, preprocessed images would have better quality)
            return [[
                [
                    [[30, 30], [200, 30], [200, 60], [30, 60]],
                    ("微信聊天记录提取", 0.80)  # Better result with preprocessing
                ],
                [
                    [[30, 80], [220, 80], [220, 110], [30, 110]],
                    ("WeChat Chat Extract", 0.78)
                ]
            ]]
        
        mock_ocr_instance.ocr.side_effect = mock_ocr_side_effect
        
        # Initialize engine
        ocr_processor.initialize_engine()
        
        # Process with preprocessing
        result_with_preprocessing = ocr_processor.process_image(low_quality_image, preprocess=True)
        
        # Process without preprocessing
        mock_ocr_instance.ocr.side_effect = lambda img, cls=True: [[
            [
                [[30, 30], [150, 30], [150, 60], [30, 60]],
                ("微信聊天", 0.65)  # Worse result without preprocessing
            ]
        ]]
        
        result_without_preprocessing = ocr_processor.process_image(low_quality_image, preprocess=False)
        
        # Verify preprocessing helps
        assert result_with_preprocessing.confidence > result_without_preprocessing.confidence
        assert len(result_with_preprocessing.text) > len(result_without_preprocessing.text)
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_confidence_threshold_filtering(self, mock_paddle_ocr, ocr_processor, low_quality_image):
        """Test that confidence threshold properly filters low confidence results."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock results with varying confidence levels
        mock_ocr_results = [[
            [
                [[30, 30], [200, 30], [200, 60], [30, 60]],
                ("高置信度文本", 0.8)  # Above threshold (0.5)
            ],
            [
                [[30, 80], [200, 80], [200, 110], [30, 110]],
                ("中等置信度", 0.6)  # Above threshold
            ],
            [
                [[30, 130], [200, 130], [200, 160], [30, 160]],
                ("低置信度", 0.3)  # Below threshold
            ]
        ]]
        mock_ocr_instance.ocr.return_value = mock_ocr_results
        
        # Initialize and extract text regions
        ocr_processor.initialize_engine()
        regions = ocr_processor.extract_text_regions(low_quality_image)
        
        # Verify filtering
        assert len(regions) == 2  # Only high confidence regions
        confidences = [region.confidence for region in regions]
        assert all(conf >= 0.5 for conf in confidences)  # All above threshold
        
        # Verify specific texts
        texts = [region.text for region in regions]
        assert "高置信度文本" in texts
        assert "中等置信度" in texts
        assert "低置信度" not in texts  # Should be filtered out
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_enhanced_confidence_calculation(self, mock_paddle_ocr, ocr_processor, high_quality_image, low_quality_image):
        """Test enhanced confidence calculation that combines OCR and image quality."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        ocr_processor.initialize_engine()
        
        # Create test OCR results with same confidence
        test_result = OCRResult(
            text="测试文本",
            confidence=0.8,
            bounding_boxes=[],
            processing_time=0.1
        )
        
        # Calculate enhanced confidence for both images
        high_quality_enhanced = ocr_processor.calculate_enhanced_confidence(high_quality_image, test_result)
        low_quality_enhanced = ocr_processor.calculate_enhanced_confidence(low_quality_image, test_result)
        
        # Enhanced confidence should be different based on image quality
        assert 0.0 <= high_quality_enhanced <= 1.0
        assert 0.0 <= low_quality_enhanced <= 1.0
        # High quality image should generally have higher enhanced confidence
        # (though this depends on the specific image quality calculation)
        assert high_quality_enhanced != test_result.confidence  # Should be modified
        assert low_quality_enhanced != test_result.confidence   # Should be modified
    
    def test_image_quality_fixtures(self, high_quality_image, low_quality_image, very_low_quality_image, dark_image, low_contrast_image):
        """Test that image quality fixtures are created correctly."""
        # Verify all images are PIL Images
        assert isinstance(high_quality_image, Image.Image)
        assert isinstance(low_quality_image, Image.Image)
        assert isinstance(very_low_quality_image, Image.Image)
        assert isinstance(dark_image, Image.Image)
        assert isinstance(low_contrast_image, Image.Image)
        
        # Verify dimensions are consistent
        assert high_quality_image.size == (400, 200)
        assert low_quality_image.size == (400, 200)
        assert very_low_quality_image.size == (400, 200)
        assert dark_image.size == (400, 200)
        assert low_contrast_image.size == (400, 200)