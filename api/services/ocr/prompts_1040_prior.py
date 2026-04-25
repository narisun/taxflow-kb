"""Extraction prompt for prior-year Form 1040 (filed returns)."""

PROMPT_1040_PRIOR = """Extract the following fields from this IRS Form 1040 tax return.
Return a JSON object with these exact keys. Use numeric values (no $ or commas).
If a field is blank or not present, use null.

{
  "tax_year": <4-digit year from the form header>,
  "filing_status": <"S", "MFJ", "MFS", "HOH", or "QSS">,
  "line_1a": <Line 1a - Wages, salaries, tips>,
  "line_2b": <Line 2b - Taxable interest>,
  "line_3b": <Line 3b - Qualified dividends>,
  "line_7": <Line 7 - Capital gain or loss>,
  "line_8": <Line 8 - Other income>,
  "line_9": <Line 9 - Total income>,
  "line_12": <Line 12 - Standard or itemized deduction>,
  "line_13a": <Line 13a - Qualified business income deduction>,
  "line_15": <Line 15 - Taxable income>,
  "line_16": <Line 16 - Tax>,
  "line_24": <Line 24 - Total tax>,
  "line_25a": <Line 25a - Federal tax withheld from W-2>,
  "line_25b": <Line 25b - Federal tax withheld from 1099>,
  "line_25c": <Line 25c - Other withholding>,
  "line_26": <Line 26 - Estimated tax payments>,
  "line_33": <Line 33 - Total payments>,
  "line_35a": <Line 35a - Refund amount>,
  "line_37": <Line 37 - Amount you owe>
}

Return ONLY the JSON object. No markdown, no explanation."""
