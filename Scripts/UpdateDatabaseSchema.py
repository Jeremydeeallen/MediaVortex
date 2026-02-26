#!/usr/bin/env python3
"""
UpdateDatabaseSchema.py

This script generates the DatabaseSchema.md file by querying the PostgreSQL database
and extracting table/column information, indexes, and index columns.
"""

import os
import sys

# Add parent directory to path so we can import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.DatabaseService import DatabaseService


def GenerateDatabaseSchema():
    """Generate the DatabaseSchema.md file from PostgreSQL."""
    try:
        db = DatabaseService()

        # Get script directory for output
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, "..", "Docs", "DatabaseSchema.md")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Database Schema Visual\n\n")
            f.write("## CRITICAL DATA FLOW RULE\n\n")
            f.write("**MediaFiles table is ONLY for display and profile assignment. NEVER use MediaFiles data for transcoding decisions.**\n\n")
            f.write("**ALL transcoding settings come exclusively from ProfileThresholds based on the assigned profile:**\n")
            f.write("- File -> Profile Assignment -> ProfileThresholds -> Transcoding Settings\n")
            f.write("- Bitrates, quality, codec, target resolution = ProfileThresholds only\n")
            f.write("- MediaFiles resolution, codec, etc. = Display only\n\n")

            # Table and Columns
            f.write("## Table and Columns\n\n")
            table_columns = db.ExecuteQuery("""
                SELECT
                    table_name || '.' || column_name AS tablecolumn,
                    data_type AS datatype,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
            """)
            f.write("| Table.Column | Data Type | Nullable | Default |\n")
            f.write("|---|---|---|---|\n")
            for row in table_columns:
                f.write(f"| {row['tablecolumn']} | {row['datatype']} | {row['is_nullable']} | {row['column_default'] or ''} |\n")

            # Indexes
            f.write("\n## Indexes\n\n")
            indexes = db.ExecuteQuery("""
                SELECT
                    t.relname AS tablename,
                    i.relname AS indexname,
                    ix.indisunique AS isunique,
                    ix.indisprimary AS isprimary,
                    pg_get_indexdef(ix.indexrelid) AS indexdef
                FROM pg_index ix
                JOIN pg_class t ON t.oid = ix.indrelid
                JOIN pg_class i ON i.oid = ix.indexrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                ORDER BY t.relname, i.relname
            """)
            f.write("| Table | Index | Unique | Primary | Definition |\n")
            f.write("|---|---|---|---|---|\n")
            for row in indexes:
                f.write(f"| {row['tablename']} | {row['indexname']} | {row['isunique']} | {row['isprimary']} | {row['indexdef']} |\n")

            # Foreign Key Constraints
            f.write("\n## Foreign Key Constraints\n\n")
            foreign_keys = db.ExecuteQuery("""
                SELECT
                    tc.table_name AS tablename,
                    tc.constraint_name AS constraintname,
                    kcu.column_name AS columnname,
                    ccu.table_name AS referencedtable,
                    ccu.column_name AS referencedcolumn,
                    rc.update_rule AS onupdate,
                    rc.delete_rule AS ondelete
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                    AND tc.table_schema = ccu.table_schema
                JOIN information_schema.referential_constraints rc
                    ON tc.constraint_name = rc.constraint_name
                    AND tc.table_schema = rc.constraint_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                ORDER BY tc.table_name, tc.constraint_name
            """)
            f.write("| Table | Constraint | Column | Referenced Table | Referenced Column | On Update | On Delete |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            for row in foreign_keys:
                f.write(f"| {row['tablename']} | {row['constraintname']} | {row['columnname']} | {row['referencedtable']} | {row['referencedcolumn']} | {row['onupdate']} | {row['ondelete']} |\n")

        print(f"DatabaseSchema.md updated successfully at: {output_path}")
        return True

    except Exception as e:
        print(f"Error generating DatabaseSchema.md: {e}")
        return False


if __name__ == "__main__":
    print("Updating DatabaseSchema.md...")
    success = GenerateDatabaseSchema()
    if success:
        print("DatabaseSchema.md updated successfully")
    else:
        print("Failed to update DatabaseSchema.md")
