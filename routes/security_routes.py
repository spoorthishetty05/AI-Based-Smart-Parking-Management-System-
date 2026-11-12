"""
Security Guard & Gate Management Routes for AI-Based Smart Parking System.
Provides live gate operations:
- Walk-in on-spot booking registration with automatic barrier gate opening
- On-spot booking termination & checkout with dwell time and overstay computation
- Real-time monitoring and filtering of all parking facility bookings
- Dynamic booking update (plate correction, slot relocation, duration extension)
- Manual gate barrier override
"""

from datetime import datetime, timedelta
import re

from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash

from core.database import get_mongo_db, get_next_sequence, clean_doc
from routes.middleware import security_required

security_bp = Blueprint('security', __name__)


# ======================================================================
# SECURITY GUARD WEB PORTAL
# ======================================================================

@security_bp.route('/security')
@security_bp.route('/security/dashboard')
@security_required
def security_dashboard():
    """Renders the dedicated Security Guard Gate Control Dashboard."""
    db = get_mongo_db()
    lots = list(db.parking_lots.find({}, {'_id': 0}).sort('lot_id', 1)) if db is not None else []
    for l in lots:
        l['name'] = l.get('name') or l.get('lot_name') or f"Lot #{l.get('lot_id', 1)}"
        l['lot_name'] = l['name']
    
    # Retrieve assigned guard metadata from MongoDB
    uid = session.get('user_id')
    guard_meta = {}
    if db is not None and uid:
        guard_user = db.users.find_one({'user_id': uid})
        if guard_user:
            guard_meta = {
                'gate': guard_user.get('gate', 'Gate 1 (Main Entry)'),
                'assigned_lot': guard_user.get('assigned_lot', 'Institutions'),
                'lot_id': guard_user.get('lot_id', 1),
                'shift': guard_user.get('shift', 'Day Shift (08:00 - 20:00)')
            }
            
    return render_template(
        'security_dashboard.html',
        current_user=session,
        guard_meta=guard_meta,
        lots=lots
    )


# ======================================================================
# LIVE GATE TELEMETRY & STATS
# ======================================================================

@security_bp.route('/api/security/stats', methods=['GET'])
@security_required
def get_security_stats():
    """Returns real-time gate telemetry: parked count, available slots, today's entries, overstays."""
    db = get_mongo_db()
    if db is None:
        return jsonify({'status': 'error', 'message': 'Database offline'}), 503

    today_str = datetime.now().strftime('%Y-%m-%d')
    lot_id_param = request.args.get('lot_id')

    slot_query = {}
    booking_query = {}
    if lot_id_param and lot_id_param != 'all':
        try:
            lid = int(lot_id_param)
            slot_query['lot_id'] = lid
            booking_query['lot_id'] = lid
        except (ValueError, TypeError):
            pass

    total_slots = db.parking_slots.count_documents(slot_query)
    vacant_slots = db.parking_slots.count_documents({**slot_query, 'status': 'available'})
    occupied_slots = db.parking_slots.count_documents({**slot_query, 'status': 'occupied'})
    overstay_slots = db.parking_slots.count_documents({**slot_query, 'status': 'overstayed'})

    # Active parked bookings
    active_bookings_count = db.bookings.count_documents({
        **booking_query,
        'status': {'$in': ['checked_in', 'active', 'parked', 'overstayed']}
    })

    # Today's entries
    today_entries = db.bookings.count_documents({
        **booking_query,
        '$or': [
            {'booking_date': today_str},
            {'created_at': {'$regex': f"^{today_str}"}},
            {'actual_entry_time': {'$regex': f"^{today_str}"}}
        ]
    })

    # Total overstay incidents
    overstay_count = max(overstay_slots, db.bookings.count_documents({
        **booking_query,
        'status': 'overstayed'
    }))

    return jsonify({
        'status': 'success',
        'stats': {
            'total_slots': total_slots,
            'vacant_slots': vacant_slots,
            'occupied_slots': occupied_slots,
            'currently_parked': max(occupied_slots, active_bookings_count),
            'today_entries': today_entries,
            'active_overstays': overstay_count
        }
    })


