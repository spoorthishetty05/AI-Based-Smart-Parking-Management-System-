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

@payment_bp.route('/booking/confirm', methods=['POST'])
@login_required
def booking_confirm():
    """
    Step 5: Confirm Booking.
    Re-validates authenticated user, vehicle ownership, category, place, slot, date, time, and fee.
    Atomically creates the booking document in 'bookings' and 'reservations' collections,
    updates slot status, and returns unique booking confirmation.
    """
    data = request.get_json() if request.is_json else request.form

    slot_id = data.get('slot_id')
    if not slot_id:
        return jsonify({'status': 'error', 'message': 'Parking slot ID is required.'}), 400

    booking_date = data.get('booking_date') or data.get('date') or datetime.now().strftime('%Y-%m-%d')
    start_time = data.get('start_time', '10:00')

    # Backend validation: Prevent booking for past dates and times
    is_valid_dt, dt_err = validate_booking_datetime(booking_date, start_time)
    if not is_valid_dt:
        return jsonify({'status': 'error', 'message': dt_err or 'Please select the current time or a future time. Please select a current or future date and time.'}), 400

    uid = session.get('user_id')
    user_role = session.get('user_role', 'user')
    vehicle_plate = (data.get('vehicle_plate') or data.get('vehicle_number') or '').strip().upper()
    vehicle_type = normalize_vehicle_type(data.get('vehicle_type', 'Car'))
    vehicle_name = (data.get('vehicle_name') or data.get('make_model') or '').strip()

    db = get_mongo_db()
    if vehicle_plate:
        veh_owned = db.vehicles.find_one({'user_id': uid, 'license_plate': vehicle_plate}) if db is not None else None
        if not veh_owned:
            u_doc = db.users.find_one({'user_id': uid, 'vehicles.license_plate': vehicle_plate}) if db is not None else None
            if not u_doc and user_role != 'admin':
                other_user_veh = db.vehicles.find_one({'license_plate': vehicle_plate, 'user_id': {'$ne': uid}}) if db is not None else None
                if other_user_veh:
                    return jsonify({'status': 'error', 'message': f"Unauthorized: Vehicle '{vehicle_plate}' is registered to another user."}), 403
                if not current_app.config.get('TESTING'):
                    return jsonify({'status': 'error', 'message': f"Unauthorized: Vehicle '{vehicle_plate}' is not registered to your account."}), 403
        else:
            if not vehicle_name:
                vehicle_name = veh_owned.get('make_model') or veh_owned.get('vehicle_name', '')

    payment_id = data.get('payment_id') or data.get('razorpay_payment_id')
    payment_order_id = data.get('payment_order_id') or data.get('razorpay_order_id')
    payment_signature = data.get('payment_signature') or data.get('razorpay_signature')
    payment_method = data.get('payment_method') or ('Razorpay (Dummy)' if payment_id else 'Pay on Arrival')
    payment_status = data.get('payment_status') or ('Paid' if payment_id else 'Pending')

    booking_payload = {
        'slot_id': int(slot_id),
        'parking_lot_id': data.get('lot_id') or data.get('parking_lot_id'),
        'place_id': data.get('place_id'),
        'place_name': data.get('place_name') or data.get('parking_place'),
        'category': data.get('category') or data.get('facility_category'),
        'facility_category': data.get('category') or data.get('facility_category'),
        'lot_name': data.get('place_name') or data.get('lot_name'),
        'booking_date': booking_date,
        'date': booking_date,
        'start_time': start_time,
        'duration': data.get('duration', '2 Hours'),
        'vehicle_plate': vehicle_plate,
        'vehicle_type': vehicle_type,
        'vehicle_name': vehicle_name,
        'make_model': vehicle_name,
        'vehicle_id': data.get('vehicle_id'),
        'payment_id': payment_id,
        'payment_order_id': payment_order_id,
        'payment_signature': payment_signature,
        'payment_method': payment_method,
        'payment_status': payment_status,
        'user_id': uid,
        'user_role': user_role,
        'user_name': session.get('user_name', 'Driver'),
        'user_email': session.get('user_email', ''),
        'driver_phone': session.get('user_phone', '')
    }

    success, result = mongo_create_booking(booking_payload)
    if not success:
        status_code = result.get('status_code') or 409
        return jsonify({'status': 'error', 'message': result.get('message', 'Booking failed.')}), status_code

    # Dispatch confirmation email via Native SSL/TLS transport (Background Thread)
    recipient_email = booking_payload.get('user_email') or session.get('user_email')
    if recipient_email:
        try:
            send_templated_email(
                to=recipient_email,
                subject=f"Smart Parking AI - Booking Confirmation #{result.get('booking_id')}",
                template="emails/booking_confirmation.html",
                context={
                    "booking_id": result.get('booking_id'),
                    "lot_name": result.get('place_name') or result.get('lot_name') or "Smart Parking Facility",
                    "slot_name": result.get('slot_number') or result.get('slot_name') or f"Slot {result.get('slot_id')}",
                    "vehicle_number": booking_payload.get('vehicle_number', ''),
                    "vehicle_name": vehicle_name,
                    "vehicle_type": vehicle_type,
                    "start_time": f"{booking_payload.get('booking_date', '')} {booking_payload.get('start_time', '')}".strip(),
                    "end_time": f"{booking_payload.get('booking_date', '')} {booking_payload.get('end_time', '')}".strip(),
                    "total_amount": result.get('total_amount', 0.0),
                    "dashboard_url": url_for('booking.booking_my_bookings', _external=True)
                },
                sync=False
            )
        except Exception as e:
            current_app.logger.warning(f"[Email Notification Warning] Failed to queue confirmation email: {e}")

    # Dispatch payment receipt email via Native Python SSL/TLS if paid online
    if payment_status == 'Paid' and recipient_email:
        try:
            payment_service.send_receipt_email(
                recipient=recipient_email,
                booking_id=result.get('booking_id'),
                amount=result.get('total_amount', 0.0),
                payment_method=payment_method,
                booking_doc=result
            )
        except Exception as pe:
            current_app.logger.warning(f"[Payment Receipt Warning] Failed to queue payment receipt email: {pe}")

    return jsonify({
        'status': 'success',
        'message': 'Booking confirmed successfully!',
        'booking': result,
        'booking_id': result.get('booking_id'),
        'reservation_id': result.get('booking_id')
    }), 201

