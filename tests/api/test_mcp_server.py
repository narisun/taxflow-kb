"""Tests for the MCP tool registry builder."""
import pytest

from api.agent.mcp_server import build_tool_registry


EXPECTED_TOOLS = [
    "get_client_summary",
    "list_dependents",
    "list_documents",
    "get_document_fields",
    "get_return_draft",
    "get_return_line_detail",
    "validate_intake_vs_documents",
    "compute_tax_return",
    "run_advisory_analysis",
    "compare_prior_year",
    "run_validation_rules",
]


class TestBuildToolRegistry:
    def test_returns_registry_with_all_tools(self):
        registry = build_tool_registry()
        registered_names = {d["name"] for d in registry.tool_definitions}
        for tool in EXPECTED_TOOLS:
            assert tool in registered_names, f"Missing tool: {tool}"

    def test_tool_count(self):
        registry = build_tool_registry()
        assert len(registry.tool_definitions) == len(EXPECTED_TOOLS)

    def test_each_tool_has_handler(self):
        registry = build_tool_registry()
        for name in EXPECTED_TOOLS:
            assert name in registry._handlers, f"No handler for: {name}"

    def test_each_tool_has_description(self):
        registry = build_tool_registry()
        for defn in registry.tool_definitions:
            assert defn["description"], f"Empty description for: {defn['name']}"

    def test_each_tool_has_input_schema(self):
        registry = build_tool_registry()
        for defn in registry.tool_definitions:
            schema = defn["input_schema"]
            assert "type" in schema, f"Missing type in schema for: {defn['name']}"
            assert schema["type"] == "object"

    def test_get_document_fields_requires_doc_id(self):
        registry = build_tool_registry()
        defn = next(d for d in registry.tool_definitions if d["name"] == "get_document_fields")
        assert "doc_id" in defn["input_schema"]["properties"]
        assert "doc_id" in defn["input_schema"]["required"]

    def test_compare_prior_year_has_optional_prior_year(self):
        registry = build_tool_registry()
        defn = next(d for d in registry.tool_definitions if d["name"] == "compare_prior_year")
        assert "prior_year" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["required"] == []

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        from unittest.mock import MagicMock
        registry = build_tool_registry()
        result = await registry.execute("nonexistent_tool", {}, MagicMock())
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_fresh_instance_each_call(self):
        """Each call to build_tool_registry returns an independent instance."""
        r1 = build_tool_registry()
        r2 = build_tool_registry()
        assert r1 is not r2
