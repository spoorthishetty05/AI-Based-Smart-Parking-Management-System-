"""
Unit and Integration Tests for Razorpay Sandbox / Dummy Payment Gateway System.
Validates:
  1. Order generation with rupee to paise conversion and MongoDB persistence.
  2. Cryptographic signature calculation and verification (HMAC-SHA256 & Sandbox fallbacks).
  3. RESTful endpoints: /api/payment/create-order, /api/payment/verify, /api/payment/transactions.
  4. End-to-end booking confirmation with online payment status.
  5. Overstay penalty clearance via Razorpay.
"""

import unittest
from datetime import datetime
from config import Config
from app import app
from core.database import get_mongo_db
from tests.conftest import get_test_client, get_future_date_and_time
from core.payment_service import (
    PaymentService, payment_service, create_payment_order,
    verify_payment, process_booking_payment, process_penalty_payment
)


class TestPaymentGatewayModule(unittest.TestCase):
    """Test suite covering Razorpay Dummy / Sandbox Payment Gateway flows."""

    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['MAIL_SUPPRESS_SEND'] = True
        cls.client = app.test_client()
        cls.db = get_mongo_db()

    def setUp(self):
        self.client = get_test_client()
        self.db = get_mongo_db()
        self.test_user_id = 99991
        self.test_email = 'razorpay.tester@smartparking.ai'

        # Seed test user and vehicle
        if self.db is not None:
            self.db.users.delete_many({'user_id': self.test_user_id})
            self.db.vehicles.delete_many({'user_id': self.test_user_id})
            self.db.payment_transactions.delete_many({'user_id': self.test_user_id})
            self.db.parking_slots.update_many({}, {'$pull': {'reserved_intervals': {'user_id': self.test_user_id}}})

            self.db.users.insert_one({
                'user_id': self.test_user_id,
                'email': self.test_email,
                'name': 'Razorpay Test Driver',
                'role': 'user',
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            self.db.vehicles.insert_one({
                'user_id': self.test_user_id,
                'license_plate': 'KA04RZ9999',
                'vehicle_type': 'Car',
                'make_model': 'Tata EV',
                'color': 'Blue'
            })

    def tearDown(self):
        if self.db is not None:
            self.db.users.delete_many({'user_id': self.test_user_id})
            self.db.vehicles.delete_many({'user_id': self.test_user_id})
            self.db.payment_transactions.delete_many({'user_id': self.test_user_id})
            self.db.parking_slots.update_many({}, {'$pull': {'reserved_intervals': {'user_id': self.test_user_id}}})

    def test_01_create_payment_order(self):
        """Verifies order creation converts rupees to paise and stores in MongoDB."""
        order = create_payment_order(amount=80.0, receipt='TEST-RC-001', user_id=self.test_user_id)
        self.assertIn('id', order)
        self.assertTrue(order['id'].startswith('order_'))
        self.assertEqual(order['amount'], 8000)  # 80 INR = 8000 Paise
        self.assertEqual(order['amount_in_rupees'], 80.0)
        self.assertEqual(order['currency'], 'INR')
        self.assertEqual(order['status'], 'created')

        if self.db is not None:
            persisted = self.db.payment_orders.find_one({'id': order['id']})
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted['amount'], 8000)

    def test_02_verify_cryptographic_signature(self):
        """Verifies HMAC-SHA256 signature computation and rejection of tampered signatures."""
        service = PaymentService(key_id='rzp_test_sample', key_secret='sample_secret_key_123', mock_mode=False)
        order_id = 'order_test_123456'
        payment_id = 'pay_test_987654'

        valid_sig = service.compute_signature(order_id, payment_id)
        self.assertTrue(service.verify_signature(order_id, payment_id, valid_sig))

        # Tampered signature must fail
        self.assertFalse(service.verify_signature(order_id, payment_id, 'invalid_tampered_signature'))

    def test_03_verify_and_record_transaction(self):
        """Verifies successful payment recording into payment_transactions."""
        service = PaymentService(mock_mode=True)
        order_id = service.generate_order_id()
        payment_id = service.generate_payment_id()
        sig = service.compute_signature(order_id, payment_id)

        success, tx = service.verify_and_record_payment(
            payment_id=payment_id,
            order_id=order_id,
            signature=sig,
            amount=80.0,
            user_id=self.test_user_id,
            payment_method='UPI / QR'
        )
        self.assertTrue(success)
        self.assertEqual(tx['payment_id'], payment_id)
        self.assertEqual(tx['status'], 'captured')
        self.assertEqual(tx['amount'], 80.0)

        if self.db is not None:
            found = self.db.payment_transactions.find_one({'payment_id': payment_id})
            self.assertIsNotNone(found)
            self.assertEqual(found['status'], 'captured')

    def test_04_api_create_order_endpoint(self):
        """Tests POST /api/payment/create-order returns valid JSON order object."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.test_user_id
            sess['user_email'] = self.test_email

        res = self.client.post('/api/payment/create-order', json={'amount': 120.0})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('order', data)
        self.assertEqual(data['order']['amount'], 12000)
        self.assertIn('key_id', data)

    def test_05_api_verify_payment_endpoint(self):
        """Tests POST /api/payment/verify successfully verifies and returns captured transaction."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.test_user_id
            sess['user_email'] = self.test_email

        order_id = payment_service.generate_order_id()
        payment_id = payment_service.generate_payment_id()
        sig = payment_service.compute_signature(order_id, payment_id)

        res = self.client.post('/api/payment/verify', json={
            'razorpay_payment_id': payment_id,
            'razorpay_order_id': order_id,
            'razorpay_signature': sig,
            'amount': 60.0,
            'method': 'Card (Visa Test)'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['transaction']['payment_id'], payment_id)

    def test_06_booking_with_online_payment(self):
        """Tests booking confirmation with Razorpay payment details persisted as Paid."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.test_user_id
            sess['user_email'] = self.test_email
            sess['user_name'] = 'Razorpay Tester'
            sess['user_role'] = 'user'

        f_date, f_start, f_end = get_future_date_and_time(days_ahead=7, start_hour=15, duration_hours=1)
        slot = self.db.parking_slots.find_one({
            'place_id': 'inst_med',
            'reserved_intervals': {
                '$not': {
                    '$elemMatch': {
                        'date': f_date,
                        'start_time': {'$lt': f_end},
                        'end_time': {'$gt': f_start}
                    }
                }
            }
        })
        if not slot:
            slot = self.db.parking_slots.find_one({'place_id': 'inst_med'})
            self.db.parking_slots.update_one(
                {'slot_id': slot['slot_id']},
                {'$pull': {'reserved_intervals': {'date': f_date}}}
            )
        slot_id = slot['slot_id']

        payment_id = payment_service.generate_payment_id()
        order_id = payment_service.generate_order_id()
        sig = payment_service.compute_signature(order_id, payment_id)

        payload = {
            'slot_id': slot_id,
            'place_id': 'inst_med',
            'place_name': 'AJ Institute of Medical Sciences',
            'category': 'Institutions',
            'facility_category': 'Institutions',
            'booking_date': f_date,
            'start_time': f_start,
            'duration': '1 Hour',
            'vehicle_plate': 'KA04RZ9999',
            'vehicle_type': 'Car',
            'payment_id': payment_id,
            'payment_order_id': order_id,
            'payment_signature': sig,
            'payment_method': 'Razorpay (UPI)',
            'payment_status': 'Paid'
        }

        res = self.client.post('/booking/confirm', json=payload)
        self.assertEqual(res.status_code, 201, f"Booking confirm failed with: {res.get_json()}")
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        booking = data['booking']
        self.assertEqual(booking.get('payment_status'), 'Paid')
        self.assertEqual(booking.get('payment_id'), payment_id)

        # Cleanup booking
        if self.db is not None and 'booking_id' in booking:
            self.db.bookings.delete_many({'booking_id': booking['booking_id']})
            self.db.reservations.delete_many({'booking_id': booking['booking_id']})
            self.db.parking_slots.update_one(
                {'slot_id': slot_id},
                {'$pull': {'reserved_intervals': {'booking_id': booking['booking_id']}}}
            )

    def test_07_penalty_settlement_via_razorpay(self):
        """Tests POST /api/reservations/<booking_id>/pay-penalty marks penalty as Paid."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.test_user_id
            sess['user_email'] = self.test_email

        booking_id = f"BK-TEST-{datetime.now().strftime('%M%S')}"
        if self.db is not None:
            self.db.bookings.insert_one({
                'booking_id': booking_id,
                'user_id': self.test_user_id,
                'vehicle_plate': 'KA04RZ9999',
                'status': 'overstayed',
                'overstay_penalty': 120.0,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

        order_id = payment_service.generate_order_id()
        payment_id = payment_service.generate_payment_id()
        sig = payment_service.compute_signature(order_id, payment_id)

        res = self.client.post(f'/api/reservations/{booking_id}/pay-penalty', json={
            'razorpay_payment_id': payment_id,
            'razorpay_order_id': order_id,
            'razorpay_signature': sig,
            'amount': 120.0,
            'method': 'UPI / QR'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')

        if self.db is not None:
            updated = self.db.bookings.find_one({'booking_id': booking_id})
            self.assertEqual(updated.get('penalty_payment_status'), 'Paid')
            self.assertEqual(updated.get('penalty_payment_id'), payment_id)
            self.db.bookings.delete_many({'booking_id': booking_id})


if __name__ == '__main__':
    unittest.main()
