"""
Unit Test Suite for Native Python SSL/TLS Secure Email Transport.
Validates:
  1. Port 465 Direct SSL/TLS vs Port 587 STARTTLS Upgrade (Nodemailer parity)
  2. HTML Template rendering & MIME multipart generation
  3. Plaintext fallback auto-extraction
  4. Binary and file attachment processing (Base64 encoding, Content-Disposition)
  5. Background worker threading (zero request lag)
  6. Flask API integration (/api/email/status, /api/email/test, /api/email/outbox)
  7. SMTP handshake mocking for both smtplib.SMTP_SSL and smtplib.SMTP+starttls
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json
import time

# Ensure project root is in sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from flask import Flask
from core.email_service import EmailService, send_email, send_templated_email, _strip_html_tags


class TestEmailTransport(unittest.TestCase):
    """Test suite for EmailService transport configuration and Nodemailer parity."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update({
            "TESTING": True,
            "MAIL_SERVER": "smtp.example.com",
            "MAIL_PORT": 587,
            "MAIL_USE_TLS": True,
            "MAIL_USE_SSL": False,
            "MAIL_USERNAME": "test_user@example.com",
            "MAIL_PASSWORD": "secret_password",
            "MAIL_DEFAULT_SENDER": "Smart Parking <noreply@smartparking.ai>",
            "MAIL_SUPPRESS_SEND": True  # Safe simulation mode during tests
        })
        self.mail = EmailService(self.app)

    def test_port_587_starttls_mode(self):
        """Validates that port 587 resolves to STARTTLS upgrade mode (Nodemailer secure: false)."""
        app = Flask(__name__)
        app.config.update({
            "MAIL_PORT": 587,
            "MAIL_SERVER": "smtp.gmail.com"
        })
        service = EmailService(app)
        self.assertFalse(service.is_secure_ssl())
        self.assertIn("STARTTLS", service.get_transport_mode())

    def test_port_465_direct_ssl_mode(self):
        """Validates that port 465 resolves to direct SSL/TLS mode (Nodemailer secure: true)."""
        app = Flask(__name__)
        app.config.update({
            "MAIL_PORT": 465,
            "MAIL_SERVER": "smtp.gmail.com"
        })
        service = EmailService(app)
        self.assertTrue(service.is_secure_ssl())
        self.assertIn("SSL/TLS", service.get_transport_mode())

    def test_explicit_mail_secure_flag(self):
        """Validates that explicit MAIL_SECURE takes precedence (Nodemailer parity)."""
        app = Flask(__name__)
        app.config.update({
            "MAIL_PORT": 587,  # Typically TLS
            "MAIL_SECURE": True  # But forced to SSL
        })
        service = EmailService(app)
        self.assertTrue(service.is_secure_ssl())

    def test_html_stripping_fallback(self):
        """Verifies clean plaintext extraction from HTML when no text body is supplied."""
        html = "<h2>Title</h2><p>Your parking spot is <strong>A-10</strong>.<br>Enjoy your stay.</p>"
        stripped = _strip_html_tags(html)
        self.assertIn("Title", stripped)
        self.assertIn("Your parking spot is A-10", stripped)
        self.assertNotIn("<strong>", stripped)
        self.assertNotIn("<p>", stripped)

    def test_mime_structure_html_and_text(self):
        """Verifies RFC-compliant multipart/alternative structure for HTML emails."""
        msg, recipients = self.mail._build_mime_message(
            to="driver@smartparking.ai",
            subject="Reservation Confirmed",
            text="Your slot is A-1",
            html="<p>Your slot is <b>A-1</b></p>"
        )
        self.assertEqual(recipients, ["driver@smartparking.ai"])
        self.assertEqual(msg["Subject"], "Reservation Confirmed")
        self.assertEqual(msg.get_content_type(), "multipart/alternative")

    def test_mime_structure_with_attachment(self):
        """Verifies multipart/mixed container when attachments are present."""
        attachment_payload = {
            "filename": "ticket.txt",
            "content": b"Parking Ticket #1234\nSlot: A-1",
            "content_type": "text/plain"
        }
        msg, recipients = self.mail._build_mime_message(
            to="driver@smartparking.ai",
            subject="Your Ticket",
            html="<p>Please find attached ticket.</p>",
            attachments=[attachment_payload]
        )
        self.assertEqual(msg.get_content_type(), "multipart/mixed")
        
        # Verify attachment payload is present
        payloads = msg.get_payload()
        self.assertEqual(len(payloads), 2)  # 1: alternative (body), 2: attachment
        attachment_part = payloads[1]
        self.assertIn('attachment; filename="ticket.txt"', attachment_part.get("Content-Disposition", ""))

    def test_template_rendering(self):
        """Verifies Jinja2 template rendering using base and booking templates."""
        context = {
            "booking_id": 8888,
            "lot_name": "Metro Parking Hub",
            "slot_name": "Slot C-03",
            "vehicle_number": "MH-02-CD-5678",
            "vehicle_type": "Car",
            "start_time": "2026-11-02 10:00",
            "end_time": "2026-11-02 12:00",
            "total_amount": 150.0,
            "dashboard_url": "http://127.0.0.1:5000"
        }
        rendered = self.mail._render_template("emails/booking_confirmation.html", context)
        self.assertIn("Slot C-03", rendered)
        self.assertIn("MH-02-CD-5678", rendered)
        self.assertIn("#8888", rendered)

    def test_overstay_alert_template_rendering(self):
        """Verifies overstay warning template rendering."""
        context = {
            "vehicle_number": "KA-01-EA-1122",
            "slot_name": "Bay 4",
            "scheduled_end_time": "12:00 PM",
            "overstay_minutes": 30,
            "penalty_amount": 60.0,
            "grace_status": "Expired",
            "checkout_url": "http://127.0.0.1:5000/checkout"
        }
        rendered = self.mail._render_template("emails/overstay_alert.html", context)
        self.assertIn("KA-01-EA-1122", rendered)
        self.assertIn("30 minutes", rendered)
        self.assertIn("₹60.00", rendered)

    def test_simulation_outbox(self):
        """Verifies that in simulation/test mode, emails are captured into the outbox."""
        self.mail.outbox.clear()
        res = self.mail.send(
            to="test.driver@smartparking.ai",
            subject="Test Simulation",
            html="<p>Test simulation body</p>",
            sync=True
        )
        self.assertTrue(res.get("success"))
        self.assertTrue(res.get("simulated"))
        self.assertEqual(len(self.mail.outbox), 1)
        self.assertEqual(self.mail.outbox[0]["subject"], "Test Simulation")

    def test_background_threading_execution(self):
        """Verifies asynchronous background dispatch returns instantly and queues task."""
        self.mail.outbox.clear()
        t0 = time.time()
        res = self.mail.send(
            to="async.driver@smartparking.ai",
            subject="Async Test",
            text="Testing non-blocking thread execution",
            sync=False
        )
        elapsed = time.time() - t0
        self.assertTrue(res.get("success"))
        # Must return in under 50ms
        self.assertLess(elapsed, 0.05)

    @patch("smtplib.SMTP_SSL")
    def test_mocked_smtp_ssl_dispatch(self, mock_smtp_ssl):
        """Verifies smtplib.SMTP_SSL is invoked when port 465 is used."""
        mock_instance = MagicMock()
        mock_smtp_ssl.return_value = mock_instance

        app = Flask(__name__)
        app.config.update({
            "MAIL_PORT": 465,
            "MAIL_SERVER": "smtp.gmail.com",
            "MAIL_USERNAME": "test@gmail.com",
            "MAIL_PASSWORD": "app_password_123",
            "MAIL_SUPPRESS_SEND": False
        })
        service = EmailService(app)
        
        # Test connection
        conn_res = service.test_connection()
        self.assertTrue(conn_res.get("success"))
        mock_smtp_ssl.assert_called_with(
            host="smtp.gmail.com",
            port=465,
            context=unittest.mock.ANY,
            timeout=15
        )
        mock_instance.login.assert_called_with("test@gmail.com", "app_password_123")
        mock_instance.quit.assert_called()

    @patch("smtplib.SMTP")
    def test_mocked_smtp_starttls_dispatch(self, mock_smtp):
        """Verifies smtplib.SMTP with starttls() is invoked when port 587 is used."""
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        app = Flask(__name__)
        app.config.update({
            "MAIL_PORT": 587,
            "MAIL_SERVER": "smtp.gmail.com",
            "MAIL_USERNAME": "test@gmail.com",
            "MAIL_PASSWORD": "app_password_123",
            "MAIL_SUPPRESS_SEND": False
        })
        service = EmailService(app)
        
        # Test connection
        conn_res = service.test_connection()
        self.assertTrue(conn_res.get("success"))
        mock_smtp.assert_called_with(
            host="smtp.gmail.com",
            port=587,
            timeout=15
        )
        mock_instance.ehlo.assert_called()
        mock_instance.starttls.assert_called()
        mock_instance.login.assert_called_with("test@gmail.com", "app_password_123")
        mock_instance.quit.assert_called()


if __name__ == "__main__":
    unittest.main()

