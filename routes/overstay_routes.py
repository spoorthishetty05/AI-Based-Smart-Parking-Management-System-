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

from core.overstay_engine import (
    check_and_update_overstays, get_active_overstays, resolve_overstay,
    get_current_sim_time, get_overstay_management_data, mark_overstay_paid,
    get_user_active_overstay, normalize_vehicle_type, calculate_overstay,
    get_overstay_dashboard_data, complete_parking_session
)
from core.email_service import send_templated_email
from core.ml_engine import predict_occupancy

overstay_bp = Blueprint('overstay', __name__)


# OVERSTAY & ALERT APIs
# ==========================================

@overstay_bp.route('/api/overstays', methods=['GET'])
def list_overstays():
    """Returns overstay violations, 6 KPI summary cards, and dynamic penalty calculations."""
    mgmt_data = get_overstay_management_data()
    filter_type = request.args.get('filter', 'all').lower()
    
    records = mgmt_data['overstays']
    if filter_type == 'active':
        records = [r for r in records if r.get('status') == 'active']
    elif filter_type == 'resolved':
        records = [r for r in records if r.get('status') == 'resolved']
    elif filter_type == 'pending':
        records = [r for r in records if (r.get('payment_status') or '').lower() == 'pending']
    elif filter_type == 'paid':
        records = [r for r in records if (r.get('payment_status') or '').lower() == 'paid']

    return jsonify({
        'status': 'success',
        'summary': mgmt_data['summary'],
        'overstays': records,
        'active_count': mgmt_data['summary']['active_overstays'],
        'total_count': len(records)
    })

@overstay_bp.route('/api/overstays/resolve/<int:overstay_id>', methods=['POST'])
def api_resolve_overstay(overstay_id):
    """Settle or waive an overstay incident and record vehicle exit."""
    data = request.get_json() or {}
    resolution_type = data.get('resolution_type', 'settled')  # 'settled' or 'waived'
    success, msg = resolve_overstay(overstay_id, resolution_type=resolution_type)
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@overstay_bp.route('/api/overstays/<int:overstay_id>/exit', methods=['POST'])
def api_overstay_record_exit(overstay_id):
    """Admin action to record vehicle exit directly from Overstay Management table."""
    data = request.get_json() or {}
    resolution_type = data.get('resolution_type', 'exited')
    success, msg = resolve_overstay(overstay_id, resolution_type=resolution_type)
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@overstay_bp.route('/api/overstays/<int:overstay_id>/mark-paid', methods=['POST'])
def api_overstay_mark_paid(overstay_id):
    """Admin action to mark an overstay penalty payment status as Paid."""
    success, msg = mark_overstay_paid(overstay_id)
    return jsonify({'status': 'success' if success else 'error', 'message': msg})

@overstay_bp.route('/api/user/active-overstay', methods=['GET'])
def api_user_active_overstay():
    """Returns active overstay details for the authenticated user for real-time warning card."""
    uid = session.get('user_id') or request.args.get('user_id')
    if uid:
        try:
            uid = int(uid)
        except (ValueError, TypeError):
            pass
    if not uid:
        return jsonify({'status': 'success', 'has_overstay': False, 'overstay': None})

    ov = get_user_active_overstay(uid)
    return jsonify({
        'status': 'success',
        'has_overstay': bool(ov),
        'overstay': ov
    })

@overstay_bp.route('/api/overstay', methods=['GET'])
@overstay_bp.route('/api/overstay/dashboard', methods=['GET'])
def api_overstay_dashboard():
    """Returns dedicated Overstay Dashboard data with 5 summary cards and 12-column table records."""
    data = get_overstay_dashboard_data()
    return jsonify({
        'status': 'success',
        'summary': data['summary'],
        'records': data['records'],
        'overstays': data.get('overstays', data['records'])
    })

@overstay_bp.route('/api/overstay/active', methods=['GET'])
def api_overstay_active():
    """Returns currently active overstays."""
    records = get_active_overstays()
    return jsonify({
        'status': 'success',
        'count': len(records),
        'records': records
    })

