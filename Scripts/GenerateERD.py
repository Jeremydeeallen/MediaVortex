#!/usr/bin/env python3
"""
GenerateERD.py

Generates a Mermaid erDiagram by querying PostgreSQL information_schema.
Includes actual foreign keys and inferred relationships from column naming conventions.

Output: Docs/ERD.md (renderable in GitHub, VS Code, etc.)
Usage: py Scripts/GenerateERD.py
"""

import os
import sys
import re

# Add parent directory to path so we can import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.DatabaseService import DatabaseService


# PostgreSQL type to Mermaid type mapping
TYPE_MAP = {
    "integer": "int",
    "bigint": "bigint",
    "smallint": "smallint",
    "serial": "serial",
    "bigserial": "bigserial",
    "boolean": "bool",
    "text": "text",
    "character varying": "varchar",
    "character": "char",
    "real": "float",
    "double precision": "double",
    "numeric": "decimal",
    "timestamp without time zone": "timestamp",
    "timestamp with time zone": "timestamptz",
    "date": "date",
    "time without time zone": "time",
    "json": "json",
    "jsonb": "jsonb",
    "bytea": "bytea",
    "bit": "bit",
    "USER-DEFINED": "enum",
}


def MapType(PgType):
    """Map a PostgreSQL data type to a shorter Mermaid-friendly type."""
    return TYPE_MAP.get(PgType, PgType)


def GetTablesAndColumns(Db):
    """Query all tables and their columns from information_schema."""
    Rows = Db.ExecuteQuery("""
        SELECT
            c.table_name AS TableName,
            c.column_name AS ColumnName,
            c.data_type AS DataType,
            c.is_nullable AS IsNullable,
            c.column_default AS ColumnDefault,
            CASE WHEN pk.column_name IS NOT NULL THEN 'YES' ELSE 'NO' END AS IsPrimaryKey
        FROM information_schema.columns c
        LEFT JOIN (
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_schema = 'public'
        ) pk ON c.table_name = pk.table_name AND c.column_name = pk.column_name
        WHERE c.table_schema = 'public'
        ORDER BY c.table_name, c.ordinal_position
    """)
    return Rows


def GetForeignKeys(Db):
    """Query actual foreign key constraints from the database."""
    Rows = Db.ExecuteQuery("""
        SELECT
            tc.table_name AS SourceTable,
            kcu.column_name AS SourceColumn,
            ccu.table_name AS TargetTable,
            ccu.column_name AS TargetColumn
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
        ORDER BY tc.table_name
    """)
    return Rows


def InferRelationships(Tables, ExistingForeignKeys):
    """Infer logical relationships from column naming conventions.

    Patterns detected:
    - ColumnName ending in 'Id' where a matching table exists (e.g., ProfileId -> Profiles)
    - ColumnName like 'TranscodeAttemptId' -> TranscodeAttempts
    """
    # Build set of existing FK relationships to avoid duplicates
    ExistingSet = set()
    for Fk in ExistingForeignKeys:
        ExistingSet.add((Fk['SourceTable'].lower(), Fk['SourceColumn'].lower()))

    # Build set of table names for matching
    TableNames = set(Tables.keys())
    TableNameLower = {T.lower(): T for T in TableNames}

    Inferred = []

    for TableName, Columns in Tables.items():
        for Col in Columns:
            ColName = Col['ColumnName']

            # Skip if this column already has an actual FK
            if (TableName.lower(), ColName.lower()) in ExistingSet:
                continue

            # Check if column name ends with 'Id' and has a matching table
            if ColName.lower().endswith('id') and ColName.lower() != 'id':
                # Extract the base name (e.g., 'ProfileId' -> 'Profile')
                BaseName = ColName[:-2]  # Remove 'Id'

                # Try common pluralization patterns
                Candidates = [
                    BaseName + 's',        # Profile -> Profiles
                    BaseName + 'es',       # Status -> Statuses
                    BaseName,              # Exact match
                ]

                # Special cases
                if BaseName.endswith('y'):
                    Candidates.append(BaseName[:-1] + 'ies')  # Category -> Categories

                for Candidate in Candidates:
                    if Candidate.lower() in TableNameLower and Candidate.lower() != TableName.lower():
                        TargetTable = TableNameLower[Candidate.lower()]
                        Inferred.append({
                            'SourceTable': TableName,
                            'SourceColumn': ColName,
                            'TargetTable': TargetTable,
                            'TargetColumn': 'Id',
                        })
                        break

    return Inferred


