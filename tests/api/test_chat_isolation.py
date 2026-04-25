"""Chat isolation tests — prove there is no interference or context sharing
across clients, orgs, or concurrent requests.

The Anthropic SDK itself is stateless (each call sends a complete payload),
but that isolation is only as good as the code that builds the payload. These
tests pin down the guarantees by capturing what ``AgentService`` would send to
Claude and asserting client-scoped correctness.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from api.agent.service import AgentService
from api.agent.tool_registry import ToolRegistry
from api.auth.models import OrganizationModel, UserModel
from api.db.models import ChatMessageModel, ClientModel, ConversationMessageModel, ConversationModel
from api.dependencies import get_agent_service

pytestmark = pytest.mark.unit


# -------------------- helpers --------------------


@dataclass
class CapturedCall:
    system: str
    messages: list[dict]


class FakeAnthropic:
    """Stub Anthropic client — records every call for assertions.

    Returns a deterministic reply that echoes the client scope so tests can
    confirm the assistant message routed back to the correct client.
    """

    def __init__(self) -> None:
        self.calls: list[CapturedCall] = []
        self.messages = self  # mimic SDK shape: client.messages.create(...)

    def create(self, *, model, max_tokens, system, messages, tools=None):
        self.calls.append(
            CapturedCall(system=system, messages=[dict(m) for m in messages])
        )
        # Echo the last user message + a scope marker from the system prompt,
        # so a test can verify which context was used.
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        scope_line = next(
            (line for line in system.splitlines() if line.startswith("- Client:")),
            "Client: unknown",
        )
        return _Response(text=f"[{scope_line}] reply to: {last_user}")


@dataclass
class _Response:
    text: str
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"

    def __post_init__(self) -> None:
        self.content = [type("Part", (), {"text": self.text, "type": "text"})()]


async def _make_client(session, org, name, filing="single", year=2024) -> ClientModel:
    c = ClientModel(
        org_id=org.id,
        created_by=None,
        name=name,
        filing_status=filing,
        tax_year=year,
    )
    session.add(c)
    await session.flush()
    return c


async def _send_message(app, seeded_user, client_id: str, text: str, fake: FakeAnthropic):
    """Invoke the router path with an injected fake Claude client."""
    from api.auth.dependencies import get_current_user
    from api.dependencies import get_pii_encryptor_dep
    from api.services.pii.encryptor import PIIEncryptor
    from httpx import ASGITransport, AsyncClient

    # Build an AgentService bound to the fake Anthropic client, and override
    # get_agent_service so the router picks it up.
    svc = AgentService(
        anthropic_client=fake,
        model="fake-model",
        max_tokens=128,
        max_tool_rounds=1,
        history_token_budget=8000,
        tool_registry=ToolRegistry(),
    )

    async def _override_user():
        factory = app.state.test_session_factory
        async with factory() as s:
            return await s.merge(seeded_user)

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_agent_service] = lambda: svc

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            f"/api/clients/{client_id}/chat", json={"content": text}
        )
    app.dependency_overrides.pop(get_agent_service, None)
    app.dependency_overrides.pop(get_current_user, None)
    return resp


# -------------------- tests --------------------


async def test_two_clients_in_same_org_have_isolated_chat_context(app, seeded_user):
    """Chat history for Client A must never leak into Client B's prompt."""
    factory = app.state.test_session_factory
    async with factory() as session:
        org = await session.get(OrganizationModel, seeded_user.org_id)
        alice = await _make_client(session, org, "Alice")
        bob = await _make_client(session, org, "Bob")
        await session.commit()
        alice_id, bob_id = alice.id, bob.id

    fake = FakeAnthropic()

    # Populate Alice's history with a unique token that must not appear in
    # Bob's prompt.
    await _send_message(app, seeded_user, alice_id, "ALICE_SECRET_TOKEN_42", fake)

    # Now send a message to Bob.
    await _send_message(app, seeded_user, bob_id, "Bob asks something", fake)

    # Two Claude calls happened. Grab the one for Bob (most recent).
    bob_call = fake.calls[-1]
    serialized = bob_call.system + "\n".join(
        m["content"] for m in bob_call.messages
    )
    assert "ALICE_SECRET_TOKEN_42" not in serialized
    assert "Alice" not in bob_call.system  # system prompt should name Bob, not Alice
    assert "Client: Bob" in bob_call.system


async def test_client_context_is_rebuilt_per_request(app, seeded_user):
    """Updating Client A between two messages must reflect in the second prompt."""
    factory = app.state.test_session_factory
    async with factory() as session:
        org = await session.get(OrganizationModel, seeded_user.org_id)
        c = await _make_client(session, org, "Carol", filing="single")
        await session.commit()
        cid = c.id

    fake = FakeAnthropic()
    await _send_message(app, seeded_user, cid, "first", fake)

    # Mutate the client record between requests.
    async with factory() as session:
        client = await session.get(ClientModel, cid)
        client.filing_status = "mfj"
        await session.commit()

    await _send_message(app, seeded_user, cid, "second", fake)

    first, second = fake.calls[0], fake.calls[1]
    # AgentService formats as: "Client: Carol — SINGLE, TY 2024"
    assert "SINGLE" in first.system
    assert "MFJ" in second.system