@overstay_bp.route('/api/overstay/history', methods=['GET'])
def api_overstay_history():
    """Returns resolved overstay history."""
    db = get_mongo_db()
    docs = list(db.overstay_records.find({'status': 'resolved'}).sort('resolved_at', -1))
    for d in docs:
        d.pop('_id', None)
    return jsonify({
        'status': 'success',
        'count': len(docs),
        'records': docs
    })

@overstay_bp.route('/api/overstay/check', methods=['POST'])
def api_overstay_check():
    """Triggers real-time overstay evaluation and returns detected alerts."""
    sim_time = get_current_sim_time()
    alerts = check_and_update_overstays(sim_time)
    return jsonify({
        'status': 'success',
        'alerts_generated': len(alerts),
        'alerts': alerts,
        'simulated_time': sim_time.strftime('%Y-%m-%d %H:%M:%S')
    })

@overstay_bp.route('/api/overstay/complete', methods=['POST'])
def api_overstay_complete():
    """Completes an active parking session and resolves any active overstay."""
    data = request.get_json() or {}
    res_id = data.get('reservation_id') or data.get('booking_id') or data.get('overstay_id')
    if not res_id:
        return jsonify({'status': 'error', 'message': 'Reservation ID or Booking ID is required.'}), 400
    
    success, msg = complete_parking_session(res_id)
    if success:
        return jsonify({'status': 'success', 'message': msg})
    return jsonify({'status': 'error', 'message': msg}), 400

@overstay_bp.route('/api/overstay/notify', methods=['POST'])
def api_overstay_notify():
    """Dispatches real-time overstay notification alert to the vehicle driver."""
    data = request.get_json() or {}
    vehicle_plate = str(data.get('vehicle') or data.get('vehicle_plate') or '').strip().upper()
    res_id = data.get('reservation_id') or data.get('booking_id')
    db = get_mongo_db()
    
    target_user_id = None
    slot_num = 'Assigned Slot'
    lot_name = 'Smart Parking'

    if db is not None:
        if res_id:
            try:
                r = db.reservations.find_one({'reservation_id': int(res_id)}) or db.bookings.find_one({'reservation_id': int(res_id)})
                if r:
                    target_user_id = r.get('user_id')
                    slot_num = r.get('slot_number', slot_num)
                    lot_name = r.get('lot_name', lot_name)
                    if not vehicle_plate:
                        vehicle_plate = (r.get('vehicle_plate') or '').upper()
            except Exception:
                pass

        if not target_user_id and vehicle_plate:
            v = db.vehicles.find_one({'license_plate': {'$regex': f"^{re.escape(vehicle_plate)}$", '$options': 'i'}})
            if v:
                target_user_id = v.get('user_id')
            else:
                r = db.reservations.find_one({'vehicle_plate': {'$regex': f"^{re.escape(vehicle_plate)}$", '$options': 'i'}})
                if r:
                    target_user_id = r.get('user_id')
                    slot_num = r.get('slot_number', slot_num)

    if not target_user_id:
        target_user_id = session.get('user_id', 1)

    notif_msg = (
        f"⚠️ Parking Overstay Notice: Vehicle {vehicle_plate or 'registered vehicle'} has exceeded "
        f"its allotted parking window at {lot_name} (Slot {slot_num}). Please relocate or extend booking."
    )
    create_notification(
        user_id=target_user_id,
        notif_type='overstay_alert',
        title=f"⚠️ Overstay Alert: {vehicle_plate or 'Vehicle'}",
        message=notif_msg,
        related_id=res_id
    )

    if db is not None and res_id:
        try:
            db.reservations.update_one({'reservation_id': int(res_id)}, {'$set': {'notification_status': 'Sent', 'overstay_notification_sent': True}})
            db.overstay_records.update_one({'reservation_id': int(res_id)}, {'$set': {'notification_status': 'Sent', 'notification_sent': True}})
        except Exception:
            pass

    return jsonify({
        'status': 'success',
        'message': f"Overstay notification successfully dispatched to driver of {vehicle_plate or 'vehicle'}."
    })


# ==========================================

# EXTENDED OVERSTAY & ADMIN CONTROLS
# ==========================================

