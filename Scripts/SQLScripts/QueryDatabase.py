"""
MediaVortex Database Troubleshooting Script
============================================
A flexible script for querying any table in the MediaVortex PostgreSQL database.

Usage:
    python QueryDatabase.py <table> [options]

Examples:
    python QueryDatabase.py tables                              # List all tables with row counts
    python QueryDatabase.py schema <table>                      # Show table schema
    python QueryDatabase.py transcodeattempts                   # Select all (limited to 50)
    python QueryDatabase.py transcodeattempts --limit 10        # Select top 10
    python QueryDatabase.py transcodeattempts --where "success = true" --limit 5
    python QueryDatabase.py transcodeattempts --columns "id,filepath,success,vmaf"
    python QueryDatabase.py transcodeattempts --where "id = 123"
    python QueryDatabase.py transcodeattempts --order "attemptdate DESC"
    python QueryDatabase.py transcodeattempts --count            # Count rows
    python QueryDatabase.py transcodeattempts --count --where "success = true"
    python QueryDatabase.py activejobs --where "status = 'Running'"
    python QueryDatabase.py transcodequeue --where "sizemb > 500" --order "sizemb DESC"
    python QueryDatabase.py sql "SELECT COUNT(*) FROM transcodeattempts WHERE success = true"
    python QueryDatabase.py sql "SELECT status, COUNT(*) FROM transcodequeue GROUP BY status"
"""

import sys
import os
import argparse
import psycopg2
import psycopg2.extras
from datetime import datetime


DB_CONFIG = {
    "host": os.environ.get("MEDIAVORTEX_DB_HOST", "localhost"),
    "port": int(os.environ.get("MEDIAVORTEX_DB_PORT", "5432")),
    "dbname": os.environ.get("MEDIAVORTEX_DB_NAME", "mediavortex"),
    "user": os.environ.get("MEDIAVORTEX_DB_USER", "mediavortex"),
    "password": os.environ.get("MEDIAVORTEX_DB_PASSWORD", "mediavortex"),
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def print_table(headers, rows, max_col_width=60):
    """Print results as a formatted table."""
    if not rows:
        print("(no rows)")
        return

    str_rows = []
    for row in rows:
        str_rows.append([truncate(str(v), max_col_width) for v in row])

    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "-+-".join("-" * w for w in col_widths)

    print(header_line)
    print(separator)
    for row in str_rows:
        print(" | ".join(row[i].ljust(col_widths[i]) for i in range(len(headers))))


def truncate(s, max_len):
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s


def list_tables(conn):
    """List all tables with row counts."""
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]

    headers = ["Table", "Rows"]
    rows = []
    for table in tables:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        count = cur.fetchone()[0]
        rows.append((table, count))

    print(f"\nMediaVortex Database - {len(tables)} tables\n")
    print_table(headers, rows)
    print()


def show_schema(conn, table_name):
    """Show column names and types for a table."""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """, (table_name.lower(),))

    columns = cur.fetchall()
    if not columns:
        print(f"Table '{table_name}' not found.")
        return

    print(f"\nSchema for: {table_name} ({len(columns)} columns)\n")
    print_table(["Column", "Type", "Nullable", "Default"], columns)
    print()


def query_table(conn, table_name, columns=None, where=None, order=None, limit=50, count_only=False):
    """Query a table with optional filters."""
    cur = conn.cursor()

    # Validate table exists
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
    """, (table_name.lower(),))

    if not cur.fetchone():
        print(f"Table '{table_name}' not found. Run 'python QueryDatabase.py tables' to see available tables.")
        return

    select_part = "COUNT(*)" if count_only else (columns if columns else "*")
    query = f'SELECT {select_part} FROM "{table_name.lower()}"'

    if where:
        query += f" WHERE {where}"
    if order and not count_only:
        query += f" ORDER BY {order}"
    if limit and not count_only:
        query += f" LIMIT {limit}"

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query)
        rows = cur.fetchall()

        if count_only:
            print(f"\n{table_name}: {rows[0]['count']} rows", end="")
            if where:
                print(f" (WHERE {where})", end="")
            print("\n")
            return

        if not rows:
            print(f"\n{table_name}: no matching rows")
            if where:
                print(f"  WHERE {where}")
            print()
            return

        headers = list(rows[0].keys())
        data = [list(row.values()) for row in rows]

        showing = f"showing {len(rows)}"
        if limit:
            showing += f" (limit {limit})"

        print(f"\n{table_name} - {showing}")
        if where:
            print(f"  WHERE {where}")
        if order:
            print(f"  ORDER BY {order}")
        print()
        print_table(headers, data)
        print()

    except psycopg2.Error as e:
        print(f"Query error: {e}")
        print(f"Query was: {query}")


