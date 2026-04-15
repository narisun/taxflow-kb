"""Tests for Claude Vision extractor with mocked Anthropic client."""
import json
import pytest
from unittest.mock import MagicMock

from api.services.ocr.claude_extractor import ClaudeVisionExtractor


def _make_claude_response(fields_json: dict) -> MagicMock:
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = json.dumps({"fields": fields_json})
    response.content = [content_block]
    return response


def _mock_client(fields_json: dict) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = _make_claude_response(fields_json)
    return client


class TestClaudeVisionExtractor:
    @pytest.mark.asyncio
    async def test_w2_extraction(self, tmp_path):
        fields = {
            "box1_wages": {"value": "85000.00", "confidence": 0.99},
            "employer_name": {"value": "ACME CORP", "confidence": 0.97},
            "employer_ein": {"value": "12-3456789", "confidence": 0.95},
        }
        extractor = ClaudeVisionExtractor(_mock_client(fields))
        pdf_file = tmp_path / "w2.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        result = await extractor.extract(str(pdf_file), "W-2")
        assert len(result.fields) == 3
        assert result.structured_data["box1_wages"] == "85000.00"
        assert result.overall_confidence == 0.95
        assert result.has_flags is False

    @pytest.mark.asyncio
    async def test_low_confidence_flagged(self, tmp_path):
        fields = {
            "box1_interest": {"value": "3847.00", "confidence": 0.95},
            "payer": {"value": "CHASE", "confidence": 0.72},
        }
        extractor = ClaudeVisionExtractor(_mock_client(fields))
        pdf_file = tmp_path / "1099.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        result = await extractor.extract(str(pdf_file), "1099-INT")
        assert result.has_flags is True
        flagged = [f for f in result.fields if f.flagged]
        assert len(flagged) == 1
        assert flagged[0].name == "payer"

    @pytest.mark.asyncio
    async def test_image_file_detected(self, tmp_path):
        fields = {"box1_wages": {"value": "50000.00", "confidence": 0.90}}
        extractor = ClaudeVisionExtractor(_mock_client(fields))
        img_file = tmp_path / "w2.png"
        img_file.write_bytes(b"\x89PNG fake image")

        await extractor.extract(str(img_file), "W-2")
        call_args = extractor.client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]
        assert content[0]["type"] == "image"

    @pytest.mark.asyncio
    async def test_pdf_file_detected(self, tmp_path):
        fields = {"box1_wages": {"value": "50000.00", "confidence": 0.90}}
        extractor = ClaudeVisionExtractor(_mock_client(fields))
        pdf_file = tmp_path / "w2.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        await extractor.extract(str(pdf_file), "W-2")
        call_args = extractor.client.messages.create.call_args
        content = call_args.kwargs["messages"][0]["content"]
        assert content[0]["type"] == "document"

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, tmp_path):
        client = MagicMock()
        response = MagicMock()
        content_block = MagicMock()
        content_block.text = "This is not valid JSON"
        response.content = [content_block]
        client.messages.create.return_value = response

        extractor = ClaudeVisionExtractor(client)
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        result = await extractor.extract(str(pdf_file), "W-2")
        assert len(result.fields) == 0
        assert result.has_flags is True
        assert any("failed" in f.lower() or "manual" in f.lower() for f in result.flags)

    @pytest.mark.asyncio
    async def test_correct_prompt_selected(self, tmp_path):
        fields = {"payer": {"value": "CHASE", "confidence": 0.95}}
        extractor = ClaudeVisionExtractor(_mock_client(fields))
        pdf_file = tmp_path / "form.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        await extractor.extract(str(pdf_file), "1099-INT")
        call_args = extractor.client.messages.create.call_args
        prompt_text = call_args.kwargs["messages"][0]["content"][1]["text"]
        assert "1099-INT" in prompt_text
        assert "box1_interest" in prompt_text
