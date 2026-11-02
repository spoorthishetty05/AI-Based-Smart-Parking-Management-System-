"""
Overstay Detection & Alert Engine for AI-Based Smart Parking System.
Monitors reservation expiration, enforces a fixed 15-minute grace period,
applies fixed vehicle-specific overstay penalties (Car: ₹60, Bike: ₹30, Other vehicles: ₹80),
triggers 3-tier notifications, provides real-time admin & user dashboard metrics, and updates slot statuses.
Uses pure MongoDB persistence.
"""

import math
from datetime import datetime, timedelta
import pymongo
from pymongo import DESCENDING
from database import get_mongo_db, get_next_sequence, create_notification
try:
    from email_service import send_templated_email
except ImportError:
    try:
        from core.email_service import send_templated_email
    except ImportError:
        send_templated_email = None


def normalize_vehicle_type(vtype):
    """
    Normalizes vehicle category into:
    - Bike
    - Car
    - Other vehicles
    """
    if not vtype:
        return 'Car'
    v = str(vtype).strip().lower()
    if any(k in v for k in ['bike', 'two', 'motorcycle', 'scooter', 'cycle']):
        return 'Bike'
    if any(k in v for k in ['car', 'sedan', 'hatchback', 'suv', 'jeep', 'van', 'ev']):
        return 'Car'
    if any(k in v for k in ['bus', 'truck', 'heavy', 'lorry', 'other']):
        return 'Other vehicles'
    return 'Car'


def get_vehicle_penalty_amount(vehicle_type):
    """
    Fixed vehicle-specific penalty amounts:
    - Car: ₹60
    - Bike: ₹30
    - Other vehicles: ₹80
    """
    norm = normalize_vehicle_type(vehicle_type)
    if norm == 'Bike':
        return 30.0
    elif norm == 'Other vehicles':
        return 80.0
    return 60.0


def get_current_sim_time(conn=None):
    """
    Retrieves current system time based on the host PC's date and time.
    Supports simulation time offsets (e.g. +15m, +30m).
    Automatically rolls over and updates daily based on the actual PC calendar.
    Uses MongoDB system_settings collection.
    """
    db = get_mongo_db()
    settings_cursor = db.system_settings.find({
        'setting_key': {'$in': ['simulated_time', 'sim_offset_seconds']}
    })
    settings = {s['setting_key']: s.get('setting_value') for s in settings_cursor}

    now = datetime.now()
    offset_seconds = 0

    # If simulated_time belongs to a different day, reset offset to 0
    if 'simulated_time' in settings and settings['simulated_time']:
        try:
            stored_dt = datetime.strptime(str(settings['simulated_time']), '%Y-%m-%d %H:%M:%S')
            if stored_dt.date() != now.date():
                db.system_settings.update_one(
                    {'setting_key': 'sim_offset_seconds'},
                    {'$set': {'setting_value': '0'}},
                    upsert=True
                )
                db.system_settings.update_one(
                    {'setting_key': 'simulated_time'},
                    {'$set': {'setting_value': now.strftime('%Y-%m-%d %H:%M:%S')}},
                    upsert=True
                )
                return now
        except (ValueError, TypeError):
            pass

    if 'sim_offset_seconds' in settings and settings['sim_offset_seconds'] is not None:
        try:
            offset_seconds = int(float(settings['sim_offset_seconds']))
        except (ValueError, TypeError):
            offset_seconds = 0
    elif 'simulated_time' in settings and settings['simulated_time']:
        try:
            stored_dt = datetime.strptime(str(settings['simulated_time']), '%Y-%m-%d %H:%M:%S')
            if stored_dt.date() == now.date():
                offset_seconds = int((stored_dt - now).total_seconds())
        except (ValueError, TypeError):
            offset_seconds = 0

    return now + timedelta(seconds=offset_seconds)


def calculate_overstay(booked_date, booked_end, current_or_exit_dt=None, vehicle_type='Car', grace_mins=15):
    """
    Calculates overstay status, duration, and vehicle-specific penalty.
    
    Fixed Grace Period: Exactly 15 minutes after the booked end time.
    Status Rules:
      1. Before booked end: 'Within Booking Time', Penalty: ₹0
      2. Booked end to booked end + 15m: 'Grace Period', Penalty: ₹0
      3. After booked end + 15m (and parked): 'Penalty Applicable'
         Fixed Penalties applied once per overstay incident:
           - Car: ₹60
           - Bike: ₹30
           - Other vehicles: ₹80
    """
    if current_or_exit_dt is None:
        current_or_exit_dt = get_current_sim_time()

    # Enforce strictly 15-minute fixed grace period
    grace_mins = 15

    # Parse booked end datetime
    booked_end_str = str(booked_end).strip() if booked_end else ''
    booked_date_str = str(booked_date).strip() if booked_date else ''

    booked_end_dt = None
    # 1. Try booked_end_str directly as full datetime
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p', '%d-%m-%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S']:
        try:
            booked_end_dt = datetime.strptime(booked_end_str, fmt)
            break
        except Exception:
            continue

    # 2. Try combining booked_date_str and booked_end_str
    if not booked_end_dt and booked_date_str:
        for fmt in [
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
            '%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p',
            '%d/%m/%Y %H:%M', '%d-%m-%Y %H:%M',
            '%d/%m/%Y %I:%M %p', '%d-%m-%Y %I:%M %p'
        ]:
            try:
                booked_end_dt = datetime.strptime(f"{booked_date_str} {booked_end_str}", fmt)
                break
            except Exception:
                continue

    # 3. If only a time was passed e.g. "11:07 PM", assume date of current_or_exit_dt
    if not booked_end_dt and booked_end_str:
        ref_date = (current_or_exit_dt or datetime.now()).strftime('%Y-%m-%d')
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %I:%M %p', '%Y-%m-%d %I:%M%p']:
            try:
                booked_end_dt = datetime.strptime(f"{ref_date} {booked_end_str}", fmt)
                break
            except Exception:
                continue

    if not booked_end_dt:
        booked_end_dt = current_or_exit_dt

    grace_end_dt = booked_end_dt + timedelta(minutes=15)
    norm_vtype = normalize_vehicle_type(vehicle_type)
    penalty_rate = get_vehicle_penalty_amount(norm_vtype)

    if current_or_exit_dt < booked_end_dt:
        # 1. Within Booking Time
        rem_seconds = (booked_end_dt - current_or_exit_dt).total_seconds()
        rem_mins = max(1, int(math.ceil(rem_seconds / 60.0)))
        rem_text = f"{rem_mins}m remaining"

        return {
            'is_overstay': False,
            'is_expiring': False,
            'is_grace': False,
            'status': 'Within Booking Time',
            'display_status': 'Within Booking Time',
            'remaining_text': rem_text,
            'remaining_minutes': max(0, int(round(rem_seconds / 60.0))),
            'booked_end_dt': booked_end_dt,
            'grace_end_dt': grace_end_dt,
            'overstay_minutes': 0,
            'started_hours': 0,
            'penalty_rate': penalty_rate,
            'penalty': 0.0,
            'penalty_amount': 0.0,
            'duration_formatted': '0m',
            'vehicle_type': norm_vtype
        }

    elif current_or_exit_dt <= grace_end_dt:
        # 2. Grace Period (Warning period, no penalty)
        grace_rem_sec = (grace_end_dt - current_or_exit_dt).total_seconds()
        grace_rem_mins = max(0, int(math.ceil(grace_rem_sec / 60.0)))
        rem_text = f"Grace: {grace_rem_mins}m left"

        return {
            'is_overstay': False,
            'is_expiring': True,
            'is_grace': True,
            'status': 'Grace Period',
            'display_status': 'Grace Period',
            'remaining_text': rem_text,
            'remaining_minutes': 0,
            'booked_end_dt': booked_end_dt,
            'grace_end_dt': grace_end_dt,
            'overstay_minutes': 0,
            'started_hours': 0,
            'penalty_rate': penalty_rate,
            'penalty': 0.0,
            'penalty_amount': 0.0,
            'duration_formatted': '0m',
            'vehicle_type': norm_vtype
        }

    else:
        # 3. Penalty Applicable (Past 15-minute grace period)
        overstay_seconds = max(1, (current_or_exit_dt - grace_end_dt).total_seconds())
        overstay_minutes = max(1, int(round(overstay_seconds / 60.0)))
        dur_h = overstay_minutes // 60
        dur_m = overstay_minutes % 60
        if dur_h > 0:
            duration_formatted = f"{dur_h}h {dur_m:02d}m" if dur_m > 0 else f"{dur_h}h"
        else:
            duration_formatted = f"{dur_m}m"

        return {
            'is_overstay': True,
            'is_expiring': False,
            'is_grace': False,
            'status': 'Penalty Applicable',
            'display_status': 'Penalty Applicable',
            'remaining_text': f"Overstay by {duration_formatted}",
            'remaining_minutes': 0,
            'booked_end_dt': booked_end_dt,
            'grace_end_dt': grace_end_dt,
            'overstay_minutes': overstay_minutes,
            'started_hours': 1,
            'penalty_rate': penalty_rate,
            'penalty': float(penalty_rate),
            'penalty_amount': float(penalty_rate),
            'duration_formatted': duration_formatted,
            'vehicle_type': norm_vtype
        }


