import sys
import os
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.database import get_mongo_db, get_db_connection
from datetime import datetime, timedelta

db = get_mongo_db()
user_id = 5
now = datetime.now()
date_str = now.strftime('%Y-%m-%d')
start_str = (now - timedelta(minutes=45)).strftime('%H:%M')
end_str = (now + timedelta(hours=2)).strftime('%H:%M')
entry_str = (now - timedelta(minutes=40)).strftime('%Y-%m-%d %H:%M:%S')

# Find slot S5
slot = db.parking_slots.find_one({'slot_number': 'S5'}) or db.parking_slots.find_one({'slot_id': 5})
slot_id = slot['slot_id']
slot_num = slot['slot_number']

booking_id = f'BK-{now.year}-9999'
res_id = 9999

# Set slot to occupied
db.parking_slots.update_one({'slot_id': slot_id}, {'$set': {'status': 'occupied', 'current_reservation_id': res_id, 'current_plate': 'KA 19 AB 1234'}})

# Insert booking
b_doc = {
    'booking_id': booking_id,
    'reservation_id': res_id,
    'pass_code': booking_id,
    'user_id': user_id,
    'user_name': 'Anoop',
    'driver_phone': '9876543210',
    'parking_lot_id': slot.get('lot_id', 1),
    'lot_name': 'AJIET Parking',
    'slot_id': slot_id,
    'slot_number': slot_num,
    'floor': 'Ground Floor',
    'slot_type': 'Standard',
    'vehicle_plate': 'KA 19 AB 1234',
    'vehicle_type': 'Car',
    'booking_date': date_str,
    'date': date_str,
    'start_time': start_str,
    'end_time': end_str,
    'actual_entry_time': entry_str,
    'duration': '2.0 Hours',
    'duration_hours': 2.0,
    'hourly_rate': 40.0,
    'total_amount': 80.0,
    'status': 'occupied',
    'created_at': entry_str
}
db.bookings.delete_many({'user_id': user_id, 'status': 'occupied'})
db.reservations.delete_many({'user_id': user_id, 'status': 'occupied'})
db.bookings.insert_one(b_doc)
b_doc['_id'] = None
db.reservations.insert_one({k: v for k, v in b_doc.items() if k != '_id'})

print(f"Active session ready for Anoop on slot: {slot_num}")
