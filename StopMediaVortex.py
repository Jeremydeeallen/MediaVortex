"""
StopMediaVortex - Service stopper
Uses ServiceLifecycleManager to stop all services
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Services.ServiceLifecycleManager import ServiceLifecycleManager

def main():
    print("MediaVortex Service Stopper")
    print("===========================")
    
    service_manager = ServiceLifecycleManager()
    
    # Default to force stop (this is for stopping service processes, not queue management)
    result = service_manager.StopAllServices(Force=True)
    
    if result["Success"]:
        print(f"\n{result['Message']}")
        if result.get("StoppedServices"):
            for service_name in result["StoppedServices"]:
                print(f"  - {service_name} stopped")
        if result.get("FailedServices"):
            print("\nFailed to stop:")
            for failure in result["FailedServices"]:
                print(f"  - {failure['ServiceName']}: {failure['Error']}")
    else:
        print(f"\nError: {result.get('ErrorMessage', 'Unknown error')}")

if __name__ == "__main__":
    main()