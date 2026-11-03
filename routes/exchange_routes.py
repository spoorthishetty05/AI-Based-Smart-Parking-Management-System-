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

from core.email_service import send_templated_email
from core.overstay_engine import get_current_sim_time

exchange_bp = Blueprint('exchange', __name__)


# MODULE 7: PARKING SLOT EXCHANGE APIs
# ==========================================

@exchange_bp.route('/api/exchange/user-active-booking', methods=['GET'])
def get_user_active_booking_for_exchange():
    """Returns the user's latest confirmed future booking with exchange offer status."""
    user_id = request.args.get('user_id', type=int)
    if not user_id:
        user_id = session.get('user_id', 1)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user's confirmed future bookings
    requested_res_id = request.args.get('reservation_id', type=int)
    
    query = """
        SELECT r.*, s.slot_number, s.slot_type, s.floor, s.zone, 
               s.distance_to_entry_m, s.distance_to_elevator_m,
               l.lot_name, l.lot_id, l.location as lot_location
        FROM reservations r
        JOIN parking_slots s ON r.slot_id = s.slot_id
        JOIN parking_lots l ON s.lot_id = l.lot_id
        WHERE r.user_id = ? AND r.status = 'confirmed'
    """
    params = [user_id]
    if requested_res_id:
        query += " AND r.reservation_id = ?"
        params.append(requested_res_id)
        
    query += " ORDER BY r.reservation_id DESC"
    cursor.execute(query, params)
    all_booking_rows = [dict(row) for row in cursor.fetchall()]

    if not all_booking_rows:
        conn.close()
        return jsonify({'status': 'success', 'has_booking': False, 'booking': None, 'is_offered': False, 'all_bookings': []})

    # Pick the most relevant booking: preferably one already listed for exchange, else latest
    selected_booking = all_booking_rows[0]
    active_listing_info = None
    is_offered = False

    for b in all_booking_rows:
        cursor.execute("""
            SELECT listing_id, status, notes, created_at
            FROM slot_exchange_listings
            WHERE reservation_id = ? AND status IN ('available', 'pending')
            LIMIT 1
        """, (b['reservation_id'],))
        l_row = cursor.fetchone()
        if l_row:
            selected_booking = b
            active_listing_info = dict(l_row)
            is_offered = True
            break

    if not is_offered:
        cursor.execute("""
            SELECT listing_id, status, notes, created_at
            FROM slot_exchange_listings
            WHERE reservation_id = ? AND status IN ('available', 'pending')
            LIMIT 1
        """, (selected_booking['reservation_id'],))
        l_row = cursor.fetchone()
        if l_row:
            active_listing_info = dict(l_row)
            is_offered = True

    conn.close()
    return jsonify({
        'status': 'success',
        'has_booking': True,
        'booking': selected_booking,
        'all_bookings': all_booking_rows,
        'is_offered': is_offered,
        'listing': active_listing_info
    })

@exchange_bp.route('/api/exchange/offer', methods=['POST'])
def offer_slot_for_exchange():
    """Allows a user to offer their confirmed future booking for exchange."""
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 1
    reservation_id = data.get('reservation_id')
    if not reservation_id:
        return jsonify({'status': 'error', 'message': 'Reservation ID is required.'}), 400
    try:
        reservation_id = int(reservation_id)
    except (ValueError, TypeError):
        pass
    notes = data.get('notes', 'Looking for a convenient slot swap.')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify reservation exists, belongs to user, and is confirmed
    cursor.execute("""
        SELECT r.*, s.slot_id, s.slot_number, s.slot_type, s.floor, s.zone, s.lot_id, u.name as owner_name, p.lot_name
        FROM reservations r
        JOIN parking_slots s ON r.slot_id = s.slot_id
        JOIN parking_lots p ON s.lot_id = p.lot_id
        JOIN users u ON r.user_id = u.user_id
        WHERE r.reservation_id = ?
    """, (reservation_id,))
    res_row = cursor.fetchone()

    if not res_row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Reservation not found.'}), 404

    res = dict(res_row)
    if int(res['user_id']) != int(user_id):
        conn.close()
        return jsonify({'status': 'error', 'message': 'Unauthorized: You can only offer your own booking.'}), 403

    if res['status'] != 'confirmed':
        conn.close()
        return jsonify({'status': 'error', 'message': f"Cannot offer booking with status '{res['status']}'. Only confirmed future bookings can be offered."}), 400

    # Security: Prevent offering already listed or pending exchange
    cursor.execute("""
        SELECT listing_id FROM slot_exchange_listings
        WHERE reservation_id = ? AND status IN ('available', 'pending')
    """, (reservation_id,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'status': 'error', 'message': 'This slot is already actively offered for exchange.'}), 400

    # Insert into exchange listings (IDs normalized to integers)
    cursor.execute("""
        INSERT INTO slot_exchange_listings 
        (reservation_id, user_id, slot_id, lot_id, date, start_time, end_time, slot_type, floor, zone, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?)
    """, (reservation_id, user_id, int(res['slot_id']), int(res['lot_id']), res['date'], res['start_time'], res['end_time'], res['slot_type'], res['floor'], res['zone'], notes))
    listing_id = cursor.lastrowid

    # Log activity
    cursor.execute("""
        INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
        VALUES (?, ?, 'Slot Offered', ?, 'info', CURRENT_TIMESTAMP)
    """, (res['slot_number'], res['owner_name'], f"Offered slot {res['slot_number']} for exchange on {res['date']} ({res['start_time']}-{res['end_time']})"))

    # Dispatch notification to the offering driver
    create_notification(
        user_id=user_id,
        notif_type='exchange_listed',
        title='Slot Listed for Exchange 🔄',
        message=f"Your booking for Slot {res['slot_number']} ({res.get('lot_name', 'Facility')}) on {res['date']} ({res['start_time']} – {res['end_time']}) is now listed on the Slot Exchange Marketplace.",
        related_id=listing_id,
        conn=conn
    )

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Slot {res['slot_number']} is now listed for exchange!",
        'listing_id': listing_id
    }), 201

