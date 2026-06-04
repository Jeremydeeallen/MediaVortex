#!/usr/bin/env python3
"""
Test Network Drive Validation Script

This script tests how the system validates network drive paths to diagnose
the "Root folder does not exist" error for Z: drive paths.

Usage:
    py Scripts/TestNetworkDriveValidation.py [--path "Z:\Videos\Couple"]
"""

import os
import sys
import ntpath
import argparse
from pathlib import Path

ProjectRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ProjectRoot)

from Services.LoggingService import LoggingService


# directive: path-schema-migration | # see path.S8
def _LocalExists(Value) -> bool:
    """Local filesystem existence check for a worker-resolved string value."""
    return bool(Value) and os.path.exists(Value)


# directive: path-schema-migration | # see path.S8
def _LocalGetSize(Value) -> int:
    """Local filesystem getsize for a worker-resolved string value."""
    return os.path.getsize(Value)


# directive: path-schema-migration | # see path.S8
def _NormalizeValue(Value) -> str:
    """Forward-slash to backslash normalization for a worker-resolved string value."""
    return (Value or "").replace("/", "\\")


class NetworkDriveValidator:
    """Test network drive path validation methods."""
    
    def __init__(self, TestPath: str = None):
        self.TestPath = TestPath or r"Z:\Videos\Couple"
        self.Results = []
    
    def TestPathValidation(self):
        """Test various path validation methods."""
        LoggingService.LogInfo(f"Testing network drive validation for: {self.TestPath}", "NetworkDriveValidator", "TestPathValidation")
        
        # Test 1: Basic os.path.exists
        self.TestMethod("os.path.exists", lambda: os.path.exists(self.TestPath))
        
        # Test 2: os.path.isdir
        self.TestMethod("os.path.isdir", lambda: os.path.isdir(self.TestPath))
        
        normalized = _NormalizeValue(self.TestPath)
        self.TestMethod("Normalize + exists", lambda: _LocalExists(normalized))
        
        # Test 4: os.listdir (more reliable for network drives)
        self.TestMethod("os.listdir", self.TestListDir)
        
        # Test 5: os.access
        self.TestMethod("os.access (R_OK)", lambda: os.access(self.TestPath, os.R_OK))
        
        # Test 6: pathlib.Path.exists
        path_obj = Path(self.TestPath)
        self.TestMethod("pathlib.Path.exists", lambda: path_obj.exists())
        
        # Test 7: pathlib.Path.is_dir
        self.TestMethod("pathlib.Path.is_dir", lambda: path_obj.is_dir())
        
        # Test 8: Try to get directory size
        self.TestMethod("Get directory size", self.TestGetDirSize)
        
        # Test 9: Check if it's a network drive
        self.TestMethod("Is network drive", self.TestIsNetworkDrive)
        
        # Test 10: Try os.path.abspath
        self.TestMethod("os.path.abspath", self.TestAbspath)
        
        # Test 11: Try os.path.realpath
        self.TestMethod("os.path.realpath", self.TestRealpath)
        
        # Test 12: Check drive mapping
        self.TestMethod("Check drive mapping", self.TestDriveMapping)
    
    def TestMethod(self, MethodName: str, TestFunction):
        """Test a specific validation method."""
        try:
            result = TestFunction()
            self.Results.append({
                'Method': MethodName,
                'Result': result,
                'Error': None
            })
            LoggingService.LogInfo(f"{MethodName}: {result}", "NetworkDriveValidator", "TestMethod")
        except Exception as e:
            self.Results.append({
                'Method': MethodName,
                'Result': False,
                'Error': str(e)
            })
            LoggingService.LogException(f"Error in {MethodName}", e, "NetworkDriveValidator", "TestMethod")
    
    def TestListDir(self):
        """Test os.listdir method."""
        try:
            files = os.listdir(self.TestPath)
            return len(files) >= 0  # If we can list it, it exists
        except Exception as e:
            raise e
    
    # directive: path-schema-migration | # see path.S8
    def TestGetDirSize(self):
        """Test getting directory size."""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(self.TestPath):
                for filename in filenames:
                    filepath = ntpath.join(dirpath, filename)
                    if _LocalExists(filepath):
                        total_size += _LocalGetSize(filepath)
            return total_size >= 0
        except Exception as e:
            raise e

    # directive: path-schema-migration | # see path.S8
    def TestIsNetworkDrive(self):
        """Test if path is a network drive."""
        normalized = _NormalizeValue(self.TestPath)
        return len(normalized) >= 2 and normalized[1] == ':' and normalized[0].isalpha()
    
    def TestAbspath(self):
        """Test os.path.abspath."""
        try:
            abspath = os.path.abspath(self.TestPath)
            return abspath != self.TestPath  # If it changed, it was converted
        except Exception as e:
            raise e
    
    def TestRealpath(self):
        """Test os.path.realpath."""
        try:
            realpath = os.path.realpath(self.TestPath)
            return realpath != self.TestPath  # If it changed, it was resolved
        except Exception as e:
            raise e
    
    def TestDriveMapping(self):
        """Test if drive is properly mapped."""
        try:
            drive_letter = self.TestPath[0] + ":"
            # Try to get drive info
            import ctypes
            result = ctypes.windll.kernel32.GetDriveTypeW(drive_letter)
            # DRIVE_REMOTE = 4
            return result == 4
        except Exception as e:
            raise e
    
    def PrintResults(self):
        """Print test results summary."""
        print("\n" + "="*80)
        print("NETWORK DRIVE VALIDATION TEST RESULTS")
        print("="*80)
        print(f"Test Path: {self.TestPath}")
        print("-"*80)
        
        for result in self.Results:
            status = "✓ PASS" if result['Result'] else "✗ FAIL"
            error = f" (Error: {result['Error']})" if result['Error'] else ""
            print(f"{status} {result['Method']:<25} {error}")
        
        print("-"*80)
        
        # Summary
        passed = sum(1 for r in self.Results if r['Result'])
        total = len(self.Results)
        print(f"Summary: {passed}/{total} tests passed")
        
        # Recommendations
        print("\nRecommendations:")
        if any(r['Method'] == 'os.listdir' and r['Result'] for r in self.Results):
            print("- Use os.listdir() for network drive validation (most reliable)")
        if any(r['Method'] == 'os.path.exists' and not r['Result'] for r in self.Results):
            print("- os.path.exists() is unreliable for network drives")
        if any(r['Method'] == 'Is network drive' and r['Result'] for r in self.Results):
            print("- Path is correctly identified as network drive")
        
        print("="*80)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Test network drive validation')
    parser.add_argument('--path', default=r"Z:\Videos\Couple", 
                       help='Path to test (default: Z:\\Videos\\Couple)')
    
    args = parser.parse_args()
    
    # Initialize logging
    LoggingService.LogInfo("Starting network drive validation test", "main", "TestNetworkDriveValidation")
    
    # Create validator and run tests
    validator = NetworkDriveValidator(args.path)
    validator.TestPathValidation()
    validator.PrintResults()
    
    LoggingService.LogInfo("Network drive validation test completed", "main", "TestNetworkDriveValidation")


if __name__ == "__main__":
    main()
