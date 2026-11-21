"""
SQLite cache used by extensions to avoid repeating wiki API requests.

The database file lives in ``data/db/<wiki_tag>.sqlite3`` (one file per wiki) and is opened lazily: importing
this module must not create files as a side effect.  Use :func:`get_bot_db` (or
the module-level ``bot_db`` proxy, which forwards to it) to obtain the instance.
"""

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from src.Yugong.core.logger import BotLogger
from src.Yugong.core.settings import settings
from src.Yugong.utilities.path_helper import PROJECT_ROOT

#: Tables YuGong itself creates.  Table and column names cannot be bound as SQL
#: parameters, so every identifier is checked against this list / a strict regex
#: before it is interpolated into a statement.
TABLES: frozenset[str] = frozenset(
    {"template", "alias", "category", "zh_convert", "cgroup"}
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class BotDB:
    """
    Wiki bot database management class.

    Uses SQLite single-file database with WAL mode for high-performance reads/writes.
    Provides generic CRUD methods with automatic JSON serialization.

    Database tables:
        1. template - Wiki template info
           - id (INTEGER, PK, autoincrement)
           - title (TEXT, NOT NULL)
           - target (TEXT, NOT NULL)

        2. alias - Redirect mapping
           - id (INTEGER, PK, autoincrement)
           - title (TEXT, NOT NULL)
           - target (TEXT, NOT NULL)

        3. category - Category mapping
           - id (INTEGER, PK, autoincrement)
           - title (TEXT, NOT NULL)
           - target (TEXT, NOT NULL)
    """

    def __init__(self, db_path: Path | None = None):
        """
        Initialize database connection.

        Args:
            db_path: Database file path, defaults to
                PROJECT_ROOT/data/db/<wiki_tag>.sqlite3
        """
        if db_path is None:
            # One database per wiki.  Category redirects and Void-ness are
            # wiki-specific; sharing them across wikis produced wrong edits.
            tag = re.sub(
                r"[^A-Za-z0-9._-]", "_", str(getattr(settings, "wiki_tag", "wiki"))
            ) or "wiki"
            db_path = PROJECT_ROOT / "data" / "db" / f"{tag}.sqlite3"

        self.db_path = db_path
        self.logger = BotLogger("bot_db")

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get database connection (WAL mode and foreign keys enabled).

        Returns:
            sqlite3.Connection: Database connection object
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _check_table(table: str) -> str:
        """Reject a table name that YuGong does not own."""
        if table not in TABLES:
            raise ValueError(f"Unknown database table {table!r}")
        return table

    @staticmethod
    def _check_columns(columns: Any) -> None:
        for column in columns:
            if not isinstance(column, str) or not _IDENTIFIER_RE.fullmatch(column):
                raise ValueError(f"Invalid SQL column name {column!r}")

    @staticmethod
    def _check_limit(limit: Any) -> None:
        """``LIMIT`` cannot be a bound parameter, so it must be a real integer."""
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 0
        ):
            raise ValueError(f"LIMIT must be a non-negative integer, got {limit!r}")

    def _init_database(self) -> None:
        """Create all tables if they don't exist and apply schema migrations."""
        with closing(self._get_connection()) as conn, conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS template (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    target TEXT NOT NULL,
                    type TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    target TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS category (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    target TEXT NOT NULL,
                    sort_index TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS zh_convert (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hans TEXT NOT NULL,
                    hant TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cgroup (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    page_title TEXT NOT NULL,
                    kind TEXT,
                    revid TEXT,
                    rules TEXT,
                    imports TEXT,
                    fetched_at TEXT
                )
            """)

            # Older versions created these tables without the columns below.
            # `CREATE TABLE IF NOT EXISTS` does not fix that, and inserts would
            # fail forever, so patch existing databases in place.
            self._ensure_column(conn, "template", "type", "TEXT")
            self._ensure_column(conn, "category", "sort_index", "TEXT")
            self._ensure_column(conn, "cgroup", "page_title", "TEXT")
            self._ensure_column(conn, "cgroup", "kind", "TEXT")
            self._ensure_column(conn, "cgroup", "revid", "TEXT")
            self._ensure_column(conn, "cgroup", "rules", "TEXT")
            self._ensure_column(conn, "cgroup", "imports", "TEXT")
            self._ensure_column(conn, "cgroup", "fetched_at", "TEXT")

            conn.commit()
            self.logger.info("Database initialized")

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection, table: str, column: str, declaration: str
    ) -> None:
        existing = {
            str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")
        }
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def insert(self, table: str, data: dict[str, Any]) -> bool:
        """
        Insert data into the specified table.

        Args:
            table: Table name
            data: Data dictionary to insert

        Returns:
            bool: Whether the insert succeeded
        """
        try:
            self._check_table(table)
            self._check_columns(data.keys())
            with closing(self._get_connection()) as conn, conn:
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?"] * len(data))
                values = [self._serialize_value(v) for v in data.values()]

                query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
                conn.execute(query, values)
                conn.commit()
                self.logger.debug(f"Inserted into {table}: {data}")
                return True
        except Exception as e:
            self.logger.error(f"Insert failed: {e}")
            return False

    def update(self, table: str, data: dict[str, Any], conditions: dict[str, Any]) -> bool:
        """
        Update data in the specified table.

        Args:
            table: Table name
            data: Fields and values to update
            conditions: Update conditions (AND-connected)

        Returns:
            bool: Whether the update succeeded
        """
        try:
            self._check_table(table)
            self._check_columns(data.keys())
            self._check_columns(conditions.keys())
            with closing(self._get_connection()) as conn, conn:
                set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
                where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])

                values = [self._serialize_value(v) for v in data.values()]
                values += [self._serialize_value(v) for v in conditions.values()]

                query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
                cursor = conn.execute(query, values)
                conn.commit()

                if cursor.rowcount > 0:
                    self.logger.debug(f"Updated {table}: {data}, conditions: {conditions}")
                    return True
                else:
                    self.logger.warning("No matching record found for update")
                    return False
        except Exception as e:
            self.logger.error(f"Update failed: {e}")
            return False

    def delete(self, table: str, conditions: dict[str, Any]) -> bool:
        """
        Delete data from the specified table.

        Args:
            table: Table name
            conditions: Delete conditions (AND-connected)

        Returns:
            bool: Whether the delete succeeded
        """
        try:
            self._check_table(table)
            self._check_columns(conditions.keys())
            with closing(self._get_connection()) as conn, conn:
                where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
                values = [self._serialize_value(v) for v in conditions.values()]

                query = f"DELETE FROM {table} WHERE {where_clause}"
                cursor = conn.execute(query, values)
                conn.commit()

                if cursor.rowcount > 0:
                    self.logger.debug(f"Deleted from {table}, conditions: {conditions}")
                    return True
                else:
                    self.logger.warning("No matching record found for delete")
                    return False
        except Exception as e:
            self.logger.error(f"Delete failed: {e}")
            return False

    def search(self, table: str, conditions: dict[str, Any] | None = None,
               columns: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Search the specified table (exact match).

        Args:
            table: Table name
            conditions: Search conditions (AND-connected), None for all rows
            columns: Column names to return, None for all columns
            limit: Limit result count

        Returns:
            List[Dict[str, Any]]: Search results
        """
        try:
            self._check_table(table)
            if columns:
                self._check_columns(columns)
            if conditions:
                self._check_columns(conditions.keys())
            self._check_limit(limit)
            with closing(self._get_connection()) as conn:
                select_columns = ", ".join(columns) if columns else "*"
                query = f"SELECT {select_columns} FROM {table}"
                values = []

                if conditions:
                    where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
                    query += f" WHERE {where_clause}"
                    values = [self._serialize_value(v) for v in conditions.values()]

                if limit:
                    query += f" LIMIT {limit}"

                cursor = conn.execute(query, values)
                rows = cursor.fetchall()

                results = [dict(row) for row in rows]
                results = [self._deserialize_row(row) for row in results]

                self.logger.debug(f"Searched {table}, conditions: {conditions}, results: {len(results)}")
                return results
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []

    def search_like(self, table: str, conditions: dict[str, str] | None = None,
                    columns: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Fuzzy search the specified table (LIKE match).

        Args:
            table: Table name
            conditions: Fuzzy conditions (AND-connected), values auto-wrapped with % wildcards
            columns: Column names to return, None for all columns
            limit: Limit result count

        Returns:
            List[Dict[str, Any]]: Search results
        """
        try:
            self._check_table(table)
            if columns:
                self._check_columns(columns)
            if conditions:
                self._check_columns(conditions.keys())
            self._check_limit(limit)
            with closing(self._get_connection()) as conn:
                select_columns = ", ".join(columns) if columns else "*"
                query = f"SELECT {select_columns} FROM {table}"
                values = []

                if conditions:
                    where_clause = " AND ".join([f"{k} LIKE ?" for k in conditions.keys()])
                    query += f" WHERE {where_clause}"
                    values = [f"%{v}%" for v in conditions.values()]

                if limit:
                    query += f" LIMIT {limit}"

                cursor = conn.execute(query, values)
                rows = cursor.fetchall()

                results = [dict(row) for row in rows]
                results = [self._deserialize_row(row) for row in results]

                self.logger.debug(f"Fuzzy search {table}, conditions: {conditions}, results: {len(results)}")
                return results
        except Exception as e:
            self.logger.error(f"Fuzzy search failed: {e}")
            return []

    def search_query(self, table: str, where_clause: str = "",
                     values: list[Any] | None = None,
                     columns: list[str] | None = None,
                     limit: int | None = None) -> list[dict[str, Any]]:
        """
        Generic query with custom WHERE clause (supports <, >, LIKE, etc.).

        Args:
            table: Table name
            where_clause: WHERE conditions (without "WHERE" keyword),
                          e.g. ``"start_time > ? AND page = ?"``.
                          Empty for all records.
            values: Parameter list matching ``?`` placeholders
            columns: Column names to return, None for all columns
            limit: Limit result count

        Returns:
            List[Dict[str, Any]]: Query results
        """
        try:
            self._check_table(table)
            if columns:
                self._check_columns(columns)
            self._check_limit(limit)
            with closing(self._get_connection()) as conn:
                select_columns = ", ".join(columns) if columns else "*"
                query = f"SELECT {select_columns} FROM {table}"
                if where_clause:
                    query += f" WHERE {where_clause}"
                if limit is not None:
                    query += f" LIMIT {limit}"

                params = [self._serialize_value(v) for v in (values or [])]
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                results = [dict(row) for row in rows]
                results = [self._deserialize_row(row) for row in results]

                self.logger.debug(
                    f"Query {table}, WHERE {where_clause!r}, "
                    f"results: {len(results)}"
                )
                return results
        except Exception as e:
            self.logger.error(f"Query failed: {e}")
            return []

    def execute_transaction(self, operations: list[tuple[str, list[Any]]]) -> bool:
        """
        Execute a transaction (multiple SQL operations).

        Args:
            operations: List of (sql_query, params) tuples

        Returns:
            bool: Whether the transaction succeeded
        """
        try:
            with closing(self._get_connection()) as conn, conn:
                for query, params in operations:
                    serialized_params = [self._serialize_value(p) for p in params]
                    conn.execute(query, serialized_params)
                conn.commit()
                self.logger.debug(f"Transaction succeeded, operations: {len(operations)}")
                return True
        except Exception as e:
            self.logger.error(f"Transaction failed: {e}")
            return False

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """
        Serialize value to storage format (list/dict → JSON string, datetime → ISO 8601).

        Args:
            value: Value to serialize

        Returns:
            Serialized value
        """
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return value

    @staticmethod
    def _deserialize_row(row: dict[str, Any]) -> dict[str, Any]:
        """
        Decode columns that :meth:`_serialize_value` stored as JSON containers.

        Only strings starting with ``[`` or ``{`` are decoded.  Decoding every
        string would silently turn a stored page title like ``"2024"`` into the
        integer ``2024``.
        """
        deserialized = {}
        for key, value in row.items():
            if isinstance(value, str) and value[:1] in "[{":
                try:
                    deserialized[key] = json.loads(value)
                except json.JSONDecodeError:
                    deserialized[key] = value
            else:
                deserialized[key] = value
        return deserialized

    def execute_raw(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """
        Execute raw SQL query and return results.

        Args:
            sql: SQL query statement
            params: Parameter list

        Returns:
            List[Dict[str, Any]]: Query results
        """
        try:
            with closing(self._get_connection()) as conn:
                cursor = conn.execute(sql, params or [])
                rows = cursor.fetchall()
                results = [dict(row) for row in rows]
                results = [self._deserialize_row(row) for row in results]
                return results
        except Exception as e:
            self.logger.error(f"Raw SQL failed: {e}")
            return []


_bot_db: BotDB | None = None


def get_bot_db() -> BotDB:
    """Return the process-wide :class:`BotDB`, creating the file on first use."""
    global _bot_db
    if _bot_db is None:
        _bot_db = BotDB()
    return _bot_db


class _BotDBProxy:
    """Lazy stand-in for the module-level ``bot_db`` singleton.

    Extension code keeps using ``bot_db.search(...)`` unchanged, but nothing
    touches the filesystem until the first real call.
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(get_bot_db(), name)


bot_db: Any = _BotDBProxy()
