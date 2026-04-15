"""Maps structured field keys to human-readable display labels for the CPA review UI."""

FIELD_LABELS: dict[str, dict[str, str]] = {
    "W-2": {
        "employer_name": "Employer Name",
        "employer_ein": "Employer EIN",
        "box1_wages": "Box 1 \u2014 Wages, salaries, tips",
        "box2_fed_withheld": "Box 2 \u2014 Federal income tax withheld",
        "box3_ss_wages": "Box 3 \u2014 Social Security wages",
        "box4_ss_withheld": "Box 4 \u2014 Social Security tax withheld",
        "box5_medicare_wages": "Box 5 \u2014 Medicare wages and tips",
        "box6_medicare_withheld": "Box 6 \u2014 Medicare tax withheld",
        "box15_state": "Box 15 \u2014 State",
        "box16_state_wages": "Box 16 \u2014 State wages, tips",
        "box17_state_withheld": "Box 17 \u2014 State income tax",
    },
    "1099-INT": {
        "payer": "Payer Name",
        "box1_interest": "Box 1 \u2014 Interest income",
        "box4_fed_withheld": "Box 4 \u2014 Federal income tax withheld",
    },
    "1099-DIV": {
        "payer": "Payer Name",
        "box1a_ordinary_dividends": "Box 1a \u2014 Total ordinary dividends",
        "box1b_qualified_dividends": "Box 1b \u2014 Qualified dividends",
        "box2a_capital_gain_distributions": "Box 2a \u2014 Total capital gain distributions",
    },
    "1099-B": {
        "payer": "Broker Name",
        "short_term_proceeds": "Short-term proceeds",
        "short_term_cost_basis": "Short-term cost basis",
        "long_term_proceeds": "Long-term proceeds",
        "long_term_cost_basis": "Long-term cost basis",
    },
    "1099-NEC": {
        "payer": "Payer Name",
        "nec_compensation": "Box 1 \u2014 Nonemployee compensation",
        "fed_tax_withheld": "Box 4 \u2014 Federal income tax withheld",
    },
    "1098": {
        "lender": "Lender Name",
        "box1_interest": "Box 1 \u2014 Mortgage interest received",
        "box10_property_taxes": "Box 10 \u2014 Property taxes",
    },
    "K-1": {
        "entity_name": "Entity Name",
        "entity_ein": "Entity EIN",
        "entity_type": "Entity Type (P=Partnership, S=S-Corp)",
        "box1_ordinary_income": "Box 1 \u2014 Ordinary business income/loss",
        "box2_rental_income": "Box 2 \u2014 Net rental real estate income/loss",
        "box4a_guaranteed_payments": "Box 4a \u2014 Guaranteed payments",
        "box14a_se_earnings": "Box 14a \u2014 Self-employment earnings",
        "box20z_section_199a_qbi": "Box 20 Code Z \u2014 Section 199A QBI",
    },
}


def get_display_label(form_type: str, field_key: str) -> str:
    """Return human-readable label for a structured field key."""
    return FIELD_LABELS.get(form_type, {}).get(field_key, field_key)
