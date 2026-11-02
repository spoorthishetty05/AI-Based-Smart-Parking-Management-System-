"""
Simulation Engine for AI-Based Smart Parking System.
Controls virtual time progression, automated parking state transitions,
and dynamic traffic event triggers (Arrivals, Departures, Rush Hours, Overstays).
Uses pure MongoDB persistence.
"""

import random
from datetime import datetime, timedelta
from database import get_mongo_db, get_next_sequence
from overstay_engine import check_and_update_overstays, get_current_sim_time

SAMPLE_PLATES = [
    'KA01AB1234', 'KA02BK3344', 'KA03CD5678', 'KA04IJ7890', 
    'KA05EF9101', 'KA05MN6789', 'KA51KL2345', 'KA53UF1122',
    'MH02BY8899', 'DL01CK4567', 'TS09EZ3321', 'TN07AB9988'
]

SAMPLE_NAMES = [
    'Spoorthi Shetty', 'Rahul Verma', 'Priya Sharma', 'Amit Kumar', 
    'Ananya Rao', 'Vikram Singh', 'Sneha Patel', 'Arjun Nair', 
    'Divya Hegde', 'Kavita Menon', 'Rohan Gupta'
]

def step_simulation_time(minutes=15):
    """
    Advances simulated system time by given minutes, checks for overstays,
    and updates auto-transitions for reservations in MongoDB.
    """
    db = get_mongo_db()

    current_time = get_current_sim_time()
    new_time = current_time + timedelta(minutes=minutes)
    offset_seconds = int((new_time - datetime.now()).total_seconds())

    db.system_settings.update_one(
        {'setting_key': 'simulated_time'},
        {'$set': {'setting_value': new_time.strftime('%Y-%m-%d %H:%M:%S')}},
        upsert=True
    )
    db.system_settings.update_one(
        {'setting_key': 'sim_offset_seconds'},
        {'$set': {'setting_value': str(offset_seconds)}},
        upsert=True
    )

    # 1. Process overstay violations
    alerts = check_and_update_overstays(new_time)

    # 2. Check for upcoming reservations that should be auto checked-in
    date_str = new_time.strftime('%Y-%m-%d')
    time_str = new_time.strftime('%H:%M')

    to_check_in = list(db.reservations.find({
        'status': 'confirmed',
        'date': date_str,
        'start_time': {'$lte': time_str}
    }))

    for r in to_check_in:
        db.reservations.update_one(
            {'reservation_id': r['reservation_id']},
            {'$set': {
                'status': 'checked_in',
                'actual_entry_time': new_time.strftime('%Y-%m-%d %H:%M:%S')
            }}
        )

        db.parking_slots.update_one(
            {'slot_id': r['slot_id']},
            {'$set': {
                'status': 'occupied',
                'current_plate': r.get('vehicle_plate', '')
            }}
        )

        slot = db.parking_slots.find_one({'slot_id': r['slot_id']}) or {}
        user = db.users.find_one({'user_id': r['user_id']}) or {}
        user_name = user.get('name', 'Driver')

        log_id = get_next_sequence('activity_logs')
        db.activity_logs.insert_one({
            'log_id': log_id,
            'slot_number': slot.get('slot_number', f"Slot-{r['slot_id']}"),
            'user_name': f"{user_name} ({r.get('vehicle_plate')})",
            'action_type': 'Checked In',
            'details': f"Automated check-in. Booking valid until {r.get('end_time')}.",
            'badge_type': 'primary',
            'timestamp': new_time.strftime('%I:%M %p'),
            'created_at': new_time.strftime('%Y-%m-%d %H:%M:%S')
        })

    return {
        'previous_time': current_time.strftime('%Y-%m-%d %H:%M:%S'),
        'current_time': new_time.strftime('%Y-%m-%d %H:%M:%S'),
        'formatted_time': new_time.strftime('%d %b %Y | %I:%M %p'),
        'alerts_triggered': alerts,
        'checked_in_count': len(to_check_in)
    }

def set_simulation_time(target_dt_str):
    """Explicitly sets simulated time to a specific timestamp in MongoDB."""
    db = get_mongo_db()
    dt = datetime.strptime(target_dt_str, '%Y-%m-%d %H:%M:%S')
    offset_seconds = int((dt - datetime.now()).total_seconds())

    db.system_settings.update_one(
        {'setting_key': 'simulated_time'},
        {'$set': {'setting_value': target_dt_str}},
        upsert=True
    )
    db.system_settings.update_one(
        {'setting_key': 'sim_offset_seconds'},
        {'$set': {'setting_value': str(offset_seconds)}},
        upsert=True
    )

    alerts = check_and_update_overstays(dt)
    return {
        'current_time': target_dt_str,
        'formatted_time': dt.strftime('%d %b %Y | %I:%M %p'),
        'alerts_triggered': alerts
    }

