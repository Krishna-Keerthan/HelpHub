"""EXPLAIN helper for query-plan assertions (test-only)."""

from sqlalchemy import TextClause, text


def explain_statement(statement: TextClause) -> TextClause:
    """EXPLAIN of ``statement`` with the same bound parameters."""
    return text("EXPLAIN " + statement.text).bindparams(*statement._bindparams.values())
