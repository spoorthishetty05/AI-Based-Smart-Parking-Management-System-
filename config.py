"""

Central Configuration Module for AI-Based Smart Parking System.
Provides environment-aware settings for Flask, MongoDB, Simulation, Security, and Email Transport.
"""

import os

def _load_env_file(filepath):
    """Zero-dependency .env parser fallback."""
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_BASE_DIR, '.env')

try:
    from dotenv import load_dotenv
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
    else:
        load_dotenv()
except ImportError:
    _load_env_file(_env_path)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _str_to_bool(val, default=False):
    if val is None:
        return default
    return str(val).strip().lower() in ('true', '1', 'yes', 'y', 't')

class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-parking-ai-secret-2026')
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'smart_parking')
    SIMULATION_DEFAULT_OFFSET = int(os.environ.get('SIMULATION_OFFSET', 0))
    DEFAULT_GRACE_PERIOD_MINUTES = 15
    DEFAULT_CAR_PENALTY = 60.0
    DEFAULT_BIKE_PENALTY = 30.0
    DEFAULT_OTHER_PENALTY = 80.0
    DEBUG = False
    TESTING = False

    # ------------------------------------------------------------------
    # Email Transport Configuration (Native Python SSL/TLS)
    # Nodemailer parity: 'secure: true' maps to SSL/TLS (port 465)
    # 'secure: false' maps to STARTTLS (port 587 or 25)
    # ------------------------------------------------------------------
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')

    # Explicit secure flag (identically mirroring Nodemailer's secure: true / false)
    _mail_secure_env = os.environ.get('MAIL_SECURE')
    if _mail_secure_env is not None:
        MAIL_SECURE = _str_to_bool(_mail_secure_env, default=False)
        MAIL_USE_SSL = MAIL_SECURE
        MAIL_USE_TLS = not MAIL_SECURE
    else:
        # Default based on port: 465 -> SSL/TLS, 587 -> STARTTLS
        MAIL_USE_SSL = _str_to_bool(os.environ.get('MAIL_USE_SSL', 'false')) or (MAIL_PORT == 465)
        MAIL_USE_TLS = _str_to_bool(os.environ.get('MAIL_USE_TLS', 'true')) if MAIL_PORT != 465 else False
        MAIL_SECURE = MAIL_USE_SSL

    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'Smart Parking AI <noreply@smartparking.ai>')
    MAIL_DEFAULT_SENDER_NAME = os.environ.get('MAIL_DEFAULT_SENDER_NAME', 'Smart Parking AI')
    MAIL_DEFAULT_SENDER_EMAIL = os.environ.get('MAIL_DEFAULT_SENDER_EMAIL', 'noreply@smartparking.ai')
    MAIL_REPLY_TO = os.environ.get('MAIL_REPLY_TO', '')
    MAIL_TIMEOUT = int(os.environ.get('MAIL_TIMEOUT', 15))
    MAIL_MAX_WORKERS = int(os.environ.get('MAIL_MAX_WORKERS', 4))
    MAIL_SUPPRESS_SEND = _str_to_bool(os.environ.get('MAIL_SUPPRESS_SEND', 'false'))
    MAIL_DEBUG = _str_to_bool(os.environ.get('MAIL_DEBUG', 'false'))

    # ------------------------------------------------------------------
    # Razorpay Payment Gateway Configuration (Sandbox / Dummy & Live)
    # ------------------------------------------------------------------
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_smartpark123')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'mock_secret_key_smartpark999')
    RAZORPAY_CURRENCY = os.environ.get('RAZORPAY_CURRENCY', 'INR')
    RAZORPAY_COMPANY_NAME = os.environ.get('RAZORPAY_COMPANY_NAME', 'Smart Parking AI')
    RAZORPAY_MOCK_MODE = _str_to_bool(os.environ.get('RAZORPAY_MOCK_MODE', 'true'))

class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True

class TestingConfig(Config):
    """Testing environment configuration."""
    TESTING = True
    DEBUG = True
    MONGO_DB_NAME = os.environ.get('TEST_MONGO_DB_NAME', 'smart_parking')
    # Suppress real SMTP network calls during test runs
    MAIL_SUPPRESS_SEND = True

class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    TESTING = False

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