def check_and_update_overstays(simulated_now=None):
    """
    Scans all active reservations and occupied slots in MongoDB.
    Enforces the fixed 15-minute grace period and fixed vehicle penalty amounts:
      - Car: ₹60
      - Bike: ₹30
      - Other vehicles: ₹80
    Dispatches 3-tier notifications with duplicate protection on dashboard refresh:
      1. Booking time ended
      2. Grace period warning
      3. Grace period expired & penalty applicable (only if still parked)
    """
    db = get_mongo_db()
    if db is None:
        return []

    if simulated_now is None:
        simulated_now = get_current_sim_time()

    grace_mins = 15

    # Fetch active reservations that might have overstayed
    active_reservations = list(db.reservations.find({
        'status': {'$in': ['confirmed', 'checked_in', 'occupied', 'overstayed', 'Within Booking Time', 'Grace Period', 'Penalty Applicable']}
    }))

    new_alerts = []

    for res in active_reservations:
        # Check if booking is already exited or completed or cancelled
        st_clean = (res.get('status') or '').lower()
        if res.get('actual_exit_time') or st_clean in ('completed', 'cancelled'):
            continue

        b_date = res.get('date') or res.get('booking_date') or simulated_now.strftime('%Y-%m-%d')
        b_end = res.get('end_time', '12:00')
        raw_vtype = res.get('vehicle_type') or 'Car'
        v_type = normalize_vehicle_type(raw_vtype)

        calc = calculate_overstay(
            booked_date=b_date,
            booked_end=b_end,
            current_or_exit_dt=simulated_now,
            vehicle_type=v_type,
            grace_mins=15
        )

        res_id = res.get('reservation_id')
        pass_code = res.get('pass_code') or res.get('booking_id') or f"PK-{res_id:05d}"
        slot_id = res.get('slot_id')

        slot = db.parking_slots.find_one({'slot_id': slot_id}) or {}
        slot_number = slot.get('slot_number') or res.get('slot_number') or f"Slot-{slot_id}"
        lot_id = slot.get('lot_id') or res.get('lot_id', 1)
        lot = db.parking_lots.find_one({'lot_id': lot_id}) or {}
        lot_name = lot.get('lot_name') or res.get('lot_name', 'City Parking')

        user = db.users.find_one({'user_id': res.get('user_id')}) or {}
        user_name = user.get('name') or res.get('user_name', 'Driver')
        driver_name = res.get('driver_name') or user_name
        user_email = user.get('email', '')
        user_phone = user.get('phone', '')
        v_plate = res.get('vehicle_plate') or (user.get('vehicles', [{}])[0].get('license_plate', 'KA-01-XX-0000') if user.get('vehicles') else 'KA-01-XX-0000')

        p_start_time = res.get('start_time', '10:00')
        sel_dur = res.get('selected_duration') or res.get('duration') or f"{res.get('duration_hours', 2)} hours"

        booked_end_display = calc['booked_end_dt'].strftime('%I:%M %p')
        grace_end_display = calc['grace_end_dt'].strftime('%I:%M %p')
        penalty_amount = get_vehicle_penalty_amount(v_type)

        # =========================================================================
        # NOTIFICATION TRIGGER 1: Booking time ended
        # Notify user when the booked parking duration ends
        # =========================================================================
        if simulated_now >= calc['booked_end_dt']:
            already_notified_ended = bool(res.get('notified_booking_ended'))
            if not already_notified_ended:
                existing_n = db.notifications.find_one({
                    'user_id': int(res.get('user_id', 0)),
                    'type': 'booking_ended',
                    'related_id': res_id
                })
                if existing_n:
                    already_notified_ended = True

            if not already_notified_ended:
                notif_msg = (
                    f"⏳ Parking Duration Ended\n\n"
                    f"Your booked parking duration has ended.\n\n"
                    f"Vehicle: {v_plate} ({v_type})\n"
                    f"Parking Lot: {lot_name}\n"
                    f"Slot: {slot_number}\n"
                    f"Booked End Time: {booked_end_display}\n"
                    f"Fixed Grace Period: 15 minutes (ends at {grace_end_display})\n"
                    f"Applicable Penalty after Grace: ₹{int(penalty_amount)}\n\n"
                    f"Please prepare to exit the parking slot before the grace period expires."
                )
                create_notification(
                    user_id=res['user_id'],
                    notif_type='booking_ended',
                    title='⏳ Parking Duration Ended',
                    message=notif_msg,
                    related_id=res_id
                )
                db.reservations.update_one(
                    {'reservation_id': res_id},
                    {'$set': {'notified_booking_ended': True}}
                )
                db.bookings.update_one(
                    {'$or': [{'reservation_id': res_id}, {'booking_id': pass_code}]},
                    {'$set': {'notified_booking_ended': True}}
                )

        # =========================================================================
        # NOTIFICATION TRIGGER 2: Grace period warning
        # Notify user that the 15-minute grace period has started
        # =========================================================================
        if simulated_now >= calc['booked_end_dt'] and simulated_now <= calc['grace_end_dt']:
            already_notified_grace = bool(res.get('notified_grace_warning'))
            if not already_notified_grace:
                existing_n = db.notifications.find_one({
                    'user_id': int(res.get('user_id', 0)),
                    'type': 'grace_warning',
                    'related_id': res_id
                })
                if existing_n:
                    already_notified_grace = True

            if not already_notified_grace:
                notif_msg = (
                    f"⚠️ 15-Minute Grace Period Active\n\n"
                    f"Your 15-minute grace period has started.\n\n"
                    f"Vehicle: {v_plate} ({v_type})\n"
                    f"Parking Lot: {lot_name}\n"
                    f"Slot: {slot_number}\n"
                    f"Booked End Time: {booked_end_display}\n"
                    f"Grace Period Ends: {grace_end_display}\n"
                    f"Applicable Penalty after Grace: ₹{int(penalty_amount)}\n\n"
                    f"Please exit before {grace_end_display} to avoid a ₹{int(penalty_amount)} overstay penalty."
                )
                create_notification(
                    user_id=res['user_id'],
                    notif_type='grace_warning',
                    title='⚠️ 15-Minute Grace Period Started',
                    message=notif_msg,
                    related_id=res_id
                )
                db.reservations.update_one(
                    {'reservation_id': res_id},
                    {'$set': {'notified_grace_warning': True}}
                )
                db.bookings.update_one(
                    {'$or': [{'reservation_id': res_id}, {'booking_id': pass_code}]},
                    {'$set': {'notified_grace_warning': True}}
                )

        # =========================================================================
        # NOTIFICATION TRIGGER 3 & RECORD: Grace period expired & penalty applicable
        # Notify user when grace period ends and penalty applies, provided vehicle still parked
        # =========================================================================
        if calc['is_overstay']:
            extra_minutes = calc['overstay_minutes']
            dur_fmt = calc['duration_formatted']

            # Check if this overstay record already exists
            existing_overstay = db.overstay_records.find_one({
                'reservation_id': res_id,
                'status': 'active'
            })

            # Duplicate notification guard: only send if not already sent
            already_notified_penalty = bool(res.get('notified_penalty_applicable') or res.get('overstay_notification_sent'))
            if not already_notified_penalty:
                existing_notif = db.notifications.find_one({
                    'user_id': int(res.get('user_id', 0)),
                    'type': {'$in': ['overstay_alert', 'penalty_applicable']},
                    'related_id': res_id
                })
                if existing_notif:
                    already_notified_penalty = True

            notif_status = 'Sent' if already_notified_penalty else 'Not Sent'

            if not existing_overstay:
                # 1. Update reservation & booking status
                db.reservations.update_one(
                    {'reservation_id': res_id},
                    {'$set': {
                        'status': 'overstayed',
                        'is_overstay': True,
                        'overstay_duration_minutes': extra_minutes,
                        'overstay_penalty': penalty_amount,
                        'vehicle_type': v_type,
                        'overstay_status': 'Penalty Applicable'
                    }}
                )
                db.bookings.update_one(
                    {'$or': [{'reservation_id': res_id}, {'booking_id': pass_code}, {'pass_code': pass_code}]},
                    {'$set': {
                        'status': 'overstayed',
                        'is_overstay': True,
                        'overstay_duration_minutes': extra_minutes,
                        'overstay_penalty': penalty_amount,
                        'vehicle_type': v_type,
                        'overstay_status': 'Penalty Applicable'
                    }}
                )

                # 2. Update slot status to overstayed (keeps slot occupied)
                if slot_id:
                    db.parking_slots.update_one(
                        {'slot_id': slot_id},
                        {'$set': {'status': 'overstayed'}}
                    )

                # 3. Create initial overstay record with complete details
                overstay_id = get_next_sequence('overstay_records')
                overstay_doc = {
                    'overstay_id': overstay_id,
                    'booking_id': pass_code,
                    'reservation_id': res_id,
                    'user_id': res.get('user_id'),
                    'user_name': user_name,
                    'driver_name': driver_name,
                    'user_email': user_email,
                    'user_phone': user_phone,
                    'vehicle_plate': v_plate,
                    'vehicle_number': v_plate,
                    'vehicle_type': v_type,
                    'lot_id': lot_id,
                    'lot_name': lot_name,
                    'parking_lot': lot_name,
                    'slot_id': slot_id,
                    'slot_number': slot_number,
                    'parking_slot': slot_number,
                    'parking_start_time': p_start_time,
                    'start_time': p_start_time,
                    'selected_duration': sel_dur,
                    'expected_end_time': calc['booked_end_dt'].strftime('%Y-%m-%d %H:%M:%S'),
                    'booked_end_time': calc['booked_end_dt'].strftime('%Y-%m-%d %H:%M:%S'),
                    'booked_end_display': booked_end_display,
                    'grace_period': '15 mins',
                    'grace_period_minutes': 15,
                    'overstay_detection_time': calc['grace_end_dt'].strftime('%Y-%m-%d %H:%M:%S'),
                    'grace_end_time': calc['grace_end_dt'].strftime('%Y-%m-%d %H:%M:%S'),
                    'grace_end_display': grace_end_display,
                    'actual_exit_time': None,
                    'current_overstay_duration': dur_fmt,
                    'overstay_duration': dur_fmt,
                    'overstay_duration_minutes': extra_minutes,
                    'overstay_duration_formatted': dur_fmt,
                    'overstay_status': 'Penalty Applicable',
                    'status': 'active',
                    'notification_status': 'Sent' if already_notified_penalty else notif_status,
                    'notification_sent': already_notified_penalty,
                    'penalty_rate': penalty_amount,
                    'current_penalty': penalty_amount,
                    'penalty': penalty_amount,
                    'final_penalty': 0.0,
                    'payment_status': 'Pending',
                    'created_at': simulated_now.strftime('%Y-%m-%d %H:%M:%S'),
                    'last_updated': simulated_now.strftime('%Y-%m-%d %H:%M:%S')
                }
                db.overstay_records.insert_one(overstay_doc)

                # 4. Dispatch Overstay Alert notification if not already sent
                if not already_notified_penalty:
                    notif_msg = (
                        f"🚨 Grace Period Expired — Penalty Applicable\n\n"
                        f"Your 15-minute grace period has expired and your vehicle remains parked.\n\n"
                        f"Vehicle: {v_plate} ({v_type})\n"
                        f"Parking Lot: {lot_name}\n"
                        f"Slot: {slot_number}\n"
                        f"Booked End Time: {booked_end_display}\n"
                        f"Grace Period End Time: {grace_end_display}\n"
                        f"Applicable Penalty: ₹{int(penalty_amount)}\n\n"
                        f"Please vacate the parking slot immediately."
                    )
                    create_notification(
                        user_id=res['user_id'],
                        notif_type='overstay_alert',
                        title='🚨 Grace Period Expired — Penalty Applicable',
                        message=notif_msg,
                        related_id=res_id,
                        send_email_alert=False
                    )
                    if send_templated_email and user_email:
                        try:
                            send_templated_email(
                                to=user_email,
                                subject=f"URGENT: Overstay Alert for Slot {slot_name} - Smart Parking AI",
                                template="emails/overstay_alert.html",
                                context={
                                    'vehicle_number': v_plate,
                                    'slot_name': slot_name,
                                    'scheduled_end_time': booked_end_display,
                                    'overstay_minutes': calc.get('overstay_minutes', 0),
                                    'penalty_amount': penalty_amount,
                                    'grace_status': 'Expired (15 min grace period exceeded)'
                                },
                                sync=False
                            )
                        except Exception:
                            pass
                    db.reservations.update_one(
                        {'reservation_id': res_id},
                        {'$set': {'overstay_notification_sent': True, 'notified_penalty_applicable': True, 'notification_status': 'Sent'}}
                    )
                    db.bookings.update_one(
                        {'$or': [{'reservation_id': res_id}, {'booking_id': pass_code}]},
                        {'$set': {'overstay_notification_sent': True, 'notified_penalty_applicable': True, 'notification_status': 'Sent'}}
                    )
                    db.overstay_records.update_one(
                        {'overstay_id': overstay_id},
                        {'$set': {'notification_status': 'Sent', 'notification_sent': True}}
                    )

                # 5. Create Activity Alert Log
                log_id = get_next_sequence('activity_logs')
                alert_text = f"Vehicle {v_plate} exceeded 15m grace period by {dur_fmt}. Fixed penalty ₹{int(penalty_amount)} applicable ({v_type})."
                db.activity_logs.insert_one({
                    'log_id': log_id,
                    'slot_number': slot_number,
                    'user_name': f"{user_name} ({v_plate})",
                    'action_type': 'Overstay Detected',
                    'details': alert_text,
                    'badge_type': 'danger',
                    'timestamp': simulated_now.strftime('%I:%M %p'),
                    'created_at': simulated_now.strftime('%Y-%m-%d %H:%M:%S')
                })

                new_alerts.append({
                    'slot_number': slot_number,
                    'user_name': user_name,
                    'vehicle_plate': v_plate,
                    'vehicle_type': v_type,
                    'overstay_duration': dur_fmt,
                    'penalty_amount': penalty_amount,
                    'detected_at': simulated_now.strftime('%H:%M:%S')
                })
            else:
                # Update existing active overstay record with fixed penalty
                db.overstay_records.update_one(
                    {'overstay_id': existing_overstay['overstay_id']},
                    {'$set': {
                        'overstay_duration_minutes': extra_minutes,
                        'overstay_duration_formatted': dur_fmt,
                        'current_overstay_duration': dur_fmt,
                        'overstay_duration': dur_fmt,
                        'current_penalty': penalty_amount,
                        'penalty': penalty_amount,
                        'penalty_rate': penalty_amount,
                        'vehicle_type': v_type,
                        'overstay_status': 'Penalty Applicable',
                        'last_updated': simulated_now.strftime('%Y-%m-%d %H:%M:%S')
                    }}
                )
                db.reservations.update_one(
                    {'reservation_id': res_id},
                    {'$set': {
                        'overstay_duration_minutes': extra_minutes,
                        'overstay_penalty': penalty_amount,
                        'overstay_status': 'Penalty Applicable'
                    }}
                )
        else:
            # Not overstayed: vehicle is either 'Within Booking Time' or in 'Grace Period'
            st_text = calc['status']

            # 1. If an active overstay record was prematurely created, remove it
            db.overstay_records.delete_many({
                'reservation_id': res_id,
                'status': 'active'
            })

            # 2. Revert reservation status if it was previously set to 'overstayed'
            revert_update = {
                'overstay_status': st_text,
                'overstay_penalty': 0.0,
                'is_overstay': False,
                'overstay_duration_minutes': 0
            }
            if res.get('status') == 'overstayed':
                # If booking start has arrived, set to checked_in, else confirmed
                revert_update['status'] = 'checked_in' if simulated_now >= calc['booked_end_dt'] - timedelta(minutes=15) else 'confirmed'

            # If vehicle is within booking time (before booked end), clear premature notifications
            if st_text == 'Within Booking Time':
                revert_update['notified_booking_ended'] = False
                revert_update['notified_grace_warning'] = False
                revert_update['notified_penalty_applicable'] = False
                revert_update['overstay_notification_sent'] = False
                revert_update['notification_status'] = 'Not Sent'

                # Delete any premature notifications for this reservation
                db.notifications.delete_many({
                    'related_id': res_id,
                    'type': {'$in': ['booking_ended', 'grace_warning', 'overstay_alert', 'penalty_applicable']}
                })

            db.reservations.update_one(
                {'reservation_id': res_id},
                {'$set': revert_update}
            )

            db.bookings.update_one(
                {'$or': [{'reservation_id': res_id}, {'booking_id': pass_code}, {'pass_code': pass_code}]},
                {'$set': {
                    'status': 'confirmed',
                    'is_overstay': False,
                    'overstay_duration_minutes': 0,
                    'overstay_penalty': 0.0,
                    'overstay_status': st_text
                }}
            )

            # 3. Revert slot status if it was marked 'overstayed'
            if slot_id:
                slot_doc = db.parking_slots.find_one({'slot_id': slot_id})
                if slot_doc and slot_doc.get('status') == 'overstayed':
                    db.parking_slots.update_one(
                        {'slot_id': slot_id},
                        {'$set': {'status': 'occupied'}}
                    )

    return new_alerts


