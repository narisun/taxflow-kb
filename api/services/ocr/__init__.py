"""OCR extraction service package."""
from api.services.ocr.protocol import OCRExtractor
from api.services.ocr.mock_extractor import MockOCRExtractor

__all__ = ["OCRExtractor", "MockOCRExtractor"]