@overstay_bp.route('/api/overstays/check-now', methods=['POST'])
def trigger_overstay_sweep():
    """Manual trigger to scan and update overstays against system clock."""
    conn = get_db_connection()
    sim_time = get_current_sim_time(conn)
    count = check_and_update_overstays(sim_time)
    conn.close()
    return jsonify({'status': 'success', 'new_overstays_flagged': count, 'simulated_time': sim_time.strftime('%Y-%m-%d %H:%M:%S')})

@overstay_bp.route('/api/admin/users/update-role', methods=['POST'])
@admin_required
def update_user_role():
    """Updates user authorization role ('admin' vs 'user')."""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    new_role = data.get('role', 'user')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': f"User role updated to '{new_role}'."})

@overstay_bp.route('/api/admin/reservations', methods=['GET'])
@admin_required
def get_all_reservations():
    """Admin endpoint to view all system reservations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, s.slot_number, s.floor, s.zone, u.name as user_name, u.email as user_email
        FROM reservations r
        JOIN parking_slots s ON r.slot_id = s.slot_id
        JOIN users u ON r.user_id = u.user_id
        ORDER BY r.reservation_id DESC
        LIMIT 100
    """)
    reservations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'status': 'success', 'reservations': reservations})

@overstay_bp.route('/api/admin/reservations/force-checkout/<int:res_id>', methods=['POST'])
@admin_required
def force_checkout_reservation(res_id):
    """Admin force-checkout action to vacate a slot immediately."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT slot_id, vehicle_plate FROM reservations WHERE reservation_id = ?", (res_id,))
    res = cursor.fetchone()
    if not res:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Reservation not found'}), 404

    sim_time = get_current_sim_time(conn)
    cursor.execute("UPDATE reservations SET status = 'completed', actual_exit_time = ? WHERE reservation_id = ?", (sim_time.strftime('%Y-%m-%d %H:%M:%S'), res_id))
    cursor.execute("UPDATE parking_slots SET status = 'available', current_reservation_id = NULL, current_plate = NULL WHERE slot_id = ?", (res['slot_id'],))
    cursor.execute("UPDATE overstay_records SET status = 'resolved', resolved_at = ? WHERE reservation_id = ?", (sim_time.strftime('%Y-%m-%d %H:%M:%S'), res_id))
    
    cursor.execute("""
        INSERT INTO activity_logs (slot_number, user_name, action_type, details, badge_type, timestamp)
        VALUES ((SELECT slot_number FROM parking_slots WHERE slot_id = ?), ?, 'Force Checkout', 'Admin manually vacated slot.', 'info', ?)
    """, (res['slot_id'], res['vehicle_plate'], sim_time.strftime('%I:%M %p')))

    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Slot successfully checked out and restored to Available.'})

@overstay_bp.route('/api/admin/reservations/approve/<int:res_id>', methods=['POST'])
@admin_required
def api_admin_approve_reservation(res_id):
    """Admin approves a booking and confirms reservation status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT r.*, s.slot_number FROM reservations r JOIN parking_slots s ON r.slot_id = s.slot_id WHERE r.reservation_id = ?", (res_id,))
    res = cursor.fetchone()
    if not res:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Reservation not found.'}), 404

    cursor.execute("UPDATE reservations SET status = 'confirmed' WHERE reservation_id = ?", (res_id,))
    cursor.execute("UPDATE parking_slots SET status = 'reserved' WHERE slot_id = ?", (res['slot_id'],))
    create_notification(
        user_id=res['user_id'],
        notif_type='booking_confirmation',
        title='Booking Approved by Admin',
        message=f"Your booking for Slot {res['slot_number']} on {res['date']} has been approved by the Administrator.",
        related_id=res_id,
        conn=conn
    )
    conn.commit()
    conn.close()

    mongo_update_reservation(res_id, {'status': 'confirmed'})
    return jsonify({'status': 'success', 'message': f"Reservation #{res_id} approved."})

