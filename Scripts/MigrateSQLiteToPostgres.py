#!/usr/bin/env python3
"""
MigrateSQLiteToPostgres.py

Migrates all data from the SQLite database (Data/MediaVortex.db) to PostgreSQL.
Reads the SQLite schema, creates equivalent PostgreSQL tables, and bulk-inserts data.

Usage:
    python Scripts/MigrateSQLiteToPostgres.py

Environment variables for PostgreSQL connection (defaults match docker-compose.yml):
    MEDIAVORTEX_DB_HOST     (default: localhost)
    MEDIAVORTEX_DB_PORT     (default: 5432)
    MEDIAVORTEX_DB_NAME     (default: mediavortex)
    MEDIAVORTEX_DB_USER     (default: mediavortex)
    MEDIAVORTEX_DB_PASSWORD (default: mediavortex)
"""

import os
import sys
import sqlite3
import time

import psycopg2
import psycopg2.extras

# Batch size for bulk inserts
BATCH_SIZE = 5000

# SQLite type -> PostgreSQL type mapping
TYPE_MAP = {
    "INTEGER": "BIGINT",
    "INT": "BIGINT",
    "REAL": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "NUMERIC": "NUMERIC",
    "TEXT": "TEXT",
    "BLOB": "BYTEA",
    "BOOLEAN": "BOOLEAN",
    "DATETIME": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
    "DATE": "DATE",
    "": "TEXT",
}


def get_sqlite_path():
    """Get path to the SQLite database."""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(script_dir, "Data", "MediaVortex.db")
    if not os.path.exists(db_path):
        print(f"SQLite database not found at: {db_path}")
        sys.exit(1)
    return db_path


def get_pg_connection():
    """Get a PostgreSQL connection using environment variables."""
    return psycopg2.connect(
        host=os.environ.get("MEDIAVORTEX_DB_HOST", "localhost"),
        port=int(os.environ.get("MEDIAVORTEX_DB_PORT", "5432")),
        dbname=os.environ.get("MEDIAVORTEX_DB_NAME", "mediavortex"),
        user=os.environ.get("MEDIAVORTEX_DB_USER", "mediavortex"),
        password=os.environ.get("MEDIAVORTEX_DB_PASSWORD", "mediavortex"),
    )


def map_sqlite_type(sqlite_type):
    """Map a SQLite column type to PostgreSQL equivalent."""
    if not sqlite_type:
        return "TEXT"
    upper = sqlite_type.upper().strip()
    # Handle types with parameters like VARCHAR(255)
    base_type = upper.split("(")[0].strip()
    if base_type in TYPE_MAP:
        return TYPE_MAP[base_type]
    if "CHAR" in upper or "CLOB" in upper or "STRING" in upper:
        return "TEXT"
    if "INT" in upper:
        return "BIGINT"
    if "REAL" in upper or "FLOA" in upper or "DOUB" in upper:
        return "DOUBLE PRECISION"
    return "TEXT"


def get_sqlite_tables(sqlite_conn):
    """Get all user tables from SQLite."""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def get_sqlite_table_info(sqlite_conn, table_name):
    """Get column info for a SQLite table."""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
    columns = []
    for row in cursor.fetchall():
        columns.append({
            "cid": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": row[3],
            "default": row[4],
            "pk": row[5],
        })
    return columns


