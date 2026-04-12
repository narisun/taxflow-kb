"""
tax_brain/evaluation/models.py

Data models for the Layer 5 evaluation framework.

GoldSetEntry  — a single verified Q&A pair with retrieval metadata.
GoldSet       — versioned collection of entries with summary stats.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ── Gold set entry ────────────────────────────────────────────────────────────

class GoldSetEntry(BaseModel):
    """
    One verified question-answer pair in the evaluation gold set.

    Fields:
        id              : Unique identifier (auto-generated UUID if not supplied).
        question        : The natural-language CPA question.
        ground_truth    : The expert-verified correct answer.
        gold_chunk_ids  : chunk_id values of the chunks that contain the answer.
                          Used to compute retrieval recall.
        expected_pub    : Primary IRS publication number ("596", "17", etc.).
        tax_year        : Tax year the question and answer apply to.
        difficulty      : "simple" | "medium" | "complex"
        topic_tags      : Free-form tags for sliced analysis (e.g. ["EIC", "phase-out"]).
        created_by      : "generated" (LLM draft) | "human" (manually written).
        verified_by     : Name/initials of CPA who verified; None = unverified.
        verified_at     : ISO-8601 timestamp of verification.
        notes           : Optional CPA annotation or correction notes.
    """
    question       : str
    ground_truth   : str
    expected_pub   : str
    gold_chunk_ids : list[str]          = Field(default_factory=list)
    tax_year       : int                = 2025
    difficulty     : str                = "simple"      # simple | medium | complex
    topic_tags     : list[str]          = Field(default_factory=list)
    created_by     : str                = "generated"   # generated | human
    verified_by    : Optional[str]      = None
    verified_at    : Optional[str]      = None
    notes          : str                = ""
    id             : str                = Field(default_factory=lambda: str(uuid.uuid4())[:8])

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def is_verified(self) -> bool:
        return self.verified_by is not None

    @property
    def short_id(self) -> str:
        return f"{self.expected_pub}-{self.id}"

    def mark_verified(self, verifier: str, note: str = "") -> None:
        self.verified_by = verifier
        self.verified_at = datetime.now(timezone.utc).isoformat()
        if note:
            self.notes = note

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: dict) -> "GoldSetEntry":
        # Get valid field names from Pydantic model
        valid_fields = cls.model_fields.keys()
        return cls(**{k: v for k, v in d.items() if k in valid_fields})


# ── Gold set collection ───────────────────────────────────────────────────────

class GoldSet(BaseModel):
    """
    Versioned collection of gold set entries.

    Attributes:
        version     : Semver-style version string (e.g. "1.0.0").
        description : Human-readable description of this set.
        entries     : List of GoldSetEntry objects.
        created_at  : Creation timestamp (ISO-8601).
    """
    version     : str             = "1.0.0"
    description : str             = "TaxFlow AI evaluation gold set"
    created_at  : str             = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    entries     : list[GoldSetEntry] = Field(default_factory=list)

    # ── Statistics ────────────────────────────────────────────────────────────

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def verified_count(self) -> int:
        return sum(1 for e in self.entries if e.is_verified)

    @property
    def by_pub(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e.expected_pub] = counts.get(e.expected_pub, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def by_difficulty(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e.difficulty] = counts.get(e.difficulty, 0) + 1
        return counts

    def summary(self) -> str:
        lines = [
            f"Gold Set v{self.version}  ({self.total} entries, "
            f"{self.verified_count} verified)",
            f"  By pub:        { {k: v for k,v in self.by_pub.items()} }",
            f"  By difficulty: { self.by_difficulty }",
        ]
        return "\n".join(lines)

    def filter(
        self,
        pub          : Optional[str]  = None,
        difficulty   : Optional[str]  = None,
        verified_only: bool           = False,
    ) -> list[GoldSetEntry]:
        result = self.entries
        if pub:
            result = [e for e in result if e.expected_pub == pub]
        if difficulty:
            result = [e for e in result if e.difficulty == difficulty]
        if verified_only:
            result = [e for e in result if e.is_verified]
        return result

    # ── I/O ──────────────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Save the gold set as a pretty-printed JSONL file (one entry per line)
        wrapped in a JSON envelope with version metadata."""
        data = {
            "version"    : self.version,
            "description": self.description,
            "created_at" : self.created_at,
            "total"      : self.total,
            "entries"    : [e.to_dict() for e in self.entries],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str | Path) -> "GoldSet":
        """Load a gold set from a JSON file saved by .save()."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        entries = [GoldSetEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            version     = data.get("version", "1.0.0"),
            description = data.get("description", ""),
            created_at  = data.get("created_at", ""),
            entries     = entries,
        )

    @classmethod
    def empty(cls) -> "GoldSet":
        return cls()
