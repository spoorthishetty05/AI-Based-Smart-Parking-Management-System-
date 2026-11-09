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

from core.simulation_engine import step_simulation_time, set_simulation_time, trigger_random_arrival, trigger_random_departure
from core.overstay_engine import get_current_sim_time, check_and_update_overstays

simulation_bp = Blueprint('simulation', __name__)


# SIMULATION CONTROL APIs
# ==========================================

@simulation_bp.route('/api/simulate/tick', methods=['POST'])
def api_simulate_tick():
    """Advances simulation clock by specified minutes."""
    data = request.get_json() or {}
    minutes = int(data.get('minutes', 15))
    result = step_simulation_time(minutes)
    return jsonify({'status': 'success', 'result': result})

@simulation_bp.route('/api/simulate/set-time', methods=['POST'])
def api_simulate_set_time():
    """Sets exact simulated time."""
    data = request.get_json() or {}
    target_time = data.get('time', '2026-05-24 09:30:00')
    result = set_simulation_time(target_time)
    return jsonify({'status': 'success', 'result': result})

@simulation_bp.route('/api/simulate/arrival', methods=['POST'])
def api_simulate_arrival():
    """Triggers realistic vehicle arrival."""
    data = request.get_json() or {}
    floor = data.get('floor', 'Ground Floor')
    result = trigger_random_arrival(floor)
    return jsonify(result)

@simulation_bp.route('/api/simulate/departure', methods=['POST'])
def api_simulate_departure():
    """Triggers realistic vehicle departure."""
    result = trigger_random_departure()
    return jsonify(result)

@simulation_bp.route('/api/simulate/reset-clock', methods=['POST'])
def api_simulate_reset_clock():
    """Resets simulation clock offset back to real host PC time without wiping database."""
    db = get_mongo_db()
    now_dt = datetime.now()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')
    if db is not None:
        db.system_settings.update_one(
            {'setting_key': 'sim_offset_seconds'},
            {'$set': {'setting_value': '0'}},
            upsert=True
        )
        db.system_settings.update_one(
            {'setting_key': 'simulated_time'},
            {'$set': {'setting_value': now_str}},
            upsert=True
        )
    # Re-evaluate all overstays against real current time
    check_and_update_overstays(now_dt)
    return jsonify({
        'status': 'success',
        'message': 'Simulation clock reset to current PC time.',
        'current_time': now_str,
        'formatted_time': now_dt.strftime('%d %b %Y | %I:%M %p')
    })

@simulation_bp.route('/api/simulate/reset', methods=['POST'])
def api_simulate_reset():
    """Resets entire system and re-seeds database to pristine initial state matching mockup."""
    from flask import current_app
    if not current_app.config.get('TESTING') and session.get('user_role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Access Denied: Administrator privileges required.'}), 403
    init_db(force_reseed=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE system_settings SET setting_value = '0' WHERE setting_key = 'sim_offset_seconds'")
    cursor.execute("UPDATE system_settings SET setting_value = ? WHERE setting_key = 'simulated_time'", (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
    conn.commit()
    conn.close()
    try:
        sync_sqlite_to_mongodb()
    except Exception as e:
        print(f"[Mongo Reset Sync] {e}")
    return jsonify({'status': 'success', 'message': 'System state successfully reset to original seed data with current PC date.'})

# ==========================================
