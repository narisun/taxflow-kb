"""Tool registry for the TaxFlow agent. Registers all READ tools."""
from __future__ import annotations
from api.agent.tool_registry import ToolRegistry
from api.agent.tools import client_tools, document_tools, return_tools


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

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
        description="Get the computed tax return draft with all 1040 line items, totals, refund/owed, and effective rate.",
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

    return registry
