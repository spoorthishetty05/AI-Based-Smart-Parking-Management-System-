import os
import sys
import json
import io
import csv
import re
from functools import wraps
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, Response, session, redirect, url_for, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, DuplicateKeyError

from core.database import (
    get_db_connection, init_db, ensure_permanent_admin, 
    PERMANENT_ADMINS, create_notification, ensure_notifications_table,
    ensure_users_columns, get_mongo_db, get_next_sequence, clear_and_init_mongodb
)
from core.mongo_engine import (
    get_mongo_client, get_mongo_db, get_mongo_status, sync_sqlite_to_mongodb, init_mongodb_data,
    mongo_save_user, mongo_get_user_by_email, mongo_get_user_by_id,
    mongo_update_user, mongo_delete_user, mongo_save_vehicle, mongo_delete_vehicle,
    mongo_record_login, mongo_save_reservation, mongo_update_reservation,
    mongo_update_slot, mongo_log_activity, mongo_save_overstay, mongo_update_overstay,
    mongo_search_available_slots, mongo_check_slot_available, mongo_create_booking,
    mongo_get_user_bookings, mongo_get_booking_by_id, mongo_cancel_booking,
    mongo_get_checkout_preview, mongo_exit_booking, mongo_start_parking,
    validate_booking_datetime, calculate_end_time_string, check_time_intervals_overlap
)
from routes.middleware import login_required, admin_required, verify_password_hash, get_authenticated_user_id

lot_bp = Blueprint('lot', __name__)


# PARKING LOT & SLOT MANAGEMENT APIs (MODULE 2)
# ==========================================

VALID_SLOT_STATUSES = {'available', 'reserved', 'occupied', 'overstayed', 'disabled'}
VALID_SLOT_TYPES = {'standard', 'regular', 'ev', 'compact', 'disabled', 'accessible', 'vip'}

@lot_bp.route('/api/lots/search', methods=['GET'])
def search_parking_lots():
    """Search parking lots by location, landmark, or lot name."""
    query = request.args.get('q', '').strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*,
               COUNT(s.slot_id) as actual_slot_count,
               COUNT(CASE WHEN LOWER(s.status) = 'available' THEN 1 END) as available_count,
               COUNT(CASE WHEN LOWER(s.status) = 'occupied' THEN 1 END) as occupied_count,
               COUNT(CASE WHEN LOWER(s.status) = 'reserved' THEN 1 END) as reserved_count,
               COUNT(CASE WHEN LOWER(s.status) = 'overstayed' THEN 1 END) as overstayed_count,
               COUNT(CASE WHEN LOWER(s.status) = 'disabled' THEN 1 END) as disabled_count
        FROM parking_lots l
        LEFT JOIN parking_slots s ON l.lot_id = s.lot_id
        GROUP BY l.lot_id
        ORDER BY l.lot_id ASC
    """)
    rows = cursor.fetchall()
    all_lots = [dict(r) for r in rows]
    conn.close()

    if query:
        filtered = [
            lot for lot in all_lots
            if query in (lot.get('lot_name') or '').lower()
            or query in (lot.get('location') or '').lower()
            or query in (lot.get('address') or '').lower()
        ]
    else:
        filtered = all_lots

    return jsonify({'status': 'success', 'query': query, 'count': len(filtered), 'lots': filtered})

@lot_bp.route('/api/lots', methods=['GET'])
def get_all_parking_lots():
    """Returns all parking lots with detailed metadata, capacity and real-time status counts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*,
               COUNT(s.slot_id) as actual_slot_count,
               COUNT(CASE WHEN LOWER(s.status) = 'available' THEN 1 END) as available_count,
               COUNT(CASE WHEN LOWER(s.status) = 'occupied' THEN 1 END) as occupied_count,
               COUNT(CASE WHEN LOWER(s.status) = 'reserved' THEN 1 END) as reserved_count,
               COUNT(CASE WHEN LOWER(s.status) = 'overstayed' THEN 1 END) as overstayed_count,
               COUNT(CASE WHEN LOWER(s.status) = 'disabled' THEN 1 END) as disabled_count
        FROM parking_lots l
        LEFT JOIN parking_slots s ON l.lot_id = s.lot_id
        GROUP BY l.lot_id
        ORDER BY l.lot_id ASC
    """)
    rows = cursor.fetchall()
    lots = [dict(r) for r in rows]
    conn.close()
    return jsonify({'status': 'success', 'count': len(lots), 'lots': lots})

@lot_bp.route('/api/lots/<int:lot_id>', methods=['GET'])
def get_single_parking_lot(lot_id):
    """Returns details of a specific parking lot."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*,
               COUNT(s.slot_id) as actual_slot_count,
               COUNT(CASE WHEN LOWER(s.status) = 'available' THEN 1 END) as available_count,
               COUNT(CASE WHEN LOWER(s.status) = 'occupied' THEN 1 END) as occupied_count,
               COUNT(CASE WHEN LOWER(s.status) = 'reserved' THEN 1 END) as reserved_count,
               COUNT(CASE WHEN LOWER(s.status) = 'overstayed' THEN 1 END) as overstayed_count,
               COUNT(CASE WHEN LOWER(s.status) = 'disabled' THEN 1 END) as disabled_count
        FROM parking_lots l
        LEFT JOIN parking_slots s ON l.lot_id = s.lot_id
        WHERE l.lot_id = ?
        GROUP BY l.lot_id
    """, (lot_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'status': 'error', 'message': f'Parking lot #{lot_id} not found.'}), 404
    lot = dict(row)
    conn.close()
    return jsonify({'status': 'success', 'lot': lot})

@lot_bp.route('/api/lots/config', methods=['GET'])
def get_lot_config():
    """Returns parking facility configuration parameters (backward compatible)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parking_lots LIMIT 1")
    lot = cursor.fetchone()
    
    cursor.execute("SELECT setting_key, setting_value FROM system_settings")
    settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
    conn.close()

    return jsonify({
        'status': 'success',
        'lot': dict(lot) if lot else {},
        'settings': settings
    })

