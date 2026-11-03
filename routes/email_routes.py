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

from core.email_service import mail_service, send_email, send_templated_email

email_bp = Blueprint('email', __name__)


# SECURE EMAIL TRANSPORT MANAGEMENT & DIAGNOSTIC APIS
# ==============================================================================

@email_bp.route('/api/email/status', methods=['GET'])
def api_email_status():
    """
    Returns current configuration status of Native Python SSL/TLS email transport.
    Mirrors Nodemailer's secure: true (Port 465) / secure: false (Port 587).
    """
    return jsonify({
        'status': 'success',
        'mail_server': mail_service.server,
        'mail_port': mail_service.port,
        'secure_mode': mail_service.is_secure_ssl(),
        'transport_protocol': mail_service.get_transport_mode(),
        'authenticated': bool(mail_service.username and mail_service.password),
        'default_sender': mail_service.default_sender,
        'reply_to': mail_service.reply_to or 'None',
        'timeout_seconds': mail_service.timeout,
        'suppress_send': mail_service.suppress_send,
        'is_simulation': mail_service.suppress_send or not (mail_service.username and mail_service.password),
        'max_background_workers': mail_service.max_workers,
        'outbox_count': len(mail_service.outbox)
    }), 200


@email_bp.route('/api/email/test-connection', methods=['GET', 'POST'])
def api_email_test_connection():
    """
    Tests SMTP server handshake and authentication without sending a message.
    """
    result = mail_service.test_connection()
    status_code = 200 if result.get('success') else (400 if 'not configured' in result.get('error', '') else 502)
    return jsonify(result), status_code


@email_bp.route('/api/email/test', methods=['GET', 'POST'])
def api_email_test():
    """
    Sends a test email via Native Python SSL/TLS Transport.
    Supports GET (for browser quick test) and POST (with custom payload).
    Supports HTML templates, custom text, attachments, and background execution.
    """
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form.to_dict() or {}
    else:
        data = request.args.to_dict()

    recipient = data.get('to') or session.get('user_email') or 'admin@smartparking.ai'
    subject = data.get('subject') or f"Smart Parking AI - Email Transport Verification ({mail_service.get_transport_mode()})"
    use_template = data.get('template', 'general')
    sync = str(data.get('sync', 'true')).lower() in ('true', '1', 'yes')

    try:
        if use_template == 'booking':
            result = send_templated_email(
                to=recipient,
                subject=subject,
                template='emails/booking_confirmation.html',
                context={
                    'booking_id': 9999,
                    'lot_name': 'Downtown Central Hub',
                    'slot_name': 'Slot A-101',
                    'vehicle_number': 'KA-01-AB-1234',
                    'vehicle_type': 'Car',
                    'start_time': datetime.now().strftime('%Y-%m-%d %H:00'),
                    'end_time': (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%d %H:00'),
                    'total_amount': 120.0,
                    'dashboard_url': url_for('booking.booking_my_bookings', _external=True)
                },
                sync=sync
            )
        elif use_template == 'overstay':
            result = send_templated_email(
                to=recipient,
                subject=subject,
                template='emails/overstay_alert.html',
                context={
                    'vehicle_number': 'KA-01-AB-1234',
                    'slot_name': 'Slot A-101',
                    'scheduled_end_time': datetime.now().strftime('%Y-%m-%d %H:00'),
                    'overstay_minutes': 45,
                    'penalty_amount': 180.0,
                    'grace_status': 'Expired (15 min grace period exceeded)',
                    'checkout_url': url_for('booking.booking_my_bookings', _external=True)
                },
                sync=sync
            )
        else:
            # Default rich HTML test message
            html_content = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; color: #1e293b;">
              <h2 style="color: #2563eb;">Native Python SSL/TLS Email Transport Active</h2>
              <p>This email verifies that your Flask application is successfully transmitting emails via:</p>
              <ul>
                <li><strong>Transport Mode:</strong> {mail_service.get_transport_mode()}</li>
                <li><strong>Server:</strong> {mail_service.server}:{mail_service.port}</li>
                <li><strong>Security:</strong> {'Direct smtplib.SMTP_SSL' if mail_service.is_secure_ssl() else 'STARTTLS upgrade via smtplib.SMTP'}</li>
                <li><strong>Execution:</strong> {'Synchronous' if sync else 'Non-blocking Background Thread'}</li>
                <li><strong>Timestamp:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
              </ul>
              <p style="color: #10b981; font-weight: bold;">&#10004; Production-Ready Nodemailer Parity achieved natively in Python!</p>
            </div>
            """
            result = send_email(
                to=recipient,
                subject=subject,
                html=html_content,
                sync=sync
            )

        return jsonify({
            'status': 'success',
            'message': 'Test email executed successfully.',
            'details': result,
            'transport_mode': mail_service.get_transport_mode()
        }), 200

    except Exception as e:
        current_app.logger.error(f"Test email execution failed: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'transport_mode': mail_service.get_transport_mode()
        }), 500


@email_bp.route('/api/email/outbox', methods=['GET'])
def api_email_outbox():
    """
    Returns contents of the in-memory test/simulation outbox.
    Useful for checking delivered emails in development and automated testing.
    """
    limit = int(request.args.get('limit', 20))
    return jsonify({
        'status': 'success',
        'count': len(mail_service.outbox),
        'outbox': mail_service.outbox[-limit:]
    }), 200


