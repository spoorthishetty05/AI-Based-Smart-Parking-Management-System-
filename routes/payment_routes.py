import os
import sys
import json
import io
import csv
import re
from functools import wraps
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, Response, session, redirect, url_for, flash, make_response, current_app
from config import Config
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

from core.payment_service import (
    payment_service, create_payment_order, verify_payment,
    process_booking_payment, process_penalty_payment
)
from core.email_service import send_templated_email
from core.overstay_engine import normalize_vehicle_type

payment_bp = Blueprint('payment', __name__)


# RAZORPAY DUMMY / SANDBOX PAYMENT GATEWAY ENDPOINTS
# ==============================================================================

@payment_bp.route('/api/payment/create-order', methods=['POST'])
def api_payment_create_order():
    """
    Creates a new payment order for Razorpay Checkout.
    Supports both dynamic amounts and booking-derived amounts.
    """
    data = request.get_json(silent=True) or {}
    amount = data.get('amount')
    booking_id = data.get('booking_id')

    if amount is None and booking_id:
        db = get_mongo_db()
        if db is not None:
            b = db.bookings.find_one({'booking_id': booking_id})
            if b:
                amount = b.get('total_amount', 40.0)

    try:
        amt_float = float(amount) if amount is not None else 80.0
    except (ValueError, TypeError):
        amt_float = 80.0

    if amt_float <= 0:
        amt_float = 1.0

    uid = session.get('user_id')
    notes = data.get('notes') or {}
    if booking_id:
        notes['booking_id'] = booking_id

    order = create_payment_order(
        amount=amt_float,
        notes=notes,
        user_id=uid
    )

    return jsonify({
        'status': 'success',
        'order': order,
        'key_id': Config.RAZORPAY_KEY_ID,
        'mock_mode': getattr(Config, 'RAZORPAY_MOCK_MODE', True)
    }), 200


@payment_bp.route('/api/payment/verify', methods=['POST'])
def api_payment_verify():
    """
    Verifies payment credentials (payment_id, order_id, signature).
    Persists transaction in 'payment_transactions' and triggers receipt email.
    Supports both Slot Reservation fees and Overstay Penalty fees.
    """
    data = request.get_json(silent=True) or {}
    payment_id = data.get('razorpay_payment_id') or data.get('payment_id')
    order_id = data.get('razorpay_order_id') or data.get('order_id')
    signature = data.get('razorpay_signature') or data.get('signature')
    amount = data.get('amount', 0.0)
    booking_id = data.get('booking_id')
    overstay_id = data.get('overstay_id')
    method = data.get('method', 'UPI / QR')
    pay_type = data.get('type', 'booking')
    uid = session.get('user_id')
    user_email = session.get('user_email')

    if not payment_id or not order_id:
        return jsonify({'status': 'error', 'message': 'Payment ID and Order ID are required.'}), 400

    if pay_type == 'overstay_penalty' or overstay_id:
        success, res = process_penalty_payment(
            booking_id=booking_id or 'OVERSTAY',
            overstay_id=overstay_id,
            payment_id=payment_id,
            order_id=order_id,
            signature=signature,
            amount=amount,
            user_id=uid,
            payment_method=method,
            user_email=user_email
        )
    elif booking_id:
        success, res = process_booking_payment(
            booking_id=booking_id,
            payment_id=payment_id,
            order_id=order_id,
            signature=signature,
            amount=amount,
            user_id=uid,
            payment_method=method,
            user_email=user_email
        )
    else:
        success, res = verify_payment(
            payment_id=payment_id,
            order_id=order_id,
            signature=signature,
            amount=amount,
            user_id=uid,
            method=method
        )

    if not success:
        return jsonify({'status': 'error', 'message': res.get('message', 'Payment verification failed.')}), 400

    return jsonify({
        'status': 'success',
        'message': 'Payment successfully verified and captured.',
        'transaction': res
    }), 200


@payment_bp.route('/api/payment/transactions', methods=['GET'])
def api_payment_transactions():
    """Returns payment history for the logged-in user."""
    uid = session.get('user_id')
    if not uid:
        return jsonify({'status': 'error', 'message': 'Authentication required.'}), 401

    txs = payment_service.get_user_transactions(uid)
    return jsonify({
        'status': 'success',
        'transactions': txs,
        'count': len(txs)
    }), 200


@payment_bp.route('/api/reservations/<booking_id>/pay-penalty', methods=['POST'])
def api_reservation_pay_penalty(booking_id):
    """
    Settles overstay penalty fine for a reservation via Razorpay.
    """
    data = request.get_json(silent=True) or {}
    payment_id = data.get('razorpay_payment_id') or data.get('payment_id')
    order_id = data.get('razorpay_order_id') or data.get('order_id')
    signature = data.get('razorpay_signature') or data.get('signature')
    amount = float(data.get('amount', 0.0))
    method = data.get('method', 'UPI / QR')
    overstay_id = data.get('overstay_id')

    success, res = process_penalty_payment(
        booking_id=booking_id,
        overstay_id=overstay_id,
        payment_id=payment_id,
        order_id=order_id,
        signature=signature,
        amount=amount,
        user_id=session.get('user_id'),
        payment_method=method,
        user_email=session.get('user_email')
    )

    if not success:
        return jsonify({'status': 'error', 'message': res.get('message', 'Failed to process penalty payment.')}), 400

    return jsonify({
        'status': 'success',
        'message': f'Penalty fee of ₹{amount:.2f} successfully paid and cleared via Razorpay.',
        'transaction': res
    }), 200
