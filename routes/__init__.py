"""
Routes Package for AI-Based Smart Parking System.
Exports and registers all domain-specific Flask Blueprints.
"""

from .auth_routes import auth_bp
from .web_routes import web_bp
from .booking_routes import booking_bp
from .payment_routes import payment_bp
from .admin_routes import admin_bp
from .user_routes import user_bp
from .lot_routes import lot_bp
from .ai_routes import ai_bp
from .overstay_routes import overstay_bp
from .simulation_routes import simulation_bp
from .exchange_routes import exchange_bp
from .email_routes import email_bp
from .security_routes import security_bp


def register_all_blueprints(app):
    """Registers all 13 modular Flask Blueprints onto the main application."""
    # 1. Authentication & Security
    app.register_blueprint(auth_bp)

    # 2. Web Application Shell (Dashboard, User & Admin Portals)
    app.register_blueprint(web_bp)

    # 3. 5-Step Guided Booking Wizard & Reservations
    app.register_blueprint(booking_bp)

    # 4. Razorpay Sandbox Payment Gateway
    app.register_blueprint(payment_bp)

    # 5. System Administration & Telemetry
    app.register_blueprint(admin_bp)

    # 6. User Profile & Multi-Vehicle Management
    app.register_blueprint(user_bp)

    # 7. Parking Facilities & 2D Slot Management
    app.register_blueprint(lot_bp)

    # 8. AI / Machine Learning & Intelligent Recommendations
    app.register_blueprint(ai_bp)

    # 9. Real-Time Overstay Radar & Penalties
    app.register_blueprint(overstay_bp)

    # 10. Virtual Clock & Dynamic Simulation
    app.register_blueprint(simulation_bp)

    # 11. Peer-to-Peer Slot Exchange & 2D Visual Swap
    app.register_blueprint(exchange_bp)

    # 12. Secure Email Transport Diagnostics
    app.register_blueprint(email_bp)

    # 13. Security Guard Gate Management & Walk-in Terminal
    app.register_blueprint(security_bp)

    # Register root endpoint aliases for backward compatibility with url_for calls
    # (e.g. url_for('login_page'), url_for('index'), url_for('admin_panel'), url_for('booking_my_bookings'))
    aliases = [
        ('/login', 'login_page', auth_bp.view_functions.get('login_page'), ['GET', 'POST']),
        ('/register', 'register_page', auth_bp.view_functions.get('register_page'), ['GET', 'POST']),
        ('/logout', 'logout', auth_bp.view_functions.get('logout'), ['GET', 'POST']),
        ('/', 'index', web_bp.view_functions.get('index'), ['GET']),
        ('/admin', 'admin_panel', web_bp.view_functions.get('admin_panel'), ['GET']),
        ('/user', 'user_panel', web_bp.view_functions.get('user_panel'), ['GET']),
        ('/security', 'security_dashboard', security_bp.view_functions.get('security_dashboard'), ['GET']),
        ('/booking', 'booking_panel', booking_bp.view_functions.get('booking_panel'), ['GET']),
        ('/booking/my-bookings', 'booking_my_bookings', booking_bp.view_functions.get('booking_my_bookings'), ['GET']),
    ]
    for rule, endpoint, view_func, methods in aliases:
        if view_func is not None:
            try:
                app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)
            except AssertionError:
                pass

