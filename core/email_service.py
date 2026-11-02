"""
Native Python SSL/TLS Secure Email Transport Module for Flask.
Behaves identically to Nodemailer's secure transport:
  - Port 465 : Direct SSL/TLS encrypted connection via smtplib.SMTP_SSL
  - Port 587 : STARTTLS upgrade via smtplib.SMTP + starttls()
Supports HTML email templates, attachments, background threading (zero request lag),
and environment-based (.env) configuration.
"""

import os
import sys
import ssl
import smtplib
import mimetypes
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email.utils import formatdate, make_msgid, formataddr, parseaddr
from email import encoders
from pathlib import Path
from typing import Optional, List, Union, Dict, Any, Tuple

# Try to import Flask utilities; handle standalone execution gracefully
try:
    from flask import current_app, render_template, has_app_context
except ImportError:
    current_app = None
    render_template = None
    has_app_context = lambda: False

# Configure logging
logger = logging.getLogger("SmartParking.EmailService")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)


def _strip_html_tags(html_content: str) -> str:
    """Simple plain-text converter for HTML email fallback."""
    import re
    # Replace line breaks and paragraphs with newlines
    text = re.sub(r'<(br|p|div|tr)[^>]*>', '\n', html_content, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '\n• ', text, flags=re.IGNORECASE)
    # Remove all other tags
    text = re.sub(r'<[^>]+>', '', text)
    # Collapse multiple whitespaces/newlines
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()


class EmailSendError(Exception):
    """Custom exception raised for email delivery failures."""
    pass


