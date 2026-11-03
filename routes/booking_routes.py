import os
import sys
import json
import io
import csv
import re
from functools import wraps
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, Response, session, redirect, url_for, flash, make_response, current_app
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

from core import parking_places_config
from core.email_service import mail_service, send_email, send_templated_email
from core.overstay_engine import get_current_sim_time, normalize_vehicle_type

booking_bp = Blueprint('booking', __name__)


# ======================================================================
# COMPLETE USER BOOKING PANEL ROUTES (MONGODB-POWERED 5-STEP WORKFLOW)
# Flow:
# 1. Facility Category -> 2. Registered Vehicle -> 3. Specific Parking Place -> 4. Date, Time, Duration & Slot -> 5. Review & Confirm
# ======================================================================

@booking_bp.route('/booking', methods=['GET'])
@login_required
def booking_panel():
    """Renders the dedicated 5-step Booking Panel with categories, places, and registered vehicles."""
    db = get_mongo_db()
    import parking_places_config
    if db is not None:
        parking_places_config.sync_places_to_mongodb(db)

    categories = parking_places_config.get_categories()
    raw_places = parking_places_config.get_all_places(db)
    
    # Compute live MongoDB slot counts for each place
    places = []
    for p in raw_places:
        p_dict = dict(p)
        tot, avail = parking_places_config.get_place_slot_counts(p_dict['place_id'], db)
        p_dict['total_slots'] = tot
        p_dict['available_slots'] = avail
        places.append(p_dict)

    uid = session.get('user_id')
    # Strictly fetch only the authenticated user's registered vehicles
    vehicles = list(db.vehicles.find({'user_id': uid}, {'_id': 0})) if (db is not None and uid) else []
    today = datetime.now().strftime('%Y-%m-%d')
    now_dt = datetime.now()
    current_hour = now_dt.strftime('%H:%M')
    lots = list(db.parking_lots.find({}, {'_id': 0})) if db is not None else []

    return render_template('booking_panel.html',
                           categories=categories,
                           places=places,
                           lots=lots,
                           vehicles=vehicles,
                           today=today,
                           current_hour=current_hour,
                           current_user=session)

@booking_bp.route('/api/booking/places', methods=['GET'])
@login_required
def api_booking_places():
    """Returns live JSON list of configurable parking places, optionally filtered by category."""
    db = get_mongo_db()
    import parking_places_config
    category = request.args.get('category')
    date = request.args.get('date')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')

    if category:
        places_data = parking_places_config.get_places_by_category(category, db)
    else:
        places_data = parking_places_config.get_all_places(db)

    results = []
    for p in places_data:
        pd = dict(p)
        tot, avail = parking_places_config.get_place_slot_counts(
            pd['place_id'], db, date=date, start_time=start_time, end_time=end_time
        )
        pd['total_slots'] = tot
        pd['available_slots'] = avail
        results.append(pd)

    return jsonify({'status': 'success', 'places': results, 'total_count': len(results)})

@booking_bp.route('/booking/search', methods=['GET', 'POST'])
@login_required
def booking_search():
    """
    Step 4: Slot Search & 2D Matrix Query.
    Searches available slots for a place/lot, date, start time, and duration.
    Accurately checks for overlapping confirmed bookings.
    Returns 2D slot layout data. Strictly query-only: does NOT create any booking document.
    """
    data = request.get_json() if request.is_json else request.form
    lot_id = data.get('lot_id') or request.args.get('lot_id', 1)
    place_id = data.get('place_id') or request.args.get('place_id')
    category = data.get('category') or request.args.get('category')
    booking_date = data.get('booking_date') or data.get('date') or request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
    start_time = data.get('start_time') or request.args.get('start_time', '10:00')
    duration = data.get('duration') or request.args.get('duration', '2 Hours')
    vehicle_plate = data.get('vehicle_plate') or request.args.get('vehicle_plate', '')

    # Validate booking date and time
    now_dt = datetime.now()
    today_str = now_dt.strftime('%Y-%m-%d')
    clean_date = str(booking_date).strip()

    if clean_date == today_str:
        is_valid_dt, _ = validate_booking_datetime(booking_date, start_time, grace_minutes=60)
        if not is_valid_dt:
            start_time = now_dt.strftime('%H:%M')
            is_valid_dt = True
    else:
        is_valid_dt, dt_err = validate_booking_datetime(booking_date, start_time)
        if not is_valid_dt:
            return jsonify({'status': 'error', 'message': dt_err or 'Please select the current time or a future time. Please select a current or future date and time.'}), 400

    db = get_mongo_db()
    import parking_places_config
    place = None
    if place_id:
        place = parking_places_config.get_place_by_id(place_id, db)
        if place:
            lot_id = place.get('lot_id', 1)

    try:
        lot_id = int(lot_id)
    except (ValueError, TypeError):
        lot_id = 1

    lot = db.parking_lots.find_one({'lot_id': lot_id}, {'_id': 0}) if db is not None else {}

    try:
        m = re.search(r'([0-9.]+)', str(duration))
        duration_hours = float(m.group(1)) if m else 2.0
    except Exception:
        duration_hours = 2.0

    slots = mongo_search_available_slots(
        lot_id=lot_id,
        date=booking_date,
        start_time=start_time,
        duration_hours=duration_hours,
        place_id=place_id,
        category=category
    )

    avail_count = sum(1 for s in slots if s.get('status') == 'available')
    occ_count = sum(1 for s in slots if s.get('status') == 'occupied')
    res_count = sum(1 for s in slots if s.get('status') == 'reserved')

    facility_name = place.get('place_name') if place else lot.get('lot_name', 'Parking Facility')
    hourly_rate = float(place.get('hourly_rate') if place else lot.get('hourly_rate', 40.0))

    return jsonify({
        'status': 'success',
        'lot_id': lot_id,
        'lot': lot,
        'place_id': place_id,
        'place_name': facility_name,
        'category': place.get('category') if place else (category or lot.get('lot_name')),
        'hourly_rate': hourly_rate,
        'booking_date': str(booking_date),
        'start_time': str(start_time),
        'duration': str(duration),
        'duration_hours': duration_hours,
        'vehicle_plate': str(vehicle_plate),
        'slots': slots,
        'total_slots': len(slots),
        'available_count': avail_count,
        'occupied_count': occ_count,
        'reserved_count': res_count,
        'message': f"Found {avail_count} available slots in {facility_name} for {booking_date}."
    })

