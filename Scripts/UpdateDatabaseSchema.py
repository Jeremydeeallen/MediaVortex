#!/usr/bin/env python3
"""
Development script to update DatabaseSchema.md with current database schema.
This script queries the database and updates the documentation file.
"""

import os
import sys
import sqlite3
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from Services.DatabaseService import DatabaseService


class DatabaseSchemaUpdater:
    """Updates the DatabaseSchema.md file with current database structure."""
    
    def __init__(self):
        self.DatabaseService = DatabaseService()
        self.SchemaFilePath = Path(__file__).parent.parent / "Docs" / "DatabaseSchema.md"
    
    def GetTableAndColumns(self) -> list:
        """Get all tables and their columns."""
        query = """
        SELECT 
            m.name || '.' || p.name AS TableColumn,
            p.type AS DataType
        FROM sqlite_master m
        CROSS JOIN pragma_table_info(m.name) p
        WHERE m.type = 'table' 
            AND m.name NOT LIKE 'sqlite_%'
        ORDER BY m.name, p.cid;
        """
        return self.DatabaseService.ExecuteQuery(query)
    
    def GetIndexes(self) -> list:
        """Get all indexes."""
        query = """
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
        return self.DatabaseService.ExecuteQuery(query)
    
    def GetIndexColumns(self) -> list:
        """Get all index columns."""
        query = """
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
        return self.DatabaseService.ExecuteQuery(query)
    
    def FormatTableAndColumns(self, rows: list) -> str:
        """Format table and columns data for markdown."""
        lines = []
        for row in rows:
            lines.append(f"{row['TableColumn']}\t{row['DataType']}")
        return "\n".join(lines)
    
    def FormatIndexes(self, rows: list) -> str:
        """Format indexes data for markdown."""
        lines = []
        for row in rows:
            lines.append(f"{row['TableName']}\t{row['IndexName']}\t{row['IsUnique']}\t{row['Origin']}\t{row['IsPartial']}")
        return "\n".join(lines)
    
    def FormatIndexColumns(self, rows: list) -> str:
        """Format index columns data for markdown."""
        lines = []
        for row in rows:
            lines.append(f"{row['TableName']}\t{row['IndexName']}\t{row['ColumnName']}\t{row['ColumnSequence']}")
        return "\n".join(lines)
    
    def UpdateSchemaFile(self):
        """Update the DatabaseSchema.md file with current database structure."""
        try:
            print("Querying database for current schema...")
            
            # Get current schema data
            TableColumns = self.GetTableAndColumns()
            Indexes = self.GetIndexes()
            IndexColumns = self.GetIndexColumns()
            
            print(f"Found {len(TableColumns)} table columns")
            print(f"Found {len(Indexes)} indexes")
            print(f"Found {len(IndexColumns)} index columns")
            
            # Read the current file
            with open(self.SchemaFilePath, 'r', encoding='utf-8') as file:
                Content = file.read()
            
            # Replace the results sections
            Content = self.ReplaceSection(Content, "### Table and Columns", self.FormatTableAndColumns(TableColumns))
            Content = self.ReplaceSection(Content, "### Indexes", self.FormatIndexes(Indexes))
            Content = self.ReplaceSection(Content, "### Index Columns", self.FormatIndexColumns(IndexColumns))
            
            # Write the updated content
            with open(self.SchemaFilePath, 'w', encoding='utf-8') as file:
                file.write(Content)
            
            print(f"Successfully updated {self.SchemaFilePath}")
            
        except Exception as e:
            print(f"Error updating schema file: {str(e)}")
            raise
    
    def ReplaceSection(self, Content: str, SectionHeader: str, NewContent: str) -> str:
        """Replace a section in the markdown content."""
        # Find the section header
        StartMarker = f"{SectionHeader}\n\n"
        StartIndex = Content.find(StartMarker)
        
        if StartIndex == -1:
            print(f"Warning: Could not find section '{SectionHeader}'")
            return Content
        
        # Find the next section or end of file
        NextSectionIndex = Content.find("\n### ", StartIndex + len(StartMarker))
        if NextSectionIndex == -1:
            # This is the last section
            EndIndex = len(Content)
        else:
            EndIndex = NextSectionIndex
        
        # Replace the content
        BeforeSection = Content[:StartIndex + len(StartMarker)]
        AfterSection = Content[EndIndex:]
        
        return BeforeSection + NewContent + "\n" + AfterSection


def main():
    """Main function to run the schema updater."""
    try:
        Updater = DatabaseSchemaUpdater()
        Updater.UpdateSchemaFile()
        print("Database schema update completed successfully!")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
