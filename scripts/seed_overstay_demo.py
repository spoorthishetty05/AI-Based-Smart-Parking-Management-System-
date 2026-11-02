"""
Seed script to create the 4 Overstay Monitoring demo records matching the system specification:
1. KA19AB1234 | Car  | Slot A-12 | Start: 10:15 AM | Duration: 2h 45m | Status: Overstayed
2. KA20CD5678 | Bike | Slot B-04 | Start: 11:20 AM | Duration: 1h 20m | Status: Expiring Soon
3. KA18EF9012 | Car  | Slot C-07 | Start: 09:45 AM | Duration: 3h 10m | Status: Overstayed
4. KA21GH3456 | Bike | Slot D-03 | Start: 12:30 PM | Duration: 1h 05m | Status: Resolved
"""

import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from datetime import datetime, timedelta
from core.database import get_mongo_db, get_next_sequence
from core.overstay_engine import check_and_update_overstays, get_current_sim_time

db = get_mongo_db()
if db is None:
    print("Database unavailable.")
    exit(1)

sim_now = get_current_sim_time()
date_str = sim_now.strftime('%Y-%m-%d')

# Ensure parking slots A-12, B-04, C-07, D-03 exist in MongoDB
slot_configs = [
    ('A-12', 'Car', 'occupied', 'KA19AB1234'),
    ('B-04', 'Bike', 'occupied', 'KA20CD5678'),
    ('C-07', 'Car', 'occupied', 'KA18EF9012'),
    ('D-03', 'Bike', 'available', None)
]

slots_by_num = {}
for snum, stype, sstatus, splate in slot_configs:
    existing = db.parking_slots.find_one({'slot_number': snum})
    if existing:
        db.parking_slots.update_one(
            {'_id': existing['_id']},
            {'$set': {'status': sstatus, 'slot_type': stype, 'current_plate': splate}}
        )
        slots_by_num[snum] = existing['slot_id']
    else:
        sid = get_next_sequence('parking_slots')
        db.parking_slots.insert_one({
            'slot_id': sid,
            'slot_number': snum,
            'lot_id': 1,
            'lot_name': 'City Center Mall',
            'slot_type': stype,
            'floor': 'Ground Floor',
            'status': sstatus,
            'current_plate': splate
        })
        slots_by_num[snum] = sid

# Clear previous demo items if any
demo_res_ids = [9101, 9102, 9103, 9104]
db.reservations.delete_many({'reservation_id': {'$in': demo_res_ids}})
db.bookings.delete_many({'reservation_id': {'$in': demo_res_ids}})
db.overstay_records.delete_many({'reservation_id': {'$in': demo_res_ids}})

# 1. KA19AB1234 | Car | A-12 | Start 10:15 AM | 2h 45m | Overstayed
res_1 = {
    'reservation_id': 9101,
    'booking_id': 'PK-09101-A12',
    'pass_code': 'PK-09101-A12',
    'user_id': 2,
    'user_name': 'Anush',
    'driver_name': 'Anush',
    'driver_phone': '9876543210',
    'lot_id': 1,
    'parking_lot_id': 1,
    'lot_name': 'City Center Mall',
    'slot_id': slots_by_num['A-12'],
    'slot_number': 'A-12',
    'vehicle_plate': 'KA19AB1234',
    'vehicle_type': 'Car',
    'booking_date': date_str,
    'date': date_str,
    'start_time': '10:15 AM',
    'end_time': (sim_now - timedelta(minutes=45)).strftime('%I:%M %p'),
    'actual_entry_time': (sim_now - timedelta(hours=2, minutes=45)).strftime('%Y-%m-%d %H:%M:%S'),
    'current_duration': '2h 45m',
    'selected_duration': '2 hours',
    'duration': '2 hours',
    'status': 'occupied',
    'notification_status': 'Not Sent',
    'overstay_notification_sent': False
}
db.reservations.insert_one(dict(res_1))
res_1.pop('_id', None)
db.bookings.insert_one(dict(res_1))