def get_active_overstays():
    """Returns all currently active overstay records with live accumulated penalties."""
    db = get_mongo_db()
    if db is None:
        return []

    sim_now = get_current_sim_time()
    # First sync status
    check_and_update_overstays(sim_now)

    overstays = list(db.overstay_records.find({'status': 'active'}).sort('overstay_duration_minutes', DESCENDING))

    records = []
    for o in overstays:
        item = dict(o)
        item.pop('_id', None)

        v_type = normalize_vehicle_type(item.get('vehicle_type', 'Car'))
        item['vehicle_type'] = v_type

        # Calculate live accumulated duration and penalty
        b_end_time = item.get('booked_end_time')
        if b_end_time:
            calc = calculate_overstay(
                booked_date=b_end_time[:10],
                booked_end=b_end_time[11:19],
                current_or_exit_dt=sim_now,
                vehicle_type=v_type
            )
            if not calc['is_overstay']:
                continue
            item['overstay_duration_minutes'] = calc['overstay_minutes']
            item['overstay_duration_formatted'] = calc['duration_formatted']
            item['current_penalty'] = calc['penalty']
            item['penalty_rate'] = calc['penalty_rate']

        item['current_exit_time'] = sim_now.strftime('%I:%M %p')
        records.append(item)

    return records


