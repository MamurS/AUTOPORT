#!/usr/bin/env python3
"""
Simple test runner for AutoPort that runs tests individually to avoid async conflicts.
"""
import subprocess
import sys
import time

# Define test suites
TEST_SUITES = {
    "Health Checks": [
        "tests/test_simple.py::test_health_check_sync",
        "tests/test_simple.py::test_api_root_sync",
        "tests/test_simple.py::test_health_check_async",
    ],
    "Authentication": [
        "tests/test_auth.py::test_register_request_otp",
        "tests/test_auth.py::test_login_with_invalid_phone",
    ],
}

def run_test(test_path):
    """Run a single test and return success status."""
    result = subprocess.run(
        ["pytest", test_path, "-q", "--tb=short"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0, result.stdout, result.stderr

def main():
    """Run all tests and print summary."""
    print("AutoPort Test Suite")
    print("=" * 60)
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for suite_name, tests in TEST_SUITES.items():
        print(f"\n{suite_name}:")
        print("-" * 40)
        
        for test in tests:
            total_tests += 1
            test_name = test.split("::")[-1]
            print(f"  Running {test_name}...", end="", flush=True)
            
            success, stdout, stderr = run_test(test)
            
            if success:
                passed_tests += 1
                print(" ✓ PASSED")
            else:
                failed_tests.append(test)
                print(" ✗ FAILED")
                if stderr:
                    print(f"    Error: {stderr.strip()}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failed_tests)}")
    print(f"Success rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if failed_tests:
        print("\nFailed tests:")
        for test in failed_tests:
            print(f"  - {test}")
    
    return len(failed_tests)

if __name__ == "__main__":
    sys.exit(main())