# 2. KA20CD5678 | Bike | B-04 | Start 11:20 AM | 1h 20m | Expiring Soon
res_2 = {
    'reservation_id': 9102,
    'booking_id': 'PK-09102-B04',
    'pass_code': 'PK-09102-B04',
    'user_id': 3,
    'user_name': 'Kiran',
    'driver_name': 'Kiran',
    'driver_phone': '9845012345',
    'lot_id': 1,
    'parking_lot_id': 1,
    'lot_name': 'City Center Mall',
    'slot_id': slots_by_num['B-04'],
    'slot_number': 'B-04',
    'vehicle_plate': 'KA20CD5678',
    'vehicle_type': 'Bike',
    'booking_date': date_str,
    'date': date_str,
    'start_time': '11:20 AM',
    'end_time': (sim_now + timedelta(minutes=10)).strftime('%I:%M %p'),
    'actual_entry_time': (sim_now - timedelta(hours=1, minutes=20)).strftime('%Y-%m-%d %H:%M:%S'),
    'current_duration': '1h 20m',
    'selected_duration': '1.5 hours',
    'duration': '1.5 hours',
    'status': 'occupied',
    'notification_status': 'Not Sent',
    'overstay_notification_sent': False
}
db.reservations.insert_one(dict(res_2))
res_2.pop('_id', None)
db.bookings.insert_one(dict(res_2))

# 3. KA18EF9012 | Car | C-07 | Start 09:45 AM | 3h 10m | Overstayed
res_3 = {
    'reservation_id': 9103,
    'booking_id': 'PK-09103-C07',
    'pass_code': 'PK-09103-C07',
    'user_id': 4,
    'user_name': 'Rohan',
    'driver_name': 'Rohan',
    'driver_phone': '9812345678',
    'lot_id': 1,
    'parking_lot_id': 1,
    'lot_name': 'City Center Mall',
    'slot_id': slots_by_num['C-07'],
    'slot_number': 'C-07',
    'vehicle_plate': 'KA18EF9012',
    'vehicle_type': 'Car',
    'booking_date': date_str,
    'date': date_str,
    'start_time': '09:45 AM',
    'end_time': (sim_now - timedelta(hours=1, minutes=10)).strftime('%I:%M %p'),
    'actual_entry_time': (sim_now - timedelta(hours=3, minutes=10)).strftime('%Y-%m-%d %H:%M:%S'),
    'current_duration': '3h 10m',
    'selected_duration': '2 hours',
    'duration': '2 hours',
    'status': 'occupied',
    'notification_status': 'Not Sent',
    'overstay_notification_sent': False
}
db.reservations.insert_one(dict(res_3))
res_3.pop('_id', None)
db.bookings.insert_one(dict(res_3))

# 4. KA21GH3456 | Bike | D-03 | Start 12:30 PM | 1h 05m | Resolved
exit_time_str = (sim_now - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
res_4 = {
    'reservation_id': 9104,
    'booking_id': 'PK-09104-D03',
    'pass_code': 'PK-09104-D03',
    'user_id': 5,
    'user_name': 'Pooja',
    'driver_name': 'Pooja',
    'driver_phone': '9741234567',
    'lot_id': 1,
    'parking_lot_id': 1,
    'lot_name': 'City Center Mall',
    'slot_id': slots_by_num['D-03'],
    'slot_number': 'D-03',
    'vehicle_plate': 'KA21GH3456',
    'vehicle_type': 'Bike',
    'booking_date': date_str,
    'date': date_str,
    'start_time': '12:30 PM',
    'end_time': (sim_now - timedelta(minutes=30)).strftime('%I:%M %p'),
    'actual_entry_time': (sim_now - timedelta(hours=1, minutes=5)).strftime('%Y-%m-%d %H:%M:%S'),
    'actual_exit_time': exit_time_str,
    'current_duration': '1h 05m',
    'selected_duration': '1 hour',
    'duration': '1 hour',
    'status': 'completed',
    'notification_status': 'Sent',
    'overstay_notification_sent': True
}
db.reservations.insert_one(dict(res_4))
res_4.pop('_id', None)
db.bookings.insert_one(dict(res_4))

# Also create resolved overstay record for #4
db.overstay_records.insert_one({
    'overstay_id': 9104,
    'reservation_id': 9104,
    'booking_id': 'PK-09104-D03',
    'user_id': 5,
    'user_name': 'Pooja',
    'driver_name': 'Pooja',
    'vehicle_plate': 'KA21GH3456',
    'vehicle_type': 'Bike',
    'lot_name': 'City Center Mall',
    'slot_number': 'D-03',
    'start_time': '12:30 PM',
    'parking_start_time': '12:30 PM',
    'current_duration': '1h 05m',
    'selected_duration': '1h 05m',
    'actual_exit_time': exit_time_str,
    'status': 'resolved',
    'payment_status': 'Paid',
    'notification_status': 'Sent',
    'final_penalty': 30.0,
    'created_at': date_str,
    'resolved_at': exit_time_str
})

# Run overstay check to calculate and register active overstay records for 9101 and 9103
check_and_update_overstays(sim_now)

print("Successfully seeded 4 overstay monitoring demonstration records with explicit durations.")
