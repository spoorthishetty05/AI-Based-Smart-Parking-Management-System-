"""
Shared Fixtures & Test Utilities for AI-Based Smart Parking System Test Suite.
"""

import sys
import os
from datetime import datetime, timedelta

# Ensure project root and core are on sys.path
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_TESTS_DIR)
for _p in [_ROOT_DIR, os.path.join(_ROOT_DIR, 'core')]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app as flask_app_module
from core.database import get_mongo_db, get_next_sequence, clear_and_init_mongodb

def get_test_app():
    """Returns configured Flask app in testing mode."""
    app = flask_app_module.app
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app

def get_test_client():
    """Returns Flask test client."""
    return get_test_app().test_client()

def get_future_date_and_time(days_ahead=1, start_hour=10, duration_hours=2):
    """Generates guaranteed future date and time strings for anti-past-date validation."""
    target_dt = datetime.now() + timedelta(days=days_ahead)
    date_str = target_dt.strftime('%Y-%m-%d')
    start_time_str = f"{start_hour:02d}:00"
    end_dt = datetime.strptime(f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M") + timedelta(hours=duration_hours)
    end_time_str = end_dt.strftime('%H:%M')
    return date_str, start_time_str, end_time_str

def create_authenticated_session(client, role='user', user_id=None, email=None, name=None):
    """Establishes an authenticated session directly in the test client."""
    with client.session_transaction() as sess:
        sess['user_id'] = user_id or (1 if role == 'admin' else 3)
        sess['user_name'] = name or ('System Administrator' if role == 'admin' else 'Test Driver')
        sess['user_email'] = email or ('admin@smartparking.ai' if role == 'admin' else 'test.driver@smartparking.ai')
        sess['user_role'] = role
        sess['user_phone'] = '9876543210'
        sess['logged_in'] = True