# ======================================================================
# VACANT SLOTS LOOKUP
# ======================================================================

@security_bp.route('/api/security/slots/available', methods=['GET'])
@security_required
def get_security_available_slots():
    """Returns available slots filtered by lot and optionally floor."""
    db = get_mongo_db()
    if db is None:
        return jsonify({'status': 'error', 'message': 'Database offline'}), 503

    query = {'status': 'available'}
    lot_id = request.args.get('lot_id')
    floor = request.args.get('floor')

    if lot_id and lot_id != 'all':
        try:
            query['lot_id'] = int(lot_id)
        except (ValueError, TypeError):
            pass

    if floor and floor != 'all':
        query['floor'] = floor

    slots = list(db.parking_slots.find(query, {'_id': 0}).sort([('lot_id', 1), ('slot_id', 1)]))
    return jsonify({
        'status': 'success',
        'slots': slots,
        'count': len(slots)
    })


# ======================================================================
# MASTER BOOKINGS QUERY & LIVE SEARCH
# ======================================================================

@security_bp.route('/api/security/bookings', methods=['GET'])
@security_required
def get_security_bookings():
    """
    Returns list of all facility bookings.
    Supports filtering by status ('all', 'checked_in', 'confirmed', 'overstayed', 'completed', 'cancelled')
    and live searching by plate number, booking ID, slot, driver name, or phone.
    """
    db = get_mongo_db()
    if db is None:
        return jsonify({'status': 'error', 'message': 'Database offline'}), 503

    status_filter = (request.args.get('status') or 'all').strip().lower()
    search = (request.args.get('search') or '').strip().lower()
    lot_id_param = request.args.get('lot_id')
    limit = int(request.args.get('limit', 150))

    query_parts = []

    if status_filter != 'all':
        if status_filter in ('active', 'parked', 'checked_in'):
            query_parts.append({'status': {'$in': ['checked_in', 'active', 'parked']}})
        elif status_filter == 'completed':
            query_parts.append({'status': {'$in': ['completed', 'completed_overstay']}})
        else:
            query_parts.append({'status': status_filter})

    if lot_id_param and lot_id_param != 'all':
        try:
            int_lot = int(lot_id_param)
            query_parts.append({'$or': [{'lot_id': int_lot}, {'lot_id': str(int_lot)}, {'place_id': lot_id_param}]})
        except (ValueError, TypeError):
            query_parts.append({'$or': [{'lot_id': lot_id_param}, {'place_id': lot_id_param}]})

    if search:
        search_escaped = re.escape(search)
        search_conditions = [
            {'license_plate': {'$regex': search_escaped, '$options': 'i'}},
            {'vehicle_plate': {'$regex': search_escaped, '$options': 'i'}},
            {'slot_number': {'$regex': search_escaped, '$options': 'i'}},
            {'booking_id': {'$regex': search_escaped, '$options': 'i'}},
            {'user_name': {'$regex': search_escaped, '$options': 'i'}},
            {'driver_name': {'$regex': search_escaped, '$options': 'i'}},
            {'phone': {'$regex': search_escaped, '$options': 'i'}}
        ]
        if search.isdigit():
            search_conditions.append({'booking_id': int(search)})
            search_conditions.append({'slot_id': int(search)})
        query_parts.append({'$or': search_conditions})

    query = {'$and': query_parts} if query_parts else {}

    raw_bookings = list(db.bookings.find(query).sort([('created_at', -1), ('booking_id', -1)]).limit(limit))

    # Clean docs and standardize fields for frontend consumption
    bookings = []
    for b in raw_bookings:
        cb = clean_doc(b)
        # Ensure uniform field names
        cb['plate'] = cb.get('license_plate') or cb.get('vehicle_plate') or '—'
        cb['driver'] = cb.get('user_name') or cb.get('driver_name') or 'Driver'
        cb['slot'] = cb.get('slot_number') or f"Slot {cb.get('slot_id', '—')}"
        cb['entry_time'] = cb.get('actual_entry_time') or cb.get('start_time') or '—'
        cb['exit_time'] = cb.get('actual_exit_time') or cb.get('end_time') or '—'
        cb['is_on_spot'] = bool(cb.get('is_on_spot') or cb.get('booking_type') == 'spot_walkin')
        bookings.append(cb)

    return jsonify({
        'status': 'success',
        'bookings': bookings,
        'count': len(bookings)
    })