@overstay_bp.route('/api/admin/reservations/cancel/<int:res_id>', methods=['POST'])
@admin_required
def api_admin_cancel_reservation(res_id):
    """Admin cancels a reservation and frees the associated slot."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT r.*, s.slot_number FROM reservations r JOIN parking_slots s ON r.slot_id = s.slot_id WHERE r.reservation_id = ?", (res_id,))
    res = cursor.fetchone()
    if not res:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Reservation not found.'}), 404

    cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE reservation_id = ?", (res_id,))
    cursor.execute("UPDATE parking_slots SET status = 'available', current_reservation_id = NULL, current_plate = NULL WHERE slot_id = ?", (res['slot_id'],))
    create_notification(
        user_id=res['user_id'],
        notif_type='cancellation',
        title='Booking Cancelled by Admin',
        message=f"Your booking for Slot {res['slot_number']} has been cancelled by the Administrator.",
        related_id=res_id,
        conn=conn
    )
    conn.commit()
    conn.close()

    mongo_update_reservation(res_id, {'status': 'cancelled'})
    mongo_update_slot(res['slot_id'], {'status': 'available', 'current_reservation_id': None, 'current_plate': None})
    return jsonify({'status': 'success', 'message': f"Reservation #{res_id} cancelled and slot restored to Available."})

@overstay_bp.route('/api/admin/exchange/overview', methods=['GET'])
@admin_required
def api_admin_exchange_overview():
    """Admin overview of all exchange listings, active swap requests, and exchange history."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Listings
    cursor.execute("""
        SELECT l.*, u.name as owner_name, u.email as owner_email, s.slot_number, p.lot_name
        FROM slot_exchange_listings l
        JOIN users u ON l.user_id = u.user_id
        JOIN parking_slots s ON l.slot_id = s.slot_id
        JOIN parking_lots p ON l.lot_id = p.lot_id
        ORDER BY l.listing_id DESC
    """)
    listings = [dict(row) for row in cursor.fetchall()]

    # Requests
    cursor.execute("""
        SELECT req.*, 
               u_req.name as requester_name, u_own.name as owner_name,
               s_req.slot_number as requester_slot_number, s_own.slot_number as owner_slot_number,
               l.lot_id
        FROM slot_exchange_requests req
        JOIN slot_exchange_listings l ON req.listing_id = l.listing_id
        JOIN users u_req ON req.requester_user_id = u_req.user_id
        JOIN users u_own ON req.owner_user_id = u_own.user_id
        JOIN reservations r_req ON req.requester_reservation_id = r_req.reservation_id
        JOIN parking_slots s_req ON r_req.slot_id = s_req.slot_id
        JOIN parking_slots s_own ON l.slot_id = s_own.slot_id
        ORDER BY req.request_id DESC
    """)
    requests_list = [dict(row) for row in cursor.fetchall()]

    # History
    cursor.execute("""
        SELECT h.*, u1.name as user1_name, u2.name as user2_name,
               s1_old.slot_number as user1_old_slot, s1_new.slot_number as user1_new_slot,
               s2_old.slot_number as user2_old_slot, s2_new.slot_number as user2_new_slot
        FROM slot_exchange_history h
        JOIN users u1 ON h.user1_id = u1.user_id
        JOIN users u2 ON h.user2_id = u2.user_id
        JOIN parking_slots s1_old ON h.user1_old_slot_id = s1_old.slot_id
        JOIN parking_slots s1_new ON h.user1_new_slot_id = s1_new.slot_id
        JOIN parking_slots s2_old ON h.user2_old_slot_id = s2_old.slot_id
        JOIN parking_slots s2_new ON h.user2_new_slot_id = s2_new.slot_id
        ORDER BY h.history_id DESC
    """)
    history = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return jsonify({
        'status': 'success',
        'listings': listings,
        'requests': requests_list,
        'history': history
    })

