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
from core.overstay_engine import normalize_vehicle_type, get_current_sim_time

user_bp = Blueprint('user', __name__)


# USER PROFILE & VEHICLE MANAGEMENT APIs (MODULE 1)
# ==========================================

@user_bp.route('/api/users/profile', methods=['GET'])
def api_get_user_profile():
    """Returns profile and registered vehicles for active user with strict user isolation."""
    req_uid = request.args.get('user_id')
    user_id, err = get_authenticated_user_id(req_uid)
    if err:
        return err

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, name, email, phone, role, created_at FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    user_dict = dict(user)

    # Registered Vehicles belonging ONLY to this user
    cursor.execute("SELECT * FROM vehicles WHERE user_id = ? ORDER BY vehicle_id DESC", (user_id,))
    vehicles = [dict(v) for v in cursor.fetchall()]

    # Stats
    cursor.execute("SELECT COUNT(*) as total_bookings FROM reservations WHERE user_id = ?", (user_id,))
    total_bookings = cursor.fetchone()['total_bookings']

    cursor.execute("SELECT COUNT(*) as total_overstays FROM reservations WHERE user_id = ? AND status = 'overstayed'", (user_id,))
    total_overstays = cursor.fetchone()['total_overstays']

    conn.close()

    return jsonify({
        'status': 'success',
        'profile': user_dict,
        'user': user_dict,
        'vehicles': vehicles,
        'stats': {
            'total_bookings': total_bookings,
            'total_overstays': total_overstays
        }
    })