def get_overstay_management_data():
    """
    Returns accurate overstay records and summary metrics for Admin Overstay Records page:
    Summary Cards:
      1. active_overstays: Vehicles exceeding permitted parking duration after grace period
      2. pending_penalties: Unpaid overstay penalties requiring action (count)
         pending_amount: Total pending penalty amount (₹)
      3. resolved_overstays: Overstay records settled or resolved
      4. total_penalties: Correct total penalty amount (pending + paid distinguished)
    Records: Only relevant overstay incidents (active overstays, grace period, resolved overstays)
    with all required columns and clear dashes for missing values.
    """
    db = get_mongo_db()
    if db is None:
        return {
            'summary': {
                'active_overstays': 0,
                'pending_penalties': 0,
                'pending_amount': 0.0,
                'resolved_overstays': 0,
                'paid_amount': 0.0,
                'total_penalties': 0.0,
                'total_penalty_amount': 0.0,
                'total_overstays': 0,
                'grace_count': 0
            },
            'overstays': []
        }

    sim_now = get_current_sim_time()
    check_and_update_overstays(sim_now)

    all_docs = list(db.overstay_records.find({}).sort('overstay_id', DESCENDING))

    records = []
    handled_res_ids = set()
    active_count = 0
    resolved_count = 0
    pending_penalties_count = 0
    pending_penalties_amount = 0.0
    paid_penalties_amount = 0.0

    for d in all_docs:
        item = dict(d)
        item.pop('_id', None)
        res_id = item.get('reservation_id')
        if res_id:
            handled_res_ids.add(res_id)

        v_type = normalize_vehicle_type(item.get('vehicle_type', 'Car'))
        item['vehicle_type'] = v_type
        penalty_rate = get_vehicle_penalty_amount(v_type)
        item['penalty_rate'] = penalty_rate

        # Backfill slot and lot if missing
        if not item.get('slot_number') and item.get('slot_id'):
            s_doc = db.parking_slots.find_one({'slot_id': item['slot_id']})
            if s_doc:
                item['slot_number'] = s_doc.get('slot_number')
        if not item.get('lot_name') and item.get('lot_id'):
            l_doc = db.parking_lots.find_one({'lot_id': item['lot_id']})
            if l_doc:
                item['lot_name'] = l_doc.get('lot_name')
                item['parking_lot'] = l_doc.get('lot_name')

        # Backfill user / booking info if missing
        if res_id and (not item.get('user_name') or not item.get('booking_id')):
            r_doc = db.reservations.find_one({'reservation_id': res_id})
            if r_doc:
                if not item.get('user_name'):
                    item['user_name'] = r_doc.get('driver_name') or r_doc.get('user_name')
                if not item.get('booking_id'):
                    item['booking_id'] = r_doc.get('pass_code') or r_doc.get('booking_id')
                if not item.get('vehicle_plate'):
                    item['vehicle_plate'] = r_doc.get('vehicle_plate')
                if not item.get('parking_lot') and r_doc.get('lot_name'):
                    item['parking_lot'] = r_doc.get('lot_name')
                    item['lot_name'] = r_doc.get('lot_name')

        # Booking ID fallback
        item['booking_id'] = item.get('booking_id') or (f"PK-{res_id:05d}" if res_id else f"OV-{item.get('overstay_id')}")
        item['user_name'] = item.get('user_name') or item.get('driver_name') or '—'
        item['vehicle_number'] = item.get('vehicle_number') or item.get('vehicle_plate') or '—'
        item['vehicle_plate'] = item['vehicle_number']
        item['parking_lot'] = item.get('parking_lot') or item.get('lot_name') or '—'
        item['lot_name'] = item['parking_lot']
        item['slot_number'] = item.get('slot_number') or item.get('parking_slot') or '—'

        # Booked End Time
        raw_b_end = d.get('booked_end_time') or d.get('expected_end_time')
        raw_b_date = d.get('booking_date') or d.get('date')
        if not raw_b_date and raw_b_end and len(str(raw_b_end)) >= 10 and str(raw_b_end)[4] == '-' and str(raw_b_end)[7] == '-':
            raw_b_date = str(raw_b_end)[:10]

        b_end_display = item.get('booked_end_display')
        if not b_end_display and raw_b_end:
            b_str = str(raw_b_end)
            try:
                if len(b_str) >= 19:
                    b_end_display = datetime.strptime(b_str[:19], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')
                elif len(b_str) >= 16:
                    b_end_display = datetime.strptime(b_str[:16], '%Y-%m-%d %H:%M').strftime('%I:%M %p')
                else:
                    b_end_display = b_str
            except Exception:
                b_end_display = b_str
        item['booked_end_time'] = b_end_display or '—'
        item['booked_end_display'] = item['booked_end_time']

        # Grace Period End
        g_end_display = item.get('grace_end_display')
        if not g_end_display and item.get('grace_end_time'):
            g_str = str(item['grace_end_time'])
            try:
                if len(g_str) >= 19:
                    g_end_display = datetime.strptime(g_str[:19], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')
                elif len(g_str) >= 16:
                    g_end_display = datetime.strptime(g_str[:16], '%Y-%m-%d %H:%M').strftime('%I:%M %p')
                else:
                    g_end_display = g_str
            except Exception:
                g_end_display = g_str
        item['grace_period_end'] = g_end_display or '—'
        item['grace_end_display'] = item['grace_period_end']

        is_active = (item.get('status') == 'active' and not item.get('actual_exit_time'))
        is_grace = (item.get('status') == 'grace' or item.get('is_grace'))

        if is_active:
            # Dynamic calculation of current duration & penalty
            calc_b_date = raw_b_date or sim_now.strftime('%Y-%m-%d')
            calc_b_end = raw_b_end or item.get('booked_end_time')
            calc = calculate_overstay(
                booked_date=calc_b_date,
                booked_end=calc_b_end,
                current_or_exit_dt=sim_now,
                vehicle_type=v_type
            )

            # If user's booking time is NOT yet completed, this is not an active overstay
            if not calc['is_overstay']:
                if calc.get('status') == 'Within Booking Time':
                    # Delete premature active overstay record and do not show in violation table
                    db.overstay_records.delete_one({'_id': d['_id']})
                    continue
                elif calc.get('is_grace'):
                    item['status'] = 'grace'
                    item['is_grace'] = True
                    item['overstay_status'] = 'Grace Period'
                    item['status_badge'] = 'warning'
                    item['current_or_exit'] = 'In Grace (Parked)'
                    item['actual_exit_display'] = 'In Grace (Parked)'
                    item['overstay_duration_minutes'] = 0
                    item['overstay_duration_formatted'] = '0m'
                    item['overstay_duration'] = '0m'
                    item['current_penalty'] = 0.0
                    item['penalty_amount'] = 0.0
                    effective_penalty = 0.0
            else:
                active_count += 1
                item['status'] = 'active'
                item['overstay_status'] = 'Overstayed'
                item['status_badge'] = 'danger'
                item['current_or_exit'] = 'Parked (Active)'
                item['actual_exit_display'] = 'Parked (Active)'
                item['overstay_duration_minutes'] = calc['overstay_minutes']
                item['overstay_duration_formatted'] = calc['duration_formatted']
                item['overstay_duration'] = calc['duration_formatted']
                item['current_penalty'] = calc['penalty']
                item['penalty_amount'] = calc['penalty']
                effective_penalty = calc['penalty']
        elif is_grace:
            item['status'] = 'grace'
            item['is_grace'] = True
            item['overstay_status'] = 'Grace Period'
            item['status_badge'] = 'warning'
            item['current_or_exit'] = 'In Grace (Parked)'
            item['actual_exit_display'] = 'In Grace (Parked)'
            item['overstay_duration_minutes'] = 0
            item['overstay_duration_formatted'] = '0m'
            item['overstay_duration'] = '0m'
            item['current_penalty'] = 0.0
            item['penalty_amount'] = 0.0
            effective_penalty = 0.0
        else:
            resolved_count += 1
            item['status'] = 'resolved'
            item['overstay_status'] = 'Resolved'
            item['status_badge'] = 'success'
            effective_penalty = float(item.get('final_penalty', item.get('current_penalty', item.get('penalty_rate', penalty_rate))))
            item['current_penalty'] = effective_penalty
            item['penalty_amount'] = effective_penalty

            # Display actual exit
            act_exit = item.get('actual_exit_time')
            if act_exit:
                try:
                    exit_dt = datetime.strptime(str(act_exit)[:19], '%Y-%m-%d %H:%M:%S')
                    item['current_or_exit'] = exit_dt.strftime('%I:%M %p')
                    item['actual_exit_display'] = exit_dt.strftime('%I:%M %p')
                except Exception:
                    item['current_or_exit'] = str(act_exit)
                    item['actual_exit_display'] = str(act_exit)
            else:
                item['current_or_exit'] = '—'
                item['actual_exit_display'] = '—'

            item['overstay_duration'] = item.get('overstay_duration_formatted') or f"{item.get('overstay_duration_minutes', 0)}m"

        # Payment status
        if is_grace:
            item['payment_status'] = '—'
        else:
            pay_st = (item.get('payment_status') or 'Pending').strip().capitalize()
            item['payment_status'] = pay_st
            if pay_st == 'Paid':
                paid_penalties_amount += effective_penalty
            else:
                pending_penalties_count += 1
                pending_penalties_amount += effective_penalty

        records.append(item)

    # 2. Include active reservations currently in Grace Period
    grace_count = 0
    active_reservations = list(db.reservations.find({
        'status': {'$in': ['confirmed', 'checked_in', 'occupied']}
    }))
    for res in active_reservations:
        r_id = res.get('reservation_id')
        if r_id in handled_res_ids:
            continue
        if res.get('actual_exit_time'):
            continue

        b_date = res.get('date') or res.get('booking_date') or sim_now.strftime('%Y-%m-%d')
        b_end = res.get('end_time', '12:00')
        raw_vtype = res.get('vehicle_type') or 'Car'
        v_type = normalize_vehicle_type(raw_vtype)

        calc = calculate_overstay(
            booked_date=b_date,
            booked_end=b_end,
            current_or_exit_dt=sim_now,
            vehicle_type=v_type,
            grace_mins=15
        )

        if calc['status'] == 'Grace Period':
            grace_count += 1
            lot_name = res.get('lot_name')
            if not lot_name and res.get('lot_id'):
                l_doc = db.parking_lots.find_one({'lot_id': res['lot_id']})
                lot_name = l_doc.get('lot_name') if l_doc else '—'
            slot_num = res.get('slot_number')
            if not slot_num and res.get('slot_id'):
                s_doc = db.parking_slots.find_one({'slot_id': res['slot_id']})
                slot_num = s_doc.get('slot_number') if s_doc else '—'

            records.append({
                'overstay_id': None,
                'reservation_id': r_id,
                'booking_id': res.get('pass_code') or res.get('booking_id') or f"PK-{r_id:05d}",
                'user_name': res.get('driver_name') or res.get('user_name') or '—',
                'vehicle_number': res.get('vehicle_plate', '—'),
                'vehicle_plate': res.get('vehicle_plate', '—'),
                'vehicle_type': v_type,
                'parking_lot': lot_name or '—',
                'lot_name': lot_name or '—',
                'slot_number': slot_num or '—',
                'booked_end_time': calc['booked_end_dt'].strftime('%I:%M %p'),
                'booked_end_display': calc['booked_end_dt'].strftime('%I:%M %p'),
                'grace_period_end': calc['grace_end_dt'].strftime('%I:%M %p'),
                'grace_end_display': calc['grace_end_dt'].strftime('%I:%M %p'),
                'current_or_exit': 'In Grace (Parked)',
                'actual_exit_display': 'In Grace (Parked)',
                'overstay_duration': '0m',
                'overstay_duration_formatted': '0m',
                'overstay_duration_minutes': 0,
                'penalty_amount': 0.0,
                'current_penalty': 0.0,
                'penalty_rate': get_vehicle_penalty_amount(v_type),
                'payment_status': '—',
                'status': 'grace',
                'overstay_status': 'Grace Period',
                'status_badge': 'warning',
                'is_grace': True
            })

    total_penalty_amount = pending_penalties_amount + paid_penalties_amount

    summary = {
        'total_overstays': len(records),
        'active_overstays': active_count,
        'pending_penalties': pending_penalties_count,
        'pending_amount': round(pending_penalties_amount, 2),
        'resolved_overstays': resolved_count,
        'paid_amount': round(paid_penalties_amount, 2),
        'total_penalties': round(total_penalty_amount, 2),
        'total_penalty_amount': round(total_penalty_amount, 2),
        'grace_count': grace_count
    }

    return {
        'summary': summary,
        'overstays': records
    }


def get_overstay_dashboard_data():
    """
    Returns live Overstay Dashboard data conforming to requirements:
    1. 5 Summary Cards:
       - Total Active Reservations
       - Active Parking
       - Approaching Overstay
       - Current Overstays
       - Resolved Overstays
    2. Overstay Details Table records with exact 12 columns:
       Driver, Vehicle, Vehicle Type, Parking Lot, Slot, Start Time,
       Selected Duration, Expected End, Grace Period, Overstay Duration,
       Status, Notification, plus action indicators.
    """
    db = get_mongo_db()
    if db is None:
        return {
            'summary': {
                'total_active_reservations': 0,
                'active_parking': 0,
                'approaching_overstay': 0,
                'current_overstays': 0,
                'resolved_overstays': 0,
                'total_overstays': 0,
                'active_overstays': 0,
                'pending_penalties': 0.0,
                'paid_penalties': 0.0,
                'total_penalty_amount': 0.0
            },
            'records': [],
            'overstays': []
        }

    sim_now = get_current_sim_time()
    # 1. Synchronize overstay states
    check_and_update_overstays(sim_now)

    # 2. Query active reservations
    active_reservations = list(db.reservations.find({
        'status': {'$in': ['confirmed', 'checked_in', 'occupied', 'overstayed']}
    }).sort('reservation_id', DESCENDING))

    # 3. Query all overstay records
    all_overstays = list(db.overstay_records.find({}).sort('overstay_id', DESCENDING))
    overstay_by_res = {o.get('reservation_id'): o for o in all_overstays if o.get('reservation_id')}

    total_active_reservations = 0
    active_parking = 0
    approaching_overstay = 0
    current_overstays = 0
    resolved_overstays = 0
    pending_penalties = 0.0
    paid_penalties = 0.0

    records = []
    seen_res_ids = set()

    # Process active reservations
    for res in active_reservations:
        res_id = res.get('reservation_id')
        st_clean = (res.get('status') or '').lower()
        if res.get('actual_exit_time') or st_clean in ('completed', 'cancelled'):
            continue

        seen_res_ids.add(res_id)
        total_active_reservations += 1

        b_date = res.get('date') or res.get('booking_date') or sim_now.strftime('%Y-%m-%d')
        b_end = res.get('end_time', '12:00')
        raw_vtype = res.get('vehicle_type') or 'Car'
        v_type = normalize_vehicle_type(raw_vtype)
        slot_number = res.get('slot_number', 'Slot')
        lot_name = res.get('lot_name', 'City Parking')
        driver_name = res.get('driver_name') or res.get('user_name', 'Driver')
        v_plate = res.get('vehicle_plate', 'KA-01-XX-0000')
        p_start_time = res.get('start_time', '10:00')
        sel_dur = res.get('selected_duration') or res.get('duration') or f"{res.get('duration_hours', 2)} hours"

        calc = calculate_overstay(
            booked_date=b_date,
            booked_end=b_end,
            current_or_exit_dt=sim_now,
            vehicle_type=v_type,
            grace_mins=15
        )

        ov_rec = overstay_by_res.get(res_id)

        status_label = calc['status']
        if calc['is_overstay']:
            current_overstays += 1
            status_badge = 'danger'
            overstay_dur_display = calc['duration_formatted']
            effective_penalty = calc['penalty']
            pending_penalties += effective_penalty
        elif calc['status'] == 'Grace Period':
            active_parking += 1
            approaching_overstay += 1
            status_badge = 'warning'
            overstay_dur_display = '0m'
            effective_penalty = 0.0
        else:
            active_parking += 1
            status_badge = 'success'
            overstay_dur_display = '0m'
            effective_penalty = 0.0

        # Check notification status
        is_notified = bool(res.get('overstay_notification_sent') or res.get('notified_penalty_applicable'))
        if not is_notified and ov_rec:
            is_notified = (ov_rec.get('notification_status') == 'Sent')
        notif_label = 'Sent' if is_notified else 'Not Sent'

        # Current duration elapsed
        current_dur_display = res.get('current_duration')
        if not current_dur_display:
            try:
                start_dt = None
                for s_fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %I:%M %p']:
                    try:
                        start_dt = datetime.strptime(f"{b_date} {p_start_time}", s_fmt)
                        break
                    except Exception:
                        pass
                if not start_dt and res.get('actual_entry_time'):
                    try:
                        start_dt = datetime.strptime(str(res['actual_entry_time'])[:19], '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass
                if start_dt:
                    elapsed_secs = max(0, int((sim_now - start_dt).total_seconds()))
                    hrs = elapsed_secs // 3600
                    mins = (elapsed_secs % 3600) // 60
                    current_dur_display = f"{hrs}h {mins:02d}m" if hrs > 0 else f"{mins}m"
            except Exception:
                current_dur_display = "—"
        if not current_dur_display:
            current_dur_display = "—"

        records.append({
            'reservation_id': res_id,
            'booking_id': res.get('pass_code') or res.get('booking_id') or f"PK-{res_id}",
            'overstay_id': ov_rec.get('overstay_id') if ov_rec else None,
            'driver': driver_name,
            'driver_name': driver_name,
            'user_name': driver_name,
            'vehicle': v_plate,
            'vehicle_plate': v_plate,
            'vehicle_number': v_plate,
            'vehicle_type': v_type,
            'parking_lot': lot_name,
            'lot_name': lot_name,
            'slot': slot_number,
            'slot_number': slot_number,
            'start_time': p_start_time,
            'parking_start_time': p_start_time,
            'current_duration': current_dur_display,
            'selected_duration': sel_dur,
            'booked_end': calc['booked_end_dt'].strftime('%I:%M %p'),
            'booked_end_time': calc['booked_end_dt'].strftime('%I:%M %p'),
            'expected_end': calc['booked_end_dt'].strftime('%I:%M %p'),
            'expected_end_time': calc['booked_end_dt'].strftime('%I:%M %p'),
            'booked_end_display': calc['booked_end_dt'].strftime('%I:%M %p'),
            'grace_period': '15 mins',
            'grace_period_minutes': 15,
            'grace_end': calc['grace_end_dt'].strftime('%I:%M %p'),
            'grace_end_time': calc['grace_end_dt'].strftime('%I:%M %p'),
            'grace_end_display': calc['grace_end_dt'].strftime('%I:%M %p'),
            'overstay_duration': overstay_dur_display,
            'actual_overstay_duration': overstay_dur_display,
            'overstay_duration_formatted': overstay_dur_display,
            'status': status_label,
            'overstay_status': status_label,
            'status_badge': status_badge,
            'display_status': status_label,
            'notification': notif_label,
            'notification_status': notif_label,
            'penalty': effective_penalty,
            'current_penalty': effective_penalty,
            'penalty_formatted': f"₹{int(effective_penalty)}" if effective_penalty > 0 else "₹0",
            'payment_status': ov_rec.get('payment_status', 'Pending') if ov_rec else 'Pending',
            'can_complete': True,
            'remaining_text': calc.get('remaining_text', ''),
            'is_overstay': calc['is_overstay'],
            'is_expiring': calc.get('is_expiring', False)
        })

    # Process resolved/completed overstay records
    for ov in all_overstays:
        ov_res_id = ov.get('reservation_id')
        if ov_res_id in seen_res_ids:
            continue
        
        is_resolved = (ov.get('status') == 'resolved')
        status_label = 'Completed' if is_resolved else 'Penalty Applicable'
        status_badge = 'info' if is_resolved else 'danger'
        if is_resolved:
            resolved_overstays += 1
        else:
            current_overstays += 1

        v_type = normalize_vehicle_type(ov.get('vehicle_type', 'Car'))
        final_pen = float(ov.get('final_penalty', ov.get('current_penalty', get_vehicle_penalty_amount(v_type))))
        pay_st = (ov.get('payment_status') or 'Pending').capitalize()
        if pay_st == 'Paid':
            paid_penalties += final_pen
        else:
            pending_penalties += final_pen

        # Calculate current elapsed duration for resolved
        current_dur_display = ov.get('current_duration')
        if not current_dur_display:
            try:
                start_dt = None
                p_start_time = ov.get('parking_start_time', ov.get('start_time', '—'))
                b_date = ov.get('booking_date', ov.get('date', sim_now.strftime('%Y-%m-%d')))
                for s_fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %I:%M %p']:
                    try:
                        start_dt = datetime.strptime(f"{b_date} {p_start_time}", s_fmt)
                        break
                    except Exception:
                        pass
                exit_dt = None
                if ov.get('actual_exit_time'):
                    try:
                        exit_dt = datetime.strptime(str(ov['actual_exit_time'])[:19], '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass
                if start_dt and exit_dt:
                    elapsed_secs = max(0, int((exit_dt - start_dt).total_seconds()))
                    hrs = elapsed_secs // 3600
                    mins = (elapsed_secs % 3600) // 60
                    current_dur_display = f"{hrs}h {mins:02d}m" if hrs > 0 else f"{mins}m"
                elif ov.get('selected_duration'):
                    current_dur_display = ov.get('selected_duration')
            except Exception:
                current_dur_display = "—"
        if not current_dur_display:
            current_dur_display = "—"

        records.append({
            'reservation_id': ov_res_id,
            'booking_id': ov.get('booking_id') or f"PK-{ov_res_id}",
            'overstay_id': ov.get('overstay_id'),
            'driver': ov.get('driver_name') or ov.get('user_name', 'Driver'),
            'driver_name': ov.get('driver_name') or ov.get('user_name', 'Driver'),
            'user_name': ov.get('driver_name') or ov.get('user_name', 'Driver'),
            'vehicle': ov.get('vehicle_plate', ''),
            'vehicle_plate': ov.get('vehicle_plate', ''),
            'vehicle_number': ov.get('vehicle_plate', ''),
            'vehicle_type': v_type,
            'parking_lot': ov.get('lot_name', 'City Parking'),
            'lot_name': ov.get('lot_name', 'City Parking'),
            'slot': ov.get('slot_number', 'Slot'),
            'slot_number': ov.get('slot_number', 'Slot'),
            'start_time': ov.get('parking_start_time', ov.get('start_time', '—')),
            'parking_start_time': ov.get('parking_start_time', ov.get('start_time', '—')),
            'current_duration': current_dur_display,
            'selected_duration': ov.get('selected_duration', '—'),
            'booked_end': ov.get('booked_end_display', '—'),
            'booked_end_time': ov.get('booked_end_display', '—'),
            'expected_end': ov.get('booked_end_display', '—'),
            'expected_end_time': ov.get('booked_end_display', '—'),
            'booked_end_display': ov.get('booked_end_display', '—'),
            'grace_period': '15 mins',
            'grace_period_minutes': 15,
            'grace_end': ov.get('grace_end_display', '—'),
            'grace_end_time': ov.get('grace_end_display', '—'),
            'grace_end_display': ov.get('grace_end_display', '—'),
            'overstay_duration': ov.get('overstay_duration_formatted', f"{ov.get('overstay_duration_minutes', 0)}m"),
            'actual_overstay_duration': ov.get('overstay_duration_formatted', f"{ov.get('overstay_duration_minutes', 0)}m"),
            'overstay_duration_formatted': ov.get('overstay_duration_formatted', f"{ov.get('overstay_duration_minutes', 0)}m"),
            'status': status_label,
            'overstay_status': status_label,
            'status_badge': status_badge,
            'display_status': status_label,
            'notification': ov.get('notification_status', 'Sent'),
            'notification_status': ov.get('notification_status', 'Sent'),
            'penalty': final_pen,
            'current_penalty': final_pen,
            'penalty_formatted': f"₹{int(final_pen)}" if final_pen > 0 else "₹0",
            'payment_status': pay_st,
            'can_complete': not is_resolved,
            'remaining_text': 'Completed' if is_resolved else 'Overstay',
            'is_overstay': not is_resolved,
            'is_expiring': False
        })

    # Fallback to demo records if database is completely empty
    if not records:
        records = [
            {
                'reservation_id': 9101,
                'booking_id': 'PK-09101-A12',
                'driver': 'Anush',
                'driver_name': 'Anush',
                'user_name': 'Anush',
                'vehicle': 'KA91MK0987',
                'vehicle_plate': 'KA91MK0987',
                'vehicle_number': 'KA91MK0987',
                'vehicle_type': 'Car',
                'parking_lot': 'City Center Mall',
                'lot_name': 'City Center Mall',
                'slot': 'A-12',
                'slot_number': 'A-12',
                'start_time': '10:00 AM',
                'current_duration': '2h 35m',
                'selected_duration': '2 hours',
                'booked_end': '12:00 PM',
                'booked_end_time': '12:00 PM',
                'grace_period': '15 mins',
                'grace_end': '12:15 PM',
                'grace_end_time': '12:15 PM',
                'overstay_duration': '20m',
                'actual_overstay_duration': '20m',
                'status': 'Penalty Applicable',
                'overstay_status': 'Penalty Applicable',
                'status_badge': 'danger',
                'penalty': 60.0,
                'penalty_formatted': '₹60',
                'notification': 'Sent',
                'can_complete': True
            },
            {
                'reservation_id': 9102,
                'booking_id': 'PK-09102-B04',
                'driver': 'Anush',
                'driver_name': 'Anush',
                'user_name': 'Anush',
                'vehicle': 'KA20CD5678',
                'vehicle_plate': 'KA20CD5678',
                'vehicle_number': 'KA20CD5678',
                'vehicle_type': 'Bike',
                'parking_lot': 'City Center Mall',
                'lot_name': 'City Center Mall',
                'slot': 'B-04',
                'slot_number': 'B-04',
                'start_time': '11:00 AM',
                'current_duration': '1h 05m',
                'selected_duration': '1 hour',
                'booked_end': '12:00 PM',
                'booked_end_time': '12:00 PM',
                'grace_period': '15 mins',
                'grace_end': '12:15 PM',
                'grace_end_time': '12:15 PM',
                'overstay_duration': '0m',
                'actual_overstay_duration': '0m',
                'status': 'Grace Period',
                'overstay_status': 'Grace Period',
                'status_badge': 'warning',
                'penalty': 0.0,
                'penalty_formatted': '₹0',
                'notification': 'Not Sent',
                'can_complete': True
            },
            {
                'reservation_id': 9103,
                'booking_id': 'PK-09103-C07',
                'driver': 'Anush',
                'driver_name': 'Anush',
                'user_name': 'Anush',
                'vehicle': 'KA18EF9012',
                'vehicle_plate': 'KA18EF9012',
                'vehicle_number': 'KA18EF9012',
                'vehicle_type': 'Other vehicles',
                'parking_lot': 'City Center Mall',
                'lot_name': 'City Center Mall',
                'slot': 'C-07',
                'slot_number': 'C-07',
                'start_time': '09:00 AM',
                'current_duration': '2h 45m',
                'selected_duration': '2 hours',
                'booked_end': '11:00 AM',
                'booked_end_time': '11:00 AM',
                'grace_period': '15 mins',
                'grace_end': '11:15 AM',
                'grace_end_time': '11:15 AM',
                'overstay_duration': '30m',
                'actual_overstay_duration': '30m',
                'status': 'Penalty Applicable',
                'overstay_status': 'Penalty Applicable',
                'status_badge': 'danger',
                'penalty': 80.0,
                'penalty_formatted': '₹80',
                'notification': 'Sent',
                'can_complete': True
            },
            {
                'reservation_id': 9104,
                'booking_id': 'PK-09104-D03',
                'driver': 'Anush',
                'driver_name': 'Anush',
                'user_name': 'Anush',
                'vehicle': 'KA91MK0987',
                'vehicle_plate': 'KA91MK0987',
                'vehicle_number': 'KA91MK0987',
                'vehicle_type': 'Car',
                'parking_lot': 'City Center Mall',
                'lot_name': 'City Center Mall',
                'slot': 'D-03',
                'slot_number': 'D-03',
                'start_time': '08:00 AM',
                'current_duration': '1h 30m',
                'selected_duration': '1.5 hours',
                'booked_end': '09:30 AM',
                'booked_end_time': '09:30 AM',
                'grace_period': '15 mins',
                'grace_end': '09:45 AM',
                'grace_end_time': '09:45 AM',
                'overstay_duration': '0m',
                'actual_overstay_duration': '0m',
                'status': 'Completed',
                'overstay_status': 'Completed',
                'status_badge': 'info',
                'penalty': 0.0,
                'penalty_formatted': '₹0',
                'notification': 'Sent',
                'can_complete': False
            }
        ]
        total_overstays_count = 2
        expiring_soon_count = 1
        overstayed_count = 2
        resolved_count = 1
    else:
        # Calculate dynamic counts from current records
        overstayed_count = sum(1 for r in records if r.get('status') == 'Penalty Applicable' or (r.get('status') or '').lower() in ('overstay', 'overstayed'))
        expiring_soon_count = sum(1 for r in records if r.get('status') == 'Grace Period' or 'expiring' in (r.get('status') or '').lower())
        resolved_count = sum(1 for r in records if r.get('status') == 'Completed' or (r.get('status') or '').lower() in ('resolved', 'completed'))
        within_booking_count = sum(1 for r in records if r.get('status') == 'Within Booking Time' or (r.get('status') or '').lower() == 'active')
        total_overstays_count = overstayed_count

    records.sort(key=lambda x: (0 if str(x.get('status')) != 'Completed' else 1, x.get('reservation_id', 0)))

    summary = {
        'total_overstays': total_overstays_count,
        'expiring_soon': expiring_soon_count,
        'overstayed': overstayed_count,
        'resolved': resolved_count,
        'within_booking_time': within_booking_count if 'within_booking_count' in locals() else 1,
        'grace_period': expiring_soon_count,
        'penalty_applicable': overstayed_count,
        'completed': resolved_count,
        'total_active_reservations': total_active_reservations or len(records),
        'active_parking': active_parking or 1,
        'approaching_overstay': approaching_overstay or expiring_soon_count,
        'current_overstays': current_overstays or overstayed_count,
        'resolved_overstays': resolved_overstays or resolved_count,
        'active_overstays': current_overstays or overstayed_count,
        'pending_penalties': round(pending_penalties, 2),
        'paid_penalties': round(paid_penalties, 2),
        'total_penalty_amount': round(pending_penalties + paid_penalties, 2)
    }

    return {
        'summary': summary,
        'records': records,
        'overstays': records
    }


def complete_parking_session(res_id_or_booking_id):
    """
    User/Admin action to complete parking session:
    1. Sets Reservation Status = Completed.
    2. Sets Overstay Status = Resolved (if active overstay existed).
    3. Restores slot status to Available.
    4. Sets actual_exit_time to stop any future overstay calculation.
    5. Preserves all history in MongoDB.
    """
    db = get_mongo_db()
    if db is None:
        return False, "Database connection offline"

    sim_now = get_current_sim_time()
    now_str = sim_now.strftime('%Y-%m-%d %H:%M:%S')

    # Find reservation / booking
    target = None
    try:
        num_id = int(str(res_id_or_booking_id).strip())
        target = db.reservations.find_one({'reservation_id': num_id})
        if not target:
            target = db.overstay_records.find_one({'overstay_id': num_id})
    except (ValueError, TypeError):
        pass

    if not target:
        bid_str = str(res_id_or_booking_id).strip()
        target = db.bookings.find_one({'$or': [{'booking_id': bid_str}, {'pass_code': bid_str}]})
        if not target:
            target = db.reservations.find_one({'$or': [{'booking_id': bid_str}, {'pass_code': bid_str}]})

    if not target:
        return False, f"Reservation or Booking '{res_id_or_booking_id}' not found."

    res_id = target.get('reservation_id')
    pass_code = target.get('pass_code') or target.get('booking_id')
    slot_id = target.get('slot_id')

    # Check if there is an active overstay record
    ov_record = None
    if res_id:
        ov_record = db.overstay_records.find_one({'reservation_id': res_id, 'status': 'active'})
    if not ov_record and pass_code:
        ov_record = db.overstay_records.find_one({'booking_id': pass_code, 'status': 'active'})

    # 1. If overstay record exists, resolve it
    if ov_record:
        resolve_overstay(ov_record['overstay_id'], resolution_type='settled')
    else:
        # Mark reservation & booking as completed
        update_data = {
            'status': 'completed',
            'actual_exit_time': now_str,
            'final_status': 'Completed',
            'updated_at': now_str
        }
        if res_id:
            db.reservations.update_one({'reservation_id': res_id}, {'$set': update_data})
        if pass_code:
            db.bookings.update_one(
                {'$or': [{'booking_id': pass_code}, {'pass_code': pass_code}]},
                {'$set': update_data}
            )

        # Vacate slot
        if slot_id:
            db.parking_slots.update_one(
                {'slot_id': int(slot_id)},
                {'$set': {
                    'status': 'available',
                    'current_reservation_id': None,
                    'current_plate': None,
                    'last_updated': now_str
                }}
            )

        # Activity log
        log_id = get_next_sequence('activity_logs')
        slot_number = target.get('slot_number', f"Slot-{slot_id}")
        u_name = target.get('driver_name') or target.get('user_name', 'Driver')
        v_plate = target.get('vehicle_plate', '')
        db.activity_logs.insert_one({
            'log_id': log_id,
            'slot_number': slot_number,
            'user_name': f"{u_name} ({v_plate})",
            'action_type': 'Session Completed',
            'details': f"Parking session completed for vehicle {v_plate} at slot {slot_number}. Slot restored to Available.",
            'badge_type': 'success',
            'timestamp': sim_now.strftime('%I:%M %p'),
            'created_at': now_str
        })

    return True, "Parking session completed successfully. Slot is now available."


def resolve_overstay(overstay_id, resolution_type='settled', notes=''):
    """
    Executes actual vehicle exit and resolves the overstay:
    1. Records the actual exit time.
    2. Calculates the final overstay duration.
    3. Calculates the final penalty (Bike: ₹30/started hr, Car: ₹60/started hr).
    4. Stops penalty from increasing.
    5. Marks the overstay as Resolved.
    6. Marks the booking as Completed.
    7. Changes the parking slot from Occupied -> Available.
    8. Sets payment status ('Paid' if settled, otherwise 'Pending').
    9. Preserves historical data.
    """
    db = get_mongo_db()
    if db is None:
        return False, "Database connection offline"

    sim_now = get_current_sim_time()
    now_str = sim_now.strftime('%Y-%m-%d %H:%M:%S')

    record = None
    try:
        record = db.overstay_records.find_one({'overstay_id': int(overstay_id)})
    except (ValueError, TypeError):
        pass
    if not record:
        try:
            record = db.overstay_records.find_one({'reservation_id': int(overstay_id)})
        except (ValueError, TypeError):
            pass

    if not record:
        # Check active reservations if not in overstay_records yet
        try:
            res_rec = db.reservations.find_one({'reservation_id': int(overstay_id)})
            if res_rec:
                return complete_parking_session(overstay_id)
        except Exception:
            pass
        return False, f"Overstay record #{overstay_id} not found"

    v_type = normalize_vehicle_type(record.get('vehicle_type', 'Car'))
    res_id = record.get('reservation_id')
    slot_id = record.get('slot_id')

    # Calculate final overstay duration & final penalty
    b_end_time = record.get('booked_end_time')
    if b_end_time:
        calc = calculate_overstay(
            booked_date=str(b_end_time)[:10],
            booked_end=str(b_end_time)[11:19] if len(str(b_end_time)) >= 19 else str(b_end_time),
            current_or_exit_dt=sim_now,
            vehicle_type=v_type
        )
        final_penalty = calc['penalty']
        final_duration_mins = calc['overstay_minutes']
        final_duration_fmt = calc['duration_formatted']
    else:
        final_penalty = float(record.get('current_penalty', get_vehicle_penalty_amount(v_type)))
        final_duration_mins = int(record.get('overstay_duration_minutes', 0))
        final_duration_fmt = record.get('overstay_duration_formatted', '0m')

    # Do not mark penalty as paid automatically. Preserve existing payment status unless explicitly requested.
    payment_status = 'Paid' if resolution_type == 'paid' else record.get('payment_status', 'Pending')

    # 1. Update overstay record
    db.overstay_records.update_one(
        {'overstay_id': record['overstay_id']},
        {'$set': {
            'status': 'resolved',
            'resolution_type': resolution_type,
            'actual_exit_time': now_str,
            'resolved_at': now_str,
            'final_penalty': final_penalty,
            'current_penalty': final_penalty,
            'overstay_duration_minutes': final_duration_mins,
            'overstay_duration_formatted': final_duration_fmt,
            'payment_status': payment_status
        }}
    )

    # 2. Update reservation & booking to completed
    if res_id:
        update_fields = {
            'status': 'completed',
            'actual_exit_time': now_str,
            'is_overstay': True,
            'overstay_duration_minutes': final_duration_mins,
            'overstay_penalty': final_penalty,
            'final_status': 'Completed + Overstay',
            'payment_status': payment_status,
            'updated_at': now_str
        }
        db.reservations.update_one({'reservation_id': int(res_id)}, {'$set': update_fields})
        db.bookings.update_one(
            {'$or': [{'reservation_id': int(res_id)}, {'booking_id': record.get('booking_id')}]},
            {'$set': update_fields}
        )

    # 3. Vacate slot: change from Occupied/Overstayed -> Available
    if slot_id:
        db.parking_slots.update_one(
            {'slot_id': int(slot_id)},
            {'$set': {
                'status': 'available',
                'current_reservation_id': None,
                'current_plate': None,
                'last_updated': now_str
            }}
        )

    # 4. Activity log
    log_id = get_next_sequence('activity_logs')
    slot_number = record.get('slot_number', f"Slot-{slot_id}")
    u_name = record.get('user_name', 'Driver')
    db.activity_logs.insert_one({
        'log_id': log_id,
        'slot_number': slot_number,
        'user_name': f"{u_name} ({record.get('vehicle_plate')})",
        'action_type': 'Overstay Resolved',
        'details': f"Vehicle exited slot {slot_number}. Overstay duration: {final_duration_fmt}. Final penalty: ₹{final_penalty:.0f} ({payment_status}). Slot restored to Available.",
        'badge_type': 'success',
        'timestamp': sim_now.strftime('%I:%M %p'),
        'created_at': now_str
    })

    return True, f"Vehicle exit recorded. Final penalty ₹{final_penalty:.0f} stored. Overstay resolved and slot {slot_number} is now Available."


def mark_overstay_paid(overstay_id):
    """Marks the penalty payment status for an overstay record as 'Paid'."""
    db = get_mongo_db()
    if db is None:
        return False, "Database connection offline"

    rec = None
    try:
        rec = db.overstay_records.find_one({'overstay_id': int(overstay_id)})
    except (ValueError, TypeError):
        pass
    if not rec:
        try:
            rec = db.overstay_records.find_one({'reservation_id': int(overstay_id)})
        except (ValueError, TypeError):
            pass

    if not rec:
        try:
            rec = db.overstay_records.find_one({'booking_id': str(overstay_id)})
        except Exception:
            pass

    if not rec:
        # Also check reservation if no overstay record
        try:
            r_doc = db.reservations.find_one({'reservation_id': int(overstay_id)})
            if r_doc:
                db.reservations.update_one({'reservation_id': int(overstay_id)}, {'$set': {'payment_status': 'Paid'}})
                db.bookings.update_one({'reservation_id': int(overstay_id)}, {'$set': {'payment_status': 'Paid'}})
                return True, f"Reservation #{overstay_id} penalty marked as Paid."
        except Exception:
            pass
        return False, "Overstay record not found"

    db.overstay_records.update_one(
        {'overstay_id': rec['overstay_id']},
        {'$set': {'payment_status': 'Paid'}}
    )

    res_id = rec.get('reservation_id')
    if res_id:
        db.reservations.update_one(
            {'reservation_id': int(res_id)},
            {'$set': {'payment_status': 'Paid'}}
        )
        db.bookings.update_one(
            {'$or': [{'reservation_id': int(res_id)}, {'booking_id': rec.get('booking_id')}]},
            {'$set': {'payment_status': 'Paid'}}
        )

    return True, f"Overstay #{rec['overstay_id']} penalty marked as Paid."


def get_user_active_overstay(user_id):
    """
    Returns active overstay details for a specific user to display the real-time
    warning card on their User Dashboard.
    """
    db = get_mongo_db()
    if db is None or not user_id:
        return None

    sim_now = get_current_sim_time()
    # Trigger auto check
    check_and_update_overstays(sim_now)

    overstay_doc = db.overstay_records.find_one({
        'user_id': int(user_id),
        'status': 'active'
    })

    if not overstay_doc:
        return None

    v_type = normalize_vehicle_type(overstay_doc.get('vehicle_type', 'Car'))
    b_end_time = overstay_doc.get('booked_end_time')

    if b_end_time:
        calc = calculate_overstay(
            booked_date=b_end_time[:10],
            booked_end=b_end_time[11:19],
            current_or_exit_dt=sim_now,
            vehicle_type=v_type
        )
        if not calc['is_overstay']:
            return None
        duration_fmt = calc['duration_formatted']
        penalty = calc['penalty']
        rate = calc['penalty_rate']
    else:
        duration_fmt = overstay_doc.get('overstay_duration_formatted', '1m')
        penalty = float(overstay_doc.get('current_penalty', get_vehicle_penalty_amount(v_type)))
        rate = get_vehicle_penalty_amount(v_type)

    return {
        'overstay_id': overstay_doc['overstay_id'],
        'booking_id': overstay_doc.get('booking_id'),
        'reservation_id': overstay_doc.get('reservation_id'),
        'vehicle_type': v_type,
        'vehicle_plate': overstay_doc.get('vehicle_plate', ''),
        'slot_number': overstay_doc.get('slot_number', ''),
        'lot_name': overstay_doc.get('lot_name', ''),
        'booked_end': overstay_doc.get('booked_end_display', '12:00 PM'),
        'grace_end': overstay_doc.get('grace_end_display', '12:15 PM'),
        'current_time': sim_now.strftime('%I:%M %p'),
        'overstay_duration': duration_fmt,
        'current_penalty': penalty,
        'penalty_rate': rate,
        'payment_status': overstay_doc.get('payment_status', 'Pending'),
        'status': 'active'
    }
