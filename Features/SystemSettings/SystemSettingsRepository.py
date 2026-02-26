#!/usr/bin/env python3
"""
SystemSettingsRepository.py - Repository for system settings data access
"""

from typing import Optional, List, Dict, Any
from Core.Database.BaseRepository import BaseRepository
from Core.Logging.LoggingService import LoggingService


class SystemSettingsRepository(BaseRepository):
    """Repository for system settings CRUD operations."""

    def GetSystemSetting(self, SettingKey: str) -> Optional[str]:
        """Get a system setting value by key."""
        query = "SELECT SettingValue FROM SystemSettings WHERE SettingKey = %s"
        rows = self.ExecuteQuery(query, (SettingKey,))

        if not rows:
            return None

        return rows[0]['SettingValue']

    def GetAllSystemSettings(self) -> List[Dict[str, Any]]:
        """Get all system settings."""
        query = "SELECT Id, SettingKey, SettingValue, Description, DataType, LastModified FROM SystemSettings ORDER BY SettingKey"
        rows = self.ExecuteQuery(query)

        settings = []
        for row in rows:
            settings.append({
                'Id': row['Id'],
                'SettingKey': row['SettingKey'],
                'SettingValue': row['SettingValue'],
                'Description': row['Description'],
                'DataType': row['DataType'],
                'LastModified': row['LastModified']
            })

        return settings

    def GetScanDirectories(self) -> List[Dict[str, str]]:
        """Get all scan directory settings (ScanDir1, ScanDir2, etc.)."""
        query = "SELECT SettingKey, SettingValue, Description FROM SystemSettings WHERE SettingKey LIKE 'ScanDir%%' ORDER BY SettingKey"
        rows = self.ExecuteQuery(query)

        scanDirs = []
        for row in rows:
            if row['SettingValue'] and row['SettingValue'].strip():
                scanDirs.append({
                    'Key': row['SettingKey'],
                    'Path': row['SettingValue'],
                    'Description': row['Description']
                })

        return scanDirs

    def AddOrUpdateSystemSetting(self, SettingKey: str, SettingValue: str, Description: str, DataType: str = 'string') -> bool:
        """Add or update a system setting."""
        try:
            existingValue = self.GetSystemSetting(SettingKey)

            if existingValue is not None:
                query = """
                    UPDATE SystemSettings
                    SET SettingValue = %s, Description = %s, DataType = %s, LastModified = NOW()
                    WHERE SettingKey = %s
                """
                self.ExecuteNonQuery(query, (SettingValue, Description, DataType, SettingKey))
            else:
                query = """
                    INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified)
                    VALUES (%s, %s, %s, %s, NOW())
                """
                self.ExecuteNonQuery(query, (SettingKey, SettingValue, Description, DataType))

            return True

        except Exception as e:
            LoggingService.LogException(f"Error adding/updating system setting {SettingKey}", e, "AddOrUpdateSystemSetting", "SystemSettingsRepository")
            return False

    def DeleteSystemSetting(self, SettingKey: str) -> bool:
        """Delete a system setting."""
        try:
            query = "DELETE FROM SystemSettings WHERE SettingKey = %s"
            affectedRows = self.ExecuteNonQuery(query, (SettingKey,))
            return affectedRows > 0

        except Exception as e:
            LoggingService.LogException(f"Error deleting system setting {SettingKey}", e, "DeleteSystemSetting", "SystemSettingsRepository")
            return False

    def RunMigrations(self):
        """Run database schema migrations. Safe to call multiple times."""
        try:
            connection = self.DatabaseService.GetConnection()
            try:
                cursor = connection.cursor()

                def column_exists(table_name, column_name):
                    cursor.execute("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = %s AND column_name = %s
                    """, (table_name.lower(), column_name.lower()))
                    return cursor.fetchone() is not None

                if not column_exists('TranscodeQueue', 'ProcessingMode'):
                    cursor.execute("ALTER TABLE TranscodeQueue ADD COLUMN ProcessingMode TEXT DEFAULT 'Transcode'")
                    connection.commit()
                    LoggingService.LogInfo("Added ProcessingMode column to TranscodeQueue", "SystemSettingsRepository", "RunMigrations")

                if not column_exists('MediaFiles', 'AudioCodec'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN AudioCodec TEXT")
                    connection.commit()
                    LoggingService.LogInfo("Added AudioCodec column to MediaFiles", "SystemSettingsRepository", "RunMigrations")
                if not column_exists('MediaFiles', 'SubtitleFormats'):
                    cursor.execute("ALTER TABLE MediaFiles ADD COLUMN SubtitleFormats TEXT")
                    connection.commit()
                    LoggingService.LogInfo("Added SubtitleFormats column to MediaFiles", "SystemSettingsRepository", "RunMigrations")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS JellyfinOperations (
                        LogFileName TEXT PRIMARY KEY,
                        OperationType TEXT NOT NULL,
                        FilePath TEXT,
                        FileName TEXT,
                        VideoCodec TEXT,
                        AudioCodec TEXT,
                        Container TEXT,
                        Resolution TEXT,
                        SubtitleCodecs TEXT,
                        Reason TEXT,
                        TranscodeActions TEXT,
                        LogDate TEXT,
                        ImportedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                for col in ['SubtitleCodecs', 'TranscodeActions',
                            'DestResolution', 'DestProfile', 'DestLevel', 'DestPixelFormat', 'DestFormat']:
                    if not column_exists('JellyfinOperations', col):
                        try:
                            cursor.execute(f"ALTER TABLE JellyfinOperations ADD COLUMN {col} TEXT")
                            cursor.execute("DELETE FROM JellyfinOperations")
                        except Exception:
                            pass

                connection.commit()
            finally:
                self.DatabaseService.CloseConnection(connection)
        except Exception as e:
            LoggingService.LogWarning(f"Migration warning: {e}", "SystemSettingsRepository", "RunMigrations")
