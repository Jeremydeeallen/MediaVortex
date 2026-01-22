#!/usr/bin/env python3
"""
Test the SystemMonitoringService
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.SystemMonitoringService import SystemMonitoringServiceInstance

def TestPowerShellCounter():
    """Test PowerShell Get-Counter for CPU temperature."""
    try:
        import subprocess
        # Try to get CPU temperature from performance counters
        result = subprocess.run([
            'powershell', '-Command', 
            "Get-Counter -Counter '\\Thermal Zone Information(*)\\Temperature' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CounterSamples | Select-Object InstanceName, CookedValue | Format-Table -AutoSize"
        ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            temperatures = []
            for line in lines:
                if line.strip() and not line.startswith('InstanceName'):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            temp_kelvin = float(parts[-1])
                            temp_celsius = temp_kelvin - 273.15
                            if 20 < temp_celsius < 150:  # Reasonable CPU temp range
                                temperatures.append(round(temp_celsius, 1))
                        except ValueError:
                            continue
            
            if temperatures:
                return max(temperatures)  # Return highest temperature
        return None
    except Exception as e:
        print(f"    Error with PowerShell counter: {e}")
        return None

def TestSystemMonitoring():
    """Test the SystemMonitoringService."""
    print("Testing SystemMonitoringService...")
    print("=" * 50)
    
    try:
        # Test individual temperature methods
        print("Testing individual temperature detection methods:")
        print("-" * 40)
        
        # Test WMI Thermal Zone
        thermal_temp = SystemMonitoringServiceInstance._TryWmiThermalZone()
        print(f"  WMI Thermal Zone: {thermal_temp}°C" if thermal_temp else "  WMI Thermal Zone: Not available")
        
        # Test WMI Temperature Probe
        probe_temp = SystemMonitoringServiceInstance._TryWmiTemperatureProbe()
        print(f"  WMI Temperature Probe: {probe_temp}°C" if probe_temp else "  WMI Temperature Probe: Not available")
        
        # Test OpenHardwareMonitor
        ohm_temp = SystemMonitoringServiceInstance._TryOpenHardwareMonitor()
        print(f"  OpenHardwareMonitor: {ohm_temp}°C" if ohm_temp else "  OpenHardwareMonitor: Not available")
        
        # Test CoreTemp
        coretemp_temp = SystemMonitoringServiceInstance._TryCoreTempWmi()
        print(f"  CoreTemp WMI: {coretemp_temp}°C" if coretemp_temp else "  CoreTemp WMI: Not available")
        
        # Test HWiNFO64
        hwinfo_temp = SystemMonitoringServiceInstance._TryHWiNFO64Wmi()
        print(f"  HWiNFO64 WMI: {hwinfo_temp}°C" if hwinfo_temp else "  HWiNFO64 WMI: Not available")
        
        # Test PowerShell Get-Counter method
        counter_temp = TestPowerShellCounter()
        print(f"  PowerShell Counter: {counter_temp}°C" if counter_temp else "  PowerShell Counter: Not available")
        
        # Test LibreHardwareMonitor
        libre_temp = SystemMonitoringServiceInstance._TryLibreHardwareMonitorWmi()
        print(f"  LibreHardwareMonitor: {libre_temp}°C" if libre_temp else "  LibreHardwareMonitor: Not available")
        
        print("\n" + "=" * 50)
        print("Detailed WMI Sensor Investigation:")
        print("-" * 35)
        
        # Let's investigate what WMI sensors are actually available
        import subprocess
        try:
            # Check what thermal zones are available
            print("  Checking WMI Thermal Zones...")
            result = subprocess.run([
                'powershell', '-Command', 
                "Get-WmiObject -Namespace 'root\\wmi' -Class MSAcpi_ThermalZoneTemperature | Select-Object InstanceName, CurrentTemperature | Format-Table -AutoSize"
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                print("  Available Thermal Zones:")
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and not line.startswith('InstanceName'):
                        print(f"    {line.strip()}")
            else:
                print("    No thermal zone details available")
                
        except Exception as e:
            print(f"    Error checking thermal zones: {e}")
        
        try:
            # Check OpenHardwareMonitor sensors if available
            print("\n  Checking OpenHardwareMonitor sensors...")
            result = subprocess.run([
                'powershell', '-Command', 
                "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object Name, Value | Format-Table -AutoSize"
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                print("  Available Temperature Sensors:")
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and not line.startswith('Name'):
                        print(f"    {line.strip()}")
            else:
                print("    OpenHardwareMonitor not available or no sensors found")
                
        except Exception as e:
            print(f"    Error checking OpenHardwareMonitor: {e}")
        
        try:
            # Check if Core Temp creates a WMI namespace
            print("\n  Checking Core Temp WMI namespace...")
            result = subprocess.run([
                'powershell', '-Command', 
                "Get-WmiObject -Namespace 'root\\CoreTemp' -Class * -ErrorAction SilentlyContinue | Select-Object -First 5 | Format-Table -AutoSize"
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                print("  Core Temp WMI Classes:")
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        print(f"    {line.strip()}")
            else:
                print("    Core Temp WMI namespace not found")
                
        except Exception as e:
            print(f"    Error checking Core Temp WMI: {e}")
        
        try:
            # Check LibreHardwareMonitor sensors if available
            print("\n  Checking LibreHardwareMonitor sensors...")
            result = subprocess.run([
                'powershell', '-Command', 
                "Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' -Class Sensor | Where-Object {$_.SensorType -eq 'Temperature'} | Select-Object Name, Value | Format-Table -AutoSize"
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                print("  LibreHardwareMonitor Temperature Sensors:")
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and not line.startswith('Name'):
                        print(f"    {line.strip()}")
            else:
                print("    LibreHardwareMonitor not available or no sensors found")
                
        except Exception as e:
            print(f"    Error checking LibreHardwareMonitor: {e}")
        
        try:
            # Check all available WMI namespaces for temperature-related ones
            print("\n  Checking for temperature-related WMI namespaces...")
            result = subprocess.run([
                'powershell', '-Command', 
                "Get-WmiObject -Namespace 'root' -Class __Namespace | Where-Object {$_.Name -like '*temp*' -or $_.Name -like '*thermal*' -or $_.Name -like '*core*' -or $_.Name -like '*cpu*' -or $_.Name -like '*libre*' -or $_.Name -like '*hardware*'} | Select-Object Name"
            ], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if result.returncode == 0 and result.stdout.strip():
                print("  Temperature-related WMI namespaces:")
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and not line.startswith('Name'):
                        print(f"    root\\{line.strip()}")
            else:
                print("    No temperature-related WMI namespaces found")
                
        except Exception as e:
            print(f"    Error checking WMI namespaces: {e}")
        
        print("\n" + "=" * 50)
        print("Final System Resources:")
        print("-" * 30)
        
        resources = SystemMonitoringServiceInstance.GetSystemResources()
        
        print(f"  CPU Usage: {resources['CpuUsage']}%")
        if resources['CpuTemperature']:
            temp = resources['CpuTemperature']
            print(f"  CPU Temperature: {temp['Celsius']}°C ({temp['Fahrenheit']}°F)")
            if 'Max' in temp:
                print(f"    Max Core: {temp['Max']}°C")
            if 'Average' in temp:
                print(f"    Average: {temp['Average']}°C")
            if 'Cores' in temp and temp['Cores']:
                print(f"    Core Count: {len(temp['Cores'])}")
                print(f"    Core Range: {min(c['Temperature'] for c in temp['Cores'])}°C - {max(c['Temperature'] for c in temp['Cores'])}°C")
        else:
            print(f"  CPU Temperature: Not available")
        print(f"  Memory: {resources['MemoryUsage']['Used']}GB / {resources['MemoryUsage']['Total']}GB ({resources['MemoryUsage']['Percent']}%)")
        print(f"  Disk: {resources['DiskUsage']['Free']}GB / {resources['DiskUsage']['Total']}GB ({resources['DiskUsage']['Percent']}%)")
        print(f"  System Info: {resources['SystemInfo']}")
        
        print("\n" + "=" * 50)
        print("Temperature Analysis:")
        print("-" * 20)
        
        all_temps = [thermal_temp, probe_temp, ohm_temp, coretemp_temp, hwinfo_temp, counter_temp, libre_temp]
        valid_temps = [t for t in all_temps if t is not None]
        
        if valid_temps:
            print(f"  All detected temperatures: {valid_temps}")
            print(f"  Highest temperature: {max(valid_temps)}°C")
            print(f"  Lowest temperature: {min(valid_temps)}°C")
            print(f"  Average temperature: {sum(valid_temps)/len(valid_temps):.1f}°C")
        else:
            print("  No temperatures detected from any method")
        
        print("\n✓ SystemMonitoringService test completed successfully!")
        
    except Exception as e:
        print(f"✗ Error testing SystemMonitoringService: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    TestSystemMonitoring()
