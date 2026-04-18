"""Maps structured field keys to human-readable display labels for the CPA review UI."""

FIELD_LABELS: dict[str, dict[str, str]] = {
    "W-2": {
        "employee_ssn": "Box a \u2014 Employee SSN",
        "employee_name": "Box e \u2014 Employee name",
        "employee_first_name": "Box e \u2014 Employee first name",
        "employee_last_name": "Box e \u2014 Employee last name",
        "employee_address": "Box f \u2014 Employee address",
        "employer_name": "Box c \u2014 Employer name",
        "employer_ein": "Box b \u2014 Employer EIN",
        "control_number": "Box d \u2014 Control number",
        "box1_wages": "Box 1 \u2014 Wages, salaries, tips",
        "box2_fed_withheld": "Box 2 \u2014 Federal income tax withheld",
        "box3_ss_wages": "Box 3 \u2014 Social Security wages",
        "box4_ss_withheld": "Box 4 \u2014 Social Security tax withheld",
        "box5_medicare_wages": "Box 5 \u2014 Medicare wages and tips",
        "box6_medicare_withheld": "Box 6 \u2014 Medicare tax withheld",
        "box12a_code": "Box 12a \u2014 Code",
        "box12a_amount": "Box 12a \u2014 Amount",
        "box14_other": "Box 14 \u2014 Other",
        "box15_state": "Box 15 \u2014 State",
        "box15_state_ein": "Box 15 \u2014 State EIN",
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
