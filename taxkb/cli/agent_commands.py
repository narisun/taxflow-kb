"""
taxkb/cli/agent_commands.py

Layer 4 command handlers: cmd_ask, cmd_validate_agent
"""
from __future__ import annotations

import logging

from taxkb.cli.config_adapter import resolve_openai_key

logger = logging.getLogger("taxflow.cli")


def cmd_ask(args) -> int:
    """Answer a CPA tax question using the full retrieval + synthesis pipeline."""
    import os
    from taxkb.factories import create_agent
    from taxkb.config import get_settings

    api_key = resolve_openai_key(args)
    if not api_key:
        logger.error("OPENAI_API_KEY is required. Pass --api-key or set the env var.")
        return 1

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    pub_filter = getattr(args, "pub", None) or None

    settings = get_settings()
    settings.pg_dsn = args.pg_dsn
    settings.synthesis_model = getattr(args, "model", "gpt-4o-mini")
    agent = create_agent(settings=settings, api_key=api_key)

    synthesize = not getattr(args, "no_synthesize", False)

    ask_tax_year = getattr(args, "tax_year", None) or None

    result = agent.query(
        args.question,
        top_k      = args.top_k,
        pub_filter = pub_filter,
        tax_year   = ask_tax_year,
        synthesize = synthesize,
    )

    show_chunks = getattr(args, "show_chunks", False)
    result.print_report(show_contexts=show_chunks)

    if getattr(args, "json_out", False):
        import json
        out = {
            "query"   : result.query,
            "answer"  : result.answer,
            "sources" : result.sources,
            "contexts": [
                {
                    "pub"    : c.reference,
                    "title"  : c.title,
                    "page"   : c.page,
                    "score"  : round(c.score, 4),
                    "chapter": c.chapter,
                    "section": c.section,
                    "text"   : c.text[:500],
                }
                for c in result.contexts
            ],
            "stats": {
                "retrieval_ms"     : round(result.retrieval_ms),
                "synthesis_ms"     : round(result.synthesis_ms),
                "model"            : result.model_used,
                "prompt_tokens"    : result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            },
        }
        print(json.dumps(out, indent=2))

    return 1 if result.error else 0


def cmd_validate_agent(args) -> int:
    """Run V4.1 CPA agent functional validation (5 real queries)."""
    import os
    from taxkb.factories import create_agent
    from taxkb.config import get_settings
    from taxkb.agent.validation.agent_probes import validate_agent

    api_key = resolve_openai_key(args)
    if not api_key:
        logger.error("OPENAI_API_KEY is required.")
        return 1

    if not args.pg_dsn:
        logger.error("--pg-dsn is required.")
        return 1

    settings = get_settings()
    settings.pg_dsn = args.pg_dsn
    settings.synthesis_model = getattr(args, "model", "gpt-4o-mini")
    agent = create_agent(settings=settings, api_key=api_key)

    v = validate_agent(agent, top_k=args.top_k)
    v.print_report()
    return 0 if v.passed else 1
