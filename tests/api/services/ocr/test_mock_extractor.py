"""Tests for mock extractor — structured format."""
import pytest
from api.services.ocr.mock_extractor import MockOCRExtractor

@pytest.fixture
def extractor():
    return MockOCRExtractor()

class TestMockExtractor:
    @pytest.mark.asyncio
    async def test_w2_returns_structured_keys(self, extractor):
        result = await extractor.extract(b"fake-pdf-content", "W-2")
        field_names = [f.name for f in result.fields]
        assert "box1_wages" in field_names
        assert "employer_name" in field_names

    @pytest.mark.asyncio
    async def test_w2_values_are_clean_numbers(self, extractor):
        result = await extractor.extract(b"fake-pdf-content", "W-2")
        wages = next(f for f in result.fields if f.name == "box1_wages")
        assert "$" not in wages.value
        assert "," not in wages.value

    @pytest.mark.asyncio
    async def test_1099_int_has_flag(self, extractor):
        result = await extractor.extract(b"fake-pdf-content", "1099-INT")
        assert result.has_flags is True

    @pytest.mark.asyncio
    async def test_structured_data_dict(self, extractor):
        result = await extractor.extract(b"fake-pdf-content", "W-2")
        data = result.structured_data
        assert isinstance(data, dict)
        assert "box1_wages" in data

    @pytest.mark.asyncio
    async def test_all_form_types(self, extractor):
        for ft in ["W-2", "1099-INT", "1099-DIV", "1099-B", "1099-NEC", "1098", "K-1"]:
            result = await extractor.extract(b"fake-pdf-content", ft)
            assert len(result.fields) >= 2, f"{ft} should have at least 2 fields"

    @pytest.mark.asyncio
    async def test_unknown_form(self, extractor):
        result = await extractor.extract(b"fake-pdf-content", "unknown")
        assert result.overall_confidence == 0.0