def GenerateERD():
    """Generate the Mermaid ERD and write to Docs/ERD.md."""
    try:
        Db = DatabaseService()

        # Gather data
        ColumnRows = GetTablesAndColumns(Db)
        ForeignKeys = GetForeignKeys(Db)

        # Organize columns by table
        Tables = {}
        for Row in ColumnRows:
            TableName = Row['TableName']
            if TableName not in Tables:
                Tables[TableName] = []
            Tables[TableName].append(Row)

        # Infer additional relationships
        InferredRelationships = InferRelationships(Tables, ForeignKeys)

        # Build Mermaid ERD
        Lines = []
        Lines.append("# Entity Relationship Diagram")
        Lines.append("")
        Lines.append("Auto-generated by `Scripts/GenerateERD.py` from the PostgreSQL database.")
        Lines.append("Renderable in GitHub, VS Code (with Mermaid extension), or [mermaid.live](https://mermaid.live).")
        Lines.append("")
        Lines.append("```mermaid")
        Lines.append("erDiagram")

        # Write relationships first (actual FKs)
        if ForeignKeys:
            Lines.append("")
            Lines.append("    %% Actual Foreign Keys")
            for Fk in ForeignKeys:
                SourceTable = Fk['SourceTable']
                TargetTable = Fk['TargetTable']
                SourceColumn = Fk['SourceColumn']
                Lines.append(f"    {TargetTable} ||--o{{ {SourceTable} : \"{SourceColumn}\"")

        # Write inferred relationships
        if InferredRelationships:
            Lines.append("")
            Lines.append("    %% Inferred Relationships (no FK constraint)")
            for Rel in InferredRelationships:
                SourceTable = Rel['SourceTable']
                TargetTable = Rel['TargetTable']
                SourceColumn = Rel['SourceColumn']
                Lines.append(f"    {TargetTable} ||..o{{ {SourceTable} : \"{SourceColumn}\"")

        # Write table definitions
        for TableName in sorted(Tables.keys()):
            Columns = Tables[TableName]
            Lines.append("")
            Lines.append(f"    {TableName} {{")
            for Col in Columns:
                MermaidType = MapType(Col['DataType'])
                ColName = Col['ColumnName']
                Markers = []
                if Col['IsPrimaryKey'] == 'YES':
                    Markers.append("PK")
                # Check if this column is a FK
                IsFk = False
                for Fk in ForeignKeys:
                    if Fk['SourceTable'] == TableName and Fk['SourceColumn'].lower() == ColName.lower():
                        IsFk = True
                        break
                if not IsFk:
                    for Rel in InferredRelationships:
                        if Rel['SourceTable'] == TableName and Rel['SourceColumn'].lower() == ColName.lower():
                            IsFk = True
                            break
                if IsFk:
                    Markers.append("FK")

                MarkerStr = ", ".join(Markers)
                if MarkerStr:
                    Lines.append(f"        {MermaidType} {ColName} {MarkerStr}")
                else:
                    Lines.append(f"        {MermaidType} {ColName}")
            Lines.append("    }")

        Lines.append("```")
        Lines.append("")

        # Add legend
        Lines.append("## Legend")
        Lines.append("")
        Lines.append("- **Solid lines** (`||--o{`): Actual foreign key constraints in the database")
        Lines.append("- **Dashed lines** (`||..o{`): Inferred relationships from column naming conventions (no FK constraint)")
        Lines.append("- **PK**: Primary Key")
        Lines.append("- **FK**: Foreign Key (actual or inferred)")
        Lines.append("")

        # Write output
        ScriptDir = os.path.dirname(os.path.abspath(__file__))
        OutputPath = os.path.join(ScriptDir, "..", "Docs", "ERD.md")
        OutputPath = os.path.normpath(OutputPath)

        os.makedirs(os.path.dirname(OutputPath), exist_ok=True)

        with open(OutputPath, 'w', encoding='utf-8') as F:
            F.write('\n'.join(Lines))

        print(f"ERD generated successfully: {OutputPath}")
        print(f"  Tables: {len(Tables)}")
        print(f"  Actual foreign keys: {len(ForeignKeys)}")
        print(f"  Inferred relationships: {len(InferredRelationships)}")
        return True

    except Exception as E:
        print(f"Error generating ERD: {E}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Generating Mermaid ERD...")
    Success = GenerateERD()
    if not Success:
        sys.exit(1)
