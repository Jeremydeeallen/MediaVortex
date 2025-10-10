#!/usr/bin/env python3
"""
AddCpuThreadLimitSetting.py - Add CPU thread limit system setting
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

def AddCpuThreadLimitSetting():
    """Add CPU thread limit system setting to database."""
    try:
        LoggingService.LogInfo("Starting CPU thread limit setting addition", "AddCpuThreadLimitSetting", "AddCpuThreadLimitSetting")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Add MaxCpuThreads setting with default value of 16 (half of 32 cores for i9-14900KF)
        Success = DatabaseManagerInstance.AddOrUpdateSystemSetting(
            SettingKey='MaxCpuThreads',
            SettingValue='16',
            Description='Maximum number of CPU threads for FFmpeg transcoding. Recommended: 16 for i9-14900KF (32 cores) to prevent system overload.',
            DataType='integer'
        )
        
        if Success:
            LoggingService.LogInfo("Successfully added MaxCpuThreads system setting", "AddCpuThreadLimitSetting", "AddCpuThreadLimitSetting")
            print("✅ Successfully added MaxCpuThreads system setting with default value: 16")
            
            # Verify the setting was added
            SettingValue = DatabaseManagerInstance.GetSystemSetting('MaxCpuThreads')
            if SettingValue:
                print(f"✅ Verified setting: MaxCpuThreads = {SettingValue}")
            else:
                print("❌ Warning: Setting was not found after addition")
        else:
            LoggingService.LogError("Failed to add MaxCpuThreads system setting", "AddCpuThreadLimitSetting", "AddCpuThreadLimitSetting")
            print("❌ Failed to add MaxCpuThreads system setting")
            
    except Exception as e:
        LoggingService.LogException("Exception adding CPU thread limit setting", e, "AddCpuThreadLimitSetting", "AddCpuThreadLimitSetting")
        print(f"❌ Exception: {str(e)}")

if __name__ == "__main__":
    AddCpuThreadLimitSetting()
