import sys, os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
"""
MongoDB Cleanup Script for AI-Based Smart Parking System
Preserves ONLY Anush's existing user account (anush@gmail.com, user_id: 3) and associated vehicle.
Removes test users, test vehicles, test bookings, reservations, overstays, notifications, and logs.
Preserves all parking lots, parking slots, system settings, counters, and collection structures.
"""

import sys
import pymongo
from bson import ObjectId

def run_cleanup():
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['smart_parking']

    print("==================================================================")
    print("MONGODB DATABASE CLEANUP: PRESERVING ONLY ANUSH'S ACCOUNT")
    print("==================================================================")

    # 1. Verify Anush exists
    anush = db.users.find_one({'email': 'anush@gmail.com'})
    if not anush:
        print("ERROR: Anush's account (anush@gmail.com) was not found in users collection! Aborting cleanup.")
        sys.exit(1)

    anush_id = anush['_id']
    anush_user_id = anush.get('user_id', 3)
    print(f"CONFIRMED ANUSH ACCOUNT:")
    print(f"  _id: {anush_id}")
    print(f"  user_id: {anush_user_id}")
    print(f"  name: {anush.get('name')}")
    print(f"  email: {anush.get('email')}")
    print(f"  phone: {anush.get('phone')}")
    print(f"  vehicles: {len(anush.get('vehicles', []))} vehicle(s)")

    # 2. Pre-cleanup counts
    print("\n--- PRE-CLEANUP RECORD COUNTS ---")
    pre_counts = {}
    for col_name in sorted(db.list_collection_names()):
        pre_counts[col_name] = db[col_name].count_documents({})
        print(f"  {col_name}: {pre_counts[col_name]}")

    # 3. Clean users: delete all where _id != anush_id
    del_users = db.users.delete_many({'_id': {'$ne': anush_id}})
    print(f"\n[Users] Deleted {del_users.deleted_count} test user account(s).")

    # 4. Clean vehicles: keep only Anush's vehicle (user_id == 3 or license_plate == 'KA91MK0987')
    del_vehicles = db.vehicles.delete_many({
        '$nor': [
            {'user_id': anush_user_id},
            {'license_plate': 'KA91MK0987'}
        ]
    })
    print(f"[Vehicles] Deleted {del_vehicles.deleted_count} test vehicle(s).")

    # 5. Clean test bookings & reservations
    del_bookings = db.bookings.delete_many({})
    print(f"[Bookings] Deleted {del_bookings.deleted_count} test booking(s).")

    del_reservations = db.reservations.delete_many({})
    print(f"[Reservations] Deleted {del_reservations.deleted_count} test reservation(s).")

    # 6. Clean overstay records
    del_overstays = db.overstay_records.delete_many({})
    print(f"[Overstay Records] Deleted {del_overstays.deleted_count} test overstay record(s).")

    # 7. Clean notifications
    del_notifs = db.notifications.delete_many({})
    print(f"[Notifications] Deleted {del_notifs.deleted_count} test notification(s).")

    # 8. Clean logs
    del_act_logs = db.activity_logs.delete_many({})
    print(f"[Activity Logs] Deleted {del_act_logs.deleted_count} test activity log(s).")

    del_login_logs = db.login_logs.delete_many({})
    print(f"[Login Logs] Deleted {del_login_logs.deleted_count} test login log(s).")

    # 9. Clean slot exchange
    db.slot_exchange_listings.delete_many({})
    db.slot_exchange_requests.delete_many({})
    print(f"[Slot Exchange] Cleaned test exchange listings & requests.")

    # 10. Reset parking slot statuses back to 'available'
    reset_slots = db.parking_slots.update_many(
        {'status': {'$in': ['occupied', 'overstayed', 'reserved']}},
        {'$set': {
            'status': 'available',
            'current_reservation_id': None,
            'current_plate': None
        }}
    )
    print(f"[Parking Slots] Preserved all {db.parking_slots.count_documents({})} slots (reset {reset_slots.modified_count} test-occupied slots to 'available').")

    # 11. Reset simulated time offset to live
    db.system_settings.update_one(
        {'setting_key': 'sim_offset_seconds'},
        {'$set': {'setting_value': '0'}},
        upsert=True
    )
    print(f"[System Settings] Preserved all {db.system_settings.count_documents({})} settings (reset sim_offset_seconds to 0).")

    # 12. Post-cleanup verification
    print("\n--- POST-CLEANUP RECORD COUNTS ---")
    for col_name in sorted(db.list_collection_names()):
        cnt = db[col_name].count_documents({})
        print(f"  {col_name}: {cnt}")

    # Verify Anush still exists and is untouched
    anush_post = db.users.find_one({'email': 'anush@gmail.com'})
    assert anush_post is not None, "FATAL: Anush account missing after cleanup!"
    assert anush_post['_id'] == anush_id, "FATAL: Anush _id changed!"
    assert anush_post['password_hash'] == anush['password_hash'], "FATAL: Password hash modified!"
    assert db.users.count_documents({}) == 1, f"Expected exactly 1 user in users collection, found {db.users.count_documents({})}"

    print("\n==================================================================")
    print("SUCCESS: Database cleanup verified! Only Anush's account is retained.")
    print("==================================================================")

if __name__ == '__main__':
    run_cleanup()
