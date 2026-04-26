"""
taxkb/rules/neo4j_store.py

Loads parsed MeFRule objects into Neo4j.
Creates Form, FormLine, Rule, ErrorCode nodes and all relationship edges.
Uses MERGE (upsert) semantics — safe to re-run after CSV version updates.
"""
from __future__ import annotations

import logging
from typing import Optional

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable

from taxkb.models import MeFRule, RuleVersionDiff, ChangeType

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Cypher statements
# ──────────────────────────────────────────────────────────────────────────────

_MERGE_FORM = """
MERGE (f:Form {form_type: $form_type, tax_year: $tax_year})
ON CREATE SET f.ingested_at = datetime()
ON MATCH  SET f.last_seen   = datetime()
RETURN f
"""

_MERGE_FORM_LINE = """
MERGE (fl:FormLine {form_type: $form_type, field_path: $field_path, tax_year: $tax_year})
ON CREATE SET
    fl.short_field  = $short_field,
    fl.data_type    = 'UNKNOWN',
    fl.ingested_at  = datetime()
RETURN fl
"""

_MERGE_RULE = """
MERGE (r:Rule {rule_id: $rule_id, tax_year: $tax_year, schema_version: $schema_version})
ON CREATE SET
    r.rule_type       = $rule_type,
    r.form_family     = $form_family,
    r.severity        = $severity,
    r.error_code      = $error_code,
    r.rule_text       = $rule_text,
    r.rule_expression = $rule_expression,
    r.expression_ast  = $expression_ast,
    r.parse_success   = $parse_success,
    r.parse_error_msg = $parse_error_msg,
    r.is_current      = true,
    r.ingested_at     = datetime()
ON MATCH SET
    r.rule_type       = $rule_type,
    r.severity        = $severity,
    r.rule_text       = $rule_text,
    r.rule_expression = $rule_expression,
    r.expression_ast  = $expression_ast,
    r.parse_success   = $parse_success,
    r.is_current      = true,
    r.last_seen       = datetime()
RETURN r
"""

_MERGE_ERROR_CODE = """
MERGE (ec:ErrorCode {code: $code})
ON CREATE SET ec.description = $description
RETURN ec
"""

_MERGE_GOVERNED_BY = """
MATCH (fl:FormLine {form_type: $form_type, field_path: $field_path, tax_year: $tax_year})
MATCH (r:Rule      {rule_id: $rule_id, tax_year: $tax_year, schema_version: $schema_version})
MERGE (fl)-[rel:GOVERNED_BY]->(r)
ON CREATE SET rel.severity = $severity, rel.rule_type = $rule_type
RETURN rel
"""

_MERGE_RAISES = """
MATCH (r:Rule      {rule_id: $rule_id, tax_year: $tax_year, schema_version: $schema_version})
MATCH (ec:ErrorCode{code: $error_code})
MERGE (r)-[:RAISES]->(ec)
"""

_MARK_SUPERSEDED = """
MATCH (r:Rule {rule_id: $rule_id, tax_year: $tax_year})
WHERE r.schema_version <> $new_version
SET r.is_current = false
"""

_MERGE_SUPERSEDES = """
MATCH (new_r:Rule {rule_id: $rule_id, tax_year: $tax_year, schema_version: $new_version})
MATCH (old_r:Rule {rule_id: $rule_id, tax_year: $tax_year, schema_version: $old_version})
MERGE (new_r)-[s:SUPERSEDES]->(old_r)
ON CREATE SET s.changed_fields = $changed_fields, s.created_at = datetime()
"""


# ──────────────────────────────────────────────────────────────────────────────
# Ingestion class
# ──────────────────────────────────────────────────────────────────────────────

