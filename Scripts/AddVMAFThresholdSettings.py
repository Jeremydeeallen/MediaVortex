#!/usr/bin/env python3
"""
Add VMAF Threshold Settings to SystemSettings Table
Database initialization script for auto-replace VMAF feature
"""

import sys
import os
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def AddVMAFThresholdSettings():
    """Add VMAF threshold settings to SystemSettings table."""
    try:
        LoggingService.LogInfo("Starting VMAF threshold settings initialization", "AddVMAFThresholdSettings", "AddVMAFThresholdSettings")
        
        database_manager = DatabaseManager()
        
        # Define the VMAF threshold settings
        vmaf_settings = [
            {
                'SettingKey': 'VMAFAutoReplaceMinThreshold',
                'SettingValue': '88.0',
                'Description': 'Minimum VMAF score for automatic file replacement',
                'DataType': 'REAL'
            },
            {
                'SettingKey': 'VMAFAutoReplaceMaxThreshold', 
                'SettingValue': '94.0',
                'Description': 'Maximum VMAF score for automatic file replacement',
                'DataType': 'REAL'
            }
        ]
        
        added_count = 0
        for setting in vmaf_settings:
            # Check if setting already exists
            existing_query = """
                SELECT Id FROM SystemSettings 
                WHERE SettingKey = ?
            """
            existing_result = database_manager.DatabaseService.ExecuteQuery(existing_query, (setting['SettingKey'],))
            
            if not existing_result:
                # Insert new setting
                insert_query = """
                    INSERT INTO SystemSettings (SettingKey, SettingValue, Description, DataType, LastModified)
                    VALUES (?, ?, ?, ?, ?)
                """
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                result = database_manager.DatabaseService.ExecuteNonQuery(insert_query, (
                    setting['SettingKey'],
                    setting['SettingValue'],
                    setting['Description'],
                    setting['DataType'],
                    current_time
                ))
                
                if result:
                    LoggingService.LogInfo(f"Added VMAF setting: {setting['SettingKey']} = {setting['SettingValue']}", 
                                         "AddVMAFThresholdSettings", "AddVMAFThresholdSettings")
                    added_count += 1
                else:
                    LoggingService.LogError(f"Failed to add VMAF setting: {setting['SettingKey']}", 
                                           "AddVMAFThresholdSettings", "AddVMAFThresholdSettings")
            else:
                LoggingService.LogInfo(f"VMAF setting already exists: {setting['SettingKey']}", 
                                     "AddVMAFThresholdSettings", "AddVMAFThresholdSettings")
        
        LoggingService.LogInfo(f"VMAF threshold settings initialization completed. Added {added_count} new settings.", 
                              "AddVMAFThresholdSettings", "AddVMAFThresholdSettings")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error adding VMAF threshold settings", e, "AddVMAFThresholdSettings", "AddVMAFThresholdSettings")
        return False


if __name__ == "__main__":
    AddVMAFThresholdSettings()

