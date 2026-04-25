"""Tests for form-specific extraction prompts."""
from api.services.ocr.prompts import get_prompt, SUPPORTED_FORM_TYPES


class TestGetPrompt:
    def test_w2_prompt_contains_field_keys(self):
        prompt = get_prompt("W-2")
        assert "box1_wages" in prompt
        assert "employer_name" in prompt
        assert "employer_ein" in prompt
        assert "box2_fed_withheld" in prompt

    def test_1099_int_prompt(self):
        prompt = get_prompt("1099-INT")
        assert "box1_interest" in prompt
        assert "payer" in prompt

    def test_1099_div_prompt(self):
        prompt = get_prompt("1099-DIV")
        assert "box1a_ordinary_dividends" in prompt
        assert "box1b_qualified_dividends" in prompt

    def test_1099_b_prompt(self):
        prompt = get_prompt("1099-B")
        assert "short_term_proceeds" in prompt
        assert "long_term_proceeds" in prompt

    def test_1099_nec_prompt(self):
        prompt = get_prompt("1099-NEC")
        assert "nec_compensation" in prompt

    def test_1098_prompt(self):
        prompt = get_prompt("1098")
        assert "box1_interest" in prompt
        assert "lender" in prompt

    def test_k1_prompt(self):
        prompt = get_prompt("K-1")
        assert "entity_name" in prompt
        assert "entity_ein" in prompt
        assert "box1_ordinary_income" in prompt

    def test_unknown_form_returns_fallback(self):
        prompt = get_prompt("unknown-form")
        assert "identify" in prompt.lower() or "extract" in prompt.lower()

    def test_all_supported_types_have_prompts(self):
        for form_type in SUPPORTED_FORM_TYPES:
            prompt = get_prompt(form_type)
            assert len(prompt) > 50

    def test_all_prompts_request_json_format(self):
        for form_type in SUPPORTED_FORM_TYPES:
            prompt = get_prompt(form_type)
            assert "json" in prompt.lower() or "JSON" in prompt

    def test_all_prompts_mention_confidence(self):
        # 1040-Prior uses direct value extraction (no confidence scores)
        # since it's extracting from a completed filed return, not raw OCR.
        skip = {"1040-Prior"}
        for form_type in SUPPORTED_FORM_TYPES:
            if form_type in skip:
                continue
            prompt = get_prompt(form_type)
            assert "confidence" in prompt.lower()
