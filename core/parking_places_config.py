"""
Configurable Parking Places and Categories Configuration Module.
Provides configurable parking facility categories and specific parking locations
for the 5-step Smart Parking booking workflow.

Categories:
1. Institutions
2. Mall
3. Public Places
4. City Parking

Each category provides 3 configurable parking places with:
- place_id
- place_name
- category
- address
- hourly_rate
- icon
- lot_id
- slot_numbers
"""

import os
from datetime import datetime

# Facility Categories
FACILITY_CATEGORIES = [
    {
        'id': 'institutions',
        'name': 'Institutions',
        'title': 'Institutions',
        'description': 'University campus, medical colleges & academic institutes',
        'icon': 'fa-graduation-cap',
        'lot_id': 1
    },
    {
        'id': 'mall',
        'name': 'Mall',
        'title': 'Mall',
        'description': 'Shopping centers, lifestyle complexes & retail plazas',
        'icon': 'fa-bag-shopping',
        'lot_id': 2
    },
    {
        'id': 'public_places',
        'name': 'Public Places',
        'title': 'Public Places',
        'description': 'Railway stations, transit terminals & public civic squares',
        'icon': 'fa-tree-city',
        'lot_id': 3
    },
    {
        'id': 'city_parking',
        'name': 'City Parking',
        'title': 'City Parking',
        'description': 'Municipal commercial hubs & central business districts',
        'icon': 'fa-square-parking',
        'lot_id': 4
    }
]

