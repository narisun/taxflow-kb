"""Tool registry — maps tool names to handlers and generates Claude tool definitions."""
from __future__ import annotations
import logging
from typing import Any, Callable
from api.agent.session import AgentSession

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable] = {}
        self._definitions: list[dict[str, Any]] = []

    def register(self, name: str, description: str, handler: Callable,
                 parameters: dict[str, Any] | None = None) -> None:
        self._handlers[name] = handler
        self._definitions.append({
            "name": name,
            "description": description,
            "input_schema": parameters or {"type": "object", "properties": {}, "required": []},
        })

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        return self._definitions

    async def execute(self, tool_name: str, tool_input: dict[str, Any],
                      session: AgentSession) -> dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return await handler(session, **tool_input)
        except Exception as exc:
            logger.exception("Tool %s failed", tool_name)
            return {"error": f"Tool {tool_name} failed: {exc}"}
