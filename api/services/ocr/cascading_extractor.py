"""Cascading extractor — tries extraction tiers in order of cost/speed.

Tier 1: AcroForm field extraction (pypdf) — fillable PDFs, free, instant
Tier 2: Text layer extraction (pdfplumber) — readable PDFs, free, instant
Tier 3: Claude Vision API — scanned/image PDFs, API cost, slower

For each tier, if meaningful fields are extracted, stop. Otherwise try next tier.
"""
import logging

from api.models.document import ExtractionResult
from api.services.ocr.text_extractor import TextLayerExtractor, detect_pdf_format

logger = logging.getLogger(__name__)


class CascadingExtractor:
    """Format-aware extractor that selects the best method for each document."""

    def __init__(self, vision_extractor=None):
        """
        Args:
            vision_extractor: Optional Claude Vision extractor for Tier 3.
                If None, Tier 3 is skipped (mock mode).
        """
        self.text_extractor = TextLayerExtractor()
        self.vision_extractor = vision_extractor

    async def extract(self, file_bytes: bytes, form_type: str) -> ExtractionResult:
        """Extract data using the best available method for this document.

        Strategy:
        1. Detect format (acroform, text, scanned, image)
        2. For text/acroform PDFs → try text layer extraction first
        3. If text extraction yields no fields → fall through to Vision
        4. For scanned/image → go directly to Vision
        """
        fmt = detect_pdf_format(file_bytes)
        logger.info(f"Document format detected: {fmt} (form_type={form_type})")

        # Text-based PDFs: try text layer first
        if fmt in ("text", "acroform"):
            result = await self.text_extractor.extract(file_bytes, form_type)
            if result.fields:
                logger.info(f"Tier 2 (text layer): extracted {len(result.fields)} fields")
                return result
            logger.info("Tier 2: no fields extracted, falling through to Vision")

        # Fall through to Vision (Tier 3) if available
        if self.vision_extractor:
            logger.info("Tier 3 (Claude Vision): sending to API")
            return await self.vision_extractor.extract(file_bytes, form_type)

        # No Vision extractor configured — return what we have
        if fmt in ("scanned", "image"):
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Scanned/image document — Vision extraction not configured. "
                       "Set OCR_EXTRACTOR=claude to enable."],
            )

        return ExtractionResult(
            fields=[], overall_confidence=0.0, has_flags=True,
            flags=["Could not extract data from this document"],
        )
