"""
Detailed LibreHardwareMonitor Diagnostic
Tests what's actually available in the WMI namespace
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import subprocess

def TestNamespace():
    """Test if namespace exists and what classes are available."""
    print("=" * 70)
    print("TEST 1: Check Namespace and Classes")
    print("=" * 70)
    
    try:
        # Check namespace
        ps_command = "Get-WmiObject -Namespace 'root' -Class __Namespace | Where-Object {$_.Name -eq 'LibreHardwareMonitor'} | Select-Object Name"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        print("Namespace Check:")
        print(result.stdout)
        
        # Check what classes exist
        ps_command2 = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -List | Select-Object Name | Sort-Object Name"
        result2 = subprocess.run([
            'powershell', '-Command', ps_command2
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        print("\nAvailable Classes:")
        print(result2.stdout)
        if result2.stderr:
            print(f"\nErrors: {result2.stderr}")
            
    except Exception as e:
        print(f"Error: {e}")

def TestSensorClass():
    """Test what's in the Sensor class."""
    print("\n" + "=" * 70)
    print("TEST 2: Check Sensor Class")
    print("=" * 70)
    
    try:
        # Get all sensors
        ps_command = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        print(f"Return Code: {result.returncode}")
        print(f"\nAll Sensors (raw):")
        print(result.stdout[:2000])  # First 2000 chars
        if len(result.stdout) > 2000:
            print(f"... (truncated, total {len(result.stdout)} chars)")
        if result.stderr:
            print(f"\nErrors: {result.stderr}")
            
        # Count sensors
        if result.returncode == 0 and result.stdout.strip():
            lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
            print(f"\nTotal lines returned: {len(lines)}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

def TestSensorProperties():
    """Test what properties Sensor objects have."""
    print("\n" + "=" * 70)
    print("TEST 3: Check Sensor Properties")
    print("=" * 70)
    
    try:
        # Get first sensor to see properties
        ps_command = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Select-Object -First 1 | Format-List"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        print("First Sensor (all properties):")
        print(result.stdout)
        if result.stderr:
            print(f"\nErrors: {result.stderr}")
            
    except Exception as e:
        print(f"Error: {e}")

def TestTemperatureSensors():
    """Test specifically temperature sensors."""
    print("\n" + "=" * 70)
    print("TEST 4: Temperature Sensors Only")
    print("=" * 70)
    
    try:
        # Try different filter approaches
        commands = [
            ("Filter by SensorType", "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object Name, Value, SensorType | Format-Table -AutoSize"),
            ("Filter by Name containing Temp", "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.Name -like '*Temp*' -or $_.Name -like '*Core*'} | Select-Object Name, Value, SensorType | Format-Table -AutoSize"),
            ("All Sensors with Name and Type", "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Select-Object Name, SensorType | Format-Table -AutoSize"),
        ]
        
        for desc, cmd in commands:
            print(f"\n{desc}:")
            print("-" * 70)
            result = subprocess.run([
                'powershell', '-Command', cmd
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            print(f"Return Code: {result.returncode}")
            if result.stdout.strip():
                print(result.stdout)
            else:
                print("(No output)")
            if result.stderr:
                print(f"Errors: {result.stderr}")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

def TestAlternativeFormats():
    """Test alternative output formats."""
    print("\n" + "=" * 70)
    print("TEST 5: Alternative Output Formats")
    print("=" * 70)
    
    try:
        # Try without Sort-Object
        ps_command = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Format-Table Name, Value -AutoSize"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        print("Without Sort-Object:")
        print(result.stdout if result.stdout.strip() else "(No output)")
        
        # Try with ConvertTo-Json
        ps_command2 = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object -First 5 | ConvertTo-Json"
        result2 = subprocess.run([
            'powershell', '-Command', ps_command2
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        print("\nFirst 5 as JSON:")
        print(result2.stdout if result2.stdout.strip() else "(No output)")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("LIBREHARDWAREMONITOR DETAILED DIAGNOSTIC")
    print("=" * 70)
    print("\n")
    
    TestNamespace()
    TestSensorClass()
    TestSensorProperties()
    TestTemperatureSensors()
    TestAlternativeFormats()
    
    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)

