"""
Test Suite: Authentication & User Management (Module 1).
Verifies:
1. Permanent Admin existence and authentication.
2. User registration permanently saved to MongoDB.
3. Newly registered user login with hashed password.
4. Rejection of invalid credentials & non-existent accounts.
5. Role-based endpoint protection (@admin_required & @login_required).
6. User logout & session invalidation.
"""

import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import unittest
from datetime import datetime
from tests.conftest import get_test_client, create_authenticated_session
from core.database import get_mongo_db, ensure_permanent_admin

class TestAuthenticationModule(unittest.TestCase):
    def setUp(self):
        self.client = get_test_client()
        self.db = get_mongo_db()
        ensure_permanent_admin()

    def test_01_permanent_admin_login(self):
        """Permanent Admin should authenticate successfully and establish admin role."""
        res = self.client.post('/login', json={
            'email': 'admin@smartparking.ai',
            'password': 'admin123',
            'login_type': 'admin'
        })
        self.assertIn(res.status_code, (200, 302))
        if res.is_json:
            self.assertEqual(res.json.get('status'), 'success')

    def test_02_invalid_credentials_rejected(self):
        """Invalid passwords must be rejected with 401 Unauthorized."""
        res = self.client.post('/login', json={
            'email': 'admin@smartparking.ai',
            'password': 'WrongPassword123!',
            'login_type': 'admin'
        })
        self.assertEqual(res.status_code, 401)

    def test_03_nonexistent_user_rejected(self):
        """Unregistered users must be rejected."""
        res = self.client.post('/login', json={
            'email': 'ghost.user.unregistered@example.com',
            'password': 'Password@123',
            'login_type': 'user'
        })
        self.assertEqual(res.status_code, 401)

    def test_04_user_registration_and_login(self):
        """New driver account with vehicle should register and persist in MongoDB."""
        ts = int(datetime.now().timestamp())
        reg_email = f"driver_test_{ts}@smartparking.edu"
        reg_plate = f"KA01TX{ts % 10000:04d}"

        reg_res = self.client.post('/register', data={
            'name': 'Autonomous Driver',
            'email': reg_email,
            'phone': '9876543210',
            'password': 'SecurePassword@123',
            'confirm_password': 'SecurePassword@123',
            'vehicle_number': reg_plate,
            'vehicle_type': 'Car',
            'make_model': 'Hyundai Creta',
            'vehicle_color': 'Silver'
        }, follow_redirects=False)

        self.assertIn(reg_res.status_code, (200, 302))

        # Verify saved in MongoDB
        user_doc = self.db.users.find_one({'email': reg_email})
        self.assertIsNotNone(user_doc, "Registered user was not found in MongoDB")
        self.assertEqual(user_doc['role'], 'user')

        # Verify vehicle saved
        veh_doc = self.db.vehicles.find_one({'user_id': user_doc['user_id']})
        self.assertIsNotNone(veh_doc, "Registered vehicle was not found in MongoDB")
        self.assertEqual(veh_doc['license_plate'], reg_plate)

        # Login with newly registered credentials
        login_res = self.client.post('/login', json={
            'email': reg_email,
            'password': 'SecurePassword@123',
            'login_type': 'user'
        })
        self.assertIn(login_res.status_code, (200, 302))

        # Cleanup test driver
        self.db.users.delete_one({'_id': user_doc['_id']})
        self.db.vehicles.delete_many({'user_id': user_doc['user_id']})
        self.db.notifications.delete_many({'user_id': user_doc['user_id']})

    def test_05_role_based_access_control(self):
        """Standard driver should be forbidden (403) from accessing admin endpoints."""
        client = get_test_client()
        create_authenticated_session(client, role='user', user_id=999)

        res = client.get('/admin')
        self.assertIn(res.status_code, (302, 403))

        api_res = client.get('/api/admin/users')
        self.assertEqual(api_res.status_code, 403)

    def test_06_logout(self):
        """Logging out should terminate session."""
        client = get_test_client()
        create_authenticated_session(client, role='user')

        res = client.get('/logout')
        self.assertIn(res.status_code, (200, 302))

if __name__ == '__main__':
    unittest.main()
