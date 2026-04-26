"""Factory for constructing :class:`api.services.ocr.protocol.OCRExtractor`.

Encapsulates the strategy selection (cascade / claude / mock) so it can be
unit-tested and injected into routers without touching ``os.environ`` or
instantiating Anthropic clients inside request handlers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from api.config import OCRMode
from api.services.ocr.cascading_extractor import CascadingExtractor
from api.services.ocr.claude_extractor import ClaudeVisionExtractor
from api.services.ocr.mock_extractor import MockOCRExtractor
from api.services.ocr.protocol import OCRExtractor

if TYPE_CHECKING:
    import anthropic


class OCRExtractorFactory:
    """Builds an :class:`OCRExtractor` based on an injected mode + client.

    The factory is stateless; instances are cheap to construct. Routers
    request one instance per request via :mod:`api.dependencies`.
    """

    def __init__(
        self,
        *,
        mode: OCRMode,
        anthropic_client: "anthropic.Anthropic | None",
    ) -> None:
        self._mode = mode
        self._anthropic_client = anthropic_client

    def build(self) -> OCRExtractor:
        if self._mode == "mock":
            return MockOCRExtractor()

        if self._mode == "claude":
            if self._anthropic_client is None:
                raise RuntimeError(
                    "OCR_EXTRACTOR=claude requires ANTHROPIC_API_KEY to be set."
                )
            return ClaudeVisionExtractor(self._anthropic_client)

        # cascade: text-layer first, Claude Vision fallback if client available.
        vision = (
            ClaudeVisionExtractor(self._anthropic_client)
            if self._anthropic_client is not None
            else None
        )
        return CascadingExtractor(vision_extractor=vision)