@lot_bp.route('/api/lots/config/update', methods=['POST'])
@admin_required
def update_lot_config():
    """Updates lot pricing and rules."""
    data = request.get_json() or {}
    hourly_rate = float(data.get('hourly_rate', 40.0))
    penalty_rate = float(data.get('overstay_penalty_rate', 100.0))
    lot_name = data.get('lot_name')

    conn = get_db_connection()
    cursor = conn.cursor()
    if lot_name:
        cursor.execute("UPDATE parking_lots SET lot_name = ?, hourly_rate = ?, overstay_penalty_rate = ?", (lot_name, hourly_rate, penalty_rate))
    else:
        cursor.execute("UPDATE parking_lots SET hourly_rate = ?, overstay_penalty_rate = ?", (hourly_rate, penalty_rate))

    cursor.execute("UPDATE system_settings SET setting_value = ? WHERE setting_key = 'hourly_rate'", (str(hourly_rate),))
    cursor.execute("UPDATE system_settings SET setting_value = ? WHERE setting_key = 'penalty_rate'", (str(penalty_rate),))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'message': 'Parking lot configuration updated.'})

@lot_bp.route('/api/admin/lots/create', methods=['POST'])
@admin_required
def create_parking_lot():
    """Admin endpoint to create a new parking lot."""
    data = request.get_json() or {}
    lot_name = data.get('lot_name', '').strip()
    location = data.get('location', '').strip()
    total_floors = int(data.get('total_floors', 1))
    total_slots = int(data.get('total_slots', 0))
    hourly_rate = float(data.get('hourly_rate', 40.0))
    overstay_penalty_rate = float(data.get('overstay_penalty_rate', 100.0))
    operating_hours = data.get('operating_hours', '24/7 (Open Daily)').strip() or '24/7 (Open Daily)'

    if not lot_name:
        return jsonify({'status': 'error', 'message': 'Parking Lot Name is required.'}), 400
    if not location:
        return jsonify({'status': 'error', 'message': 'Parking Lot Location is required.'}), 400
    if total_floors < 1:
        return jsonify({'status': 'error', 'message': 'Number of floors must be at least 1.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO parking_lots (lot_name, location, total_floors, total_slots, hourly_rate, overstay_penalty_rate, operating_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (lot_name, location, total_floors, total_slots, hourly_rate, overstay_penalty_rate, operating_hours))
    new_lot_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Parking Lot '{lot_name}' created successfully.",
        'lot_id': new_lot_id
    }), 201