# Configurable Specific Parking Locations (3 per category)
DEFAULT_PARKING_PLACES = [
    # -------------------------------------------------------------
    # 1. Institutions (Lot 1, 43 slots)
    # -------------------------------------------------------------
    {
        'place_id': 'inst_univ',
        'place_name': 'AJ Institute of Management',
        'category': 'Institutions',
        'address': 'NH 66, Kottara Chowki, Mangaluru - 575006',
        'hourly_rate': 30.0,
        'overstay_penalty_rate': 80.0,
        'icon': 'fa-graduation-cap',
        'image_url': '/static/images/aj_management.jpg',
        'supported_vehicles': ['Car', 'Bike'],
        'lot_id': 1,
        'operating_hours': '06:00 AM - 11:00 PM',
        'slot_numbers': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'R1', 'R2', 'R3', 'R4']
    },
    {
        'place_id': 'inst_edu',
        'place_name': 'AJ Institute of Engineering and Technology',
        'category': 'Institutions',
        'address': 'NH 66, Kottara, Mangaluru - 575006',
        'hourly_rate': 40.0,
        'overstay_penalty_rate': 100.0,
        'icon': 'fa-school',
        'image_url': '/static/images/aj_engineering.jpg',
        'supported_vehicles': ['Car', 'Bike'],
        'lot_id': 1,
        'operating_hours': '07:00 AM - 10:00 PM',
        'slot_numbers': ['R19', 'R20', 'R21', 'R22', 'R23', 'R24', 'R25', 'R26', 'R27', 'R28', 'R29', 'R30', 'R31', 'R32']
    },
    {
        'place_id': 'inst_med',
        'place_name': 'AJ Institute of Medical Sciences',
        'category': 'Institutions',
        'address': 'Kuntikana, Mangaluru - 575004',
        'hourly_rate': 35.0,
        'overstay_penalty_rate': 90.0,
        'icon': 'fa-hospital',
        'image_url': '/static/images/aj_medical.jpg',
        'supported_vehicles': ['Car', 'Bike'],
        'lot_id': 1,
        'operating_hours': '24/7 (Emergency & Visitor Access)',
        'slot_numbers': ['R5', 'R6', 'R7', 'R8', 'R9', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15', 'R16', 'R17', 'R18']
    },

    # -------------------------------------------------------------
    # 2. Mall (Lot 2, 37 slots)
    # -------------------------------------------------------------
    {
        'place_id': 'mall_city_centre',
        'place_name': 'City Centre Mall',
        'category': 'Mall',
        'address': 'MG Road, Commercial Center, Bangalore',
        'hourly_rate': 50.0,
        'overstay_penalty_rate': 120.0,
        'icon': 'fa-bag-shopping',
        'lot_id': 2,
        'operating_hours': '09:00 AM - 11:30 PM',
        'slot_numbers': [f'U{i:02d}' for i in range(1, 14)]
    },
    {
        'place_id': 'mall_central',
        'place_name': 'Central Mall',
        'category': 'Mall',
        'address': 'Residency Road, Lifestyle Hub, Bangalore',
        'hourly_rate': 60.0,
        'overstay_penalty_rate': 140.0,
        'icon': 'fa-store',
        'lot_id': 2,
        'operating_hours': '09:30 AM - 11:00 PM',
        'slot_numbers': [f'U{i:02d}' for i in range(14, 26)]
    },
    {
        'place_id': 'mall_shopping',
        'place_name': 'Shopping Mall',
        'category': 'Mall',
        'address': 'Outer Ring Road, Retail Boulevard, Bangalore',
        'hourly_rate': 50.0,
        'overstay_penalty_rate': 120.0,
        'icon': 'fa-cart-shopping',
        'lot_id': 2,
        'operating_hours': '10:00 AM - 11:00 PM',
        'slot_numbers': [f'U{i:02d}' for i in range(26, 38)]
    },

    # -------------------------------------------------------------
    # 3. Public Places (Lot 3, 30 slots)
    # -------------------------------------------------------------
    {
        'place_id': 'pub_railway',
        'place_name': 'Railway Station',
        'category': 'Public Places',
        'address': 'Station Road, City Railway Terminus, Bangalore',
        'hourly_rate': 20.0,
        'overstay_penalty_rate': 60.0,
        'icon': 'fa-train-subway',
        'lot_id': 3,
        'operating_hours': '24/7 (Open Daily)',
        'slot_numbers': [f'U{i:02d}' for i in range(38, 48)]
    },
    {
        'place_id': 'pub_bus',
        'place_name': 'Bus Stand',
        'category': 'Public Places',
        'address': 'Central KSRTC Terminal, Majestic, Bangalore',
        'hourly_rate': 20.0,
        'overstay_penalty_rate': 60.0,
        'icon': 'fa-bus',
        'lot_id': 3,
        'operating_hours': '24/7 (Open Daily)',
        'slot_numbers': [f'U{i:02d}' for i in range(48, 58)]
    },
    {
        'place_id': 'pub_parking_area',
        'place_name': 'Public Parking Area',
        'category': 'Public Places',
        'address': 'Town Hall Square, Corporation Circle, Bangalore',
        'hourly_rate': 25.0,
        'overstay_penalty_rate': 70.0,
        'icon': 'fa-square-parking',
        'lot_id': 3,
        'operating_hours': '06:00 AM - 11:00 PM',
        'slot_numbers': [f'U{i:02d}' for i in range(58, 68)]
    },

    # -------------------------------------------------------------
    # 4. City Parking (Lot 4, 100 slots)
    # -------------------------------------------------------------
    {
        'place_id': 'city_hampankatta',
        'place_name': 'Hampankatta Parking',
        'category': 'City Parking',
        'address': 'Hampankatta Commercial Junction, Mangaluru',
        'hourly_rate': 40.0,
        'overstay_penalty_rate': 100.0,
        'icon': 'fa-city',
        'lot_id': 4,
        'operating_hours': '24/7 (Open Daily)',
        'slot_numbers': (
            [f'A{i}' for i in range(1, 13)] +
            [f'B{i}' for i in range(1, 13)] +
            [f'C{i}' for i in range(1, 11)]
        )
    },
    {
        'place_id': 'city_central',
        'place_name': 'Central City Parking',
        'category': 'City Parking',
        'address': 'K.S. Rao Road, City Centre, Mangaluru',
        'hourly_rate': 40.0,
        'overstay_penalty_rate': 100.0,
        'icon': 'fa-building-columns',
        'lot_id': 4,
        'operating_hours': '24/7 (Open Daily)',
        'slot_numbers': (
            [f'C{i}' for i in range(11, 14)] +
            [f'D{i}' for i in range(1, 14)] +
            [f'E{i}' for i in range(1, 13)] +
            [f'F{i}' for i in range(1, 6)]
        )
    },
    {
        'place_id': 'city_market',
        'place_name': 'Market Area Parking',
        'category': 'City Parking',
        'address': 'Central Market Complex, Car Street, Mangaluru',
        'hourly_rate': 35.0,
        'overstay_penalty_rate': 90.0,
        'icon': 'fa-shop',
        'lot_id': 4,
        'operating_hours': '05:00 AM - 11:00 PM',
        'slot_numbers': (
            [f'F{i}' for i in range(6, 13)] +
            [f'G{i}' for i in range(1, 14)] +
            [f'H{i}' for i in range(1, 14)]
        )
    }
]

def get_categories():
    """Returns list of category objects."""
    return FACILITY_CATEGORIES

def normalize_category_name(cat):
    """Normalizes category name case-insensitively."""
    if not cat:
        return ''
    c_lower = str(cat).strip().lower().replace('_', ' ')
    for c in FACILITY_CATEGORIES:
        if c['name'].lower() == c_lower or c['id'].lower() == c_lower or c_lower.startswith(c['id'].lower()):
            return c['name']
    # Match 'public places' and 'public place'
    if 'public' in c_lower:
        return 'Public Places'
    if 'institution' in c_lower:
        return 'Institutions'
    if 'mall' in c_lower:
        return 'Mall'
    if 'city' in c_lower:
        return 'City Parking'
    return str(cat).strip()

