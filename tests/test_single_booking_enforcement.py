"""
Test Suite: Single Active Booking Enforcement & Rebooking Lifecycle.
Verifies:
1. A driver can successfully create a single active parking reservation.
2. Double-booking prevention: Attempting to book a second slot while holding an active booking is strictly rejected (HTTP 409).
3. Early review block: Reviewing a second slot while holding an active booking is rejected (HTTP 409).
4. Same-vehicle double-booking prevention: A vehicle cannot have multiple active bookings simultaneously.
5. Cancellation releases the restriction: Cancelling an active booking allows immediate rebooking of other slots.
6. Completed bookings do not restrict future reservations.
7. Admin & Security personnel can manage and register walk-ins without user limits.
"""

import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import unittest
from datetime import datetime, timedelta
from tests.conftest import get_test_client, create_authenticated_session, get_future_date_and_time
from core.database import get_mongo_db, ensure_permanent_admin


class TestSingleBookingEnforcement(unittest.TestCase):
    def setUp(self):
        self.client = get_test_client()
        self.db = get_mongo_db()
        ensure_permanent_admin()

        self.driver_uid = 7771
        self.driver_email = 'single.booking.tester@smartparking.edu'
        self.driver_plate = 'KA01SB7771'

        # Fetch valid slots for inst_med
        med_slots = list(self.db.parking_slots.find({'place_id': 'inst_med'}))
        self.slot1_id = med_slots[0]['slot_id']
        self.slot2_id = med_slots[1]['slot_id']
        self.slot3_id = med_slots[2]['slot_id']

        # Clean slate for this test user
        if self.db is not None:
            self.db.bookings.delete_many({'user_id': self.driver_uid})
            self.db.reservations.delete_many({'user_id': self.driver_uid})
            self.db.vehicles.delete_many({'user_id': self.driver_uid})
            self.db.users.delete_many({'user_id': self.driver_uid})

            # Ensure driver and vehicle exist in database
            self.db.users.insert_one({
                'user_id': self.driver_uid,
                'name': 'Single Booking Tester',
                'email': self.driver_email,
                'phone': '9876543210',
                'role': 'user',
                'is_active': 1
            })
            self.db.vehicles.insert_one({
                'vehicle_id': self.driver_uid,
                'user_id': self.driver_uid,
                'license_plate': self.driver_plate,
                'vehicle_type': 'Car',
                'make_model': 'Tata Nexon',
                'color': 'Blue'
            })

            # Ensure test slots are clean and available
            self.db.parking_slots.update_many(
                {'slot_id': {'$in': [self.slot1_id, self.slot2_id, self.slot3_id]}},
                {
                    '$set': {'status': 'available', 'current_plate': None, 'current_reservation_id': None},
                    '$pull': {'reserved_intervals': {'user_id': self.driver_uid}}
                }
            )

        create_authenticated_session(
            self.client,
            role='user',
            user_id=self.driver_uid,
            email=self.driver_email,
            name='Single Booking Tester'
        )

    def tearDown(self):
        if self.db is not None:
            self.db.bookings.delete_many({'user_id': self.driver_uid})
            self.db.reservations.delete_many({'user_id': self.driver_uid})
            self.db.vehicles.delete_many({'user_id': self.driver_uid})
            self.db.users.delete_many({'user_id': self.driver_uid})
            self.db.parking_slots.update_many(
                {'slot_id': {'$in': [self.slot1_id, self.slot2_id, self.slot3_id]}},
                {
                    '$set': {'status': 'available', 'current_plate': None, 'current_reservation_id': None},
                    '$pull': {'reserved_intervals': {'user_id': self.driver_uid}}
                }
            )

    def test_01_user_can_create_single_booking(self):
        """Driver without active bookings should successfully reserve one slot."""
        f_date, f_start, _ = get_future_date_and_time(days_ahead=2, start_hour=11, duration_hours=2)

        res = self.client.post('/booking/confirm', json={
            'slot_id': self.slot1_id,
            'lot_id': 1,
            'place_id': 'inst_med',
            'place_name': 'AJ Institute of Medical Sciences',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': self.driver_plate,
            'vehicle_type': 'Car'
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIsNotNone(data.get('booking', {}).get('booking_id'))

    def test_02_attempt_second_booking_blocked_no_double_booking(self):
        """Driver holding an active booking must be blocked (HTTP 409) from booking a second slot."""
        f_date, f_start, _ = get_future_date_and_time(days_ahead=2, start_hour=11, duration_hours=2)

        # 1. First booking -> Succeeds
        res1 = self.client.post('/booking/confirm', json={
            'slot_id': self.slot1_id,
            'lot_id': 1,
            'place_id': 'inst_med',
            'place_name': 'AJ Institute of Medical Sciences',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': self.driver_plate,
            'vehicle_type': 'Car'
        })
        self.assertEqual(res1.status_code, 201)

        # 2. Attempt second booking for a different slot (Slot 2) -> MUST BE BLOCKED
        res2 = self.client.post('/booking/confirm', json={
            'slot_id': self.slot2_id,
            'lot_id': 1,
            'place_id': 'inst_med',
            'place_name': 'AJ Institute of Medical Sciences',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': self.driver_plate,
            'vehicle_type': 'Car'
        })
        self.assertEqual(res2.status_code, 409)
        data2 = res2.get_json()
        self.assertEqual(data2.get('status'), 'error')
        self.assertIn('Active booking limit reached', data2.get('message', ''))
        self.assertIn('cancel your existing booking', data2.get('message', ''))

    def test_03_attempt_second_booking_review_blocked(self):
        """Driver holding an active booking is rejected during review step before paying."""
        f_date, f_start, _ = get_future_date_and_time(days_ahead=2, start_hour=11, duration_hours=2)

        # Create active booking
        self.client.post('/booking/confirm', json={
            'slot_id': self.slot1_id,
            'lot_id': 1,
            'place_id': 'inst_med',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': self.driver_plate,
            'vehicle_type': 'Car'
        })

        # Review another slot
        rev_res = self.client.post('/booking/review', json={
            'slot_id': self.slot2_id,
            'place_id': 'inst_med',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': self.driver_plate
        })
        self.assertEqual(rev_res.status_code, 409)
        self.assertIn('Active booking limit reached', rev_res.get_json().get('message', ''))

    def test_04_cancel_booking_releases_limit_and_allows_rebooking(self):
        """Cancelling active booking releases slot back to available and allows user to rebook another slot immediately."""
        f_date, f_start, _ = get_future_date_and_time(days_ahead=3, start_hour=14, duration_hours=2)

        # 1. Book Slot 1
        res1 = self.client.post('/booking/confirm', json={
            'slot_id': self.slot1_id,
            'lot_id': 1,
            'place_id': 'inst_med',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': self.driver_plate,
            'vehicle_type': 'Car'
        })
        self.assertEqual(res1.status_code, 201)
        bid = res1.get_json()['booking']['booking_id']

        # 2. Cancel the booking
        cancel_res = self.client.post(f'/booking/{bid}/cancel')
        self.assertEqual(cancel_res.status_code, 200)

        # Verify status in MongoDB is cancelled
        b_doc = self.db.bookings.find_one({'booking_id': bid})
        self.assertEqual(b_doc.get('status'), 'cancelled')

        # 3. User now rebooks a DIFFERENT slot (Slot 2) -> MUST SUCCEED
        rebook_res = self.client.post('/booking/confirm', json={
            'slot_id': self.slot2_id,
            'lot_id': 1,
            'place_id': 'inst_med',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': self.driver_plate,
            'vehicle_type': 'Car'
        })
        self.assertEqual(rebook_res.status_code, 201)
        rebook_data = rebook_res.get_json()
        self.assertEqual(rebook_data.get('status'), 'success')
        self.assertNotEqual(rebook_data['booking']['booking_id'], bid)
        self.assertEqual(rebook_data['booking']['slot_id'], self.slot2_id)

    def test_05_completed_booking_allows_rebooking(self):
        """A past/completed parking session does not restrict driver from booking a new slot."""
        f_date, f_start, _ = get_future_date_and_time(days_ahead=3, start_hour=10, duration_hours=1)

        # Seed an already completed booking
        old_bid = f"BK-COMPLETED-{self.driver_uid}"
        self.db.bookings.insert_one({
            'booking_id': old_bid,
            'user_id': self.driver_uid,
            'vehicle_plate': self.driver_plate,
            'status': 'completed',
            'booking_date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
            'slot_id': self.slot1_id
        })

        # New booking must be allowed
        res = self.client.post('/booking/confirm', json={
            'slot_id': self.slot3_id,
            'lot_id': 1,
            'place_id': 'inst_med',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '1 Hour',
            'vehicle_plate': self.driver_plate,
            'vehicle_type': 'Car'
        })
        self.assertEqual(res.status_code, 201)

    def test_06_security_guard_not_restricted_for_walkin_spot_bookings(self):
        """Security Guard registering walk-in guests at gate is not restricted by single booking limit."""
        sec_client = get_test_client()
        create_authenticated_session(sec_client, role='security', user_id=6, email='security@smartparking.ai')

        ts = int(datetime.now().timestamp())
        plate_a = f"KA01WK{ts % 10000:04d}A"
        plate_b = f"KA01WK{ts % 10000:04d}B"

        # Guard registers 1st walk-in
        res1 = sec_client.post('/api/security/spot-booking', json={
            'license_plate': plate_a,
            'lot_id': 1,
            'driver_name': 'Walk-in Driver 1'
        })
        self.assertEqual(res1.status_code, 201)

        # Guard registers 2nd walk-in -> Allowed because guard creates spot bookings on behalf of different drivers
        res2 = sec_client.post('/api/security/spot-booking', json={
            'license_plate': plate_b,
            'lot_id': 1,
            'driver_name': 'Walk-in Driver 2'
        })
        self.assertEqual(res2.status_code, 201)


if __name__ == '__main__':
    unittest.main()
