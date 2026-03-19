"""
Basic OCR processor tests that don't require PaddleOCR installation.
"""
import pytest
from unittest.mock import Mock, patch
import sys

# Mock PaddleOCR before importing our modules
sys.modules['paddleocr'] = Mock()

from models.config import OCRConfig
from models.data_models import OCRResult, Rectangle


class TestOCRBasics:
    """Basic tests for OCR functionality without PaddleOCR dependency."""
    
    def test_ocr_config_creation(self):
        """Test OCR configuration creation."""
        config = OCRConfig()
        
        # Default OCR language now aligns with PaddleOCR's Chinese/English code 'ch'
        assert config.language == "ch"
        assert config.confidence_threshold == 0.7
        assert config.use_gpu is False
    
    def test_ocr_config_custom_values(self):
        """Test OCR configuration with custom values."""
        config = OCRConfig(
            language="en",
            confidence_threshold=0.8,
            use_gpu=True
        )
        
        assert config.language == "en"
        assert config.confidence_threshold == 0.8
        assert config.use_gpu is True
    
    def test_ocr_result_creation(self):
        """Test OCR result data structure."""
        bounding_boxes = [
            Rectangle(x=10, y=10, width=100, height=30),
            Rectangle(x=10, y=50, width=150, height=30)
        ]
        
        result = OCRResult(
            text="测试文本\nTest Text",
            confidence=0.85,
            bounding_boxes=bounding_boxes,
            processing_time=0.5
        )
        
        assert result.text == "测试文本\nTest Text"
        assert result.confidence == 0.85
        assert len(result.bounding_boxes) == 2
        assert result.processing_time == 0.5
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_ocr_processor_import(self, mock_paddle_ocr):
        """Test that OCR processor can be imported and initialized."""
        from services.ocr_processor import OCRProcessor
        
        processor = OCRProcessor()
        assert processor is not None
        assert processor.config is not None
        assert not processor.is_engine_ready()
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_ocr_processor_with_config(self, mock_paddle_ocr):
        """Test OCR processor initialization with custom config."""
        from services.ocr_processor import OCRProcessor
        
        config = OCRConfig(language="en", confidence_threshold=0.6)
        processor = OCRProcessor(config)
        
        assert processor.config.language == "en"
        assert processor.config.confidence_threshold == 0.6
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_ocr_engine_initialization_mock(self, mock_paddle_ocr):
        """Test OCR engine initialization with mocked PaddleOCR."""
        from services.ocr_processor import OCRProcessor
        
        # Setup mock
        mock_ocr_instance = Mock()
        mock_paddle_ocr.return_value = mock_ocr_instance
        
        processor = OCRProcessor()
        result = processor.initialize_engine()
        
        assert result is True
        assert processor.is_engine_ready()
        mock_paddle_ocr.assert_called_once()
    
    @patch('services.ocr_processor.PaddleOCR')
    def test_supported_languages(self, mock_paddle_ocr):
        """Test getting supported languages list."""
        from services.ocr_processor import OCRProcessor
        
        processor = OCRProcessor()
        languages = processor.get_supported_languages()
        
        assert isinstance(languages, list)
        assert "chi_sim" in languages
        assert "en" in languages
        assert len(languages) > 0