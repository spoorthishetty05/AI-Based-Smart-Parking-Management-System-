"""
Database management module for AI-Based Smart Parking System.
Uses MongoDB as the sole, primary database engine.
No SQLite or SQL database used.
"""

import os
import re
import json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import pymongo
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

DEFAULT_MONGO_URI = os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017')
DATABASE_NAME = 'smart_parking'
DB_PATH = None  # SQLite completely removed

_mongo_client_cache = None
_mongo_uri_cache = None

def get_mongo_client(uri=None):
    """Returns a shared, verified MongoClient connected to local MongoDB Community Server."""
    global _mongo_client_cache, _mongo_uri_cache
    target_uri = uri or DEFAULT_MONGO_URI

    # Strictly reject remote cloud URLs
    if 'mongodb+srv' in target_uri or 'mongodb.net' in target_uri:
        raise ValueError("Remote cloud database connections (MongoDB Atlas) are strictly disabled. Local MongoDB Community Server only.")

    if _mongo_client_cache is not None and _mongo_uri_cache == target_uri:
        try:
            _mongo_client_cache.admin.command('ping')
            return _mongo_client_cache
        except Exception:
            _mongo_client_cache = None

    try:
        client = MongoClient(target_uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)
        client.admin.command('ping')
        _mongo_client_cache = client
        _mongo_uri_cache = target_uri
        return client
    except Exception as e:
        _mongo_client_cache = None
        raise ConnectionFailure(
            f"Local MongoDB Community Server is unavailable at '{target_uri}'. "
            "Please ensure MongoDB service is running locally on port 27017. "
            "Cloud databases and local file fallbacks are strictly disabled."
        ) from e

def get_mongo_db(uri=None):
    """Returns the smart_parking MongoDB database instance."""
    client = get_mongo_client(uri)
    return client[DATABASE_NAME]

def get_db():
    """Convenience alias returning the primary MongoDB database."""
    return get_mongo_db()

_SEQUENCE_ID_FIELD_MAP = {
    'users': 'user_id',
    'vehicles': 'vehicle_id',
    'parking_lots': 'lot_id',
    'parking_slots': 'slot_id',
    'reservations': 'reservation_id',
    'overstay_records': 'overstay_id',
    'notifications': 'notification_id',
    'slot_exchange_requests': 'request_id',
    'slot_exchange_listings': 'listing_id',
    'slot_exchange_history': 'history_id',
}