@overstay_bp.route('/api/admin/exchange/moderate', methods=['POST'])
@admin_required
def api_admin_exchange_moderate():
    """Admin moderate exchange request: approve, reject, or cancel."""
    data = request.get_json() or {}
    action = data.get('action', '').strip().lower() # 'approve', 'reject', 'cancel'
    request_id = data.get('request_id')
    listing_id = data.get('listing_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    if action in ('approve', 'accept') and request_id:
        cursor.execute("SELECT * FROM slot_exchange_requests WHERE request_id = ?", (request_id,))
        req_row = cursor.fetchone()
        if not req_row:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Request not found.'}), 404
        req = dict(req_row)

        cursor.execute("SELECT * FROM slot_exchange_listings WHERE listing_id = ?", (req['listing_id'],))
        listing = dict(cursor.fetchone())

        cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (req['requester_reservation_id'],))
        req_res = dict(cursor.fetchone())

        cursor.execute("SELECT * FROM reservations WHERE reservation_id = ?", (listing['reservation_id'],))
        own_res = dict(cursor.fetchone())

        cursor.execute("UPDATE reservations SET slot_id = ? WHERE reservation_id = ?", (listing['slot_id'], req_res['reservation_id']))
        cursor.execute("UPDATE reservations SET slot_id = ? WHERE reservation_id = ?", (req_res['slot_id'], own_res['reservation_id']))
        cursor.execute("UPDATE slot_exchange_requests SET status = 'accepted', responded_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
        cursor.execute("UPDATE slot_exchange_listings SET status = 'completed' WHERE listing_id = ?", (listing['listing_id'],))

        cursor.execute("""
            INSERT INTO slot_exchange_history
            (request_id, listing_id, user1_id, user1_reservation_id, user1_old_slot_id, user1_new_slot_id,
             user2_id, user2_reservation_id, user2_old_slot_id, user2_new_slot_id, status, action_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', 'Admin Approved Exchange')
        """, (
            request_id, listing['listing_id'],
            req['requester_user_id'], req_res['reservation_id'], req_res['slot_id'], listing['slot_id'],
            listing['user_id'], own_res['reservation_id'], listing['slot_id'], req_res['slot_id']
        ))

        create_notification(req['requester_user_id'], 'exchange_accepted', 'Slot Exchange Approved by Admin', 'Your slot exchange has been approved and completed by Administrator.', request_id, conn)
        create_notification(listing['user_id'], 'exchange_accepted', 'Slot Exchange Approved by Admin', 'Your slot exchange has been approved and completed by Administrator.', request_id, conn)

        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Exchange approved and slots swapped successfully.'})

    elif action == 'reject' and request_id:
        cursor.execute("UPDATE slot_exchange_requests SET status = 'rejected', responded_at = CURRENT_TIMESTAMP WHERE request_id = ?", (request_id,))
        cursor.execute("UPDATE slot_exchange_listings SET status = 'available' WHERE listing_id = (SELECT listing_id FROM slot_exchange_requests WHERE request_id = ?)", (request_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Exchange request rejected.'})

    elif action == 'cancel_listing' and listing_id:
        cursor.execute("UPDATE slot_exchange_listings SET status = 'cancelled' WHERE listing_id = ?", (listing_id,))
        cursor.execute("UPDATE slot_exchange_requests SET status = 'cancelled' WHERE listing_id = ? AND status = 'pending'", (listing_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Listing cancelled.'})

    conn.close()
    return jsonify({'status': 'error', 'message': 'Invalid action or parameters.'}), 400

@overstay_bp.route('/api/admin/ai/forecast', methods=['GET'])
@admin_required
def api_admin_ai_forecast():
    """Generates 24-hour occupancy forecast, peak busy periods, and lot recommendations using live MongoDB data and AI model."""
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    db = get_mongo_db()

    # Live slot counts from MongoDB
    total_slots = db.parking_slots.count_documents({})
    occupied_slots = db.parking_slots.count_documents({'status': 'occupied'})
    reserved_slots = db.parking_slots.count_documents({'status': 'reserved'})
    in_use_slots = occupied_slots + reserved_slots
    available_slots = db.parking_slots.count_documents({'status': 'available'})
    if available_slots + in_use_slots != total_slots and total_slots > 0:
        available_slots = max(0, total_slots - in_use_slots)
    current_occupancy = round((in_use_slots / total_slots * 100), 1) if total_slots > 0 else 0.0

    forecast_points = []
    busy_hours = []
    max_hour = 17
    max_occ = 0.0

    for h in range(0, 24):
        pred = predict_occupancy(target_date, f"{h:02d}:00", floor='All')
        occ_val = round(pred.get('predicted_occupancy', pred.get('predicted_occupancy_percentage', 50.0)), 1)
        if occ_val > max_occ:
            max_occ = occ_val
            max_hour = h
        forecast_points.append({
            'hour': f"{h:02d}:00",
            'occupancy_percentage': occ_val,
            'traffic_level': pred.get('traffic_level', 'Medium')
        })
        if occ_val >= 65.0:
            busy_hours.append(h)

    # Compute contiguous busy hour ranges
    busy_ranges = []
    if busy_hours:
        start_h = busy_hours[0]
        prev_h = start_h
        for curr_h in busy_hours[1:]:
            if curr_h == prev_h + 1:
                prev_h = curr_h
            else:
                busy_ranges.append(f"{start_h:02d}:00 – {min(24, prev_h + 1):02d}:00")
                start_h = curr_h
                prev_h = curr_h
        busy_ranges.append(f"{start_h:02d}:00 – {min(24, prev_h + 1):02d}:00")
    else:
        busy_ranges = [f"{max_hour:02d}:00 – {min(24, max_hour + 2):02d}:00"]

    predicted_peak_hour = f"{max_hour:02d}:00 - {min(24, max_hour + 1):02d}:00"
    predicted_peak_occupancy = round(max_occ)

    current_hour = datetime.now().hour
    upcoming_busy = [r for r in busy_ranges if int(r.split('–')[0].split(':')[0]) >= current_hour]
    next_busy_period = upcoming_busy[0] if upcoming_busy else busy_ranges[0]
    busy_periods_banner = f"Today: {busy_ranges[0]}"

    # Floor-based recommendations from MongoDB
    floors = db.parking_slots.distinct('floor')
    palette = ['#14b8a6', '#38bdf8', '#a855f7', '#06b6d4', '#f59e0b']
    recommended = []
    for idx, fl in enumerate(floors):
        f_total = db.parking_slots.count_documents({'floor': fl})
        f_avail = db.parking_slots.count_documents({'floor': fl, 'status': 'available'})
        recommended.append({
            'floor': fl,
            'available': f_avail,
            'total': f_total,
            'color': palette[idx % len(palette)]
        })

    if not recommended:
        recommended = [
            {'floor': 'Ground Floor', 'available': available_slots, 'total': total_slots, 'color': '#14b8a6'}
        ]

    return jsonify({
        'status': 'success',
        'target_date': target_date,
        'current_occupancy': round(current_occupancy),
        'total_slots': total_slots,
        'occupied_slots': in_use_slots,
        'available_slots': available_slots,
        'predicted_peak_hour': predicted_peak_hour,
        'predicted_peak_occupancy': predicted_peak_occupancy,
        'next_busy_period': next_busy_period,
        'busy_periods_banner': busy_periods_banner,
        'forecast': forecast_points,
        'busy_periods': busy_ranges,
        'recommended_areas': recommended
    })

@overstay_bp.route('/api/admin/settings/update', methods=['POST'])
@admin_required
def update_system_settings():
    """Updates global parameters: grace period, simulation speed, pricing."""
    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor()

    for key, val in data.items():
        cursor.execute("INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES (?, ?)", (key, str(val)))

    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'System settings saved.'})

@overstay_bp.route('/api/reports/export-csv', methods=['GET'])
def export_reports_csv():
    """Exports system reservations and parking utilization from MongoDB as a downloadable CSV."""
    db = get_mongo_db()
    reservations = list(db.reservations.find().sort('reservation_id', -1))

    users_map = {u.get('user_id'): u.get('name', 'User') for u in db.users.find()}
    slots_map = {s.get('slot_id'): s for s in db.parking_slots.find()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Reservation ID', 'Date', 'Start Time', 'End Time', 'Vehicle Plate', 'Slot Number', 'Floor', 'Zone', 'Slot Type', 'User Name', 'Status', 'Total Fee (INR)', 'Created At'])

    for r in reservations:
        s = slots_map.get(r.get('slot_id'), {})
        user_name = users_map.get(r.get('user_id'), r.get('driver_name', 'Customer'))
        writer.writerow([
            r.get('reservation_id', ''),
            r.get('date', ''),
            r.get('start_time', ''),
            r.get('end_time', ''),
            r.get('vehicle_plate', ''),
            s.get('slot_number', r.get('slot_number', '')),
            s.get('floor', r.get('floor', '')),
            s.get('zone', r.get('zone', '')),
            s.get('slot_type', r.get('slot_type', '')),
            user_name,
            r.get('status', ''),
            r.get('total_amount', 0),
            r.get('created_at', '')
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=smart_parking_report.csv"}
    )

# ==========================================