async def test_chat_history_scoped_by_org(app, seeded_user):
    """Two orgs, same client name — messages in org A must not leak to org B."""
    factory = app.state.test_session_factory

    # Create a second org + user.
    async with factory() as session:
        other_org = OrganizationModel(name="Other Firm", slug="other-firm")
        session.add(other_org)
        await session.flush()
        other_user = UserModel(
            org_id=other_org.id,
            auth0_sub="auth0|other-admin",
            email="admin@other.example",
            name="Other Admin",
            role="admin",
            onboarding_status="complete",
        )
        session.add(other_user)

        # A client in each org.
        org_a = await session.get(OrganizationModel, seeded_user.org_id)
        client_a = await _make_client(session, org_a, "Shared Name")
        client_b = await _make_client(session, other_org, "Shared Name")
        await session.flush()

        # Create a conversation in org A for client_a and seed a message.
        conv_a = ConversationModel(
            client_id=client_a.id,
            user_id=seeded_user.id,
            org_id=org_a.id,
            created_by=seeded_user.id,
            conversation_type="client",
            title="Client chat",
            is_active=True,
        )
        session.add(conv_a)
        await session.flush()

        session.add(
            ConversationMessageModel(
                conversation_id=conv_a.id,
                role="user",
                content="ORG_A_SECRET",
                org_id=org_a.id,
                created_by=seeded_user.id,
            )
        )
        await session.commit()

        a_id, b_id = client_a.id, client_b.id
        other_user_fresh = (
            await session.execute(
                select(UserModel).where(UserModel.id == other_user.id)
            )
        ).scalar_one()

    fake = FakeAnthropic()

    # Send a message as the OTHER org's user to the OTHER org's client.
    await _send_message(app, other_user_fresh, b_id, "hi from other org", fake)

    call = fake.calls[-1]
    assembled = call.system + "\n".join(m["content"] for m in call.messages)
    assert "ORG_A_SECRET" not in assembled


async def test_concurrent_messages_to_different_clients_dont_cross(app, seeded_user):
    """Parallel requests to Client A and Client B must produce isolated prompts."""
    factory = app.state.test_session_factory
    async with factory() as session:
        org = await session.get(OrganizationModel, seeded_user.org_id)
        a = await _make_client(session, org, "ClientA")
        b = await _make_client(session, org, "ClientB")
        await session.flush()

        # Create conversations and seed history markers.
        conv_a = ConversationModel(
            client_id=a.id,
            user_id=seeded_user.id,
            org_id=org.id,
            created_by=seeded_user.id,
            conversation_type="client",
            title="Client chat",
            is_active=True,
        )
        conv_b = ConversationModel(
            client_id=b.id,
            user_id=seeded_user.id,
            org_id=org.id,
            created_by=seeded_user.id,
            conversation_type="client",
            title="Client chat",
            is_active=True,
        )
        session.add_all([conv_a, conv_b])
        await session.flush()

        session.add_all(
            [
                ConversationMessageModel(
                    conversation_id=conv_a.id,
                    role="assistant",
                    content="HISTORY_ONLY_FOR_A",
                    org_id=org.id,
                    created_by=seeded_user.id,
                ),
                ConversationMessageModel(
                    conversation_id=conv_b.id,
                    role="assistant",
                    content="HISTORY_ONLY_FOR_B",
                    org_id=org.id,
                    created_by=seeded_user.id,
                ),
            ]
        )
        await session.commit()
        a_id, b_id = a.id, b.id

    fake = FakeAnthropic()
    # Fire both requests concurrently.
    await asyncio.gather(
        _send_message(app, seeded_user, a_id, "Q about A", fake),
        _send_message(app, seeded_user, b_id, "Q about B", fake),
    )

    # Each call must contain only its own marker in the history.
    by_client = {}
    for call in fake.calls:
        # Determine which client the call belongs to from the system prompt.
        name_line = [
            line for line in call.system.splitlines() if line.startswith("- Client:")
        ][0]
        by_client[name_line] = call

    call_a = by_client["- Client: ClientA \u2014 SINGLE, TY 2024"]
    call_b = by_client["- Client: ClientB \u2014 SINGLE, TY 2024"]

    def _flatten(call: CapturedCall) -> str:
        return call.system + "\n".join(m["content"] for m in call.messages)

    assert "HISTORY_ONLY_FOR_A" in _flatten(call_a)
    assert "HISTORY_ONLY_FOR_A" not in _flatten(call_b)
    assert "HISTORY_ONLY_FOR_B" in _flatten(call_b)
    assert "HISTORY_ONLY_FOR_B" not in _flatten(call_a)


async def test_current_message_not_duplicated_in_prompt(app, seeded_user):
    """Regression guard: the just-sent message must appear exactly once.

    Prior to the fix, the router flushed the user message before calling the
    service, which then re-read it as 'history' AND appended it again -> the
    message appeared twice in the Claude payload.
    """
    factory = app.state.test_session_factory
    async with factory() as session:
        org = await session.get(OrganizationModel, seeded_user.org_id)
        c = await _make_client(session, org, "Dave")
        await session.commit()
        cid = c.id

    fake = FakeAnthropic()
    await _send_message(app, seeded_user, cid, "UNIQUE_QUESTION_xyz", fake)

    call = fake.calls[-1]
    question_occurrences = sum(
        1 for m in call.messages if m["content"] == "UNIQUE_QUESTION_xyz"
    )
    assert question_occurrences == 1, (
        f"Expected exactly 1 copy of the user message; saw {question_occurrences}. "
        f"Messages: {[m['content'] for m in call.messages]}"
    )
