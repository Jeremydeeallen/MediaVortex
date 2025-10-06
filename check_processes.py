#!/usr/bin/env python3
"""
Check Running Processes for Quality Testing
"""

import psutil
import os

def CheckQualityTestingProcesses():
    """Check if QualityTesting processes are running."""
    try:
        print('=== CHECKING RUNNING PROCESSES ===')
        
        quality_processes = []
        
        # Check for QualityTestWorker processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                if 'QualityTestWorker' in cmdline or 'QualityTestingService' in cmdline:
                    quality_processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cmdline': cmdline
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if quality_processes:
            print(f'Found {len(quality_processes)} QualityTesting processes:')
            for proc in quality_processes:
                print(f'  PID {proc["pid"]}: {proc["name"]} - {proc["cmdline"]}')
        else:
            print('No QualityTesting processes found')
            
        return len(quality_processes) > 0
        
    except Exception as e:
        print(f'Error checking processes: {e}')
        return False

if __name__ == "__main__":
    CheckQualityTestingProcesses()
