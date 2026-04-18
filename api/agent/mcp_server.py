"""Tool registry for the TaxFlow agent. Registers all tools."""
from __future__ import annotations
from api.agent.tool_registry import ToolRegistry
from api.agent.tools import client_tools, document_tools, return_tools, tax_tools


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    # ── Existing READ tools ───────────────────────────────────────────────
    registry.register(
        name="get_client_summary",
        description="Get the current client's profile including name, filing status, tax year, dependents, workflow step, contact info, and masked PII (SSN, DOB, address).",
        handler=client_tools.get_client_summary,
    )
    registry.register(
        name="list_dependents",
        description="List all dependents claimed for the current client with masked SSN/DOB.",
        handler=client_tools.list_dependents,
    )
    registry.register(
        name="list_documents",
        description="List all uploaded tax documents for the current client with form type, status, confidence, and upload/review audit trail.",
        handler=document_tools.list_documents,
    )
    registry.register(
        name="get_document_fields",
        description="Get extracted field values from a specific document. Use after list_documents to drill into a W-2, 1099, etc. SSN values are masked.",
        handler=document_tools.get_document_fields,
        parameters={
            "type": "object",
            "properties": {"doc_id": {"type": "string", "description": "Document ID from list_documents"}},
            "required": ["doc_id"],
        },
    )
    registry.register(
        name="get_return_draft",
        description="Get the computed tax return draft with all 1040 line items, totals, refund/owed, and effective rate. Returns not_computed status if no draft exists yet.",
        handler=return_tools.get_return_draft,
    )
    registry.register(
        name="get_return_line_detail",
        description="Get breakdown of which documents contribute to a specific 1040 line number (e.g., '1a' for wages, '2b' for interest).",
        handler=return_tools.get_return_line_detail,
        parameters={
            "type": "object",
            "properties": {"line_number": {"type": "string", "description": "1040 line number (e.g., '1a', '2b', '25a')"}},
            "required": ["line_number"],
        },
    )

    # ── Tax computation & analysis tools ──────────────────────────────────
    registry.register(
        name="validate_intake_vs_documents",
        description=(
            "Cross-check the client's intake form data against their uploaded documents "
            "to catch mismatches. Compares SSN, name, address, and state between the intake "
            "record and extracted document fields. Use for 'Run validations' to verify "
            "documents belong to the right client."
        ),
        handler=tax_tools.validate_intake_vs_documents,
    )
    registry.register(
        name="compute_tax_return",
        description=(
            "Run the full tax computation for the current client. Assembles all approved "
            "documents, computes 1040 lines, calculates refund or amount owed, and saves "
            "the draft. Use when the user asks to compute the return or estimate their refund."
        ),
        handler=tax_tools.compute_tax_return,
    )
    registry.register(
        name="run_advisory_analysis",
        description=(
            "Run 12 tax-saving advisory rules and return recommendations sorted by "
            "estimated dollar savings. Includes HSA, 401(k), Roth conversion, charitable "
            "bunching, education credits, and more. Use for 'Draft advisory'."
        ),
        handler=tax_tools.run_advisory_analysis,
    )
    registry.register(
        name="compare_prior_year",
        description=(
            "Compare the current year tax return to a prior year line by line. "
            "Shows changes in income, deductions, tax, and payments with percentage deltas. "
            "Use for 'Analyze yoy'. Defaults to comparing with the previous year."
        ),
        handler=tax_tools.compare_prior_year,
        parameters={
            "type": "object",
            "properties": {
                "prior_year": {"type": "integer", "description": "Prior year to compare against. Defaults to tax_year - 1."},
            },
            "required": [],
        },
    )
    registry.register(
        name="run_validation_rules",
        description=(
            "Run structural validation rules on the tax return: MFJ spouse check, SSN format, "
            "withholding vs income, HOH dependent requirement, duplicate SSN, and more. "
            "Returns pass/fail results with severity (ERROR/WARNING/INFO)."
        ),
        handler=tax_tools.run_validation_rules,
    )

    return registry