def sync_places_to_mongodb(db):
    """
    Ensures MongoDB collection 'parking_places' exists and is populated.
    Also ensures each parking slot in 'parking_slots' has place_id, place_name,
    and category assigned without altering any existing slots or IDs.
    """
    if db is None:
        return

    # 1. Populate parking_places collection if empty or missing entries
    for p in DEFAULT_PARKING_PLACES:
        existing = db.parking_places.find_one({'place_id': p['place_id']})
        if not existing:
            p_copy = dict(p)
            p_copy['total_slots'] = len(p['slot_numbers'])
            p_copy['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            p_copy['updated_at'] = p_copy['created_at']
            db.parking_places.insert_one(p_copy)
        else:
            # Sync rates, address, and metadata
            db.parking_places.update_one(
                {'place_id': p['place_id']},
                {'$set': {
                    'place_name': p['place_name'],
                    'category': p['category'],
                    'address': p['address'],
                    'hourly_rate': p['hourly_rate'],
                    'overstay_penalty_rate': p['overstay_penalty_rate'],
                    'icon': p['icon'],
                    'image_url': p.get('image_url', ''),
                    'supported_vehicles': p.get('supported_vehicles', ['Car', 'Bike']),
                    'lot_id': p['lot_id'],
                    'operating_hours': p['operating_hours'],
                    'slot_numbers': p['slot_numbers'],
                    'total_slots': len(p['slot_numbers'])
                }}
            )

    # 2. Assign place_id, place_name, category to existing parking_slots in MongoDB
    for p in DEFAULT_PARKING_PLACES:
        db.parking_slots.update_many(
            {
                'lot_id': p['lot_id'],
                'slot_number': {'$in': p['slot_numbers']}
            },
            {
                '$set': {
                    'place_id': p['place_id'],
                    'place_name': p['place_name'],
                    'category': p['category'],
                    'facility_category': p['category']
                }
            }
        )

def get_all_places(db=None):
    """
    Returns list of all parking places. Reads from MongoDB if available,
    falling back to DEFAULT_PARKING_PLACES.
    """
    if db is not None:
        try:
            places = list(db.parking_places.find({}, {'_id': 0}))
            if places:
                return places
        except Exception:
            pass
    return DEFAULT_PARKING_PLACES

def get_places_by_category(category_name, db=None):
    """Returns the 3 parking places belonging to the specified category."""
    norm_cat = normalize_category_name(category_name)
    all_p = get_all_places(db)
    return [p for p in all_p if normalize_category_name(p.get('category')) == norm_cat]

def get_place_by_id(place_id, db=None):
    """Returns single place dictionary by place_id."""
    if not place_id:
        return None
    pid = str(place_id).strip()
    all_p = get_all_places(db)
    for p in all_p:
        if p.get('place_id') == pid:
            return p
    # Try case-insensitive place_name lookup
    for p in all_p:
        if p.get('place_name', '').lower() == pid.lower():
            return p
    return None

def get_place_by_name(name, db=None):
    """Returns single place dictionary by name with alias support."""
    if not name:
        return None
    n_lower = str(name).strip().lower()
    all_p = get_all_places(db)
    for p in all_p:
        if p.get('place_name', '').lower() == n_lower:
            return p
    # Aliases for backward compatibility
    aliases = {
        'university campus': 'inst_univ',
        'aj institute of management': 'inst_univ',
        'educational institution': 'inst_edu',
        'aj institute of engineering and technology': 'inst_edu',
        'medical college': 'inst_med',
        'aj institute of medical sciences': 'inst_med',
    }
    if n_lower in aliases:
        return get_place_by_id(aliases[n_lower], db)
    return None

def get_place_slot_counts(place_id, db=None, date=None, start_time=None, end_time=None):
    """
    Computes real total slots and available slots for a place from MongoDB.
    No fake counts are used.
    """
    place = get_place_by_id(place_id, db)
    if not place:
        return 0, 0

    if db is None:
        total = len(place.get('slot_numbers', []))
        return total, total

    pid = place['place_id']
    lot_id = place.get('lot_id', 1)
    slot_numbers = place.get('slot_numbers', [])

    # Total slots
    total = db.parking_slots.count_documents({
        'lot_id': lot_id,
        'slot_number': {'$in': slot_numbers}
    })
    if total == 0:
        total = len(slot_numbers)

    # If no date/interval given, count slots where status == 'available'
    if not date:
        available = db.parking_slots.count_documents({
            'lot_id': lot_id,
            'slot_number': {'$in': slot_numbers},
            'status': 'available'
        })
        return total, available

    # For date/interval, count slots that have no overlapping confirmed reservation
    from mongo_engine import mongo_search_available_slots
    slots = mongo_search_available_slots(lot_id=lot_id, date=date, start_time=start_time, end_time=end_time, place_id=pid)
    avail_count = sum(1 for s in slots if s.get('status') == 'available')
    return total, avail_count