def build_create_table_sql(table_name, columns):
    """Build a PostgreSQL CREATE TABLE statement from SQLite column info."""
    col_defs = []
    pk_columns = [c for c in columns if c["pk"] > 0]

    for col in columns:
        pg_type = map_sqlite_type(col["type"])

        # Use SERIAL for integer primary keys (SQLite autoincrement)
        if col["pk"] == 1 and len(pk_columns) == 1 and "INT" in (col["type"] or "").upper():
            pg_type = "BIGSERIAL"

        parts = [f'"{col["name"]}"', pg_type]

        if col["notnull"] and col["pk"] == 0:
            parts.append("NOT NULL")

        if col["default"] is not None and col["pk"] == 0:
            default_val = col["default"]
            # Convert SQLite defaults to PG
            if default_val.upper() == "CURRENT_TIMESTAMP":
                parts.append("DEFAULT CURRENT_TIMESTAMP")
            elif default_val.upper() in ("NULL",):
                parts.append("DEFAULT NULL")
            elif pg_type == "BOOLEAN":
                # SQLite uses 0/1 for booleans
                parts.append(f"DEFAULT {'TRUE' if default_val in ('1', 'true', 'True') else 'FALSE'}")
            elif default_val.replace('.', '', 1).replace('-', '', 1).isdigit():
                # Numeric default - use as-is
                parts.append(f"DEFAULT {default_val}")
            elif default_val.startswith("'") and default_val.endswith("'"):
                # Already quoted string
                parts.append(f"DEFAULT {default_val}")
            else:
                # Unquoted string default - quote it
                parts.append(f"DEFAULT '{default_val}'")

        col_defs.append(" ".join(parts))

    # Add primary key constraint
    if pk_columns:
        pk_cols = ", ".join(f'"{c["name"]}"' for c in sorted(pk_columns, key=lambda x: x["pk"]))
        col_defs.append(f"PRIMARY KEY ({pk_cols})")

    return f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n  {",".join(col_defs)}\n)'


def migrate_table_data(sqlite_conn, pg_conn, table_name, columns):
    """Migrate data from a SQLite table to PostgreSQL in batches."""
    col_names = [col["name"] for col in columns]
    col_list = ", ".join(f'"{c}"' for c in col_names)

    # Identify boolean columns (SQLite stores 0/1, PG needs bool cast)
    bool_indices = set()
    for i, col in enumerate(columns):
        pg_type = map_sqlite_type(col["type"])
        if pg_type == "BOOLEAN":
            bool_indices.add(i)

    # Use explicit CAST for boolean columns in placeholders
    placeholder_parts = []
    for i in range(len(col_names)):
        if i in bool_indices:
            placeholder_parts.append("%s::BOOLEAN")
        else:
            placeholder_parts.append("%s")
    placeholders = ", ".join(placeholder_parts)

    insert_sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'

    # Count rows
    cursor = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table_name}"')
    total_rows = cursor.fetchone()[0]

    if total_rows == 0:
        print(f"  {table_name}: 0 rows (empty table)")
        return 0

    # Read and insert in batches
    sqlite_cursor = sqlite_conn.execute(f'SELECT {col_list} FROM "{table_name}"')
    pg_cursor = pg_conn.cursor()

    migrated = 0
    batch = []
    start_time = time.time()

    while True:
        rows = sqlite_cursor.fetchmany(BATCH_SIZE)
        if not rows:
            break

        # Convert rows to tuples, handling None and other type issues
        clean_rows = []
        for row in rows:
            clean_row = []
            for i, val in enumerate(row):
                if isinstance(val, bytes):
                    clean_row.append(psycopg2.Binary(val))
                elif i in bool_indices and val is not None:
                    clean_row.append(bool(val))
                else:
                    clean_row.append(val)
            clean_rows.append(tuple(clean_row))

        try:
            psycopg2.extras.execute_batch(pg_cursor, insert_sql, clean_rows, page_size=1000)
            pg_conn.commit()
        except Exception as e:
            pg_conn.rollback()
            print(f"  ERROR inserting batch into {table_name}: {e}")
            # Try row-by-row for this batch to find problematic rows
            for i, row in enumerate(clean_rows):
                try:
                    pg_cursor.execute(insert_sql, row)
                    pg_conn.commit()
                    migrated += 1
                except Exception as row_err:
                    pg_conn.rollback()
                    if migrated + i < 5:  # Only print first few errors
                        print(f"    Skipping row {migrated + i}: {row_err}")
            continue

        migrated += len(clean_rows)

        # Progress update every 50k rows
        if migrated % 50000 < BATCH_SIZE:
            elapsed = time.time() - start_time
            rate = migrated / elapsed if elapsed > 0 else 0
            print(f"  {table_name}: {migrated:,}/{total_rows:,} rows ({rate:.0f} rows/sec)")

    elapsed = time.time() - start_time
    rate = migrated / elapsed if elapsed > 0 else 0
    print(f"  {table_name}: {migrated:,}/{total_rows:,} rows migrated ({elapsed:.1f}s, {rate:.0f} rows/sec)")

    # Reset sequences for SERIAL columns
    for col in columns:
        if col["pk"] == 1 and "INT" in (col["type"] or "").upper():
            try:
                pg_cursor.execute(f"""
                    SELECT setval(pg_get_serial_sequence('"{table_name}"', '{col["name"]}'),
                           COALESCE((SELECT MAX("{col["name"]}") FROM "{table_name}"), 0) + 1, false)
                """)
                pg_conn.commit()
            except Exception:
                pg_conn.rollback()

    return migrated


