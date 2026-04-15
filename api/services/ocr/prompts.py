"""Form-specific extraction prompts for Claude Vision API."""

SUPPORTED_FORM_TYPES = ["W-2", "1099-INT", "1099-DIV", "1099-B", "1099-NEC", "1098", "K-1"]

_RESPONSE_FORMAT = """
Return ONLY valid JSON in this exact format (no markdown fences, no extra text):
{
  "fields": {
    "field_key": {"value": "extracted_value", "confidence": 0.95},
    ...
  }
}
"""

_COMMON_RULES = """
Rules:
- Return numeric values as plain numbers without $ signs or commas (e.g., "112400.00" not "$112,400.00")
- EINs should be in XX-XXXXXXX format (e.g., "12-3456789")
- For each field, assess your confidence from 0.0 to 1.0
- If a field is not present on the form, omit it from the response
- If a field is partially illegible, include your best guess and set confidence below 0.8
"""

_PROMPTS: dict[str, str] = {
    "W-2": f"""You are extracting data from a US tax form W-2 (Wage and Tax Statement).

Extract the following fields using these exact JSON keys:
- employer_name: Employer's name (box c)
- employer_ein: Employer's EIN (box b), in XX-XXXXXXX format
- box1_wages: Wages, salaries, tips (box 1)
- box2_fed_withheld: Federal income tax withheld (box 2)
- box3_ss_wages: Social Security wages (box 3)
- box4_ss_withheld: Social Security tax withheld (box 4)
- box5_medicare_wages: Medicare wages and tips (box 5)
- box6_medicare_withheld: Medicare tax withheld (box 6)
- box15_state: State abbreviation (box 15)
- box16_state_wages: State wages, tips, etc. (box 16)
- box17_state_withheld: State income tax (box 17)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1099-INT": f"""You are extracting data from a US tax form 1099-INT (Interest Income).

Extract the following fields using these exact JSON keys:
- payer: Payer's name
- box1_interest: Interest income (box 1)
- box4_fed_withheld: Federal income tax withheld (box 4)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1099-DIV": f"""You are extracting data from a US tax form 1099-DIV (Dividends and Distributions).

Extract the following fields using these exact JSON keys:
- payer: Payer's name
- box1a_ordinary_dividends: Total ordinary dividends (box 1a)
- box1b_qualified_dividends: Qualified dividends (box 1b)
- box2a_capital_gain_distributions: Total capital gain distributions (box 2a)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1099-B": f"""You are extracting data from a US tax form 1099-B (Proceeds from Broker Transactions).

Extract the following fields using these exact JSON keys:
- payer: Broker's name
- short_term_proceeds: Total short-term proceeds (box 1d, short-term)
- short_term_cost_basis: Total short-term cost basis (box 1e, short-term)
- long_term_proceeds: Total long-term proceeds (box 1d, long-term)
- long_term_cost_basis: Total long-term cost basis (box 1e, long-term)

If the form shows individual transactions rather than totals, sum them by holding period (short-term vs long-term).

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1099-NEC": f"""You are extracting data from a US tax form 1099-NEC (Nonemployee Compensation).

Extract the following fields using these exact JSON keys:
- payer: Payer's name
- nec_compensation: Nonemployee compensation (box 1)
- fed_tax_withheld: Federal income tax withheld (box 4)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "1098": f"""You are extracting data from a US tax form 1098 (Mortgage Interest Statement).

Extract the following fields using these exact JSON keys:
- lender: Recipient/lender name
- box1_interest: Mortgage interest received (box 1)
- box10_property_taxes: Property taxes (box 10), if present

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",

    "K-1": f"""You are extracting data from a US tax form Schedule K-1 (Partner's or Shareholder's Share of Income).

Extract the following fields using these exact JSON keys:
- entity_name: Partnership or S-Corporation name
- entity_ein: Entity's EIN, in XX-XXXXXXX format
- entity_type: "P" for Partnership (Form 1065) or "S" for S-Corporation (Form 1120-S)
- box1_ordinary_income: Ordinary business income/loss (box 1)
- box2_rental_income: Net rental real estate income/loss (box 2)
- box4a_guaranteed_payments: Guaranteed payments for services (box 4a)
- box14a_se_earnings: Net earnings from self-employment (box 14, code A)
- box20z_section_199a_qbi: Qualified business income (box 20, code Z)

{_COMMON_RULES}
{_RESPONSE_FORMAT}""",
}

_FALLBACK_PROMPT = f"""You are extracting data from a US tax document. The exact form type is unknown.

Please:
1. Identify what type of tax form this is
2. Extract all visible numeric values and their labels
3. Use descriptive field keys (e.g., "total_income", "tax_withheld")

{_COMMON_RULES}
{_RESPONSE_FORMAT}"""


def get_prompt(form_type: str) -> str:
    """Return the extraction prompt for the given form type."""
    return _PROMPTS.get(form_type, _FALLBACK_PROMPT)
