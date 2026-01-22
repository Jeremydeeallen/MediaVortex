# CPU Temperature Monitoring Limitations on Windows

## The Problem

**Windows does not natively expose per-core CPU temperatures through standard APIs.**

### What Windows Provides:
- **Package temperature only** - Overall CPU temperature via WMI `MSAcpi_ThermalZoneTemperature`
- **No per-core temperatures** - Not available through:
  - WMI (Windows Management Instrumentation)
  - Win32 APIs
  - System files
  - Registry
  - PowerShell cmdlets

### Why Per-Core Temperatures Aren't Available:

1. **Hardware abstraction**: Windows abstracts hardware details - it doesn't need to know individual core temps
2. **Security**: Direct hardware access requires kernel-mode drivers
3. **Hardware variety**: Different CPUs expose temperature data differently
4. **No standard API**: Microsoft never created a standard API for this

### What Other Solutions Do:

All software that reads per-core temperatures uses one of these methods:

1. **Manufacturer-specific drivers** (Intel XTU, AMD Ryzen Master)
2. **Hardware abstraction libraries** (LibreHardwareMonitor, OpenHardwareMonitor)
3. **Direct hardware access** via kernel drivers (requires admin privileges)
4. **MSR (Model Specific Registers)** - Direct CPU register access (very low-level, CPU-specific)

## Our Options:

### Option 1: Package Temperature Only (No External Dependencies)
- ✅ Works with pure Windows APIs
- ✅ No external libraries/DLLs
- ❌ Only provides overall CPU temp, not per-core

### Option 2: MSR (Model Specific Register) Access
- ✅ Pure Python with ctypes
- ✅ Direct CPU register access
- ❌ Requires admin privileges
- ❌ CPU-specific implementation
- ❌ Very complex (different for Intel vs AMD)
- ❌ Risk of system instability if done incorrectly

### Option 3: Use Hardware Library DLL (Current Approach)
- ✅ Provides per-core temperatures
- ✅ Well-tested and safe
- ❌ Requires LibreHardwareMonitorLib.dll file (single file, no installation)

## Recommendation

For your use case (thermal management and core rotation), you have two realistic options:

### A. Use Package Temperature + CPU Load Per Core
- Monitor overall CPU package temperature
- Use `psutil` to monitor load per core
- Rotate cores based on load (hotter cores likely under higher load)
- **Pros**: No external dependencies, works immediately
- **Cons**: Less precise than actual temperature per core

### B. Accept the DLL Requirement
- Use LibreHardwareMonitorLib.dll (single file, no installation needed)
- Provides accurate per-core temperatures
- **Pros**: Accurate, reliable, single file dependency
- **Cons**: Still a dependency (but no running software needed)

## Current Implementation

The code currently tries multiple methods in order:
1. HardwareMonitorService (direct DLL access - requires LibreHardwareMonitorLib.dll)
2. LibreHardwareMonitor WMI (requires software running)
3. OpenHardwareMonitor WMI (requires software running)
4. WMI Thermal Zones (package temp only - built into Windows)

