"""
Authentication & Authorization Middleware for AI-Based Smart Parking System.
Provides decorators and security helpers across all Flask Blueprints.
"""

import hmac
from functools import wraps
from urllib.parse import urlparse
from flask import session, request, jsonify, redirect, url_for, flash
from werkzeug.security import check_password_hash


def verify_password_hash(stored_hash, password):
    """Verifies password hash using constant-time comparison to prevent timing attacks."""
    if not stored_hash or not password:
        return False
    try:
        if check_password_hash(stored_hash, password):
            return True
    except Exception:
        pass
    # Backward compatibility constant-time verification for non-standard legacy entries
    if isinstance(stored_hash, str) and not stored_hash.startswith(('scrypt:', 'pbkdf2:')):
        return hmac.compare_digest(stored_hash, password)
    return False


def is_safe_redirect_url(target):
    """
    Validates redirect URLs against Open Redirect attacks.
    Ensures URL is strictly local (relative path) and does not point to external hosts.
    """
    if not target or not isinstance(target, str):
        return False
    # Must start with a single '/' and not '//' or '/\'
    if not target.startswith('/') or target.startswith('//') or target.startswith('/\\'):
        return False
    # Verify hostname component is empty
    try:
        parsed = urlparse(target)
        if parsed.scheme or parsed.netloc:
            return False
    except Exception:
        return False
    return True


def login_required(f):
    """Session-based route protection decorator."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Authentication required. Please log in.'}), 401
            try:
                target_url = url_for('auth.login_page', next=request.path)
            except Exception:
                target_url = url_for('auth.login_page', next=request.path)
            return redirect(target_url)
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Session and role-based route protection decorator for Administrator operations."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Authentication required. Please log in as Administrator.'}), 401
            try:
                target_url = url_for('auth.login_page', tab='admin', next=request.path)
            except Exception:
                target_url = url_for('auth.login_page', tab='admin', next=request.path)
            return redirect(target_url)
        if session.get('user_role') != 'admin':
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Access Denied: Administrator privileges required.'}), 403
            flash('Access Denied: Administrator privileges required.', 'error')
            try:
                home_url = url_for('web.index')
            except Exception:
                home_url = url_for('web.index')
            return redirect(home_url)
        return f(*args, **kwargs)
    return decorated_function


def security_required(f):
    """Session and role-based route protection decorator for Security Personnel & Admins."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Authentication required. Please log in as Security Guard.'}), 401
            try:
                target_url = url_for('auth.login_page', tab='security', next=request.path)
            except Exception:
                target_url = url_for('auth.login_page', tab='security', next=request.path)
            return redirect(target_url)
        if session.get('user_role') not in ('security', 'guard', 'admin'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Access Denied: Security Guard privileges required.'}), 403
            flash('Access Denied: Security Guard privileges required.', 'error')
            try:
                home_url = url_for('web.index')
            except Exception:
                home_url = url_for('web.index')
            return redirect(home_url)
        return f(*args, **kwargs)
    return decorated_function


def get_authenticated_user_id(target_user_id=None):
    """
    Returns (user_id, error_response_tuple).
    Enforces that only the authenticated user (or an admin) can access or modify data.
    Guarantees strict isolation between User A and User B.
    """
    if 'user_id' not in session:
        return None, (jsonify({'status': 'error', 'message': 'Authentication required. Please log in.'}), 401)
    
    current_uid = session['user_id']
    is_admin = (session.get('user_role') == 'admin')

    if target_user_id is not None:
        try:
            target_uid = int(target_user_id)
        except (ValueError, TypeError):
            return None, (jsonify({'status': 'error', 'message': 'Invalid user ID format.'}), 400)

        if target_uid != current_uid and not is_admin:
            return None, (jsonify({'status': 'error', 'message': "Forbidden: You do not have permission to access or modify another user's profile or vehicles."}), 403)
        return target_uid, None

    return current_uid, None

