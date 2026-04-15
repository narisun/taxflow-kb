"""Claude Vision extractor — sends PDFs/images to Claude API for structured extraction."""
import base64
import json

from api.models.document import ExtractionResult, ExtractedField
from api.services.ocr.prompts import get_prompt

CONFIDENCE_FLAG_THRESHOLD = 0.90
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ClaudeVisionExtractor:
    def __init__(self, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def extract(self, file_bytes: bytes, form_type: str) -> ExtractionResult:
        """Extract structured data from a tax document."""
        b64_data = base64.standard_b64encode(file_bytes).decode("utf-8")

        # Detect media type from file magic bytes
        if file_bytes[:4] == b"%PDF":
            media_type, block_type = "application/pdf", "document"
        elif file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            media_type, block_type = "image/png", "image"
        elif file_bytes[:2] in (b"\xff\xd8",):
            media_type, block_type = "image/jpeg", "image"
        else:
            media_type, block_type = "application/pdf", "document"

        prompt = get_prompt(form_type)

        media_block = {
            "type": block_type,
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64_data,
            },
        }
        text_block = {"type": "text", "text": prompt}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": [media_block, text_block]}],
            )
        except Exception:
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Extraction failed — API error. Manual entry required."],
            )

        raw_text = response.content[0].text if response.content else ""
        return self._parse_response(raw_text)

    def _parse_response(self, raw_text: str) -> ExtractionResult:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Extraction failed — invalid response. Manual entry required."],
            )

        fields_data = parsed.get("fields", {})
        if not isinstance(fields_data, dict):
            return ExtractionResult(
                fields=[], overall_confidence=0.0, has_flags=True,
                flags=["Extraction failed — unexpected format. Manual entry required."],
            )

        fields: list[ExtractedField] = []
        min_confidence = 1.0
        has_flags = False
        flag_messages: list[str] = []

        for key, info in fields_data.items():
            if isinstance(info, dict):
                value = str(info.get("value", ""))
                confidence = float(info.get("confidence", 0.0))
            else:
                value = str(info)
                confidence = 0.5

            flagged = confidence < CONFIDENCE_FLAG_THRESHOLD
            flag_reason = ""
            if flagged:
                has_flags = True
                flag_reason = f"Low confidence ({confidence:.0%})"
                flag_messages.append(f"{key}: {confidence:.0%} confidence")

            min_confidence = min(min_confidence, confidence)
            fields.append(ExtractedField(
                name=key, value=value, confidence=confidence,
                flagged=flagged, flag_reason=flag_reason,
            ))

        overall = min_confidence if fields else 0.0
        return ExtractionResult(
            fields=fields, overall_confidence=overall,
            has_flags=has_flags, flags=flag_messages,
        )
