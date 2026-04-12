"""OCR extractor protocol definition."""
from typing import Protocol

from api.models.document import ExtractionResult


class OCRExtractor(Protocol):
    async def extract(self, file_path: str, form_type: str) -> ExtractionResult: ...