class EmailService:
    """
    Enterprise-ready Flask Email Service providing Native Python SSL/TLS transport.
    Mirrors Nodemailer's transport model:
      - secure: True  -> Direct SSL/TLS (port 465) via smtplib.SMTP_SSL
      - secure: False -> Plain connection upgraded via STARTTLS (port 587) via smtplib.SMTP
    """

    def __init__(self, app=None):
        self.app = app
        self.server: str = "smtp.gmail.com"
        self.port: int = 587
        self.secure: Optional[bool] = None  # None = auto-detect by port
        self.use_ssl: bool = False
        self.use_tls: bool = True
        self.username: str = ""
        self.password: str = ""
        self.default_sender: str = "Smart Parking AI <noreply@smartparking.ai>"
        self.reply_to: str = ""
        self.timeout: int = 15
        self.suppress_send: bool = False
        self.debug: bool = False
        self.max_workers: int = 4
        
        # Test & Simulation Outbox (stores sent messages when in testing/simulation mode)
        self.outbox: List[Dict[str, Any]] = []
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()

        if app is not None:
            self.init_app(app)
        else:
            self._load_from_environ()

    def _load_from_environ(self):
        """Loads configuration directly from os.environ when running standalone."""
        self.server = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
        self.port = int(os.environ.get("MAIL_PORT", 587))
        self.username = os.environ.get("MAIL_USERNAME", "").strip()
        self.password = os.environ.get("MAIL_PASSWORD", "").strip()
        self.default_sender = os.environ.get("MAIL_DEFAULT_SENDER", "Smart Parking AI <noreply@smartparking.ai>")
        self.reply_to = os.environ.get("MAIL_REPLY_TO", "").strip()
        self.timeout = int(os.environ.get("MAIL_TIMEOUT", 15))
        self.suppress_send = os.environ.get("MAIL_SUPPRESS_SEND", "false").lower() in ("true", "1")
        self.debug = os.environ.get("MAIL_DEBUG", "false").lower() in ("true", "1")
        self.max_workers = int(os.environ.get("MAIL_MAX_WORKERS", 4))

        explicit_secure = os.environ.get("MAIL_SECURE", None)
        if explicit_secure is not None:
            self.secure = explicit_secure.lower() in ("true", "1")
            self.use_ssl = self.secure
            self.use_tls = not self.secure
        else:
            self.use_ssl = (os.environ.get("MAIL_USE_SSL", "false").lower() in ("true", "1")) or (self.port == 465)
            self.use_tls = (os.environ.get("MAIL_USE_TLS", "true").lower() in ("true", "1")) if self.port != 465 else False
            self.secure = self.use_ssl

        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.max_workers,
                    thread_name_prefix="EmailWorker"
                )

    def init_app(self, app):
        """Initializes the email service with a Flask application."""
        self.app = app

        cfg = app.config
        self.server = cfg.get("MAIL_SERVER", os.environ.get("MAIL_SERVER", "smtp.gmail.com"))
        self.port = int(cfg.get("MAIL_PORT", os.environ.get("MAIL_PORT", 587)))
        self.username = cfg.get("MAIL_USERNAME", os.environ.get("MAIL_USERNAME", "")).strip()
        self.password = cfg.get("MAIL_PASSWORD", os.environ.get("MAIL_PASSWORD", "")).strip()
        self.default_sender = cfg.get("MAIL_DEFAULT_SENDER", os.environ.get("MAIL_DEFAULT_SENDER", "Smart Parking AI <noreply@smartparking.ai>"))
        self.reply_to = cfg.get("MAIL_REPLY_TO", os.environ.get("MAIL_REPLY_TO", "")).strip()
        self.timeout = int(cfg.get("MAIL_TIMEOUT", os.environ.get("MAIL_TIMEOUT", 15)))
        self.suppress_send = bool(cfg.get("MAIL_SUPPRESS_SEND", False))
        self.debug = bool(cfg.get("MAIL_DEBUG", False))
        self.max_workers = int(cfg.get("MAIL_MAX_WORKERS", 4))

        # Nodemailer secure parity resolution:
        # If MAIL_SECURE is set in config, it takes precedence.
        # Otherwise: port 465 -> secure: True (SSL/TLS), port 587 -> secure: False (STARTTLS)
        explicit_secure = cfg.get("MAIL_SECURE", None)
        if explicit_secure is not None:
            self.secure = bool(explicit_secure)
            self.use_ssl = self.secure
            self.use_tls = not self.secure
        else:
            self.use_ssl = bool(cfg.get("MAIL_USE_SSL", False)) or (self.port == 465)
            self.use_tls = bool(cfg.get("MAIL_USE_TLS", True)) if self.port != 465 else False
            self.secure = self.use_ssl

        # Attach extension to Flask app
        if not hasattr(app, "extensions"):
            app.extensions = {}
        app.extensions["mail"] = self

        # Initialize thread pool executor
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.max_workers,
                    thread_name_prefix="EmailWorker"
                )

        logger.info(
            f"EmailService initialized [Host: {self.server}:{self.port} | "
            f"Mode: {'SSL/TLS (Port 465 direct)' if self.is_secure_ssl() else 'STARTTLS (Port 587 upgrade)'} | "
            f"Auth: {'Configured' if self.username else 'Simulation/Unauthenticated'} | "
            f"Suppress: {self.suppress_send}]"
        )

    @property
    def executor(self) -> ThreadPoolExecutor:
        """Lazy-loaded thread pool executor for background tasks."""
        if self._executor is None:
            with self._lock:
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(
                        max_workers=self.max_workers,
                        thread_name_prefix="EmailWorker"
                    )
        return self._executor

    def is_secure_ssl(self) -> bool:
        """
        Determines if the transport uses direct SSL/TLS (Nodemailer secure: true, Port 465)
        versus STARTTLS upgrade (Nodemailer secure: false, Port 587).
        """
        if self.secure is not None:
            return self.secure
        if self.port == 465 or self.use_ssl:
            return True
        return False

    def get_transport_mode(self) -> str:
        """Returns readable transport descriptor for logging/debugging."""
        return "SSL/TLS (Direct smtplib.SMTP_SSL, port 465)" if self.is_secure_ssl() else "STARTTLS (Upgrade smtplib.SMTP + starttls, port 587)"

    def _create_smtp_connection(self):
        """
        Instantiates and returns an authenticated secure SMTP connection.
        Handles direct SSL/TLS (port 465) or STARTTLS upgrade (port 587).
        """
        # Modern secure SSL Context with TLS 1.2+ minimum
        ssl_context = ssl.create_default_context()

        if self.is_secure_ssl():
            # Option 1A: Direct SSL/TLS (Nodemailer secure: true / port 465)
            logger.debug(f"Connecting via direct SSL/TLS to {self.server}:{self.port}...")
            server = smtplib.SMTP_SSL(
                host=self.server,
                port=self.port,
                context=ssl_context,
                timeout=self.timeout
            )
        else:
            # Option 1B: STARTTLS Upgrade (Nodemailer secure: false / port 587)
            logger.debug(f"Connecting via STARTTLS upgrade to {self.server}:{self.port}...")
            server = smtplib.SMTP(
                host=self.server,
                port=self.port,
                timeout=self.timeout
            )
            server.ehlo()
            server.starttls(context=ssl_context)
            server.ehlo()

        if self.username and self.password:
            logger.debug(f"Authenticating SMTP user: {self.username}")
            server.login(self.username, self.password)

        return server

    def test_connection(self) -> Dict[str, Any]:
        """
        Validates SMTP server reachability, SSL/TLS handshake, and credentials.
        Returns a dictionary with status and diagnostic info.
        """
        if not self.username and not self.suppress_send:
            return {
                "success": False,
                "mode": self.get_transport_mode(),
                "error": "MAIL_USERNAME / MAIL_PASSWORD not configured. Running in simulation mode."
            }

        try:
            server = self._create_smtp_connection()
            server.quit()
            return {
                "success": True,
                "mode": self.get_transport_mode(),
                "server": self.server,
                "port": self.port,
                "message": f"Successfully connected and authenticated using {self.get_transport_mode()}."
            }
        except smtplib.SMTPAuthenticationError as e:
            msg = f"SMTP Authentication failed (code {e.smtp_code}): {e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else e.smtp_error}."
            if "gmail" in self.server.lower():
                msg += " For Gmail, please generate an App Password from your Google Account Security settings."
            logger.error(msg)
            return {"success": False, "mode": self.get_transport_mode(), "error": msg}
        except Exception as e:
            msg = f"SMTP connection error: {str(e)}"
            logger.error(msg)
            return {"success": False, "mode": self.get_transport_mode(), "error": msg}

    def _build_mime_message(
        self,
        to: Union[str, List[str]],
        subject: str,
        text: Optional[str] = None,
        html: Optional[str] = None,
        sender: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Tuple[MIMEMultipart, List[str]]:
        """
        Constructs a complete RFC-compliant MIME message with multipart/alternative
        and multipart/mixed support for HTML and attachments.
        """
        # Determine sender
        from_address = sender or self.default_sender

        # Normalize recipients to list
        if isinstance(to, str):
            to_list = [addr.strip() for addr in to.split(",") if addr.strip()]
        else:
            to_list = [str(addr).strip() for addr in to if str(addr).strip()]

        cc_list = []
        if cc:
            if isinstance(cc, str):
                cc_list = [addr.strip() for addr in cc.split(",") if addr.strip()]
            else:
                cc_list = [str(addr).strip() for addr in cc if str(addr).strip()]

        bcc_list = []
        if bcc:
            if isinstance(bcc, str):
                bcc_list = [addr.strip() for addr in bcc.split(",") if addr.strip()]
            else:
                bcc_list = [str(addr).strip() for addr in bcc if str(addr).strip()]

        all_recipients = to_list + cc_list + bcc_list
        if not all_recipients:
            raise ValueError("At least one recipient ('to') is required.")

        # Fallback text if only HTML provided
        if not text and html:
            text = _strip_html_tags(html)
        if not text:
            text = ""

        # Root message container: multipart/mixed if attachments exist, else multipart/alternative
        has_attachments = bool(attachments)
        if has_attachments:
            msg_root = MIMEMultipart("mixed")
            msg_body = MIMEMultipart("alternative")
            msg_root.attach(msg_body)
        else:
            msg_root = MIMEMultipart("alternative")
            msg_body = msg_root

        # Attach text and html alternatives
        part_text = MIMEText(text, "plain", "utf-8")
        msg_body.attach(part_text)

        if html:
            part_html = MIMEText(html, "html", "utf-8")
            msg_body.attach(part_html)

        # Standard Email Headers
        msg_root["Subject"] = subject
        msg_root["From"] = from_address
        msg_root["To"] = ", ".join(to_list)
        if cc_list:
            msg_root["Cc"] = ", ".join(cc_list)
        
        rt = reply_to or self.reply_to
        if rt:
            msg_root["Reply-To"] = rt

        msg_root["Date"] = formatdate(localtime=True)
        msg_root["Message-ID"] = make_msgid(domain="smartparking.ai")
        msg_root["X-Mailer"] = "SmartParking AI Secure Mailer (Python Native SSL/TLS)"

        # Custom headers
        if headers:
            for k, v in headers.items():
                msg_root[k] = v

        # Process Attachments
        if attachments:
            for att in attachments:
                part = self._process_attachment(att)
                if part:
                    msg_root.attach(part)

        return msg_root, all_recipients

    def _process_attachment(self, attachment: Any) -> Optional[MIMEBase]:
        """
        Converts file paths, bytes, or dictionary specifications into MIMEBase attachment parts.
        Supported formats:
          - Path or string filepath: "/path/to/receipt.pdf"
          - Dict: {"filename": "receipt.pdf", "content": b"...", "content_type": "application/pdf"}
          - Tuple: (filename, content_bytes, content_type)
        """
        filename = "attachment.dat"
        content_bytes = b""
        content_type = None

        if isinstance(attachment, (str, Path)):
            file_path = Path(attachment)
            if not file_path.exists() or not file_path.is_file():
                logger.warning(f"Attachment file not found: {file_path}")
                return None
            filename = file_path.name
            content_type, _ = mimetypes.guess_type(str(file_path))
            try:
                with open(file_path, "rb") as f:
                    content_bytes = f.read()
            except Exception as e:
                logger.error(f"Failed to read attachment {file_path}: {e}")
                return None

        elif isinstance(attachment, dict):
            filename = attachment.get("filename", "attachment.dat")
            content_type = attachment.get("content_type")
            raw = attachment.get("content")
            if hasattr(raw, "read"):
                content_bytes = raw.read()
            elif isinstance(raw, str):
                content_bytes = raw.encode("utf-8")
            elif isinstance(raw, (bytes, bytearray)):
                content_bytes = bytes(raw)
            else:
                # If filepath given inside dict
                if "path" in attachment:
                    p = Path(attachment["path"])
                    if p.exists():
                        filename = p.name
                        content_type, _ = mimetypes.guess_type(str(p))
                        content_bytes = p.read_bytes()

        elif isinstance(attachment, (tuple, list)):
            filename = str(attachment[0])
            raw = attachment[1]
            if len(attachment) > 2:
                content_type = str(attachment[2])
            if hasattr(raw, "read"):
                content_bytes = raw.read()
            elif isinstance(raw, str):
                content_bytes = raw.encode("utf-8")
            elif isinstance(raw, (bytes, bytearray)):
                content_bytes = bytes(raw)

        if not content_bytes:
            return None

        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

        main_type, sub_type = content_type.split("/", 1) if "/" in content_type else ("application", "octet-stream")

        part = MIMEBase(main_type, sub_type)
        part.set_payload(content_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        part.add_header("Content-Type", f'{content_type}; name="{filename}"')
        return part

    def send(
        self,
        to: Union[str, List[str]],
        subject: str,
        text: Optional[str] = None,
        html: Optional[str] = None,
        template: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        sender: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        sync: bool = False
    ) -> Dict[str, Any]:
        """
        Sends an email message either synchronously or asynchronously via background thread.

        Parameters:
          to: Recipient email address or list of addresses.
          subject: Email subject line.
          text: Plain text body.
          html: Rich HTML body.
          template: Jinja2 template filename (e.g. 'emails/booking_confirmation.html').
          context: Variables to pass into the template.
          sender: Sender address (defaults to MAIL_DEFAULT_SENDER).
          cc: CC recipient(s).
          bcc: BCC recipient(s).
          reply_to: Reply-To address.
          attachments: List of file paths, dicts, or tuples to attach.
          headers: Custom headers dict.
          sync: If True, blocks until sent; if False (default), executes in background thread.

        Returns:
          Dictionary with status details ('success': True/False, 'mode', 'message_id').
        """
        # Render template if specified
        rendered_html = html
        if template:
            ctx = context or {}
            rendered_html = self._render_template(template, ctx)

        # Build MIME message
        mime_msg, recipients = self._build_mime_message(
            to=to,
            subject=subject,
            text=text,
            html=rendered_html,
            sender=sender,
            cc=cc,
            bcc=bcc,
            reply_to=reply_to,
            attachments=attachments,
            headers=headers
        )

        message_id = mime_msg["Message-ID"]

        # Check simulation mode: if credentials are missing or send is suppressed, log and record to outbox
        is_simulation = self.suppress_send or not (self.username and self.password)

        if is_simulation:
            record = {
                "message_id": message_id,
                "to": recipients,
                "from": mime_msg["From"],
                "subject": subject,
                "text": text or _strip_html_tags(rendered_html or ""),
                "html": rendered_html,
                "has_attachments": bool(attachments),
                "attachments_count": len(attachments) if attachments else 0,
                "mode": "Simulation (Outbox)",
                "timestamp": formatdate(localtime=True)
            }
            self.outbox.append(record)
            logger.info(
                f"[EMAIL SIMULATION] Sent to: {recipients} | Subject: '{subject}' | "
                f"Mode: {self.get_transport_mode()} (No live credentials/Suppressed)"
            )
            return {
                "success": True,
                "simulated": True,
                "message_id": message_id,
                "mode": self.get_transport_mode(),
                "recipients": recipients,
                "subject": subject
            }

        # Synchronous execution
        if sync:
            return self._send_raw(mime_msg, recipients)

        # Asynchronous background execution (Zero web request lag)
        # Capture current Flask app context to pass into background worker
        flask_app = None
        if has_app_context() and current_app:
            try:
                flask_app = current_app._get_current_object()
            except Exception:
                flask_app = self.app
        else:
            flask_app = self.app

        self.executor.submit(self._dispatch_background, flask_app, mime_msg, recipients)
        logger.debug(f"[Background Email Dispatched] Message-ID: {message_id} -> {recipients}")
        return {
            "success": True,
            "queued": True,
            "message_id": message_id,
            "mode": self.get_transport_mode(),
            "recipients": recipients,
            "subject": subject
        }

    def _dispatch_background(self, flask_app, mime_msg: MIMEMultipart, recipients: List[str]):
        """Worker function executed inside the background ThreadPool."""
        if flask_app:
            with flask_app.app_context():
                try:
                    self._send_raw(mime_msg, recipients)
                except Exception as e:
                    logger.error(f"[Background Email Error] Failed to send to {recipients}: {e}", exc_info=True)
        else:
            try:
                self._send_raw(mime_msg, recipients)
            except Exception as e:
                logger.error(f"[Background Email Error] Failed to send to {recipients}: {e}", exc_info=True)

    def _send_raw(self, mime_msg: MIMEMultipart, recipients: List[str]) -> Dict[str, Any]:
        """Low-level SMTP dispatch method executing actual socket connection."""
        server = None
        try:
            server = self._create_smtp_connection()
            from_address = parseaddr(mime_msg["From"])[1] or mime_msg["From"]
            server.sendmail(from_address, recipients, mime_msg.as_string())
            logger.info(
                f"Email successfully delivered to {recipients} | "
                f"Subject: '{mime_msg['Subject']}' | Mode: {self.get_transport_mode()}"
            )
            return {
                "success": True,
                "message_id": mime_msg["Message-ID"],
                "mode": self.get_transport_mode(),
                "recipients": recipients
            }
        except smtplib.SMTPAuthenticationError as e:
            err = f"SMTP Authentication Error ({e.smtp_code}): {e.smtp_error}"
            logger.error(err)
            raise EmailSendError(err) from e
        except smtplib.SMTPException as e:
            err = f"SMTP Protocol Error: {str(e)}"
            logger.error(err)
            raise EmailSendError(err) from e
        except Exception as e:
            err = f"Failed to send email: {str(e)}"
            logger.error(err)
            raise EmailSendError(err) from e
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Renders Jinja2 HTML email template within Flask or standalone environment."""
        # 1. Use Flask render_template if available inside request/app context
        if has_app_context() and render_template:
            try:
                return render_template(template_name, **context)
            except Exception as e:
                logger.warning(f"Flask render_template failed for {template_name}: {e}. Trying fallback loader.")

        # 2. Standalone Jinja2 Environment fallback
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
            # Search in templates/ directory
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            templates_dir = os.path.join(base_dir, "templates")
            env = Environment(
                loader=FileSystemLoader(templates_dir),
                autoescape=select_autoescape(["html", "xml"])
            )
            tmpl = env.get_template(template_name)
            return tmpl.render(**context)
        except Exception as e:
            logger.error(f"Error rendering email template '{template_name}': {e}")
            raise


# Singleton instance for import across application
mail_service = EmailService()


def send_email(
    to: Union[str, List[str]],
    subject: str,
    text: Optional[str] = None,
    html: Optional[str] = None,
    template: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Any]] = None,
    sync: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience function for sending emails using the configured singleton EmailService.
    Supports native Python SSL (Port 465) / STARTTLS (Port 587) with background threading.
    """
    return mail_service.send(
        to=to,
        subject=subject,
        text=text,
        html=html,
        template=template,
        context=context,
        attachments=attachments,
        sync=sync,
        **kwargs
    )


def send_templated_email(
    to: Union[str, List[str]],
    subject: str,
    template: str,
    context: Dict[str, Any],
    attachments: Optional[List[Any]] = None,
    sync: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """Convenience function specifically for Jinja2 HTML templated emails."""
    return mail_service.send(
        to=to,
        subject=subject,
        template=template,
        context=context,
        attachments=attachments,
        sync=sync,
        **kwargs
    )

