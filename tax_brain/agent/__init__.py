"""
tax_brain.agent — CPA query agent with hierarchical retrieval and synthesis.
"""
from tax_brain.agent.agent import TaxBrainAgent, AgentConfig
from tax_brain.agent.models import QueryResult, RetrievedPassage
from tax_brain.agent.retriever import TaxBrainRetriever
from tax_brain.agent.classifier import classify_query, QueryMetadata

__all__ = [
    "TaxBrainAgent",
    "AgentConfig",
    "QueryResult",
    "RetrievedPassage",
    "TaxBrainRetriever",
    "classify_query",
    "QueryMetadata",
]