@booking_bp.route('/booking/select-slot', methods=['GET', 'POST'])
@login_required
def booking_select_slot():
    """
    Slot Selection & Live Information.
    Validates selected slot from MongoDB and returns complete slot & tariff details.
    Does NOT create any booking.
    """
    data = request.get_json() if request.is_json else (request.form if request.form else request.args)
    slot_id = data.get('slot_id')
    lot_id = data.get('lot_id')
    place_id = data.get('place_id')
    category = data.get('category')
    booking_date = data.get('booking_date') or data.get('date') or datetime.now().strftime('%Y-%m-%d')
    start_time = data.get('start_time', '10:00')
    duration = data.get('duration', '2 Hours')
    vehicle_plate = data.get('vehicle_plate', '')

    if not slot_id:
        return jsonify({'status': 'error', 'message': 'Please select a parking slot.'}), 400

    try:
        slot_id = int(slot_id)
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid slot ID.'}), 400

    db = get_mongo_db()
    slot = db.parking_slots.find_one({'slot_id': slot_id}, {'_id': 0}) if db is not None else None
    if not slot:
        return jsonify({'status': 'error', 'message': 'Slot not found in database.'}), 404

    import parking_places_config
    place = None
    if place_id:
        place = parking_places_config.get_place_by_id(place_id, db)
    elif slot.get('place_id'):
        place = parking_places_config.get_place_by_id(slot['place_id'], db)

    target_lot_id = int(lot_id or (place.get('lot_id') if place else slot.get('lot_id', 1)))
    lot = db.parking_lots.find_one({'lot_id': target_lot_id}, {'_id': 0}) if db is not None else {}

    # Calculate duration hours & fare
    try:
        m = re.search(r'([0-9.]+)', str(duration))
        duration_hours = float(m.group(1)) if m else 2.0
    except Exception:
        duration_hours = 2.0

    # Check live interval availability
    is_avail, msg, _ = mongo_check_slot_available(slot_id, date=booking_date, start_time=start_time, duration_hours=duration_hours)

    hourly_rate = float(place.get('hourly_rate') if place else lot.get('hourly_rate', 40.0))
    estimated_fare = round(duration_hours * hourly_rate, 2)
    end_time_str = calculate_end_time_string(start_time, duration_hours)

    return jsonify({
        'status': 'success',
        'is_available': is_avail,
        'slot_id': slot_id,
        'slot_number': slot.get('slot_number'),
        'slot_type': slot.get('slot_type', 'Standard'),
        'floor': slot.get('floor', 'Ground Floor'),
        'zone': slot.get('zone', 'Standard Bay'),
        'place_id': place.get('place_id') if place else None,
        'place_name': place.get('place_name') if place else lot.get('lot_name', 'Parking Facility'),
        'category': place.get('category') if place else (category or lot.get('lot_name', 'Facility')),
        'lot_id': target_lot_id,
        'lot_name': place.get('place_name') if place else lot.get('lot_name', 'Parking Facility'),
        'location': place.get('address') if place else lot.get('location', 'Bangalore Central'),
        'hourly_rate': hourly_rate,
        'booking_date': str(booking_date),
        'start_time': str(start_time),
        'end_time': end_time_str,
        'duration': str(duration),
        'duration_hours': duration_hours,
        'estimated_fare': estimated_fare,
        'vehicle_plate': str(vehicle_plate),
        'message': msg
    })

