import os
import re
import atexit
from typing import Optional

import psycopg2
import psycopg2.pool
import psycopg2.extras


class CaseInsensitiveDict(dict):
    """Dict that allows case-insensitive key access and preserves PascalCase keys for JSON.

    PostgreSQL returns lowercase column names, but existing code uses PascalCase.
    This wrapper allows both 'SettingValue' and 'settingvalue' to work.
    Keys are stored in PascalCase (from the SQL query) so JSON serialization
    outputs PascalCase keys that the frontend expects.
    """

    def __init__(self, data=None, **kwargs):
        super().__init__()
        self._key_map = {}
        if data:
            for key, value in data.items():
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def __setitem__(self, key, value):
        lower_key = key.lower() if isinstance(key, str) else key
        # If we already have a mapping for this key, use the existing stored key
        # (preserves PascalCase set by set_preferred_key)
        if lower_key in self._key_map:
            actual_key = self._key_map[lower_key]
            super().__setitem__(actual_key, value)
        else:
            self._key_map[lower_key] = key
            super().__setitem__(key, value)

    def __getitem__(self, key):
        lower_key = key.lower() if isinstance(key, str) else key
        actual_key = self._key_map.get(lower_key, key)
        return super().__getitem__(actual_key)

    def __contains__(self, key):
        lower_key = key.lower() if isinstance(key, str) else key
        return lower_key in self._key_map

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def set_preferred_key(self, preferred_key):
        """Set the preferred (PascalCase) version of a key.

        Moves the value from the old key to the new preferred key,
        so JSON serialization outputs PascalCase.
        """
        lower_key = preferred_key.lower() if isinstance(preferred_key, str) else preferred_key
        if lower_key in self._key_map:
            old_key = self._key_map[lower_key]
            if old_key != preferred_key:
                # Get the value, remove old key, store with new key
                value = super().__getitem__(old_key)
                super().__delitem__(old_key)
                self._key_map[lower_key] = preferred_key
                super().__setitem__(preferred_key, value)


# Parse SELECT column names from SQL to get PascalCase versions
_SELECT_RE = re.compile(
    r'^\s*SELECT\s+(.*?)\s+FROM\s',
    re.IGNORECASE | re.DOTALL,
)

def _parse_select_columns(query: str) -> list:
    """Extract column names/aliases from a SELECT query.

    Returns a list of PascalCase column names as written in the SQL.
    Handles: simple columns, table.column, column AS alias, expressions.
    Returns empty list if parsing fails (e.g. SELECT *).
    """
    m = _SELECT_RE.match(query)
    if not m:
        return []

    columns_str = m.group(1).strip()
    if '*' in columns_str and 'AS' not in columns_str.upper():
        return []

    # Split by comma, respecting parentheses (for function calls like COUNT(*))
    columns = []
    depth = 0
    current = []
    for char in columns_str:
        if char == '(':
            depth += 1
            current.append(char)
        elif char == ')':
            depth -= 1
            current.append(char)
        elif char == ',' and depth == 0:
            columns.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        columns.append(''.join(current).strip())

    # Extract the final column name/alias from each column expression
    result = []
    for col in columns:
        col = col.strip()
        if not col:
            continue

        # Check for AS alias (case insensitive)
        as_match = re.search(r'\bAS\s+(\w+)\s*$', col, re.IGNORECASE)
        if as_match:
            result.append(as_match.group(1))
            continue

        # Check for CASE expression without AS - skip
        if col.upper().startswith('CASE') or col.upper().startswith('(CASE'):
            continue

        # Simple column or table.column
        # Take the last word (handles "table.column" -> "column")
        parts = col.split('.')
        last_part = parts[-1].strip()
        # Remove any trailing whitespace or non-identifier chars
        ident_match = re.match(r'(\w+)', last_part)
        if ident_match:
            result.append(ident_match.group(1))

    return result


