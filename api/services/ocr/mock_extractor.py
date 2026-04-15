"""Mock OCR extractor for development — returns structured data with file-based variation."""
import hashlib
from api.models.document import ExtractionResult, ExtractedField


class MockOCRExtractor:
    async def extract(self, file_bytes: bytes, form_type: str) -> ExtractionResult:
        """Return mock data with slight variation based on file content hash."""
        # Use file hash to create variation — different files produce different values
        h = int(hashlib.md5(file_bytes).hexdigest()[:8], 16) if file_bytes else 0
        variation = (h % 50) * 1000  # 0 to 49000 variation

        if form_type == "W-2":
            wages = 75000 + variation
            withheld = round(wages * 0.18)
            fields = [
                ExtractedField(name="box1_wages", value=f"{wages:.2f}", confidence=0.99),
                ExtractedField(name="box2_fed_withheld", value=f"{withheld:.2f}", confidence=0.99),
                ExtractedField(name="employer_name", value="ACME CORPORATION", confidence=0.97),
                ExtractedField(name="employer_ein", value="12-3456789", confidence=0.95),
                ExtractedField(name="box3_ss_wages", value=f"{wages:.2f}", confidence=0.98),
                ExtractedField(name="box5_medicare_wages", value=f"{wages:.2f}", confidence=0.98),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.95, has_flags=False, flags=[])

        elif form_type == "1099-INT":
            interest = 1500 + (h % 20) * 100
            fields = [
                ExtractedField(name="payer", value="CHASE BANK", confidence=0.96),
                ExtractedField(name="box1_interest", value=f"{interest:.2f}", confidence=0.96),
                ExtractedField(
                    name="box4_fed_withheld", value="0.00", confidence=0.82,
                    flagged=True, flag_reason="Value partially illegible",
                ),
            ]
            return ExtractionResult(
                fields=fields, overall_confidence=0.82, has_flags=True,
                flags=["box4_fed_withheld: 82% confidence"],
            )

        elif form_type == "1099-DIV":
            divs = 3000 + (h % 15) * 200
            fields = [
                ExtractedField(name="payer", value="VANGUARD", confidence=0.97),
                ExtractedField(name="box1a_ordinary_dividends", value=f"{divs:.2f}", confidence=0.95),
                ExtractedField(name="box1b_qualified_dividends", value=f"{round(divs * 0.8):.2f}", confidence=0.95),
                ExtractedField(name="box2a_capital_gain_distributions", value=f"{round(divs * 0.25):.2f}", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.93, has_flags=False, flags=[])

        elif form_type == "1099-B":
            proceeds = 30000 + variation
            fields = [
                ExtractedField(name="payer", value="FIDELITY INVESTMENTS", confidence=0.94),
                ExtractedField(name="short_term_proceeds", value=f"{round(proceeds * 0.3):.2f}", confidence=0.91),
                ExtractedField(name="short_term_cost_basis", value=f"{round(proceeds * 0.27):.2f}", confidence=0.91),
                ExtractedField(name="long_term_proceeds", value=f"{round(proceeds * 0.7):.2f}", confidence=0.94),
                ExtractedField(name="long_term_cost_basis", value=f"{round(proceeds * 0.6):.2f}", confidence=0.91),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.91, has_flags=False, flags=[])

        elif form_type == "1099-NEC":
            comp = 15000 + variation
            fields = [
                ExtractedField(name="payer", value="CONSULTING CLIENT INC", confidence=0.95),
                ExtractedField(name="nec_compensation", value=f"{comp:.2f}", confidence=0.97),
                ExtractedField(name="fed_tax_withheld", value="0.00", confidence=0.99),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.95, has_flags=False, flags=[])

        elif form_type == "1098":
            interest = 8000 + (h % 20) * 500
            fields = [
                ExtractedField(name="lender", value="FIRST NATIONAL BANK", confidence=0.95),
                ExtractedField(name="box1_interest", value=f"{interest:.2f}", confidence=0.98),
                ExtractedField(name="box10_property_taxes", value=f"{round(interest * 0.5):.2f}", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.93, has_flags=False, flags=[])

        elif form_type == "K-1":
            income = 5000 + (h % 10) * 1000
            fields = [
                ExtractedField(name="entity_name", value="SMITH HOLDINGS LLC", confidence=0.93),
                ExtractedField(name="entity_ein", value="98-7654321", confidence=0.90),
                ExtractedField(name="entity_type", value="P", confidence=0.95),
                ExtractedField(name="box1_ordinary_income", value=f"{income:.2f}", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.90, has_flags=False, flags=[])

        # Unknown/Other form type — flag for manual review
        return ExtractionResult(
            fields=[], overall_confidence=0.0, has_flags=True,
            flags=["Unrecognized form type — manual classification and data entry required"],
        )
