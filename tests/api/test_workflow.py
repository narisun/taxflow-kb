"""Tests for the workflow step management service."""
import pytest

from api.services.workflow import (
    STEPS,
    can_complete_step,
    mark_step_complete,
    mark_step_incomplete,
    get_workflow_status,
    _step_index,
    _build_step_status,
)


# ── Pure function tests (no DB) ──────────────────────────────────────────────


class TestStepIndex:
    def test_valid_steps(self):
        assert _step_index("intake") == 0
        assert _step_index("documents") == 1
        assert _step_index("tax_return") == 2
        assert _step_index("filed") == 3

    def test_invalid_step_returns_zero(self):
        assert _step_index("bogus") == 0


class TestCanCompleteStep:
    def test_intake_always_completable(self):
        assert can_complete_step("intake", has_documents=False, has_return_draft=False, current_step="intake")

    def test_documents_requires_documents(self):
        assert not can_complete_step("documents", has_documents=False, has_return_draft=False, current_step="intake")

    def test_documents_completable_with_docs(self):
        assert can_complete_step("documents", has_documents=True, has_return_draft=False, current_step="intake")

    def test_tax_return_requires_draft(self):
        assert not can_complete_step("tax_return", has_documents=True, has_return_draft=False, current_step="documents")

    def test_tax_return_completable_with_draft(self):
        assert can_complete_step("tax_return", has_documents=True, has_return_draft=True, current_step="documents")

    def test_cannot_skip_steps(self):
        assert not can_complete_step("tax_return", has_documents=True, has_return_draft=True, current_step="intake")

    def test_filed_requires_tax_return_complete(self):
        assert not can_complete_step("filed", has_documents=True, has_return_draft=True, current_step="documents")
        assert can_complete_step("filed", has_documents=True, has_return_draft=True, current_step="tax_return")


class TestBuildStepStatus:
    def test_intake_step(self):
        steps = _build_step_status("intake")
        assert len(steps) == 4
        assert steps[0] == {"id": "intake", "label": "Intake", "complete": True}
        assert steps[1] == {"id": "documents", "label": "Documents", "complete": False}

    def test_documents_step(self):
        steps = _build_step_status("documents")
        assert steps[0]["complete"] is True
        assert steps[1]["complete"] is True
        assert steps[2]["complete"] is False

    def test_filed_step(self):
        steps = _build_step_status("filed")
        assert all(s["complete"] for s in steps)


# ── Async tests (require DB) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_invalid_step(authenticated_client, app):
    """mark_step_complete with bogus step returns error dict."""
    session_factory = app.state.test_session_factory
    async with session_factory() as session:
        result = await mark_step_complete(session, "nonexistent-id", "org-1", "bogus")
        assert "error" in result


@pytest.mark.asyncio
async def test_mark_step_client_not_found(authenticated_client, app):
    """mark_step_complete with nonexistent client returns error."""
    session_factory = app.state.test_session_factory
    async with session_factory() as session:
        result = await mark_step_complete(session, "no-such-id", "org-1", "documents")
        assert result == {"error": "Client not found"}


@pytest.mark.asyncio
async def test_mark_incomplete_intake_rejected(authenticated_client, app):
    """Cannot unmark intake — it's always the baseline."""
    session_factory = app.state.test_session_factory
    async with session_factory() as session:
        result = await mark_step_incomplete(session, "any-id", "org-1", "intake")
        assert "error" in result
