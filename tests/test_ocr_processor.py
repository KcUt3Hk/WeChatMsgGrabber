"""
Unit tests for OCR processor module.
Tests OCR recognition accuracy and different image quality processing.
"""
import pytest
import tempfile
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from unittest.mock import Mock, patch
import sys

# Mock PaddleOCR before importing our modules
sys.modules['paddleocr'] = Mock()

from services.ocr_processor import OCRProcessor
from services.image_preprocessor import ImagePreprocessor
from models.config import OCRConfig
from models.data_models import OCRResult, TextRegion, Rectangle


class TestOCRProcessor:
    """Test cases for OCRProcessor class."""
    
    @pytest.fixture
    def ocr_config(self):
        """Create test OCR configuration."""
        return OCRConfig(
            language="chi_sim",
            confidence_threshold=0.5,
            use_gpu=False
        )
    
    @pytest.fixture
    def ocr_processor(self, ocr_config):
        """Create OCR processor instance for testing."""
        return OCRProcessor(ocr_config)
    
    @pytest.fixture
    def sample_text_image(self):
        """Create a sample image with Chinese and English text."""
        # Create a white background image
        width, height = 400, 200
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        # Add text (using default font since we can't guarantee font availability)
        try:
            # Try to use a larger font if available
            font = ImageFont.load_default()
        except:
            font = None
        
        # Draw Chinese and English text
        text_lines = [
            "微信聊天记录获取助手",
            "WeChatMsgGraber",
            "测试文本 Test Text"
        ]
        
        y_offset = 20
        for line in text_lines:
            draw.text((20, y_offset), line, fill='black', font=font)
            y_offset += 40
        
        return image
    
    @pytest.fixture
    def low_quality_image(self, sample_text_image):
        """Create a low quality version of the sample image."""
        # Add noise and blur to simulate low quality
        img_array = np.array(sample_text_image)
        
        # Add random noise
        noise = np.random.randint(0, 50, img_array.shape, dtype=np.uint8)
        noisy_img = np.clip(img_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        # Convert back to PIL and apply blur
        noisy_pil = Image.fromarray(noisy_img)
        blurred = noisy_pil.filter(ImageFilter.BLUR)
        
        return blurred
    
    @pytest.fixture
    def empty_image(self):
        """Create an empty white image."""
        return Image.new('RGB', (200, 100), color='white')
    
    def test_initialization_default_config(self):
        """Test OCR processor initialization with default configuration."""
        processor = OCRProcessor()
        
        assert processor.config is not None
        # Default OCR language now aligns with PaddleOCR's Chinese/English code 'ch'
        assert processor.config.language == "ch"
        assert processor.config.confidence_threshold == 0.7
        assert processor.config.use_gpu is False
        assert processor.ocr_engine is None
        assert not processor.is_engine_ready()
    
    def test_initialization_custom_config(self, ocr_config):
        """Test OCR processor initialization with custom configuration."""
        processor = OCRProcessor(ocr_config)
        
        assert processor.config == ocr_config
        assert processor.config.confidence_threshold == 0.5
        assert not processor.is_engine_ready()
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_initialize_engine_success(self, mock_paddle_ocr, ocr_processor):
        """Test successful OCR engine initialization."""
        # Mock PaddleOCR initialization
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        result = ocr_processor.initialize_engine()
        
        assert result is True
        assert ocr_processor.is_engine_ready()
        mock_paddle_ocr.assert_called_once_with(
            use_angle_cls=True,
            lang="ch",
            use_gpu=False,
            show_log=False
        )
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_initialize_engine_failure(self, mock_paddle_ocr, ocr_processor):
        """Test OCR engine initialization failure."""
        # Mock PaddleOCR to raise exception
        mock_paddle_ocr.side_effect = Exception("PaddleOCR initialization failed")
        
        result = ocr_processor.initialize_engine()
        
        assert result is False
        assert not ocr_processor.is_engine_ready()
    
    def test_process_image_without_engine(self, ocr_processor, sample_text_image):
        """Test processing image without initialized engine."""
        with pytest.raises(RuntimeError, match="OCR engine not initialized"):
            ocr_processor.process_image(sample_text_image)
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_process_image_success(self, mock_paddle_ocr, ocr_processor, sample_text_image):
        """Test successful image processing with OCR."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock OCR results
        mock_ocr_results = [[
            [
                [[10, 10], [100, 10], [100, 30], [10, 30]],
                ("微信聊天记录", 0.95)
            ],
            [
                [[10, 50], [150, 50], [150, 70], [10, 70]],
                ("WeChat Chat", 0.90)
            ]
        ]]
        mock_ocr_instance.ocr.return_value = mock_ocr_results
        
        # Initialize engine and process image
        ocr_processor.initialize_engine()
        result = ocr_processor.process_image(sample_text_image)
        
        # Verify results
        assert isinstance(result, OCRResult)
        assert "微信聊天记录" in result.text
        assert "WeChat Chat" in result.text
        assert result.confidence > 0.0
        assert len(result.bounding_boxes) == 2
        assert result.processing_time > 0.0
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_process_image_no_text_found(self, mock_paddle_ocr, ocr_processor, empty_image):
        """Test processing image with no text detected."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock empty OCR results
        mock_ocr_instance.ocr.return_value = [[]]
        
        # Initialize engine and process image
        ocr_processor.initialize_engine()
        result = ocr_processor.process_image(empty_image)
        
        # Verify results
        assert isinstance(result, OCRResult)
        assert result.text == ""
        assert result.confidence == 0.0
        assert len(result.bounding_boxes) == 0
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_process_image_with_preprocessing(self, mock_paddle_ocr, ocr_processor, low_quality_image):
        """Test image processing with preprocessing enabled."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock OCR results
        mock_ocr_results = [[
            [
                [[10, 10], [100, 10], [100, 30], [10, 30]],
                ("测试文本", 0.85)
            ]
        ]]
        mock_ocr_instance.ocr.return_value = mock_ocr_results
        
        # Initialize engine and process with preprocessing
        ocr_processor.initialize_engine()
        result = ocr_processor.process_image(low_quality_image, preprocess=True)
        
        # Verify preprocessing was applied (image should be processed)
        assert isinstance(result, OCRResult)
        assert "测试文本" in result.text
        assert result.confidence > 0.0
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_extract_text_regions_with_confidence_filter(self, mock_paddle_ocr, ocr_processor, sample_text_image):
        """Test text region extraction with confidence threshold filtering."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock OCR results with varying confidence levels
        mock_ocr_results = [[
            [
                [[10, 10], [100, 10], [100, 30], [10, 30]],
                ("高置信度文本", 0.95)  # Above threshold
            ],
            [
                [[10, 50], [100, 50], [100, 70], [10, 70]],
                ("低置信度文本", 0.3)   # Below threshold
            ]
        ]]
        mock_ocr_instance.ocr.return_value = mock_ocr_results
        
        # Initialize engine and extract regions
        ocr_processor.initialize_engine()
        regions = ocr_processor.extract_text_regions(sample_text_image)
        
        # Verify only high confidence regions are returned
        assert len(regions) == 1
        assert regions[0].text == "高置信度文本"
        assert regions[0].confidence == 0.95
        assert isinstance(regions[0].bounding_box, Rectangle)
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_get_confidence_score(self, mock_paddle_ocr, ocr_processor):
        """Test confidence score retrieval."""
        # Create test OCR result
        test_result = OCRResult(
            text="测试文本",
            confidence=0.85,
            bounding_boxes=[],
            processing_time=0.1
        )
        
        confidence = ocr_processor.get_confidence_score(test_result)
        assert confidence == 0.85
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_calculate_enhanced_confidence(self, mock_paddle_ocr, ocr_processor, sample_text_image):
        """Test enhanced confidence calculation combining OCR and image quality."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        ocr_processor.initialize_engine()
        
        # Create test OCR result
        test_result = OCRResult(
            text="测试文本",
            confidence=0.8,
            bounding_boxes=[],
            processing_time=0.1
        )
        
        enhanced_confidence = ocr_processor.calculate_enhanced_confidence(sample_text_image, test_result)
        
        # Enhanced confidence should be between 0 and 1
        assert 0.0 <= enhanced_confidence <= 1.0
        # Should incorporate both OCR confidence and image quality
        assert enhanced_confidence != test_result.confidence
    
    def test_get_supported_languages(self, ocr_processor):
        """Test getting list of supported languages."""
        languages = ocr_processor.get_supported_languages()
        
        assert isinstance(languages, list)
        assert len(languages) > 0
        assert "chi_sim" in languages
        assert "en" in languages
        assert "ch" in languages
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_cleanup(self, mock_paddle_ocr, ocr_processor):
        """Test OCR engine cleanup."""
        # Initialize engine first
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        ocr_processor.initialize_engine()
        
        assert ocr_processor.is_engine_ready()
        
        # Cleanup
        ocr_processor.cleanup()
        
        assert not ocr_processor.is_engine_ready()
        assert ocr_processor.ocr_engine is None
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_ocr_processing_error_handling(self, mock_paddle_ocr, ocr_processor, sample_text_image):
        """Test OCR processing error handling."""
        # Setup mock OCR engine that raises exception
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        mock_ocr_instance.ocr.side_effect = Exception("OCR processing error")
        
        # Initialize engine and process image
        ocr_processor.initialize_engine()
        result = ocr_processor.process_image(sample_text_image)
        
        # Should return empty result on error
        assert isinstance(result, OCRResult)
        assert result.text == ""
        assert result.confidence == 0.0
        assert len(result.bounding_boxes) == 0
        assert result.processing_time > 0.0
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_different_image_qualities(self, mock_paddle_ocr, ocr_processor, sample_text_image, low_quality_image):
        """Test OCR processing with different image qualities."""
        # Setup mock OCR engine
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        # Mock different results for different quality images
        call_count = 0
        def mock_ocr_side_effect(image_array, cls=True):
            nonlocal call_count
            call_count += 1
            # First call (high quality image) returns high confidence
            if call_count == 1:
                return [[
                    [
                        [[10, 10], [100, 10], [100, 30], [10, 30]],
                        ("清晰文本", 0.95)  # Higher confidence
                    ]
                ]]
            else:
                # Second call (low quality image) returns lower confidence
                return [[
                    [
                        [[10, 10], [100, 10], [100, 30], [10, 30]],
                        ("模糊文本", 0.6)  # Lower confidence
                    ]
                ]]
        
        mock_ocr_instance.ocr.side_effect = mock_ocr_side_effect
        
        # Initialize engine
        ocr_processor.initialize_engine()
        
        # Process high quality image
        high_quality_result = ocr_processor.process_image(sample_text_image)
        
        # Process low quality image
        low_quality_result = ocr_processor.process_image(low_quality_image)
        
        # Verify different confidence levels
        assert high_quality_result.confidence > low_quality_result.confidence
        assert high_quality_result.text != low_quality_result.text


class TestOCRProcessorIntegration:
    """Integration tests for OCR processor with real image processing."""
    
    @pytest.fixture
    def real_text_image(self):
        """Create a realistic text image for integration testing."""
        # Create image with clear, readable text
        width, height = 600, 300
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        # Use default font
        font = ImageFont.load_default()
        
        # Draw text that simulates WeChat chat messages
        messages = [
            "张三: 你好，今天天气怎么样？",
            "李四: 天气很好，适合出去走走",
            "System: 张三 撤回了一条消息",
            "王五: [图片]",
            "赵六: 👍"
        ]
        
        y_offset = 30
        for message in messages:
            draw.text((30, y_offset), message, fill='black', font=font)
            y_offset += 45
        
        return image
    
    def test_realistic_chat_message_extraction(self, real_text_image):
        """Test OCR extraction on realistic chat message image."""
        # This test would require actual PaddleOCR installation
        # For now, we'll test the structure and error handling
        
        config = OCRConfig(language="chi_sim", confidence_threshold=0.5)
        processor = OCRProcessor(config)
        
        # Test without engine initialization (should raise error)
        with pytest.raises(RuntimeError):
            processor.process_image(real_text_image)
        
        # Test engine readiness
        assert not processor.is_engine_ready()
        
        # Test configuration
        assert processor.config.language == "chi_sim"
        assert processor.config.confidence_threshold == 0.5


def test_detect_text_regions_accepts_grayscale_input():
    pre = ImagePreprocessor()
    img = Image.new('RGB', (240, 120), color='white')
    draw = ImageDraw.Draw(img)
    draw.rectangle((30, 30, 210, 90), fill='black')
    gray = pre.preprocess_for_ocr(img)
    rects = pre.detect_text_regions(gray)
    assert isinstance(rects, list)


def test_detect_and_process_regions_adds_media_placeholder(monkeypatch):
    config = OCRConfig(language="chi_sim", confidence_threshold=0.5)
    processor = OCRProcessor(config)
    processor.ocr_engine = object()

    rect = Rectangle(x=10, y=10, width=240, height=180)

    def fake_detect_text_regions(image):
        return [rect]

    def fake_crop_text_region(image, region):
        crop = Image.new('L', (region.width, region.height), color=255)
        d = ImageDraw.Draw(crop)
        d.rectangle((20, 20, region.width - 20, region.height - 20), fill=0)
        return crop

    def fake_process_image(img, preprocess=True, preprocess_options=None, is_cropped_region=False):
        return OCRResult(text="", confidence=0.1, bounding_boxes=[], processing_time=0.01)

    monkeypatch.setattr(processor.preprocessor, "detect_text_regions", fake_detect_text_regions)
    monkeypatch.setattr(processor.preprocessor, "crop_text_region", fake_crop_text_region)
    monkeypatch.setattr(processor.preprocessor, "refine_crop", lambda img, padding=15: Rectangle(x=0, y=0, width=img.width, height=img.height))
    monkeypatch.setattr(processor, "process_image", fake_process_image)

    base = Image.new('RGB', (600, 800), color='white')
    results = processor.detect_and_process_regions(base, max_regions=10)
    assert any(tr.type in ("image", "sticker") for tr, _ in results)


def test_detect_and_process_regions_adds_media_placeholder_for_small_square(monkeypatch):
    config = OCRConfig(language="chi_sim", confidence_threshold=0.5)
    processor = OCRProcessor(config)
    processor.ocr_engine = object()

    rect = Rectangle(x=10, y=10, width=60, height=60)

    def fake_detect_text_regions(image):
        return [rect]

    def fake_crop_text_region(image, region):
        crop = Image.new('L', (region.width, region.height), color=255)
        d = ImageDraw.Draw(crop)
        d.ellipse((10, 10, region.width - 10, region.height - 10), fill=0)
        return crop

    def fake_process_image(img, preprocess=True, preprocess_options=None, is_cropped_region=False):
        return OCRResult(text="", confidence=0.1, bounding_boxes=[], processing_time=0.01)

    monkeypatch.setattr(processor.preprocessor, "detect_text_regions", fake_detect_text_regions)
    monkeypatch.setattr(processor.preprocessor, "crop_text_region", fake_crop_text_region)
    monkeypatch.setattr(processor.preprocessor, "refine_crop", lambda img, padding=15: Rectangle(x=0, y=0, width=img.width, height=img.height))
    monkeypatch.setattr(processor, "process_image", fake_process_image)

    base = Image.new('RGB', (600, 800), color='white')
    results = processor.detect_and_process_regions(base, max_regions=10)
    assert any(tr.type in ("image", "sticker") for tr, _ in results)
