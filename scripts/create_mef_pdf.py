#!/usr/bin/env python3
"""
Generate a synthetic IRS MeF Business Rules publication PDF.

This creates a structured document covering common Form 1040 MeF rejection
codes and business rules, suitable for ingestion into the Tax Brain knowledge
base via the standard PDF parsing pipeline.
"""
from fpdf import FPDF


class MeFPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, "IRS Modernized e-File (MeF) Business Rules -- Form 1040 Series", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"MeF Business Rule Crosswalk  --  Page {self.page_no()}", align="C")

    def chapter_heading(self, title):
        self.set_font("Helvetica", "B", 14)
        self.ln(4)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def section_heading(self, title):
        self.set_font("Helvetica", "B", 11)
        self.ln(2)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5, text)
        self.ln(2)

    def rule_block(self, rule_id, rule_text, explanation, resolution):
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 6, f"Business Rule: {rule_id}", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5, f"Rule Text: {rule_text}")
        self.ln(1)
        self.multi_cell(0, 5, f"Explanation: {explanation}")
        self.ln(1)
        self.multi_cell(0, 5, f"Resolution: {resolution}")
        self.ln(4)


def build_pdf(output_path: str):
    pdf = MeFPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ── Title Page ──────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 20)
    pdf.ln(30)
    pdf.cell(0, 12, "IRS Modernized e-File (MeF)", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 12, "Business Rule Crosswalk", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 14)
    pdf.cell(0, 10, "Form 1040 Series -- Tax Year 2025", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, (
        "This document provides the complete crosswalk of MeF business rules "
        "for the Form 1040 series. Each business rule defines a validation condition "
        "that the IRS Modernized e-File system checks when processing electronically "
        "filed returns. When a rule is violated, the return is rejected with the "
        "corresponding error reject code.\n\n"
        "Tax professionals and CPAs should reference this crosswalk when diagnosing "
        "e-file rejections. Each rule entry includes the rule number, rule text, "
        "plain-language explanation, and suggested resolution steps."
    ))

    # ── Chapter 1: Overview ─────────────────────────────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 1. MeF System Overview")

    pdf.body_text(
        "The Modernized e-File (MeF) system is the IRS platform for receiving "
        "electronically filed tax returns. MeF performs real-time validation of "
        "returns against a comprehensive set of business rules before accepting "
        "them for processing. Returns that violate one or more business rules are "
        "rejected and must be corrected and resubmitted."
    )

    pdf.section_heading("How MeF Validation Works")
    pdf.body_text(
        "When a return is transmitted to MeF, the system performs schema validation "
        "(ensuring the XML structure is correct) and then applies business rules "
        "(logical validation of the data). Business rules check mathematical "
        "relationships between fields, required attachments, cross-references to "
        "IRS master file data, and compliance with tax law provisions. Each business "
        "rule has a unique identifier (e.g., F1040-001) and a rule text that "
        "describes the condition being checked."
    )

    pdf.section_heading("Rejection Process")
    pdf.body_text(
        "When a return fails validation, MeF returns an acknowledgement with "
        "the rejection code(s). The tax preparer or software must correct the "
        "errors and retransmit the return. Common categories of rejections include: "
        "math errors (fields that don't add up correctly), missing forms or schedules, "
        "data mismatches with IRS records (SSN, EIN, name), and logical inconsistencies "
        "between related fields."
    )

    pdf.section_heading("Error Reject Codes vs Business Rules")
    pdf.body_text(
        "Each MeF business rule maps to an Error Reject Code (ERC) used by legacy "
        "Electronic Filing (ELF) systems. The crosswalk between ERCs and MeF business "
        "rule numbers allows practitioners to look up rejections regardless of which "
        "identifier their software reports."
    )

    # ── Chapter 2: Form 1040 Amount / Math Rules ────────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 2. Form 1040 Amount and Math Validation Rules")

    pdf.body_text(
        "These rules validate the mathematical relationships between key fields "
        "on Form 1040, including total income, adjusted gross income, tax liability, "
        "payments, overpayment, amount owed, and estimated tax penalty amounts."
    )

    # F1040-001
    pdf.rule_block(
        "F1040-001",
        "If Form 1040, 'OverpaidAmt' (Line 34) has a non-zero value and "
        "'EsPenaltyAmt' (Line 38) is greater than 'OverpaidAmt' (Line 34), "
        "then 'AmountOwedAmt' (Line 37) must have a non-zero value.",
        "This error occurs when the Estimated Tax Penalty on Line 38 exceeds the "
        "Overpayment on Line 34, but the return does not show a Balance Due on "
        "Line 37. The logic requires that when the penalty is larger than the "
        "overpayment, the taxpayer must owe money (Amount Owed must be significant). "
        "This typically happens when the estimated tax penalty amount was not properly "
        "netted against the overpayment to compute the balance due.",
        "Verify that Line 37 (Amount Owed) reflects the correct balance after "
        "netting the overpayment against the estimated tax penalty. If the estimated "
        "tax penalty (Line 38) is greater than the overpayment (Line 34), calculate "
        "the amount owed as: Penalty - Overpayment = Amount Owed, and enter this "
        "on Line 37. Recalculate and retransmit the return."
    )

    # F1040-002
    pdf.rule_block(
        "F1040-002",
        "If Form 1040, 'OverpaidAmt' (Line 34) has a non-zero value and "
        "'EsPenaltyAmt' (Line 38) is less than or equal to 'OverpaidAmt' (Line 34), "
        "then 'AmountOwedAmt' (Line 37) must be zero or not present.",
        "This is the companion rule to F1040-001. When the overpayment exceeds or "
        "equals the estimated tax penalty, there should be no amount owed because the "
        "overpayment covers the penalty. Having both an overpayment and an amount owed "
        "in this scenario is a mathematical inconsistency.",
        "Remove the Amount Owed value from Line 37. The overpayment on Line 34 is "
        "sufficient to cover the penalty on Line 38, so no balance due should exist. "
        "The net refund is: Overpayment - Penalty = Refund Amount."
    )

    # F1040-003 through F1040-005
    pdf.rule_block(
        "F1040-003",
        "If 'TotalPaymentsAmt' (Line 33) is less than 'TotalTaxAmt' (Line 24), "
        "then 'OverpaidAmt' (Line 34) must be zero or not present.",
        "When total payments are less than total tax, the taxpayer owes money and "
        "cannot have an overpayment. The return shows inconsistent math between the "
        "payment, tax, and overpayment lines.",
        "Verify Lines 24 and 33 are correct. If payments are genuinely less than "
        "tax, remove the overpayment amount and enter the difference as Amount Owed "
        "on Line 37."
    )

    pdf.rule_block(
        "F1040-004",
        "If 'TotalPaymentsAmt' (Line 33) is greater than or equal to 'TotalTaxAmt' "
        "(Line 24), then 'AmountOwedAmt' (Line 37) must be zero or not present.",
        "When total payments meet or exceed total tax, there is no balance due. "
        "Having an amount owed when payments cover or exceed the tax is a math error.",
        "Remove the Amount Owed from Line 37 and ensure the overpayment on Line 34 "
        "equals the difference: Total Payments - Total Tax = Overpayment."
    )

    pdf.rule_block(
        "F1040-005",
        "'TotalTaxAmt' (Line 24) must equal the sum of all tax components on "
        "Lines 16 through 23.",
        "The total tax line must be the correct sum of all individual tax components "
        "including income tax, AMT, excess premium tax credit repayment, self-employment "
        "tax, unreported Social Security/Medicare tax, and additional taxes.",
        "Recalculate Line 24 as the sum of Lines 16 through 23. Verify each component "
        "is correctly computed and that the sum matches."
    )

    # ── Chapter 3: Identity Validation Rules ────────────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 3. Identity and Filing Status Validation Rules")

    pdf.body_text(
        "These rules validate taxpayer identity information against IRS master "
        "file records. SSN/ITIN mismatches, name discrepancies, and date of birth "
        "errors are among the most common causes of MeF rejections."
    )

    pdf.rule_block(
        "F1040-034",
        "'PrimarySSN' must match IRS records for the primary taxpayer.",
        "The Social Security Number entered for the primary taxpayer does not match "
        "IRS records. This can occur when a digit is transposed, a former SSN is used, "
        "or when an ITIN is entered instead of an SSN.",
        "Verify the primary taxpayer's SSN against their Social Security card. If the "
        "taxpayer recently obtained a new SSN, they may need to contact the SSA to "
        "update records. Correct the SSN and retransmit."
    )

    pdf.rule_block(
        "F1040-035",
        "'SpouseSSN' must match IRS records for the spouse on a joint return.",
        "Similar to F1040-034 but for the spouse's SSN on a Married Filing Jointly "
        "return. The spouse's SSN does not match IRS master file records.",
        "Verify the spouse's SSN against their Social Security card. Correct and "
        "retransmit. If recently married with a name change, ensure the SSA has "
        "been notified of the name change."
    )

    pdf.rule_block(
        "F1040-036",
        "'PrimaryNameControlTxt' must match the IRS master file for the SSN provided.",
        "The name control (derived from the last name) does not match what the IRS "
        "has on file for the SSN. This commonly occurs after a name change (marriage, "
        "divorce) when the SSA records have not been updated.",
        "Check that the last name on the return matches the taxpayer's Social Security "
        "card exactly. If a name change occurred, the taxpayer should update their "
        "name with SSA using Form SS-5 before refiling."
    )

    pdf.rule_block(
        "F1040-071",
        "If filing status is Married Filing Jointly, then 'SpouseSSN' must be present.",
        "A joint return requires both the primary taxpayer's and spouse's SSNs. The "
        "spouse's SSN is missing from a return filed with MFJ status.",
        "Enter the spouse's SSN. If the spouse does not have an SSN, apply for an "
        "ITIN using Form W-7, or change the filing status."
    )

    # ── Chapter 4: Required Forms and Schedules ─────────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 4. Required Forms and Schedules Rules")

    pdf.body_text(
        "These rules ensure that required forms and schedules are attached when "
        "specific items are claimed on the return. Missing required attachments "
        "are a frequent source of MeF rejections."
    )

    pdf.rule_block(
        "F8962-070",
        "If the IRS Marketplace data indicates the taxpayer, spouse, or dependent "
        "received advance Premium Tax Credit (APTC), then Form 8962 must be attached.",
        "The IRS Master File shows that advance Premium Tax Credits were paid for "
        "health insurance obtained through the ACA Marketplace. Form 8962 (Premium "
        "Tax Credit) must be filed to reconcile the advance credit, even if the "
        "taxpayer did not receive Form 1095-A or believes they did not receive a subsidy. "
        "This is the marketplace data validation rule.",
        "Obtain Form 1095-A from the Marketplace and complete Form 8962 to reconcile "
        "the advance Premium Tax Credit. Attach Form 8962 to the return. If the "
        "taxpayer believes they did not receive APTC, they may attach a PDF statement "
        "with the heading 'ACA Explanation' explaining why Form 8962 is not required."
    )

    pdf.rule_block(
        "F1040-037",
        "If Schedule C income is present, then Schedule SE must be attached when "
        "net self-employment earnings exceed $400.",
        "Self-employment income from Schedule C that exceeds $400 requires "
        "computation and reporting of self-employment tax on Schedule SE. The "
        "schedule is missing from the return.",
        "Attach Schedule SE computing the self-employment tax based on the net "
        "earnings from Schedule C. Ensure the SE tax flows to the appropriate "
        "line on Form 1040."
    )

    pdf.rule_block(
        "F1040-162",
        "If Form 1040 includes 'EducationCreditAmt', then Form 8863 must be attached.",
        "An education credit (American Opportunity or Lifetime Learning) is claimed "
        "on the return but Form 8863 is not attached. Form 8863 is required to "
        "compute and support education credit claims.",
        "Complete Form 8863 with the student's information, qualified expenses, and "
        "educational institution EIN. Attach it to the return."
    )

    pdf.rule_block(
        "F1040-164",
        "If Form 1040 includes 'ChildTaxCreditAmt' and the amount exceeds the "
        "standard threshold, then Schedule 8812 must be attached.",
        "The Child Tax Credit claimed requires Schedule 8812 (Credits for Qualifying "
        "Children and Other Dependents) to support the computation. The schedule is "
        "missing or incomplete.",
        "Complete Schedule 8812 and attach it to the return. Ensure qualifying "
        "children have valid SSNs and meet all eligibility requirements."
    )

    # ── Chapter 5: OBBBA-Related MeF Validation Rules ──────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 5. OBBBA-Related MeF Validation Rules (Tax Year 2025+)")

    pdf.body_text(
        "The One Big Beautiful Bill Act (OBBBA) introduced several new provisions "
        "effective for tax year 2025 and later that require new MeF validation rules. "
        "These rules apply to the tips and overtime deduction (Schedule 1-A), the "
        "senior deduction, the vehicle interest deduction, and the Trump Account "
        "(Form 4547)."
    )

    pdf.section_heading("Schedule 1-A (Tips and Overtime Deduction)")

    pdf.rule_block(
        "F1040S1A-001",
        "If Schedule 1-A is attached, then 'QualifiedTipsAmt' plus "
        "'QualifiedOvertimeAmt' must not exceed 'TotalIncomeAmt' on Form 1040.",
        "The combined tips and overtime deduction on Schedule 1-A cannot exceed the "
        "taxpayer's total reported income. MeF validates that the deduction does not "
        "create a negative income situation.",
        "Verify that the qualified tips and overtime amounts on Schedule 1-A do not "
        "exceed total income. Reduce the deduction amounts if necessary."
    )

    pdf.rule_block(
        "F1040S1A-002",
        "If 'QualifiedTipsAmt' is claimed on Schedule 1-A, then W-2 reporting "
        "must include tip income. Code 'TP' on W-2 Box 12 indicates separately "
        "reported qualified tips.",
        "The tips deduction requires that tip income was reported on the taxpayer's "
        "W-2. While Code TP on the W-2 is the standard reporting method, the "
        "deduction can still be claimed without Code TP if the taxpayer provides "
        "documentation of tips received. The employer may face penalties for not "
        "using Code TP.",
        "Verify W-2 tip reporting. If Code TP is missing, the taxpayer should "
        "provide alternative documentation of tips received (daily tip log, "
        "employer allocation records). The employer may need to issue a corrected W-2."
    )

    pdf.section_heading("Senior Deduction")

    pdf.rule_block(
        "F1040-SENIOR-001",
        "If 'SeniorDeductionAmt' is claimed, the primary taxpayer's date of birth "
        "must indicate age 65 or older as of the end of the tax year.",
        "The OBBBA senior deduction requires the taxpayer to be age 65 or older. "
        "MeF validates the taxpayer's birth date from IRS records against this "
        "requirement. If the taxpayer is under 65, the deduction is rejected.",
        "Verify the taxpayer's date of birth on the return matches IRS records. "
        "If the taxpayer turned 65 during the tax year, they qualify. If under 65, "
        "remove the senior deduction."
    )

    pdf.rule_block(
        "F1040-SENIOR-002",
        "If 'SeniorDeductionAmt' is claimed, the taxpayer must have a Social "
        "Security Number (SSN) valid for work. ITINs are not eligible.",
        "The OBBBA senior deduction requires an SSN valid for employment, not an "
        "ITIN. ITIN holders are ineligible for the senior deduction even if they "
        "meet the age requirement. The system verifies SSN validity.",
        "If the taxpayer has an ITIN, they cannot claim the senior deduction. "
        "Remove the deduction. If the taxpayer is eligible for an SSN, they should "
        "apply through SSA before claiming the deduction."
    )

    pdf.rule_block(
        "F1040-SENIOR-003",
        "For Married Filing Separately, 'SeniorDeductionAmt' is calculated "
        "independently for each spouse based on individual age and income.",
        "On MFS returns, each spouse is evaluated separately for the senior "
        "deduction. The lower-income spouse can claim up to $6,000 if over 65, "
        "regardless of the other spouse's income level.",
        "Calculate the senior deduction for each spouse independently. Verify "
        "each spouse's age and income thresholds separately."
    )

    pdf.section_heading("Vehicle Interest Deduction")

    pdf.rule_block(
        "F1040-VEHICLE-001",
        "If 'VehicleInterestDeductionAmt' is claimed, documentation of U.S. "
        "vehicle assembly must be provided.",
        "The OBBBA vehicle interest deduction applies only to vehicles assembled "
        "in the United States. MeF may validate the assembly location and reject "
        "the deduction for foreign-assembled vehicles. The deduction is limited to "
        "$10,000 per year for auto loan interest on U.S.-assembled vehicles.",
        "Provide documentation of U.S. assembly (vehicle sticker, manufacturer "
        "certification). Verify the vehicle qualifies under the American-made "
        "requirement. Ensure the deduction does not exceed the $10,000 annual limit."
    )

    pdf.section_heading("Trump Account (Form 4547)")

    pdf.rule_block(
        "F4547-001",
        "If Form 4547 is attached, the child's SSN must be valid and the child "
        "must be under age 18 or a newborn.",
        "The Trump Account (MAGA Account) requires a valid SSN for the child. "
        "Form 4547 establishes the tax-free savings account with the $1,000 federal "
        "seed money. The child must meet age requirements.",
        "Verify the child's SSN and date of birth. Ensure the child is eligible "
        "for a Trump Account under OBBBA provisions."
    )

    pdf.rule_block(
        "F4547-002",
        "Contributions to a Trump Account cannot exceed $5,000 per year per child. "
        "Employer contributions reported on W-2 Box 12 count toward this limit.",
        "Total contributions including employer contributions (reported as a fringe "
        "benefit on W-2 Box 12) must not exceed the $5,000 annual limit. The $1,000 "
        "federal seed does not count toward this limit.",
        "Verify total contributions (personal + employer) do not exceed $5,000. "
        "Check W-2 Box 12 for employer contribution amounts. Reduce personal "
        "contribution if the combined total exceeds the limit."
    )

    # ── Chapter 6: Dependent and Credit Validation ──────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 6. Dependent and Credit Validation Rules")

    pdf.body_text(
        "These rules validate dependent claims, earned income credit eligibility, "
        "child tax credit computations, and other credit-related requirements."
    )

    pdf.rule_block(
        "F1040-038",
        "'DependentSSN' must match IRS records and must not be claimed on another "
        "return for the same tax year.",
        "A dependent's SSN has already been claimed on another return filed for the "
        "same tax year, or the SSN does not match IRS records. Only one return can "
        "claim a dependent's SSN.",
        "Verify the dependent's SSN. If another taxpayer has already claimed the "
        "dependent, determine who has the right to claim them based on IRS tiebreaker "
        "rules (custodial parent, higher AGI). The other return may need to be amended."
    )

    pdf.rule_block(
        "F1040-EIC-001",
        "If Earned Income Credit is claimed, 'EarnedIncomeAmt' must not exceed "
        "the AGI threshold for the taxpayer's filing status and number of qualifying children.",
        "The Earned Income Credit has AGI phase-out limits. If AGI exceeds the "
        "threshold, the credit must be reduced or eliminated. MeF validates the "
        "income against the applicable limit.",
        "Verify AGI against EIC income limits for the tax year. Recalculate the "
        "credit using the EIC worksheet or IRS tables."
    )

    # ── Chapter 7: Business Income and QBI Rules ────────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 7. Business Income and QBI Validation Rules")

    pdf.body_text(
        "These rules validate business income reporting, Qualified Business Income "
        "(QBI) deduction calculations, and self-employment tax computations."
    )

    pdf.rule_block(
        "F8995A-001",
        "If 'QBIDeductionAmt' is claimed, 'QualifiedBusinessIncomeAmt' must be "
        "a positive number.",
        "The Section 199A QBI deduction requires positive Qualified Business Income. "
        "If the business shows a net loss, QBI is negative and no QBI deduction is "
        "available for that tax year. The loss carries forward under QBI loss carryover rules.",
        "If business income is negative, remove the QBI deduction. The negative QBI "
        "carries forward to the next tax year to offset future QBI."
    )

    pdf.rule_block(
        "F1040-SE-001",
        "If 'SelfEmploymentTaxAmt' is reported, it must be computed using the "
        "standard rate of 15.3% on net self-employment earnings (12.4% Social "
        "Security + 2.9% Medicare).",
        "MeF does not perform detailed validation of SE tax calculations. The system "
        "trusts taxpayer-provided amounts. However, errors in SE tax computation may "
        "be caught in subsequent IRS processing or random audits.",
        "Use Schedule SE to correctly compute self-employment tax. Verify the net "
        "earnings from self-employment and apply the correct rates."
    )

    # ── Chapter 8: SALT and Itemized Deduction Rules ────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 8. SALT and Itemized Deduction Validation Rules")

    pdf.body_text(
        "The OBBBA modified the State and Local Tax (SALT) deduction cap for tax "
        "year 2025 and beyond. MeF validation rules enforce the new limits."
    )

    pdf.rule_block(
        "FSCHEDA-SALT-001",
        "If Schedule A is attached, 'StateAndLocalTaxAmt' must not exceed the "
        "applicable SALT cap based on filing status and income.",
        "The OBBBA raised the SALT deduction cap to $40,000 for taxpayers with "
        "income under $500,000. MeF validation checks that the claimed SALT "
        "deduction does not exceed this cap. Taxpayers must calculate and self-limit "
        "the SALT deduction on Schedule A.",
        "Verify the SALT deduction does not exceed the applicable cap. For income "
        "under $500,000, the cap is $40,000. Calculate the actual state and local "
        "taxes paid and apply the limitation."
    )

    # ── Chapter 9: Duplicate Claim Prevention ───────────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 9. Duplicate Claim Prevention Rules")

    pdf.body_text(
        "These rules prevent taxpayers from claiming the same deduction or credit "
        "in multiple places on the return."
    )

    pdf.rule_block(
        "F1040-DUP-VEHICLE-001",
        "Vehicle interest deduction can only be claimed once as an above-the-line "
        "deduction on Schedule 1-A. It cannot also be claimed as an itemized "
        "deduction on Schedule A.",
        "MeF checks for duplicate vehicle interest claims. If the deduction appears "
        "both on Schedule 1-A (above-the-line) and Schedule A (itemized), the return "
        "is rejected. The deduction is only allowed as an above-the-line deduction.",
        "Remove the vehicle interest from Schedule A if it is already claimed on "
        "Schedule 1-A. The above-the-line treatment on Schedule 1-A is more "
        "beneficial as it reduces AGI."
    )

    pdf.rule_block(
        "F4547-DUP-001",
        "Trump Account contributions and traditional IRA contributions are separate "
        "and do not conflict. Both can be claimed in the same tax year for the same child.",
        "There is no validation conflict between Trump Account contributions ($5,000 "
        "annual limit) and IRA contributions ($7,000 or $8,000 for age 50+). These "
        "are independent contribution limits under different code sections.",
        "No action needed. Both contributions are independently valid."
    )

    # ── Chapter 10: Glossary ────────────────────────────────────────────
    pdf.add_page()
    pdf.chapter_heading("Chapter 10. Glossary of MeF Terms")

    terms = [
        ("MeF", "Modernized e-File -- the IRS electronic filing system that validates and processes tax returns submitted electronically."),
        ("Business Rule", "A logical validation condition that MeF checks. Each rule has a unique identifier and defines what data relationships must hold for a return to be accepted."),
        ("Error Reject Code (ERC)", "A code returned when a return fails MeF validation. The ERC identifies which business rule was violated."),
        ("Schema Validation", "The first stage of MeF processing that checks the XML structure of the return against the published schema definitions."),
        ("Acknowledgement", "The response from MeF after processing a return. An acceptance acknowledgement means the return passed all validations. A rejection acknowledgement lists the violated business rules."),
        ("Master File", "The IRS database containing taxpayer information including SSNs, filing history, and third-party data (W-2s, 1095-As, etc.)."),
        ("APTC", "Advance Premium Tax Credit -- payments made by the government to health insurance Marketplaces on behalf of taxpayers who enrolled in coverage under the Affordable Care Act."),
        ("OBBBA", "One Big Beautiful Bill Act -- legislation effective 2025+ that introduced new tax provisions including tips/overtime deduction, senior deduction, vehicle interest deduction, SALT cap increase, and Trump Accounts."),
        ("Schedule 1-A", "The new schedule introduced by OBBBA for claiming the above-the-line deduction for qualified tips and qualified overtime pay."),
        ("Trump Account", "Also called MAGA Account or Newborn Savings Account. A tax-advantaged savings account for children under 18, established by OBBBA, funded with a $1,000 federal seed and up to $5,000 annual contributions."),
        ("Code TP", "A new W-2 Box 12 code for reporting qualified tips separately. Required for employers of tipped employees starting tax year 2025."),
    ]

    for term, definition in terms:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, term, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, definition)
        pdf.ln(2)

    pdf.output(output_path)
    print(f"Created MeF PDF: {output_path}")
    return output_path


if __name__ == "__main__":
    build_pdf("pMeF_2025.pdf")
