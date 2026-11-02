import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from datetime import datetime
from core.database import get_mongo_db
from core.overstay_engine import check_and_update_overstays, get_overstay_management_data

def reconcile():
    db = get_mongo_db()
    now_dt = datetime.now()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')

    # 1. Reset simulation settings to real host PC time
    db.system_settings.update_one(
        {'setting_key': 'sim_offset_seconds'},
        {'$set': {'setting_value': '0'}},
        upsert=True
    )
    db.system_settings.update_one(
        {'setting_key': 'simulated_time'},
        {'$set': {'setting_value': now_str}},
        upsert=True
    )

    # 2. Re-evaluate all reservations against current PC time
    check_and_update_overstays(now_dt)

    # 3. Fetch overstay management data
    data = get_overstay_management_data()
    print("RECONCILIATION COMPLETE")
    print(f"Current Host PC Time: {now_str}")
    print(f"Summary: {data['summary']}")
    print(f"Overstay Violation Records count: {len(data['overstays'])}")

    res16 = db.reservations.find_one({'reservation_id': 16})
    if res16:
        print(f"Res 16 status: {res16.get('status')}, overstay_status: {res16.get('overstay_status')}, penalty: {res16.get('overstay_penalty')}")

    slot_s1 = db.parking_slots.find_one({'slot_number': 'S1'})
    if slot_s1:
        print(f"Slot S1 status: {slot_s1.get('status')}")

    active_overstays = list(db.overstay_records.find({'status': 'active'}))
    print(f"Active Overstay Records in DB: {len(active_overstays)}")

if __name__ == '__main__':
    reconcile()

