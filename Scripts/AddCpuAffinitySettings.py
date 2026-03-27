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
                'Description': 'Enable topology-aware CPU affinity for FFmpeg processes',
                'DataType': 'boolean'
            },
            {
                'SettingKey': 'TranscodeCoreTier',
                'SettingValue': 'performance',
                'Description': 'Core tier for transcode jobs: performance (P-cores), efficiency (E-cores), or all',
                'DataType': 'string'
            },
            {
                'SettingKey': 'QualityTestCoreTier',
                'SettingValue': 'efficiency',
                'Description': 'Core tier for quality test jobs: performance (P-cores), efficiency (E-cores), or all',
                'DataType': 'string'
            },
            {
                'SettingKey': 'ThermalGateEnabled',
                'SettingValue': 'true',
                'Description': 'Block new jobs when system temperature is too high',
                'DataType': 'boolean'
            },
            {
                'SettingKey': 'ThermalGateMaxTemp',
                'SettingValue': '80.0',
                'Description': 'Per-core temperature threshold for "cool enough" to start new jobs',
                'DataType': 'float'
            },
            {
                'SettingKey': 'ThermalGateMinCoolCores',
                'SettingValue': '8',
                'Description': 'Minimum number of cool cores required before starting new jobs',
                'DataType': 'integer'
            },
            {
                'SettingKey': 'ThermalPauseCriticalTemp',
                'SettingValue': '90.0',
                'Description': 'Average CPU temperature that pauses all new job starts',
                'DataType': 'float'
            },
            {
                'SettingKey': 'ThermalGateMaxWaitSeconds',
                'SettingValue': '600',
                'Description': 'Maximum seconds to wait for thermal clearance before allowing job anyway',
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

