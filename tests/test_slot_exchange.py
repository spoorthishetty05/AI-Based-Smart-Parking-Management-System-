"""
Test Suite: Peer-to-Peer Slot Exchange (Module 7).
Verifies:
1. Slot listing for exchange (/api/exchange/offer).
2. Retrieval of available exchange listings (/api/exchange/search).
3. Slot exchange request lifecycle (/api/exchange/request).
4. Acceptance of exchange request & atomic slot swap (/api/exchange/respond).
5. Cancellation and withdrawal flows.
"""

import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import unittest
from tests.conftest import get_test_client, create_authenticated_session
from core.database import get_db_connection, get_mongo_db

class TestSlotExchangeModule(unittest.TestCase):
    def setUp(self):
        self.client = get_test_client()
        self.user1_id = 1
        self.user2_id = 2

    def test_01_seed_and_offer_slot_for_exchange(self):
        """User 1 should be able to seed a test booking and offer it for exchange."""
        create_authenticated_session(self.client, role='user', user_id=self.user1_id)

        # 1. Quick seed a booking for user 1
        seed_res = self.client.post('/api/exchange/quick-seed-booking', json={
            'user_id': self.user1_id,
            'vehicle_type': 'Car'
        })
        self.assertEqual(seed_res.status_code, 201)
        res_data = seed_res.json
        res_id = res_data.get('reservation_id')
        self.assertIsNotNone(res_id)

        # 2. Offer the booking for exchange
        offer_res = self.client.post('/api/exchange/offer', json={
            'user_id': self.user1_id,
            'reservation_id': res_id,
            'notes': 'Prefer ground floor slot'
        })
        self.assertEqual(offer_res.status_code, 201)
        listing_id = offer_res.json.get('listing_id')
        self.assertIsNotNone(listing_id)

        # 3. Check search/browse from another user's perspective
        create_authenticated_session(self.client, role='user', user_id=self.user2_id)
        search_res = self.client.get(f'/api/exchange/search?user_id={self.user2_id}')
        self.assertEqual(search_res.status_code, 200)
        listings = search_res.json.get('opportunities', [])
        found = any(l.get('listing_id') == listing_id for l in listings)
        self.assertTrue(found, "Newly offered slot should be visible in search listings for user 2")

    def test_02_full_exchange_lifecycle_and_swap(self):
        """End-to-end exchange flow: User 1 offers -> User 2 requests -> User 1 accepts."""
        # Step A: Seed booking for User 1 and offer it
        create_authenticated_session(self.client, role='user', user_id=self.user1_id)
        u1_seed = self.client.post('/api/exchange/quick-seed-booking', json={'user_id': self.user1_id}).json
        u1_res_id = u1_seed['reservation_id']
        u1_slot_no = u1_seed['slot_number']

        offer_res = self.client.post('/api/exchange/offer', json={
            'user_id': self.user1_id,
            'reservation_id': u1_res_id
        }).json
        listing_id = offer_res['listing_id']

        # Step B: Seed booking for User 2
        create_authenticated_session(self.client, role='user', user_id=self.user2_id)
        u2_seed = self.client.post('/api/exchange/quick-seed-booking', json={'user_id': self.user2_id}).json
        u2_res_id = u2_seed['reservation_id']
        u2_slot_no = u2_seed['slot_number']

        # Step C: User 2 requests exchange
        req_res = self.client.post('/api/exchange/request', json={
            'requester_user_id': self.user2_id,
            'listing_id': listing_id,
            'requester_reservation_id': u2_res_id
        })
        self.assertEqual(req_res.status_code, 201)
        request_id = req_res.json.get('request_id')
        self.assertIsNotNone(request_id)

        # Step D: User 1 accepts the exchange
        create_authenticated_session(self.client, role='user', user_id=self.user1_id)
        respond_res = self.client.post('/api/exchange/respond', json={
            'user_id': self.user1_id,
            'request_id': request_id,
            'action': 'accept'
        })
        self.assertEqual(respond_res.status_code, 200)
        self.assertEqual(respond_res.json.get('status'), 'success')

        # Step E: Verify swap in database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT r.slot_id, s.slot_number FROM reservations r JOIN parking_slots s ON r.slot_id = s.slot_id WHERE r.reservation_id = ?", (u1_res_id,))
        u1_new = cur.fetchone()
        cur.execute("SELECT r.slot_id, s.slot_number FROM reservations r JOIN parking_slots s ON r.slot_id = s.slot_id WHERE r.reservation_id = ?", (u2_res_id,))
        u2_new = cur.fetchone()
        conn.close()

        # Slots must have swapped!
        self.assertEqual(u1_new['slot_number'], u2_slot_no)
        self.assertEqual(u2_new['slot_number'], u1_slot_no)

    def test_03_cancel_exchange_offer(self):
        """User should be able to withdraw an active exchange offer."""
        create_authenticated_session(self.client, role='user', user_id=self.user1_id)
        seed = self.client.post('/api/exchange/quick-seed-booking', json={'user_id': self.user1_id}).json
        offer = self.client.post('/api/exchange/offer', json={
            'user_id': self.user1_id,
            'reservation_id': seed['reservation_id']
        }).json
        listing_id = offer['listing_id']

        # Cancel offer
        cancel_res = self.client.post('/api/exchange/cancel-offer', json={
            'user_id': self.user1_id,
            'listing_id': listing_id
        })
        self.assertEqual(cancel_res.status_code, 200)
        self.assertEqual(cancel_res.json.get('status'), 'success')

if __name__ == '__main__':
    unittest.main()
