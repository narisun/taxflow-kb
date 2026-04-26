"""Tests for ResearchSession — frozen, no client_id, no PII."""
from unittest.mock import MagicMock
from api.agent.research_session import ResearchSession


class TestResearchSession:
    def test_creation(self):
        session = ResearchSession(
            org_id="org-1",
            user_id="user-1",
            conversation_id="conv-1",
            db_session=MagicMock(),
            taxkb_pool=MagicMock(),
        )
        assert session.org_id == "org-1"
        assert session.user_id == "user-1"
        assert session.conversation_id == "conv-1"

    def test_frozen(self):
        session = ResearchSession(
            org_id="org-1",
            user_id="user-1",
            conversation_id="conv-1",
            db_session=MagicMock(),
            taxkb_pool=MagicMock(),
        )
        import pytest
        with pytest.raises(AttributeError):
            session.org_id = "changed"