def EscapeLikePattern(Value: str) -> str:
    """Escape special LIKE characters (!, %, _) in a value for use with ESCAPE '!'.

    Must be applied to any user-supplied string used in a LIKE pattern
    so that characters like ! % _ are treated as literals.
    """
    return Value.replace('!', '!!').replace('%', '!%').replace('_', '!_')


class DatabaseService:
    """Low-level database connection service using PostgreSQL with connection pooling."""

    _pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

    def __init__(self, connection_params: dict = None):
        if connection_params is None:
            connection_params = {
                "host": os.environ.get("MEDIAVORTEX_DB_HOST", "localhost"),
                "port": int(os.environ.get("MEDIAVORTEX_DB_PORT", "5432")),
                "dbname": os.environ.get("MEDIAVORTEX_DB_NAME", "mediavortex"),
                "user": os.environ.get("MEDIAVORTEX_DB_USER", "mediavortex"),
                "password": os.environ.get("MEDIAVORTEX_DB_PASSWORD", "mediavortex"),
            }

        self._connection_params = connection_params
        self._ensure_pool()
        self.LastInsertId = 0

    def _ensure_pool(self):
        """Initialize the shared connection pool if it doesn't exist yet."""
        if DatabaseService._pool is None or DatabaseService._pool.closed:
            DatabaseService._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                **self._connection_params,
            )
            atexit.register(self._close_pool)

    @staticmethod
    def _close_pool():
        if DatabaseService._pool is not None and not DatabaseService._pool.closed:
            DatabaseService._pool.closeall()

    def GetConnection(self):
        """Get a connection from the pool. Caller MUST return it via CloseConnection."""
        self._ensure_pool()
        connection = DatabaseService._pool.getconn()
        connection.autocommit = False
        return connection

    def CloseConnection(self, connection=None):
        """Return a connection to the pool."""
        if connection is not None and DatabaseService._pool is not None:
            DatabaseService._pool.putconn(connection)

    def ExecuteQuery(self, query: str, parameters: tuple = ()) -> list:
        """Execute a SELECT query and return results as list of case-insensitive dicts.

        Column names are stored in PascalCase (as written in the SQL SELECT clause)
        so that JSON serialization preserves the casing the frontend expects.
        """
        connection = self.GetConnection()
        try:
            cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, parameters)
            rows = cursor.fetchall()

            # Parse PascalCase column names from the SQL query
            preferred_names = _parse_select_columns(query)

            result = []
            for row in rows:
                d = CaseInsensitiveDict(row)
                # Apply PascalCase key names from the SQL SELECT clause
                for name in preferred_names:
                    d.set_preferred_key(name)
                result.append(d)

            return result
        finally:
            self.CloseConnection(connection)

    def ExecuteNonQuery(self, query: str, parameters: tuple = ()) -> int:
        """Execute an INSERT, UPDATE, or DELETE query and return affected rows."""
        connection = self.GetConnection()
        try:
            cursor = connection.cursor()
            cursor.execute(query, parameters)
            connection.commit()

            # Capture last insert ID if the query uses RETURNING
            if cursor.description is not None:
                row = cursor.fetchone()
                if row:
                    self.LastInsertId = row[0]

            return cursor.rowcount

        except Exception as e:
            connection.rollback()
            from Core.Logging.LoggingService import LoggingService
            LoggingService.LogException(
                f"ExecuteNonQuery failed. Query: {query}, Parameters: {parameters}, ParamCount: {len(parameters)}",
                e, "DatabaseService", "ExecuteNonQuery"
            )
            raise
        finally:
            self.CloseConnection(connection)

    def ExecuteScalar(self, query: str, parameters: tuple = ()):
        """Execute a query and return the first column of the first row."""
        connection = self.GetConnection()
        try:
            cursor = connection.cursor()
            cursor.execute(query, parameters)
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            self.CloseConnection(connection)

    def GetLastInsertId(self) -> int:
        """Get the ID of the last inserted row (set by RETURNING clause)."""
        try:
            if hasattr(self, 'LastInsertId'):
                return self.LastInsertId
            return 0
        except Exception:
            return 0