def get_next_sequence(sequence_name):
    """Atomically increments and returns the next unused sequential integer ID for an entity."""
    db = get_mongo_db()
    id_field = _SEQUENCE_ID_FIELD_MAP.get(sequence_name)
    while True:
        ret = db.counters.find_one_and_update(
            {'_id': sequence_name},
            {'$inc': {'seq': 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        seq = int(ret['seq'])
        if not id_field:
            return seq
        if not db[sequence_name].find_one({id_field: seq}, {'_id': 1}):
            return seq

def clean_doc(doc):
    """Converts a MongoDB document to a JSON-serializable dictionary without raw ObjectId."""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [clean_doc(d) for d in doc]
    if not isinstance(doc, dict):
        if type(doc).__name__ == 'ObjectId':
            return str(doc)
        return doc
    d = dict(doc)
    for k, v in list(d.items()):
        if isinstance(v, list):
            d[k] = [clean_doc(x) for x in v]
        elif isinstance(v, dict):
            d[k] = clean_doc(v)
        elif type(v).__name__ == 'ObjectId':
            d[k] = str(v)
    if '_id' in d and type(d['_id']).__name__ == 'ObjectId':
        d['_id'] = str(d['_id'])
    return d

PERMANENT_ADMINS = [
    {
        'name': 'System Administrator',
        'email': 'admin@smartparking.ai',
        'password': 'admin',
        'phone': '+91 9876500001',
        'role': 'admin'
    },
    {
        'name': 'Spoorthi Shetty',
        'email': 'spoorthi@smartparking.ai',
        'password': 'admin',
        'phone': '+91 9876543210',
        'role': 'admin'
    }
]

STANDARD_DRIVERS = [
    {
        'name': 'test1',
        'email': 'test1@smartparking.ai',
        'password': 'test1',
        'phone': '9876543210',
        'role': 'user',
        'vehicle_plate': 'KA01TE1111',
        'vehicle_type': 'Car'
    },
    {
        'name': 'Krithika Shetty',
        'email': 'krithikasanthoshshetty@gmail.com',
        'password': 'password123',
        'phone': '+91 9876543211',
        'role': 'user',
        'vehicle_plate': 'KA10A4614',
        'vehicle_type': 'Car'
    },
    {
        'name': 'Standard Driver',
        'email': 'driver@smartparking.ai',
        'password': 'driver123',
        'phone': '+91 9876543212',
        'role': 'user',
        'vehicle_plate': 'KA01AB1234',
        'vehicle_type': 'Car'
    }
]

SECURITY_GUARDS = [
    {
        'name': 'Chief Security Officer',
        'email': 'security@smartparking.ai',
        'password': 'security123',
        'phone': '+91 9876500099',
        'role': 'security',
        'gate': 'Gate 1 (North Entry)',
        'assigned_lot': 'Institutions',
        'lot_id': 1
    },
    {
        'name': 'Guard Ramesh Kumar',
        'email': 'guard@smartparking.ai',
        'password': 'guard123',
        'phone': '+91 9876500098',
        'role': 'security',
        'gate': 'Gate 2 (Main Mall Entrance)',
        'assigned_lot': 'Mall',
        'lot_id': 2
    }
]

# ======================================================================
# COMPLETE DATABASE RESET & INITIALIZATION (MONGODB ONLY)
# ======================================================================

def clear_and_init_mongodb(force_reseed=True, preserve_users=True):
    """
    Initializes collections in MongoDB 'smart_parking' database.
    By default (preserve_users=True), preserves all existing registered users
    and permanent admins, preventing any loss of user accounts across server restarts.
    """
    db = get_mongo_db()
    if db is None:
        return False

    existing_user_count = 0
    try:
        existing_user_count = db.users.count_documents({})
    except Exception:
        existing_user_count = 0

    # 1. Drop collections (preserve users and vehicles if preserve_users=True and users exist)
    if preserve_users and existing_user_count > 0:
        collections_to_wipe = [
            'parking_lots', 'parking_slots',
            'reservations', 'bookings', 'overstay_records', 'occupancy_records',
            'predictions', 'activity_logs', 'system_settings',
            'simulation_state', 'login_logs', 'slot_exchange_listings',
            'slot_exchange_requests', 'slot_exchange_history', 'notifications'
        ]
    else:
        collections_to_wipe = [
            'users', 'vehicles', 'parking_lots', 'parking_slots',
            'reservations', 'bookings', 'overstay_records', 'occupancy_records',
            'predictions', 'activity_logs', 'system_settings',
            'simulation_state', 'login_logs', 'slot_exchange_listings',
            'slot_exchange_requests', 'slot_exchange_history', 'notifications',
            'counters'
        ]

    for coll in collections_to_wipe:
        try:
            db[coll].drop()
        except Exception:
            pass

    # 2. Delete legacy SQLite database file if it exists on disk
    legacy_sqlite = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smart_parking.db')
    if os.path.exists(legacy_sqlite):
        try:
            os.remove(legacy_sqlite)
            print("[MongoDB] Removed legacy SQLite file smart_parking.db.")
        except Exception as e:
            print(f"[MongoDB] Could not remove smart_parking.db: {e}")

    # Delete decoupled JSON store if it exists
    legacy_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'mongo_collections.json')
    if os.path.exists(legacy_json):
        try:
            os.remove(legacy_json)
        except Exception:
            pass

    # 3. Initialize sequence counters
    counters = [
        {'_id': 'parking_lots', 'seq': 4},
        {'_id': 'parking_slots', 'seq': 210},
        {'_id': 'reservations', 'seq': 0},
        {'_id': 'bookings', 'seq': 0},
        {'_id': 'overstay_records', 'seq': 0},
        {'_id': 'slot_exchange_listings', 'seq': 0},
        {'_id': 'slot_exchange_requests', 'seq': 0},
        {'_id': 'slot_exchange_history', 'seq': 0},
        {'_id': 'notifications', 'seq': 0},
        {'_id': 'activity_logs', 'seq': 1},
        {'_id': 'login_logs', 'seq': 0}
    ]
    for c in counters:
        try:
            db.counters.update_one({'_id': c['_id']}, {'$set': c}, upsert=True)
        except Exception:
            pass

    # Ensure counters sequence for users and vehicles
    try:
        max_user = db.users.find_one(sort=[('user_id', DESCENDING)])
        max_uid = int(max_user['user_id']) if (max_user and 'user_id' in max_user) else 2
        db.counters.update_one({'_id': 'users'}, {'$set': {'seq': max(max_uid, 2)}}, upsert=True)
        max_veh = db.vehicles.find_one(sort=[('vehicle_id', DESCENDING)])
        max_vid = int(max_veh['vehicle_id']) if (max_veh and 'vehicle_id' in max_veh) else 0
        db.counters.update_one({'_id': 'vehicles'}, {'$set': {'seq': max_vid}}, upsert=True)
    except Exception:
        pass

    # 4. Seed System Settings
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    settings_data = [
        {'setting_key': 'simulated_time', 'setting_value': now_str},
        {'setting_key': 'sim_offset_seconds', 'setting_value': '0'},
        {'setting_key': 'sim_speed', 'setting_value': '1'},
        {'setting_key': 'auto_simulation', 'setting_value': '0'},
        {'setting_key': 'grace_period_mins', 'setting_value': '10'},
        {'setting_key': 'hourly_rate', 'setting_value': '40.0'},
        {'setting_key': 'penalty_rate', 'setting_value': '60.0'},
        {'setting_key': 'penalty_rate_car', 'setting_value': '60.0'},
        {'setting_key': 'penalty_rate_bike', 'setting_value': '30.0'}
    ]
    db.system_settings.insert_many(settings_data)

    # 5. Seed Permanent Administrators Only (admin@smartparking.ai, spoorthi@smartparking.ai)
    # Strictly NO demo users or sample records automatically created
    ensure_permanent_admin()

    # 7. Seed 4 Parking Lots (Total 210 slots)
    lots_data = [
        {
            'lot_id': 1,
            'name': 'Institutions',
            'lot_name': 'Institutions',
            'location': 'Campus Block, University & Medical Center, Bangalore',
            'total_floors': 2,
            'total_slots': 43,
            'hourly_rate': 30.0,
            'overstay_penalty_rate': 80.0,
            'operating_hours': '06:00 AM - 11:00 PM'
        },
        {
            'lot_id': 2,
            'name': 'Mall',
            'lot_name': 'Mall',
            'location': 'Phoenix Grand Mall, Commercial Blvd, Bangalore',
            'total_floors': 2,
            'total_slots': 37,
            'hourly_rate': 50.0,
            'overstay_penalty_rate': 120.0,
            'operating_hours': '09:00 AM - 11:30 PM'
        },
        {
            'lot_id': 3,
            'name': 'Public places',
            'lot_name': 'Public places',
            'location': 'City Metro Interchange & Public Plaza, Bangalore',
            'total_floors': 2,
            'total_slots': 30,
            'hourly_rate': 20.0,
            'overstay_penalty_rate': 60.0,
            'operating_hours': '24/7 (Open Daily)'
        },
        {
            'lot_id': 4,
            'name': 'City Parking',
            'lot_name': 'City Parking',
            'location': 'Hampankatta, Mangaluru',
            'total_floors': 2,
            'total_slots': 100,
            'hourly_rate': 40.0,
            'overstay_penalty_rate': 100.0,
            'operating_hours': '24/7 (Open Daily)'
        }
    ]
    db.parking_lots.insert_many(lots_data)

    # 8. Seed 210 Slots (100% available, zero bookings)
    slots_to_insert = []
    slot_id_counter = 1

    # Lot 1 (Institutions): 43 slots (S1-S11, R1-R32)
    ground_slot_types = {
        'S1': ('Standard', 15, 10), 'S2': ('Standard', 18, 12),
        'S3': ('Standard', 21, 14), 'S4': ('Standard', 24, 16),
        'S5': ('EV', 27, 18), 'S6': ('EV', 30, 20),
        'S7': ('Standard', 33, 22), 'S8': ('Standard', 36, 24),
        'S9': ('Standard', 39, 26), 'S10': ('Standard', 42, 28),
        'S11': ('Compact', 45, 30),
        'R1': ('Standard', 12, 10), 'R2': ('Standard', 15, 12),
        'R3': ('Standard', 18, 14), 'R4': ('Standard', 21, 16),
        'R5': ('Standard', 24, 18), 'R6': ('Standard', 27, 20),
        'R7': ('Standard', 30, 22), 'R8': ('Standard', 33, 24),
        'R9': ('Standard', 36, 26), 'R10': ('Standard', 39, 28),
        'R11': ('Standard', 42, 30),
        'R22': ('Standard', 12, 10), 'R23': ('Standard', 15, 12),
        'R24': ('Standard', 18, 14), 'R25': ('Standard', 21, 16),
        'R26': ('Standard', 24, 18), 'R27': ('Standard', 27, 20),
        'R28': ('Standard', 30, 22), 'R29': ('Standard', 33, 24),
        'R30': ('Standard', 36, 26), 'R31': ('Standard', 39, 28),
        'R32': ('Standard', 42, 30)
    }
    for r in range(12, 22):
        st = 'VIP' if r % 5 == 0 else ('Disabled' if r % 4 == 0 else 'Standard')
        ground_slot_types[f'R{r}'] = (st, 20 + r, 15 + r)

    for slot_num, (stype, dist_entry, dist_elev) in ground_slot_types.items():
        slots_to_insert.append({
            'slot_id': slot_id_counter,
            'lot_id': 1,
            'slot_number': slot_num,
            'floor': 'Ground Floor',
            'zone': 'Long Term Parking',
            'slot_type': stype,
            'distance_to_entry_m': dist_entry,
            'distance_to_elevator_m': dist_elev,
            'status': 'available',
            'current_reservation_id': None,
            'current_plate': None
        })
        slot_id_counter += 1

    # Lot 2 (Mall): 37 slots (U01 to U37)
    for idx in range(1, 38):
        zone = 'Short Term Parking' if idx <= 20 else 'Mall Express / VIP'
        stype = 'EV' if idx % 5 == 0 else ('Compact' if idx % 3 == 0 else 'Standard')
        slots_to_insert.append({
            'slot_id': slot_id_counter,
            'lot_id': 2,
            'slot_number': f'U{idx:02d}',
            'floor': 'Upper Floor',
            'zone': zone,
            'slot_type': stype,
            'distance_to_entry_m': 20 + (idx % 12) * 3,
            'distance_to_elevator_m': 10 + (idx % 8) * 2,
            'status': 'available',
            'current_reservation_id': None,
            'current_plate': None
        })
        slot_id_counter += 1

    # Lot 3 (Public places): 30 slots (U38 to U67)
    for idx in range(38, 68):
        zone = 'Public Transit & EV Hub' if idx <= 50 else 'General Public Bay'
        stype = 'EV' if idx <= 50 else ('Disabled' if idx % 4 == 0 else 'Standard')
        slots_to_insert.append({
            'slot_id': slot_id_counter,
            'lot_id': 3,
            'slot_number': f'U{idx:02d}',
            'floor': 'Upper Floor',
            'zone': zone,
            'slot_type': stype,
            'distance_to_entry_m': 25 + (idx % 15) * 3,
            'distance_to_elevator_m': 15 + (idx % 10) * 2,
            'status': 'available',
            'current_reservation_id': None,
            'current_plate': None
        })
        slot_id_counter += 1

    # Lot 4 (City Parking): 100 slots (A1-A12, B1-B12, C1-C13, D1-D13, E1-E12, F1-F12, G1-G13, H1-H13)
    city_slots = []
    # Row A: A1-A12
    city_slots.append(('A1', 'Ground Floor', 'City Central Wing', 'Regular'))
    city_slots.append(('A2', 'Ground Floor', 'City Central Wing', 'VIP'))
    city_slots.append(('A3', 'Ground Floor', 'City Central Wing', 'Accessible'))
    city_slots.append(('A4', 'Ground Floor', 'City Central Wing', 'EV'))
    for i in range(5, 13):
        st = 'EV' if i % 4 == 0 else ('VIP' if i % 3 == 0 else 'Regular')
        city_slots.append((f'A{i}', 'Ground Floor', 'City Central Wing', st))

    # Row B: B1-B12
    city_slots.append(('B1', 'Ground Floor', 'City Central Wing', 'Regular'))
    city_slots.append(('B2', 'Ground Floor', 'City Central Wing', 'Regular'))
    city_slots.append(('B3', 'Ground Floor', 'City Central Wing', 'Accessible'))
    city_slots.append(('B4', 'Ground Floor', 'City Central Wing', 'VIP'))
    for i in range(5, 13):
        st = 'Accessible' if i % 4 == 0 else ('VIP' if i % 3 == 0 else 'Regular')
        city_slots.append((f'B{i}', 'Ground Floor', 'City Central Wing', st))

    # Row C: C1-C13
    city_slots.append(('C1', 'Ground Floor', 'City Central Wing', 'Regular'))
    city_slots.append(('C2', 'Ground Floor', 'City Central Wing', 'EV'))
    city_slots.append(('C3', 'Ground Floor', 'City Central Wing', 'Regular'))
    city_slots.append(('C4', 'Ground Floor', 'City Central Wing', 'Accessible'))
    for i in range(5, 14):
        st = 'EV' if i % 3 == 0 else 'Regular'
        city_slots.append((f'C{i}', 'Ground Floor', 'City Central Wing', st))

    # Row D: D1-D13
    for i in range(1, 14):
        st = 'VIP' if i in (1, 7) else ('Accessible' if i in (2, 8) else 'Regular')
        city_slots.append((f'D{i}', 'Ground Floor', 'City Central Wing', st))

    # Upper Floor: E1-E12, F1-F12, G1-G13, H1-H13
    for i in range(1, 13):
        city_slots.append((f'E{i}', 'Upper Floor', 'Elevated Parking Deck', 'Regular'))
        city_slots.append((f'F{i}', 'Upper Floor', 'Elevated Parking Deck', 'EV' if i % 2 == 0 else 'Regular'))

    for i in range(1, 14):
        city_slots.append((f'G{i}', 'Upper Floor', 'Elevated Parking Deck', 'Accessible' if i % 3 == 0 else 'Regular'))
        city_slots.append((f'H{i}', 'Upper Floor', 'Elevated Parking Deck', 'VIP' if i % 4 == 0 else 'Regular'))

    for slot_num, floor, zone, stype in city_slots:
        status = 'available'
        curr_plate = None

        slots_to_insert.append({
            'slot_id': slot_id_counter,
            'lot_id': 4,
            'slot_number': slot_num,
            'floor': floor,
            'zone': zone,
            'slot_type': stype,
            'distance_to_entry_m': 15,
            'distance_to_elevator_m': 20,
            'status': status,
            'current_reservation_id': None,
            'current_plate': curr_plate
        })
        slot_id_counter += 1

    db.parking_slots.insert_many(slots_to_insert)

    # 9. Seed Initial Clean Activity Log
    db.activity_logs.insert_one({
        'log_id': 1,
        'slot_number': 'All',
        'user_name': 'System',
        'action_type': 'Initialized',
        'details': 'System initialized fresh in MongoDB. All 210 parking slots available across 4 parking facilities.',
        'badge_type': 'success',
        'timestamp': '09:00 AM',
        'created_at': now_str
    })

    # 10. Create Unique & Performance Indexes in MongoDB
    db.users.create_index('email', unique=True)
    db.users.create_index('user_id', unique=True)
    db.parking_lots.create_index('lot_id', unique=True)
    db.parking_slots.create_index('slot_id', unique=True)
    db.parking_slots.create_index('slot_number', unique=True)
    db.parking_slots.create_index('lot_id')
    db.reservations.create_index('reservation_id', unique=True)
    db.reservations.create_index('user_id')
    db.reservations.create_index('slot_id')
    db.bookings.create_index('booking_id', unique=True)
    db.bookings.create_index('user_id')
    db.bookings.create_index('slot_id')
    db.bookings.create_index('booking_date')
    db.vehicles.create_index('vehicle_id', unique=True)
    db.vehicles.create_index('user_id')
    db.slot_exchange_listings.create_index('listing_id', unique=True)
    db.slot_exchange_listings.create_index('reservation_id')
    db.slot_exchange_listings.create_index('user_id')
    db.slot_exchange_requests.create_index('request_id', unique=True)
    db.slot_exchange_requests.create_index('listing_id')
    db.notifications.create_index('notification_id', unique=True)
    db.notifications.create_index('user_id')
    db.system_settings.create_index('setting_key', unique=True)

    try:
        import parking_places_config
        parking_places_config.sync_places_to_mongodb(db)
    except Exception as e:
        print(f"[MongoDB] Places sync warning: {e}")

    print(f"[MongoDB] Database successfully cleared and initialized with {len(slots_to_insert)} slots.")
    return True

def resolve_duplicate_users():
    """
    Checks for any duplicate accounts with the same normalized email address in MongoDB.
    Safely resolves duplicates by keeping the primary/most recently updated document
    and removing redundant duplicates, ensuring the unique index is maintained cleanly.
    """
    db = get_mongo_db()
    if db is None:
        return
    try:
        users = list(db.users.find({}))
        seen_emails = {}
        for u in users:
            curr_email = u.get('email') or u.get('Email') or u.get('user_email')
            if not curr_email:
                continue
            norm = str(curr_email).strip().lower()
            if norm not in seen_emails:
                seen_emails[norm] = u
            else:
                existing = seen_emails[norm]
                if u.get('password_hash') and not existing.get('password_hash'):
                    db.users.delete_one({'_id': existing['_id']})
                    seen_emails[norm] = u
                else:
                    db.users.delete_one({'_id': u['_id']})

        # Ensure unique index on normalized email
        db.users.create_index('email', unique=True)
        db.users.create_index('user_id', unique=True)
    except Exception as e:
        print(f"[MongoDB Notice] resolve_duplicate_users: {e}")

def init_db(force_reseed=False):
    """Compatibility initializer targeting MongoDB. Guarantees registered users are never wiped."""
    db = get_mongo_db()
    if db is None:
        return False
    if force_reseed:
        return clear_and_init_mongodb(force_reseed=True, preserve_users=True)
    if db.parking_slots.count_documents({}) == 0:
        return clear_and_init_mongodb(force_reseed=False, preserve_users=True)
    try:
        resolve_duplicate_users()
        db.bookings.create_index('booking_id', unique=True)
        db.bookings.create_index('user_id')
        db.bookings.create_index('slot_id')
        db.users.create_index('email', unique=True)
        db.users.create_index('user_id', unique=True)
    except Exception:
        pass
    normalize_existing_users()
    return True

def normalize_existing_users():
    """Ensures all existing MongoDB user documents have normalized lowercase email, valid user_id, and compatible password_hash."""
    db = get_mongo_db()
    if db is None:
        return
    try:
        users = list(db.users.find({}))
        for u in users:
            updates = {}
            # Standardize email
            curr_email = u.get('email') or u.get('Email') or u.get('user_email')
            if curr_email:
                norm = str(curr_email).strip().lower()
                if u.get('email') != norm:
                    updates['email'] = norm

            # Standardize password_hash if legacy password field was used
            if not u.get('password_hash') and u.get('password'):
                raw_pwd = u.get('password')
                if str(raw_pwd).startswith(('scrypt:', 'pbkdf2:')):
                    updates['password_hash'] = raw_pwd
                else:
                    updates['password_hash'] = generate_password_hash(raw_pwd)

            # Ensure valid sequential user_id
            if u.get('user_id') is None or u.get('user_id') == 0:
                updates['user_id'] = get_next_sequence('users')

            if updates:
                db.users.update_one({'_id': u['_id']}, {'$set': updates})
    except Exception as e:
        print(f"[Mongo Warning] normalize_existing_users notice: {e}")

def ensure_permanent_admin(conn=None):
    """Ensures permanent admin and standard test driver accounts exist in MongoDB with verified role, hash, and user_id."""
    db = get_mongo_db()
    for idx, admin in enumerate(PERMANENT_ADMINS, start=1):
        existing = db.users.find_one({'email': admin['email'].lower()})
        hashed = generate_password_hash(admin['password'])
        if not existing:
            db.users.insert_one({
                'user_id': idx,
                'name': admin['name'],
                'email': admin['email'].lower(),
                'password_hash': hashed,
                'phone': admin['phone'],
                'role': 'admin',
                'is_active': 1,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            db.users.update_one(
                {'email': admin['email'].lower()},
                {'$set': {'user_id': idx, 'role': 'admin', 'is_active': 1, 'password_hash': hashed}}
            )

    # Also seed standard drivers for instant user portal access
    for idx, driver in enumerate(STANDARD_DRIVERS, start=3):
        existing = db.users.find_one({'email': driver['email'].lower()})
        hashed = generate_password_hash(driver['password'])
        if not existing:
            db.users.insert_one({
                'user_id': idx,
                'name': driver['name'],
                'email': driver['email'].lower(),
                'password_hash': hashed,
                'phone': driver['phone'],
                'role': 'user',
                'is_active': 1,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            if driver.get('vehicle_plate'):
                db.vehicles.update_one(
                    {'user_id': idx, 'plate_number': driver['vehicle_plate']},
                    {'$set': {
                        'vehicle_id': idx,
                        'user_id': idx,
                        'plate_number': driver['vehicle_plate'],
                        'vehicle_type': driver.get('vehicle_type', 'Car'),
                        'vehicle_model': 'Standard Vehicle',
                        'color': 'Silver',
                        'is_primary': 1,
                        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }},
                    upsert=True
                )
        else:
            db.users.update_one(
                {'email': driver['email'].lower()},
                {'$set': {'role': 'user', 'is_active': 1, 'password_hash': hashed}}
            )

    # Also seed security guard officers for instant gate operator portal access
    for idx, guard in enumerate(SECURITY_GUARDS, start=6):
        existing = db.users.find_one({'email': guard['email'].lower()})
        hashed = generate_password_hash(guard['password'])
        if not existing:
            db.users.insert_one({
                'user_id': idx,
                'name': guard['name'],
                'email': guard['email'].lower(),
                'password_hash': hashed,
                'phone': guard['phone'],
                'role': 'security',
                'gate': guard.get('gate', 'Gate 1 (North Entry)'),
                'assigned_lot': guard.get('assigned_lot', 'Institutions'),
                'lot_id': guard.get('lot_id', 1),
                'is_active': 1,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            db.users.update_one(
                {'email': guard['email'].lower()},
                {'$set': {
                    'role': 'security',
                    'is_active': 1,
                    'password_hash': hashed,
                    'gate': guard.get('gate', 'Gate 1 (North Entry)'),
                    'assigned_lot': guard.get('assigned_lot', 'Institutions'),
                    'lot_id': guard.get('lot_id', 1)
                }}
            )

    # Ensure counters sequence for users is at least 7 so next registered user gets 8
    db.counters.update_one({'_id': 'users'}, {'$max': {'seq': 7}}, upsert=True)

def ensure_notifications_table(conn=None):
    """No-op for MongoDB (collection dynamically created)."""
    pass

def ensure_users_columns(conn=None):
    """No-op for MongoDB schema-free document model."""
    pass

def create_notification(user_id, notif_type, title, message, related_id=None, conn=None, send_email_alert=True):
    """Creates a user notification document in MongoDB and dispatches an email alert to the registered user."""
    db = get_mongo_db()
    nid = get_next_sequence('notifications')
    doc = {
        'notification_id': nid,
        'user_id': int(user_id) if str(user_id).isdigit() else user_id,
        'type': str(notif_type),
        'title': str(title),
        'message': str(message),
        'related_id': related_id,
        'is_read': 0,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    db.notifications.insert_one(doc)

    # Automatically dispatch notification as email to the registered user
    if send_email_alert:
        try:
            uid_query = {'user_id': int(user_id)} if str(user_id).isdigit() else {'user_id': user_id}
            user = db.users.find_one(uid_query)
            recipient_email = (user.get('email') if user else '').strip()
            user_name = user.get('name', 'Valued Driver') if user else 'Valued Driver'

            if recipient_email and '@' in recipient_email:
                from core.email_service import send_email
                badge_map = {
                    'booking_confirmed': 'Booking Confirmed',
                    'booking_cancelled': 'Booking Cancelled',
                    'overstay_alert': 'Overstay Violation',
                    'grace_warning': 'Grace Period Warning',
                    'booking_ended': 'Booking Notice',
                    'penalty_applied': 'Penalty Notice',
                    'wallet_topup': 'Wallet Update',
                    'profile_updated': 'Profile Security',
                    'password_changed': 'Security Notice',
                    'vehicle_registered': 'Vehicle Update',
                    'exchange_offered': 'Slot Exchange',
                    'exchange_requested': 'Slot Exchange Request',
                    'exchange_accepted': 'Slot Exchange Approved',
                    'exchange_rejected': 'Slot Exchange Declined',
                    'exchange_counter': 'Slot Exchange Counter-Offer',
                    'payment_success': 'Payment Receipt'
                }
                badge_text = badge_map.get(str(notif_type), 'Smart Parking Alert')
                formatted_message = str(message).replace('\n', '<br>')

                send_email(
                    to=recipient_email,
                    subject=f"Smart Parking AI - {title}",
                    template="emails/general_notification.html",
                    context={
                        "headline": title,
                        "badge_text": badge_text,
                        "user_name": user_name,
                        "message": formatted_message,
                        "action_url": "http://127.0.0.1:5000/user/panel",
                        "action_text": "View In-App Dashboard",
                        "current_year": datetime.now().year,
                        "support_email": "support@smartparking.ai"
                    },
                    sync=False
                )
        except Exception as e:
            import logging
            logging.getLogger("SmartParking.Notification").warning(f"Could not dispatch email for notification {nid}: {e}")

    return nid

# ======================================================================
# MONGODB-BACKED COMPATIBILITY CONNECTION & CURSOR LAYER
# ======================================================================
# Allows legacy test suites and external callers that invoke
# conn = get_db_connection() and cursor.execute(...) to query
# MongoDB directly without requiring SQLite or SQL database files.

class MongoRow(dict):
    """Dictionary-like and tuple-like row object matching sqlite3.Row semantics."""
    def __init__(self, data):
        cleaned = clean_doc(data) or {}
        super().__init__(cleaned)
        self._keys = list(cleaned.keys())
        self._values = list(cleaned.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key] if key < len(self._values) else None
        return self.get(key, None)

    def keys(self):
        return self._keys

    def values(self):
        return self._values

    def items(self):
        return super().items()

class MongoCursor:
    def __init__(self, db):
        self.db = db
        self._results = []
        self._index = 0
        self.lastrowid = None
        self.rowcount = 0

    def execute(self, sql, params=()):
        sql_clean = re.sub(r'\s+', ' ', sql.strip()).strip()
        params = list(params) if isinstance(params, (list, tuple)) else [params]
        sql_upper = sql_clean.upper()

        self._results = []
        self._index = 0
        self.rowcount = 0

        # PRAGMA or DDL statements
        if sql_upper.startswith('PRAGMA') or sql_upper.startswith('CREATE TABLE') or sql_upper.startswith('ALTER TABLE'):
            return self

        # SELECT SUM(...)
        if 'SELECT SUM(' in sql_upper:
            sum_m = re.search(r'SUM\(([a-zA-Z0-9_.]+)\)\s*(?:AS\s+([a-zA-Z0-9_]+))?', sql, re.IGNORECASE)
            if sum_m:
                sum_field = sum_m.group(1).split('.')[-1]
                alias = sum_m.group(2) if sum_m.group(2) else sum_field
                coll_m = re.search(r'FROM\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
                coll_name = coll_m.group(1) if coll_m else 'reservations'
                q = {}
                if 'WHERE' in sql_upper:
                    where_part = re.split(r'\bWHERE\b', sql, flags=re.IGNORECASE)[1].strip()
                    q = self._parse_simple_where(where_part, params)
                docs = list(self.db[coll_name].find(q))
                total = sum(float(d.get(sum_field) or 0) for d in docs)
                self._results = [MongoRow({alias: total, 'sum': total})]
                self.rowcount = 1
                return self

        # GROUP BY statements
        if 'GROUP BY' in sql_upper:
            return self._handle_group_by(sql_clean, params)

        # SELECT COUNT(*) as cnt FROM ...
        if 'SELECT COUNT(' in sql_upper:
            coll_m = re.search(r'FROM\s+([a-zA-Z0-9_]+)', sql_clean, re.IGNORECASE)
            coll_name = coll_m.group(1) if coll_m else 'parking_slots'
            q = {}
            if 'WHERE' in sql_upper:
                where_part = re.split(r'\bWHERE\b', sql_clean, flags=re.IGNORECASE)[1].strip()
                q = self._parse_simple_where(where_part, params)
            cnt = self.db[coll_name].count_documents(q)
            alias_m = re.search(r'\bAS\s+([a-zA-Z0-9_]+)\s+FROM\b', sql_clean, re.IGNORECASE)
            if not alias_m:
                alias_m = re.search(r'COUNT\([^)]*\)\s+(?:AS\s+)?([a-zA-Z0-9_]+)', sql_clean, re.IGNORECASE)
            alias = alias_m.group(1) if alias_m else 'cnt'
            res_data = {'cnt': cnt, 'count': cnt, alias: cnt, 'total_exchanged': cnt}
            self._results = [MongoRow(res_data)]
            self.rowcount = 1
            return self

        # SELECT
        if sql_upper.startswith('SELECT'):
            self._handle_select(sql_clean, params)
            return self

        # INSERT
        if sql_upper.startswith('INSERT'):
            self._handle_insert(sql_clean, params)
            return self

        # UPDATE
        if sql_upper.startswith('UPDATE'):
            self._handle_update(sql_clean, params)
            return self

        # DELETE
        if sql_upper.startswith('DELETE'):
            self._handle_delete(sql_clean, params)
            return self

        return self

    def executemany(self, sql, seq_of_params):
        for p in seq_of_params:
            self.execute(sql, p)
        return self

    def executescript(self, script):
        for stmt in script.split(';'):
            s = stmt.strip()
            if s:
                self.execute(s)
        return self

    def fetchone(self):
        if self._index < len(self._results):
            row = self._results[self._index]
            self._index += 1
            return row
        return None

    def fetchall(self):
        rows = self._results[self._index:]
        self._index = len(self._results)
        return rows

    def _parse_simple_where(self, where_clause, params):
        q = {}
        # remove ORDER BY, LIMIT
        where_clause = re.split(r'\b(ORDER BY|LIMIT|GROUP BY)\b', where_clause, flags=re.IGNORECASE)[0].strip()

        # Handle OR conditions (e.g. h.user1_id = ? OR h.user2_id = ?)
        if re.search(r'\bOR\b', where_clause, re.IGNORECASE) and not re.search(r'\bAND\b', where_clause, re.IGNORECASE):
            or_parts = re.split(r'\bOR\b', where_clause, flags=re.IGNORECASE)
            or_list = []
            p_idx = 0
            for op in or_parts:
                op = op.strip()
                m_or = re.match(r'([a-zA-Z0-9_.]+)\s*=\s*(\?|\'[^\']*\'|[0-9]+)', op)
                if m_or:
                    field = m_or.group(1).split('.')[-1]
                    val = m_or.group(2)
                    if val == '?' and p_idx < len(params):
                        val_in = params[p_idx]
                        p_idx += 1
                        if isinstance(val_in, (int, str)):
                            try:
                                i_val = int(val_in)
                                or_list.append({field: i_val})
                                or_list.append({field: str(val_in)})
                            except ValueError:
                                or_list.append({field: val_in})
                        else:
                            or_list.append({field: val_in})
                    else:
                        v = val.strip("'\"")
                        if v.isdigit():
                            or_list.append({field: int(v)})
                            or_list.append({field: v})
                        else:
                            or_list.append({field: v})
            if or_list:
                return {'$or': or_list}

        conditions = re.split(r'\bAND\b', where_clause, flags=re.IGNORECASE)
        p_idx = 0

        for cond in conditions:
            cond = cond.strip()
            if not cond or cond in ('1=1', '1 = 1', 'True', 'TRUE', '1'):
                continue

            # col LIKE ?
            m_like = re.match(r'(?:UPPER|LOWER)?\s*\(?([a-zA-Z0-9_.]+)\)?\s+LIKE\s+(\?|\'[^\']*\')', cond, re.IGNORECASE)
            if m_like:
                field, val = m_like.group(1).split('.')[-1], m_like.group(2)
                if val == '?':
                    term = str(params[p_idx]).strip('%')
                    p_idx += 1
                    q[field] = re.compile(re.escape(term), re.IGNORECASE)
                else:
                    v = val.strip("'\"% ")
                    q[field] = re.compile(re.escape(v), re.IGNORECASE)
                continue

            # LOWER(col) = ?
            m = re.match(r'LOWER\(([a-zA-Z0-9_]+)\)\s*=\s*(\?|\'[^\']*\'|[0-9]+)', cond, re.IGNORECASE)
            if m:
                field, val = m.group(1), m.group(2)
                if field.isdigit():
                    continue
                if val == '?':
                    q[field] = re.compile(f"^{re.escape(str(params[p_idx]))}$", re.IGNORECASE)
                    p_idx += 1
                else:
                    v = val.strip("'\"")
                    q[field] = re.compile(f"^{re.escape(v)}$", re.IGNORECASE)
                continue

            # col = ?
            m2 = re.match(r'([a-zA-Z0-9_.]+)\s*=\s*(\?|\'[^\']*\'|[0-9]+)', cond)
            if m2:
                field, val = m2.group(1).split('.')[-1], m2.group(2)
                if field.isdigit():
                    continue
                if val == '?':
                    val_in = params[p_idx]
                    p_idx += 1
                    if isinstance(val_in, (int, float)) or (isinstance(val_in, str) and val_in.isdigit()):
                        iv = int(val_in)
                        q[field] = {'$in': [iv, str(iv)]}
                    else:
                        q[field] = val_in
                else:
                    v = val.strip("'\"")
                    if v.isdigit():
                        iv = int(v)
                        q[field] = {'$in': [iv, str(iv)]}
                    else:
                        q[field] = v
                continue

            # col != ?
            m3 = re.match(r'([a-zA-Z0-9_.]+)\s*!=\s*(\?|\'[^\']*\'|[0-9]+)', cond)
            if m3:
                field, val = m3.group(1).split('.')[-1], m3.group(2)
                raw_val = params[p_idx] if val == '?' else val.strip("'\"")
                if val == '?':
                    p_idx += 1
                if isinstance(raw_val, (int, float)) or (isinstance(raw_val, str) and raw_val.isdigit()):
                    iv = int(raw_val)
                    q[field] = {'$nin': [iv, str(iv)]}
                else:
                    q[field] = {'$ne': raw_val}
                continue

            # col IN (...)
            m4 = re.match(r'([a-zA-Z0-9_.]+)\s+IN\s*\(([^)]+)\)', cond, re.IGNORECASE)
            if m4:
                field = m4.group(1).split('.')[-1]
                in_vals = [v.strip().strip("'\"") for v in m4.group(2).split(',')]
                q[field] = {'$in': in_vals}
                continue

        return q

    def _handle_group_by(self, sql, params):
        sql_upper = sql.upper()
        coll_m = re.search(r'FROM\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
        coll_name = coll_m.group(1) if coll_m else 'parking_slots'

        # Extract WHERE clause
        q = {}
        if 'WHERE' in sql_upper:
            where_part = re.split(r'\bWHERE\b', sql, flags=re.IGNORECASE)[1]
            where_part = re.split(r'\b(GROUP BY|ORDER BY|LIMIT)\b', where_part, flags=re.IGNORECASE)[0].strip()
            q = self._parse_simple_where(where_part, params)

        # 1. Special case: parking_lots joined with parking_slots
        if coll_name == 'parking_lots' or 'LEFT JOIN PARKING_SLOTS' in sql_upper:
            lots = list(self.db.parking_lots.find(q))
            res_rows = []
            for lot in lots:
                lid = lot.get('lot_id')
                slots = list(self.db.parking_slots.find({'lot_id': lid}))
                row_dict = dict(lot)
                row_dict.pop('_id', None)
                row_dict['actual_slot_count'] = len(slots)
                row_dict['available_count'] = sum(1 for s in slots if (s.get('status') or '').lower() == 'available')
                row_dict['occupied_count'] = sum(1 for s in slots if (s.get('status') or '').lower() == 'occupied')
                row_dict['reserved_count'] = sum(1 for s in slots if (s.get('status') or '').lower() == 'reserved')
                row_dict['overstayed_count'] = sum(1 for s in slots if (s.get('status') or '').lower() == 'overstayed')
                row_dict['disabled_count'] = sum(1 for s in slots if (s.get('status') or '').lower() in ('disabled', 'maintenance'))
                res_rows.append(MongoRow(row_dict))
            self._results = res_rows
            self.rowcount = len(res_rows)
            return self

        # 2. Special case: users joined with reservations
        if coll_name == 'users' and 'RESERVATIONS' in sql_upper:
            users = list(self.db.users.find(q))
            res_rows = []
            for u in users:
                uid = u.get('user_id')
                r_list = list(self.db.reservations.find({'user_id': uid}))
                row_dict = dict(u)
                row_dict.pop('_id', None)
                row_dict['total_bookings'] = len(r_list)
                row_dict['total_overstays'] = sum(1 for r in r_list if (r.get('status') or '').lower() == 'overstayed')
                res_rows.append(MongoRow(row_dict))
            self._results = res_rows
            self.rowcount = len(res_rows)
            return self

        # 3. Special case: parking_slots joined with reservations (slot utilization)
        if coll_name == 'parking_slots' and 'RESERVATIONS' in sql_upper:
            slots = list(self.db.parking_slots.find(q))
            res_rows = []
            for s in slots:
                sid = s.get('slot_id')
                r_list = list(self.db.reservations.find({'slot_id': sid}))
                scores = [r.get('suitability_score') for r in r_list if r.get('suitability_score') is not None]
                row_dict = {
                    'slot_id': sid,
                    'slot_number': s.get('slot_number'),
                    'floor': s.get('floor'),
                    'zone': s.get('zone'),
                    'slot_type': s.get('slot_type'),
                    'booking_count': len(r_list),
                    'avg_suitability': round(sum(scores) / len(scores), 1) if scores else 0.0
                }
                res_rows.append(MongoRow(row_dict))
            res_rows.sort(key=lambda x: x.get('booking_count', 0), reverse=True)
            self._results = res_rows
            self.rowcount = len(res_rows)
            return self

        # 4. Special case: notifications group by type
        if coll_name == 'notifications':
            pipeline = []
            if q:
                pipeline.append({'$match': q})
            pipeline.append({
                '$group': {
                    '_id': '$type',
                    'cnt': {'$sum': 1},
                    'count': {'$sum': 1},
                    'unread': {'$sum': {'$cond': [{'$eq': ['$is_read', 0]}, 1, 0]}}
                }
            })
            self._results = []
            for doc in self.db.notifications.aggregate(pipeline):
                self._results.append(MongoRow({
                    'type': doc['_id'],
                    'cnt': doc['cnt'],
                    'count': doc['count'],
                    'unread': doc['unread']
                }))
            self.rowcount = len(self._results)
            return self

        # 5. Generic Group By (e.g. GROUP BY status)
        group_m = re.search(r'GROUP\s+BY\s+([a-zA-Z0-9_.]+)', sql, re.IGNORECASE)
        group_field = group_m.group(1).split('.')[-1] if group_m else 'status'
        pipeline = []
        if q:
            pipeline.append({'$match': q})
        pipeline.append({
            '$group': {
                '_id': f'${group_field}',
                'cnt': {'$sum': 1},
                'count': {'$sum': 1}
            }
        })
        self._results = []
        for doc in self.db[coll_name].aggregate(pipeline):
            self._results.append(MongoRow({
                group_field: doc['_id'],
                'status': doc['_id'],
                'cnt': doc['cnt'],
                'count': doc['count']
            }))
        self.rowcount = len(self._results)
        return self

    def _handle_select(self, sql, params):
        coll_m = re.search(r'FROM\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
        coll_name = coll_m.group(1) if coll_m else 'users'
        sql_upper = sql.upper()

        cols = None
        if coll_m:
            select_part = sql[:coll_m.start()].strip()
            cols_str = re.sub(r'^SELECT\s+(DISTINCT\s+)?', '', select_part, flags=re.IGNORECASE).strip()
            if cols_str and cols_str != '*' and not cols_str.endswith('.*'):
                cols = [c.strip() for c in cols_str.split(',') if c.strip()]

        q = {}
        if 'WHERE' in sql_upper:
            where_part = re.split(r'\bWHERE\b', sql, flags=re.IGNORECASE)[1].strip()
            q = self._parse_simple_where(where_part, params)

        docs = list(self.db[coll_name].find(q))

        # Check limit
        limit_m = re.search(r'LIMIT\s+([0-9]+)', sql, re.IGNORECASE)
        limit = int(limit_m.group(1)) if limit_m else None
        if not limit and re.search(r'LIMIT\s+\?', sql, re.IGNORECASE) and params:
            try:
                limit = int(params[-1])
            except (ValueError, TypeError, IndexError):
                pass

        # Order by
        if 'ORDER BY' in sql_upper:
            order_part = re.split(r'\bORDER BY\b', sql, flags=re.IGNORECASE)[1].strip()
            desc = 'DESC' in order_part.upper()
            order_col = order_part.split()[0].replace(',', '').strip().split('.')[-1]
            try:
                docs.sort(key=lambda d: d.get(order_col, 0) or 0, reverse=desc)
            except Exception:
                pass

        if limit:
            docs = docs[:limit]

        self._results = []
        for d in docs:
            cd = dict(d)
            cd.pop('_id', None)

            # Enrich joined data if query contains JOIN
            if 'JOIN' in sql_upper:
                if coll_name == 'vehicles':
                    uid = cd.get('user_id')
                    u = self.db.users.find_one({'user_id': uid}) or {}
                    cd['owner_name'] = u.get('name', 'Unknown')
                    cd['owner_email'] = u.get('email', '')
                    cd['owner_phone'] = u.get('phone', '')

                elif coll_name == 'parking_slots':
                    lid = cd.get('lot_id')
                    lot = self.db.parking_lots.find_one({'lot_id': lid}) or {}
                    cd['lot_name'] = lot.get('lot_name', '')
                    c_res_id = cd.get('current_reservation_id')
                    if c_res_id:
                        res = self.db.reservations.find_one({'reservation_id': c_res_id}) or {}
                        u = self.db.users.find_one({'user_id': res.get('user_id')}) or {}
                        cd['user_name'] = u.get('name')
                        cd['user_email'] = u.get('email')
                        cd['license_plate'] = res.get('license_plate') or cd.get('current_plate')

                elif coll_name == 'reservations':
                    sid = cd.get('slot_id')
                    slot = self.db.parking_slots.find_one({'slot_id': sid}) or {}
                    lid = slot.get('lot_id')
                    lot = self.db.parking_lots.find_one({'lot_id': lid}) or {}
                    uid = cd.get('user_id')
                    u = self.db.users.find_one({'user_id': uid}) or {}
                    cd['lot_id'] = lid or slot.get('lot_id', 1)
                    cd['slot_number'] = slot.get('slot_number', '')
                    cd['floor'] = slot.get('floor', '')
                    cd['zone'] = slot.get('zone', '')
                    cd['slot_type'] = slot.get('slot_type', '')
                    cd['lot_name'] = lot.get('lot_name', '')
                    cd['lot_location'] = lot.get('location', '')
                    cd['user_name'] = u.get('name', '')
                    cd['owner_name'] = u.get('name', '')
                    cd['requester_name'] = u.get('name', '')
                    cd['driver_name'] = u.get('name', '')
                    cd['user_email'] = u.get('email', '')
                    cd['phone'] = u.get('phone', '')

                elif coll_name in ('slot_exchange_requests', 'slot_exchange_listings', 'slot_exchange_history'):
                    sid = cd.get('slot_id') or cd.get('offered_slot_id')
                    if sid:
                        slot = self.db.parking_slots.find_one({'slot_id': sid}) or {}
                        cd['slot_number'] = slot.get('slot_number', '')
                        cd['distance_to_entry_m'] = slot.get('distance_to_entry_m', 15)
                        cd['distance_to_elevator_m'] = slot.get('distance_to_elevator_m', 20)
                    lid = cd.get('lot_id')
                    if lid:
                        lot = self.db.parking_lots.find_one({'lot_id': lid}) or {}
                        cd['lot_name'] = lot.get('lot_name', '')
                        cd['lot_location'] = lot.get('location', '')
                        cd['hourly_rate'] = lot.get('hourly_rate', 40.0)
                    uid = cd.get('user_id') or cd.get('owner_user_id')
                    if uid:
                        u = self.db.users.find_one({'user_id': uid}) or {}
                        cd['owner_name'] = u.get('name', '')
                        cd['owner_email'] = u.get('email', '')
                        cd['owner_member_since'] = u.get('created_at', '')
                    req_uid = cd.get('requester_user_id') or cd.get('user1_id')
                    if req_uid:
                        u = self.db.users.find_one({'user_id': req_uid}) or {}
                        cd['requester_name'] = u.get('name', '')
                        cd['requester_email'] = u.get('email', '')
                        cd['requester_member_since'] = u.get('created_at', '')
                        cd['user1_name'] = u.get('name', '')

                    # Look up request reservation & slot details
                    r_req_id = cd.get('requester_reservation_id')
                    if r_req_id:
                        r_req = self.db.reservations.find_one({'reservation_id': r_req_id}) or {}
                        s_req = self.db.parking_slots.find_one({'slot_id': r_req.get('slot_id')}) or {}
                        l_req = self.db.parking_lots.find_one({'lot_id': s_req.get('lot_id')}) or {}
                        cd['requester_slot_number'] = s_req.get('slot_number', '')
                        cd['requester_floor'] = s_req.get('floor', '')
                        cd['requester_slot_type'] = s_req.get('slot_type', '')
                        cd['requester_lot_name'] = l_req.get('lot_name', '')
                        cd['requester_date'] = r_req.get('date', '')
                        cd['requester_start_time'] = r_req.get('start_time', '')
                        cd['requester_end_time'] = r_req.get('end_time', '')

                    # Look up listing & owner reservation & slot details
                    list_id = cd.get('listing_id')
                    if list_id:
                        list_doc = self.db.slot_exchange_listings.find_one({'listing_id': list_id}) or {}
                        cd['owner_reservation_id'] = list_doc.get('reservation_id')
                        cd['owner_slot_id'] = list_doc.get('slot_id')
                        cd['listing_owner_id'] = list_doc.get('user_id')
                        cd['listing_status'] = list_doc.get('status')
                        r_own_id = list_doc.get('reservation_id') or cd.get('owner_reservation_id')
                        if r_own_id:
                            r_own = self.db.reservations.find_one({'reservation_id': r_own_id}) or {}
                            s_own = self.db.parking_slots.find_one({'slot_id': r_own.get('slot_id')}) or {}
                            l_own = self.db.parking_lots.find_one({'lot_id': s_own.get('lot_id')}) or {}
                            cd['owner_slot_number'] = s_own.get('slot_number', '')
                            cd['owner_floor'] = s_own.get('floor', '')
                            cd['owner_slot_type'] = s_own.get('slot_type', '')
                            cd['owner_lot_name'] = l_own.get('lot_name', '')
                            cd['owner_date'] = r_own.get('date', '')
                            cd['owner_start_time'] = r_own.get('start_time', '')
                            cd['owner_end_time'] = r_own.get('end_time', '')

                    # History slots & users
                    if coll_name == 'slot_exchange_history':
                        u1 = self.db.users.find_one({'user_id': cd.get('user1_id')}) or {}
                        u2 = self.db.users.find_one({'user_id': cd.get('user2_id')}) or {}
                        s1_old = self.db.parking_slots.find_one({'slot_id': cd.get('user1_old_slot_id')}) or {}
                        s1_new = self.db.parking_slots.find_one({'slot_id': cd.get('user1_new_slot_id')}) or {}
                        s2_old = self.db.parking_slots.find_one({'slot_id': cd.get('user2_old_slot_id')}) or {}
                        s2_new = self.db.parking_slots.find_one({'slot_id': cd.get('user2_new_slot_id')}) or {}
                        cd['user1_name'] = u1.get('name', '')
                        cd['user2_name'] = u2.get('name', '')
                        cd['user1_old_slot_no'] = s1_old.get('slot_number', '')
                        cd['user1_new_slot_no'] = s1_new.get('slot_number', '')
                        cd['user2_old_slot_no'] = s2_old.get('slot_number', '')
                        cd['user2_new_slot_no'] = s2_new.get('slot_number', '')

            if cols:
                has_wildcard = any(c.strip() == '*' or c.strip().endswith('.*') for c in cols)
                if has_wildcard:
                    projected = dict(cd)
                    for c in cols:
                        if c.strip() == '*' or c.strip().endswith('.*'):
                            continue
                        m_as = re.search(r'\bAS\b\s+([a-zA-Z0-9_]+)', c, re.IGNORECASE)
                        alias = m_as.group(1) if m_as else c.split('.')[-1].strip()
                        raw_col = re.split(r'\bAS\b', c, flags=re.IGNORECASE)[0].strip().split('.')[-1]
                        val = cd.get(raw_col) if raw_col in cd else cd.get(alias)
                        projected[alias] = val
                    self._results.append(MongoRow(projected))
                else:
                    projected = {}
                    for c in cols:
                        m_as = re.search(r'\bAS\b\s+([a-zA-Z0-9_]+)', c, re.IGNORECASE)
                        alias = m_as.group(1) if m_as else c.split('.')[-1].strip()
                        raw_col = re.split(r'\bAS\b', c, flags=re.IGNORECASE)[0].strip().split('.')[-1]
                        val = cd.get(raw_col) if raw_col in cd else cd.get(alias)
                        projected[alias] = val
                    self._results.append(MongoRow(projected))
            else:
                self._results.append(MongoRow(cd))

        if 'DISTINCT' in sql_upper:
            seen = set()
            deduped = []
            for r in self._results:
                tup = tuple(r.values())
                if tup not in seen:
                    seen.add(tup)
                    deduped.append(r)
            self._results = deduped

        self.rowcount = len(self._results)

    def _handle_insert(self, sql, params):
        coll_m = re.search(r'INTO\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
        coll_name = coll_m.group(1) if coll_m else 'users'

        cols_m = re.search(r'\(([^)]+)\)\s+VALUES', sql, re.IGNORECASE)
        doc = {}
        if cols_m:
            cols = [c.strip() for c in cols_m.group(1).split(',')]
            vals_m = re.search(r'VALUES\s*\((.*)\)', sql, re.IGNORECASE | re.DOTALL)
            if vals_m:
                import csv
                try:
                    val_reader = csv.reader([vals_m.group(1).strip()], skipinitialspace=True)
                    vals = next(val_reader)
                except Exception:
                    vals = [v.strip() for v in vals_m.group(1).split(',')]
            else:
                vals = ['?' for _ in cols]

            p_idx = 0
            for i, col in enumerate(cols):
                raw_v = vals[i].strip() if i < len(vals) else '?'
                if raw_v == '?':
                    if p_idx < len(params):
                        doc[col] = params[p_idx]
                        p_idx += 1
                else:
                    v = raw_v.strip("'\"")
                    if v.isdigit():
                        val = int(v)
                    else:
                        try:
                            val = float(v)
                        except ValueError:
                            val = v
                    doc[col] = val

            numeric_id_cols = {
                'user_id', 'vehicle_id', 'slot_id', 'lot_id', 'reservation_id', 
                'listing_id', 'request_id', 'history_id', 'notification_id', 'related_id',
                'owner_user_id', 'requester_user_id', 'requester_reservation_id',
                'user1_id', 'user2_id', 'user1_reservation_id', 'user2_reservation_id',
                'user1_old_slot_id', 'user1_new_slot_id', 'user2_old_slot_id', 'user2_new_slot_id',
                'current_reservation_id', 'is_read', 'is_active'
            }
            for col_key in list(doc.keys()):
                if col_key in numeric_id_cols and doc[col_key] is not None:
                    try:
                        doc[col_key] = int(doc[col_key])
                    except (ValueError, TypeError):
                        pass

        # Assign auto-increment sequence ID if missing
        id_field_map = {
            'users': 'user_id',
            'vehicles': 'vehicle_id',
            'parking_lots': 'lot_id',
            'parking_slots': 'slot_id',
            'reservations': 'reservation_id',
            'overstay_records': 'overstay_id',
            'notifications': 'notification_id',
            'activity_logs': 'log_id',
            'login_logs': 'log_id',
            'slot_exchange_requests': 'request_id',
            'slot_exchange_listings': 'listing_id',
            'slot_exchange_history': 'history_id'
        }
        id_field = id_field_map.get(coll_name)
        if id_field and (id_field not in doc or doc[id_field] is None):
            doc[id_field] = get_next_sequence(coll_name)
            self.lastrowid = doc[id_field]
        elif id_field and doc.get(id_field):
            self.lastrowid = int(doc[id_field])

        if coll_name == 'users':
            if 'is_active' not in doc:
                doc['is_active'] = 1
            if 'email' in doc and doc['email']:
                doc['email'] = str(doc['email']).strip().lower()

        if 'created_at' not in doc:
            doc['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.db[coll_name].insert_one(doc)
        self.rowcount = 1

    def _handle_update(self, sql, params):
        coll_m = re.search(r'UPDATE\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
        coll_name = coll_m.group(1) if coll_m else 'users'

        set_part = sql.split('SET', 1)[1].split('WHERE', 1)[0].strip()
        where_part = sql.split('WHERE', 1)[1].strip() if 'WHERE' in sql else ''

        set_assignments = [s.strip() for s in set_part.split(',')]
        updates = {}
        p_idx = 0
        for assign in set_assignments:
            parts = assign.split('=', 1)
            col = parts[0].strip()
            val_expr = parts[1].strip()
            if val_expr == '?':
                updates[col] = params[p_idx]
                p_idx += 1
            elif val_expr.upper() == 'NULL':
                updates[col] = None
            else:
                updates[col] = val_expr.strip("'\"")

        where_params = params[p_idx:]
        q = self._parse_simple_where(where_part, where_params) if where_part else {}

        numeric_id_cols = {
            'user_id', 'vehicle_id', 'slot_id', 'lot_id', 'reservation_id', 
            'listing_id', 'request_id', 'history_id', 'notification_id', 'related_id',
            'owner_user_id', 'requester_user_id', 'requester_reservation_id',
            'current_reservation_id', 'is_read', 'is_active'
        }
        for col_key in list(updates.keys()):
            if col_key in numeric_id_cols and updates[col_key] is not None:
                try:
                    updates[col_key] = int(updates[col_key])
                except (ValueError, TypeError):
                    pass

        res = self.db[coll_name].update_many(q, {'$set': updates})
        self.rowcount = res.modified_count

    def _handle_delete(self, sql, params):
        coll_m = re.search(r'FROM\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
        coll_name = coll_m.group(1) if coll_m else 'users'

        q = {}
        if 'WHERE' in sql.upper():
            where_part = sql.split('WHERE', 1)[1].strip()
            q = self._parse_simple_where(where_part, params)

        res = self.db[coll_name].delete_many(q)
        self.rowcount = res.deleted_count

class MongoConnection:
    """Wrapper exposing standard connection semantics backed 100% by MongoDB."""
    def __init__(self, db=None):
        self.db = db if db is not None else get_mongo_db()
        self.row_factory = None

    def cursor(self):
        return MongoCursor(self.db)

    def commit(self):
        pass  # MongoDB handles write persistence automatically

    def rollback(self):
        pass

    def close(self):
        pass

    def execute(self, sql, params=()):
        c = self.cursor()
        return c.execute(sql, params)

    def executescript(self, script):
        c = self.cursor()
        return c.executescript(script)

def get_db_connection():
    """Returns a MongoConnection wrapper providing 100% MongoDB persistence."""
    return MongoConnection(get_mongo_db())

if __name__ == '__main__':
    clear_and_init_mongodb(force_reseed=True)
