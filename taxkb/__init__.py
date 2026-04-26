"""
Tax Brain — AI-Powered IRS Knowledge Base for CPAs.

Public API:
    from taxkb import TaxBrainAgent, QueryResult, create_agent
"""
from taxkb.agent.agent import TaxBrainAgent, AgentConfig
from taxkb.agent.models import QueryResult, RetrievedPassage
from taxkb.factories import create_agent

__all__ = [
    "TaxBrainAgent",
    "AgentConfig",
    "QueryResult",
    "RetrievedPassage",
    "create_agent",
]
