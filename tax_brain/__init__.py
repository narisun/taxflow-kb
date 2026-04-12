"""
Tax Brain — AI-Powered IRS Knowledge Base for CPAs.

Public API:
    from tax_brain import TaxBrainAgent, QueryResult, create_agent
"""
from tax_brain.agent.agent import TaxBrainAgent, AgentConfig
from tax_brain.agent.models import QueryResult, RetrievedPassage
from tax_brain.factories import create_agent

__all__ = [
    "TaxBrainAgent",
    "AgentConfig",
    "QueryResult",
    "RetrievedPassage",
    "create_agent",
]
