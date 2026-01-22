"""
Check if LibreHardwareMonitor is running
"""

import sys
import os
import subprocess

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def CheckIfRunning():
    """Check if LibreHardwareMonitor process is running."""
    print("=" * 70)
    print("Checking LibreHardwareMonitor Status")
    print("=" * 70)
    
    try:
        # Check for running process
        ps_command = "Get-Process -Name '*Libre*' -ErrorAction SilentlyContinue | Select-Object Name, Id, Path"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0 and result.stdout.strip():
            print("✓ LibreHardwareMonitor process IS RUNNING:")
            print(result.stdout)
        else:
            print("✗ LibreHardwareMonitor process IS NOT RUNNING")
            print("\nTo use LibreHardwareMonitor for temperature monitoring:")
            print("1. Download LibreHardwareMonitor from: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor")
            print("2. Run LibreHardwareMonitor.exe (it must be running for WMI sensors to be available)")
            print("3. Make sure it's running as Administrator for full access")
            
        # Check services
        print("\n" + "-" * 70)
        print("Checking for LibreHardwareMonitor Services:")
        ps_command2 = "Get-Service -Name '*Libre*' -ErrorAction SilentlyContinue | Select-Object Name, Status, DisplayName"
        result2 = subprocess.run([
            'powershell', '-Command', ps_command2
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result2.returncode == 0 and result2.stdout.strip():
            print(result2.stdout)
        else:
            print("(No LibreHardwareMonitor services found)")
            
    except Exception as e:
        print(f"Error: {e}")

def TestAlternativeSources():
    """Test if we can get temperatures from other sources."""
    print("\n" + "=" * 70)
    print("Testing Alternative Temperature Sources")
    print("=" * 70)
    
    # Try OpenHardwareMonitor
    try:
        ps_command = "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object Name, Value -First 5"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0 and result.stdout.strip():
            print("\n✓ OpenHardwareMonitor sensors available:")
            print(result.stdout)
        else:
            print("\n✗ OpenHardwareMonitor not available")
    except Exception as e:
        print(f"Error checking OpenHardwareMonitor: {e}")
    
    # Try Core Temp WMI
    try:
        ps_command = "Get-WmiObject -Namespace 'root\\CoreTemp' -Class * -ErrorAction SilentlyContinue | Select-Object -First 1"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0 and result.stdout.strip():
            print("\n✓ Core Temp WMI available:")
            print(result.stdout[:500])
        else:
            print("\n✗ Core Temp WMI not available")
    except Exception as e:
        print(f"Error checking Core Temp: {e}")

if __name__ == "__main__":
    CheckIfRunning()
    TestAlternativeSources()
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("\nFor per-core temperature monitoring, you need:")
    print("1. LibreHardwareMonitor running (download from GitHub)")
    print("2. OR OpenHardwareMonitor running")
    print("3. OR Core Temp installed and running")
    print("\nThe WMI namespace exists, but sensors are only available when")
    print("the monitoring software is actively running.")

