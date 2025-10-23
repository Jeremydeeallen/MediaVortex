#!/usr/bin/env python3
"""
AddQualityTestHardwareAccelerationSetting.py - Add hardware acceleration system setting for quality testing
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

def AddQualityTestHardwareAccelerationSetting():
    """Add hardware acceleration system setting to database."""
    try:
        LoggingService.LogInfo("Starting quality test hardware acceleration setting addition", "AddQualityTestHardwareAccelerationSetting", "AddQualityTestHardwareAccelerationSetting")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Add UseHardwareAcceleration setting with default value of True (NVIDIA enabled by default)
        Success = DatabaseManagerInstance.AddOrUpdateSystemSetting(
            SettingKey='UseHardwareAcceleration',
            SettingValue='True',
            Description='Enable NVIDIA hardware acceleration for quality testing VMAF calculations. When enabled, uses -hwaccel cuda for faster processing. Requires NVIDIA GPU.',
            DataType='boolean'
        )
        
        if Success:
            LoggingService.LogInfo("Successfully added UseHardwareAcceleration system setting", "AddQualityTestHardwareAccelerationSetting", "AddQualityTestHardwareAccelerationSetting")
            print("✅ Successfully added UseHardwareAcceleration system setting with default value: True")
            
            # Verify the setting was added
            SettingValue = DatabaseManagerInstance.GetSystemSetting('UseHardwareAcceleration')
            if SettingValue:
                print(f"✅ Verified setting: UseHardwareAcceleration = {SettingValue}")
            else:
                print("❌ Warning: Setting was not found after addition")
        else:
            LoggingService.LogError("Failed to add UseHardwareAcceleration system setting", "AddQualityTestHardwareAccelerationSetting", "AddQualityTestHardwareAccelerationSetting")
            print("❌ Failed to add UseHardwareAcceleration system setting")
            
    except Exception as e:
        LoggingService.LogException("Error adding quality test hardware acceleration setting", e, "AddQualityTestHardwareAccelerationSetting", "AddQualityTestHardwareAccelerationSetting")
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    AddQualityTestHardwareAccelerationSetting()

