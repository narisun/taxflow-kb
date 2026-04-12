"""
tax_brain.rules — MeF business rules ingestion and validation.

Parses IRS MeF CSV files into structured rule objects, stores them
in Neo4j (graph) and PostgreSQL (relational), and validates structural
integrity, expert accuracy, and regression safety.
"""
from tax_brain.rules.csv_parser import CSVParser
from tax_brain.rules.ast_parser import parse_expression

__all__ = [
    "CSVParser",
    "parse_expression",
]
