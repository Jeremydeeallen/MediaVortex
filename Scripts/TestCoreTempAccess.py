"""
Test Core Temp Access Methods
Core Temp exposes data via shared memory and registry
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import subprocess
import winreg

def TestCoreTempRegistry():
    """Core Temp stores data in registry."""
    print("=" * 70)
    print("TEST 1: Core Temp Registry Access")
    print("=" * 70)
    
    try:
        # Core Temp typically stores data in registry
        # HKEY_LOCAL_MACHINE\SOFTWARE\Core Temp
        key_path = r"SOFTWARE\Core Temp"
        
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            print(f"✓ Found registry key: {key_path}")
            
            # Try to enumerate values
            i = 0
            print("\nRegistry values:")
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    print(f"  {name}: {value}")
                    i += 1
                except WindowsError:
                    break
            winreg.CloseKey(key)
        except FileNotFoundError:
            print(f"✗ Registry key not found: {key_path}")
        except Exception as e:
            print(f"Error: {e}")
            
    except Exception as e:
        print(f"Error: {e}")

def TestCoreTempWMI():
    """Test if Core Temp exposes WMI data."""
    print("\n" + "=" * 70)
    print("TEST 2: Core Temp WMI")
    print("=" * 70)
    
    try:
        # Check for Core Temp WMI namespace
        ps_command = "Get-WmiObject -Namespace 'root' -Class __Namespace | Where-Object {$_.Name -eq 'CoreTemp'} | Select-Object Name"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0 and 'CoreTemp' in result.stdout:
            print("✓ Core Temp namespace exists")
            
            # Try to get classes
            ps_command2 = "Get-WmiObject -Namespace 'root\\CoreTemp' -List | Select-Object Name | Format-Table"
            result2 = subprocess.run([
                'powershell', '-Command', ps_command2
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            print("\nCore Temp classes:")
            print(result2.stdout if result2.stdout.strip() else "(No classes found)")
        else:
            print("✗ Core Temp WMI namespace not found")
            
    except Exception as e:
        print(f"Error: {e}")

def TestSharedMemory():
    """Core Temp may use shared memory."""
    print("\n" + "=" * 70)
    print("TEST 3: Shared Memory Access")
    print("=" * 70)
    
    print("Core Temp uses shared memory for inter-process communication.")
    print("This requires the CoreTemp.dll or CoreTempReader library.")
    print("\nTo use Core Temp programmatically, you would need:")
    print("1. CoreTempReader.dll (from Core Temp SDK)")
    print("2. Or use the Core Temp .NET library")
    print("\nAlternative: Use LibreHardwareMonitor which provides better WMI support")

if __name__ == "__main__":
    TestCoreTempRegistry()
    TestCoreTempWMI()
    TestSharedMemory()
    
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    print("\nSince LibreHardwareMonitor WMI namespace exists but is empty,")
    print("you need to:")
    print("\n1. Download and run LibreHardwareMonitor:")
    print("   https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases")
    print("\n2. Run LibreHardwareMonitor.exe")
    print("   (It must be running for sensors to appear in WMI)")
    print("\n3. Run as Administrator for full hardware access")
    print("\nOR")
    print("\nWe can implement Core Temp shared memory access (requires SDK)")

