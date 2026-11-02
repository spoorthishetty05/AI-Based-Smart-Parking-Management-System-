"""
Master Test Runner for AI-Based Smart Parking System.
Discovers and executes all test suites under tests/, summarizing results and exit codes.
"""

import sys
import os
import time
import unittest

# Ensure project root and core are in sys.path
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

def main():
    print("=" * 80)
    print("  AI-BASED SMART PARKING SYSTEM — UNIFIED MASTER TEST SUITE")
    print("=" * 80)
    start_time = time.time()

    loader = unittest.TestLoader()
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    suite = loader.discover(start_dir=tests_dir, pattern='test_*.py')

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print("\n" + "=" * 80)
    print("  TEST EXECUTION SUMMARY")
    print("=" * 80)
    print(f"  Total Tests Executed : {result.testsRun}")
    print(f"  Passed Tests         : {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  Failures             : {len(result.failures)}")
    print(f"  Errors               : {len(result.errors)}")
    print(f"  Execution Time       : {elapsed:.2f} seconds")
    print("=" * 80)

    if result.wasSuccessful():
        print("  RESULT: ALL SUITES PASSED [100% SUCCESS]")
        return 0
    else:
        print("  RESULT: TEST SUITE FAILED")
        return 1

if __name__ == '__main__':
    sys.exit(main())