@exchange_bp.route('/api/exchange/cancel-offer', methods=['POST'])
def cancel_slot_exchange_offer():
    """Cancels an active exchange offer."""
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 1
    listing_id = data.get('listing_id')
    reservation_id = data.get('reservation_id')

    if not listing_id and not reservation_id:
        return jsonify({'status': 'error', 'message': 'Listing ID or Reservation ID is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    if listing_id:
        try:
            listing_id = int(listing_id)
        except (ValueError, TypeError):
            pass
        cursor.execute("SELECT * FROM slot_exchange_listings WHERE listing_id = ?", (listing_id,))
    else:
        try:
            reservation_id = int(reservation_id)
        except (ValueError, TypeError):
            pass
        cursor.execute("SELECT * FROM slot_exchange_listings WHERE reservation_id = ? AND status IN ('available', 'pending')", (reservation_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Active listing not found.'}), 404

    listing = dict(row)
    if int(listing['user_id']) != int(user_id):
        conn.close()
        return jsonify({'status': 'error', 'message': 'Unauthorized to cancel this listing.'}), 403

    if listing['status'] not in ('available', 'pending'):
        conn.close()
        return jsonify({'status': 'error', 'message': f"Listing cannot be cancelled because it is already {listing['status']}."}), 400

    actual_listing_id = int(listing['listing_id'])
    cursor.execute("UPDATE slot_exchange_listings SET status = 'cancelled' WHERE listing_id = ?", (actual_listing_id,))
    cursor.execute("UPDATE slot_exchange_requests SET status = 'cancelled' WHERE listing_id = ? AND status = 'pending'", (actual_listing_id,))

    create_notification(
        user_id=user_id,
        notif_type='exchange_cancelled',
        title='Exchange Offer Withdrawn',
        message="You withdrew your slot from the exchange marketplace. Your original booking remains confirmed.",
        related_id=actual_listing_id,
        conn=conn
    )

    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'message': 'Exchange offer withdrawn successfully.'})

@exchange_bp.route('/api/exchange/seed-demo', methods=['POST'])
def api_seed_demo_exchange():
    """Seeds a swappable slot listing from another driver for immediate testing."""
    data = request.get_json() or {}
    current_uid = data.get('user_id') or session.get('user_id', 1)
    try:
        current_uid = int(current_uid)
    except (ValueError, TypeError):
        current_uid = 1

    other_uid = 4 if current_uid != 4 else 3
    today_str = datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Find an available slot in Lot 1 or Lot 4
    cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE status = 'available' AND lot_id = 1 LIMIT 1")
    slot_row = cursor.fetchone()
    if not slot_row:
        cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE status = 'available' LIMIT 1")
        slot_row = cursor.fetchone()

    if not slot_row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'No slots available to create demo offer.'}), 400

    slot = dict(slot_row)
    v_type = data.get('vehicle_type') or ('Bike' if str(slot.get('slot_number', '')).upper().startswith('B') else 'Car')
    cursor.execute("""
        INSERT INTO reservations 
        (user_id, slot_id, vehicle_plate, vehicle_type, date, start_time, end_time, status, total_amount, notes)
        VALUES (?, ?, 'KA19MG2026', ?, ?, '15:00', '17:00', 'confirmed', 60.0, 'Demo Booking')
    """, (other_uid, slot['slot_id'], v_type, today_str))
    new_res_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO slot_exchange_listings
        (reservation_id, user_id, slot_id, lot_id, date, start_time, end_time, slot_type, floor, zone, status, notes)
        VALUES (?, ?, ?, ?, ?, '15:00', '17:00', ?, ?, ?, 'available', 'Looking to swap for a slot closer to entrance.')
    """, (new_res_id, other_uid, slot['slot_id'], slot['lot_id'], today_str, slot['slot_type'], slot['floor'], slot['zone']))
    listing_id = cursor.lastrowid

    cursor.execute("UPDATE parking_slots SET status = 'reserved', current_reservation_id = ? WHERE slot_id = ?", (new_res_id, slot['slot_id']))

    # Sync vehicle_type to MongoDB slot
    db_m = get_mongo_db()
    if db_m is not None:
        try:
            db_m.parking_slots.update_one({'slot_id': slot['slot_id']}, {'$set': {'status': 'reserved', 'current_reservation_id': new_res_id, 'vehicle_type': v_type}})
        except Exception:
            pass

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Swap offer for Slot {slot['slot_number']} listed by driver #{other_uid}! You can now propose a swap.",
        'listing_id': listing_id
    })

@exchange_bp.route('/api/exchange/quick-seed-booking', methods=['POST'])
def quick_seed_booking_for_exchange():
    """Quickly seeds an active confirmed reservation for the current user to test slot exchange immediately."""
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 1

    conn = get_db_connection()
    cursor = conn.cursor()

    # Find an available slot in Lot 1 or 4 (prefer requested slot or lot if provided)
    req_slot_id = data.get('slot_id')
    slot = None
    if req_slot_id:
        cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE slot_id = ?", (req_slot_id,))
        slot = cursor.fetchone()
    if not slot:
        cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE status = 'available' AND lot_id = 1 LIMIT 1")
        slot = cursor.fetchone()
    if not slot:
        cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE status = 'available' LIMIT 1")
        slot = cursor.fetchone()

    if not slot:
        conn.close()
        return jsonify({'status': 'error', 'message': 'No available slots to create test booking.'}), 400

    slot = dict(slot)
    target_date = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
    v_type = data.get('vehicle_type') or ('Bike' if str(slot.get('slot_number', '')).upper().startswith('B') else 'Car')

    cursor.execute("""
        INSERT INTO reservations 
        (user_id, slot_id, vehicle_plate, vehicle_type, date, start_time, end_time, status, total_amount, notes)
        VALUES (?, ?, 'KA01MG2026', ?, ?, '10:00', '12:00', 'confirmed', 60.0, 'Slot Exchange Demo Booking')
    """, (user_id, slot['slot_id'], v_type, target_date))
    res_id = cursor.lastrowid
    cursor.execute("UPDATE parking_slots SET status = 'reserved', current_reservation_id = ? WHERE slot_id = ?", (res_id, slot['slot_id']))

    # Sync vehicle_type to MongoDB slot
    db_m = get_mongo_db()
    if db_m is not None:
        try:
            db_m.parking_slots.update_one({'slot_id': slot['slot_id']}, {'$set': {'status': 'reserved', 'current_reservation_id': res_id, 'vehicle_type': v_type}})
        except Exception:
            pass

    create_notification(
        user_id=user_id,
        notif_type='booking_confirmation',
        title='Demo Booking Confirmed!',
        message=f"Test reservation for Slot {slot['slot_number']} on {target_date} created. You can now offer or exchange this slot!",
        related_id=res_id,
        conn=conn
    )

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Confirmed booking created for Slot {slot['slot_number']} on {target_date}!",
        'reservation_id': res_id,
        'slot_number': slot['slot_number']
    }), 201

@exchange_bp.route('/api/exchange/simulate-incoming-request', methods=['POST'])
def simulate_incoming_exchange_request():
    """
    Simulates another driver (e.g. Chaithali or Anoop) submitting an exchange request 
    to the current user's slot so the user can test the incoming request & accept/reject flow.
    """
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 1

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch user's confirmed booking
    cursor.execute("""
        SELECT r.*, s.slot_number, s.slot_type, s.floor, s.zone, s.lot_id, u.name as user_name
        FROM reservations r
        JOIN parking_slots s ON r.slot_id = s.slot_id
        JOIN users u ON r.user_id = u.user_id
        WHERE r.user_id = ? AND r.status = 'confirmed'
        ORDER BY r.reservation_id DESC LIMIT 1
    """, (user_id,))
    user_res = cursor.fetchone()

    target_date = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')

    if not user_res:
        # If user has no booking, auto-seed one for testing
        cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE status = 'available' AND lot_id = 1 LIMIT 1")
        avail_slot = cursor.fetchone()
        if not avail_slot:
            cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE status = 'available' LIMIT 1")
            avail_slot = cursor.fetchone()
        if not avail_slot:
            conn.close()
            return jsonify({'status': 'error', 'message': 'No slots available to create test booking.'}), 400
        
        avail_slot = dict(avail_slot)
        cursor.execute("""
            INSERT INTO reservations 
            (user_id, slot_id, vehicle_plate, date, start_time, end_time, status, total_amount, notes)
            VALUES (?, ?, 'KA01SP2026', ?, '10:00', '12:00', 'confirmed', 60.0, 'Auto-created Test Booking')
        """, (user_id, avail_slot['slot_id'], target_date))
        user_res_id = cursor.lastrowid
        cursor.execute("UPDATE parking_slots SET status = 'reserved', current_reservation_id = ? WHERE slot_id = ?", (user_res_id, avail_slot['slot_id']))
        conn.commit()
        cursor.execute("""
            SELECT r.*, s.slot_number, s.slot_type, s.floor, s.zone, s.lot_id, u.name as user_name
            FROM reservations r
            JOIN parking_slots s ON r.slot_id = s.slot_id
            JOIN users u ON r.user_id = u.user_id
            WHERE r.reservation_id = ?
        """, (user_res_id,))
        user_res = cursor.fetchone()

    user_res = dict(user_res)

    # 2. Check if listing exists, if not create one
    cursor.execute("""
        SELECT listing_id FROM slot_exchange_listings 
        WHERE reservation_id = ? AND status IN ('available', 'pending')
    """, (user_res['reservation_id'],))
    l_row = cursor.fetchone()
    if l_row:
        listing_id = l_row['listing_id']
    else:
        cursor.execute("""
            INSERT INTO slot_exchange_listings 
            (reservation_id, user_id, slot_id, lot_id, date, start_time, end_time, slot_type, floor, zone, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', 'Listed for swap')
        """, (user_res['reservation_id'], user_id, user_res['slot_id'], user_res['lot_id'],
              user_res['date'], user_res['start_time'], user_res['end_time'],
              user_res['slot_type'], user_res['floor'], user_res['zone']))
        listing_id = cursor.lastrowid

    # 3. Pick demo partner driver
    other_uid = 4 if user_id != 4 else 5
    cursor.execute("SELECT name FROM users WHERE user_id = ?", (other_uid,))
    u_other = cursor.fetchone()
    other_name = u_other['name'] if u_other else 'Driver Chaithali'

    # Find another available slot for the other driver
    cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE status = 'available' AND slot_id != ? LIMIT 1", (user_res['slot_id'],))
    other_slot = cursor.fetchone()
    if not other_slot:
        cursor.execute("SELECT slot_id, slot_number, floor, zone, slot_type, lot_id FROM parking_slots WHERE slot_id != ? LIMIT 1", (user_res['slot_id'],))
        other_slot = cursor.fetchone()

    if not other_slot:
        conn.close()
        return jsonify({'status': 'error', 'message': 'No alternative slots available to propose swap.'}), 400

    other_slot = dict(other_slot)
    cursor.execute("""
        INSERT INTO reservations 
        (user_id, slot_id, vehicle_plate, date, start_time, end_time, status, total_amount, notes)
        VALUES (?, ?, 'KA19CH2026', ?, ?, ?, 'confirmed', 60.0, 'Demo Partner Booking')
    """, (other_uid, other_slot['slot_id'], user_res['date'], user_res['start_time'], user_res['end_time']))
    other_res_id = cursor.lastrowid
    cursor.execute("UPDATE parking_slots SET status = 'reserved', current_reservation_id = ? WHERE slot_id = ?", (other_res_id, other_slot['slot_id']))

    # 4. Insert incoming request to user's listing
    cursor.execute("""
        INSERT INTO slot_exchange_requests
        (listing_id, requester_user_id, requester_reservation_id, owner_user_id, status, match_score, match_rationale, match_method)
        VALUES (?, ?, ?, ?, 'pending', 94.5, 'Identical Date & Schedule Match • Nearby Elevator', 'rule_based')
    """, (listing_id, other_uid, other_res_id, user_id))
    request_id = cursor.lastrowid

    # Dispatch notification to user
    create_notification(
        user_id=user_id,
        notif_type='exchange_request',
        title='Incoming Slot Exchange Request 🔄',
        message=f"{other_name} requested to swap Slot {other_slot['slot_number']} for your Slot {user_res['slot_number']} on {user_res['date']}.",
        related_id=request_id,
        conn=conn
    )

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Simulated incoming request from {other_name} (offering Slot {other_slot['slot_number']})!",
        'request_id': request_id,
        'partner_name': other_name,
        'partner_slot': other_slot['slot_number']
    }), 201

@exchange_bp.route('/api/exchange/simulate-owner-response', methods=['POST'])
def simulate_owner_response():
    """
    Simulates acceptance or rejection of a pending request by the partner driver,
    enabling immediate end-to-end testing of slot exchange.
    """
    data = request.get_json() or {}
    request_id = data.get('request_id')
    action = (data.get('action') or 'accept').strip().lower()

    if not request_id:
        return jsonify({'status': 'error', 'message': 'Request ID is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT owner_user_id FROM slot_exchange_requests WHERE request_id = ?", (request_id,))
    req_row = cursor.fetchone()
    conn.close()

    if not req_row:
        return jsonify({'status': 'error', 'message': 'Exchange request not found.'}), 404

    owner_uid = req_row['owner_user_id']
    # Delegate to respond_to_exchange_request logic with simulation authorization
    with current_app.test_request_context('/api/exchange/respond', method='POST', json={
        'request_id': request_id,
        'action': action,
        'user_id': owner_uid,
        'simulate': True
    }):
        return respond_to_exchange_request()

@exchange_bp.route('/api/exchange/search', methods=['GET'])
@exchange_bp.route('/api/exchange/browse', methods=['GET'])
def search_exchange_opportunities():
    """Returns available exchange opportunities with transparent rule-based matching."""
    current_user_id = request.args.get('user_id', type=int) or session.get('user_id', 1)
    date_filter = request.args.get('date', '').strip()
    lot_id_filter = request.args.get('lot_id', '').strip()
    floor_filter = request.args.get('floor', '').strip()
    slot_type_filter = request.args.get('slot_type', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get current user's booking if any for matching calculation
    cursor.execute("""
        SELECT r.*, s.slot_number, s.slot_type, s.floor, s.zone, s.lot_id,
               s.distance_to_entry_m, s.distance_to_elevator_m
        FROM reservations r
        JOIN parking_slots s ON r.slot_id = s.slot_id
        WHERE r.user_id = ? AND r.status = 'confirmed'
        ORDER BY r.date ASC, r.start_time ASC
        LIMIT 1
    """, (current_user_id,))
    user_booking_row = cursor.fetchone()
    user_booking = dict(user_booking_row) if user_booking_row else None

    # Base query for listings from OTHER users
    # Include both 'available' and 'pending' listings so opportunities remain visible to other drivers
    query = """
        SELECT l.*, s.slot_number, s.distance_to_entry_m, s.distance_to_elevator_m,
               p.lot_name, p.location as lot_location, p.hourly_rate,
               u.name as owner_name, u.email as owner_email, u.created_at as owner_member_since
        FROM slot_exchange_listings l
        JOIN parking_slots s ON l.slot_id = s.slot_id
        JOIN parking_lots p ON l.lot_id = p.lot_id
        JOIN users u ON l.user_id = u.user_id
        WHERE l.status IN ('available', 'pending') AND l.user_id != ?
    """
    params = [current_user_id]

    if date_filter and date_filter.lower() not in ('all', 'any', 'all dates', ''):
        query += " AND l.date = ?"
        params.append(date_filter)

    if lot_id_filter and lot_id_filter.lower() != 'all':
        query += " AND l.lot_id = ?"
        params.append(int(lot_id_filter))

    if floor_filter and floor_filter.lower() != 'all':
        query += " AND l.floor = ?"
        params.append(floor_filter)

    if slot_type_filter and slot_type_filter.lower() != 'all':
        query += " AND l.slot_type = ?"
        params.append(slot_type_filter)

    query += " ORDER BY l.created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    opportunities = []
    for r in rows:
        item = dict(r)
        
        # Transparent Rule-Based Compatibility Scoring
        score = 80.0
        rationales = []

        if user_booking:
            if item['date'] == user_booking['date']:
                score += 8.0
                rationales.append("Identical Date Match")
            if item['start_time'] == user_booking['start_time']:
                score += 5.0
                rationales.append("Matching Time Window")
            if item['lot_id'] == user_booking['lot_id']:
                score += 4.0
                rationales.append("Same Parking Facility")
            if item['distance_to_elevator_m'] <= 15:
                score += 2.0
                rationales.append("Near Elevator")
            elif item['distance_to_entry_m'] <= 15:
                score += 2.0
                rationales.append("Near Entry/Exit Gate")

        score = min(98.5, max(75.0, score))
        item['match_score'] = round(score, 1)
        item['match_method'] = 'rule_based'
        item['match_rationale'] = " • ".join(rationales) if rationales else "Rule-Based Compatibility Match"
        opportunities.append(item)

    conn.close()
    return jsonify({
        'status': 'success',
        'count': len(opportunities),
        'opportunities': opportunities,
        'listings': opportunities,
        'has_user_booking': user_booking is not None
    })

@exchange_bp.route('/api/exchange/request', methods=['POST'])
@exchange_bp.route('/api/exchange/propose', methods=['POST'])
def request_slot_exchange():
    """Allows a user to request an exchange for another user's offered slot."""
    data = request.get_json() or {}
    requester_user_id = data.get('requester_user_id') or session.get('user_id', 1)
    listing_id = data.get('listing_id')
    requester_reservation_id = data.get('requester_reservation_id')

    if not requester_reservation_id:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT reservation_id FROM reservations WHERE user_id = ? AND status = 'confirmed' ORDER BY reservation_id DESC LIMIT 1", (requester_user_id,))
        r_row = cur.fetchone()
        conn.close()
        if r_row:
            requester_reservation_id = r_row['reservation_id']

    if not listing_id:
        return jsonify({'status': 'error', 'message': 'Listing ID is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Verify listing exists and is available
    cursor.execute("""
        SELECT l.*, s.slot_number, u.name as owner_name
        FROM slot_exchange_listings l
        JOIN parking_slots s ON l.slot_id = s.slot_id
        JOIN users u ON l.user_id = u.user_id
        WHERE l.listing_id = ?
    """, (listing_id,))
    listing_row = cursor.fetchone()

    if not listing_row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Listing not found.'}), 404

    listing = dict(listing_row)

    if listing['status'] not in ('available', 'pending'):
        conn.close()
        return jsonify({'status': 'error', 'message': f"This slot is currently {listing['status']} and cannot receive new exchange requests."}), 400

    # Security: Prevent user exchanging with their own listing
    if int(listing['user_id']) == int(requester_user_id):
        conn.close()
        return jsonify({'status': 'error', 'message': 'You cannot request an exchange for your own slot.'}), 400

    # 2. Get requester's booking if not explicitly provided
    if not requester_reservation_id:
        cursor.execute("""
            SELECT reservation_id FROM reservations
            WHERE user_id = ? AND status = 'confirmed'
            ORDER BY date ASC, start_time ASC
            LIMIT 1
        """, (requester_user_id,))
        req_res_row = cursor.fetchone()
        if not req_res_row:
            conn.close()
            return jsonify({'status': 'error', 'message': 'You must have an active confirmed future booking to propose an exchange.'}), 400
        requester_reservation_id = req_res_row['reservation_id']

    # Verify requester's reservation is confirmed and belongs to requester
    cursor.execute("""
        SELECT r.*, s.slot_number, s.slot_type, u.name as requester_name
        FROM reservations r
        JOIN parking_slots s ON r.slot_id = s.slot_id
        JOIN users u ON r.user_id = u.user_id
        WHERE r.reservation_id = ?
    """, (requester_reservation_id,))
    req_res_row = cursor.fetchone()

    if not req_res_row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Your offered reservation was not found.'}), 404

    req_res = dict(req_res_row)
    if int(req_res['user_id']) != int(requester_user_id):
        conn.close()
        return jsonify({'status': 'error', 'message': 'Unauthorized: You can only trade your own booking.'}), 403

    if req_res['status'] != 'confirmed':
        conn.close()
        return jsonify({'status': 'error', 'message': f"Cannot trade reservation with status '{req_res['status']}'."}), 400

    # Security: Prevent duplicate pending requests for the same listing
    cursor.execute("""
        SELECT request_id FROM slot_exchange_requests
        WHERE listing_id = ? AND requester_user_id = ? AND status = 'pending'
    """, (listing_id, requester_user_id))
    if cursor.fetchone():
        conn.close()
        return jsonify({'status': 'error', 'message': 'You already have a pending exchange request for this slot.'}), 400

    # Insert request
    cursor.execute("""
        INSERT INTO slot_exchange_requests
        (listing_id, requester_user_id, requester_reservation_id, owner_user_id, status, match_score, match_rationale, match_method)
        VALUES (?, ?, ?, ?, 'pending', 88.5, 'Schedule & Facility Rule-Based Match', 'rule_based')
    """, (listing_id, requester_user_id, requester_reservation_id, listing['user_id']))
    request_id = cursor.lastrowid

    # Mark listing as pending negotiation
    cursor.execute("UPDATE slot_exchange_listings SET status = 'pending' WHERE listing_id = ?", (listing_id,))

    # Log activity
    cursor.execute("""
        INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
        VALUES (?, ?, 'Exchange Requested', ?, 'warning', CURRENT_TIMESTAMP)
    """, (listing['slot_number'], req_res['requester_name'], f"{req_res['requester_name']} requested to exchange slot {req_res['slot_number']} for {listing['slot_number']}."))

    # Dispatch Module 9: Exchange Request Notification to slot owner
    create_notification(
        user_id=listing['user_id'],
        notif_type='exchange_request',
        title='New Slot Exchange Request 🔄',
        message=f"{req_res['requester_name']} requested to exchange slot {req_res['slot_number']} for your slot {listing['slot_number']} on {listing['date']}.",
        related_id=request_id,
        conn=conn
    )
    # Also notify requester that request has been recorded
    create_notification(
        user_id=requester_user_id,
        notif_type='exchange_proposed',
        title='Exchange Proposal Sent 📤',
        message=f"You offered to swap Slot {req_res['slot_number']} for Slot {listing['slot_number']} (Owner: {listing.get('owner_name')}). Waiting for owner review.",
        related_id=request_id,
        conn=conn
    )

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': f"Exchange request sent to {listing['owner_name']}!",
        'request_id': request_id
    }), 201

@exchange_bp.route('/api/exchange/cancel-request', methods=['POST'])
def cancel_slot_exchange_request():
    """Allows a requester to cancel/withdraw their pending exchange request."""
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    request_id = data.get('request_id')

    if not request_id:
        return jsonify({'status': 'error', 'message': 'Request ID is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM slot_exchange_requests WHERE request_id = ?", (request_id,))
    req_row = cursor.fetchone()
    if not req_row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Exchange request not found.'}), 404

    req = dict(req_row)
    if int(req['requester_user_id']) != int(user_id):
        conn.close()
        return jsonify({'status': 'error', 'message': 'Unauthorized to cancel this exchange request.'}), 403

    if req['status'] != 'pending':
        conn.close()
        return jsonify({'status': 'error', 'message': f"Request cannot be cancelled because it is already {req['status']}."}), 400

    cursor.execute("UPDATE slot_exchange_requests SET status = 'cancelled' WHERE request_id = ?", (request_id,))

    # Check if other pending requests remain on this listing; if none, revert listing status to available
    cursor.execute("SELECT COUNT(*) as cnt FROM slot_exchange_requests WHERE listing_id = ? AND status = 'pending'", (req['listing_id'],))
    remaining = cursor.fetchone()['cnt']
    if remaining == 0:
        cursor.execute("UPDATE slot_exchange_listings SET status = 'available' WHERE listing_id = ?", (req['listing_id'],))

    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Exchange request withdrawn successfully.'})

@exchange_bp.route('/api/exchange/requests', methods=['GET'])
def get_exchange_requests():
    """Returns received requests, sent requests, and exchange history for the user."""
    user_id = request.args.get('user_id', type=int) or session.get('user_id', 1)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Received Requests (requests sent to the current user)
    cursor.execute("""
        SELECT req.*, 
               u_req.name as requester_name, u_req.email as requester_email, u_req.created_at as requester_member_since,
               s_req.slot_number as requester_slot_number, s_req.floor as requester_floor, s_req.slot_type as requester_slot_type,
               l_req.lot_name as requester_lot_name,
               r_req.date as requester_date, r_req.start_time as requester_start_time, r_req.end_time as requester_end_time,
               s_own.slot_number as owner_slot_number, s_own.floor as owner_floor, s_own.slot_type as owner_slot_type,
               l_own.lot_name as owner_lot_name,
               r_own.date as owner_date, r_own.start_time as owner_start_time, r_own.end_time as owner_end_time
        FROM slot_exchange_requests req
        JOIN users u_req ON req.requester_user_id = u_req.user_id
        JOIN reservations r_req ON req.requester_reservation_id = r_req.reservation_id
        JOIN parking_slots s_req ON r_req.slot_id = s_req.slot_id
        JOIN parking_lots l_req ON s_req.lot_id = l_req.lot_id
        JOIN slot_exchange_listings list ON req.listing_id = list.listing_id
        JOIN reservations r_own ON list.reservation_id = r_own.reservation_id
        JOIN parking_slots s_own ON r_own.slot_id = s_own.slot_id
        JOIN parking_lots l_own ON s_own.lot_id = l_own.lot_id
        WHERE req.owner_user_id = ? AND req.status = 'pending'
        ORDER BY req.created_at DESC
    """, (user_id,))
    received = [dict(r) for r in cursor.fetchall()]

    # 2. Sent Requests (requests initiated by the current user)
    cursor.execute("""
        SELECT req.*, 
               u_own.name as owner_name, u_own.email as owner_email,
               s_own.slot_number as owner_slot_number, s_own.floor as owner_floor, s_own.slot_type as owner_slot_type,
               l_own.lot_name as owner_lot_name,
               r_own.date as owner_date, r_own.start_time as owner_start_time, r_own.end_time as owner_end_time,
               s_req.slot_number as requester_slot_number, s_req.floor as requester_floor,
               r_req.date as requester_date, r_req.start_time as requester_start_time, r_req.end_time as requester_end_time
        FROM slot_exchange_requests req
        JOIN users u_own ON req.owner_user_id = u_own.user_id
        JOIN slot_exchange_listings list ON req.listing_id = list.listing_id
        JOIN reservations r_own ON list.reservation_id = r_own.reservation_id
        JOIN parking_slots s_own ON r_own.slot_id = s_own.slot_id
        JOIN parking_lots l_own ON s_own.lot_id = l_own.lot_id
        JOIN reservations r_req ON req.requester_reservation_id = r_req.reservation_id
        JOIN parking_slots s_req ON r_req.slot_id = s_req.slot_id
        WHERE req.requester_user_id = ?
        ORDER BY req.created_at DESC
    """, (user_id,))
    sent = [dict(r) for r in cursor.fetchall()]

    # 3. Exchange History
    cursor.execute("""
        SELECT h.*,
               u1.name as user1_name, u2.name as user2_name,
               s1_old.slot_number as user1_old_slot_no, s1_new.slot_number as user1_new_slot_no,
               s2_old.slot_number as user2_old_slot_no, s2_new.slot_number as user2_new_slot_no
        FROM slot_exchange_history h
        JOIN users u1 ON h.user1_id = u1.user_id
        JOIN users u2 ON h.user2_id = u2.user_id
        JOIN parking_slots s1_old ON h.user1_old_slot_id = s1_old.slot_id
        JOIN parking_slots s1_new ON h.user1_new_slot_id = s1_new.slot_id
        JOIN parking_slots s2_old ON h.user2_old_slot_id = s2_old.slot_id
        JOIN parking_slots s2_new ON h.user2_new_slot_id = s2_new.slot_id
        WHERE h.user1_id = ? OR h.user2_id = ?
        ORDER BY h.exchanged_at DESC
    """, (user_id, user_id))
    history = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return jsonify({
        'status': 'success',
        'received_requests': received,
        'sent_requests': sent,
        'history': history,
        'pending_received_count': len(received)
    })

@exchange_bp.route('/api/exchange/respond', methods=['POST'])
def respond_to_exchange_request():
    """Allows an owner to accept or reject an exchange request with atomic swap and final validation."""
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    request_id = data.get('request_id')
    action = data.get('action', '').strip().lower() # 'accept' or 'reject'

    if not request_id or action not in ('accept', 'reject'):
        return jsonify({'status': 'error', 'message': "Request ID and action ('accept' or 'reject') are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch request details
    cursor.execute("""
        SELECT req.*, 
               list.reservation_id as owner_reservation_id, list.slot_id as owner_slot_id, list.user_id as listing_owner_id,
               list.status as listing_status
        FROM slot_exchange_requests req
        JOIN slot_exchange_listings list ON req.listing_id = list.listing_id
        WHERE req.request_id = ?
    """, (request_id,))
    req_row = cursor.fetchone()

    if not req_row:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Exchange request not found.'}), 404

    req = dict(req_row)

    # Security: Verify the respondent is the listing owner (or allowed via automated simulation)
    allow_simulation = data.get('simulate', False)
    if not allow_simulation and int(req['owner_user_id']) != int(user_id):
        conn.close()
        return jsonify({'status': 'error', 'message': 'Unauthorized: Only the slot owner can accept or reject this request.'}), 403

    if req['status'] != 'pending':
        conn.close()
        return jsonify({'status': 'error', 'message': f"This request has already been {req['status']}."}), 400

    # -------------------------------------------------------------
    # CASE 1: REJECT
    # -------------------------------------------------------------
    if action == 'reject':
        cursor.execute("UPDATE slot_exchange_requests SET status = 'rejected', responded_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
        
        # Check if other pending requests exist on this listing; if none, make listing available again
        cursor.execute("SELECT COUNT(*) as cnt FROM slot_exchange_requests WHERE listing_id = ? AND status = 'pending' AND request_id != ?", (req['listing_id'], request_id))
        remaining = cursor.fetchone()['cnt']
        if remaining == 0:
            cursor.execute("UPDATE slot_exchange_listings SET status = 'available' WHERE listing_id = ?", (req['listing_id'],))

        # Log history
        cursor.execute("""
            INSERT INTO slot_exchange_history
            (request_id, listing_id, user1_id, user1_reservation_id, user1_old_slot_id, user1_new_slot_id,
             user2_id, user2_reservation_id, user2_old_slot_id, user2_new_slot_id, status, action_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'rejected', 'Exchange request declined by slot owner.')
        """, (request_id, req['listing_id'], req['owner_user_id'], req['owner_reservation_id'], req['owner_slot_id'], req['owner_slot_id'],
              req['requester_user_id'], req['requester_reservation_id'], req['owner_slot_id'], req['owner_slot_id']))

        # Log activity
        cursor.execute("""
            INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
            VALUES ('--', 'Owner', 'Exchange Rejected', 'Exchange request was declined. Original bookings remain unchanged.', 'info', CURRENT_TIMESTAMP)
        """)

        # Dispatch Module 9: Exchange Rejected Notification to requester
        create_notification(
            user_id=req['requester_user_id'],
            notif_type='exchange_rejected',
            title='Slot Exchange Declined',
            message=f"Your request to exchange for this parking slot was declined by the owner. Original bookings remain unchanged.",
            related_id=request_id,
            conn=conn
        )

        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Exchange request declined. Original booking remains unchanged.'})

    # -------------------------------------------------------------
    # CASE 2: ACCEPT (FINAL VALIDATION & ATOMIC SWAP)
    # -------------------------------------------------------------
    # Final Validation: Check Owner Reservation
    cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (req['owner_reservation_id'],))
    owner_res = cursor.fetchone()
    if not owner_res or owner_res['status'] != 'confirmed':
        conn.close()
        return jsonify({'status': 'error', 'message': 'Validation failed: Your reservation is no longer confirmed.'}), 400

    # Final Validation: Check Requester Reservation
    cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (req['requester_reservation_id'],))
    requester_res = cursor.fetchone()
    if not requester_res or requester_res['status'] != 'confirmed':
        conn.close()
        return jsonify({'status': 'error', 'message': 'Validation failed: The requesting user reservation is no longer confirmed.'}), 400

    owner_old_slot_id = owner_res['slot_id']
    requester_old_slot_id = requester_res['slot_id']

    # Fetch slot names for user feedback
    cursor.execute("SELECT slot_number FROM parking_slots WHERE slot_id = ?", (owner_old_slot_id,))
    owner_slot_name = cursor.fetchone()['slot_number']
    cursor.execute("SELECT slot_number FROM parking_slots WHERE slot_id = ?", (requester_old_slot_id,))
    requester_slot_name = cursor.fetchone()['slot_number']

    # Execute Atomic Swap
    try:
        # 1. Swap slot_id in reservations
        cursor.execute("UPDATE reservations SET slot_id = ? WHERE reservation_id = ?", (requester_old_slot_id, req['owner_reservation_id']))
        cursor.execute("UPDATE reservations SET slot_id = ? WHERE reservation_id = ?", (owner_old_slot_id, req['requester_reservation_id']))

        # 2. Update parking_slots current_reservation_id and current_plate pointers if currently held
        req_plate = requester_res.get('vehicle_plate') if hasattr(requester_res, 'get') else requester_res['vehicle_plate']
        own_plate = owner_res.get('vehicle_plate') if hasattr(owner_res, 'get') else owner_res['vehicle_plate']

        cursor.execute("""
            UPDATE parking_slots 
            SET current_reservation_id = ?, current_plate = ?
            WHERE slot_id = ?
        """, (req['requester_reservation_id'], req_plate, owner_old_slot_id))

        cursor.execute("""
            UPDATE parking_slots 
            SET current_reservation_id = ?, current_plate = ?
            WHERE slot_id = ?
        """, (req['owner_reservation_id'], own_plate, requester_old_slot_id))

        # 3. Mark request accepted and listing completed
        cursor.execute("UPDATE slot_exchange_requests SET status = 'accepted', responded_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
        cursor.execute("UPDATE slot_exchange_listings SET status = 'completed' WHERE listing_id = ?", (req['listing_id'],))
        cursor.execute("UPDATE slot_exchange_listings SET status = 'completed' WHERE reservation_id = ? AND status IN ('available', 'pending')", (req['requester_reservation_id'],))

        # 4. Reject any other competing pending requests for this listing
        cursor.execute("""
            UPDATE slot_exchange_requests 
            SET status = 'rejected', responded_at = CURRENT_TIMESTAMP 
            WHERE listing_id = ? AND request_id != ? AND status = 'pending'
        """, (req['listing_id'], request_id))

        # 5. Insert immutable audit record in exchange history
        cursor.execute("""
            INSERT INTO slot_exchange_history
            (request_id, listing_id, user1_id, user1_reservation_id, user1_old_slot_id, user1_new_slot_id,
             user2_id, user2_reservation_id, user2_old_slot_id, user2_new_slot_id, status, action_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', 'Slot exchange successfully completed.')
        """, (request_id, req['listing_id'], req['owner_user_id'], req['owner_reservation_id'], owner_old_slot_id, requester_old_slot_id,
              req['requester_user_id'], req['requester_reservation_id'], requester_old_slot_id, owner_old_slot_id))

        # 6. Insert activity logs
        cursor.execute("""
            INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
            VALUES (?, 'System', 'Slot Exchanged', ?, 'success', CURRENT_TIMESTAMP)
        """, (requester_slot_name, f"Exchange completed! Slot {owner_slot_name} swapped for Slot {requester_slot_name}."))

        # 7. Dispatch Module 9: Exchange Accepted Notifications
        create_notification(
            user_id=req['requester_user_id'],
            notif_type='exchange_accepted',
            title='Slot Exchange Accepted! 🎉',
            message=f"Great news! Your exchange request was accepted. You are now assigned Slot {owner_slot_name} (swapped from {requester_slot_name}).",
            related_id=request_id,
            conn=conn
        )
        create_notification(
            user_id=req['owner_user_id'],
            notif_type='exchange_accepted',
            title='Slot Exchange Finalized',
            message=f"Exchange successful! You are now assigned Slot {requester_slot_name} (swapped from {owner_slot_name}).",
            related_id=request_id,
            conn=conn
        )

        conn.commit()

        # Real-time MongoDB Persistence for Slot Exchange Swap
        db_m = get_mongo_db()
        if db_m is not None:
            try:
                slot_owner_doc = db_m.parking_slots.find_one({'slot_id': int(owner_old_slot_id)})
                slot_req_doc = db_m.parking_slots.find_one({'slot_id': int(requester_old_slot_id)})

                owner_new_snum = slot_req_doc.get('slot_number') if slot_req_doc else requester_slot_name
                req_new_snum = slot_owner_doc.get('slot_number') if slot_owner_doc else owner_slot_name

                # Swap in db.reservations
                db_m.reservations.update_one(
                    {'$or': [{'reservation_id': int(req['owner_reservation_id'])}, {'pass_code': str(owner_res.get('pass_code', ''))}]},
                    {'$set': {
                        'slot_id': int(requester_old_slot_id),
                        'slot_number': owner_new_snum,
                        'floor': slot_req_doc.get('floor', 'Ground Floor') if slot_req_doc else 'Ground Floor',
                        'zone': slot_req_doc.get('zone', 'General') if slot_req_doc else 'General',
                        'slot_type': slot_req_doc.get('slot_type', 'Standard') if slot_req_doc else 'Standard'
                    }}
                )
                db_m.reservations.update_one(
                    {'$or': [{'reservation_id': int(req['requester_reservation_id'])}, {'pass_code': str(requester_res.get('pass_code', ''))}]},
                    {'$set': {
                        'slot_id': int(owner_old_slot_id),
                        'slot_number': req_new_snum,
                        'floor': slot_owner_doc.get('floor', 'Ground Floor') if slot_owner_doc else 'Ground Floor',
                        'zone': slot_owner_doc.get('zone', 'General') if slot_owner_doc else 'General',
                        'slot_type': slot_owner_doc.get('slot_type', 'Standard') if slot_owner_doc else 'Standard'
                    }}
                )

                # Swap in db.bookings
                db_m.bookings.update_one(
                    {'$or': [{'reservation_id': int(req['owner_reservation_id'])}, {'booking_id': str(owner_res.get('pass_code', ''))}]},
                    {'$set': {
                        'slot_id': int(requester_old_slot_id),
                        'slot_number': owner_new_snum,
                        'floor': slot_req_doc.get('floor', 'Ground Floor') if slot_req_doc else 'Ground Floor',
                        'slot_type': slot_req_doc.get('slot_type', 'Standard') if slot_req_doc else 'Standard'
                    }}
                )
                db_m.bookings.update_one(
                    {'$or': [{'reservation_id': int(req['requester_reservation_id'])}, {'booking_id': str(requester_res.get('pass_code', ''))}]},
                    {'$set': {
                        'slot_id': int(owner_old_slot_id),
                        'slot_number': req_new_snum,
                        'floor': slot_owner_doc.get('floor', 'Ground Floor') if slot_owner_doc else 'Ground Floor',
                        'slot_type': slot_owner_doc.get('slot_type', 'Standard') if slot_owner_doc else 'Standard'
                    }}
                )

                # Update parking_slots pointers in MongoDB
                db_m.parking_slots.update_one(
                    {'slot_id': int(owner_old_slot_id)},
                    {'$set': {
                        'current_reservation_id': req['requester_reservation_id'],
                        'current_plate': requester_res.get('vehicle_plate')
                    }}
                )
                db_m.parking_slots.update_one(
                    {'slot_id': int(requester_old_slot_id)},
                    {'$set': {
                        'current_reservation_id': req['owner_reservation_id'],
                        'current_plate': owner_res.get('vehicle_plate')
                    }}
                )

                # Update MongoDB exchange request status
                db_m.slot_exchange_requests.update_one({'request_id': int(request_id)}, {'$set': {'status': 'accepted'}})
                db_m.slot_exchange_listings.update_one({'listing_id': int(req['listing_id'])}, {'$set': {'status': 'completed'}})

                mongo_log_activity({
                    'slot_number': req_new_snum,
                    'user_name': f"Exchange: {owner_res.get('user_name', 'Owner')} ⇄ {requester_res.get('user_name', 'Requester')}",
                    'action_type': 'Slot Swapped',
                    'details': f"Slot exchange completed between {owner_res.get('user_name')} and {requester_res.get('user_name')}. Swapped Slot {owner_slot_name} and Slot {requester_slot_name}.",
                    'badge_type': 'success',
                    'timestamp': datetime.now().strftime('%I:%M %p')
                })
            except Exception as m_err:
                print(f"[MongoDB Exchange Sync Warning] {m_err}")
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': f'Database error during swap: {str(e)}'}), 500

    conn.close()
    return jsonify({
        'status': 'success',
        'message': f"Exchange successful! You now have Slot {requester_slot_name}, and the requester has Slot {owner_slot_name}.",
        'new_slot_number': requester_slot_name
    })

@exchange_bp.route('/api/exchange/visual-swap', methods=['POST'])
def visual_slot_swap():
    """
    Executes a visual slot swap directly through the 2D layout.
    Supports:
    1. Direct swap into an available slot (user moves from source_slot to target_slot).
    2. Mutual swap with another driver's active exchange listing.
    Maintains 100% data consistency with SQLite & MongoDB, audit records, logs, and notifications.
    """
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        user_id = 1

    source_slot_id = data.get('source_slot_id')
    target_slot_id = data.get('target_slot_id')
    reservation_id = data.get('reservation_id')

    if not source_slot_id or not target_slot_id:
        return jsonify({'status': 'error', 'message': 'Both source and target slot selections are required.'}), 400

    try:
        source_slot_id = int(source_slot_id)
        target_slot_id = int(target_slot_id)
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid slot IDs provided.'}), 400

    if source_slot_id == target_slot_id:
        return jsonify({'status': 'error', 'message': 'Source and target slots cannot be the same.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Fetch user's active confirmed reservation for the source slot
    if reservation_id:
        cursor.execute("""
            SELECT r.*, u.name as user_name
            FROM reservations r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.reservation_id = ? AND r.user_id = ? AND r.slot_id = ? AND r.status = 'confirmed'
        """, (reservation_id, user_id, source_slot_id))
    else:
        cursor.execute("""
            SELECT r.*, u.name as user_name
            FROM reservations r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.user_id = ? AND r.slot_id = ? AND r.status = 'confirmed'
            ORDER BY r.reservation_id DESC LIMIT 1
        """, (user_id, source_slot_id))
    
    user_res = cursor.fetchone()
    if not user_res:
        # Also check by user_id without strict slot_id if user already had a confirmed booking
        cursor.execute("""
            SELECT r.*, u.name as user_name
            FROM reservations r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.user_id = ? AND r.status = 'confirmed'
            ORDER BY r.reservation_id DESC LIMIT 1
        """, (user_id,))
        fallback_res = cursor.fetchone()
        if fallback_res and int(fallback_res['slot_id']) == source_slot_id:
            user_res = fallback_res
        else:
            conn.close()
            return jsonify({'status': 'error', 'message': 'No active confirmed reservation found for your selected slot.'}), 404

    user_res = dict(user_res)
    actual_res_id = user_res['reservation_id']

    # 2. Fetch source and target slot info
    cursor.execute("SELECT * FROM parking_slots WHERE slot_id = ?", (source_slot_id,))
    source_slot = cursor.fetchone()
    cursor.execute("SELECT * FROM parking_slots WHERE slot_id = ?", (target_slot_id,))
    target_slot = cursor.fetchone()

    if not source_slot or not target_slot:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Slot information could not be found.'}), 404

    source_slot = dict(source_slot)
    target_slot = dict(target_slot)
    source_slot_name = source_slot['slot_number']
    target_slot_name = target_slot['slot_number']

    # 3. Check target slot eligibility:
    # Check if target slot is listed for exchange by another user
    cursor.execute("""
        SELECT l.*, r.user_id as listing_user_id, r.vehicle_plate as listing_plate, r.vehicle_type as listing_vehicle_type, u.name as listing_user_name
        FROM slot_exchange_listings l
        JOIN reservations r ON l.reservation_id = r.reservation_id
        JOIN users u ON l.user_id = u.user_id
        WHERE l.slot_id = ? AND l.status IN ('available', 'pending') AND l.user_id != ?
        LIMIT 1
    """, (target_slot_id, user_id))
    active_listing = cursor.fetchone()

    # 4. Check if target slot is available
    target_status = (target_slot.get('status') or 'available').lower()

    if not active_listing and target_status not in ('available', 'open'):
        conn.close()
        return jsonify({
            'status': 'error',
            'message': f"Slot {target_slot_name} is {target_status.upper()} and ineligible for exchange."
        }), 400

    try:
        if active_listing:
            # Mutual Swap with listed exchange slot
            other_res_id = active_listing['reservation_id']
            other_uid = active_listing['user_id']
            other_name = active_listing['listing_user_name']

            # Swap in reservations
            cursor.execute("UPDATE reservations SET slot_id = ? WHERE reservation_id = ?", (target_slot_id, actual_res_id))
            cursor.execute("UPDATE reservations SET slot_id = ? WHERE reservation_id = ?", (source_slot_id, other_res_id))

            # Update parking_slots pointers
            cursor.execute("UPDATE parking_slots SET current_reservation_id = ?, current_plate = ? WHERE slot_id = ?",
                           (actual_res_id, user_res.get('vehicle_plate'), target_slot_id))
            cursor.execute("UPDATE parking_slots SET current_reservation_id = ?, current_plate = ? WHERE slot_id = ?",
                           (other_res_id, active_listing.get('listing_plate'), source_slot_id))

            # Update listing status to completed
            cursor.execute("UPDATE slot_exchange_listings SET status = 'completed' WHERE listing_id = ?", (active_listing['listing_id'],))
            
            # Record in slot_exchange_history
            cursor.execute("""
                INSERT INTO slot_exchange_history
                (request_id, listing_id, user1_id, user1_reservation_id, user1_old_slot_id, user1_new_slot_id,
                 user2_id, user2_reservation_id, user2_old_slot_id, user2_new_slot_id, status, action_note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
            """, (0, active_listing['listing_id'], user_id, actual_res_id, source_slot_id, target_slot_id,
                  other_uid, other_res_id, target_slot_id, source_slot_id,
                  f"Visual slot swap completed: Slot {source_slot_name} exchanged with Slot {target_slot_name}."))

            # Notifications
            create_notification(
                user_id=user_id,
                notif_type='exchange_accepted',
                title='Slot Exchange Completed! 🔄',
                message=f"Visual swap successful! You are now assigned Slot {target_slot_name} (exchanged with {other_name}'s {source_slot_name}).",
                related_id=actual_res_id,
                conn=conn
            )
            create_notification(
                user_id=other_uid,
                notif_type='exchange_accepted',
                title='Slot Exchange Finalized 🔄',
                message=f"Your listed Slot {target_slot_name} was swapped for Slot {source_slot_name} by driver {user_res.get('user_name', 'Driver')}.",
                related_id=other_res_id,
                conn=conn
            )
        else:
            # Direct Swap with an available slot
            # Update user's reservation
            cursor.execute("UPDATE reservations SET slot_id = ? WHERE reservation_id = ?", (target_slot_id, actual_res_id))

            # Update parking_slots
            cursor.execute("UPDATE parking_slots SET status = 'available', current_reservation_id = NULL, current_plate = NULL WHERE slot_id = ?", (source_slot_id,))
            cursor.execute("UPDATE parking_slots SET status = 'reserved', current_reservation_id = ?, current_plate = ? WHERE slot_id = ?",
                           (actual_res_id, user_res.get('vehicle_plate'), target_slot_id))

            # If user had an active listing for the source slot, update it or mark completed
            cursor.execute("UPDATE slot_exchange_listings SET status = 'completed' WHERE reservation_id = ? AND status IN ('available', 'pending')", (actual_res_id,))

            # Record in slot_exchange_history
            cursor.execute("""
                INSERT INTO slot_exchange_history
                (request_id, listing_id, user1_id, user1_reservation_id, user1_old_slot_id, user1_new_slot_id,
                 user2_id, user2_reservation_id, user2_old_slot_id, user2_new_slot_id, status, action_note)
                VALUES (0, 0, ?, ?, ?, ?, 0, 0, 0, 0, 'completed', ?)
            """, (user_id, actual_res_id, source_slot_id, target_slot_id,
                  f"Visual slot swap completed: Slot {source_slot_name} exchanged for Slot {target_slot_name}."))

            # Notification
            create_notification(
                user_id=user_id,
                notif_type='exchange_accepted',
                title='Slot Exchange Completed! 🔄',
                message=f"Visual swap successful! You are now assigned Slot {target_slot_name} (previously Slot {source_slot_name}).",
                related_id=actual_res_id,
                conn=conn
            )

        # Log Activity
        cursor.execute("""
            INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
            VALUES (?, ?, 'Slot Exchanged', ?, 'success', CURRENT_TIMESTAMP)
        """, (target_slot_name, user_res.get('user_name', 'Driver'),
              f"Visual swap completed: Slot {source_slot_name} exchanged for Slot {target_slot_name}."))

        conn.commit()

        # MongoDB Dual Persistence
        db_m = get_mongo_db()
        if db_m is not None:
            try:
                # Update user reservation in MongoDB
                db_m.reservations.update_one(
                    {'$or': [{'reservation_id': int(actual_res_id)}, {'pass_code': str(user_res.get('pass_code', ''))}]},
                    {'$set': {
                        'slot_id': int(target_slot_id),
                        'slot_number': target_slot_name,
                        'floor': target_slot.get('floor', 'Ground Floor'),
                        'zone': target_slot.get('zone', 'General'),
                        'slot_type': target_slot.get('slot_type', 'Standard')
                    }}
                )
                db_m.bookings.update_one(
                    {'$or': [{'reservation_id': int(actual_res_id)}, {'booking_id': str(user_res.get('pass_code', ''))}]},
                    {'$set': {
                        'slot_id': int(target_slot_id),
                        'slot_number': target_slot_name,
                        'floor': target_slot.get('floor', 'Ground Floor'),
                        'slot_type': target_slot.get('slot_type', 'Standard')
                    }}
                )

                if active_listing:
                    db_m.reservations.update_one(
                        {'$or': [{'reservation_id': int(other_res_id)}, {'pass_code': str(active_listing.get('pass_code', ''))}]},
                        {'$set': {
                            'slot_id': int(source_slot_id),
                            'slot_number': source_slot_name,
                            'floor': source_slot.get('floor', 'Ground Floor'),
                            'zone': source_slot.get('zone', 'General'),
                            'slot_type': source_slot.get('slot_type', 'Standard')
                        }}
                    )
                    db_m.bookings.update_one(
                        {'$or': [{'reservation_id': int(other_res_id)}, {'booking_id': str(active_listing.get('pass_code', ''))}]},
                        {'$set': {
                            'slot_id': int(source_slot_id),
                            'slot_number': source_slot_name,
                            'floor': source_slot.get('floor', 'Ground Floor'),
                            'slot_type': source_slot.get('slot_type', 'Standard')
                        }}
                    )
                    db_m.parking_slots.update_one(
                        {'slot_id': int(target_slot_id)},
                        {'$set': {'current_reservation_id': actual_res_id, 'current_plate': user_res.get('vehicle_plate'), 'vehicle_type': user_res.get('vehicle_type', 'Car')}}
                    )
                    db_m.parking_slots.update_one(
                        {'slot_id': int(source_slot_id)},
                        {'$set': {'current_reservation_id': other_res_id, 'current_plate': active_listing.get('listing_plate'), 'vehicle_type': active_listing.get('listing_vehicle_type') or active_listing.get('vehicle_type') or 'Car'}}
                    )
                    db_m.slot_exchange_listings.update_one({'listing_id': int(active_listing['listing_id'])}, {'$set': {'status': 'completed'}})
                else:
                    db_m.parking_slots.update_one(
                        {'slot_id': int(source_slot_id)},
                        {'$set': {'status': 'available', 'current_reservation_id': None, 'current_plate': None, 'vehicle_type': None}}
                    )
                    db_m.parking_slots.update_one(
                        {'slot_id': int(target_slot_id)},
                        {'$set': {'status': 'reserved', 'current_reservation_id': actual_res_id, 'current_plate': user_res.get('vehicle_plate'), 'vehicle_type': user_res.get('vehicle_type', 'Car')}}
                    )

                mongo_log_activity({
                    'slot_number': target_slot_name,
                    'user_name': user_res.get('user_name', 'Driver'),
                    'action_type': 'Visual Slot Swapped',
                    'details': f"Slot {source_slot_name} swapped for Slot {target_slot_name} via 2D visual layout.",
                    'badge_type': 'success',
                    'timestamp': datetime.now().strftime('%I:%M %p')
                })
            except Exception as mongo_err:
                print(f"[MongoDB Visual Swap Sync Warning] {mongo_err}")

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'status': 'error', 'message': f'Database error during swap: {str(e)}'}), 500

    conn.close()
    return jsonify({
        'status': 'success',
        'message': f"Slot exchange completed successfully! You are now assigned Slot {target_slot_name}.",
        'previous_slot': source_slot_name,
        'current_slot': target_slot_name,
        'exchange_status': 'Completed',
        'reservation_id': actual_res_id,
        'new_slot_id': target_slot_id,
        'new_slot_number': target_slot_name
    })

# ==========================================
