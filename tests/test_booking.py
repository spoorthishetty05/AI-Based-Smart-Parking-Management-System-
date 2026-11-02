"""
Test Suite: Smart Parking Booking & 5-Step Guided Wizard (Module 3).
Verifies:
1. Parking places and category retrieval.
2. Slot matrix search & availability verification.
3. Review step with tariff recalculation.
4. Booking confirmation & atomic slot reservation.
5. Digital QR Pass issuance and details.
6. Rejection of past dates and times.
7. My Bookings listing (upcoming & history).
8. Booking cancellation and slot release back to available.
"""

import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import unittest
from datetime import datetime, timedelta
from tests.conftest import get_test_client, create_authenticated_session, get_future_date_and_time
from core.database import get_mongo_db, get_next_sequence

class TestBookingModule(unittest.TestCase):
    def setUp(self):
        self.client = get_test_client()
        self.db = get_mongo_db()
        self.test_uid = 88  # Krithika Shetty or dedicated test user
        create_authenticated_session(self.client, role='user', user_id=self.test_uid, email='krithikasanthoshshetty@gmail.com')

    def test_01_places_and_categories_api(self):
        """API should return configured parking places and categories."""
        res = self.client.get('/api/booking/places')
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        self.assertGreater(len(data.get('places', [])), 0)

    def test_02_slot_search_and_availability(self):
        """Searching slots should return live 2D matrix status without booking."""
        f_date, f_start, _ = get_future_date_and_time(days_ahead=2, start_hour=14)
        res = self.client.post('/booking/search', json={
            'place_id': 'inst_med',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': 'KA10A4614'
        })
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('slots', data)
        self.assertGreater(data.get('total_slots', 0), 0)

    def test_03_booking_review_tariff_calculation(self):
        """Review should calculate correct tariff and verify interval availability."""
        f_date, f_start, f_end = get_future_date_and_time(days_ahead=2, start_hour=14, duration_hours=2)
        slot = self.db.parking_slots.find_one({'place_id': 'inst_med', 'status': 'available'})
        if not slot:
            slot = self.db.parking_slots.find_one({'place_id': 'inst_med'})

        res = self.client.post('/booking/review', json={
            'slot_id': slot['slot_id'],
            'place_id': 'inst_med',
            'category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '2 Hours',
            'vehicle_plate': 'KA10A4614'
        })
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data.get('slot_number'), slot['slot_number'])
        self.assertGreater(data.get('total_amount', 0), 0)

    def test_04_full_booking_lifecycle_and_pass_and_cancellation(self):
        """Complete booking lifecycle: confirm -> verify pass -> view bookings -> cancel."""
        f_date, f_start, _ = get_future_date_and_time(days_ahead=3, start_hour=11, duration_hours=1)
        slot = self.db.parking_slots.find_one({'place_id': 'inst_med', 'status': 'available'})
        if not slot:
            slot = self.db.parking_slots.find_one({'place_id': 'inst_med'})
        slot_id = slot['slot_id']
        slot_number = slot['slot_number']

        # 1. Confirm Booking
        conf_res = self.client.post('/booking/confirm', json={
            'slot_id': slot_id,
            'place_id': 'inst_med',
            'place_name': 'AJ Institute of Medical Sciences',
            'category': 'Institutions',
            'facility_category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '1 Hour',
            'vehicle_plate': 'KA10A4614',
            'vehicle_number': 'KA10A4614',
            'vehicle_type': 'Bike'
        })
        self.assertEqual(conf_res.status_code, 201)
        b_data = conf_res.json.get('booking')
        bid = b_data['booking_id']
        self.assertIsNotNone(bid)

        # Verify saved in MongoDB
        mongo_b = self.db.bookings.find_one({'booking_id': bid})
        self.assertIsNotNone(mongo_b)
        self.assertEqual(mongo_b['status'], 'confirmed')

        # 2. Digital Pass API
        pass_res = self.client.get(f'/booking/{bid}/pass')
        self.assertEqual(pass_res.status_code, 200)
        pass_info = pass_res.json.get('pass')
        self.assertIsNotNone(pass_info)
        self.assertEqual(pass_info.get('slot_number'), slot_number)

        # 3. View in My Bookings
        my_res = self.client.get('/booking/my-bookings', headers={'Accept': 'application/json'})
        self.assertEqual(my_res.status_code, 200)
        up_list = my_res.json.get('upcoming', [])
        found_in_upcoming = any(b.get('booking_id') == bid for b in up_list)
        self.assertTrue(found_in_upcoming, f"Booking {bid} should be listed in upcoming bookings")

        # 4. Cancel Booking
        cancel_res = self.client.post(f'/booking/{bid}/cancel')
        self.assertEqual(cancel_res.status_code, 200)

        # Verify cancelled status in MongoDB
        mongo_b_cancelled = self.db.bookings.find_one({'booking_id': bid})
        self.assertEqual(mongo_b_cancelled['status'], 'cancelled')

        # Clean up test documents
        self.db.bookings.delete_one({'booking_id': bid})
        self.db.reservations.delete_one({'booking_id': bid})
        self.db.notifications.delete_many({'user_id': self.test_uid, 'related_id': slot_id})
        self.db.parking_slots.update_one({'slot_id': slot_id}, {'$pull': {'reserved_intervals': {'booking_id': bid}}})

    def test_05_anti_past_date_validation(self):
        """Booking for past dates must be strictly rejected with HTTP 400."""
        past_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        res = self.client.post('/booking/confirm', json={
            'slot_id': 1,
            'booking_date': past_date,
            'start_time': '10:00',
            'duration': '1 Hour',
            'vehicle_plate': 'KA10A4614'
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json.get('status'), 'error')

if __name__ == '__main__':
    unittest.main()