# ======================================================================
# ON-SPOT WALK-IN BOOKING (GATE ENTRY)
# ======================================================================

@security_bp.route('/api/security/spot-booking', methods=['POST'])
@security_required
def api_security_spot_booking():
    """
    Registers an on-spot walk-in vehicle arrival at the gate:
    1. Validates vehicle license plate and vehicle type.
    2. Selects or auto-assigns an available slot in the selected lot.
    3. Sets slot status = 'occupied' and locks current plate.
    4. Creates active booking with status = 'checked_in' and actual_entry_time = now.
    5. Returns successful response with barrier gate open signal.
    """
    data = request.get_json() or {}
    license_plate = str(data.get('license_plate') or data.get('vehicle_plate') or '').strip().upper()
    vehicle_type = str(data.get('vehicle_type') or 'Car').strip()
    driver_name = str(data.get('driver_name') or 'Walk-in Guest Driver').strip()
    driver_phone = str(data.get('driver_phone') or '—').strip()
    notes = str(data.get('notes') or '').strip()

    if not license_plate:
        return jsonify({'status': 'error', 'message': 'Vehicle License Plate number is required.'}), 400

    try:
        duration_hours = float(data.get('duration_hours', 2))
        if duration_hours <= 0:
            duration_hours = 2.0
    except (ValueError, TypeError):
        duration_hours = 2.0

    try:
        lot_id = int(data.get('lot_id', 1))
    except (ValueError, TypeError):
        lot_id = 1

    db = get_mongo_db()
    if db is None:
        return jsonify({'status': 'error', 'message': 'Database offline'}), 503

    # Find lot information
    lot = db.parking_lots.find_one({'lot_id': lot_id})
    lot_name = (lot.get('lot_name') or lot.get('name', 'Main Facility')) if lot else 'Main Facility'
    hourly_rate = float(lot.get('hourly_rate', 40)) if lot else 40.0
    total_amount = round(hourly_rate * duration_hours, 2)

    # Determine Slot: specific or auto-assign available
    target_slot_id = data.get('slot_id')
    slot = None
    if target_slot_id:
        try:
            slot = db.parking_slots.find_one({'slot_id': int(target_slot_id), 'lot_id': lot_id})
            if not slot or slot.get('status') != 'available':
                return jsonify({'status': 'error', 'message': f"Selected slot #{target_slot_id} is no longer available. Please choose another."}), 409
        except (ValueError, TypeError):
            slot = None

    if not slot:
        # Auto-assign first available slot in lot
        slot = db.parking_slots.find_one({'lot_id': lot_id, 'status': 'available'})
        if not slot:
            # Check if any other facility has an available slot
            slot = db.parking_slots.find_one({'status': 'available'})
            if not slot:
                return jsonify({'status': 'error', 'message': f"Facility '{lot_name}' is currently at 100% capacity. No vacant slots available."}), 409
            lot_id = int(slot['lot_id'])
            lot = db.parking_lots.find_one({'lot_id': lot_id})
            lot_name = (lot.get('lot_name') or lot.get('name', 'Main Facility')) if lot else 'Main Facility'

    slot_id = int(slot['slot_id'])
    slot_number = slot.get('slot_number', f"S{slot_id}")
    floor = slot.get('floor', 'Ground Floor')
    zone = slot.get('zone', 'General')

    # Calculate timings
    now_dt = datetime.now()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_dt = now_dt + timedelta(hours=duration_hours)
    end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    today_str = now_dt.strftime('%Y-%m-%d')

    # Sequential Booking ID (unique across both bookings and reservations)
    while True:
        new_bid = get_next_sequence('bookings')
        if not db.bookings.find_one({'booking_id': new_bid}) and not db.reservations.find_one({'reservation_id': new_bid}):
            break
    db.counters.update_one({'_id': 'reservations'}, {'$max': {'seq': int(new_bid)}}, upsert=True)
    guard_name = session.get('user_name', 'Security Officer')

    booking_doc = {
        'booking_id': new_bid,
        'user_id': session.get('user_id', 1),
        'user_name': driver_name,
        'phone': driver_phone,
        'email': 'onspot@smartparking.ai',
        'lot_id': lot_id,
        'lot_name': lot_name,
        'slot_id': slot_id,
        'slot_number': slot_number,
        'floor': floor,
        'zone': zone,
        'license_plate': license_plate,
        'vehicle_plate': license_plate,
        'vehicle_type': vehicle_type,
        'booking_date': today_str,
        'start_time': now_dt.strftime('%H:%M'),
        'end_time': end_dt.strftime('%H:%M'),
        'duration_hours': duration_hours,
        'duration_str': f"{int(duration_hours)} Hours" if duration_hours.is_integer() else f"{duration_hours} Hours",
        'actual_entry_time': now_str,
        'actual_exit_time': None,
        'status': 'checked_in',
        'booking_type': 'spot_walkin',
        'payment_status': 'paid_on_spot',
        'total_amount': total_amount,
        'hourly_rate': hourly_rate,
        'is_on_spot': True,
        'created_by_guard': guard_name,
        'notes': notes,
        'created_at': now_str
    }

    # Save to bookings and reservations collections
    db.bookings.insert_one(booking_doc)
    
    # Dual compatibility insertion
    res_doc = dict(booking_doc)
    res_doc['reservation_id'] = new_bid
    try:
        db.reservations.insert_one(res_doc)
    except Exception:
        pass

    # Update slot state to OCCUPIED
    db.parking_slots.update_one(
        {'slot_id': slot_id},
        {'$set': {
            'status': 'occupied',
            'current_plate': license_plate,
            'current_reservation_id': new_bid
        }}
    )

    # Activity log
    try:
        db.activity_logs.insert_one({
            'activity_id': get_next_sequence('activity_logs'),
            'user_id': session.get('user_id'),
            'action': 'SPOT_BOOKING_CREATED',
            'details': f"Guard {guard_name} registered spot arrival for {license_plate} at {slot_number} ({lot_name})",
            'timestamp': now_str
        })
    except Exception:
        pass

    return jsonify({
        'status': 'success',
        'message': f"Spot booking registered for {license_plate}. Barrier gate opened.",
        'barrier_opened': True,
        'booking': {
            'booking_id': new_bid,
            'plate': license_plate,
            'slot_number': slot_number,
            'lot_name': lot_name,
            'floor': floor,
            'entry_time': now_str,
            'valid_until': end_str,
            'total_amount': total_amount
        }
    }), 201


