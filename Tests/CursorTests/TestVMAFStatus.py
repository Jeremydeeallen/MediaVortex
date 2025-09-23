#!/usr/bin/env python3
"""
Test VMAF Status API Response
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager
from Services.VMAFQueueBusinessService import VMAFQueueBusinessService
import json

def TestVMAFStatus():
    """Test the VMAF status API response."""
    try:
        # Test the VMAF status logic
        vmaf_service = VMAFQueueBusinessService()
        status = vmaf_service.GetVMAFQueueStatus()
        
        print('=== VMAF STATUS API RESPONSE ===')
        print(f'IsRunning: {status.get("IsRunning", "Not found")}')
        print(f'Total items: {status.get("TotalItems", "Not found")}')
        print(f'Running items: {status.get("RunningItems", "Not found")}')
        print(f'Pending items: {status.get("PendingItems", "Not found")}')
        print(f'Completed items: {status.get("CompletedItems", "Not found")}')
        print(f'Failed items: {status.get("FailedItems", "Not found")}')
        
        print('\nFull response:')
        print(json.dumps(status, indent=2, default=str))
        
        # Check what the UI logic should do
        is_running = status.get("IsRunning", False)
        print(f'\n=== UI LOGIC ANALYSIS ===')
        print(f'IsRunning: {is_running}')
        
        if is_running:
            print('UI should show: Stop button active, Start button hidden')
        else:
            print('UI should show: Start button active, Stop button hidden')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    TestVMAFStatus()