def run_raw_sql(conn, sql, commit=False):
    """Execute a raw SQL query and display results.
    By default, non-SELECT statements are rolled back (safe for troubleshooting).
    Pass commit=True for writes that must persist (e.g., worker registration)."""
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql)

        if cur.description is None:
            if commit:
                conn.commit()
                print(f"Query executed and committed. Rows affected: {cur.rowcount}")
            else:
                conn.rollback()
                print(f"Query executed (rolled back -- use --commit to persist). Rows affected: {cur.rowcount}")
            return

        rows = cur.fetchall()
        if not rows:
            print("(no rows)")
            return

        headers = list(rows[0].keys())
        data = [list(row.values()) for row in rows]

        print(f"\n{len(rows)} rows returned\n")
        print_table(headers, data)
        print()

    except psycopg2.Error as e:
        print(f"SQL error: {e}")
        conn.rollback()


def main():
    parser = argparse.ArgumentParser(
        description="MediaVortex Database Troubleshooting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python QueryDatabase.py tables
  python QueryDatabase.py schema transcodeattempts
  python QueryDatabase.py transcodeattempts --limit 10
  python QueryDatabase.py transcodeattempts --where "success = true" --limit 5
  python QueryDatabase.py transcodeattempts --columns "id,filepath,success"
  python QueryDatabase.py transcodequeue --where "sizemb > 500" --order "sizemb DESC"
  python QueryDatabase.py activejobs --where "status = 'Running'"
  python QueryDatabase.py sql "SELECT status, COUNT(*) FROM transcodequeue GROUP BY status"
        """
    )

    parser.add_argument("command", help="Table name, 'tables', 'schema', or 'sql'")
    parser.add_argument("argument", nargs="?", help="Table name (for schema) or SQL query (for sql)")
    parser.add_argument("--where", "-w", help="WHERE clause (without the WHERE keyword)")
    parser.add_argument("--order", "-o", help="ORDER BY clause (without ORDER BY keyword)")
    parser.add_argument("--limit", "-l", type=int, default=50, help="Max rows to return (default: 50, 0 for unlimited)")
    parser.add_argument("--columns", "-c", help="Comma-separated column names to select")
    parser.add_argument("--count", action="store_true", help="Return row count instead of data")
    parser.add_argument("--commit", action="store_true", help="Commit writes (INSERT/UPDATE/DELETE) instead of rolling back")

    args = parser.parse_args()

    conn = get_connection()

    try:
        if args.command == "tables":
            list_tables(conn)
        elif args.command == "schema":
            if not args.argument:
                print("Usage: python QueryDatabase.py schema <table_name>")
                sys.exit(1)
            show_schema(conn, args.argument)
        elif args.command == "sql":
            if not args.argument:
                print("Usage: python QueryDatabase.py sql \"SELECT ...\"")
                sys.exit(1)
            run_raw_sql(conn, args.argument, commit=args.commit)
        else:
            limit = args.limit if args.limit != 0 else None
            query_table(conn, args.command, columns=args.columns, where=args.where,
                       order=args.order, limit=limit, count_only=args.count)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