class RuleGraphStore:
    """
    Loads MeF rules into Neo4j.

    Usage:
        ingestor = RuleGraphStore("bolt://localhost:7687", "neo4j", "password")
        counts = ingestor.ingest(rules)
        ingestor.close()
    """

    def __init__(self, uri: str, user: str, password: str):
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        self._verify_connectivity()

    def _verify_connectivity(self) -> None:
        try:
            self._driver.verify_connectivity()
            logger.info("Neo4j connection verified.")
        except ServiceUnavailable as exc:
            raise ConnectionError(f"Cannot connect to Neo4j at configured URI: {exc}") from exc

    def close(self) -> None:
        self._driver.close()

    # ──────────────────────────────────────────────────────────────────────
    # Main ingestion entry point
    # ──────────────────────────────────────────────────────────────────────

    def ingest(self, rules: list[MeFRule]) -> dict[str, int]:
        """
        Upsert all rules into Neo4j.

        Returns a counts dict: {nodes_created, relationships_created, errors}
        """
        counts = {"nodes_created": 0, "relationships_created": 0, "errors": 0}

        with self._driver.session(database="neo4j") as session:
            for rule in rules:
                try:
                    created = session.execute_write(self._upsert_rule_tx, rule)
                    counts["nodes_created"]         += created["nodes"]
                    counts["relationships_created"] += created["rels"]
                except Exception as exc:
                    counts["errors"] += 1
                    logger.error("Failed to ingest rule %s: %s", rule.rule_id, exc)

        logger.info(
            "Neo4j ingestion complete: %d nodes, %d rels, %d errors",
            counts["nodes_created"], counts["relationships_created"], counts["errors"],
        )
        return counts

    def apply_supersedes(
        self,
        diffs: list[RuleVersionDiff],
        new_version: str,
    ) -> int:
        """
        After ingesting a new schema version, mark old rules as superseded
        and create SUPERSEDES edges.  Returns number of supersede relationships created.
        """
        count = 0
        with self._driver.session(database="neo4j") as session:
            for diff in diffs:
                if diff.change_type == ChangeType.MODIFIED and diff.old_version:
                    session.execute_write(
                        self._apply_supersedes_tx,
                        diff.rule_id,
                        diff.tax_year,
                        diff.old_version,
                        new_version,
                        diff.changed_fields,
                    )
                    count += 1
        logger.info("Created %d SUPERSEDES relationships", count)
        return count

    # ──────────────────────────────────────────────────────────────────────
    # Transaction functions (static so they're passed to execute_write)
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _upsert_rule_tx(tx, rule: MeFRule) -> dict:
        nodes, rels = 0, 0

        # 1. Ensure Form node exists
        tx.run(_MERGE_FORM, form_type=rule.form_family, tax_year=rule.tax_year)
        nodes += 1

        # 2. Ensure FormLine node exists
        tx.run(
            _MERGE_FORM_LINE,
            form_type  = rule.form_family,
            field_path = rule.field_path,
            tax_year   = rule.tax_year,
            short_field= rule.short_field,
        )
        nodes += 1

        # 3. Upsert Rule node
        tx.run(
            _MERGE_RULE,
            rule_id        = rule.rule_id,
            tax_year       = rule.tax_year,
            schema_version = rule.schema_version,
            rule_type      = rule.rule_type.value,
            form_family    = rule.form_family,
            severity       = rule.severity.value,
            error_code     = rule.error_code,
            rule_text      = rule.rule_text,
            rule_expression= rule.rule_expression,
            expression_ast = str(rule.expression_ast) if rule.expression_ast else None,
            parse_success  = rule.parse_success,
            parse_error_msg= rule.parse_error_msg,
        )
        nodes += 1

        # 4. Ensure ErrorCode node exists
        tx.run(
            _MERGE_ERROR_CODE,
            code       = rule.error_code,
            description= rule.rule_text[:200],
        )
        nodes += 1

        # 5. FormLine —[GOVERNED_BY]→ Rule
        tx.run(
            _MERGE_GOVERNED_BY,
            form_type      = rule.form_family,
            field_path     = rule.field_path,
            tax_year       = rule.tax_year,
            rule_id        = rule.rule_id,
            schema_version = rule.schema_version,
            severity       = rule.severity.value,
            rule_type      = rule.rule_type.value,
        )
        rels += 1

        # 6. Rule —[RAISES]→ ErrorCode
        tx.run(
            _MERGE_RAISES,
            rule_id        = rule.rule_id,
            tax_year       = rule.tax_year,
            schema_version = rule.schema_version,
            error_code     = rule.error_code,
        )
        rels += 1

        return {"nodes": nodes, "rels": rels}

    @staticmethod
    def _apply_supersedes_tx(
        tx,
        rule_id: str,
        tax_year: int,
        old_version: str,
        new_version: str,
        changed_fields: list[str],
    ) -> None:
        # Mark all prior versions of this rule as not current
        tx.run(
            _MARK_SUPERSEDED,
            rule_id=rule_id, tax_year=tax_year, new_version=new_version,
        )
        # Create SUPERSEDES edge
        tx.run(
            _MERGE_SUPERSEDES,
            rule_id=rule_id, tax_year=tax_year,
            old_version=old_version, new_version=new_version,
            changed_fields=changed_fields,
        )
