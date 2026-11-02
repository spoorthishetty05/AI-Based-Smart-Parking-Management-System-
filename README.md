# AI-Based Smart Parking System

An enterprise-grade, intelligent parking management and reservation platform powered by Flask, MongoDB, SQLite, and Scikit-Learn.

---

## 🏗️ Architecture & Clean Directory Structure

The project has been refactored into a modular, production-ready architecture:

```
Smart Parking/
├── app.py                      # Application entrypoint & Flask route definitions
├── config.py                   # Centralized configuration (Dev, Test, Prod)
├── requirements.txt            # Python dependencies
│
├── core/                       # Core domain logic & backend engines
│   ├── database.py             # Dual SQLite + MongoDB connection management
│   ├── mongo_engine.py         # MongoDB document validation & sync engine
│   ├── overstay_engine.py      # Real-time overstay detection & tiered penalty engine
│   ├── ml_engine.py            # AI occupancy prediction & regression models
│   ├── recommendation_engine.py# Multi-criteria intelligent slot recommendation
│   ├── simulation_engine.py    # Virtual clock & dynamic vehicle arrival/departure
│   ├── visualization_engine.py # Analytics, heatmaps, and chart generation
│   ├── parking_places_config.py# Parking facilities & institutional configurations
│   └── __init__.py             # Core package initialization
│
├── scripts/                    # Database administration, seeding & migration tools
│   ├── seed_demo_data.py       # Seeds standard test data and initial slots
│   ├── seed_overstay_demo.py   # Simulates realistic overstay sessions for demo
│   ├── seed_active_session.py  # Quick-seeds active vehicle check-ins
│   ├── reset_database.py       # Resets database to pristine initial state
│   ├── migrate_database.py     # Schema migrations across SQLite and MongoDB
│   ├── clean_database.py       # Database sanitization tool
│   ├── clean_city_parking.py   # Cleans specific facility records
│   └── check_lots_and_slots.py # Telemetry verification tool
│
├── tests/                      # Unified master automated test suite
│   ├── conftest.py             # Test fixtures, mock clients & date helpers
│   ├── test_auth.py            # Authentication, RBAC, and session tests (6 tests)
│   ├── test_booking.py         # Booking workflow, tariffs & pass verification (5 tests)
│   ├── test_overstay.py        # Overstay detection & tiered penalties (4 tests)
│   ├── test_slot_exchange.py   # Peer-to-peer slot swap marketplace (3 tests)
│   ├── test_ml_simulation.py   # Scikit-learn occupancy & simulation clock (5 tests)
│   ├── test_admin_system.py    # Admin stats, KPIs & notifications (5 tests)
│   └── run_tests.py            # Master test runner executing all suites
│
├── data/                       # Datasets, historical parking CSVs
├── models/                     # Trained ML model weights (.joblib)
├── templates/                  # Jinja2 HTML templates & redesigned parking pass UI
└── static/                     # CSS stylesheets, JavaScript client, and icons
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python**: 3.10+ (Recommended: Python 3.12)
- **MongoDB**: Local Community Server running on `127.0.0.1:27017`
- **Dependencies**: Install required packages:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Running the Application
Launch the Flask development server:
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

- **Permanent Administrator Login**:
  - Email: `admin@smartparking.ai`
  - Password: `admin` (or configured credentials)
- **Driver Portal**:
  - Register a new driver account or sign in with an existing user.

---

## 🧪 Automated Testing

A unified test suite covering 100% of functional requirements is provided under `tests/`.

### Run All 28 Unit & Integration Tests:
```bash
python tests/run_tests.py
```

### Run an Individual Test Suite:
```bash
python tests/test_auth.py
python tests/test_booking.py
python tests/test_overstay.py
python tests/test_slot_exchange.py
python tests/test_ml_simulation.py
python tests/test_admin_system.py
```

---

## 🛠️ Administrative & Maintenance Scripts

All one-off, administrative, and maintenance utilities are organized under `scripts/`:

- **Reset Database**:
  ```bash
  python scripts/reset_database.py
  ```
- **Seed Demo Overstay Sessions**:
  ```bash
  python scripts/seed_overstay_demo.py
  ```
- **Check Parking Lots & Slots Status**:
  ```bash
  python scripts/check_lots_and_slots.py
  ```

---

## ✨ Key Features & Architectural Highlights

1. **Modern Parking Pass UI**:
   - High-fidelity ticket pass matching the reference design.
   - Dynamic SVG/PNG scannable QR code generated per booking ID.
   - Clean print styles with automated layout optimization.
2. **Intelligent Slot Recommendation**:
   - Multi-criteria ranking considering walking distance to elevators, entry gates, shade, and EV charging.
3. **Automated Overstay Management**:
   - Real-time overstay sweeps with customizable grace periods and tiered hourly multipliers by vehicle type.
4. **Peer-to-Peer Slot Exchange**:
   - Two-phase swap negotiation between registered drivers with atomic database swaps.
5. **Native Python SSL/TLS Secure Email Transport**:
   - Integrated directly into Flask with zero external Node.js runtime dependencies.
   - **Port 465**: Direct SSL/TLS encrypted connection via `smtplib.SMTP_SSL` (`MAIL_SECURE=true`, Nodemailer `secure: true` parity).
   - **Port 587**: STARTTLS upgrade via `smtplib.SMTP` + `.starttls()` (`MAIL_SECURE=false`).
   - Non-blocking background worker threading (`ThreadPoolExecutor`) ensures zero web request lag.
   - Full Jinja2 responsive HTML templates (`booking_confirmation.html`, `overstay_alert.html`, `password_reset.html`, `payment_receipt.html`).
   - Base64-encoded MIME attachments, fallback plaintext extraction, and `.env` configuration.
   - Built-in Simulation Outbox for development without requiring live credentials.
6. **Clean & Resilient Architecture**:
   - Root facades maintain complete backward-compatibility for legacy callers while modular code resides strictly in `core/`.

