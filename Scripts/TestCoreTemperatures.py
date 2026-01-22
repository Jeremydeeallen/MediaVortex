"""
Test Core Temperature Detection
Tests LibreHardwareMonitor WMI output and core temperature parsing
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import subprocess
import re
from Services.SystemMonitoringService import SystemMonitoringServiceInstance
from Services.LoggingService import LoggingService

def TestLibreHardwareMonitorRaw():
    """Test raw LibreHardwareMonitor WMI output."""
    print("=" * 70)
    print("TEST 1: Raw LibreHardwareMonitor WMI Output")
    print("=" * 70)
    
    try:
        ps_command = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object Name, Value | Sort-Object Name"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        print(f"PowerShell Return Code: {result.returncode}")
        print(f"\nRaw Output:\n{'-' * 70}")
        print(result.stdout)
        print(f"{'-' * 70}\n")
        
        if result.stderr:
            print(f"Errors:\n{result.stderr}\n")
            
        return result.stdout
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def TestLibreHardwareMonitorParsing():
    """Test parsing of LibreHardwareMonitor output."""
    print("=" * 70)
    print("TEST 2: Parsing LibreHardwareMonitor Output")
    print("=" * 70)
    
    try:
        ps_command = "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object Name, Value | Sort-Object Name"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            sensors = {}
            core_temps = {}
            
            print("Parsing lines:")
            print("-" * 70)
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or ('Name' in line and 'Value' in line):
                    print(f"Line {line_num}: SKIPPED (header/empty)")
                    continue
                
                print(f"\nLine {line_num}: '{line}'")
                
                try:
                    parts = line.split()
                    if len(parts) < 2:
                        print(f"  -> SKIPPED: Too few parts ({len(parts)})")
                        continue
                    
                    temp_str = parts[-1]
                    try:
                        temp_celsius = float(temp_str)
                    except ValueError:
                        print(f"  -> SKIPPED: Not a valid temperature '{temp_str}'")
                        continue
                    
                    name = ' '.join(parts[:-1])
                    print(f"  -> Sensor Name: '{name}'")
                    print(f"  -> Temperature: {temp_celsius}°C")
                    
                    if 20 < temp_celsius < 150:
                        sensors[name] = round(temp_celsius, 1)
                        print(f"  -> ADDED to sensors dict")
                        
                        # Test core matching
                        core_number = None
                        
                        if 'Distance to TjMax' in name or 'Package' in name:
                            print(f"  -> SKIPPED: Package/Distance sensor")
                        else:
                            # Try pattern: "CPU Core #0" or "Core #0"
                            core_match = re.search(r'(?:CPU\s+)?Core\s*#\s*(\d+)', name, re.IGNORECASE)
                            if core_match:
                                core_number = int(core_match.group(1))
                                print(f"  -> MATCHED Pattern 1: Core #{core_number}")
                            else:
                                # Try pattern: "CPU Core 0" or "Core 0" (without #)
                                alt_match = re.search(r'(?:CPU\s+)?Core\s+(\d+)', name, re.IGNORECASE)
                                if alt_match:
                                    core_number = int(alt_match.group(1))
                                    print(f"  -> MATCHED Pattern 2: Core {core_number}")
                                else:
                                    # Try pattern: "CPU Core Temperature #0"
                                    temp_match = re.search(r'Core\s+(?:Temperature\s+)?#?\s*(\d+)', name, re.IGNORECASE)
                                    if temp_match:
                                        core_number = int(temp_match.group(1))
                                        print(f"  -> MATCHED Pattern 3: Core {core_number}")
                                    else:
                                        print(f"  -> NO MATCH: Tried all patterns")
                            
                            if core_number is not None:
                                core_temps[core_number] = round(temp_celsius, 1)
                                print(f"  -> ADDED Core {core_number}: {temp_celsius}°C")
                    else:
                        print(f"  -> SKIPPED: Temperature out of range ({temp_celsius}°C)")
                        
                except Exception as e:
                    print(f"  -> ERROR parsing line: {e}")
                    import traceback
                    traceback.print_exc()
            
            print("\n" + "=" * 70)
            print("PARSING RESULTS")
            print("=" * 70)
            print(f"\nTotal Sensors Found: {len(sensors)}")
            print(f"Core Temperatures Found: {len(core_temps)}")
            
            if sensors:
                print(f"\nAll Sensors:")
                for name, temp in sorted(sensors.items()):
                    print(f"  {name}: {temp}°C")
            
            if core_temps:
                print(f"\nCore Temperatures (sorted by core number):")
                for core_num in sorted(core_temps.keys()):
                    print(f"  Core {core_num}: {core_temps[core_num]}°C")
            else:
                print(f"\nNO CORE TEMPERATURES FOUND!")
                print(f"\nLooking for patterns in sensor names:")
                for name in sorted(sensors.keys()):
                    if 'core' in name.lower():
                        print(f"  '{name}' - contains 'core'")
                        
        else:
            print("No output from PowerShell command")
            if result.stderr:
                print(f"Error: {result.stderr}")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

def TestSystemMonitoringService():
    """Test SystemMonitoringService GetCpuTemperature method."""
    print("=" * 70)
    print("TEST 3: SystemMonitoringService GetCpuTemperature")
    print("=" * 70)
    
    try:
        temp_data = SystemMonitoringServiceInstance._GetCpuTemperatureWindowsDetailed()
        
        if temp_data:
            print(f"\nPackage Temperature: {temp_data.get('Package')}°C")
            print(f"Max Temperature: {temp_data.get('Max')}°C")
            print(f"Average Temperature: {temp_data.get('Average')}°C")
            print(f"\nCore Count: {len(temp_data.get('Cores', []))}")
            
            cores = temp_data.get('Cores', [])
            if cores:
                print(f"\nCore Temperatures:")
                for core in sorted(cores, key=lambda x: x.get('Core', 0)):
                    core_num = core.get('Core', '?')
                    temp = core.get('Temperature')
                    if temp is not None:
                        print(f"  Core {core_num}: {temp}°C")
                    else:
                        print(f"  Core {core_num}: N/A")
            else:
                print("\nNO CORES IN RESULT!")
        else:
            print("GetCpuTemperatureWindowsDetailed returned None")
            
        # Also test the full GetCpuTemperature method
        print("\n" + "-" * 70)
        print("Full GetCpuTemperature Result:")
        print("-" * 70)
        full_result = SystemMonitoringServiceInstance.GetCpuTemperature()
        if full_result:
            print(f"Package: {full_result.get('Celsius')}°C / {full_result.get('Fahrenheit')}°F")
            print(f"Cores Returned: {len(full_result.get('Cores', []))}")
            
            cores = full_result.get('Cores', [])
            if cores:
                print(f"\nFirst 5 cores:")
                for core in sorted(cores[:5], key=lambda x: x.get('Core', 0)):
                    core_num = core.get('Core', '?')
                    temp = core.get('Temperature')
                    print(f"  Core {core_num}: {temp if temp is not None else 'N/A'}°C")
        else:
            print("GetCpuTemperature returned None")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

def TestWMINamespace():
    """Test if LibreHardwareMonitor WMI namespace exists."""
    print("=" * 70)
    print("TEST 4: Check WMI Namespace Availability")
    print("=" * 70)
    
    try:
        # Check if namespace exists
        ps_command = "Get-WmiObject -Namespace 'root' -Class __Namespace | Where-Object {$_.Name -eq 'LibreHardwareMonitor'} | Select-Object Name"
        result = subprocess.run([
            'powershell', '-Command', ps_command
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0:
            if result.stdout.strip() and 'LibreHardwareMonitor' in result.stdout:
                print("✓ LibreHardwareMonitor namespace EXISTS")
            else:
                print("✗ LibreHardwareMonitor namespace NOT FOUND")
                print("\nChecking all available namespaces:")
                ps_command2 = "Get-WmiObject -Namespace 'root' -Class __Namespace | Select-Object Name | Sort-Object Name"
                result2 = subprocess.run([
                    'powershell', '-Command', ps_command2
                ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                print(result2.stdout)
        else:
            print(f"Error checking namespace: {result.stderr}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("CPU CORE TEMPERATURE DETECTION TEST")
    print("=" * 70)
    print("\n")
    
    # Test 1: Check if namespace exists
    TestWMINamespace()
    print("\n")
    
    # Test 2: Raw output
    raw_output = TestLibreHardwareMonitorRaw()
    print("\n")
    
    # Test 3: Parsing test
    TestLibreHardwareMonitorParsing()
    print("\n")
    
    # Test 4: SystemMonitoringService test
    TestSystemMonitoringService()
    print("\n")
    
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

