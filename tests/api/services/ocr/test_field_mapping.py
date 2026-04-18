"""Tests for field display label mapping."""
from api.services.ocr.field_mapping import get_display_label, FIELD_LABELS
from api.services.ocr.prompts import SUPPORTED_FORM_TYPES


class TestGetDisplayLabel:
    def test_w2_wages(self):
        assert get_display_label("W-2", "box1_wages") == "Box 1 \u2014 Wages, salaries, tips"

    def test_w2_employer(self):
        assert get_display_label("W-2", "employer_name") == "Box c \u2014 Employer name"

    def test_1099_int_interest(self):
        assert get_display_label("1099-INT", "box1_interest") == "Box 1 \u2014 Interest income"

    def test_1099_div_qualified(self):
        assert get_display_label("1099-DIV", "box1b_qualified_dividends") == "Box 1b \u2014 Qualified dividends"

    def test_k1_entity_name(self):
        assert get_display_label("K-1", "entity_name") == "Entity Name"

    def test_unknown_key_returns_key(self):
        assert get_display_label("W-2", "nonexistent_field") == "nonexistent_field"

    def test_unknown_form_returns_key(self):
        assert get_display_label("unknown-form", "some_field") == "some_field"

    def test_all_supported_forms_have_labels(self):
        for form_type in SUPPORTED_FORM_TYPES:
            assert form_type in FIELD_LABELS
            assert len(FIELD_LABELS[form_type]) >= 2