@lot_bp.route('/api/admin/lots/update', methods=['POST'])
@admin_required
def update_parking_lot():
    """Admin endpoint to update parking lot details."""
    data = request.get_json() or {}
    lot_id = data.get('lot_id')
    if not lot_id:
        return jsonify({'status': 'error', 'message': 'lot_id is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parking_lots WHERE lot_id = ?", (lot_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        return jsonify({'status': 'error', 'message': f'Parking lot #{lot_id} not found.'}), 404

    lot_name = data.get('lot_name', existing['lot_name']).strip()
    location = data.get('location', existing['location']).strip()
    total_floors = int(data.get('total_floors', existing['total_floors']))
    total_slots = int(data.get('total_slots', existing['total_slots']))
    hourly_rate = float(data.get('hourly_rate', existing['hourly_rate']))
    overstay_penalty_rate = float(data.get('overstay_penalty_rate', existing['overstay_penalty_rate']))
    default_hours = existing['operating_hours'] if 'operating_hours' in existing.keys() else '24/7 (Open Daily)'
    operating_hours = data.get('operating_hours', default_hours).strip() or '24/7 (Open Daily)'

    if not lot_name:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Parking Lot Name cannot be empty.'}), 400

    cursor.execute("""
        UPDATE parking_lots 
        SET lot_name = ?, location = ?, total_floors = ?, total_slots = ?, hourly_rate = ?, overstay_penalty_rate = ?, operating_hours = ?
        WHERE lot_id = ?
    """, (lot_name, location, total_floors, total_slots, hourly_rate, overstay_penalty_rate, operating_hours, lot_id))
    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Parking Lot '{lot_name}' updated successfully.",
        'lot': {
            'lot_id': lot_id,
            'lot_name': lot_name,
            'location': location,
            'total_floors': total_floors,
            'total_slots': total_slots,
            'hourly_rate': hourly_rate,
            'overstay_penalty_rate': overstay_penalty_rate
        }
    })

