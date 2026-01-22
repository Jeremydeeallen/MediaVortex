#!/usr/bin/env python3
"""
Add CPU Affinity Settings to SystemSettings Table
Database initialization script for dynamic CPU affinity feature
"""

import sys
import os

# Add the project root to the Python path
ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def AddCpuAffinitySettings():
    """Add CPU affinity settings to SystemSettings table."""
    try:
        LoggingService.LogInfo("Starting CPU affinity settings initialization", "AddCpuAffinitySettings", "AddCpuAffinitySettings")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Define the CPU affinity settings
        CpuAffinitySettings = [
            {
                'SettingKey': 'CpuAffinityEnabled',
                'SettingValue': 'true',
                'Description': 'Enable dynamic CPU affinity selection and monitoring',
                'DataType': 'boolean'
            },
            {
                'SettingKey': 'CpuAffinityTemperatureThreshold',
                'SettingValue': '98.0',
                'Description': 'Temperature threshold in Celsius for core migration during active transcoding',
                'DataType': 'float'
            },
            {
                'SettingKey': 'CpuAffinityMonitoringInterval',
                'SettingValue': '45',
                'Description': 'Seconds between temperature checks during active transcoding',
                'DataType': 'integer'
            },
            {
                'SettingKey': 'CpuAffinityCoolingWaitEnabled',
                'SettingValue': 'true',
                'Description': 'Wait for CPU cores to cool below target temperature after job completion before proceeding',
                'DataType': 'boolean'
            },
            {
                'SettingKey': 'CpuAffinityCoolingWaitTargetTemp',
                'SettingValue': '60.0',
                'Description': 'Target temperature in Celsius to wait for after job completion (50-85°C)',
                'DataType': 'float'
            },
            {
                'SettingKey': 'CpuAffinityCoolingWaitMaxSeconds',
                'SettingValue': '300',
                'Description': 'Maximum seconds to wait for cooling after job completion (30-300 seconds)',
                'DataType': 'integer'
            }
        ]
        
        AddedCount = 0
        UpdatedCount = 0
        
        for Setting in CpuAffinitySettings:
            # Check if setting already exists
            ExistingValue = DatabaseManagerInstance.GetSystemSetting(Setting['SettingKey'])
            
            if ExistingValue is None:
                # Add new setting
                Result = DatabaseManagerInstance.AddOrUpdateSystemSetting(
                    Setting['SettingKey'],
                    Setting['SettingValue'],
                    Setting['Description'],
                    Setting['DataType']
                )
                
                if Result:
                    LoggingService.LogInfo(f"Added CPU affinity setting: {Setting['SettingKey']} = {Setting['SettingValue']}", 
                                         "AddCpuAffinitySettings", "AddCpuAffinitySettings")
                    AddedCount += 1
                else:
                    LoggingService.LogError(f"Failed to add CPU affinity setting: {Setting['SettingKey']}", 
                                           "AddCpuAffinitySettings", "AddCpuAffinitySettings")
            else:
                # Update existing setting (to ensure description and data type are correct)
                Result = DatabaseManagerInstance.AddOrUpdateSystemSetting(
                    Setting['SettingKey'],
                    Setting['SettingValue'],
                    Setting['Description'],
                    Setting['DataType']
                )
                
                if Result:
                    LoggingService.LogInfo(f"Updated CPU affinity setting: {Setting['SettingKey']} = {Setting['SettingValue']}", 
                                         "AddCpuAffinitySettings", "AddCpuAffinitySettings")
                    UpdatedCount += 1
        
        LoggingService.LogInfo(f"CPU affinity settings initialization completed. Added {AddedCount} new settings, updated {UpdatedCount} existing settings.", 
                              "AddCpuAffinitySettings", "AddCpuAffinitySettings")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error adding CPU affinity settings", e, "AddCpuAffinitySettings", "AddCpuAffinitySettings")
        return False


if __name__ == "__main__":
    AddCpuAffinitySettings()

