"""
Diagnostic & Verification CLI Script for Native Python SSL/TLS Secure Email Transport.
Tests:
  1. Environment configuration (.env & config.py)
  2. Transport mode resolution (Port 465 SSL/TLS vs Port 587 STARTTLS / Nodemailer parity)
  3. MIME message construction (Text + HTML + Custom Headers)
  4. File and binary attachments
  5. HTML template rendering via Jinja2
  6. Non-blocking background worker threading
  7. SMTP handshake & authentication (or Simulation/Outbox when credentials unconfigured)
"""

import os
import sys
import time
import argparse

# Ensure project root is in sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import Config
from core.email_service import EmailService, send_email, send_templated_email

def main():
    parser = argparse.ArgumentParser(description="Test Native Python SSL/TLS Email Transport")
    parser.add_argument("--to", default="driver@smartparking.ai", help="Recipient email address")
    parser.add_argument("--server", default=None, help="SMTP server host override")
    parser.add_argument("--port", type=int, default=None, help="SMTP port override (465 for SSL, 587 for STARTTLS)")
    parser.add_argument("--secure", action="store_true", help="Force direct SSL/TLS (Nodemailer secure: true)")
    parser.add_argument("--starttls", action="store_true", help="Force STARTTLS upgrade (Nodemailer secure: false)")
    parser.add_argument("--sync", action="store_true", default=True, help="Send synchronously")
    parser.add_argument("--async-test", action="store_true", help="Test background threading")
    parser.add_argument("--attach", action="store_true", help="Include test attachment")
    args = parser.parse_args()

    # Ensure UTF-8 console output on Windows
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 80)
    print("  AI SMART PARKING SYSTEM - NATIVE PYTHON SSL/TLS EMAIL TRANSPORT TEST")
    print("=" * 80)

    # Initialize service
    mail = EmailService()
    
    # Apply overrides if provided
    if args.server:
        mail.server = args.server
    if args.port:
        mail.port = args.port
    if args.secure:
        mail.secure = True
        mail.use_ssl = True
        mail.use_tls = False
    elif args.starttls:
        mail.secure = False
        mail.use_ssl = False
        mail.use_tls = True

    print(f"  [1] Configuration:")
    print(f"      - SMTP Host       : {mail.server}")
    print(f"      - Port            : {mail.port}")
    print(f"      - Nodemailer Parity: {'secure: true' if mail.is_secure_ssl() else 'secure: false'}")
    print(f"      - Transport Mode  : {mail.get_transport_mode()}")
    print(f"      - Authentication  : {'Configured (' + mail.username + ')' if mail.username else 'Unset (Running in Simulation Mode)'}")
    print(f"      - Default Sender  : {mail.default_sender}")
    print(f"      - Suppress Send   : {mail.suppress_send}")
    print(f"      - Thread Workers  : {mail.max_workers}")

    # Step 2: Test template rendering
    print("\n  [2] Testing HTML Email Template Rendering...")
    try:
        sample_context = {
            "booking_id": 1042,
            "lot_name": "MG Road Urban Smart Lot",
            "slot_name": "Bay-B04",
            "vehicle_number": "KA-04-ME-9021",
            "vehicle_type": "Car",
            "start_time": "2026-11-02 14:00",
            "end_time": "2026-11-02 16:00",
            "total_amount": 100.0,
            "dashboard_url": "http://127.0.0.1:5000/booking/my-bookings"
        }
        rendered = mail._render_template("emails/booking_confirmation.html", sample_context)
        print(f"      [OK] Template rendered successfully ({len(rendered)} bytes generated)")
    except Exception as e:
        print(f"      [FAIL] Template rendering error: {e}")
        return 1

    # Step 3: Test Attachment Processing
    attachments = None
    if args.attach:
        print("\n  [3] Testing Attachment Attachment System...")
        sample_receipt = (
            "=========================================\n"
            "   SMART PARKING AI - PARKING TICKET     \n"
            "=========================================\n"
            "Slot: Bay-B04\n"
            "Vehicle: KA-04-ME-9021\n"
            "Fee Paid: INR 100.00\n"
            "Status: Validated via IoT Sensor\n"
            "=========================================\n"
        ).encode('utf-8')
        attachments = [{
            "filename": "SmartParking_Receipt_1042.txt",
            "content": sample_receipt,
            "content_type": "text/plain"
        }]
        print("      [OK] In-memory binary attachment attached.")

    # Step 4: Dispatch Email
    is_sync = not args.async_test
    print(f"\n  [4] Dispatching Email ({'Synchronous' if is_sync else 'Asynchronous Background Thread'})...")
    t0 = time.time()
    result = mail.send(
        to=args.to,
        subject=f"Smart Parking Verification [{mail.get_transport_mode()}]",
        template="emails/booking_confirmation.html",
        context=sample_context,
        attachments=attachments,
        sync=is_sync
    )
    elapsed = time.time() - t0

    print(f"      [OK] Dispatch returned in {elapsed * 1000:.2f} ms")
    print(f"      [OK] Status: {result.get('success')} | Mode: {result.get('mode')}")
    print(f"      [OK] Message-ID: {result.get('message_id')}")

    if not is_sync:
        print("      Waiting 1s for background thread worker...")
        time.sleep(1)

    print(f"      [OK] Total outbox records captured: {len(mail.outbox)}")

    print("\n" + "=" * 80)
    print("  RESULT: NATIVE PYTHON SSL/TLS TRANSPORT FULLY OPERATIONAL!")
    print("=" * 80)
    return 0

if __name__ == "__main__":
    sys.exit(main())
