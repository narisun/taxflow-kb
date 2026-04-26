"""
taxkb.agent — CPA query agent with hierarchical retrieval and synthesis.
"""
from taxkb.agent.agent import TaxBrainAgent, AgentConfig
from taxkb.agent.models import QueryResult, RetrievedPassage
from taxkb.agent.retriever import TaxBrainRetriever
from taxkb.agent.classifier import classify_query, QueryMetadata

__all__ = [
    "TaxBrainAgent",
    "AgentConfig",
    "QueryResult",
    "RetrievedPassage",
    "TaxBrainRetriever",
    "classify_query",
    "QueryMetadata",
]
