"""
Test HardwareMonitorService using LibreHardwareMonitorLib.dll
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def TestPythonNet():
    """Test if pythonnet is installed."""
    print("=" * 70)
    print("TEST 1: Check pythonnet Installation")
    print("=" * 70)
    
    try:
        import clr
        print("✓ pythonnet (clr) is installed")
        return True
    except ImportError:
        print("✗ pythonnet (clr) is NOT installed")
        print("\nInstall with: pip install pythonnet")
        return False

def TestLibreHardwareMonitorLib():
    """Test if LibreHardwareMonitorLib.dll can be found and loaded."""
    print("\n" + "=" * 70)
    print("TEST 2: Check LibreHardwareMonitorLib.dll")
    print("=" * 70)
    
    import clr
    
    dll_paths = [
        r"C:\Program Files\LibreHardwareMonitor\LibreHardwareMonitorLib.dll",
        r"C:\Program Files (x86)\LibreHardwareMonitor\LibreHardwareMonitorLib.dll",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "LibreHardwareMonitorLib.dll"),
    ]
    
    dll_found = False
    for dll_path in dll_paths:
        if os.path.exists(dll_path):
            print(f"✓ Found DLL at: {dll_path}")
            try:
                clr.AddReference(dll_path)
                print("✓ Successfully loaded DLL")
                dll_found = True
                
                # Try to import types
                from LibreHardwareMonitor.Hardware import Computer
                print("✓ Successfully imported Computer class")
                return True
            except Exception as e:
                print(f"✗ Error loading DLL: {e}")
                return False
    
    if not dll_found:
        print("✗ LibreHardwareMonitorLib.dll not found")
        print("\nPlease:")
        print("1. Download LibreHardwareMonitor from:")
        print("   https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases")
        print("2. Extract LibreHardwareMonitorLib.dll from the release")
        print("3. Place it in one of these locations:")
        for path in dll_paths:
            print(f"   - {path}")
        print("\n   OR place it in the MediaVortex project root directory")
        return False

def TestHardwareMonitorService():
    """Test HardwareMonitorService."""
    print("\n" + "=" * 70)
    print("TEST 3: Test HardwareMonitorService")
    print("=" * 70)
    
    try:
        from Services.HardwareMonitorService import HardwareMonitorServiceInstance
        
        if not HardwareMonitorServiceInstance.IsInitialized:
            print("✗ HardwareMonitorService not initialized")
            print("Check logs for initialization errors")
            return
        
        print("✓ HardwareMonitorService initialized")
        
        # Get temperatures
        temp_data = HardwareMonitorServiceInstance.GetCpuCoreTemperatures()
        
        if temp_data:
            print(f"\nPackage Temperature: {temp_data.get('Package')}°C")
            print(f"Max Temperature: {temp_data.get('Max')}°C")
            print(f"Average Temperature: {temp_data.get('Average')}°C")
            
            cores = temp_data.get('Cores', [])
            print(f"\nFound {len(cores)} cores:")
            for core in sorted(cores, key=lambda x: x.get('Core', 0)):
                core_num = core.get('Core', '?')
                temp = core.get('Temperature', 'N/A')
                print(f"  Core {core_num}: {temp}°C")
        else:
            print("✗ No temperature data returned")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("HARDWAREMONITORSERVICE TEST")
    print("=" * 70)
    print("\n")
    
    if not TestPythonNet():
        print("\nPlease install pythonnet first: pip install pythonnet")
        sys.exit(1)
    
    if not TestLibreHardwareMonitorLib():
        print("\nPlease install LibreHardwareMonitorLib.dll first")
        sys.exit(1)
    
    TestHardwareMonitorService()
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