# ======================================================================
# ON-SPOT TERMINATION & CHECKOUT (GATE EXIT)
# ======================================================================

@security_bp.route('/api/security/bookings/<booking_id>/terminate', methods=['POST'])
@security_required
def api_security_terminate_booking(booking_id):
    """
    Terminates / checks out any booking at the gate:
    1. Computes actual dwell time and overstay penalties if applicable.
    2. Marks booking status = 'completed' (or 'completed_overstay').
    3. Frees the slot: sets status = 'available', clears plate and reservation pointer.
    4. Settle overstay radar records if any.
    5. Returns success with exit barrier gate open signal.
    """
    db = get_mongo_db()
    if db is None:
        return jsonify({'status': 'error', 'message': 'Database offline'}), 503

    bid_str = str(booking_id).strip()
    bid_int = int(bid_str) if bid_str.isdigit() else None

    # Find booking in bookings collection
    b = db.bookings.find_one({'$or': [{'booking_id': bid_str}, {'booking_id': bid_int}]})
    if not b:
        b = db.reservations.find_one({'$or': [{'booking_id': bid_str}, {'reservation_id': bid_int}]})
    if not b:
        return jsonify({'status': 'error', 'message': f"Booking '#{booking_id}' not found."}), 404

    curr_st = (b.get('status') or '').lower()
    if curr_st in ('completed', 'completed_overstay', 'cancelled'):
        return jsonify({'status': 'error', 'message': f"Booking '#{booking_id}' is already closed ({curr_st})."}), 400

    now_dt = datetime.now()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')

    # Dwell Time calculation
    entry_raw = b.get('actual_entry_time')
    if entry_raw:
        try:
            entry_dt = datetime.strptime(entry_raw, '%Y-%m-%d %H:%M:%S')
        except Exception:
            try:
                entry_dt = datetime.strptime(entry_raw, '%Y-%m-%d %H:%M')
            except Exception:
                entry_dt = now_dt - timedelta(minutes=30)
    else:
        entry_dt = now_dt - timedelta(minutes=30)

    dwell_seconds = max(60, (now_dt - entry_dt).total_seconds())
    dwell_minutes = int(dwell_seconds // 60)
    dwell_hours = round(dwell_minutes / 60, 1)

    # Overstay penalty calculation
    overstay_minutes = 0
    overstay_penalty = 0.0
    end_raw = b.get('end_time')
    b_date = b.get('booking_date') or now_dt.strftime('%Y-%m-%d')

    if end_raw:
        try:
            if len(end_raw) == 5:
                scheduled_end_dt = datetime.strptime(f"{b_date} {end_raw}", '%Y-%m-%d %H:%M')
            else:
                scheduled_end_dt = datetime.strptime(end_raw, '%Y-%m-%d %H:%M:%S')
            
            # 15 minutes grace period
            grace_dt = scheduled_end_dt + timedelta(minutes=15)
            if now_dt > grace_dt:
                overstay_minutes = int((now_dt - scheduled_end_dt).total_seconds() // 60)
                # Overstay penalty rate: Rs. 100 per hour or lot overstay rate
                lot = db.parking_lots.find_one({'lot_id': b.get('lot_id', 1)})
                pen_rate = float(lot.get('overstay_penalty_rate', 100)) if lot else 100.0
                overstay_penalty = round((overstay_minutes / 60.0) * pen_rate, 2)
        except Exception:
            pass

    final_status = 'completed_overstay' if overstay_penalty > 0 else 'completed'
    guard_name = session.get('user_name', 'Security Officer')

    # Update booking
    updates = {
        'status': final_status,
        'actual_exit_time': now_str,
        'dwell_time_minutes': dwell_minutes,
        'dwell_time_hours': dwell_hours,
        'overstay_minutes': overstay_minutes,
        'overstay_penalty': overstay_penalty,
        'terminated_by_guard': guard_name,
        'terminated_at': now_str
    }

    db.bookings.update_one({'_id': b['_id']}, {'$set': updates})
    try:
        db.reservations.update_one(
            {'$or': [
                {'reservation_id': b.get('reservation_id')},
                {'reservation_id': b.get('booking_id')},
                {'booking_id': b.get('booking_id')}
            ]},
            {'$set': updates}
        )
    except Exception:
        pass

    # Free the Slot!
    slot_id = b.get('slot_id')
    if slot_id:
        try:
            db.parking_slots.update_one(
                {'slot_id': int(slot_id)},
                {'$set': {
                    'status': 'available',
                    'current_plate': None,
                    'current_reservation_id': None
                }}
            )
        except Exception:
            pass

    # Resolve any pending overstay record
    try:
        db.overstay_records.update_many(
            {'$or': [{'booking_id': b.get('booking_id')}, {'slot_id': slot_id}]},
            {'$set': {'status': 'resolved', 'resolved_at': now_str, 'resolved_by': guard_name}}
        )
    except Exception:
        pass

    # Activity log
    try:
        db.activity_logs.insert_one({
            'activity_id': get_next_sequence('activity_logs'),
            'user_id': session.get('user_id'),
            'action': 'BOOKING_TERMINATED_AT_GATE',
            'details': f"Guard {guard_name} checked out {b.get('license_plate', 'vehicle')} at gate. Dwell: {dwell_minutes}m, Overstay Fee: ₹{overstay_penalty}",
            'timestamp': now_str
        })
    except Exception:
        pass

    plate = b.get('license_plate') or b.get('vehicle_plate') or 'Vehicle'
    return jsonify({
        'status': 'success',
        'message': f"Booking for {plate} checked out successfully. Exit barrier gate opened.",
        'barrier_opened': True,
        'summary': {
            'booking_id': b.get('booking_id'),
            'plate': plate,
            'slot_number': b.get('slot_number'),
            'dwell_time_minutes': dwell_minutes,
            'dwell_time_hours': dwell_hours,
            'overstay_minutes': overstay_minutes,
            'overstay_penalty': overstay_penalty,
            'exit_time': now_str
        }
    })


# ======================================================================
# UPDATE BOOKING (PLATE, SLOT RELOCATION, EXTENSION)
# ======================================================================

@security_bp.route('/api/security/bookings/<booking_id>/update', methods=['POST'])
@security_required
def api_security_update_booking(booking_id):
    """
    Updates booking attributes by security guard:
    - License plate correction
    - Slot relocation (moves vehicle from slot A to slot B atomically)
    - Duration extension
    - Driver details & notes
    """
    db = get_mongo_db()
    if db is None:
        return jsonify({'status': 'error', 'message': 'Database offline'}), 503

    bid_str = str(booking_id).strip()
    bid_int = int(bid_str) if bid_str.isdigit() else None

    b = db.bookings.find_one({'$or': [{'booking_id': bid_str}, {'booking_id': bid_int}]})
    if not b:
        return jsonify({'status': 'error', 'message': f"Booking '#{booking_id}' not found."}), 404

    data = request.get_json() or {}
    guard_name = session.get('user_name', 'Security Officer')
    updates = {}
    activity_details = []

    # 1. License Plate Update
    new_plate = data.get('license_plate') or data.get('plate')
    if new_plate:
        new_plate = str(new_plate).strip().upper()
        if new_plate != b.get('license_plate'):
            updates['license_plate'] = new_plate
            updates['vehicle_plate'] = new_plate
            activity_details.append(f"plate updated to {new_plate}")
            # If vehicle is currently parked, update slot plate as well
            if b.get('status') in ('checked_in', 'occupied', 'parked'):
                db.parking_slots.update_one(
                    {'slot_id': b.get('slot_id')},
                    {'$set': {'current_plate': new_plate}}
                )

    # 2. Driver Info Update
    if 'driver_name' in data:
        updates['user_name'] = str(data['driver_name']).strip()
    if 'driver_phone' in data:
        updates['phone'] = str(data['driver_phone']).strip()
    if 'vehicle_type' in data:
        updates['vehicle_type'] = str(data['vehicle_type']).strip()
    if 'notes' in data:
        updates['notes'] = str(data['notes']).strip()

    # 3. Slot Relocation
    new_slot_id = data.get('new_slot_id')
    if new_slot_id and int(new_slot_id) != b.get('slot_id'):
        new_sid = int(new_slot_id)
        target_slot = db.parking_slots.find_one({'slot_id': new_sid})
        if not target_slot:
            return jsonify({'status': 'error', 'message': f"Slot #{new_sid} does not exist."}), 404
        if target_slot.get('status') != 'available':
            return jsonify({'status': 'error', 'message': f"Target slot {target_slot.get('slot_number', new_sid)} is currently {target_slot.get('status')}. Cannot relocate."}), 409

        old_sid = b.get('slot_id')
        new_snum = target_slot.get('slot_number', f"S{new_sid}")

        # Free old slot
        if old_sid:
            db.parking_slots.update_one(
                {'slot_id': old_sid},
                {'$set': {'status': 'available', 'current_plate': None, 'current_reservation_id': None}}
            )

        # Occupy new slot if booking is currently checked in
        if b.get('status') in ('checked_in', 'occupied', 'parked'):
            db.parking_slots.update_one(
                {'slot_id': new_sid},
                {'$set': {
                    'status': 'occupied',
                    'current_plate': updates.get('license_plate', b.get('license_plate')),
                    'current_reservation_id': b.get('booking_id')
                }}
            )

        updates['slot_id'] = new_sid
        updates['slot_number'] = new_snum
        updates['floor'] = target_slot.get('floor', 'Ground Floor')
        updates['zone'] = target_slot.get('zone', 'General')
        activity_details.append(f"relocated from {b.get('slot_number')} to {new_snum}")

    # 4. Duration Extension
    extend_hours = data.get('extend_hours')
    if extend_hours:
        try:
            ext_h = float(extend_hours)
            if ext_h > 0:
                old_end = b.get('end_time', '12:00')
                b_date = b.get('booking_date', datetime.now().strftime('%Y-%m-%d'))
                try:
                    if len(old_end) == 5:
                        old_end_dt = datetime.strptime(f"{b_date} {old_end}", '%Y-%m-%d %H:%M')
                    else:
                        old_end_dt = datetime.strptime(old_end, '%Y-%m-%d %H:%M:%S')
                    new_end_dt = old_end_dt + timedelta(hours=ext_h)
                    updates['end_time'] = new_end_dt.strftime('%H:%M')
                    updates['duration_hours'] = round(float(b.get('duration_hours', 2)) + ext_h, 1)
                    updates['duration_str'] = f"{updates['duration_hours']} Hours"
                    
                    # Update charge
                    lot = db.parking_lots.find_one({'lot_id': b.get('lot_id', 1)})
                    rate = float(lot.get('hourly_rate', 40)) if lot else 40.0
                    updates['total_amount'] = round(float(b.get('total_amount', 0)) + (rate * ext_h), 2)
                    activity_details.append(f"extended by {ext_h} hours (new end: {updates['end_time']})")
                except Exception:
                    pass
        except (ValueError, TypeError):
            pass

    if updates:
        updates['last_modified_by_guard'] = guard_name
        updates['last_modified_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.bookings.update_one({'_id': b['_id']}, {'$set': updates})
        try:
            db.reservations.update_one(
            {'$or': [
                {'reservation_id': b.get('reservation_id')},
                {'reservation_id': b.get('booking_id')},
                {'booking_id': b.get('booking_id')}
            ]},
            {'$set': updates}
        )
        except Exception:
            pass

        # Activity log
        try:
            db.activity_logs.insert_one({
                'activity_id': get_next_sequence('activity_logs'),
                'user_id': session.get('user_id'),
                'action': 'BOOKING_UPDATED_BY_GUARD',
                'details': f"Guard {guard_name} updated booking #{booking_id}: {', '.join(activity_details)}",
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        except Exception:
            pass

    return jsonify({
        'status': 'success',
        'message': f"Booking #{booking_id} updated successfully.",
        'updates': updates
    })


# ======================================================================
# MANUAL GATE BARRIER OVERRIDE
# ======================================================================

@security_bp.route('/api/security/gate/barrier', methods=['POST'])
@security_required
def api_security_barrier_control():
    """Manual emergency open / close signal for barrier gates."""
    data = request.get_json() or {}
    action = (data.get('action') or 'open').strip().lower()
    gate_name = data.get('gate_name') or 'Gate 1 (North Entry)'
    reason = data.get('reason') or 'Manual security officer override'

    guard_name = session.get('user_name', 'Security Officer')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    db = get_mongo_db()
    if db is not None:
        try:
            db.activity_logs.insert_one({
                'activity_id': get_next_sequence('activity_logs'),
                'user_id': session.get('user_id'),
                'action': f"GATE_BARRIER_{action.upper()}",
                'details': f"Guard {guard_name} triggered barrier {action.upper()} at {gate_name}. Reason: {reason}",
                'timestamp': now_str
            })
        except Exception:
            pass

    return jsonify({
        'status': 'success',
        'action': action,
        'gate_name': gate_name,
        'barrier_state': 'OPENED' if action == 'open' else 'CLOSED',
        'triggered_by': guard_name,
        'timestamp': now_str,
        'message': f"Barrier gate at {gate_name} successfully {action}ed."
    })
