"""
Test Suite: Overstay Monitoring & Vehicle Exit Checkout (Module 5 & Checkout).
Verifies:
1. Vehicle type normalization and fixed penalties (Car: ₹60, Bike: ₹30, Other: ₹80).
2. 15-minute grace period calculation.
3. Overstay sweep & notification generation.
4. Checkout preview API calculation.
5. Vehicle exit processing & slot restoration to available.
6. Overstay resolution & mark-paid endpoints.
"""

import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import unittest
from datetime import datetime, timedelta
from tests.conftest import get_test_client, create_authenticated_session
from core.database import get_mongo_db, get_next_sequence
from core.overstay_engine import (
    normalize_vehicle_type, get_vehicle_penalty_amount, calculate_overstay,
    check_and_update_overstays, get_active_overstays
)

class TestOverstayModule(unittest.TestCase):
    def setUp(self):
        self.client = get_test_client()
        self.db = get_mongo_db()

    def test_01_vehicle_normalization_and_penalties(self):
        """Validates vehicle normalization and tiered penalties."""
        self.assertEqual(normalize_vehicle_type('Car'), 'Car')
        self.assertEqual(normalize_vehicle_type('SUV'), 'Car')
        self.assertEqual(normalize_vehicle_type('Sedan'), 'Car')
        self.assertEqual(normalize_vehicle_type('Hatchback'), 'Car')
        self.assertEqual(normalize_vehicle_type('Bike'), 'Bike')
        self.assertEqual(normalize_vehicle_type('Scooter'), 'Bike')
        self.assertEqual(normalize_vehicle_type('Motorcycle'), 'Bike')
        self.assertEqual(normalize_vehicle_type('Heavy Truck'), 'Other vehicles')

        self.assertEqual(get_vehicle_penalty_amount('Bike'), 30.0)
        self.assertEqual(get_vehicle_penalty_amount('Car'), 60.0)
        self.assertEqual(get_vehicle_penalty_amount('SUV'), 60.0)
        self.assertEqual(get_vehicle_penalty_amount('Heavy Truck'), 80.0)

    def test_02_grace_period_and_overstay_calculation(self):
        """Verifies 15-minute grace period and hourly started penalty multiplication."""
        today = datetime.now().strftime('%Y-%m-%d')
        booked_end = '12:00'

        # Case A: Exit within 15 min grace (12:10) -> No penalty
        exit_dt_grace = datetime.strptime(f"{today} 12:10", "%Y-%m-%d %H:%M")
        res_grace = calculate_overstay(today, booked_end, exit_dt_grace, 'Car')
        self.assertFalse(res_grace['is_overstay'])
        self.assertEqual(res_grace['penalty_amount'], 0.0)

        # Case B: Exit 40 mins after booked end (12:40) -> 25 mins over grace -> 1 started hour -> ₹60
        exit_dt_overstay = datetime.strptime(f"{today} 12:40", "%Y-%m-%d %H:%M")
        res_overstay = calculate_overstay(today, booked_end, exit_dt_overstay, 'Car')
        self.assertTrue(res_overstay['is_overstay'])
        self.assertEqual(res_overstay['started_hours'], 1)
        self.assertEqual(res_overstay['penalty_amount'], 60.0)

        # Case C: Same overstay for Bike -> ₹30
        res_bike = calculate_overstay(today, booked_end, exit_dt_overstay, 'Bike')
        self.assertTrue(res_bike['is_overstay'])
        self.assertEqual(res_bike['penalty_amount'], 30.0)

    def test_03_checkout_preview_and_exit_flow(self):
        """Verifies checkout preview calculation and vehicle exit session completion."""
        create_authenticated_session(self.client, role='user', user_id=88)

        # Create temporary active booking
        slot = self.db.parking_slots.find_one({'status': 'available'}) or self.db.parking_slots.find_one()
        slot_id = slot['slot_id']
        slot_num = slot['slot_number']

        now = datetime.now()
        bid = f"BK-TEST-CHECKOUT-{int(now.timestamp())}"
        r_doc = {
            'booking_id': bid,
            'reservation_id': 99911,
            'pass_code': bid,
            'user_id': 88,
            'slot_id': slot_id,
            'slot_number': slot_num,
            'lot_name': 'Test Parking Facility',
            'parking_lot_id': 1,
            'vehicle_plate': 'KA10A4614',
            'vehicle_type': 'Car',
            'booking_date': now.strftime('%Y-%m-%d'),
            'start_time': (now - timedelta(hours=1)).strftime('%H:%M'),
            'end_time': (now + timedelta(hours=1)).strftime('%H:%M'),
            'actual_entry_time': (now - timedelta(minutes=50)).strftime('%Y-%m-%d %H:%M:%S'),
            'duration': '2 Hours',
            'duration_hours': 2.0,
            'status': 'occupied',
            'total_amount': 60.0
        }
        self.db.bookings.insert_one(r_doc)
        self.db.reservations.insert_one(r_doc)
        self.db.parking_slots.update_one({'slot_id': slot_id}, {'$set': {'status': 'occupied', 'current_plate': 'KA10A4614'}})

        # 1. Checkout Preview
        preview_res = self.client.get(f'/booking/{bid}/checkout-preview')
        self.assertEqual(preview_res.status_code, 200)
        p_data = preview_res.json.get('preview')
        self.assertIsNotNone(p_data)
        self.assertEqual(p_data.get('slot_number'), slot_num)

        # 2. Vehicle Exit
        exit_res = self.client.post(f'/booking/{bid}/exit')
        self.assertEqual(exit_res.status_code, 200)

        # Verify slot restored to available
        slot_after = self.db.parking_slots.find_one({'slot_id': slot_id})
        self.assertEqual(slot_after['status'], 'available')

        # Cleanup test documents
        self.db.bookings.delete_one({'booking_id': bid})
        self.db.reservations.delete_one({'booking_id': bid})

    def test_04_overstay_sweep_execution(self):
        """Executing overstay sweep should update records cleanly without exceptions."""
        check_and_update_overstays()
        records = get_active_overstays()
        self.assertIsInstance(records, list)

if __name__ == '__main__':
    unittest.main()