def verify_migration(sqlite_conn, pg_conn, tables):
    """Verify row counts match between SQLite and PostgreSQL."""
    print("\n=== Verification ===")
    all_match = True
    pg_cursor = pg_conn.cursor()

    for table_name in tables:
        sqlite_cursor = sqlite_conn.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        sqlite_count = sqlite_cursor.fetchone()[0]

        pg_cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        pg_count = pg_cursor.fetchone()[0]

        status = "OK" if sqlite_count == pg_count else "MISMATCH"
        if sqlite_count != pg_count:
            all_match = False

        print(f"  {table_name}: SQLite={sqlite_count:,}, PostgreSQL={pg_count:,} [{status}]")

    return all_match


def main():
    print("=" * 60)
    print("MediaVortex SQLite -> PostgreSQL Migration")
    print("=" * 60)

    # Connect to SQLite
    sqlite_path = get_sqlite_path()
    print(f"\nSQLite database: {sqlite_path}")
    file_size_mb = os.path.getsize(sqlite_path) / (1024 * 1024)
    print(f"Database size: {file_size_mb:.1f} MB")

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = None  # Use tuple rows for speed

    # Connect to PostgreSQL
    print("\nConnecting to PostgreSQL...")
    try:
        pg_conn = get_pg_connection()
        pg_conn.autocommit = False
        print("Connected successfully.")
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}")
        print("\nMake sure PostgreSQL is running (docker-compose up -d postgres)")
        sys.exit(1)

    # Get tables
    tables = get_sqlite_tables(sqlite_conn)
    print(f"\nFound {len(tables)} tables to migrate: {', '.join(tables)}")

    # Phase 1: Create tables
    print("\n=== Phase 1: Creating Tables ===")
    pg_cursor = pg_conn.cursor()
    for table_name in tables:
        columns = get_sqlite_table_info(sqlite_conn, table_name)
        create_sql = build_create_table_sql(table_name, columns)
        try:
            pg_cursor.execute(create_sql)
            pg_conn.commit()
            print(f"  Created: {table_name} ({len(columns)} columns)")
        except Exception as e:
            pg_conn.rollback()
            print(f"  ERROR creating {table_name}: {e}")

    # Phase 2: Migrate data
    print("\n=== Phase 2: Migrating Data ===")
    total_migrated = 0
    overall_start = time.time()

    for table_name in tables:
        columns = get_sqlite_table_info(sqlite_conn, table_name)
        count = migrate_table_data(sqlite_conn, pg_conn, table_name, columns)
        total_migrated += count

    overall_elapsed = time.time() - overall_start
    print(f"\nTotal: {total_migrated:,} rows migrated in {overall_elapsed:.1f}s")

    # Phase 3: Verify
    all_match = verify_migration(sqlite_conn, pg_conn, tables)

    # Cleanup
    sqlite_conn.close()
    pg_conn.close()

    print("\n" + "=" * 60)
    if all_match:
        print("Migration completed successfully! All row counts match.")
    else:
        print("Migration completed with mismatches. Review the verification output above.")
    print("=" * 60)


if __name__ == "__main__":
    main()
