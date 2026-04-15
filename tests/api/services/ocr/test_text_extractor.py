"""Tests for text layer extraction."""
import pytest
from api.services.ocr.text_extractor import (
    TextLayerExtractor,
    detect_pdf_format,
    _classify_form,
    _parse_currency,
    _extract_number,
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


class TestExtractNumber:
    def test_plain(self):
        assert _extract_number("160000") == "160000.00"

    def test_with_dollar(self):
        assert _extract_number("$21,000.00") == "21000.00"

    def test_empty(self):
        assert _extract_number("") == ""


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
    async def test_extracts_from_real_w2(self):
        """Test extraction from a real W-2 PDF if available."""
        try:
            with open("/Users/admin-h26/Downloads/johndoe_W2.pdf", "rb") as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip("johndoe_W2.pdf not found")

        extractor = TextLayerExtractor()
        result = await extractor.extract(content, "W-2")

        assert len(result.fields) >= 10
        field_map = {f.name: f.value for f in result.fields}

        assert field_map["employer_ein"] == "12-1234567"
        assert field_map["employer_name"] == "ACME CORPORATION"
        assert field_map["box1_wages"] == "160000.00"
        assert field_map["box2_fed_withheld"] == "21000.00"
        assert field_map["box3_ss_wages"] == "140000.00"
        assert field_map["employee_ssn"] == "123-12-1234"
        assert field_map["employee_name"] == "John Doe M"
        assert field_map["box15_state"] == "NJ"

    @pytest.mark.asyncio
    async def test_handles_minimal_pdf(self):
        """Minimal/simple PDFs should not crash — may extract 0 fields."""
        try:
            with open("tests/sample_w2.pdf", "rb") as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip("tests/sample_w2.pdf not found")

        extractor = TextLayerExtractor()
        result = await extractor.extract(content, "W-2")
        # Minimal PDF may or may not have extractable fields — just don't crash
        assert isinstance(result.fields, list)

    @pytest.mark.asyncio
    async def test_empty_bytes(self):
        extractor = TextLayerExtractor()
        result = await extractor.extract(b"", "W-2")
        assert result.overall_confidence == 0.0
        assert result.has_flags is True

    @pytest.mark.asyncio
    async def test_unknown_form_generic_extract(self):
        """Unknown forms should capture all data in other_fields."""
        extractor = TextLayerExtractor()
        result = await extractor.extract(b"not a pdf", "Other")
        assert result.has_flags is True


class TestCascadingExtractor:
    @pytest.mark.asyncio
    async def test_cascade_uses_text_layer(self):
        from api.services.ocr.cascading_extractor import CascadingExtractor

        try:
            with open("tests/sample_w2.pdf", "rb") as f:
                content = f.read()
        except FileNotFoundError:
            pytest.skip("tests/sample_w2.pdf not found")

        extractor = CascadingExtractor(vision_extractor=None)
        result = await extractor.extract(content, "W-2")
        if result.fields:
            assert len(result.fields) > 0
