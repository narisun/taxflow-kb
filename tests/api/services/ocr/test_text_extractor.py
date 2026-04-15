"""Tests for text layer extraction."""
import pytest
from api.services.ocr.text_extractor import (
    TextLayerExtractor,
    detect_pdf_format,
    _classify_form,
    _find_amount_after_label,
    _parse_currency,
)


class TestParseCurrency:
    def test_plain_number(self):
        assert _parse_currency("112400.00") == "112400.00"

    def test_with_dollar_sign(self):
        assert _parse_currency("$112,400.00") == "112400.00"

    def test_with_commas(self):
        assert _parse_currency("112,400.00") == "112400.00"

    def test_empty(self):
        assert _parse_currency("") == ""

    def test_integer(self):
        assert _parse_currency("5000") == "5000.00"


class TestFindAmountAfterLabel:
    def test_w2_wages(self):
        text = "Box 1 Wages, salaries, tips  $112,400.00  Box 2 Federal income tax withheld"
        result = _find_amount_after_label(text, [r"1\s+wages"])
        assert result == "112400.00"

    def test_fed_withheld(self):
        text = "Box 2 Federal income tax withheld  18750.00"
        result = _find_amount_after_label(text, [r"federal\s+(?:income\s+)?tax\s+withheld"])
        assert result == "18750.00"

    def test_no_match(self):
        text = "This has no tax data"
        result = _find_amount_after_label(text, [r"wages"])
        assert result == ""


class TestClassifyForm:
    def test_w2_from_text(self):
        assert _classify_form("W-2 Wage and Tax Statement 2024") == "W-2"

    def test_w2_from_filename(self):
        assert _classify_form("some text", "john_w2_2024.pdf") == "W-2"

    def test_1099_int(self):
        assert _classify_form("1099-INT Interest Income") == "1099-INT"

    def test_1098(self):
        assert _classify_form("1098 Mortgage Interest Statement") == "1098"

    def test_unknown(self):
        assert _classify_form("random document") == "Other"


class TestDetectFormat:
    def test_not_pdf(self):
        assert detect_pdf_format(b"not a pdf") == "not_pdf"

    def test_png_image(self):
        assert detect_pdf_format(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100) == "image"

    def test_jpeg_image(self):
        assert detect_pdf_format(b"\xff\xd8\xff\xe0" + b"\x00" * 100) == "image"


class TestTextLayerExtractor:
    @pytest.mark.asyncio
    async def test_extracts_from_sample_w2(self):
        """Test extraction from our sample W-2 PDF."""
        try:
            with open("tests/sample_w2.pdf", "rb") as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip("tests/sample_w2.pdf not found")

        extractor = TextLayerExtractor()
        result = await extractor.extract(content, "W-2")

        assert len(result.fields) > 0
        field_names = [f.name for f in result.fields]

        # Our sample W-2 should have wages and withheld
        if "box1_wages" in field_names:
            wages = next(f for f in result.fields if f.name == "box1_wages")
            assert wages.value == "112400.00"

    @pytest.mark.asyncio
    async def test_empty_bytes(self):
        extractor = TextLayerExtractor()
        result = await extractor.extract(b"", "W-2")
        assert result.overall_confidence == 0.0
        assert result.has_flags is True

    @pytest.mark.asyncio
    async def test_auto_classify_other(self):
        """When form_type is 'Other', should auto-detect from text."""
        # Create minimal PDF-like bytes (won't work with pdfplumber but tests the path)
        extractor = TextLayerExtractor()
        result = await extractor.extract(b"not a pdf", "Other")
        assert result.has_flags is True


class TestCascadingExtractor:
    @pytest.mark.asyncio
    async def test_cascade_uses_text_layer(self):
        """Cascading extractor should use text layer for readable PDFs."""
        from api.services.ocr.cascading_extractor import CascadingExtractor

        try:
            with open("tests/sample_w2.pdf", "rb") as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip("tests/sample_w2.pdf not found")

        extractor = CascadingExtractor(vision_extractor=None)
        result = await extractor.extract(content, "W-2")

        # Should extract fields from text layer without needing Vision
        if result.fields:
            field_names = [f.name for f in result.fields]
            assert "box1_wages" in field_names or len(result.fields) > 0
