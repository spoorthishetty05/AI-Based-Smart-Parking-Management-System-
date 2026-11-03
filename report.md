# AI-Based Smart Parking Management System — Project Error & Bug Report

**Document Version:** 1.0.0  
**Generated Date:** November 2, 2026  
**System Architecture:** Python 3.12, Flask, MongoDB (Local Community Server on port 27017), Scikit-Learn ML Engines, Native SSL/TLS SMTP Transport  
**Repository:** [AI-Based-Smart-Parking-Management-System-](https://github.com/spoorthishetty05/AI-Based-Smart-Parking-Management-System-)  

---

## Executive Summary

This report provides a detailed retrospective of all software defects, runtime errors, architectural discrepancies, and data inconsistencies identified, diagnosed, and resolved across the **AI-Based Smart Parking Management System**.

During the project lifecycle, multiple subsystems—including user authentication, 2D matrix rendering, overstay calculation algorithms, machine learning forecasting engines, reporting dashboards, and email delivery mechanisms—contained critical issues that impaired system operation. All identified defects have been systematically investigated, remediated, and verified with an automated 40-test master test suite achieving a 100% pass rate.

---

## Table of Contents

1. [Bug 1: AI Forecasting 24-Hour Flat 50% Line and Hardcoded Peak Overrides](#bug-1-ai-forecasting-24-hour-flat-50-line-and-hardcoded-peak-overrides)
2. [Bug 2: Interactive 2D Parking Matrix "No Parking Slots Found" Error](#bug-2-interactive-2d-parking-matrix-no-parking-slots-found-error)
3. [Bug 3: User Authentication & Registration 401 Unauthorized Failure](#bug-3-user-authentication--registration-401-unauthorized-failure)
4. [Bug 4: Premature Overstay Status Flagged Before Time Expiration](#bug-4-premature-overstay-status-flagged-before-time-expiration)
5. [Bug 5: Reports & Analytics Dashboard Failure (SQLite/MongoDB Mismatch)](#bug-5-reports--analytics-dashboard-failure-sqlitemongodb-mismatch)
6. [Bug 6: Legacy Email Architecture & Native SSL/TLS Re-implementation](#bug-6-legacy-email-architecture--native-ssltls-re-implementation)
7. [Bug 7: Disconnection Between In-App Notifications and Email Delivery](#bug-7-disconnection-between-in-app-notifications-and-email-delivery)
8. [Bug 8: Windows cp1252 Terminal UnicodeEncodeError on Logging](#bug-8-windows-cp1252-terminal-unicodeencodeerror-on-logging)
9. [Bug 9: Missing python-dotenv Dependency Silencing Environment Configuration](#bug-9-missing-python-dotenv-dependency-silencing-environment-configuration)
10. [Bug 10: Git Repository Synchronization & Unpushed Master Branch](#bug-10-git-repository-synchronization--unpushed-master-branch)
11. [Bug 11: Absence of Payment Gateway and Online Reservation / Penalty Clearance Integration](#bug-11-absence-of-payment-gateway-and-online-reservation--penalty-clearance-integration)
12. [Enterprise Architectural Refactoring: Flask Blueprints & SQLite Deprecation](#enterprise-architectural-refactoring-flask-blueprints--sqlite-deprecation)
13. [Bug 12: Transient DNS Network Outage and Resilient Email Fallback](#bug-12-transient-dns-network-outage-and-resilient-email-fallback)
14. [Master Test Suite Verification](#master-test-suite-verification)
15. [System Maintenance & Production Recommendations](#system-maintenance--production-recommendations)

---

## Defect Catalog & Resolution Details

### Bug 1: AI Forecasting 24-Hour Flat 50% Line and Hardcoded Peak Overrides

- **Component:** `core/ml_engine.py`, `app.py`, `static/js/admin_panel.js`, `templates/admin_panel.html`
- **Severity:** High
- **Symptom:**
  In the Admin Panel under the AI Intelligence tab (`#tab-ai`), the 24-Hour Future Occupancy Forecast chart displayed an unnatural, flat horizontal line at exactly 50% across all 24 hours, except for an artificial spike to 87% at 17:00. Top KPI cards displayed static values (68% Occupancy, 48 Available, 102/150 slots), simulator capacity was hardcoded to 150 slots, and floor recommendations showed 4 non-existent floors (`Ground`, `First`, `Second`, `Third`) with hardcoded availability.
- **Root Cause:**
  1. `core/ml_engine.py` returned predictions under the dictionary key `'predicted_occupancy'`, whereas `app.py` in `api_admin_ai_forecast()` queried `pred.get('predicted_occupancy_percentage', 50.0)`. Because the key was missing, every single hour defaulted to the fallback `50.0%`.
  2. In `static/js/admin_panel.js`, line 1104 contained a hardcoded override: `if (h === '17:00') return 87;`, and the Chart.js peak callout plugin was hardcoded to index `17:00`.
  3. `api_admin_ai_forecast()` in `app.py` returned hardcoded dictionary values (`current_occupancy: 68`, `total_slots: 150`, `available_slots: 48`, `predicted_peak_hour: '17:00 - 18:00'`) instead of aggregating live MongoDB counts.
  4. Date pickers in `admin_panel.html` were hardcoded to `18 Sep 2026`.
- **Resolution:**
  - Standardized `core/ml_engine.py` to return both `'predicted_occupancy'` and `'predicted_occupancy_percentage'`, querying total slot capacity dynamically from MongoDB `db.parking_slots`.
  - Refactored `api_admin_ai_forecast()` in `app.py` to count live occupied, reserved, and available slots (Total: 210 slots; 24 in-use; 186 available), calculate live current occupancy (11.4%), dynamically identify peak demand hour and occupancy from the model, and construct floor-wise availability from actual database floors (`Ground Floor` and `Upper Floor`).
  - Removed `if (h === '17:00') return 87;` from `admin_panel.js`. Rewrote `renderForecastChart()` so the peak callout badge dynamically locates the true maximum value across all predicted hours.
  - Dynamically bound the AI simulator to capacity (210 slots) and defaulted all date pickers to `todayStr`.

---

### Bug 2: Interactive 2D Parking Matrix "No Parking Slots Found" Error

- **Component:** `static/js/guided_booking_wizard.js`, `core/mongo_engine.py`, `app.py`
- **Severity:** High
- **Symptom:**
  During the 5-Step Guided Booking Wizard at Step 4 (Slot Selection), selecting the "University Campus" facility resulted in an error alert inside the interactive matrix container: *"No parking slots currently found for this location."* Users were blocked from selecting any parking slot or proceeding to checkout.
- **Root Cause:**
  A string mismatch existed between the frontend facility selector values and the MongoDB documents in `parking_slots`. The frontend submitted place labels such as `"University Campus"`, while the database stored facility categories as `"Institutions"`, `"Mall"`, `"Public places"`, and `"City Parking"`, or specific place IDs like `"inst_univ"`. Because the backend performed an exact match query without category normalization, 0 slots matched.
- **Resolution:**
  - Implemented category and facility alias mapping in `core/parking_places_config.py` and `core/mongo_engine.py`.
  - Updated slot query logic to match against both `facility_category`, `place_id`, and `place_name`.
  - Ensured all 210 slots across all 4 categories load reliably with real-time status indicators (Available, Occupied, Reserved, Overstayed).

---

### Bug 3: User Authentication & Registration 401 Unauthorized Failure

- **Component:** `app.py`, `core/database.py`, `core/mongo_engine.py`
- **Severity:** Critical
- **Symptom:**
  Newly registered driver accounts (e.g., username `test1`) were unable to log in immediately after registration. The application returned `HTTP 401 Unauthorized` with the error message: *"Invalid email or password"*.
- **Root Cause:**
  1. Password hashing algorithm divergence: Registration saved passwords using standard Werkzeug scrypt hashing, while certain authentication paths checked legacy sha256 or truncated strings.
  2. Case-sensitivity in email lookups: When users registered with capitalized emails (e.g. `Test1@smartparking.ai`) and logged in with lowercase (or vice versa), the MongoDB query `{'email': email}` failed to find the document.
  3. Session dictionary missing `user_role`: After registration, auto-login failed to set `session['user_role'] = 'user'`, causing subsequent role-based route guards to reject requests.
- **Resolution:**
  - Standardized password generation and verification across all authentication modules using Werkzeug's `generate_password_hash(..., method='scrypt')` and `check_password_hash()`.
  - Normalized all email inputs across registration, login, and profile updates using `.strip().lower()`.
  - Ensured complete session initialization on login: `user_id`, `user_name`, `user_email`, `user_role`, and vehicle metadata.

---

### Bug 4: Premature Overstay Status Flagged Before Time Expiration

- **Component:** `core/overstay_engine.py`, `app.py`
- **Severity:** High
- **Symptom:**
  In the Admin Overstay Management tab (`#tab-overstay`), active vehicle sessions were flagged with red "Overstayed" badges and penalty charges even when the driver's booked duration was still active and not yet completed.
- **Root Cause:**
  1. Timezone and datetime awareness mismatch: System compared naive local datetime strings with UTC ISO timestamps.
  2. Grace period omission: The overstay sweep evaluated `current_time > booked_end_time` instead of `current_time > grace_end_time` (where `grace_end_time = booked_end_time + 15 minutes`).
  3. Simulation clock offset accumulation: The global simulation offset was adding virtual hours to real-time queries without recalculating expiration thresholds.
- **Resolution:**
  - Standardized all time parsing across the engine using local system format `YYYY-MM-DD HH:MM:SS`.
  - Refactored `check_and_update_overstays()`:
    - Active period: `now <= booked_end_time` -> Status: `Within Booking Time` (Penalty: ₹0).
    - Grace period: `booked_end_time < now <= grace_end_time` -> Status: `Grace Period Active` (Penalty: ₹0).
    - Overstay violation: `now > grace_end_time` -> Status: `Penalty Applicable` (Hourly tiered penalty applied).
  - Verified with comprehensive test cases in `tests/test_overstay.py`.

---

### Bug 5: Reports & Analytics Dashboard Failure (SQLite/MongoDB Mismatch)

- **Component:** `app.py` (`/api/reports/summary`, `/api/reports/export-csv`), `static/js/admin_panel.js`, `templates/admin_panel.html`
- **Severity:** High
- **Symptom:**
  Navigating to the Reports & Analytics tab (`#tab-reports`) displayed static dummy numbers (1,248 Bookings, ₹82,450 Revenue, 37 Overstays). The CSV export crashed or returned empty data. Hardcoded static table rows (`KA19AB1234`, `B1-12`) were visible in the Recent Overstays and Recent Activity tables.
- **Root Cause:**
  - The legacy `/api/reports/summary` and `/api/reports/export-csv` functions executed SQLite queries via `conn = get_db_connection(); cursor.execute("SELECT * FROM reservations")`. Since all data was migrated to MongoDB, SQLite had no `reservations` table, throwing `sqlite3.OperationalError: no such table: reservations`.
  - The code suppressed the exception by falling back to hardcoded static metrics:
    ```python
    display_rev = total_rev if total_rev >= 80000 else 82450.0
    total_bookings = db_bookings if db_bookings >= 1200 else 1248
    ```
  - Floor occupancy was hardcoded to fictitious floors (`B1`, `G`, `1F`, `2F`, `3F`, `4F`).
  - Frontend Chart.js instances had fixed maximum axes (`max: 200` for bookings, `max: 80000` for revenue), flattening real trends to the baseline.
- **Resolution:**
  - Completely rewrote `/api/reports/summary` using pure MongoDB aggregations on `db.reservations`, `db.parking_slots`, `db.overstay_records`, and `db.activity_logs`.
  - Real metrics: live total bookings (26), real collected revenue (₹1,560.0), live campus occupancy (11.4%), active overstay records (1), and actual facility floors (`Ground Floor`: 25.8%, `Upper Floor`: 0.0%).
  - Rewrote `/api/reports/export-csv` to stream actual booking records directly from MongoDB into CSV.
  - Updated `static/js/admin_panel.js` to dynamically scale chart Y-axes to match real data and dynamically populate the `repOverstayRecordsTbody` and `repRecentActivityTbody` tables.

---

### Bug 6: Legacy Email Architecture & Native SSL/TLS Re-implementation

- **Component:** `core/email_service.py`, `config.py`, `app.py`
- **Severity:** Medium
- **Symptom:**
  The project previously contained fragmented, incomplete email sending routines that failed under SSL/TLS connections or blocked the main HTTP request thread for several seconds while attempting SMTP handshakes.
- **Root Cause:**
  Lack of a centralized email transport service supporting standard SSL/TLS and STARTTLS protocols, absence of non-blocking background threads, and hardcoded SMTP configurations.
- **Resolution:**
  - Implemented `core/email_service.py` providing complete Nodemailer parity in native Python:
    - **Port 465**: Direct SSL/TLS encrypted connection via `smtplib.SMTP_SSL` (`MAIL_SECURE=true`).
    - **Port 587**: STARTTLS protocol upgrade via `smtplib.SMTP` + `starttls()` (`MAIL_SECURE=false`).
  - Added non-blocking asynchronous dispatching using `concurrent.futures.ThreadPoolExecutor` (4 worker threads).
  - Designed responsive Jinja2 HTML email templates in `templates/emails/` (`booking_confirmation.html`, `overstay_alert.html`, `payment_receipt.html`, `general_notification.html`, `base_email.html`).
  - Tested live delivery against Google SMTP servers with 100% success.

---

### Bug 7: Disconnection Between In-App Notifications and Email Delivery

- **Component:** `core/database.py` (`create_notification()`), `core/overstay_engine.py`
- **Severity:** Medium
- **Symptom:**
  In-app notifications appeared in the web UI header bell icon, but registered users never received email alerts for critical events such as grace period warnings, overstay fines, or slot exchange updates.
- **Root Cause:**
  `create_notification()` in `core/database.py` solely inserted documents into `db.notifications` without calling the email transport layer.
- **Resolution:**
  - Refactored `create_notification(user_id, notif_type, title, message, ...)`:
    1. Persists notification in MongoDB `db.notifications`.
    2. Dynamically queries `db.users` for the registered email of `user_id`.
    3. Asynchronously dispatches a formatted email via `send_email(..., template="emails/general_notification.html")`.
  - Added duplicate prevention (`send_email_alert=False`) where specialized rich templates (e.g. detailed booking pass with QR code) are sent independently.

---

### Bug 8: Windows cp1252 Terminal UnicodeEncodeError on Logging

- **Component:** `core/email_service.py`
- **Severity:** Low (Platform-specific)
- **Symptom:**
  When background email threads logged status messages containing emojis (such as `🚨`, `🎉`, `🔄`, `⚠️`) to the Windows console, Python threw unhandled exceptions:
  ```
  UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f389' in position 177: character maps to <undefined>
  ```
- **Root Cause:**
  The default `logging.StreamHandler(sys.stdout)` uses the Windows active code page (`cp1252`), which cannot represent Unicode astral plane emojis.
- **Resolution:**
  - Created a custom `SafeStreamHandler(logging.StreamHandler)` inside `core/email_service.py` that intercepts `UnicodeEncodeError` and automatically encodes with fallback character replacement (`errors='replace'`).

---

### Bug 9: Missing python-dotenv Dependency Silencing Environment Configuration

- **Component:** `config.py`
- **Severity:** Medium
- **Symptom:**
  Variables declared in `.env` (such as `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_PORT`) were not populating `os.environ`. The application ran in unauthenticated simulation mode instead of connecting to real SMTP servers.
- **Root Cause:**
  `config.py` used `try: from dotenv import load_dotenv ... except ImportError: pass`. Because `python-dotenv` was not installed in the Python environment, the import failed silently without loading the `.env` file.
- **Resolution:**
  - Engineered a zero-dependency `.env` file parser (`_load_env_file()`) inside `config.py` that reads and populates `os.environ` natively using standard Python file I/O.
  - Ensures seamless environment loading on any system without requiring third-party package installations.

---

### Bug 10: Git Repository Synchronization & Unpushed Master Branch

- **Component:** Git VCS / Remote Configuration
- **Severity:** Medium
- **Symptom:**
  The GitHub repository at `https://github.com/spoorthishetty05/AI-Based-Smart-Parking-Management-System-` was completely empty, displaying GitHub's initial setup screen, despite work being committed locally.
- **Root Cause:**
  1. Commits were created on a detached or untracked local `main` branch.
  2. Local author was configured as `SpoorthiShetty` while the remote GitHub account handle was `spoorthishetty05`.
  3. `git push -u origin main` had never been executed.
- **Resolution:**
  - Configured repository-level author name to `spoorthishetty05` and email to `spoorthishetty86@gmail.com`.
  - Configured upstream remote tracking: `git branch -M main` and `git push -u origin main`.
  - Pushed all 86 project files and subsequent fix commits to GitHub.

---

### Bug 11: Absence of Payment Gateway and Online Reservation / Penalty Clearance Integration

- **Component:** `core/payment_service.py`, `app.py`, `static/css/razorpay_modal.css`, `static/js/razorpay_checkout.js`, `templates/booking_panel.html`, `static/js/guided_booking_wizard.js`, `templates/user_panel.html`, `static/js/user_panel.js`, `tests/test_payment.py`
- **Severity:** Medium / Core Capability Gap
- **Symptom:**
  Parking reservations and overstay penalties could only be recorded as unverified offline events. There was no interactive checkout modal allowing users to settle slot fees online or clear overstay penalty fines at exit. The existing Jinja2 payment receipt email template (`templates/emails/payment_receipt.html`) was completely unused and never dispatched upon booking or checkout.
- **Root Cause:**
  1. No payment service or gateway abstraction existed in `core/`.
  2. No cryptographic HMAC-SHA256 signature verification or order creation endpoints (`/api/payment/create-order`, `/api/payment/verify`) were registered in Flask.
  3. No frontend checkout modal matching Razorpay's UI (Cards, UPI/QR, Netbanking, Wallets) existed to handle customer payments.
  4. Step 5 Review & Confirm Booking submitted directly without capturing payment tokens or updating `payment_status: 'Paid'`.
  5. The vehicle exit modal provided no mechanism to clear overstay penalty fees before exit.
- **Resolution:**
  - **Core Payment Engine (`core/payment_service.py`):** Implemented `PaymentService` with authentic Razorpay Sandbox/Dummy order generation (`order_...`), rupee-to-paise conversion, HMAC-SHA256 cryptographic signature verification, sandbox test token verification, and automated transaction persistence in MongoDB `payment_transactions` and `payment_orders`.
  - **Razorpay Checkout UI (`static/css/razorpay_modal.css` & `static/js/razorpay_checkout.js`):** Built an authentic Razorpay checkout modal with dark navy header (`#0c2340`), "TEST MODE" badge, tabbed navigation (UPI/QR with simulated QR code and approval, Cards with 1-click test card auto-fill, Netbanking with top Indian banks, and Wallets), and emerald green "Pay ₹XX" CTA.
  - **Guided Booking Wizard & Quick Booking (`templates/booking_panel.html` & `static/js/guided_booking_wizard.js`):** Step 5 Review now provides interactive Payment Method selection (Pay with Razorpay vs Pay on Arrival). On confirming, Razorpay Checkout opens; upon authorization, booking payload includes `payment_id`, `payment_order_id`, and `payment_status: 'Paid'`, issuing a digital barrier pass with a "PAID ✓" badge.
  - **Exit Parking Overstay Penalty Settlement (`templates/user_panel.html` & `static/js/user_panel.js`):** Integrated "Pay Penalty via Razorpay" button in the checkout modal so drivers can settle accrued overstay penalty fines before vacating the slot.
  - **Automated Payment Receipts:** Connected successful payment capture to `core/email_service.py` to automatically dispatch itemized `payment_receipt.html` emails asynchronously via Native SSL/TLS.
  - **Automated Test Suite:** Created `tests/test_payment.py` (7 tests) covering order creation, signature validation, transaction logging, online booking confirmation, and penalty settlement.

---

### Bug 12: Incomplete Vehicle Identification in Booking Wizard Step 2 & Missing Persistence of Vehicle Name / Type Across Booking Lifecycle

- **Component:** `templates/user_panel.html`, `templates/booking_panel.html`, `static/js/guided_booking_wizard.js`, `app.py`, `core/mongo_engine.py`, `templates/emails/booking_confirmation.html`, `tests/test_booking.py`
- **Severity:** Medium / User Experience & Data Integrity
- **Symptom:**
  In Step 2 of the guided booking wizard ("Which vehicle are you using?"), vehicle cards displayed only license plate numbers and generic subtitles without explicit category badges or prominent vehicle model labels. Clicking the "Manual Plate" card lacked inputs to enter the Vehicle Name / Model. Furthermore, `state.vehicleName` was omitted from the wizard state and booking submission payload, resulting in booking records, confirmation emails, and digital passes lacking the specific vehicle model name.
- **Root Cause:**
  1. `userWizardSelectVehicle(el, plate, type)` did not capture or store the vehicle model name (`make_model` / `vehicle_name`).
  2. `#manualVehicleCard` referenced an undefined JavaScript function `userWizardSelectManualVehicle(this)`.
  3. `#wizardManualPlateBox` only contained inputs for License Plate and Category, omitting Vehicle Name / Model.
  4. Backend endpoints (`/booking/review`, `/booking/confirm`, `/booking/<id>/pass`) and `core/mongo_engine.py` (`mongo_create_booking`) did not persist or return `vehicle_name` and `make_model` in MongoDB `db.bookings` and `db.reservations`.
- **Resolution:**
  - **Enhanced Step 2 UI (`templates/user_panel.html` & `templates/booking_panel.html`):** Registered vehicle cards now prominently display the Vehicle Name / Model (e.g., Suzuki Swift, Tata Nexon), an explicit category badge (`Car`, `SUV`, `EV`, `Bike`), and the vehicle registration number. Also added a real-time selection indicator (`#wizardStep2SelectedPlate`) in the footer navigation.
  - **Comprehensive Manual Vehicle Entry:** Implemented `userWizardSelectManualVehicle(el)` and `userWizardOnManualPlateChange()` with responsive input fields for License Plate Number, Vehicle Name / Model, and Vehicle Category / Type.
  - **Wizard State Flow (`static/js/guided_booking_wizard.js`):** Extended `window.guidedBookingState` with `vehicleName`. Updated Step 5 Review (`#wizardRevVehicle`) to display `${plate} • ${name} (${type})`, and included `vehicle_name` and `make_model` in `basePayload` for wizard bookings and `quickPayload` for Quick Bookings.
  - **Backend & MongoDB Persistence (`app.py` & `core/mongo_engine.py`):** Updated `booking_confirm` and `mongo_create_booking` to atomically persist `vehicle_name` and `make_model` in both `db.bookings` and `db.reservations`, and return them in digital parking passes (`booking_get_pass`).
  - **Template & Email Updates (`templates/emails/booking_confirmation.html`):** Updated booking confirmation emails to present `{{ vehicle_number }} • {{ vehicle_name }} ({{ vehicle_type }})`.
  - **Automated Test Suite (`tests/test_booking.py`):** Extended `test_04_full_booking_lifecycle_and_pass_and_cancellation` to confirm `vehicle_name` and `vehicle_type` persistence in MongoDB documents and digital pass responses.

---

### Bug 13: Absence of Direct Online Penalty Clearance in Overstay Details Radar Table

- **Component:** `static/js/user_panel.js`, `static/css/user_panel.css`, `core/overstay_engine.py`, `core/payment_service.py`
- **Severity:** Medium / Revenue Clearance & User Experience
- **Symptom:**
  In the Overstay Details table (`tab-overstay`), active violations exceeding duration limits with applicable penalties (e.g. `₹60`) only displayed a "Notify" button in the Action column. Drivers and users viewing the overstay radar had no direct mechanism to settle the overdue penalty fee online, leaving penalties unpaid until exit.
- **Root Cause:**
  1. `renderOverstayTable` in `static/js/user_panel.js` solely rendered the notify action button without an online payment trigger for penalty fees.
  2. `get_overstay_dashboard_data` in `core/overstay_engine.py` did not check `penalty_payment_status` on reservations or overstay documents, continuing to report paid records as pending.
  3. `process_penalty_payment` in `core/payment_service.py` only queried by strict `booking_id` string rather than supporting polymorphic identifiers (`reservation_id`, `pass_code`, vehicle plate).
- **Resolution:**
  - **Direct Razorpay Penalty Action (`static/js/user_panel.js` & `static/css/user_panel.css`):** Added a prominent emerald green **"Pay ₹XX"** action button (`btn-ov-pay-penalty`) in the Overstay Details table for any vehicle with an unpaid penalty. When paid, the action updates to an emerald **"Cleared ✓"** badge and the penalty column displays **"₹XX (PAID ✓)"**.
  - **Modal Flow (`payOverstayDirectly`):** Clicking "Pay ₹XX" launches the Razorpay Sandbox Modal with UPI / QR, test cards, Netbanking, and Wallets. Upon completion, calls `/api/reservations/<id>/pay-penalty` and refreshes the radar table.
  - **Polymorphic Lookup & Persistence (`core/payment_service.py` & `core/overstay_engine.py`):** Updated `process_penalty_payment` to atomically resolve and mark `db.bookings`, `db.reservations`, and `db.overstay_records` as `Paid` and `resolved`, deducting from pending penalty totals.

---

### Bug 14: Inconsistent Portal Terminology and Unwanted Rate Display on User Dashboard

- **Component:** `templates/user_panel.html`, `templates/booking_panel.html`, `templates/my_bookings.html`, `static/js/user_panel.js`
- **Severity:** Low / UI Consistency & Presentation
- **Symptom:**
  1. The top header of the user panel displayed **"Driver Dashboard"** and the sidebar badge displayed **"DRIVER PORTAL"**, while the navigation item was labelled **"User Dashboard"**.
  2. The "Nearby Facilities" card on the main user dashboard showed hourly rates (e.g. `₹30/hr`, `₹50/hr`, `₹20/hr`, `₹40/hr`) under the live available count, which the user requested not to display on the dashboard overview.
- **Root Cause:**
  1. Static HTML in `templates/user_panel.html` and tab switching logic in `static/js/user_panel.js` defaulted to `Driver Dashboard` and `DRIVER PORTAL`.
  2. `renderDashboardNearbyLots` in `static/js/user_panel.js` appended an hourly rate tag `₹${l.hourly_rate || 40}/hr` next to each facility's open slot count.
- **Resolution:**
  - **Terminology Unification:** Changed header titles, browser document title, fallback session attributes, and sidebar badges to consistently say **"User Dashboard"** and **"USER PORTAL"** across `templates/user_panel.html`, `templates/booking_panel.html`, `templates/my_bookings.html`, and `static/js/user_panel.js`.
  - **Rate Display Removal:** Removed the hourly fee line from the dashboard's `renderDashboardNearbyLots` component, leaving a clean display of facility names, operating hours, and live vacant count.
  - **Find Parking Lots Optimization:** Removed the hourly rate badge (`₹XX/hr`) and the redundant search filter bar from the **Find Parking Lots** view (`tab-find` in `templates/user_panel.html` and `searchParkingLots` in `static/js/user_panel.js`), providing a clean, distraction-free view of all available facilities.

---

### Bug 15: Emoji Glyphs in Vehicle Type Dropdowns and Missing 'Other Vehicle' Option

- **Component:** `templates/user_panel.html`, `templates/booking_panel.html`, `core/recommendation_engine.py`, `static/js/guided_booking_wizard.js`
- **Severity:** Low / UI Consistency & Usability
- **Symptom:**
  1. The **AI Intelligent Parking Slot Recommender** vehicle type dropdown displayed emojis (`🚗 Car`, `🏍️ Bike`) inside select menu options which caused rendering artifacts and inconsistency.
  2. Users with vehicles other than cars or bikes (such as commercial vans, crossovers, or other transport) had no "Other Vehicle" category to choose in the recommendation form, vehicle registration modal, and booking wizard.
- **Root Cause:**
  1. `<select id="aiVehicleType">`, `<select id="wizardInputManualType">`, and `<select id="newVehicleType">` hardcoded Unicode emoji characters in option labels.
  2. Recommendation suitability calculation (`calculate_slot_suitability` in `core/recommendation_engine.py`) did not have an explicit branch for `'Other'` / `'Other Vehicle'`.
- **Resolution:**
  - **Clean Typography:** Removed emoji icons from all vehicle dropdown menus, rendering crisp text labels (`Car`, `Bike`, `SUV`, `Electric Vehicle`, `Other Vehicle`).
  - **Added 'Other Vehicle' Option:** Added `<option value="Other">Other Vehicle</option>` across AI recommendation dropdowns, the 5-step booking wizard, and user vehicle registration modals.
  - **AI Compatibility Ranking:** Updated `core/recommendation_engine.py` to assign top suitability (1.0) for Standard and Compact slots when "Other Vehicle" is requested.
  - **Booking Wizard Step 1 Tariff Removal:** Removed the hourly fee badge (`₹XX.0/hr`) from the facility selection cards in Step 1 (*"Where do you want to park?"*) of the booking wizard (`templates/user_panel.html`), aligning with the overall cleaner, decluttered overview style while retaining full live vacancy indicators.

---

### Enterprise Architectural Refactoring: Flask Blueprints & SQLite Deprecation

- **Component:** `app.py`, `routes/`, `.gitignore`, `smart_parking.db`
- **Severity:** Architectural Modernization & Code Quality
- **Symptom:**
  `app.py` had accumulated 6,632 lines of code containing web routes, authentication, simulation, AI forecasts, Razorpay payment processing, and slot exchange logic in a single monolithic file. In addition, an orphaned binary `smart_parking.db` existed in the repository despite MongoDB being the exclusive database engine.
- **Root Cause:**
  Lack of domain decomposition and modular blueprint boundaries caused high cognitive load, tight coupling, and maintenance friction.
- **Resolution:**
  - **Deprecated & Removed SQLite Binary:** Cleanly removed `smart_parking.db` via `git rm`, added `*.db`, `*.sqlite`, `*.sqlite3` to `.gitignore`, and updated documentation.
  - **Modular Blueprint Architecture (`routes/`):** Decomposed `app.py` into 12 dedicated Flask Blueprints in `routes/`:
    1. `routes/auth_routes.py` (`auth_bp`): Login, registration, role verification, and authentication APIs.
    2. `routes/web_routes.py` (`web_bp`): HTML web page views, root landing page, and dashboards.
    3. `routes/booking_routes.py` (`booking_bp`): 5-step booking wizard, reservation lifecycle, passes.
    4. `routes/payment_routes.py` (`payment_bp`): Razorpay orders, payment verification, penalty clearance.
    5. `routes/admin_routes.py` (`admin_bp`): Admin metrics, live telemetry, and reports.
    6. `routes/lot_routes.py` (`lot_bp`): Facilities, slot management, and activity logs.
    7. `routes/ai_routes.py` (`ai_bp`): Recommendation engine, ML forecasting, and clustering.
    8. `routes/overstay_routes.py` (`overstay_bp`): Radar tracking, barrier gate control, penalty fees.
    9. `routes/simulation_routes.py` (`simulation_bp`): Virtual clock and simulation test harness.
    10. `routes/exchange_routes.py` (`exchange_bp`): P2P slot marketplace and 2D visual swapping.
    11. `routes/email_routes.py` (`email_bp`): SMTP telemetry, diagnostic delivery test, and outbox.
    12. `routes/user_routes.py` (`user_bp`): Profile management, vehicle registrations, and settings.
    13. `routes/middleware.py`: Reusable decorators (`login_required`, `admin_required`) and session helpers.
  - **Lean Application Entrypoint:** Reduced `app.py` from 6,632 lines to 49 lines, retaining pure application factory instantiation, middleware loading, and MongoDB connectivity checks.
  - **Full Backward Compatibility:** Preserved all 149 routes, endpoints, session handling, and backward-compatible route aliases. Verified with 100% test pass rate across the unified test suite.

---

### Bug 12: Transient DNS Network Outage and Resilient Email Fallback

- **Component:** `core/email_service.py`, `tests/test_email_service.py`
- **Severity:** Medium
- **Symptom:**
  During momentary DNS lags, Wi-Fi drops, or laptop sleep re-awakenings, background email dispatches failed with `socket.gaierror: [Errno 11001] getaddrinfo failed` connecting to `smtp.gmail.com:587`. The background thread dumped full multi-line tracebacks into the server terminal, and the undelivered messages were dropped without retry or persistence.
- **Root Cause:**
  `_create_smtp_connection()` made a single socket connection attempt without backoff retry. In addition, `_dispatch_background()` logged `exc_info=True` for transient socket/DNS errors and had no fallback storage mechanism when offline.
- **Resolution:**
  - **Automatic Retry with Backoff:** Implemented up to 2 retries with a 1.0s delay in `_create_smtp_connection()` for transient socket errors (`socket.gaierror`, `socket.timeout`, `OSError`, `ConnectionError`).
  - **Graceful Offline Outbox Fallback:** Added `_dispatch_with_fallback()` which catches persistent offline/DNS errors, safely captures the undelivered email into `service.outbox` (`Offline (Network/DNS Unreachable)`), and logs a clean, informative single-line notice without dumping noisy tracebacks.
  - **Unit Test Coverage:** Added `test_dns_network_error_offline_outbox_fallback` to `tests/test_email_service.py`, asserting that simulated socket failures trigger retries and archive cleanly into the outbox.

---

## Master Test Suite Verification

To verify that all bug fixes function harmoniously without regression, the project was evaluated using the unified test runner `tests/run_tests.py`:

```
================================================================================
  AI-BASED SMART PARKING SYSTEM — UNIFIED MASTER TEST SUITE
================================================================================
Total Suites Executed : 8 (Admin, Auth, Booking, ML/Simulation, Overstay, Exchange, Email, Payment)
Total Tests Executed  : 48
Passed Tests          : 48
Failures              : 0
Errors                : 0
Execution Time        : 38.25 seconds
================================================================================
RESULT: ALL SUITES PASSED [100% SUCCESS]
================================================================================
```

### Breakdown of Test Suites
| Suite | Module | Tests | Status |
| :--- | :--- | :---: | :---: |
| **Admin & System** | `tests/test_admin_system.py` | 5 | **PASS** |
| **Authentication & RBAC** | `tests/test_auth.py` | 6 | **PASS** |
| **Booking & Slot Allocation** | `tests/test_booking.py` | 5 | **PASS** |
| **ML Models & Virtual Clock** | `tests/test_ml_simulation.py` | 5 | **PASS** |
| **Overstay & Penalty Engine** | `tests/test_overstay.py` | 4 | **PASS** |
| **Slot Exchange Lifecycle** | `tests/test_slot_exchange.py` | 3 | **PASS** |
| **SSL/TLS Email Transport** | `tests/test_email_service.py` | 13 | **PASS** |
| **Razorpay Payment Gateway** | `tests/test_payment.py` | 7 | **PASS** |
| **TOTAL** | | **48** | **100%** |

---

## System Maintenance & Production Recommendations

1. **MongoDB Service Health**:  
   Ensure the local MongoDB daemon is running before starting Flask:
   ```powershell
   net start MongoDB
   ```
2. **Starting the Web Server**:
   ```powershell
   python app.py
   ```
   Access the dashboard at `http://127.0.0.1:5000`.
3. **Environment Security**:  
   Never commit `.env` containing production email passwords or secret keys. Ensure `.gitignore` continues to exclude `.env`, `*.pyc`, `__pycache__/`, and `.DS_Store`.
4. **Email Credentials**:  
   When using Gmail SMTP (`smtp.gmail.com`), generate an **App Password** from Google Account Settings (Security > 2-Step Verification > App Passwords) rather than using your main account password.

---
*Report compiled and certified for the AI-Based Smart Parking System repository.*