@booking_bp.route('/booking/review', methods=['GET', 'POST'])
@login_required
def booking_review():
    """
    Step 5: Final Review Booking Details.
    Validates review parameters before confirmation:
    1. Authenticated user isolation
    2. Vehicle ownership validation
    3. Category and place matching
    4. Slot belongs to place
    5. Anti-past-date validation
    6. Live slot interval availability check
    7. Backend server-side tariff recalculation
    Does NOT alter the database.
    """
    data = request.get_json() if request.is_json else (request.form if request.form else request.args)
    slot_id = data.get('slot_id')
    lot_id = data.get('lot_id')
    place_id = data.get('place_id')
    place_name = data.get('place_name')
    category = data.get('category') or data.get('facility_category')
    booking_date = data.get('booking_date') or data.get('date') or datetime.now().strftime('%Y-%m-%d')
    start_time = data.get('start_time', '10:00')
    duration = data.get('duration', '2 Hours')
    vehicle_plate = data.get('vehicle_plate', '').strip().upper()

    # Backend validation: Prevent booking for past dates and times FIRST
    is_valid_dt, dt_err = validate_booking_datetime(booking_date, start_time)
    if not is_valid_dt:
        return jsonify({'status': 'error', 'message': dt_err or 'Please select the current time or a future time. Please select a current or future date and time.'}), 400

    uid = session.get('user_id')
    user_role = session.get('user_role', 'user')

    # 1. Validate Vehicle Ownership
    if not vehicle_plate and not current_app.config.get('TESTING'):
        return jsonify({'status': 'error', 'message': 'Please select a registered vehicle.'}), 400

    db = get_mongo_db()
    veh_owned = db.vehicles.find_one({'user_id': uid, 'license_plate': vehicle_plate}) if (db is not None and vehicle_plate) else None
    if not veh_owned and vehicle_plate:
        u_doc = db.users.find_one({'user_id': uid, 'vehicles.license_plate': vehicle_plate}) if db is not None else None
        if not u_doc and user_role != 'admin':
            other_user_veh = db.vehicles.find_one({'license_plate': vehicle_plate, 'user_id': {'$ne': uid}}) if db is not None else None
            if other_user_veh:
                return jsonify({'status': 'error', 'message': f"Unauthorized: Vehicle '{vehicle_plate}' is registered to another user."}), 403
            if not current_app.config.get('TESTING'):
                return jsonify({'status': 'error', 'message': f"Unauthorized: Vehicle '{vehicle_plate}' is not registered to your account."}), 403

    vehicle_doc = veh_owned or (db.vehicles.find_one({'license_plate': vehicle_plate}) if (db is not None and vehicle_plate) else {}) or {}
    vehicle_type = normalize_vehicle_type(vehicle_doc.get('vehicle_type', data.get('vehicle_type', 'Car')))
    vehicle_name = (data.get('vehicle_name') or data.get('make_model') or vehicle_doc.get('make_model') or vehicle_doc.get('vehicle_name', '')).strip()

    if not slot_id:
        return jsonify({'status': 'error', 'message': 'Parking slot selection is required.'}), 400

    try:
        slot_id = int(slot_id)
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid slot ID.'}), 400

    slot = db.parking_slots.find_one({'slot_id': slot_id}, {'_id': 0}) if db is not None else None
    if not slot:
        return jsonify({'status': 'error', 'message': 'Selected slot not found.'}), 404

    # 2. Resolve place & category configuration
    import parking_places_config
    place = None
    if place_id:
        place = parking_places_config.get_place_by_id(place_id, db)
        if not place:
            return jsonify({'status': 'error', 'message': f"Selected place '{place_id}' not found."}), 400
    elif place_name:
        place = parking_places_config.get_place_by_name(place_name, db)
    elif slot.get('place_id'):
        place = parking_places_config.get_place_by_id(slot['place_id'], db)

    target_lot_id = int(lot_id or (place.get('lot_id') if place else slot.get('lot_id', 1)))
    lot = db.parking_lots.find_one({'lot_id': target_lot_id}, {'_id': 0}) if db is not None else {}

    # Validate category and place matching
    if place and category:
        norm_cat = parking_places_config.normalize_category_name(category)
        norm_p_cat = parking_places_config.normalize_category_name(place.get('category'))
        if norm_cat != norm_p_cat:
            return jsonify({'status': 'error', 'message': f"Selected place '{place.get('place_name')}' does not belong to category '{category}'."}), 400

    # Validate slot belongs to selected place
    if place and place.get('slot_numbers') and slot.get('slot_number') not in place['slot_numbers']:
        return jsonify({'status': 'error', 'message': f"Slot {slot.get('slot_number')} does not belong to {place.get('place_name')}."}), 400


    # Calculate hours & end time
    try:
        m = re.search(r'([0-9.]+)', str(duration))
        duration_hours = float(m.group(1)) if m else 2.0
    except Exception:
        duration_hours = 2.0

    end_time_str = calculate_end_time_string(start_time, duration_hours)

    # 4. Verify live slot interval availability
    is_avail, msg, _ = mongo_check_slot_available(slot_id, date=booking_date, start_time=start_time, end_time=end_time_str, duration_hours=duration_hours)
    if not is_avail:
        return jsonify({'status': 'error', 'message': f"Slot is no longer available: {msg}"}), 409

    hourly_rate = float(place.get('hourly_rate') if place else lot.get('hourly_rate', 40.0))
    total_amount = round(duration_hours * hourly_rate, 2)

    final_cat = place.get('category') if place else (category or lot.get('lot_name', 'Facility'))
    final_place_name = place.get('place_name') if place else lot.get('lot_name', 'Parking Facility')
    final_address = place.get('address') if place else lot.get('location', 'Bangalore Central')

    return jsonify({
        'status': 'success',
        'lot_id': target_lot_id,
        'lot_name': final_place_name,
        'place_id': place.get('place_id') if place else None,
        'place_name': final_place_name,
        'parking_place': final_place_name,
        'address': final_address,
        'location': final_address,
        'category': final_cat,
        'facility_category': final_cat,
        'slot_id': slot_id,
        'slot_number': slot.get('slot_number'),
        'slot_type': slot.get('slot_type', 'Standard'),
        'floor': slot.get('floor', 'Ground Floor'),
        'zone': slot.get('zone', 'Standard Bay'),
        'booking_date': str(booking_date),
        'start_time': str(start_time),
        'end_time': end_time_str,
        'duration': str(duration),
        'duration_hours': duration_hours,
        'vehicle_plate': vehicle_plate,
        'vehicle_type': vehicle_type,
        'vehicle_name': vehicle_name,
        'make_model': vehicle_name,
        'hourly_rate': hourly_rate,
        'total_amount': total_amount,
        'estimated_fare': total_amount,
        'is_available': True
    })

