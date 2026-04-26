"""
taxkb.instructions — IRS form instruction graph.

Parses IRS instruction HTML pages into structured sections linked
to form lines, stores them in Neo4j and PostgreSQL, and validates
structural integrity and FormLine link coverage.
"""
from taxkb.instructions.html_parser import parse_instruction_html

__all__ = [
    "parse_instruction_html",
]
