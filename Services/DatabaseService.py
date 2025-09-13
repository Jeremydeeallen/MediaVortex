import sqlite3
import os
from typing import Optional


class DatabaseService:
    """Low-level database connection service. The only file allowed to interact with /Data/MediaVortex.db"""
    
    def __init__(self, database_path: str = None):
        if database_path is None:
            # Get the directory of this file and navigate to Data folder
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            database_path = os.path.join(project_root, "Data", "MediaVortex.db")
        
        self.DatabasePath = database_path
        self._connection: Optional[sqlite3.Connection] = None
    
    def GetConnection(self) -> sqlite3.Connection:
        """Get a database connection. Creates a new one for each call to handle threading."""
        connection = sqlite3.connect(self.DatabasePath)
        connection.row_factory = sqlite3.Row  # Enable column access by name
        return connection
    
    def CloseConnection(self):
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def ExecuteQuery(self, query: str, parameters: tuple = ()) -> list:
        """Execute a SELECT query and return results."""
        connection = self.GetConnection()
        try:
            cursor = connection.cursor()
            cursor.execute(query, parameters)
            return cursor.fetchall()
        finally:
            connection.close()
    
    def ExecuteNonQuery(self, query: str, parameters: tuple = ()) -> int:
        """Execute an INSERT, UPDATE, or DELETE query and return affected rows."""
        connection = self.GetConnection()
        try:
            cursor = connection.cursor()
            cursor.execute(query, parameters)
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()
    
    def ExecuteScalar(self, query: str, parameters: tuple = ()):
        """Execute a query and return the first column of the first row."""
        connection = self.GetConnection()
        try:
            cursor = connection.cursor()
            cursor.execute(query, parameters)
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            connection.close()
    
    def GetLastInsertId(self) -> int:
        """Get the ID of the last inserted row."""
        # This method is no longer needed since we close connections immediately
        # The lastrowid should be captured right after the insert
        return 0
