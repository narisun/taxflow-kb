"""Mock OCR extractor for development — returns structured data matching Pydantic model fields."""
from api.models.document import ExtractionResult, ExtractedField


class MockOCRExtractor:
    async def extract(self, file_path: str, form_type: str) -> ExtractionResult:
        """Return realistic mock data using structured field keys."""
        if form_type == "W-2":
            fields = [
                ExtractedField(name="box1_wages", value="112400.00", confidence=0.99),
                ExtractedField(name="box2_fed_withheld", value="18750.00", confidence=0.99),
                ExtractedField(name="employer_name", value="ACME CORPORATION", confidence=0.97),
                ExtractedField(name="employer_ein", value="12-3456789", confidence=0.95),
                ExtractedField(name="box3_ss_wages", value="112400.00", confidence=0.98),
                ExtractedField(name="box5_medicare_wages", value="112400.00", confidence=0.98),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.95, has_flags=False, flags=[])

        elif form_type == "1099-INT":
            fields = [
                ExtractedField(name="payer", value="CHASE BANK", confidence=0.96),
                ExtractedField(name="box1_interest", value="3847.00", confidence=0.96),
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
            fields = [
                ExtractedField(name="payer", value="VANGUARD", confidence=0.97),
                ExtractedField(name="box1a_ordinary_dividends", value="5200.00", confidence=0.95),
                ExtractedField(name="box1b_qualified_dividends", value="4100.00", confidence=0.95),
                ExtractedField(name="box2a_capital_gain_distributions", value="1200.00", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.93, has_flags=False, flags=[])

        elif form_type == "1099-B":
            fields = [
                ExtractedField(name="payer", value="FIDELITY INVESTMENTS", confidence=0.94),
                ExtractedField(name="short_term_proceeds", value="15200.00", confidence=0.91),
                ExtractedField(name="short_term_cost_basis", value="13800.00", confidence=0.91),
                ExtractedField(name="long_term_proceeds", value="52300.00", confidence=0.94),
                ExtractedField(name="long_term_cost_basis", value="48100.00", confidence=0.91),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.91, has_flags=False, flags=[])

        elif form_type == "1099-NEC":
            fields = [
                ExtractedField(name="payer", value="CONSULTING CLIENT INC", confidence=0.95),
                ExtractedField(name="nec_compensation", value="25000.00", confidence=0.97),
                ExtractedField(name="fed_tax_withheld", value="0.00", confidence=0.99),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.95, has_flags=False, flags=[])

        elif form_type == "1098":
            fields = [
                ExtractedField(name="lender", value="FIRST NATIONAL BANK", confidence=0.95),
                ExtractedField(name="box1_interest", value="14220.00", confidence=0.98),
                ExtractedField(name="box10_property_taxes", value="6800.00", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.93, has_flags=False, flags=[])

        elif form_type == "K-1":
            fields = [
                ExtractedField(name="entity_name", value="SMITH HOLDINGS LLC", confidence=0.93),
                ExtractedField(name="entity_ein", value="98-7654321", confidence=0.90),
                ExtractedField(name="entity_type", value="P", confidence=0.95),
                ExtractedField(name="box1_ordinary_income", value="8400.00", confidence=0.93),
            ]
            return ExtractionResult(fields=fields, overall_confidence=0.90, has_flags=False, flags=[])

        # Unknown/Other form type — flag for manual review
        return ExtractionResult(
            fields=[], overall_confidence=0.0, has_flags=True,
            flags=["Unrecognized form type — manual classification and data entry required"],
        )