@user_bp.route('/api/users/profile/update', methods=['POST'])
def api_update_user_profile():
    """Updates user contact and profile information (Name, Email, Phone) with validation and uniqueness checks."""
    data = request.get_json() or {}
    req_uid = data.get('user_id')
    user_id, err = get_authenticated_user_id(req_uid)
    if err:
        return err

    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()

    if not name:
        return jsonify({'status': 'error', 'message': 'Full name cannot be empty.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    updates = []
    params = []

    updates.append("name = ?")
    params.append(name)

    if email:
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            conn.close()
            return jsonify({'status': 'error', 'message': 'Please enter a valid email address.'}), 400

        # Check uniqueness against other users
        cursor.execute("SELECT user_id FROM users WHERE LOWER(email) = ? AND user_id != ?", (email, user_id))
        if cursor.fetchone():
            conn.close()
            return jsonify({'status': 'error', 'message': 'An account with this email address already exists.'}), 409
        
        updates.append("email = ?")
        params.append(email)

    if phone:
        digits_only = re.sub(r'\D', '', phone)
        if len(digits_only) < 10:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Phone number must have at least 10 digits.'}), 400
        updates.append("phone = ?")
        params.append(phone)

    params.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)
    conn.commit()

    # Dynamically update session details if modifying self
    if session.get('user_id') == user_id:
        session['user_name'] = name
        if email:
            session['user_email'] = email
        if phone:
            session['user_phone'] = phone

    # Fetch updated user object
    cursor.execute("SELECT user_id, name, email, phone, role, created_at FROM users WHERE user_id = ?", (user_id,))
    updated_user = dict(cursor.fetchone())
    conn.close()

    # Real-time MongoDB persistence
    mongo_update_user(user_id, {
        'name': name,
        **({'email': email} if email else {}),
        **({'phone': phone} if phone else {})
    })

    return jsonify({
        'status': 'success',
        'message': 'Profile updated successfully.',
        'profile': updated_user
    })

@user_bp.route('/api/users/vehicles/add', methods=['POST'])
def api_add_vehicle():
    """Adds a new vehicle to the authenticated user's garage."""
    data = request.get_json() or {}
    req_uid = data.get('user_id')
    user_id, err = get_authenticated_user_id(req_uid)
    if err:
        return err

    plate = (data.get('license_plate') or '').strip().upper()
    v_type = normalize_vehicle_type(data.get('vehicle_type', 'Car'))
    make_model = data.get('make_model', 'Sedan').strip()
    color = data.get('color', 'White').strip()

    if not plate:
        return jsonify({'status': 'error', 'message': 'License plate is required.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO vehicles (user_id, license_plate, vehicle_type, make_model, color)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, plate, v_type, make_model, color))
    conn.commit()
    v_id = cursor.lastrowid

    cursor.execute("SELECT * FROM vehicles WHERE vehicle_id = ?", (v_id,))
    new_vehicle = dict(cursor.fetchone())
    conn.close()

    # Real-time MongoDB persistence
    mongo_save_vehicle(new_vehicle)

    return jsonify({
        'status': 'success',
        'vehicle_id': v_id,
        'vehicle': new_vehicle,
        'message': f"Vehicle '{plate}' registered successfully."
    })

@user_bp.route('/api/users/vehicles/<int:vehicle_id>', methods=['GET'])
def api_get_single_vehicle(vehicle_id):
    """Returns details of a specific vehicle owned by the authenticated user."""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Authentication required. Please log in.'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehicles WHERE vehicle_id = ?", (vehicle_id,))
    vehicle = cursor.fetchone()
    conn.close()

    if not vehicle:
        return jsonify({'status': 'error', 'message': 'Vehicle not found.'}), 404

    # Ownership check
    if vehicle['user_id'] != session['user_id'] and session.get('user_role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Forbidden: You do not have permission to view this vehicle.'}), 403

    return jsonify({'status': 'success', 'vehicle': dict(vehicle)})

@user_bp.route('/api/users/vehicles/<int:vehicle_id>/update', methods=['POST', 'PUT'])
@user_bp.route('/api/users/vehicles/<int:vehicle_id>', methods=['PUT'])
def api_update_vehicle(vehicle_id):
    """Updates vehicle details (plate, type, make/model, color) owned by authenticated user."""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Authentication required. Please log in.'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehicles WHERE vehicle_id = ?", (vehicle_id,))
    vehicle = cursor.fetchone()

    if not vehicle:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Vehicle not found.'}), 404

    # Ownership check
    if vehicle['user_id'] != session['user_id'] and session.get('user_role') != 'admin':
        conn.close()
        return jsonify({'status': 'error', 'message': 'Forbidden: You do not have permission to edit this vehicle.'}), 403

    data = request.get_json() or {}
    plate = (data.get('license_plate') or vehicle['license_plate']).strip().upper()
    v_type = normalize_vehicle_type(data.get('vehicle_type') or vehicle['vehicle_type'])
    make_model = (data.get('make_model') or vehicle['make_model']).strip()
    color = (data.get('color') or vehicle['color']).strip()

    if not plate:
        conn.close()
        return jsonify({'status': 'error', 'message': 'License plate cannot be empty.'}), 400

    cursor.execute("""
        UPDATE vehicles 
        SET license_plate = ?, vehicle_type = ?, make_model = ?, color = ?
        WHERE vehicle_id = ?
    """, (plate, v_type, make_model, color, vehicle_id))
    conn.commit()

    cursor.execute("SELECT * FROM vehicles WHERE vehicle_id = ?", (vehicle_id,))
    updated_vehicle = dict(cursor.fetchone())
    conn.close()

    # Real-time MongoDB persistence
    mongo_save_vehicle(updated_vehicle)

    return jsonify({
        'status': 'success',
        'message': f"Vehicle '{plate}' updated successfully.",
        'vehicle': updated_vehicle
    })

@user_bp.route('/api/users/vehicles/<int:vehicle_id>', methods=['DELETE'])
def api_delete_vehicle(vehicle_id):
    """Deletes a registered vehicle owned by the authenticated user."""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Authentication required. Please log in.'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehicles WHERE vehicle_id = ?", (vehicle_id,))
    vehicle = cursor.fetchone()

    if not vehicle:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Vehicle not found.'}), 404

    # Ownership check
    if vehicle['user_id'] != session['user_id'] and session.get('user_role') != 'admin':
        conn.close()
        return jsonify({'status': 'error', 'message': 'Forbidden: You do not have permission to delete this vehicle.'}), 403

    cursor.execute("DELETE FROM vehicles WHERE vehicle_id = ?", (vehicle_id,))
    conn.commit()
    conn.close()

    # Real-time MongoDB deletion
    mongo_delete_vehicle(vehicle_id, user_id=vehicle['user_id'])

    return jsonify({'status': 'success', 'message': f"Vehicle '{vehicle['license_plate']}' removed successfully."})

# ==========================================

# MODULE 9: NOTIFICATION MODULE APIs
# ==========================================

@user_bp.route('/api/notifications', methods=['GET'])
def get_user_notifications():
    """Returns notifications for user with unread count and category breakdown."""
    user_id = request.args.get('user_id', type=int) or session.get('user_id', 1)
    notif_type = request.args.get('type', '').strip()
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    limit = int(request.args.get('limit', 50))

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM notifications WHERE user_id = ?"
    params = [user_id]

    if notif_type and notif_type.lower() not in ('all', ''):
        query += " AND type = ?"
        params.append(notif_type)

    if unread_only:
        query += " AND is_read = 0"

    query += " ORDER BY notification_id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, tuple(params))
    notifs = [dict(row) for row in cursor.fetchall()]

    # Unread count
    cursor.execute("SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,))
    unread_cnt = cursor.fetchone()['cnt']

    # Category summaries
    cursor.execute("""
        SELECT type, COUNT(*) as cnt, SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) as unread
        FROM notifications
        WHERE user_id = ?
        GROUP BY type
    """, (user_id,))
    categories = {r['type']: {'total': r['cnt'], 'unread': r['unread'] or 0} for r in cursor.fetchall()}

    conn.close()

    return jsonify({
        'status': 'success',
        'notifications': notifs,
        'unread_count': unread_cnt,
        'total_count': len(notifs),
        'categories': categories
    })

@user_bp.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    """Marks an individual notification as read."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE notification_id = ?", (notification_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Notification marked as read.'})

@user_bp.route('/api/notifications/mark-all-read', methods=['POST'])
def mark_all_notifications_read():
    """Marks all notifications for current user as read."""
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'All notifications marked as read.'})

@user_bp.route('/api/notifications/clear', methods=['POST'])
def clear_user_notifications():
    """Clears notifications for current user."""
    data = request.get_json() or {}
    user_id = data.get('user_id') or session.get('user_id', 1)
    only_read = data.get('only_read', False)
    conn = get_db_connection()
    cursor = conn.cursor()
    if only_read:
        cursor.execute("DELETE FROM notifications WHERE user_id = ? AND is_read = 1", (user_id,))
    else:
        cursor.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Notifications cleared successfully.'})

@user_bp.route('/api/notifications/check-alerts', methods=['POST'])
def check_and_generate_alerts():
    """
    Evaluates active reservations against simulated system time to dispatch
    Booking Reminders (within 30m of start) and Parking Expiry Alerts (within 15m of end).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    sim_time = get_current_sim_time(conn)

    cursor.execute("""
        SELECT r.*, s.slot_number, u.name as user_name
        FROM reservations r
        JOIN parking_slots s ON r.slot_id = s.slot_id
        JOIN users u ON r.user_id = u.user_id
        WHERE r.status IN ('confirmed', 'checked_in')
    """)
    active_res = cursor.fetchall()
    created_count = 0

    for res in active_res:
        try:
            start_dt = datetime.strptime(f"{res['date']} {res['start_time']}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{res['date']} {res['end_time']}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        # 1. Booking Reminder: within 30 minutes before start time
        time_until_start = (start_dt - sim_time).total_seconds()
        if 0 <= time_until_start <= 1800:
            cursor.execute("SELECT notification_id FROM notifications WHERE related_id = ? AND type = 'booking_reminder'", (res['reservation_id'],))
            if not cursor.fetchone():
                mins_left = max(1, int(time_until_start / 60))
                create_notification(
                    user_id=res['user_id'],
                    notif_type='booking_reminder',
                    title='🔔 Upcoming Parking Reminder',
                    message=f"Reminder: Your session for Slot {res['slot_number']} starts in ~{mins_left} mins (at {res['start_time']}). QR pass is active.",
                    related_id=res['reservation_id'],
                    conn=conn
                )
                created_count += 1

        # 2. Parking Expiry Alert: within 15 minutes before end time
        time_until_end = (end_dt - sim_time).total_seconds()
        if 0 <= time_until_end <= 900:
            cursor.execute("SELECT notification_id FROM notifications WHERE related_id = ? AND type = 'parking_expiry_alert'", (res['reservation_id'],))
            if not cursor.fetchone():
                mins_left = max(1, int(time_until_end / 60))
                create_notification(
                    user_id=res['user_id'],
                    notif_type='parking_expiry_alert',
                    title='⏳ Parking Session Expiring Soon',
                    message=f"Warning: Your parking session for Slot {res['slot_number']} ends in {mins_left} mins (at {res['end_time']}). Please prepare to exit.",
                    related_id=res['reservation_id'],
                    conn=conn
                )
                created_count += 1

    conn.commit()
    conn.close()
    return jsonify({
        'status': 'success',
        'new_alerts_generated': created_count,
        'simulated_time': sim_time.strftime('%Y-%m-%d %H:%M:%S')
    })


# ==============================================================================