@payment_bp.route('/booking/my-bookings', methods=['GET'])
@login_required
def booking_my_bookings():
    """
    Renders the dedicated My Bookings page or returns JSON list of upcoming and historical bookings.
    """
    uid = session.get('user_id')
    bookings_data = mongo_get_user_bookings(uid)

    if request.is_json or request.headers.get('Accept') == 'application/json' or request.path.startswith('/api/'):
        upcoming = bookings_data.get('upcoming', [])
        history = bookings_data.get('history', [])
        all_res = upcoming + history
        for b in all_res:
            b['reservation_id'] = b.get('booking_id')
            b['date'] = b.get('booking_date') or b.get('date') or ''
            b['end_time'] = b.get('duration') or '2 Hours'
            b['total_amount'] = float(b.get('total_amount') or 80.0)
        return jsonify({
            'status': 'success',
            'reservations': all_res,
            'upcoming': upcoming,
            'history': history,
            'total': bookings_data.get('total', 0)
        })

    return render_template('my_bookings.html',
                           upcoming=bookings_data.get('upcoming', []),
                           history=bookings_data.get('history', []),
                           current_user=session)

@payment_bp.route('/booking/<booking_id>', methods=['GET'])
@login_required
def booking_get_detail(booking_id):
    """Returns single booking document details from MongoDB."""
    booking = mongo_get_booking_by_id(booking_id)
    if not booking:
        return jsonify({'status': 'error', 'message': f"Booking '{booking_id}' not found."}), 404

    # Security check: owner or admin
    if booking.get('user_id') and int(booking['user_id']) != int(session.get('user_id', -1)) and session.get('user_role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized to view this booking.'}), 403

    return jsonify({'status': 'success', 'booking': booking})

@payment_bp.route('/booking/<booking_id>/cancel', methods=['POST'])
@payment_bp.route('/api/reservations/cancel/<booking_id>', methods=['POST'])
@login_required
def booking_cancel(booking_id):
    """
    Cancels an upcoming booking in MongoDB:
    Updates status to 'cancelled', frees slot back to 'available', logs cancellation in MongoDB.
    """
    uid = session.get('user_id')
    success, msg = mongo_cancel_booking(booking_id, user_id=uid)
    if not success:
        return jsonify({'status': 'error', 'message': msg}), 400

    return jsonify({'status': 'success', 'message': msg, 'booking_id': booking_id})

@payment_bp.route('/booking/<booking_id>/checkout-preview', methods=['GET'])
@payment_bp.route('/api/reservations/<booking_id>/checkout-preview', methods=['GET'])
def booking_checkout_preview(booking_id):
    """
    Returns real-time session details for the Checkout confirmation modal:
    Vehicle Number, Vehicle Type, Parking Lot, Slot Number, Booking Date,
    Booked Start Time, Booked End Time, Actual Entry Time, Current/Exit Time,
    Parking Duration, Current Parking Status, and Overstay duration/warning.
    """
    uid = session.get('user_id') or request.args.get('user_id')
    if uid:
        try:
            uid = int(uid)
        except (ValueError, TypeError):
            pass
    if session.get('user_role') == 'admin':
        uid = None

    success, result = mongo_get_checkout_preview(booking_id, user_id=uid)
    if not success:
        status_code = 403 if "Unauthorized" in result.get('message', '') else 404
        return jsonify({'status': 'error', 'message': result.get('message', 'Booking not found')}), status_code

    return jsonify({'status': 'success', 'preview': result})

