import os
import sys
import json
import io
import csv
import re
from functools import wraps
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, Response, session, redirect, url_for, flash, make_response, render_template
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

web_bp = Blueprint('web', __name__)

@web_bp.route('/admin')
@admin_required
def admin_panel():
    """Dedicated Admin Panel for monitoring, user & lot management, AI and reports."""
    return render_template('admin_panel.html', current_user=session)

@web_bp.route('/user')
@login_required
def user_panel():
    """Dedicated User Panel for finding parking, slot booking, live layout, and slot exchange."""
    db = get_mongo_db()
    import parking_places_config
    if db is not None:
        parking_places_config.sync_places_to_mongodb(db)
    categories = parking_places_config.get_categories()
    raw_places = parking_places_config.get_all_places(db)
    places = []
    for p in raw_places:
        pd = dict(p)
        tot, avail = parking_places_config.get_place_slot_counts(pd['place_id'], db)
        pd['total_slots'] = tot
        pd['available_slots'] = avail
        places.append(pd)

    lots = list(db.parking_lots.find({}, {'_id': 0})) if db is not None else []
    uid = session.get('user_id')
    vehicles = list(db.vehicles.find({'user_id': uid}, {'_id': 0})) if (db is not None and uid) else []
    today = datetime.now().strftime('%Y-%m-%d')
    now_dt = datetime.now()
    current_hour = now_dt.strftime('%H:%M')
    return render_template('user_panel.html',
                           lots=lots,
                           categories=categories,
                           places=places,
                           vehicles=vehicles,
                           today=today,
                           current_hour=current_hour,
                           current_user=session)

@web_bp.route('/')
@web_bp.route('/search')
@web_bp.route('/dashboard')
@login_required
def index():
    """Main application shell that directs to Admin, Security or User Panel based on authenticated role."""
    if session.get('user_role') == 'admin':
        return render_template('admin_panel.html', current_user=session)
    if session.get('user_role') in ('security', 'guard'):
        return redirect(url_for('security.security_dashboard'))
    db = get_mongo_db()
    import parking_places_config
    if db is not None:
        parking_places_config.sync_places_to_mongodb(db)
    categories = parking_places_config.get_categories()
    raw_places = parking_places_config.get_all_places(db)
    places = []
    for p in raw_places:
        pd = dict(p)
        tot, avail = parking_places_config.get_place_slot_counts(pd['place_id'], db)
        pd['total_slots'] = tot
        pd['available_slots'] = avail
        places.append(pd)

    lots = list(db.parking_lots.find({}, {'_id': 0})) if db is not None else []
    uid = session.get('user_id')
    vehicles = list(db.vehicles.find({'user_id': uid}, {'_id': 0})) if (db is not None and uid) else []
    today = datetime.now().strftime('%Y-%m-%d')
    now_dt = datetime.now()
    current_hour = now_dt.strftime('%H:%M')
    return render_template('user_panel.html',
                           lots=lots,
                           categories=categories,
                           places=places,
                           vehicles=vehicles,
                           today=today,
                           current_hour=current_hour,
                           current_user=session)

