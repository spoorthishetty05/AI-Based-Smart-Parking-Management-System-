"""
Test Suite: Administration, System Status & In-App Notifications (Modules 8, 9, 10).
Verifies:
1. System telemetry and overall occupancy status (/api/system/status).
2. Administrator metrics and stats (/api/admin/stats).
3. Role-based access control protecting administrative endpoints from regular drivers.
4. In-app notifications retrieval, unread count tracking, and mark-as-read.
5. Administrative reservations oversight.
"""

import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import unittest
from tests.conftest import get_test_client, create_authenticated_session

class TestAdminAndSystemModule(unittest.TestCase):
    def setUp(self):
        self.client = get_test_client()

    def test_01_system_status_telemetry(self):
        """Public / authenticated system status endpoint should return slot breakdown and live counts."""
        res = self.client.get('/api/system/status')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('parking_statistics', data)
        self.assertIn('stats', data)
        p_stats = data['parking_statistics']
        self.assertIn('total_slots', p_stats)
        self.assertIn('occupancy_rate', p_stats)
        self.assertGreater(p_stats['total_slots'], 0)

    def test_02_admin_access_control(self):
        """Admin endpoints should be forbidden or unauthorized for unauthenticated or driver sessions."""
        # A: Unauthenticated request to admin stats
        res_unauth = self.client.get('/api/admin/stats')
        self.assertIn(res_unauth.status_code, (401, 403, 302))

        # B: Authenticated regular driver requesting admin stats
        create_authenticated_session(self.client, role='user', user_id=99)
        res_driver = self.client.get('/api/admin/stats')
        self.assertIn(res_driver.status_code, (401, 403, 302))

    def test_03_admin_stats_authorized(self):
        """Authenticated administrator should receive full operational metrics and KPI summaries."""
        create_authenticated_session(self.client, role='admin', user_id=1)
        res = self.client.get('/api/admin/stats')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('stats', data)
        stats = data['stats']
        self.assertIn('active_users', stats)
        self.assertIn('total_slots', stats)

    def test_04_in_app_notifications_lifecycle(self):
        """In-app notifications endpoint should return user notifications and permit marking as read."""
        user_id = 1
        create_authenticated_session(self.client, role='admin', user_id=user_id)

        # 1. Fetch notifications
        res = self.client.get(f'/api/notifications?user_id={user_id}')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('unread_count', data)
        self.assertIn('notifications', data)

        # 2. Mark all read
        mark_all = self.client.post('/api/notifications/mark-all-read', json={'user_id': user_id})
        self.assertEqual(mark_all.status_code, 200)

        # 3. Verify unread count is 0
        verify_res = self.client.get(f'/api/notifications?user_id={user_id}&unread_only=true')
        self.assertEqual(verify_res.status_code, 200)
        self.assertEqual(verify_res.json.get('unread_count'), 0)

    def test_05_admin_reservations_management(self):
        """Administrator should be able to view all reservations across facilities."""
        create_authenticated_session(self.client, role='admin', user_id=1)
        res = self.client.get('/api/admin/reservations')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('reservations', data)
        self.assertIsInstance(data['reservations'], list)

if __name__ == '__main__':
    unittest.main()