def trigger_random_arrival(floor='Ground Floor'):
    """Simulates a new vehicle entering and occupying an available slot."""
    db = get_mongo_db()
    sim_time = get_current_sim_time()

    query = {'status': 'available'}
    if floor and floor != 'All':
        query['floor'] = floor

    available_slots = list(db.parking_slots.find(query))
    if not available_slots:
        return {'status': 'error', 'message': 'No available slots on selected floor!'}

    chosen = random.choice(available_slots)
    plate = random.choice(SAMPLE_PLATES) + f"{random.randint(10, 99)}"
    name = random.choice(SAMPLE_NAMES)

    start_t = sim_time.strftime('%H:%M')
    end_dt = sim_time + timedelta(hours=random.choice([1, 2, 3]))
    end_t = end_dt.strftime('%H:%M')

    res_id = get_next_sequence('reservations')
    db.reservations.insert_one({
        'reservation_id': res_id,
        'user_id': 1,
        'slot_id': chosen['slot_id'],
        'vehicle_plate': plate,
        'date': sim_time.strftime('%Y-%m-%d'),
        'start_time': start_t,
        'end_time': end_t,
        'actual_entry_time': sim_time.strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'checked_in',
        'total_amount': 80.0,
        'created_at': sim_time.strftime('%Y-%m-%d %H:%M:%S')
    })

    db.parking_slots.update_one(
        {'slot_id': chosen['slot_id']},
        {'$set': {
            'status': 'occupied',
            'current_plate': plate,
            'current_reservation_id': res_id
        }}
    )

    log_id = get_next_sequence('activity_logs')
    db.activity_logs.insert_one({
        'log_id': log_id,
        'slot_number': chosen['slot_number'],
        'user_name': f"{name} ({plate})",
        'action_type': 'Vehicle Arrived',
        'details': f"Vehicle occupied slot {chosen['slot_number']}. Reserved until {end_t}.",
        'badge_type': 'primary',
        'timestamp': sim_time.strftime('%I:%M %p'),
        'created_at': sim_time.strftime('%Y-%m-%d %H:%M:%S')
    })

    return {
        'status': 'success',
        'slot_number': chosen['slot_number'],
        'plate': plate,
        'user_name': name,
        'message': f"Slot {chosen['slot_number']} occupied by {plate}"
    }

def trigger_random_departure():
    """Simulates a vehicle vacating an occupied slot."""
    db = get_mongo_db()
    sim_time = get_current_sim_time()

    occupied_slots = list(db.parking_slots.find({'status': {'$in': ['occupied', 'overstayed']}}))
    if not occupied_slots:
        return {'status': 'error', 'message': 'No occupied slots found!'}

    chosen = random.choice(occupied_slots)
    plate = chosen.get('current_plate') or 'KA01ZZ9999'

    cur_res_id = chosen.get('current_reservation_id')
    user_name = 'Visitor'
    if cur_res_id:
        res = db.reservations.find_one({'reservation_id': cur_res_id})
        if res:
            db.reservations.update_one(
                {'reservation_id': cur_res_id},
                {'$set': {
                    'status': 'completed',
                    'actual_exit_time': sim_time.strftime('%Y-%m-%d %H:%M:%S')
                }}
            )
            user = db.users.find_one({'user_id': res.get('user_id')})
            if user:
                user_name = user.get('name', 'Driver')

    db.parking_slots.update_one(
        {'slot_id': chosen['slot_id']},
        {'$set': {
            'status': 'available',
            'current_plate': None,
            'current_reservation_id': None
        }}
    )

    log_id = get_next_sequence('activity_logs')
    db.activity_logs.insert_one({
        'log_id': log_id,
        'slot_number': chosen['slot_number'],
        'user_name': f"{user_name} ({plate})",
        'action_type': 'Vacated',
        'details': f"Vehicle departed. Slot {chosen['slot_number']} is now Available.",
        'badge_type': 'success',
        'timestamp': sim_time.strftime('%I:%M %p'),
        'created_at': sim_time.strftime('%Y-%m-%d %H:%M:%S')
    })

    return {
        'status': 'success',
        'slot_number': chosen['slot_number'],
        'plate': plate,
        'message': f"Slot {chosen['slot_number']} vacated by {plate}"
    }
