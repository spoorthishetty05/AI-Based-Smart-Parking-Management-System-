"""
Authentication & Authorization Unified Test Suite.
Verifies Driver, Administrator, and Security Guard authentication, role permissions, and session lifecycles.
"""
import unittest
import sys
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from tests.test_auth import TestAuthenticationModule
from tests.test_admin_system import TestAdminAndSystemModule
from tests.test_security_guard import TestSecurityGuardModule

if __name__ == '__main__':
    print("=" * 80)
    print("  RUNNING ADMIN, USER & SECURITY GUARD AUTHENTICATION TEST SUITE")
    print("=" * 80)
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(TestAuthenticationModule))
    suite.addTests(loader.loadTestsFromTestCase(TestAdminAndSystemModule))
    suite.addTests(loader.loadTestsFromTestCase(TestSecurityGuardModule))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