@lot_bp.route('/api/admin/lots/<int:lot_id>', methods=['DELETE'])
@admin_required
def delete_parking_lot(lot_id):
    """Admin endpoint to delete parking lot."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parking_lots WHERE lot_id = ?", (lot_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        return jsonify({'status': 'error', 'message': f'Parking lot #{lot_id} not found.'}), 404

    # Check if active reservations exist in this lot
    cursor.execute("""
        SELECT COUNT(*) as active_cnt 
        FROM reservations r 
        JOIN parking_slots s ON r.slot_id = s.slot_id 
        WHERE s.lot_id = ? AND r.status IN ('confirmed', 'checked_in', 'overstayed')
    """, (lot_id,))
    if cursor.fetchone()['active_cnt'] > 0:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Cannot delete parking lot with active reservations or parked vehicles.'}), 400

    cursor.execute("DELETE FROM parking_slots WHERE lot_id = ?", (lot_id,))
    cursor.execute("DELETE FROM parking_lots WHERE lot_id = ?", (lot_id,))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'message': f"Parking lot #{lot_id} deleted successfully."})

@lot_bp.route('/api/slots', methods=['GET'])
@lot_bp.route('/api/slots/all', methods=['GET'])
def get_slots():
    """Returns slots filtered by lot, floor, zone, slot_type, and status from MongoDB."""
    lot_id = request.args.get('lot_id')
    floor = request.args.get('floor', 'All')
    zone = request.args.get('zone', 'All')
    slot_type = request.args.get('slot_type', 'All')
    status = request.args.get('status', 'All').lower()
    search = request.args.get('search', '').strip()

    db = get_mongo_db()
    if db is not None:
        q = {}
        if lot_id and lot_id != 'All':
            try:
                q['lot_id'] = int(lot_id)
            except Exception:
                pass
        if floor and floor != 'All':
            q['floor'] = floor
        if zone and zone != 'All':
            q['zone'] = zone
        if slot_type and slot_type != 'All':
            q['slot_type'] = re.compile(f"^{re.escape(slot_type)}$", re.IGNORECASE)
        if status and status != 'all':
            q['status'] = re.compile(f"^{re.escape(status)}$", re.IGNORECASE)
        if search:
            q['$or'] = [
                {'slot_number': re.compile(re.escape(search), re.IGNORECASE)},
                {'current_plate': re.compile(re.escape(search), re.IGNORECASE)}
            ]
        raw_slots = list(db.parking_slots.find(q, {'_id': 0}).sort('slot_id', 1))
        
        lots_cache = {}
        for s in raw_slots:
            s['status'] = (s.get('status') or 'available').lower()
            lid = s.get('lot_id')
            if lid not in lots_cache:
                lots_cache[lid] = db.parking_lots.find_one({'lot_id': lid}, {'_id': 0}) or {}
            s['lot_name'] = lots_cache[lid].get('lot_name', 'Parking Facility')
            s['lot_location'] = lots_cache[lid].get('location', '')
            
            # Resolve vehicle_type for Car vs Bike/Scooter visual rendering
            vtype = s.get('vehicle_type')
            if not vtype and s.get('current_reservation_id'):
                res_doc = db.reservations.find_one({'reservation_id': s['current_reservation_id']}, {'vehicle_type': 1, '_id': 0})
                if res_doc and res_doc.get('vehicle_type'):
                    vtype = res_doc['vehicle_type']
            if not vtype and s.get('current_plate'):
                veh_doc = db.vehicles.find_one({'license_plate': s['current_plate']}, {'vehicle_type': 1, '_id': 0})
                if veh_doc and veh_doc.get('vehicle_type'):
                    vtype = veh_doc['vehicle_type']
            if not vtype:
                st_type = (s.get('slot_type') or '').lower()
                s_num = (s.get('slot_number') or '').upper()
                if any(w in st_type for w in ['bike', 'scooter', 'motorcycle', 'two-wheeler']) or (s_num.startswith('B') and s.get('lot_id') == 4):
                    vtype = 'Bike'
                else:
                    vtype = 'Car'
            s['vehicle_type'] = vtype
        return jsonify({
            'status': 'success',
            'floor': floor,
            'count': len(raw_slots),
            'slots': raw_slots
        })

    return jsonify({'status': 'error', 'message': 'MongoDB unavailable'}), 500

@lot_bp.route('/api/slots/<int:slot_id>', methods=['GET'])
def get_single_slot(slot_id):
    """Returns detailed single slot metadata from MongoDB."""
    db = get_mongo_db()
    if db is None:
        return jsonify({'status': 'error', 'message': 'MongoDB unavailable'}), 500
    slot = db.parking_slots.find_one({'slot_id': slot_id}, {'_id': 0})
    if not slot:
        return jsonify({'status': 'error', 'message': f'Slot #{slot_id} not found.'}), 404
    slot['status'] = (slot.get('status') or 'available').lower()
    lot = db.parking_lots.find_one({'lot_id': slot.get('lot_id')}, {'_id': 0}) or {}
    slot['lot_name'] = lot.get('lot_name', 'Parking Facility')
    slot['lot_location'] = lot.get('location', '')
    return jsonify({'status': 'success', 'slot': slot})

@lot_bp.route('/api/admin/slots/create', methods=['POST'])
@admin_required
def create_slot():
    """Admin endpoint to create a new parking slot with strict state validation."""
    data = request.get_json() or {}
    slot_number = data.get('slot_number', '').strip().upper()
    lot_id = data.get('lot_id', 1)
    floor = data.get('floor', 'Ground Floor').strip()
    zone = data.get('zone', 'Long Term Parking').strip()
    slot_type = data.get('slot_type', 'Standard').strip()
    status = data.get('status', 'available').strip().lower()
    dist_entry = int(data.get('distance_to_entry_m', 15))
    dist_elev = int(data.get('distance_to_elevator_m', 20))
    plate = data.get('current_plate', '').strip().upper() or None

    # Validation: Slot Number
    if not slot_number:
        return jsonify({'status': 'error', 'message': 'Slot Number is required.'}), 400

    # Validation: Status
    if status not in VALID_SLOT_STATUSES:
        return jsonify({'status': 'error', 'message': f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_SLOT_STATUSES))}."}), 400

    # Validation: Slot Type
    stype_clean = slot_type.strip().lower()
    if stype_clean not in VALID_SLOT_TYPES:
        return jsonify({'status': 'error', 'message': f"Invalid slot type '{slot_type}'. Must be one of: Regular (Standard), VIP, Accessible (Disabled), EV, Compact."}), 400
    if stype_clean in ('regular', 'standard'):
        slot_type_normalized = 'Regular'
    elif stype_clean in ('accessible', 'disabled'):
        slot_type_normalized = 'Accessible'
    elif stype_clean == 'ev':
        slot_type_normalized = 'EV'
    elif stype_clean == 'vip':
        slot_type_normalized = 'VIP'
    elif stype_clean == 'compact':
        slot_type_normalized = 'Compact'
    else:
        slot_type_normalized = slot_type.capitalize()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Validation: Lot ID exists
    cursor.execute("SELECT lot_id FROM parking_lots WHERE lot_id = ?", (lot_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'status': 'error', 'message': f"Parking Lot #{lot_id} does not exist."}), 400

    # Validation: Duplicate Slot Number
    cursor.execute("SELECT slot_id FROM parking_slots WHERE slot_number = ?", (slot_number,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'status': 'error', 'message': f"Slot number '{slot_number}' already exists."}), 400

    cursor.execute("""
        INSERT INTO parking_slots 
        (lot_id, slot_number, floor, zone, slot_type, distance_to_entry_m, distance_to_elevator_m, status, current_plate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (lot_id, slot_number, floor, zone, slot_type_normalized, dist_entry, dist_elev, status, plate))
    new_slot_id = cursor.lastrowid

    # Update total_slots in lot
    cursor.execute("UPDATE parking_lots SET total_slots = (SELECT COUNT(*) FROM parking_slots WHERE lot_id = ?) WHERE lot_id = ?", (lot_id, lot_id))

    # Log activity
    cursor.execute("""
        INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
        VALUES (?, 'Administrator', 'Slot Created', ?, 'info', ?)
    """, (slot_number, f"Created slot {slot_number} ({slot_type_normalized}, {floor})", datetime.now().strftime('%I:%M %p')))

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Slot {slot_number} created successfully.",
        'slot_id': new_slot_id,
        'slot': {
            'slot_id': new_slot_id,
            'slot_number': slot_number,
            'lot_id': lot_id,
            'floor': floor,
            'zone': zone,
            'slot_type': slot_type_normalized,
            'status': status
        }
    }), 201

