"""
tax_brain/adapters/postgres.py

Concrete PostgreSQL connection pool implementation.
"""
from __future__ import annotations

from typing import Any

import psycopg2.pool


class PgConnectionPool:
    """
    Thread-safe PostgreSQL connection pool wrapper.

    Wraps psycopg2.pool.ThreadedConnectionPool for safe connection reuse
    across threads. Implements the ConnectionPool protocol.
    """

    def __init__(
        self,
        dsn: str,
        min_conn: int = 2,
        max_conn: int = 10,
    ) -> None:
        """
        Initialize the PostgreSQL connection pool.

        Args:
            dsn: PostgreSQL connection string (DSN).
                Example: "postgresql://user:pass@localhost:5432/dbname"
            min_conn: Minimum number of connections to maintain. Defaults to 2.
            max_conn: Maximum number of connections to allow. Defaults to 10.

        Raises:
            psycopg2.Error: If connection pool creation fails.
        """
        self._dsn = dsn
        self._min_conn = min_conn
        self._max_conn = max_conn
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            min_conn,
            max_conn,
            dsn,
        )

    def getconn(self) -> Any:
        """
        Acquire a connection from the pool.

        Returns:
            Any: A psycopg2 connection object.

        Raises:
            psycopg2.pool.PoolError: If no connections are available.
        """
        return self._pool.getconn()

    def putconn(self, conn: Any) -> None:
        """
        Return a connection to the pool for reuse.

        Args:
            conn: The connection to return to the pool.
        """
        self._pool.putconn(conn)

    def closeall(self) -> None:
        """Close all connections in the pool."""
        self._pool.closeall()

    def __del__(self) -> None:
        """Ensure pool is closed when object is garbage collected."""
        try:
            self.closeall()
        except Exception:
            pass
