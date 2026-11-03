"""
Application Entrypoint & Modular Server Startup for AI-Based Smart Parking System.
All route handlers are organized cleanly across domain blueprints in the routes/ package.
"""

import os
import sys
from flask import Flask
from flask_cors import CORS
from config import Config

# Ensure core domain package is accessible
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_DIR = os.path.join(_BASE_DIR, 'core')
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

from core.database import init_db
from core.overstay_engine import check_and_update_overstays
from core.email_service import mail_service
from routes import register_all_blueprints

# Initialize Application
app = Flask(__name__)
CORS(app)
app.config.from_object(Config)

# Initialize Native Python SSL/TLS Secure Email Transport
mail_service.init_app(app)

# Ensure MongoDB database and collections exist on startup
try:
    init_db()
except Exception as e:
    print(f"[MongoDB Startup Notice] {e}")

# Auto-check initial overstays
try:
    check_and_update_overstays()
except Exception as e:
    print(f"[Overstay Check Notice] {e}")

# Register all modular Flask Blueprints
register_all_blueprints(app)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting AI-Based Smart Parking System server on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=Config.DEBUG)