@lot_bp.route('/api/admin/slots/update', methods=['POST'])
@lot_bp.route('/api/admin/slot/update', methods=['POST'])
@admin_required
def update_slot():
    """Admin endpoint to update slot properties or status with strict state validation."""
    data = request.get_json() or {}
    slot_id = data.get('slot_id')
    if not slot_id:
        return jsonify({'status': 'error', 'message': 'slot_id is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parking_slots WHERE slot_id = ?", (slot_id,))
    slot = cursor.fetchone()
    if not slot:
        conn.close()
        return jsonify({'status': 'error', 'message': f'Slot #{slot_id} not found.'}), 404

    new_status = data.get('status')
    new_slot_number = data.get('slot_number')
    slot_type = data.get('slot_type')
    floor = data.get('floor')
    zone = data.get('zone')
    plate = data.get('current_plate') or data.get('plate')
    lot_id = data.get('lot_id')

    updates = []
    params = []

    # Status validation
    if new_status is not None:
        st_clean = new_status.strip().lower()
        if st_clean not in VALID_SLOT_STATUSES:
            conn.close()
            return jsonify({'status': 'error', 'message': f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(VALID_SLOT_STATUSES))}."}), 400
        updates.append("status = ?")
        params.append(st_clean)

        # State transition rules
        if st_clean == 'available':
            updates.append("current_reservation_id = NULL, current_plate = NULL")
        elif st_clean in ('occupied', 'overstayed') and plate:
            updates.append("current_plate = ?")
            params.append(plate.strip().upper())

    # Slot type validation
    if slot_type is not None:
        stype_clean = slot_type.strip().lower()
        if stype_clean not in VALID_SLOT_TYPES:
            conn.close()
            return jsonify({'status': 'error', 'message': f"Invalid slot type '{slot_type}'. Must be one of: Regular (Standard), VIP, Accessible (Disabled), EV, Compact."}), 400
        if stype_clean in ('regular', 'standard'):
            stype_normalized = 'Regular'
        elif stype_clean in ('accessible', 'disabled'):
            stype_normalized = 'Accessible'
        elif stype_clean == 'ev':
            stype_normalized = 'EV'
        elif stype_clean == 'vip':
            stype_normalized = 'VIP'
        elif stype_clean == 'compact':
            stype_normalized = 'Compact'
        else:
            stype_normalized = slot_type.capitalize()
        updates.append("slot_type = ?")
        params.append(stype_normalized)

    # Slot number uniqueness
    if new_slot_number is not None:
        num_clean = new_slot_number.strip().upper()
        if not num_clean:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Slot number cannot be empty.'}), 400
        cursor.execute("SELECT slot_id FROM parking_slots WHERE slot_number = ? AND slot_id != ?", (num_clean, slot_id))
        if cursor.fetchone():
            conn.close()
            return jsonify({'status': 'error', 'message': f"Slot number '{num_clean}' already in use by another slot."}), 400
        updates.append("slot_number = ?")
        params.append(num_clean)

    if floor is not None:
        updates.append("floor = ?")
        params.append(floor.strip())
    if zone is not None:
        updates.append("zone = ?")
        params.append(zone.strip())
    if lot_id is not None:
        cursor.execute("SELECT lot_id FROM parking_lots WHERE lot_id = ?", (lot_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'status': 'error', 'message': f"Parking Lot #{lot_id} does not exist."}), 400
        updates.append("lot_id = ?")
        params.append(lot_id)

    if updates:
        params.append(slot_id)
        cursor.execute(f"UPDATE parking_slots SET {', '.join(updates)} WHERE slot_id = ?", params)
        conn.commit()

    # Fetch updated slot
    cursor.execute("SELECT s.*, l.lot_name FROM parking_slots s LEFT JOIN parking_lots l ON s.lot_id = l.lot_id WHERE s.slot_id = ?", (slot_id,))
    updated_slot = dict(cursor.fetchone())
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Slot {updated_slot['slot_number']} updated successfully.",
        'slot': updated_slot
    })

