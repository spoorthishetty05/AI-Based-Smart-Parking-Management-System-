"""
Test Suite: Security Guard & Gate Operations.
Verifies:
1. Security Guard login & authentication routing.
2. Role-based access control (@security_required).
3. Live gate telemetry and statistics.
4. On-spot walk-in booking registration with barrier opening.
5. Slot state mutation to 'occupied' upon spot booking.
6. Bookings query and live search filters.
7. Booking updates: license plate correction & slot relocation.
8. Booking termination at gate: status change to 'completed', slot freeing, dwell time computation.
9. Manual gate barrier toggle.
10. Admin Security Guard management (CRUD).
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


class TestSecurityGuardModule(unittest.TestCase):
    def setUp(self):
        self.client = get_test_client()
        self.db = get_mongo_db()
        ensure_permanent_admin()
        # Guarantee available slots in lot 1 for testing spot registrations
        self.db.parking_slots.update_many(
            {'lot_id': 1},
            {'$set': {'status': 'available', 'current_plate': None, 'current_reservation_id': None}}
        )

    def test_01_security_guard_login(self):
        """Security Guard authenticates successfully and receives security dashboard redirect."""
        res = self.client.post('/login', json={
            'email': 'security@smartparking.ai',
            'password': 'security123',
            'login_type': 'security'
        })
        self.assertIn(res.status_code, (200, 302))
        if res.is_json:
            self.assertEqual(res.json.get('status'), 'success')
            self.assertIn('/security', res.json.get('redirect', ''))

    def test_02_access_control_security_required(self):
        """Non-authenticated or standard driver users must be blocked from /security."""
        # Unauthenticated access -> 302 redirect or 401
        res = self.client.get('/security')
        self.assertIn(res.status_code, (302, 401))

        # Standard Driver user -> 403 or redirect
        driver_client = get_test_client()
        create_authenticated_session(driver_client, role='user', user_id=10, email='driver@test.com')
        res_driver = driver_client.get('/security')
        self.assertIn(res_driver.status_code, (302, 403))

        # Security Officer -> 200 OK
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6, email='security@smartparking.ai')
        res_sec = sec_client.get('/security')
        self.assertEqual(res_sec.status_code, 200)

    def test_03_telemetry_stats(self):
        """Guard should receive live gate telemetry stats."""
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6)
        res = sec_client.get('/api/security/stats')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        stats = data.get('stats', {})
        self.assertIn('currently_parked', stats)
        self.assertIn('vacant_slots', stats)
        self.assertIn('today_entries', stats)
        self.assertIn('active_overstays', stats)

    def test_04_vacant_slots_lookup(self):
        """Guard should fetch list of vacant slots in a lot."""
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6)
        res = sec_client.get('/api/security/slots/available?lot_id=1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIsInstance(data.get('slots'), list)

    def test_05_spot_booking_creation(self):
        """Walk-in spot registration marks slot occupied, creates booking, and signals barrier open."""
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6)

        ts = int(datetime.now().timestamp())
        test_plate = f"KA04SPOT{ts % 10000:04d}"

        res = sec_client.post('/api/security/spot-booking', json={
            'license_plate': test_plate,
            'vehicle_type': 'Car',
            'lot_id': 1,
            'duration_hours': 2,
            'driver_name': 'Spot Customer',
            'driver_phone': '9876543210'
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertTrue(data.get('barrier_opened'))

        bid = data['booking']['booking_id']
        slot_number = data['booking']['slot_number']

        # Verify in MongoDB bookings
        booking = self.db.bookings.find_one({'booking_id': bid})
        self.assertIsNotNone(booking)
        self.assertEqual(booking.get('status'), 'checked_in')
        self.assertEqual(booking.get('license_plate'), test_plate)
        self.assertTrue(booking.get('is_on_spot'))

        # Verify parking slot is occupied
        slot = self.db.parking_slots.find_one({'slot_number': slot_number, 'lot_id': 1})
        self.assertIsNotNone(slot)
        self.assertEqual(slot.get('status'), 'occupied')
        self.assertEqual(slot.get('current_plate'), test_plate)

    def test_06_bookings_query_and_search(self):
        """Guard queries bookings list and searches by license plate."""
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6)

        # Create spot booking first
        ts = int(datetime.now().timestamp())
        test_plate = f"KA05FIND{ts % 10000:04d}"
        sec_client.post('/api/security/spot-booking', json={
            'license_plate': test_plate,
            'lot_id': 1
        })

        # Query all
        res = sec_client.get('/api/security/bookings?status=all')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertGreater(data.get('count', 0), 0)

        # Search specifically for test plate
        res_search = sec_client.get(f'/api/security/bookings?search={test_plate}')
        self.assertEqual(res_search.status_code, 200)
        search_data = res_search.get_json()
        self.assertGreater(search_data.get('count', 0), 0)
        found_plates = [b.get('plate') for b in search_data.get('bookings', [])]
        self.assertIn(test_plate, found_plates)

    def test_07_update_booking_plate_and_relocation(self):
        """Guard updates license plate and relocates vehicle to another slot."""
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6)

        ts = int(datetime.now().timestamp())
        orig_plate = f"KA01OLD{ts % 10000:04d}"
        new_plate = f"KA01NEW{ts % 10000:04d}"

        # 1. Create spot booking
        create_res = sec_client.post('/api/security/spot-booking', json={
            'license_plate': orig_plate,
            'lot_id': 1
        })
        bid = create_res.get_json()['booking']['booking_id']

        # Find another available slot in lot 1
        avail_slot = self.db.parking_slots.find_one({'lot_id': 1, 'status': 'available'})
        self.assertIsNotNone(avail_slot, "Requires at least one vacant slot in lot 1")
        target_slot_id = avail_slot['slot_id']
        target_slot_num = avail_slot['slot_number']

        # 2. Update plate and relocate slot
        update_res = sec_client.post(f'/api/security/bookings/{bid}/update', json={
            'license_plate': new_plate,
            'new_slot_id': target_slot_id,
            'driver_name': 'Updated Driver',
            'extend_hours': 1
        })
        self.assertEqual(update_res.status_code, 200)
        data = update_res.get_json()
        self.assertEqual(data.get('status'), 'success')

        # Verify booking in MongoDB
        updated_b = self.db.bookings.find_one({'booking_id': bid})
        self.assertEqual(updated_b.get('license_plate'), new_plate)
        self.assertEqual(updated_b.get('slot_id'), target_slot_id)
        self.assertEqual(updated_b.get('slot_number'), target_slot_num)

        # Verify new slot is occupied with new plate
        new_slot = self.db.parking_slots.find_one({'slot_id': target_slot_id})
        self.assertEqual(new_slot.get('status'), 'occupied')
        self.assertEqual(new_slot.get('current_plate'), new_plate)

    def test_08_terminate_booking_checkout(self):
        """Guard terminates/checks out booking on the spot, freeing slot and signaling exit barrier."""
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6)

        ts = int(datetime.now().timestamp())
        test_plate = f"KA03EXIT{ts % 10000:04d}"

        # Create spot booking
        create_res = sec_client.post('/api/security/spot-booking', json={
            'license_plate': test_plate,
            'lot_id': 1
        })
        bid = create_res.get_json()['booking']['booking_id']
        slot_number = create_res.get_json()['booking']['slot_number']

        # Verify slot is occupied
        slot_before = self.db.parking_slots.find_one({'slot_number': slot_number, 'lot_id': 1})
        self.assertEqual(slot_before.get('status'), 'occupied')

        # Terminate / checkout booking
        term_res = sec_client.post(f'/api/security/bookings/{bid}/terminate')
        self.assertEqual(term_res.status_code, 200)
        term_data = term_res.get_json()
        self.assertEqual(term_data.get('status'), 'success')
        self.assertTrue(term_data.get('barrier_opened'))
        self.assertIn('dwell_time_minutes', term_data.get('summary', {}))

        # Verify booking status changed to completed in MongoDB
        booking_after = self.db.bookings.find_one({'booking_id': bid})
        self.assertIn(booking_after.get('status'), ('completed', 'completed_overstay'))
        self.assertIsNotNone(booking_after.get('actual_exit_time'))

        # Verify slot is freed to available
        slot_after = self.db.parking_slots.find_one({'slot_number': slot_number, 'lot_id': 1})
        self.assertEqual(slot_after.get('status'), 'available')
        self.assertIsNone(slot_after.get('current_plate'))

    def test_09_manual_barrier_toggle(self):
        """Guard issues manual barrier open/close command."""
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6)

        res = sec_client.post('/api/security/gate/barrier', json={
            'action': 'open',
            'gate_name': 'Gate 1 (North Entry)',
            'reason': 'Emergency VIP access'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data.get('barrier_state'), 'OPENED')

    def test_10_admin_guard_management_crud(self):
        """Admin can list, create, toggle status, and delete security guard accounts."""
        admin_client = get_test_client()
        create_authenticated_session(admin_client, role='admin', user_id=1)

        # 1. Query guards list
        list_res = admin_client.get('/api/admin/guards')
        self.assertEqual(list_res.status_code, 200)
        guards_data = list_res.get_json()
        self.assertEqual(guards_data.get('status'), 'success')
        self.assertGreater(len(guards_data.get('guards', [])), 0)

        # 2. Create new guard
        ts = int(datetime.now().timestamp())
        new_email = f"guard_test_{ts}@smartparking.ai"
        create_res = admin_client.post('/api/admin/guards/create', json={
            'name': 'Officer Arjun V',
            'email': new_email,
            'phone': '9876500055',
            'password': 'guardpassword123',
            'gate': 'Gate 3 (South Bay)',
            'assigned_lot': 'Institutions',
            'lot_id': 1,
            'shift': 'Night Shift (20:00 - 08:00)'
        })
        self.assertEqual(create_res.status_code, 201)
        created_guard = create_res.get_json().get('guard', {})
        new_gid = created_guard.get('user_id')
        self.assertIsNotNone(new_gid)

        # Verify created in MongoDB
        db_guard = self.db.users.find_one({'user_id': new_gid})
        self.assertIsNotNone(db_guard)
        self.assertEqual(db_guard.get('role'), 'security')
        self.assertEqual(db_guard.get('gate'), 'Gate 3 (South Bay)')

        # 3. Toggle guard duty status
        toggle_res = admin_client.post('/api/admin/guards/toggle-status', json={'user_id': new_gid})
        self.assertEqual(toggle_res.status_code, 200)
        self.assertEqual(toggle_res.get_json().get('is_active'), 0)

        # 4. Delete newly created guard
        del_res = admin_client.delete(f'/api/admin/guards/{new_gid}')
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.get_json().get('status'), 'success')

        # Verify removed from MongoDB
        deleted_doc = self.db.users.find_one({'user_id': new_gid})
        self.assertIsNone(deleted_doc)


if __name__ == '__main__':
    unittest.main()
