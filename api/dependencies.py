"""FastAPI dependency providers.

Single place where process-wide collaborators are constructed. Tests override
these through ``app.dependency_overrides`` rather than patching module-level
globals.

Only infrastructure/adapter dependencies live here. Per-request dependencies
(current user, DB session) stay in their own modules to keep the import graph
clean.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from api.config import Settings, get_settings
from api.services.ocr.factory import OCRExtractorFactory
from api.services.ocr.protocol import OCRExtractor
from api.services.pii.encryptor import PIIEncryptor, build_pii_encryptor

import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import anthropic


SettingsDep = Annotated[Settings, Depends(get_settings)]


@lru_cache(maxsize=1)
def _cached_anthropic_client(api_key: str) -> "anthropic.Anthropic":
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def get_anthropic_client(
    settings: SettingsDep,
) -> "anthropic.Anthropic | None":
    """Return a cached Anthropic client, or ``None`` if no key is configured.

    The client is cached by api_key so repeated requests do not open new HTTP
    pools. Returning ``None`` (rather than raising) lets tests and offline dev
    environments run without Claude credentials — downstream services degrade
    gracefully.
    """
    key = settings.anthropic_api_key.get_secret_value()
    if not key:
        return None
    return _cached_anthropic_client(key)


AnthropicClientDep = Annotated[
    "anthropic.Anthropic | None", Depends(get_anthropic_client)
]


@lru_cache(maxsize=1)
def _cached_encryptor(key: str | None, is_production: bool) -> PIIEncryptor:
    return build_pii_encryptor(key=key, is_production=is_production)


def get_pii_encryptor_dep(settings: SettingsDep) -> PIIEncryptor:
    """DI-friendly accessor for :class:`PIIEncryptor`."""
    return _cached_encryptor(
        settings.pii_encryption_key.get_secret_value(),
        settings.is_production,
    )


PIIEncryptorDep = Annotated[PIIEncryptor, Depends(get_pii_encryptor_dep)]


def get_ocr_extractor(
    settings: SettingsDep,
    anthropic_client: AnthropicClientDep,
) -> OCRExtractor:
    """Construct a per-request OCR extractor.

    The factory itself is stateless, so constructing it per-request is cheap.
    """
    factory = OCRExtractorFactory(
        mode=settings.ocr_extractor,
        anthropic_client=anthropic_client,
    )
    return factory.build()


OCRExtractorDep = Annotated[OCRExtractor, Depends(get_ocr_extractor)]


# --- Higher-level services (lazy imports avoid circular deps) -----------------


def get_chat_service(
    settings: SettingsDep,
    anthropic_client: AnthropicClientDep,
):
    """Construct a :class:`api.services.chat.ChatService` with injected deps."""
    from api.services.chat import ChatService

    return ChatService(
        anthropic_client=anthropic_client,
        model=settings.anthropic_model,
        max_tokens=settings.chat_max_tokens,
    )


def get_tax_return_service(
    encryptor: PIIEncryptorDep,
):
    """Construct a :class:`api.services.tax.TaxReturnService`."""
    from api.services.tax import TaxReturnService

    return TaxReturnService(encryptor=encryptor)


def get_agent_service(
    settings: SettingsDep,
    anthropic_client: AnthropicClientDep,
    encryptor: PIIEncryptorDep,
):
    """Construct an AgentService with injected deps."""
    from api.agent.service import AgentService
    from api.agent.mcp_server import build_tool_registry

    return AgentService(
        anthropic_client=anthropic_client,
        model=settings.agent_model,
        max_tokens=settings.agent_max_tokens,
        max_tool_rounds=settings.agent_max_tool_rounds,
        history_token_budget=settings.agent_history_token_budget,
        tool_registry=build_tool_registry(),
    )


@lru_cache(maxsize=1)
def _cached_tax_brain_pool():
    """Lazy singleton psycopg2 pool for tax_brain KB access."""
    try:
        from tax_brain.factories import create_pool
        return create_pool()
    except Exception:
        logger.warning("tax_brain pool unavailable — research tools will be degraded")
        return None


def get_tax_brain_pool():
    return _cached_tax_brain_pool()


def get_research_service(
    settings: SettingsDep,
    anthropic_client: AnthropicClientDep,
):
    """Construct a ResearchService with research tool registry."""
    from api.agent.research_service import ResearchService
    from api.agent.tools.research_tools import build_research_tool_registry

    return ResearchService(
        anthropic_client=anthropic_client,
        model=settings.agent_model,
        max_tokens=settings.agent_max_tokens,
        max_tool_rounds=settings.agent_max_tool_rounds,
        tool_registry=build_research_tool_registry(),
    )
