#!/usr/bin/env python3
"""
UpdateDatabaseSchema.py

This script generates the DatabaseSchema.md file by querying the database
and extracting table/column information, indexes, and index columns.
"""

import sqlite3
import os
from datetime import datetime

def GetDatabasePath():
    """Get the path to the MediaVortex database."""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(script_dir, "Data", "MediaVortex.db")

def ExecuteQuery(cursor, query):
    """Execute a query and return results."""
    try:
        cursor.execute(query)
        return cursor.fetchall()
    except Exception as e:
        print(f"Error executing query: {e}")
        return []

def GenerateDatabaseSchema():
    """Generate the DatabaseSchema.md file."""
    try:
        db_path = GetDatabasePath()
        
        if not os.path.exists(db_path):
            print(f"Database not found at: {db_path}")
            return False
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get script directory for output
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, "..", "Docs", "DatabaseSchema.md")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Database Schema Visual\n\n")
            f.write("## CRITICAL DATA FLOW RULE\n\n")
            f.write("**MediaFiles table is ONLY for display and profile assignment. NEVER use MediaFiles data for transcoding decisions.**\n\n")
            f.write("**ALL transcoding settings come exclusively from ProfileThresholds based on the assigned profile:**\n")
            f.write("- File → Profile Assignment → ProfileThresholds → Transcoding Settings\n")
            f.write("- Bitrates, quality, codec, target resolution = ProfileThresholds only\n")
            f.write("- MediaFiles resolution, codec, etc. = Display only\n\n")
            f.write("## Queries Used\n\n")
            f.write("### Table and Columns\n")
            f.write("```sql\n")
            f.write("SELECT \n")
            f.write("    m.name || '.' || p.name AS TableColumn,\n")
            f.write("    p.type AS DataType\n")
            f.write("FROM sqlite_master m\n")
            f.write("CROSS JOIN pragma_table_info(m.name) p\n")
            f.write("WHERE m.type = 'table' \n")
            f.write("    AND m.name NOT LIKE 'sqlite_%'\n")
            f.write("ORDER BY m.name, p.cid;\n")
            f.write("```\n\n")
            f.write("### Indexes\n")
            f.write("```sql\n")
            f.write("SELECT \n")
            f.write("    m.name AS TableName,\n")
            f.write("    i.name AS IndexName,\n")
            f.write("    i.\"unique\" AS IsUnique,\n")
            f.write("    i.\"origin\" AS Origin,\n")
            f.write("    i.\"partial\" AS IsPartial\n")
            f.write("FROM sqlite_master m\n")
            f.write("CROSS JOIN pragma_index_list(m.name) i\n")
            f.write("WHERE m.type = 'table' \n")
            f.write("    AND m.name NOT LIKE 'sqlite_%'\n")
            f.write("ORDER BY m.name, i.seq;\n")
            f.write("```\n\n")
            f.write("### Index Columns\n")
            f.write("```sql\n")
            f.write("SELECT \n")
            f.write("    m.name AS TableName,\n")
            f.write("    i.name AS IndexName,\n")
            f.write("    ic.name AS ColumnName,\n")
            f.write("    ic.seqno AS ColumnSequence\n")
            f.write("FROM sqlite_master m\n")
            f.write("CROSS JOIN pragma_index_list(m.name) i\n")
            f.write("CROSS JOIN pragma_index_info(i.name) ic\n")
            f.write("WHERE m.type = 'table' \n")
            f.write("    AND m.name NOT LIKE 'sqlite_%'\n")
            f.write("ORDER BY m.name, i.seq, ic.seqno;\n")
            f.write("```\n\n")
            f.write("### Foreign Key Constraints\n")
            f.write("```sql\n")
            f.write("SELECT \n")
            f.write("    m.name AS TableName,\n")
            f.write("    fk.id AS ConstraintId,\n")
            f.write("    fk.seq AS ColumnSequence,\n")
            f.write("    fk.\"table\" AS ReferencedTable,\n")
            f.write("    fk.\"from\" AS ColumnName,\n")
            f.write("    fk.\"to\" AS ReferencedColumn,\n")
            f.write("    fk.on_update AS OnUpdate,\n")
            f.write("    fk.on_delete AS OnDelete,\n")
            f.write("    fk.match AS MatchType\n")
            f.write("FROM sqlite_master m\n")
            f.write("CROSS JOIN pragma_foreign_key_list(m.name) fk\n")
            f.write("WHERE m.type = 'table' \n")
            f.write("    AND m.name NOT LIKE 'sqlite_%'\n")
            f.write("ORDER BY m.name, fk.id, fk.seq;\n")
            f.write("```\n\n")
            f.write("## Results\n\n")
            
            # Get table and columns
            f.write("### Table and Columns\n\n")
            table_columns_query = """
            SELECT 
                m.name || '.' || p.name AS TableColumn,
                p.type AS DataType
            FROM sqlite_master m
            CROSS JOIN pragma_table_info(m.name) p
            WHERE m.type = 'table' 
                AND m.name NOT LIKE 'sqlite_%'
            ORDER BY m.name, p.cid;
            """
            
            table_columns = ExecuteQuery(cursor, table_columns_query)
            for row in table_columns:
                f.write(f"{row[0]}\t{row[1]}\n")
            
            # Get indexes
            f.write("\n### Indexes\n\n")
            indexes_query = """
            SELECT 
                m.name AS TableName,
                i.name AS IndexName,
                i."unique" AS IsUnique,
                i."origin" AS Origin,
                i."partial" AS IsPartial
            FROM sqlite_master m
            CROSS JOIN pragma_index_list(m.name) i
            WHERE m.type = 'table' 
                AND m.name NOT LIKE 'sqlite_%'
            ORDER BY m.name, i.seq;
            """
            
            indexes = ExecuteQuery(cursor, indexes_query)
            for row in indexes:
                f.write(f"{row[0]}\t{row[1]}\t{row[2]}\t{row[3]}\t{row[4]}\n")
            
            # Get index columns
            f.write("\n### Index Columns\n\n")
            index_columns_query = """
            SELECT 
                m.name AS TableName,
                i.name AS IndexName,
                ic.name AS ColumnName,
                ic.seqno AS ColumnSequence
            FROM sqlite_master m
            CROSS JOIN pragma_index_list(m.name) i
            CROSS JOIN pragma_index_info(i.name) ic
            WHERE m.type = 'table' 
                AND m.name NOT LIKE 'sqlite_%'
            ORDER BY m.name, i.seq, ic.seqno;
            """
            
            index_columns = ExecuteQuery(cursor, index_columns_query)
            for row in index_columns:
                f.write(f"{row[0]}\t{row[1]}\t{row[2]}\t{row[3]}\n")
            
            # Get foreign key constraints
            f.write("\n### Foreign Key Constraints\n\n")
            foreign_keys_query = """
            SELECT 
                m.name AS TableName,
                fk.id AS ConstraintId,
                fk.seq AS ColumnSequence,
                fk."table" AS ReferencedTable,
                fk."from" AS ColumnName,
                fk."to" AS ReferencedColumn,
                fk.on_update AS OnUpdate,
                fk.on_delete AS OnDelete,
                fk.match AS MatchType
            FROM sqlite_master m
            CROSS JOIN pragma_foreign_key_list(m.name) fk
            WHERE m.type = 'table' 
                AND m.name NOT LIKE 'sqlite_%'
            ORDER BY m.name, fk.id, fk.seq;
            """
            
            foreign_keys = ExecuteQuery(cursor, foreign_keys_query)
            for row in foreign_keys:
                f.write(f"{row[0]}\t{row[1]}\t{row[2]}\t{row[3]}\t{row[4]}\t{row[5]}\t{row[6]}\t{row[7]}\t{row[8]}\n")
        
        conn.close()
        print(f"DatabaseSchema.md updated successfully at: {output_path}")
        return True
        
    except Exception as e:
        print(f"Error generating DatabaseSchema.md: {e}")
        return False

if __name__ == "__main__":
    print("Updating DatabaseSchema.md...")
    success = GenerateDatabaseSchema()
    if success:
        print("✅ DatabaseSchema.md updated successfully")
    else:
        print("❌ Failed to update DatabaseSchema.md")
