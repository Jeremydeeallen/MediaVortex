#!/usr/bin/env python3
"""
Test runner for Phase 3.2 TDD tests.
This script runs all contract and integration tests to verify they FAIL before implementation.
In TDD, tests should fail first, then we implement to make them pass.
"""

import sys
import unittest
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

def RunContractTests():
    """Run all contract tests."""
    print("=" * 60)
    print("Running Contract Tests (TDD - Should FAIL)")
    print("=" * 60)
    
    # Import and run contract tests
    from Tests.Contract.TestTranscodeStart import TestTranscodeStart
    from Tests.Contract.TestTranscodeStatus import TestTranscodeStatus
    from Tests.Contract.TestQueueGet import TestQueueGet
    
    ContractTestSuite = unittest.TestSuite()
    ContractTestSuite.addTest(unittest.makeSuite(TestTranscodeStart))
    ContractTestSuite.addTest(unittest.makeSuite(TestTranscodeStatus))
    ContractTestSuite.addTest(unittest.makeSuite(TestQueueGet))
    
    ContractRunner = unittest.TextTestRunner(verbosity=2)
    ContractResult = ContractRunner.run(ContractTestSuite)
    
    return ContractResult


def RunIntegrationTests():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("Running Integration Tests (TDD - Should FAIL)")
    print("=" * 60)
    
    # Import and run integration tests
    from Tests.Integration.TestTranscodingWorkflow import TestTranscodingWorkflow
    from Tests.Integration.TestFilenameResolution import TestFilenameResolution
    from Tests.Integration.TestQualityScoring import TestQualityScoring
    
    IntegrationTestSuite = unittest.TestSuite()
    IntegrationTestSuite.addTest(unittest.makeSuite(TestTranscodingWorkflow))
    IntegrationTestSuite.addTest(unittest.makeSuite(TestFilenameResolution))
    IntegrationTestSuite.addTest(unittest.makeSuite(TestQualityScoring))
    
    IntegrationRunner = unittest.TextTestRunner(verbosity=2)
    IntegrationResult = IntegrationRunner.run(IntegrationTestSuite)
    
    return IntegrationResult


def Main():
    """Main test runner function."""
    print("Phase 3.2 TDD Test Runner")
    print("Testing that all tests FAIL before implementation (TDD approach)")
    print("=" * 60)
    
    # Run contract tests
    ContractResult = RunContractTests()
    
    # Run integration tests
    IntegrationResult = RunIntegrationTests()
    
    # Summary
    print("\n" + "=" * 60)
    print("TDD Test Results Summary")
    print("=" * 60)
    
    TotalTests = ContractResult.testsRun + IntegrationResult.testsRun
    TotalFailures = len(ContractResult.failures) + len(IntegrationResult.failures)
    TotalErrors = len(ContractResult.errors) + len(IntegrationResult.errors)
    
    print(f"Total Tests Run: {TotalTests}")
    print(f"Total Failures: {TotalFailures}")
    print(f"Total Errors: {TotalErrors}")
    
    if TotalFailures > 0 or TotalErrors > 0:
        print("\n✅ TDD SUCCESS: Tests are failing as expected!")
        print("This is correct for TDD - tests should fail before implementation.")
        print("Ready to proceed to Phase 3.3 (Core Implementation)")
        print("\nNext steps:")
        print("1. Implement the missing methods in Controllers/TranscodeQueueController.py")
        print("2. Implement the missing methods in Services/TranscodingBusinessService.py")
        print("3. Run tests again to verify they pass")
        return True
    else:
        print("\n❌ TDD FAILURE: All tests are passing!")
        print("This is unexpected for TDD - tests should fail before implementation.")
        print("Please check if implementation already exists or tests are not comprehensive enough.")
        return False


if __name__ == "__main__":
    success = Main()
    sys.exit(0 if success else 1)
