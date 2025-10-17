#!/usr/bin/env python3
"""
StopAllTranscodeServices.py
Script to stop all running TranscodeService instances and clean up the database.
"""

import sys
import os
import psutil
import time
from datetime import datetime

# Add parent directory to path to import shared services
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)
sys.path.append(root_dir)

# Import with full path
sys.path.insert(0, root_dir)
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def StopAllTranscodeServices():
    """Stop all running TranscodeService instances and clean up database."""
    try:
        print("=== STOPPING ALL TRANSCODESERVICE INSTANCES ===")
        
        # Initialize database manager
        db_manager = DatabaseManager()
        
        # Step 1: Find all TranscodeService processes by name
        transcode_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'TranscodeService':
                    transcode_processes.append(proc)
                    print(f"Found TranscodeService process: PID {proc.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not transcode_processes:
            print("No TranscodeService processes found.")
        else:
            print(f"Found {len(transcode_processes)} TranscodeService processes.")
            
            # Stop each process
            for proc in transcode_processes:
                try:
                    print(f"Stopping TranscodeService PID {proc.info['pid']}...")
                    proc.terminate()
                    
                    # Wait for graceful shutdown
                    try:
                        proc.wait(timeout=10)
                        print(f"TranscodeService PID {proc.info['pid']} stopped gracefully.")
                    except psutil.TimeoutExpired:
                        print(f"TranscodeService PID {proc.info['pid']} didn't stop gracefully, forcing kill...")
                        proc.kill()
                        proc.wait()
                        print(f"TranscodeService PID {proc.info['pid']} force killed.")
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    print(f"Error stopping TranscodeService PID {proc.info['pid']}: {e}")
        
        # Step 2: Clean up database
        print("\n=== CLEANING UP DATABASE ===")
        
        # Update ServiceStatus to Stopped
        db_manager.UpdateServiceStatus("TranscodeService", {
            'Status': 'Stopped',
            'ProcessId': 0,
            'IsProcessing': False,
            'ActiveJobsCount': 0,
            'HealthStatus': 'Stopped'
        })
        
        print("Database cleaned up - TranscodeService status set to Stopped.")
        
        # Step 3: Verify cleanup
        print("\n=== VERIFICATION ===")
        
        # Check for any remaining TranscodeService processes
        remaining_processes = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] == 'TranscodeService':
                    remaining_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if remaining_processes:
            print(f"WARNING: {len(remaining_processes)} TranscodeService processes still running:")
            for proc in remaining_processes:
                print(f"  PID {proc.info['pid']}")
        else:
            print("✓ No TranscodeService processes running.")
        
        # Check database status
        service_status = db_manager.GetServiceStatus("TranscodeService")
        if service_status:
            status = service_status.get('Status', 'Unknown')
            process_id = service_status.get('ProcessId', 0)
            print(f"✓ Database status: {status}, ProcessId: {process_id}")
        else:
            print("✓ No ServiceStatus record found for TranscodeService.")
        
        print("\n=== CLEANUP COMPLETE ===")
        print("You can now start TranscodeService again.")
        
        return True
        
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
        LoggingService.LogException("Error stopping TranscodeService instances", e, "StopAllTranscodeServices", "StopAllTranscodeServices")
        return False


def TestDuplicatePrevention():
    """Test the duplicate prevention mechanism."""
    try:
        print("\n=== TESTING DUPLICATE PREVENTION ===")
        
        # Check current ServiceStatus
        db_manager = DatabaseManager()
        service_status = db_manager.GetServiceStatus("TranscodeService")
        
        if service_status:
            status = service_status.get('Status', 'Unknown')
            process_id = service_status.get('ProcessId', 0)
            print(f"Current ServiceStatus: {status}, ProcessId: {process_id}")
            
            # Check if process is actually running
            if process_id > 0:
                try:
                    proc = psutil.Process(process_id)
                    if proc.is_running() and proc.name() == 'TranscodeService':
                        print(f"✓ Process {process_id} is actually running - duplicate prevention should work.")
                    else:
                        print(f"✗ Process {process_id} is not running - stale database record.")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    print(f"✗ Process {process_id} not found - stale database record.")
            else:
                print("✓ No ProcessId in database - safe to start.")
        else:
            print("✓ No ServiceStatus record - safe to start.")
        
        return True
        
    except Exception as e:
        print(f"Error testing duplicate prevention: {str(e)}")
        return False


def main():
    """Main entry point."""
    print("TranscodeService Cleanup and Test Tool")
    print("=" * 50)
    
    # Stop all instances
    success = StopAllTranscodeServices()
    
    if success:
        # Test duplicate prevention
        TestDuplicatePrevention()
        
        print("\n=== NEXT STEPS ===")
        print("1. Try starting TranscodeService again")
        print("2. Check the logs for detailed process tracking")
        print("3. If duplicates still occur, check the logs for the prevention logic")
    
    return success


if __name__ == "__main__":
    main()