@lot_bp.route('/api/admin/slots/<int:slot_id>', methods=['DELETE'])
@admin_required
def delete_slot(slot_id):
    """Admin endpoint to delete a parking slot."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM parking_slots WHERE slot_id = ?", (slot_id,))
    slot = cursor.fetchone()
    if not slot:
        conn.close()
        return jsonify({'status': 'error', 'message': f'Slot #{slot_id} not found.'}), 404

    # Prevent deleting if occupied or has active reservation unless force
    force = request.args.get('force', '0') == '1'
    if slot['status'] in ('occupied', 'overstayed') and not force:
        conn.close()
        return jsonify({'status': 'error', 'message': f"Cannot delete slot '{slot['slot_number']}' because it is currently {slot['status']}."}), 400

    lot_id = slot['lot_id']
    cursor.execute("DELETE FROM reservations WHERE slot_id = ?", (slot_id,))
    cursor.execute("DELETE FROM parking_slots WHERE slot_id = ?", (slot_id,))
    # Update lot total_slots
    cursor.execute("UPDATE parking_lots SET total_slots = (SELECT COUNT(*) FROM parking_slots WHERE lot_id = ?) WHERE lot_id = ?", (lot_id, lot_id))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'message': f"Slot '{slot['slot_number']}' deleted successfully."})

@lot_bp.route('/api/slots/toggle-maintenance', methods=['POST'])
@admin_required
def toggle_slot_maintenance():
    """Toggles slot maintenance (disabled vs available)."""
    data = request.get_json() or {}
    slot_id = data.get('slot_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT slot_number, status FROM parking_slots WHERE slot_id = ?", (slot_id,))
    slot = cursor.fetchone()
    if not slot:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Slot not found'}), 404

    new_status = 'available' if slot['status'] == 'disabled' else 'disabled'
    cursor.execute("UPDATE parking_slots SET status = ? WHERE slot_id = ?", (new_status, slot_id))
    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'slot_id': slot_id,
        'new_status': new_status,
        'message': f"Slot {slot['slot_number']} is now {'Under Maintenance' if new_status == 'disabled' else 'Available'}."
    })

@lot_bp.route('/api/activity-logs', methods=['GET'])
def get_activity_logs():
    """Returns chronological recent activity feed."""
    limit = int(request.args.get('limit', 15))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM activity_logs 
        ORDER BY log_id DESC 
        LIMIT ?
    """, (limit,))
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'status': 'success', 'logs': logs})

# ==========================================