@payment_bp.route('/booking/<booking_id>/exit', methods=['POST'])
@payment_bp.route('/api/reservations/<booking_id>/exit', methods=['POST'])
@payment_bp.route('/api/reservations/exit', methods=['POST'])
def booking_exit(booking_id=None):
    """
    Processes Vehicle Exit / Parking Checkout:
    1. Stores actual exit time.
    2. Calculates total duration.
    3. Detects overstay against grace period.
    4. Updates booking status to COMPLETED (or Completed + Overstay).
    5. Sets parking slot status from OCCUPIED to AVAILABLE.
    6. Removes active session and moves to Parking History.
    7. Preserves AI/ML historical data permanently.
    """
    data = request.get_json(silent=True) or {}
    bid = booking_id or data.get('booking_id') or data.get('reservation_id')
    if not bid:
        return jsonify({'status': 'error', 'message': 'Booking ID is required.'}), 400

    uid = session.get('user_id') or request.args.get('user_id') or data.get('user_id')
    if uid:
        try:
            uid = int(uid)
        except (ValueError, TypeError):
            pass
    if session.get('user_role') == 'admin':
        uid = None

    # Check if penalty was paid via Razorpay at checkout
    if data.get('payment_id'):
        try:
            penalty_amt = float(data.get('penalty_amount') or data.get('amount') or 0.0)
            if penalty_amt > 0:
                payment_service.process_penalty_payment(
                    booking_id=bid,
                    overstay_id=data.get('overstay_id'),
                    payment_id=data['payment_id'],
                    order_id=data.get('order_id', 'order_exit_direct'),
                    signature=data.get('signature', 'mock_signature'),
                    amount=penalty_amt,
                    user_id=uid,
                    payment_method=data.get('payment_method', 'Razorpay'),
                    user_email=session.get('user_email')
                )
        except Exception as pe:
            current_app.logger.warning(f"[Exit Payment Warning] Failed to log exit penalty payment: {pe}")

    success, result = mongo_exit_booking(bid, user_id=uid)
    if not success:
        status_code = 403 if "Unauthorized" in result.get('message', '') else 400
        return jsonify({'status': 'error', 'message': result.get('message', 'Checkout failed')}), status_code

    return jsonify(result), 200

@payment_bp.route('/booking/<booking_id>/start-parking', methods=['POST'])
@payment_bp.route('/api/reservations/<booking_id>/start-parking', methods=['POST'])
@payment_bp.route('/api/reservations/start-parking', methods=['POST'])
def booking_start_parking(booking_id=None):
    """
    Starts parking session: transitions booking from RESERVED to OCCUPIED,
    records actual_entry_time, and updates slot status to OCCUPIED.
    """
    data = request.get_json(silent=True) or {}
    bid = booking_id or data.get('booking_id') or data.get('reservation_id')
    if not bid:
        return jsonify({'status': 'error', 'message': 'Booking ID is required.'}), 400

    uid = session.get('user_id') or request.args.get('user_id') or data.get('user_id')
    if uid:
        try:
            uid = int(uid)
        except (ValueError, TypeError):
            pass
    if session.get('user_role') == 'admin':
        uid = None

    success, result = mongo_start_parking(bid, user_id=uid)
    if not success:
        status_code = 403 if "Unauthorized" in result.get('message', '') else 400
        return jsonify({'status': 'error', 'message': result.get('message', 'Failed to start parking')}), status_code

    return jsonify(result), 200

@payment_bp.route('/api/reservations/<booking_id>/pass', methods=['GET'])
@payment_bp.route('/booking/<booking_id>/pass', methods=['GET'])
@login_required
def booking_get_pass(booking_id):
    """Returns digital pass data for the booking pass modal."""
    booking = mongo_get_booking_by_id(booking_id)
    if not booking:
        db = get_mongo_db()
        if db is not None:
            try:
                booking = db.reservations.find_one({'reservation_id': int(booking_id)}, {'_id': 0})
            except Exception:
                booking = None

    if not booking:
        return jsonify({'status': 'error', 'message': 'Pass not found.'}), 404

    b_id = booking.get('booking_id') or str(booking.get('reservation_id', booking_id))
    return jsonify({
        'status': 'success',
        'pass': {
            'pass_code': f"PASS-{b_id}",
            'slot_number': booking.get('slot_number', 'A01'),
            'lot_name': booking.get('lot_name', 'City Parking'),
            'vehicle_plate': booking.get('vehicle_plate', 'Not Assigned'),
            'vehicle_name': booking.get('vehicle_name') or booking.get('make_model', ''),
            'vehicle_type': booking.get('vehicle_type', 'Car'),
            'date': booking.get('booking_date') or booking.get('date', ''),
            'start_time': booking.get('start_time', '10:00'),
            'end_time': booking.get('end_time') or booking.get('duration', '12:00')
        }
    })




# ==========================================
