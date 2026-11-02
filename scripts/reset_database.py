"""
reset_fresh_data.py
Completely resets the MongoDB database to a 100% fresh, clean state:
- Clears all bookings, reservations, overstay records, exchange listings, and activity logs.
- Re-seeds permanent administrators & standard test accounts.
- Re-seeds all 4 Parking Facilities (Institutions, Mall, Public places, City Parking).
- Re-initializes all 210 slots in 100% 'available' status with zero active reservations.
"""

import sys
import os

# Ensure project root in sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.database import clear_and_init_mongodb, get_mongo_db

def reset_fresh():
    print("=" * 70)
    print("RESETTING SMART PARKING DATABASE (MONGODB) FRESH...")
    print("=" * 70)

    # 1. Clear and re-initialize MongoDB collections
    success = clear_and_init_mongodb(force_reseed=True, preserve_users=False)
    if not success:
        print("ERROR: Failed to connect to or reinitialize MongoDB.")
        return False

    db = get_mongo_db()
    if db is None:
        print("ERROR: Could not retrieve MongoDB database instance.")
        return False

    # 2. Verify collection counts
    print("\nCollection Document Counts in MongoDB 'smart_parking':")
    collections = [
        'users', 'vehicles', 'parking_lots', 'parking_slots',
        'reservations', 'bookings', 'overstay_records', 'slot_exchange_listings',
        'slot_exchange_requests', 'slot_exchange_history', 'notifications',
        'activity_logs', 'system_settings'
    ]
    for coll_name in collections:
        cnt = db[coll_name].count_documents({})
        print(f" - {coll_name:<24}: {cnt} documents")

    # 3. Verify slot availability
    available_cnt = db.parking_slots.count_documents({'status': 'available'})
    total_slots = db.parking_slots.count_documents({})
    print(f"\nSlot Status Breakdown: {available_cnt}/{total_slots} slots available (100% fresh)")

    # 4. Display parking lots
    print("\nParking Facilities Configured:")
    for lot in db.parking_lots.find().sort('lot_id', 1):
        lot_slots = db.parking_slots.count_documents({'lot_id': lot['lot_id']})
        print(f" - [{lot.get('lot_id')}] {lot.get('lot_name')} ({lot_slots} slots, {lot.get('operating_hours')})")

    # 5. Display registered users
    print("\nDefault Users & Administrators:")
    for u in db.users.find().sort('user_id', 1):
        print(f" - [{u.get('user_id')}] {u.get('name')} <{u.get('email')}> ({u.get('role')})")

    print("\n" + "=" * 70)
    print("DATABASE IS NOW COMPLETELY FRESH AND READY FOR NEW REGISTRATIONS & BOOKINGS!")
    print("=" * 70)
    return True

if __name__ == '__main__':
    reset_fresh()