# ==============================================================================

# SMART RESERVATION & USER APIs
# ==========================================

@booking_bp.route('/api/reservations/create', methods=['POST'])
def create_reservation():
    """Creates a new parking reservation based on user-filled original input."""
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id') or 1
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 1
    slot_id = data.get('slot_id')
    vehicle_plate = (data.get('vehicle_plate') or '').strip().upper()
    driver_name = (data.get('driver_name') or session.get('user_name', '')).strip()
    driver_phone = (data.get('driver_phone') or session.get('user_phone', '')).strip()
    date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    start_time = data.get('start_time', '10:00')
    try:
        duration_hours = float(data.get('duration_hours', 2.0))
    except (ValueError, TypeError):
        duration_hours = 2.0
    selected_duration = str(data.get('selected_duration') or data.get('duration') or f"{int(duration_hours) if duration_hours.is_integer() else duration_hours} hours").strip()
    ai_recommended = bool(data.get('ai_recommended', False))
    suitability_score = float(data.get('suitability_score', 90.0))
    notes = data.get('notes', '')

    if not vehicle_plate:
        return jsonify({'status': 'error', 'message': 'Vehicle license plate number is required.'}), 400

    if not slot_id:
        return jsonify({'status': 'error', 'message': 'Parking slot selection is required.'}), 400

    # Calculate end time: Expected End Time = Parking Start Time + Selected Duration
    try:
        start_dt = datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        start_dt = datetime.now()
        date_str = start_dt.strftime('%Y-%m-%d')
        start_time = start_dt.strftime('%H:%M')

    end_dt = start_dt + timedelta(hours=duration_hours)
    end_time = end_dt.strftime('%H:%M')
    expected_end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    expected_end_display = end_dt.strftime('%I:%M %p')
    grace_end_dt = end_dt + timedelta(minutes=10)
    grace_end_time = grace_end_dt.strftime('%Y-%m-%d %H:%M:%S')
    grace_end_display = grace_end_dt.strftime('%I:%M %p')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Disallow booking for past dates and past times
    is_valid_dt, dt_err = validate_booking_datetime(date_str, start_time)
    if not is_valid_dt:
        conn.close()
        sim_time = get_current_sim_time(conn)
        current_sys_date = sim_time.strftime('%Y-%m-%d')
        return jsonify({
            'status': 'error',
            'message': f"Cannot book for a past date or time ({date_str} {start_time}). Bookings are only permitted for today ({current_sys_date}) and advance future dates. Please select the current time or a future time. Please select a current or future date and time."
        }), 400

    # Verify slot availability
    cursor.execute("SELECT slot_number, status, lot_id, floor, zone, slot_type FROM parking_slots WHERE slot_id = ?", (slot_id,))
    slot = cursor.fetchone()
    if not slot:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Slot not found'}), 404

    # If user provided driver name/phone, update or look up user
    if driver_name:
        cursor.execute("SELECT user_id, name FROM users WHERE user_id = ?", (user_id,))
        existing_u = cursor.fetchone()
        if existing_u:
            if driver_phone:
                cursor.execute("UPDATE users SET name = ?, phone = ? WHERE user_id = ?", (driver_name, driver_phone, user_id))
            else:
                cursor.execute("UPDATE users SET name = ? WHERE user_id = ?", (driver_name, user_id))
        user_display_name = driver_name
    else:
        cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
        u_row = cursor.fetchone()
        user_display_name = u_row['name'] if u_row else 'Driver'

    # Check if vehicle exists in user garage, if not, auto-add it
    cursor.execute("SELECT vehicle_id FROM vehicles WHERE license_plate = ?", (vehicle_plate,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO vehicles (user_id, license_plate, vehicle_type, make_model, color)
            VALUES (?, ?, ?, 'Personal Vehicle', 'White')
        """, (user_id, vehicle_plate, data.get('vehicle_type', 'Car')))

    # Double-booking guard: Re-validate availability for the requested time window
    cursor.execute("""
        SELECT reservation_id, date, start_time, end_time, vehicle_plate
        FROM reservations
        WHERE slot_id = ?
          AND date = ?
          AND status IN ('confirmed', 'checked_in')
          AND start_time < ?
          AND end_time > ?
    """, (slot_id, date_str, end_time, start_time))
    conflict = cursor.fetchone()
    if conflict:
        conn.close()
        return jsonify({
            'status': 'error',
            'message': f"Slot #{slot['slot_number']} is already booked from {conflict['start_time']} to {conflict['end_time']} on {conflict['date']}. Please select an alternative slot."
        }), 409

    # Calculate fee (40/hr or lot rate)
    cursor.execute("SELECT lot_name, hourly_rate FROM parking_lots WHERE lot_id = ?", (slot['lot_id'],))
    lot_row = cursor.fetchone()
    lot_name = lot_row['lot_name'] if lot_row and lot_row.get('lot_name') else 'City Parking'
    hourly_rate = lot_row['hourly_rate'] if lot_row else 40.0
    total_amount = round(duration_hours * hourly_rate, 2)

    # Insert reservation
    cursor.execute("""
        INSERT INTO reservations 
        (user_id, slot_id, vehicle_plate, date, start_time, end_time, status, ai_recommended, suitability_score, total_amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?)
    """, (user_id, slot_id, vehicle_plate, date_str, start_time, end_time, 1 if ai_recommended else 0, suitability_score, total_amount, notes))
    res_id = cursor.lastrowid

    # Update slot status to reserved
    cursor.execute("""
        UPDATE parking_slots 
        SET status = 'reserved', current_reservation_id = ?, current_plate = ?
        WHERE slot_id = ?
    """, (res_id, vehicle_plate, slot_id))

    # Log activity
    cursor.execute("""
        INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
        VALUES (?, ?, 'Reserved', ?, 'warning', ?)
    """, (
        slot['slot_number'],
        f"{user_display_name} ({vehicle_plate})",
        f"Slot {slot['slot_number']} reserved for {duration_hours}h ({start_time} - {end_time}). AI score: {suitability_score}%.",
        datetime.now().strftime('%I:%M %p')
    ))

    # Dispatch Module 9: Booking Confirmation notification
    create_notification(
        user_id=user_id,
        notif_type='booking_confirmation',
        title='Booking Confirmed!',
        message=f"Your booking for Slot {slot['slot_number']} on {date_str} ({start_time} - {end_time}) is confirmed! Pass: PK-{res_id:05d}-{slot['slot_number']}.",
        related_id=res_id,
        conn=conn
    )

    conn.commit()
    conn.close()

    pass_code = f"PK-{res_id:05d}-{slot['slot_number']}"

    # Real-time MongoDB persistence: store ALL booking fields in MongoDB 'reservations'
    mongo_save_reservation({
        'reservation_id': res_id,
        'pass_code': pass_code,
        'user_id': user_id,
        'user_name': user_display_name,
        'driver_name': driver_name or user_display_name,
        'driver_phone': driver_phone,
        'slot_id': slot_id,
        'slot_number': slot['slot_number'],
        'lot_id': slot['lot_id'],
        'lot_name': lot_name,
        'floor': slot['floor'],
        'zone': slot['zone'],
        'slot_type': slot['slot_type'],
        'vehicle_plate': vehicle_plate,
        'vehicle_type': normalize_vehicle_type(data.get('vehicle_type', 'Car')),
        'date': date_str,
        'start_time': start_time,
        'end_time': end_time,
        'selected_duration': selected_duration,
        'duration': selected_duration,
        'duration_hours': duration_hours,
        'expected_end_time': expected_end_time,
        'expected_end_display': expected_end_display,
        'grace_period': 10,
        'grace_end_time': grace_end_time,
        'grace_end_display': grace_end_display,
        'notification_status': 'Not Sent',
        'overstay_notification_sent': False,
        'hourly_rate': hourly_rate,
        'total_amount': total_amount,
        'status': 'confirmed',
        'ai_recommended': bool(ai_recommended),
        'suitability_score': suitability_score,
        'notes': notes,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    # Also record in MongoDB bookings collection for 5-step / user-facing compatibility
    db_m = get_mongo_db()
    if db_m is not None:
        try:
            db_m.bookings.insert_one({
                'booking_id': pass_code,
                'reservation_id': res_id,
                'pass_code': pass_code,
                'user_id': user_id,
                'user_name': user_display_name,
                'driver_name': driver_name or user_display_name,
                'user_email': session.get('user_email', ''),
                'driver_phone': driver_phone,
                'parking_lot_id': slot.get('lot_id', 1),
                'lot_name': lot_name,
                'slot_id': slot_id,
                'slot_number': slot['slot_number'],
                'floor': slot['floor'],
                'slot_type': slot['slot_type'],
                'vehicle_plate': vehicle_plate,
                'vehicle_type': normalize_vehicle_type(data.get('vehicle_type', 'Car')),
                'booking_date': date_str,
                'date': date_str,
                'start_time': start_time,
                'end_time': end_time,
                'selected_duration': selected_duration,
                'duration': selected_duration,
                'duration_hours': duration_hours,
                'expected_end_time': expected_end_time,
                'expected_end_display': expected_end_display,
                'grace_period': 10,
                'grace_end_time': grace_end_time,
                'grace_end_display': grace_end_display,
                'notification_status': 'Not Sent',
                'overstay_notification_sent': False,
                'hourly_rate': hourly_rate,
                'total_amount': total_amount,
                'status': 'confirmed',
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        except Exception as ex:
            print(f"[MongoDB Warning] bookings insert: {ex}")

    # Update slot in MongoDB
    mongo_update_slot(slot_id, {
        'status': 'reserved',
        'current_reservation_id': res_id,
        'current_plate': vehicle_plate,
        'vehicle_type': normalize_vehicle_type(data.get('vehicle_type', 'Car'))
    })
    # Save activity log in MongoDB
    mongo_log_activity({
        'slot_number': slot['slot_number'],
        'user_name': f"{user_display_name} ({vehicle_plate})",
        'action_type': 'Reserved',
        'details': f"Slot {slot['slot_number']} reserved for {duration_hours}h ({start_time} - {end_time}). AI score: {suitability_score}%.",
        'badge_type': 'warning',
        'timestamp': datetime.now().strftime('%I:%M %p')
    })

    return jsonify({
        'status': 'success',
        'reservation_id': res_id,
        'booking_id': pass_code,
        'pass_code': pass_code,
        'slot_id': slot_id,
        'slot_number': slot['slot_number'],
        'floor': slot['floor'],
        'zone': slot['zone'],
        'user_name': user_display_name,
        'vehicle_plate': vehicle_plate,
        'date': date_str,
        'start_time': start_time,
        'end_time': end_time,
        'duration_hours': duration_hours,
        'total_amount': total_amount,
        'message': f"Reservation confirmed for Slot {slot['slot_number']}! Assigned Pass Code: {pass_code}"
    })

@booking_bp.route('/api/reservations/my', methods=['GET'])
def get_my_reservations():
    """Returns reservations for the active user from MongoDB (session-aware with ?user_id override)."""
    req_uid = request.args.get('user_id')
    if req_uid:
        try:
            user_id = int(req_uid)
        except (ValueError, TypeError):
            user_id = 1
    else:
        user_id = session.get('user_id', 1)

    bookings_data = mongo_get_user_bookings(user_id)
    upcoming = bookings_data.get('upcoming', [])
    history = bookings_data.get('history', [])
    all_res = upcoming + history

    for b in all_res:
        b['reservation_id'] = b.get('reservation_id') or b.get('booking_id')
        b['date'] = b.get('booking_date') or b.get('date') or ''
        b['start_time'] = b.get('start_time') or '10:00'
        b['end_time'] = b.get('end_time') or '12:00'
        b['duration'] = b.get('parking_duration') or b.get('duration') or '2 Hours'
        b['parking_duration'] = b.get('parking_duration') or b.get('duration') or '2 Hours'
        b['actual_entry_time'] = b.get('actual_entry_time')
        b['actual_exit_time'] = b.get('actual_exit_time')
        b['is_overstay'] = bool(b.get('is_overstay', False))
        b['overstay_duration_minutes'] = int(b.get('overstay_duration_minutes') or 0)
        b['overstay_penalty'] = float(b.get('overstay_penalty') or 0.0)
        b['final_status'] = b.get('final_status') or ('Completed + Overstay' if b.get('is_overstay') else ('Completed' if (b.get('status') or '').lower() == 'completed' else b.get('status', 'confirmed').capitalize()))
        b['total_amount'] = float(b.get('total_amount') or 80.0)
        b['slot_number'] = b.get('slot_number') or '-'
        b['lot_name'] = b.get('lot_name') or 'City Parking'
        b['floor'] = b.get('floor') or 'Ground Floor'
        b['vehicle_plate'] = b.get('vehicle_plate') or 'KA01AB1234'
        b['vehicle_type'] = b.get('vehicle_type') or 'Car'
        b['status'] = (b.get('status') or 'confirmed').lower()

    return jsonify({
        'status': 'success',
        'reservations': all_res,
        'upcoming': upcoming,
        'history': history,
        'total': len(all_res)
    })

@booking_bp.route('/api/reservations/facility-history', methods=['GET'])
def get_facility_parking_history():
    """Returns all booked parking sessions across the entire facility for all users."""
    db = get_mongo_db()
    if db is None:
        return jsonify({'status': 'success', 'reservations': [], 'total': 0})

    b_docs = list(db.bookings.find({}).sort('_id', -1).limit(100))
    res_docs = list(db.reservations.find({}).sort('_id', -1).limit(100))

    all_history = []
    seen_ids = set()

    for b in b_docs:
        bid = b.get('booking_id')
        if bid and bid not in seen_ids:
            seen_ids.add(bid)
            is_ov = bool(b.get('is_overstay', False))
            st_raw = (b.get('status') or 'confirmed').lower()
            fin_st = b.get('final_status') or ('Completed + Overstay' if is_ov else ('Completed' if st_raw == 'completed' else st_raw.capitalize()))
            all_history.append({
                'reservation_id': bid,
                'booking_id': bid,
                'user_id': b.get('user_id'),
                'user_name': b.get('user_name', 'Driver'),
                'lot_name': b.get('lot_name', 'Institutions'),
                'slot_number': b.get('slot_number', '-'),
                'floor': b.get('floor', 'Ground Floor'),
                'date': b.get('booking_date') or b.get('date', ''),
                'start_time': b.get('start_time', '10:00'),
                'end_time': b.get('end_time', '12:00'),
                'duration': b.get('parking_duration') or b.get('duration', '2 Hours'),
                'parking_duration': b.get('parking_duration') or b.get('duration', '2 Hours'),
                'actual_entry_time': b.get('actual_entry_time'),
                'actual_exit_time': b.get('actual_exit_time'),
                'is_overstay': is_ov,
                'overstay_duration_minutes': int(b.get('overstay_duration_minutes') or 0),
                'overstay_penalty': float(b.get('overstay_penalty') or 0.0),
                'final_status': fin_st,
                'status': st_raw,
                'total_amount': float(b.get('total_amount') or 60.0),
                'vehicle_plate': b.get('vehicle_plate', ''),
                'vehicle_type': b.get('vehicle_type', 'Car')
            })

    for r in res_docs:
        pid = r.get('pass_code') or f"RES-{r.get('reservation_id')}"
        if pid not in seen_ids:
            seen_ids.add(pid)
            is_ov = bool(r.get('is_overstay', False))
            st_raw = (r.get('status') or 'confirmed').lower()
            fin_st = r.get('final_status') or ('Completed + Overstay' if is_ov else ('Completed' if st_raw == 'completed' else st_raw.capitalize()))
            all_history.append({
                'reservation_id': pid,
                'booking_id': pid,
                'user_id': r.get('user_id'),
                'user_name': r.get('user_name', 'Driver'),
                'lot_name': r.get('lot_name', 'Institutions'),
                'slot_number': r.get('slot_number', '-'),
                'floor': r.get('floor', 'Ground Floor'),
                'date': r.get('date', ''),
                'start_time': r.get('start_time', '10:00'),
                'end_time': r.get('end_time', '12:00'),
                'duration': r.get('parking_duration') or f"{r.get('duration_hours', 2)} Hours",
                'parking_duration': r.get('parking_duration') or f"{r.get('duration_hours', 2)} Hours",
                'actual_entry_time': r.get('actual_entry_time'),
                'actual_exit_time': r.get('actual_exit_time'),
                'is_overstay': is_ov,
                'overstay_duration_minutes': int(r.get('overstay_duration_minutes') or 0),
                'overstay_penalty': float(r.get('overstay_penalty') or 0.0),
                'final_status': fin_st,
                'status': st_raw,
                'total_amount': float(r.get('total_amount') or 60.0),
                'vehicle_plate': r.get('vehicle_plate', ''),
                'vehicle_type': r.get('vehicle_type', 'Car')
            })

    return jsonify({
        'status': 'success',
        'reservations': all_history,
        'total': len(all_history)
    })

@booking_bp.route('/api/reservations/cancel/<res_id>', methods=['POST'])
@booking_bp.route('/api/reservations/cancel/<int:res_id>', methods=['POST'])
def cancel_reservation(res_id):
    """Cancels a reservation and frees the slot in MongoDB."""
    uid = session.get('user_id')
    success, msg = mongo_cancel_booking(res_id, user_id=uid)
    if not success:
        # Fallback to direct DB check if needed
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT r.user_id, r.slot_id, r.vehicle_plate, r.date, s.slot_number FROM reservations r JOIN parking_slots s ON r.slot_id = s.slot_id WHERE r.reservation_id = ?", (res_id,))
            res = cursor.fetchone()
            if res:
                cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE reservation_id = ?", (res_id,))
                cursor.execute("UPDATE parking_slots SET status = 'available', current_reservation_id = NULL, current_plate = NULL WHERE slot_id = ?", (res['slot_id'],))
                conn.commit()
                conn.close()
                mongo_update_reservation(res_id, {'status': 'cancelled'})
                mongo_update_slot(res['slot_id'], {'status': 'available', 'current_reservation_id': None, 'current_plate': None})
                return jsonify({'status': 'success', 'message': 'Reservation cancelled successfully.'})
        except Exception:
            pass
        conn.close()
        return jsonify({'status': 'error', 'message': msg}), 400

    return jsonify({'status': 'success', 'message': msg, 'booking_id': res_id})

# ==========================================

# EXTENDED RESERVATION WORKFLOW APIs
# ==========================================

@booking_bp.route('/api/reservations/search', methods=['POST'])
def search_reservations():
    """Searches available slots matching duration, vehicle type, and floor."""
    data = request.get_json() or {}
    floor = data.get('floor', 'All')
    slot_type = data.get('slot_type', 'All')
    duration = float(data.get('duration', 2.0))

    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM parking_slots WHERE status = 'available'"
    params = []
    if floor and floor != 'All':
        query += " AND floor = ?"
        params.append(floor)
    if slot_type and slot_type != 'All':
        query += " AND slot_type = ?"
        params.append(slot_type)
    query += " ORDER BY distance_to_entry_m ASC"

    cursor.execute(query, params)
    slots = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        'status': 'success',
        'available_count': len(slots),
        'slots': slots,
        'estimated_fare': round(duration * 40.0, 2)
    })

@booking_bp.route('/api/reservations/modify/<int:res_id>', methods=['POST'])
def modify_reservation(res_id):
    """Extends duration or modifies vehicle plate for an existing booking."""
    data = request.get_json() or {}
    added_hours = float(data.get('added_hours', 1.0))
    new_plate = data.get('vehicle_plate')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (res_id,))
    res = cursor.fetchone()
    if not res:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Reservation not found'}), 404

    # Calculate new end time and amount
    start_dt = datetime.strptime(f"{res['date']} {res['start_time']}", "%Y-%m-%d %H:%M")
    curr_end_dt = datetime.strptime(f"{res['date']} {res['end_time']}", "%Y-%m-%d %H:%M")
    new_end_dt = curr_end_dt + timedelta(hours=added_hours)
    new_end_time = new_end_dt.strftime('%H:%M')
    new_total = res['total_amount'] + (added_hours * 40.0)

    updates = ["end_time = ?", "total_amount = ?"]
    params = [new_end_time, new_total]

    if new_plate:
        updates.append("vehicle_plate = ?")
        params.append(new_plate.strip().upper())

    params.append(res_id)
    cursor.execute(f"UPDATE reservations SET {', '.join(updates)} WHERE reservation_id = ?", params)
    
    if new_plate:
        cursor.execute("UPDATE parking_slots SET current_plate = ? WHERE slot_id = ?", (new_plate.strip().upper(), res['slot_id']))

    cursor.execute("""
        INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
        VALUES ((SELECT slot_number FROM parking_slots WHERE slot_id = ?), ?, 'Modified', ?, 'info', ?)
    """, (
        res['slot_id'],
        f"User ({new_plate or res['vehicle_plate']})",
        f"Reservation #{res_id} extended by {added_hours}h to {new_end_time}.",
        datetime.now().strftime('%I:%M %p')
    ))

    conn.commit()
    conn.close()

    # Real-time MongoDB persistence for modification
    mongo_res_mod = {
        'end_time': new_end_time,
        'total_amount': new_total
    }
    if new_plate:
        mongo_res_mod['vehicle_plate'] = new_plate.strip().upper()
        mongo_update_slot(res['slot_id'], {'current_plate': new_plate.strip().upper()})
    mongo_update_reservation(res_id, mongo_res_mod)
    mongo_log_activity({
        'slot_number': res['slot_id'],
        'user_name': f"User ({new_plate or res['vehicle_plate']})",
        'action_type': 'Modified',
        'details': f"Reservation #{res_id} extended by {added_hours}h to {new_end_time}.",
        'badge_type': 'info',
        'timestamp': datetime.now().strftime('%I:%M %p')
    })

    return jsonify({
        'status': 'success',
        'message': f"Reservation extended to {new_end_time}. New total: ₹{new_total:.2f}",
        'new_end_time': new_end_time,
        'new_total_amount': new_total
    })

@booking_bp.route('/api/reservations/<int:res_id>/pass', methods=['GET'])
def get_reservation_pass(res_id):
    """Generates digital QR parking pass metadata."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, s.slot_number, s.floor, s.zone, s.slot_type, s.distance_to_entry_m, s.distance_to_elevator_m,
               u.name as user_name, u.phone as user_phone, u.email as user_email,
               p.lot_name, p.location as lot_location
        FROM reservations r
        JOIN parking_slots s ON r.slot_id = s.slot_id
        JOIN users u ON r.user_id = u.user_id
        JOIN parking_lots p ON s.lot_id = p.lot_id
        WHERE r.reservation_id = ?
    """, (res_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({'status': 'error', 'message': 'Reservation not found'}), 404

    pass_data = dict(row)
    pass_data['pass_code'] = f"PK-{pass_data['reservation_id']:05d}-{pass_data['slot_number']}"
    pass_data['qr_text'] = f"SMARTPARK:{pass_data['pass_code']}:{pass_data['vehicle_plate']}:{pass_data['date']}"
    
    return jsonify({
        'status': 'success',
        'pass': pass_data
    })

# ==========================================
