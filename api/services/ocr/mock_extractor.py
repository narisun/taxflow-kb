"""Mock OCR extractor for development -- returns realistic data without calling any API."""
from api.models.document import ExtractionResult, ExtractedField


class MockOCRExtractor:
    async def extract(self, file_path: str, form_type: str) -> ExtractionResult:
        """Return realistic mock data per form type."""
        if form_type == "W-2":
            fields = [
                ExtractedField(name="Box 1 — Wages", value="$112,400.00", confidence=0.99),
                ExtractedField(name="Box 2 — Federal Tax Withheld", value="$18,750.00", confidence=0.99),
                ExtractedField(name="Employer", value="ACME CORPORATION", confidence=0.97),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.99, has_flags=False, flags=[])

        elif form_type == "1099-INT":
            fields = [
                ExtractedField(name="Box 1 — Interest Income", value="$3,847.00", confidence=0.96),
                ExtractedField(
                    name="Account Number", value="••••8821", confidence=0.82,
                    flagged=True, flag_reason="Partially illegible",
                ),
            ]
            return ExtractionResult(
                fields=fields, overall_confidence=0.82, has_flags=True,
                flags=["Account number 82% confidence"],
            )

        elif form_type == "1098":
            fields = [
                ExtractedField(name="Box 1 — Mortgage Interest", value="$14,220.00", confidence=0.98),
                ExtractedField(name="Lender", value="FIRST NATIONAL BANK", confidence=0.95),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.95, has_flags=False, flags=[])

        elif form_type == "1099-B":
            fields = [
                ExtractedField(name="1d — Proceeds", value="$52,300.00", confidence=0.94),
                ExtractedField(name="1e — Cost Basis", value="$48,100.00", confidence=0.91),
                ExtractedField(
                    name="Date Sold", value="09/15/2024", confidence=0.78,
                    flagged=True, flag_reason="Date partially obscured",
                ),
            ]
            return ExtractionResult(
                fields=fields, overall_confidence=0.78, has_flags=True,
                flags=["Date sold 78% confidence"],
            )

        elif form_type == "K-1":
            fields = [
                ExtractedField(name="Box 1 — Ordinary Business Income", value="$8,400.00", confidence=0.93),
                ExtractedField(name="Partnership Name", value="SMITH HOLDINGS LLC", confidence=0.90),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.90, has_flags=False, flags=[])

        # Unknown form type
        return ExtractionResult(fields=[], overall_confidence=0.0, has_flags=False, flags=[])
