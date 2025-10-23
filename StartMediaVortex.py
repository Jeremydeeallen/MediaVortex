"""
StartMediaVortex - Service orchestrator
Uses ServiceLifecycleManager to start all services
"""

import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Services.ServiceLifecycleManager import ServiceLifecycleManager

def main():
    print("================================")
    print("Starting MediaVortex services...")
    
    service_manager = ServiceLifecycleManager()
    result = service_manager.StartAllServices()
    
    if result["Success"]:
        print(f"\n{result['Message']}")
        for service in result["StartedServices"]:
            print(f"  - {service['ServiceName']}: PID {service['PID']}")
        print("\nAll services started. Orchestrator exiting.")
    else:
        print(f"\nError: {result.get('ErrorMessage', 'Unknown error')}")
        if result.get("FailedServices"):
            print("\nFailed services:")
            for failure in result["FailedServices"]:
                print(f"  - {failure['ServiceName']}: {failure['Error']}")
        sys.exit(1)

if __name__ == "__main__":
    main()