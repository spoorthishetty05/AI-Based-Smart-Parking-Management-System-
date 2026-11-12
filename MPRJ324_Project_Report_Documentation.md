# MCA Main Project (MPRJ324) — Project Report Documentation & Overleaf LaTeX Source

**Project Title:** AI-Based Smart Parking Management System  
**Course Code:** MPRJ324 (MCA Main Project Dissertation)  
**Target Length:** 80–100 Pages (formatted in Overleaf with double-spaced `12pt` academic typography, figures, tables, module specifications, evaluation charts, screenshots, and core code appendices)  
**Technology Stack:** Python 3.12, Flask 3.x (13 Modular Blueprints), MongoDB (`pymongo[srv]`), Scikit-Learn (`GradientBoostingRegressor`, `RandomForestRegressor`, `DecisionTreeRegressor`, `Ridge`, `KMeans`, `StandardScaler`), Pandas, NumPy, Joblib, Chart.js, QRCode.js, Native Python SSL/TLS SMTP, Razorpay Sandbox Integration, Gunicorn / Render Cloud Config.

---

## PART 1: Verified Project Data Summary (Strict Ground Truth from Codebase)

Use these exact verified numbers and architecture facts throughout your viva, presentation slides, and Overleaf report:

### 1.1 Facility & Infrastructure Inventory (`core/parking_places_config.py`)
The system manages **4 facility categories**, **12 named parking locations**, and **210 total parking bays** distributed across **Ground Floor (93 slots)** and **Upper Floor (117 slots)**:

| Lot ID | Category | Locations (3 per category) | Hourly Rate (Rs.) | Overstay Rate (Rs./hr config) | Slot IDs | Total Slots |
| :--- | :--- | :--- | :---: | :---: | :--- | :---: |
| **1** | **Institutions** | AJ Institute of Management (`inst_univ`), AJ Institute of Engineering & Technology (`inst_edu`), AJ Institute of Medical Sciences (`inst_med`) | 30 / 40 / 35 | 80 / 100 / 90 | `S1–S11`, `R1–R32` | **43** |
| **2** | **Mall** | City Centre Mall (`mall_city_centre`), Central Mall (`mall_central`), Shopping Mall (`mall_shopping`) | 50 / 60 / 50 | 120 / 140 / 120 | `U01–U37` | **37** |
| **3** | **Public Places** | Railway Station (`pub_railway`), Bus Stand (`pub_bus`), Public Parking Area (`pub_parking_area`) | 20 / 20 / 25 | 60 / 60 / 70 | `U38–U67` | **30** |
| **4** | **City Parking** | Hampankatta Parking (`city_hampankatta`), Central City Parking (`city_central`), Market Area Parking (`city_market`) | 40 / 40 / 35 | 100 / 100 / 90 | `A1–A12`, `B1–B12`, `C1–C13`, `D1–D13`, `E1–E12`, `F1–F12`, `G1–G13`, `H1–H13` | **100** |
| **Total** | **4 Categories** | **12 Parking Facilities** | **Rs. 20–60/hr** | — | **210 Physical Bays** | **210** |

### 1.2 Machine Learning Dataset & Features (`data/historical_parking_data.csv` & `core/ml_engine.py`)
- **Dataset Size:** `4,320` hourly records × `19` columns spanning **180 days** (`2026-01-01 00:00:00` to `2026-06-29 23:00:00`).
- **Descriptive Statistics of `occupancy_percentage`:** Mean = `46.33%`, Std. Dev. = `29.42%`, Min = `5.0%`, Max = `98.5%`.
- **Weather Distribution:** `Clear` = `2,848` hrs (`65.9%`), `Cloudy` = `824` hrs (`19.1%`), `Rainy` = `648` hrs (`15.0%`).
- **Train / Test Partitioning:** Out-of-time chronological split (`shuffle=False`, `test_size=0.2`): **3,456 Training rows** (80%) and **864 Testing rows** (20%).
- **16 Engineered Model Features (`feature_cols`):**
  `hour`, `day_of_week`, `month`, `is_weekend`, `is_holiday`, `has_event`, `sin_hour`, `cos_hour`, `sin_day`, `cos_day`, `lag_1h_occ`, `lag_24h_occ`, `rolling_mean_3h`, `weather_Clear`, `weather_Cloudy`, `weather_Rainy`.

### 1.3 Verified Model Evaluation Results (`models/occupancy_model.joblib` & `models/kmeans_model.joblib`)
- **Regression Benchmark (Test Set, $N = 864$):**
  - **GradientBoostingRegressor** *(Selected Best Model, `n_estimators=100, learning_rate=0.08, max_depth=5`)*: **$R^2 = 0.9826$**, $\text{MAE} = 2.897\%$, $\text{MSE} = 14.870$, $\text{RMSE} = 3.856\%$
  - **RandomForestRegressor** *(`n_estimators=120, max_depth=14`)*: $R^2 = 0.9824$, $\text{MAE} = 2.905\%$, $\text{MSE} = 15.050$, $\text{RMSE} = 3.879\%$
  - **DecisionTreeRegressor** *(`max_depth=10`)*: $R^2 = 0.9723$, $\text{MAE} = 3.599\%$, $\text{MSE} = 23.695$, $\text{RMSE} = 4.868\%$
  - **Ridge Regression** *(`alpha=1.0`)*: $R^2 = 0.9182$, $\text{MAE} = 6.349\%$, $\text{MSE} = 69.885$, $\text{RMSE} = 8.360\%$
- **Top Feature Importances (GradientBoostingRegressor):**
  `lag_24h_occ` (`0.7507`), `rolling_mean_3h` (`0.1328`), `hour` (`0.0299`), `cos_hour` (`0.0261`), `lag_1h_occ` (`0.0200`), `sin_hour` (`0.0166`), `weather_Rainy` (`0.0091`), `has_event` (`0.0080`).
- **4-Band Traffic Regime Classification Performance (Discretized Test Predictions, $N = 864$):**
  - Classes: `Low` ($<40\%$), `Moderate` ($40\text{–}70\%$), `High` ($70\text{–}85\%$), `Critical` ($\ge 85\%$)
  - **Overall Accuracy:** `90.97%` | **Weighted Precision:** `0.9112` | **Weighted Recall:** `0.9097` | **Weighted F1-Score:** `0.9088`
  - **Confusion Matrix (`[Low, Moderate, High, Critical]`):**
    `[[379, 4, 0, 0], [4, 197, 22, 0], [0, 18, 172, 7], [0, 0, 23, 38]]`
- **K-Means Unsupervised Congestion Clustering (`n_clusters=3`, `StandardScaler`, Inertia = `6516.18`, Silhouette Score = `0.4371`):**
  - **Off-Peak / Low Demand:** `1,560` samples (`36.1%`), Mean Occ = `17.3%`, Mean Hour = `3.9`
  - **Moderate Flow / Standard Turnover:** `595` samples (`13.8%`), Mean Occ = `25.8%`, Mean Hour = `21.7`
  - **Peak Rush / High Congestion:** `2,165` samples (`50.1%`), Mean Occ = `72.9%`, Mean Hour = `14.2`

### 1.4 Automated Test Suite Verification (`tests/run_tests.py`)
- **Total Executed:** **64 tests across 10 suites — 64 Passed, 0 Failed, 0 Errors (100% Pass Rate)**
  - `test_admin_system.py` (5), `test_auth.py` (6), `test_booking.py` (5), `test_email_service.py` (13), `test_ml_simulation.py` (5), `test_overstay.py` (4), `test_payment.py` (7), `test_security_guard.py` (10), `test_single_booking_enforcement.py` (6), `test_slot_exchange.py` (3).

---

## PART 2: Overleaf LaTeX Code (`main.tex`)

### Instructions for Overleaf Setup
1. Open [Overleaf](https://www.overleaf.com) → **New Project** → **Blank Project** (name it `MPRJ324_Smart_Parking_Report`).
2. Replace everything in `main.tex` with the LaTeX code below.
3. Replace placeholders such as `[STUDENT NAME]`, `[REGISTER NO / USN]`, `[GUIDE NAME]`, `[HOD NAME]`, `[COLLEGE / UNIVERSITY NAME]`, and `[ACADEMIC YEAR]` using Overleaf search (`Ctrl+F`).
4. Optional Screenshots (Chapter 6): Create a folder `screenshots/` in Overleaf and upload screenshots of your running dashboards (`login.png`, `user_dashboard.png`, `booking_wizard.png`, `qr_pass.png`, `security_console.png`, `admin_ai_lab.png`, `overstay_radar.png`, `slot_exchange.png`). Even *before* uploading images, the `\screenshotbox` macro automatically renders clean placeholder frames so Overleaf compiles cleanly with zero errors!
5. Click **Recompile** (`pdfLaTeX`).

````latex
% ==============================================================================
% MCA MAIN PROJECT (MPRJ324) DISSERTATION REPORT — OVERLEAF SOURCE
% Project: AI-Based Smart Parking Management System
% Compiler: pdfLaTeX (Overleaf TeX Live)
% ==============================================================================
\documentclass[12pt,a4paper,oneside]{report}

% --- Core Packages ---
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[top=1in, bottom=1in, left=1.25in, right=1in]{geometry}
\usepackage{setspace}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{graphicx}
\usepackage{float}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{tabularx}
\usepackage{multirow}
\usepackage{xcolor}
\usepackage{amsmath,amssymb}
\usepackage{listings}
\usepackage{tikz}
\usepackage{pgfplots}
\usepackage{caption}
\usepackage{subcaption}
\usepackage{tocloft}
\usepackage{enumitem}
\usepackage[hidelinks,colorlinks=true,linkcolor=blue!60!black,citecolor=teal!70!black,urlcolor=blue!70!black]{hyperref}

\pgfplotsset{compat=1.18}
\usetikzlibrary{shapes.geometric, arrows.meta, positioning, fit, backgrounds, calc, shadows}

% --- Color Palette ---
\definecolor{primaryblue}{HTML}{1E3A8A}
\definecolor{accentteal}{HTML}{0F766E}
\definecolor{codebg}{HTML}{F8FAFC}
\definecolor{codeframe}{HTML}{CBD5E1}
\definecolor{codekw}{HTML}{1D4ED8}
\definecolor{codestr}{HTML}{047857}
\definecolor{codecomm}{HTML}{64748B}

% --- Code Listings Styling ---
\lstdefinestyle{pythoncode}{
    language=Python,
    backgroundcolor=\color{codebg},
    frame=single,
    rulecolor=\color{codeframe},
    basicstyle=\ttfamily\footnotesize,
    keywordstyle=\color{codekw}\bfseries,
    stringstyle=\color{codestr},
    commentstyle=\color{codecomm}\itshape,
    numberstyle=\tiny\color{codecomm},
    numbers=left,
    stepnumber=1,
    numbersep=8pt,
    breaklines=true,
    breakatwhitespace=false,
    showstringspaces=false,
    tabsize=4,
    captionpos=b
}
\lstset{style=pythoncode}

% --- Page Headers & Footers ---
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\textit{AI-Based Smart Parking Management System}}
\fancyhead[R]{\small\textit{MPRJ324 --- MCA Project Report}}
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0.4pt}

% --- Chapter Heading Formatting ---
\titleformat{\chapter}[display]
  {\normalfont\huge\bfseries\color{primaryblue}}
  {\chaptertitlename\ \thechapter}{14pt}{\Huge}
\titlespacing*{\chapter}{0pt}{-20pt}{24pt}

% --- Screenshot Placeholder / Auto-Image Macro ---
% Automatically loads the image if uploaded to screenshots/, or renders a neat frame.
\newcommand{\screenshotbox}[3]{%
  \begin{figure}[H]
    \centering
    \IfFileExists{screenshots/#1}{%
      \includegraphics[width=0.92\textwidth]{screenshots/#1}%
    }{%
      \fbox{%
        \begin{minipage}[c][6.2cm][c]{0.88\textwidth}
          \centering
          \textcolor{primaryblue}{\textbf{[Application Screenshot: #1]}}\\[6pt]
          \small\textit{Upload \texttt{screenshots/#1} in Overleaf to display the live UI capture here.}\\[4pt]
          \footnotesize\color{gray}#3
        \end{minipage}%
      }%
    }%
    \caption{#2}
    \label{fig:#1}
  \end{figure}
}

% --- Convenience Macros for Project Placeholders ---
\newcommand{\studentname}{[STUDENT FULL NAME]}
\newcommand{\studentusn}{[UNIVERSITY REGISTER NO. / USN]}
\newcommand{\guidename}{[INTERNAL GUIDE NAME, DESIGNATION]}
\newcommand{\hodname}{[HOD NAME, HEAD OF DEPARTMENT]}
\newcommand{\collegename}{[INSTITUTE / UNIVERSITY NAME]}
\newcommand{\deptname}{Department of Master of Computer Applications (MCA)}
\newcommand{\academicyear}{2025--2026}

\begin{document}
\onehalfspacing

% ==============================================================================
% FRONT MATTER
% ==============================================================================
\pagenumbering{roman}

% --- TITLE PAGE ---
\begin{titlepage}
  \centering
  \vspace*{0.4cm}
  {\Large\bfseries \collegename \par}
  \vspace{0.2cm}
  {\large \deptname \par}
  \vspace{1.0cm}
  \rule{\textwidth}{1.5pt}\\[0.4cm]
  {\Huge\bfseries\color{primaryblue} AI-BASED SMART PARKING MANAGEMENT SYSTEM \par}
  \vspace{0.25cm}
  {\large\textit{Intelligent Occupancy Forecasting, Multi-Criteria Bay Recommendation, Automated Overstay Enforcement, Peer-to-Peer Slot Exchange, and Security Gate Console} \par}
  \rule{\textwidth}{1.5pt}\\[1.0cm]

  {\large A Main Project Dissertation Report Submitted in Partial Fulfillment of the Requirements for the Award of the Degree of \par}
  \vspace{0.3cm}
  {\Large\bfseries MASTER OF COMPUTER APPLICATIONS (MCA) \par}
  \vspace{0.2cm}
  {\large Course Code: \textbf{MPRJ324} \par}

  \vspace{1.0cm}
  {\large Submitted By \par}
  \vspace{0.2cm}
  {\Large\bfseries \studentname \par}
  {\large Register No.: \textbf{\studentusn} \par}

  \vspace{1.0cm}
  {\large Under the Guidance of \par}
  \vspace{0.2cm}
  {\Large\bfseries \guidename \par}
  {\normalsize \deptname \par}

  \vfill
  {\large Academic Year: \academicyear \par}
\end{titlepage}

% --- BONAFIDE CERTIFICATE ---
\chapter*{BONAFIDE CERTIFICATE}
\addcontentsline{toc}{chapter}{Bonafide Certificate}

This is to certify that the Main Project Dissertation entitled \textbf{``AI-Based Smart Parking Management System''} (Course Code: \textbf{MPRJ324}) is a bonafide record of original software engineering, machine learning modeling, and system implementation work carried out by \textbf{\studentname} (Register No.: \textbf{\studentusn}) in the \deptname, \collegename, in partial fulfillment of the requirements for the award of the degree of \textbf{Master of Computer Applications (MCA)} during the academic year \academicyear.

This dissertation has not been submitted previously, in part or in full, to this or any other University or Institution for the award of any degree or diploma.

\vspace{2.5cm}
\noindent
\begin{tabularx}{\textwidth}{X X}
  \rule{6cm}{0.6pt} & \rule{6cm}{0.6pt} \\
  \textbf{\guidename} & \textbf{\hodname} \\
  Project Guide & Head of the Department \\
  \deptname & \deptname \\
\end{tabularx}

\vspace{2.2cm}
\noindent
\textbf{External Viva-Voce Examination Held On:} \underline{\hspace{4.5cm}}\\[1.5cm]
\begin{tabularx}{\textwidth}{X X}
  \rule{6cm}{0.6pt} & \rule{6cm}{0.6pt} \\
  \textbf{Internal Examiner} & \textbf{External Examiner} \\
\end{tabularx}
\clearpage

% --- DECLARATION BY STUDENT ---
\chapter*{DECLARATION}
\addcontentsline{toc}{chapter}{Declaration by the Student}

I, \textbf{\studentname} (Register No.: \textbf{\studentusn}), hereby declare that the Main Project work entitled \textbf{``AI-Based Smart Parking Management System''} submitted to \collegename\ for the course \textbf{MPRJ324} is an authentic record of my own work carried out under the supervision and guidance of \textbf{\guidename}.

I further affirm that the software source code, machine learning pipelines, database schemas, empirical evaluations, and experimental findings presented in this report have not formed the basis for the award of any degree, diploma, or certificate elsewhere, and all external literature and software libraries have been duly acknowledged.

\vspace{2.5cm}
\noindent
Place: [CITY NAME] \hfill \rule{5.5cm}{0.6pt} \\
Date: \underline{\hspace{3.5cm}} \hfill \textbf{\studentname} \\
\mbox{} \hfill (\studentusn)
\clearpage

% --- ACKNOWLEDGMENTS ---
\chapter*{ACKNOWLEDGMENTS}
\addcontentsline{toc}{chapter}{Acknowledgments}

I express my sincere gratitude to \textbf{\hodname}, Head of the \deptname, \collegename, for providing institutional support, computing infrastructure, and academic encouragement throughout the MCA program.

I am deeply indebted to my project guide, \textbf{\guidename}, for continuous mentorship, technical reviews of the backend MongoDB persistence architecture and Scikit-Learn forecasting pipelines, and constructive feedback during iterative debugging and system verification.

I also extend my appreciation to the faculty members, laboratory staff, and peers whose critical testing of the Driver Portal, Security Guard Gate Console, and Admin Intelligence Dashboard helped identify edge cases in concurrent slot allocation, overstay calculation, and atomic booking rollbacks. Finally, I thank my family for their constant support during the completion of this dissertation.
\clearpage

% --- ABSTRACT ---
\chapter*{ABSTRACT}
\addcontentsline{toc}{chapter}{Abstract}

Urban campuses, commercial malls, civic terminals, and central business districts suffer from acute parking search congestion, manual barrier bottlenecks, revenue leakage from unmonitored overstays, and zero predictive visibility into upcoming bay demand. Existing management utilities either operate as static CRUD reservation ledgers or rely exclusively on expensive proprietary IoT hardware sensors without intelligent occupancy forecasting, conflict-free interval validation, or multi-party bay optimization.

This dissertation presents the design, implementation, and empirical validation of an \textbf{AI-Based Smart Parking Management System} engineered with Python 3.12, Flask (13 modular domain Blueprints), MongoDB, and Scikit-Learn. The platform manages \textbf{210 physical parking slots} across \textbf{12 configurable facilities} spanning 4 domains (\textit{Institutions}, \textit{Mall}, \textit{Public Places}, and \textit{City Parking}) distributed over Ground Floor (93 bays) and Upper Floor (117 bays).

At its analytical core, the system benchmarks four supervised regressors on a 180-day hourly historical dataset (\textbf{4,320 rows, 19 features}) augmented with cyclical diurnal/weekly encodings ($\sin/\cos$), temporal lags (\texttt{lag\_1h\_occ}, \texttt{lag\_24h\_occ}, \texttt{rolling\_mean\_3h}), and meteorological/event multipliers. On an out-of-time chronological 80/20 split (3,456 train / 864 test samples), \textbf{GradientBoostingRegressor} outperforms Random Forest, Decision Tree, and Ridge Regression with \textbf{$R^2 = 0.9826$}, \textbf{$\text{MAE} = 2.897\%$}, and \textbf{$\text{RMSE} = 3.856\%$}, while achieving \textbf{90.97\% accuracy} and a \textbf{0.9088 weighted F1-score} across four operational traffic regimes (\texttt{Low}, \texttt{Moderate}, \texttt{High}, \texttt{Critical}). Complementarily, unsupervised \textbf{K-Means clustering} ($k=3$, Silhouette Score = \textbf{0.4371}) segments traffic behaviors into \textit{Off-Peak}, \textit{Moderate Flow}, and \textit{Peak Rush} clusters, and a 6-factor \textbf{Multi-Criteria Slot Recommendation Engine} ranks available bays in real time.

Beyond predictive intelligence, the application delivers end-to-end operational execution: a 5-Step Guided Booking Wizard with strict interval-overlap validation and rollback protection, dynamic scannable QR digital passes, an automated \textbf{Overstay Detection \& Penalty Engine} enforcing a 15-minute grace window and vehicle-tiered penalties (Car: Rs. 60, Bike: Rs. 30, Other: Rs. 80), an atomic \textbf{Peer-to-Peer Slot Exchange Marketplace}, a dedicated \textbf{Security Guard Gate Console} for walk-in barrier check-ins/checkouts, Razorpay sandbox payment verification (\texttt{HMAC-SHA256}), and non-blocking native SSL/TLS email alerts. System correctness was verified through a unified 64-test automated suite achieving a \textbf{100\% pass rate} (64/64 passed across 10 modules).

\clearpage
\tableofcontents
\clearpage
\listoffigures
\clearpage
\listoftables
\clearpage

% ==============================================================================
% MAIN BODY
% ==============================================================================
\pagenumbering{arabic}

% ==============================================================================
% CHAPTER 1: INTRODUCTION
% ==============================================================================
\chapter{Introduction}

\section{Background and Domain Overview}
Rapid urbanization and rising private vehicle ownership across Indian tier-1 and tier-2 cities such as Mangaluru and Bengaluru have outpaced structured parking supply at academic campuses, medical complexes, shopping malls, railway terminals, and commercial hubs. Drivers frequently cruise through parking aisles without prior bay visibility, while gate operators rely on paper registers or disconnected single-terminal spreadsheet trackers. These fragmented practices produce long entry queues, uneven bay utilization (congested Ground Floor entrances alongside underutilized Upper Floor bays), uncollected post-expiry overstay charges, and inability to shift peak-hour arrivals before saturation occurs.

Modernizing facility operations requires unifying three layers into a single software platform:
\begin{enumerate}[leftmargin=*]
  \item \textbf{Predictive Traffic Intelligence:} Forecasting hourly occupancy trends ahead of arrival using temporal cyclical signals, historical lag autocorrelation, weather conditions, and special event indicators.
  \item \textbf{Conflict-Free Operational Persistence:} Managing real-time 2D bay availability, strict time-interval overlap prevention, walk-in security barrier registration, and atomic peer-to-peer slot exchanges backed by a schema-flexible NoSQL store (MongoDB).
  \item \textbf{Automated Financial \& Compliance Governance:} Enforcing exact booking end times with a fixed grace period, calculating tiered vehicle penalties, processing cryptographic payment signatures, and dispatching asynchronous transactional notifications.
\end{enumerate}

The \textbf{AI-Based Smart Parking Management System} implements all three layers across \textbf{4 facility categories} (\textit{Institutions}, \textit{Mall}, \textit{Public Places}, and \textit{City Parking}) covering \textbf{12 configured locations} and \textbf{210 physical bays} across Ground Floor (93 slots) and Upper Floor (117 slots).

\section{Problem Statement}
Conventional parking systems and preliminary prototype applications exhibit five critical operational and engineering gaps addressed directly by this project:
\begin{enumerate}[leftmargin=*]
  \item \textbf{Absence of Forward Demand Visibility:} Administrators and drivers lack reliable 24-hour forecasts conditioned on time of day, weekend patterns, rainy-weather car surges, and campus/commercial events.
  \item \textbf{Manual Gate Bottlenecks \& Dual-Channel Desync:} Walk-in guests arriving at physical gates without pre-booking must be registered instantaneously alongside online web reservations without causing double-booked \texttt{booking\_id}/\texttt{reservation\_id} collisions or partial writes.
  \item \textbf{Revenue Leakage from Unmonitored Overstays:} Vehicles remaining parked beyond their booked end window consume bays needed by incoming reservations, yet premature penalty triggers or missing grace-period logic cause customer disputes.
  \item \textbf{Suboptimal Bay Assignment:} Simple first-come-first-served allocation ignores walking distance to entry gates, elevator proximity, vehicle-to-slot compatibility (EV, Compact, SUV, Bike, Disabled), covered bay preferences, and congestion scores.
  \item \textbf{Rigid Non-Transferable Reservations:} Drivers whose plans shift slightly cannot safely swap assigned bays or intervals with other active drivers without risking orphaned slot locks.
\end{enumerate}

\section{Objectives of the Project}
The primary objectives accomplished in this system are:
\begin{itemize}[leftmargin=*]
  \item To engineer a modular Flask web architecture organized into \textbf{13 domain Blueprints} and specialized backend engines under \texttt{core/} backed by \textbf{MongoDB} as the primary transactional database.
  \item To construct an hourly parking time-series dataset (180 days, 4,320 records) and benchmark four Scikit-Learn regression algorithms (\texttt{GradientBoostingRegressor}, \texttt{RandomForestRegressor}, \texttt{DecisionTreeRegressor}, and \texttt{Ridge}) alongside unsupervised \texttt{KMeans} clustering ($k=3$).
  \item To implement a \textbf{6-criterion Weighted Slot Suitability Engine} ranking available slots between $60.0\%$ and $98.5\%$ with human-readable rationale tags.
  \item To build a \textbf{Role-Based Multi-Portal Interface} serving Drivers (5-Step Guided Wizard, Digital QR Pass, Slot Exchange), Security Guards (On-Spot Walk-In Registration, Floor/Bay Allocation, Gate Radar Checkout), and Administrators (AI Intelligence Lab, Live Heatmaps, Overstay Radar, Virtual Simulation Clock, and Analytics Export).
  \item To enforce a deterministic \textbf{15-minute grace period} and vehicle-specific overstay penalties (Car: Rs. 60, Bike: Rs. 30, Other: Rs. 80) paired with Razorpay-style HMAC-SHA256 verification and non-blocking SSL/TLS email alerts.
  \item To validate all subsystems end-to-end through an automated master test suite achieving 100\% pass rate across all functional workflows.
\end{itemize}

\section{Scope and Limitations}
\subsection{Scope}
\begin{itemize}[leftmargin=*]
  \item Full lifecycle reservation workflow across 12 locations (AJ Institutions in Mangaluru, city malls, transit hubs, and commercial lots).
  \item Online pre-booking (single active booking enforcement for standard drivers) and high-throughput Security Gate walk-in booking without single-booking caps.
  \item Automated virtual clock progression (\texttt{simulation\_engine.py}) enabling deterministic demonstration of check-ins, grace windows, and overstay sweeps without waiting real-time hours.
  \item Cloud-ready deployment supporting both local MongoDB Community Server and MongoDB Atlas via \texttt{MONGO\_URI} with Gunicorn WSGI compatibility.
\end{itemize}

\subsection{Limitations}
\begin{itemize}[leftmargin=*]
  \item \textbf{Simulated Telemetry Dataset:} Because proprietary municipal IoT loop-detector feeds were unavailable during academic development, ML training relies on a physically grounded 180-day synthetic hourly time-series (\texttt{historical\_parking\_data.csv}) modeled around dual-peak commuter curves, weather surges, and event spikes.
  \item \textbf{Sandbox Payment Gateway:} Payment order creation and \texttt{HMAC-SHA256} signature validation follow Razorpay API conventions in sandbox/mock mode (\texttt{RAZORPAY\_MOCK\_MODE=true}) without live merchant bank settlement.
  \item \textbf{Virtual Hardware Barriers:} Gate open/close events are represented digitally in the Security Gate Console rather than wired to physical RS-485 boom-barrier relays or ANPR cameras.
\end{itemize}

% ==============================================================================
% CHAPTER 2: LITERATURE SURVEY / REVIEW
% ==============================================================================
\chapter{Literature Survey / Review}

\section{Summary of Existing Research Works}
Academic and industrial literature in intelligent transportation and smart parking spans sensor networks, computer vision, time-series occupancy forecasting, and reservation optimization:

\begin{enumerate}[leftmargin=*]
  \item \textbf{IoT Sensor-Driven Smart Parking Guidance (2018--2021):} Several IEEE smart-city architectures deploy ultrasonic rangefinders, magnetometer nodes, or LoRaWAN/MQTT gateways at each bay to broadcast binary vacant/occupied states to mobile dashboards. While accurate for instantaneous bay occupancy, hardware-only deployments incur high capital/maintenance costs per stall and offer zero short-term look-ahead forecasting before a driver arrives.
  \item \textbf{Statistical Time-Series Forecasting (ARIMA / Linear Models):} Classical econometric models such as ARIMA and regularized linear regression (Ridge) capture baseline diurnal means cleanly when traffic follows smooth periodic trends. However, linear models struggle with sharp nonlinear transitions such as weekday 08:00--10:00 morning rush hours, evening 17:00--20:00 peaks, and sudden multiplicative impacts from rainy weather or local events.
  \item \textbf{Deep Sequential \& Computer Vision Pipelines (CNN / LSTM):} Vision-based detectors (e.g., PKLot CNN classifiers) identify bay occupancy from overhead CCTV frames, while LSTM recurrent networks learn temporal sequences over multi-year parking meter logs. Although effective on large GPU clusters, deep models require high memory footprints (often exceeding low-cost cloud web tiers) and extensive annotated training corpora.
  \item \textbf{Tree-Based Ensemble Learning for Tabular Urban Demand (Random Forest / Gradient Boosting):} Recent comparative studies in urban mobility show that gradient boosted trees and random forests paired with explicit cyclical trigonometric time encodings ($\sin/\cos$ of hour and weekday), short-term lag windows (\texttt{t-1h}, \texttt{t-24h}), and rolling averages consistently rival deep networks on tabular hourly occupancy series while maintaining sub-millisecond CPU inference latency and transparent feature importances.
  \item \textbf{Reservation \& Dynamic Pricing Systems:} Game-theoretic and heuristic allocation systems optimize bay revenue and walking distance, yet frequently overlook operational gate exceptions such as walk-in overrides, grace-period dispute prevention, and peer-to-peer swap atomicity.
\end{enumerate}

\section{Comparative Analysis: Existing Approaches vs. Proposed Methodology}

\begin{table}[H]
\centering
\caption{Comparative Analysis of Existing Approaches vs. Proposed System}
\label{tab:lit_comparison}
\small
\begin{tabularx}{\textwidth}{>{\bfseries}p{3.0cm} X X X}
\toprule
\textbf{Dimension} & \textbf{Sensor-Only IoT Systems} & \textbf{Linear / Deep-Only ML Prototypes} & \textbf{Proposed System (Smart Parking AI)} \\
\midrule
Occupancy Visibility & Current state only; zero advance forecast & Forecast only; lacks bay-level reservation engine & Live 2D bay matrix + 24h GBR forecast ($R^2 = 0.9826$) \\
\addlinespace
Feature Modeling & Raw binary sensor pulse & Raw hour integers or unindexed sequences & Cyclical $\sin/\cos$, 1h/24h lags, 3h rolling mean, weather \& events \\
\addlinespace
Bay Allocation Logic & Nearest open sensor stall & None / manual selection & 6-factor Multi-Criteria Suitability Engine (60\%--98.5\%) \\
\addlinespace
Gate \& Overstay Governance & Manual attendant penalties & Not implemented & 15-min fixed grace period + vehicle-tiered auto penalties + Security Gate Console \\
\addlinespace
Booking Flexibility & Single-user static ticket & N/A & Atomic Peer-to-Peer Slot Exchange + rollback-safe transactions \\
\addlinespace
Deployment Footprint & Per-bay hardware sensors required & High RAM / GPU runtime (TF/PyTorch) & Pure Python/Scikit-Learn ($\approx 471$ KB model); runs on 512 MB cloud RAM \\
\bottomrule
\end{tabularx}
\end{table}

% ==============================================================================
% CHAPTER 3: SYSTEM REQUIREMENTS & FEASIBILITY ANALYSIS
% ==============================================================================
\chapter{System Requirements \& Feasibility Analysis}

\section{Hardware and Software Requirements}

\begin{table}[H]
\centering
\caption{Hardware Requirements (Development \& Cloud Production)}
\label{tab:hw_req}
\begin{tabularx}{\textwidth}{>{\bfseries}p{4.2cm} X X}
\toprule
\textbf{Component} & \textbf{Minimum Development Spec} & \textbf{Cloud Deployment Target (Render)} \\
\midrule
Processor (CPU) & Dual-Core x86\_64 (2.0 GHz+) & 0.1--1.0 vCPU shared cloud container \\
Memory (RAM) & 4 GB RAM & 512 MB RAM (single Gunicorn worker + 4 threads) \\
Disk Storage & 500 MB free space (Code + MongoDB) & $\approx$ 11 MB application footprint + 512 MB Atlas M0 DB \\
Network & Broadband / Local Loopback (\texttt{127.0.0.1}) & HTTPS (TLS) + Port 27017/SRV Atlas + Port 587/465 SMTP \\
Client Browser & Chrome / Edge / Firefox (HTML5 + ES6) & Any desktop or mobile web browser \\
\bottomrule
\end{tabularx}
\end{table}

\begin{table}[H]
\centering
\caption{Software \& Technology Stack Specification}
\label{tab:sw_req}
\begin{tabularx}{\textwidth}{>{\bfseries}p{4.2cm} p{4.2cm} X}
\toprule
\textbf{Layer} & \textbf{Technology / Library} & \textbf{Role in Project} \\
\midrule
Language Runtime & Python 3.12 & Core backend, ML training, WSGI execution \\
Web Framework & Flask $\ge 3.0.0$, Flask-CORS & Modular routing across 13 domain Blueprints \\
WSGI Server & Gunicorn $\ge 21.2.0$ & Multi-threaded production HTTP serving \\
Database Engine & MongoDB + PyMongo[srv] $\ge 4.6$ & Persistent storage (15 collections + atomic counters) \\
ML \& Data Science & Scikit-Learn $\ge 1.4$, Pandas, NumPy, Joblib & Regression benchmarking, K-Means clustering, serialization \\
Visualization & Chart.js, Matplotlib (Agg), QRCode.js & Interactive forecasts, headless EDA plots, QR tickets \\
Email Transport & Python \texttt{smtplib} + \texttt{ThreadPoolExecutor} & Non-blocking STARTTLS (587) / SSL (465) HTML alerts \\
Payment Mock API & HMAC-SHA256 (\texttt{payment\_service.py}) & Razorpay-compatible order \& signature verification \\
\bottomrule
\end{tabularx}
\end{table}

\section{Technical Feasibility}
The architecture intentionally selects \textbf{Scikit-Learn} tabular ensembles serialized via \texttt{joblib} (\texttt{occupancy\_model.joblib}: 470.8 KB; \texttt{kmeans\_model.joblib}: 19.9 KB) rather than heavyweight deep-learning frameworks. Because the entire codebase, frontend static assets, dataset (690.6 KB), and serialized models occupy only \textbf{10.6 MB} on disk and consume under 250 MB RAM with a single Gunicorn worker (\texttt{--workers 1 --threads 4}), the system operates reliably on standard university lab machines as well as free-tier cloud containers (512 MB RAM). Furthermore, MongoDB's document model accommodates dynamic interval arrays (\texttt{booked\_slots}), counters, and audit trails without rigid schema migrations.

\section{Operational and Economic Feasibility}
\begin{itemize}[leftmargin=*]
  \item \textbf{Operational Feasibility:} Three dedicated role portals prevent workflow clutter. Drivers book via a guided 5-step wizard; Security Guards operate a high-contrast dark Gate Console tailored for rapid walk-in plate entry and one-click barrier checkouts; Administrators inspect KPIs, run virtual clock overstay simulations, and export CSV ledgers. Legacy SQLite dependencies and error-prone hardcoded UI shortcuts were eliminated during architectural hardening.
  \item \textbf{Economic Feasibility:} The software eliminates proprietary per-bay sensor hardware costs during phase-1 rollout, relies exclusively on open-source Python packages, runs on zero-cost cloud hosting (Render Free Tier + MongoDB Atlas 512 MB M0), and recovers municipal/campus overstay revenue through automated grace-period and penalty enforcement.
\end{itemize}

% ==============================================================================
% CHAPTER 4: SYSTEM DESIGN & ARCHITECTURE
% ==============================================================================
\chapter{System Design \& Architecture}

\section{System Architecture \& Data Flow Diagram}
Figure \ref{fig:sys_arch} illustrates the layered architecture linking the three role-specific client interfaces to the 13 Flask Blueprints, domain processing engines under \texttt{core/}, Scikit-Learn predictive artifacts, and MongoDB collections.

\begin{figure}[H]
\centering
\begin{tikzpicture}[
  node distance=0.8cm and 0.9cm,
  box/.style={rectangle, draw=primaryblue, thick, rounded corners=4pt, fill=blue!5, text width=3.4cm, align=center, minimum height=1.0cm, font=\small},
  eng/.style={rectangle, draw=accentteal, thick, rounded corners=4pt, fill=teal!6, text width=3.2cm, align=center, minimum height=0.95cm, font=\footnotesize},
  db/.style={cylinder, shape border rotate=90, draw=orange!80!black, thick, fill=orange!8, minimum height=1.2cm, minimum width=3.2cm, align=center, font=\small},
  arr/.style={-{Stealth[length=2.5mm]}, thick, color=black!75}
]
  % Top Client Layer
  \node[box] (driver) {\textbf{Driver Portal}\\5-Step Wizard, QR Pass,\\Slot Exchange};
  \node[box, right=of driver] (guard) {\textbf{Security Gate Console}\\Walk-In Entry, Floor/Bay,\\Radar Checkout};
  \node[box, right=of guard] (admin) {\textbf{Admin Intelligence}\\AI Lab, Overstay Radar,\\Simulation \& Reports};

  % Middle Flask Layer
  \node[box, fill=indigo!8, text width=11.6cm, below=1.0cm of guard] (flask) {\textbf{Flask WSGI Application (\texttt{app.py}) --- 13 Modular Blueprints}\\ \footnotesize \texttt{auth, web, booking, payment, admin, user, lot, ai, overstay, simulation, exchange, email, security}};

  % Core Engine Layer
  \node[eng, below left=1.1cm and -1.0cm of flask] (ml) {\textbf{ML \& K-Means}\\(\texttt{ml\_engine.py})\\GBR + Clustering};
  \node[eng, right=0.5cm of ml] (rec) {\textbf{Suitability Engine}\\(\texttt{recommendation\_engine.py})\\6-Factor Scoring};
  \node[eng, right=0.5cm of rec] (ovr) {\textbf{Overstay Engine}\\(\texttt{overstay\_engine.py})\\15m Grace + Penalty};
  \node[eng, below=0.7cm of ml] (pay) {\textbf{Payment Service}\\(\texttt{payment\_service.py})\\HMAC-SHA256 Orders};
  \node[eng, right=0.5cm of pay] (mail) {\textbf{Email Transport}\\(\texttt{email\_service.py})\\SSL/TLS 4 Workers};
  \node[eng, right=0.5cm of mail] (sim) {\textbf{Simulation Engine}\\(\texttt{simulation\_engine.py})\\Virtual Clock Offsets};

  % Bottom Persistence Layer
  \node[db, below=1.0cm of mail] (mongo) {\textbf{MongoDB (\texttt{smart\_parking})}\\15 Collections + Atomic Counters};
  \node[box, fill=gray!10, draw=gray!70!black, text width=3.4cm, left=1.0cm of mongo] (joblib) {\textbf{Model Artifacts}\\ \footnotesize \texttt{occupancy\_model.joblib}\\ \texttt{kmeans\_model.joblib}};

  % Arrows
  \draw[arr] (driver.south) -- (driver.south |- flask.north);
  \draw[arr] (guard.south) -- (flask.north);
  \draw[arr] (admin.south) -- (admin.south |- flask.north);

  \draw[arr] (flask.south) -- (ml.north);
  \draw[arr] (flask.south) -- (rec.north);
  \draw[arr] (flask.south) -- (ovr.north);
  \draw[arr] (ml.south) -- (pay.north);
  \draw[arr] (rec.south) -- (mail.north);
  \draw[arr] (ovr.south) -- (sim.north);

  \draw[arr] (ml.west) -- ++(-0.6,0) |- (joblib.west);
  \draw[arr] (pay.south) -- (pay.south |- mongo.north);
  \draw[arr] (mail.south) -- (mongo.north);
  \draw[arr] (sim.south) -- (sim.south |- mongo.north);
\end{tikzpicture}
\caption{System Architecture and Modular Blueprint Data Flow}
\label{fig:sys_arch}
\end{figure}

\section{ML Training and Inference Pipeline}
Figure \ref{fig:ml_pipeline} shows the end-to-end training and prediction workflow implemented in \texttt{core/ml\_engine.py}.

\begin{figure}[H]
\centering
\begin{tikzpicture}[
  node distance=0.55cm,
  stepbox/.style={rectangle, draw=primaryblue, thick, rounded corners=3pt, fill=blue!4, text width=11cm, align=center, minimum height=0.85cm, font=\small},
  arr/.style={-{Stealth[length=2.3mm]}, thick}
]
  \node[stepbox] (s1) {\textbf{1. Historical Time-Series Ingestion:} Read \texttt{data/historical\_parking\_data.csv} (4,320 hourly records, 180 days)};
  \node[stepbox, below=of s1] (s2) {\textbf{2. Feature Engineering:} Extract \texttt{hour}, \texttt{day\_of\_week}, cyclic $\sin/\cos$ transforms, weather one-hot flags, \texttt{lag\_1h}, \texttt{lag\_24h}, \texttt{rolling\_mean\_3h}};
  \node[stepbox, below=of s2] (s3) {\textbf{3. Chronological Split (\texttt{shuffle=False}):} 80\% Train (3,456 rows) / 20\% Out-of-Time Test (864 rows)};
  \node[stepbox, below=of s3] (s4) {\textbf{4. Multi-Model Benchmark + K-Means:} Fit GBR, RandomForest, DecisionTree, Ridge; Fit StandardScaler + KMeans ($k=3$)};
  \node[stepbox, below=of s4] (s5) {\textbf{5. Evaluation \& Serialization:} Select highest-$R^2$ regressor (GBR: $R^2=0.9826$), serialize to \texttt{models/*.joblib}};
  \node[stepbox, below=of s5, fill=teal!7, draw=accentteal] (s6) {\textbf{6. Real-Time Inference (\texttt{/api/ai/predict}):} Predict occupancy \%, confidence band ($\pm 4.2\%$), slot count vs. live MongoDB bays};

  \draw[arr] (s1) -- (s2);
  \draw[arr] (s2) -- (s3);
  \draw[arr] (s3) -- (s4);
  \draw[arr] (s4) -- (s5);
  \draw[arr] (s5) -- (s6);
\end{tikzpicture}
\caption{Scikit-Learn Training, Validation, and Inference Pipeline}
\label{fig:ml_pipeline}
\end{figure}

\section{Use Case \& Operational Flowcharts}

\begin{figure}[H]
\centering
\begin{tikzpicture}[
  actor/.style={rectangle, draw=primaryblue, thick, rounded corners=6pt, fill=blue!8, text width=2.8cm, align=center, minimum height=1.1cm, font=\small\bfseries},
  uc/.style={ellipse, draw=accentteal, thick, fill=teal!5, text width=4.8cm, align=center, minimum height=0.8cm, font=\footnotesize},
  line/.style={-{Stealth[length=2mm]}, thick, color=black!70}
]
  \node[actor] (d) {Driver (User)};
  \node[actor, below=3.0cm of d] (g) {Security Guard};
  \node[actor, below=2.8cm of g] (a) {Administrator};

  \node[uc, right=2.4cm of d, yshift=0.9cm] (u1) {Register / Login \& Manage Vehicles};
  \node[uc, right=2.4cm of d, yshift=-0.1cm] (u2) {5-Step AI Guided Booking \& QR Pass};
  \node[uc, right=2.4cm of d, yshift=-1.1cm] (u3) {Pay Booking / Penalty (Razorpay Sandbox)};
  \node[uc, right=2.4cm of d, yshift=-2.1cm] (u4) {Offer / Request Peer Slot Exchange};

  \node[uc, right=2.4cm of g, yshift=0.45cm] (u5) {On-Spot Walk-In Guest Registration};
  \node[uc, right=2.4cm of g, yshift=-0.65cm] (u6) {Gate Radar Checkout \& Slot Reassignment};

  \node[uc, right=2.4cm of a, yshift=0.9cm] (u7) {AI 24h Forecast, K-Means \& EDA Lab};
  \node[uc, right=2.4cm of a, yshift=-0.1cm] (u8) {Overstay Radar \& Virtual Clock Step};
  \node[uc, right=2.4cm of a, yshift=-1.1cm] (u9) {Manage Slots, Guards \& CSV Analytics};

  \draw[line] (d) -- (u1); \draw[line] (d) -- (u2); \draw[line] (d) -- (u3); \draw[line] (d) -- (u4);
  \draw[line] (g) -- (u5); \draw[line] (g) -- (u6);
  \draw[line] (a) -- (u7); \draw[line] (a) -- (u8); \draw[line] (a) -- (u9);
\end{tikzpicture}
\caption{Role-Based System Use Case Model}
\label{fig:use_case}
\end{figure}

\begin{figure}[H]
\centering
\begin{tikzpicture}[
  node distance=0.5cm,
  proc/.style={rectangle, draw=primaryblue, thick, fill=blue!4, text width=7.5cm, align=center, minimum height=0.75cm, font=\footnotesize},
  dec/.style={diamond, aspect=2.6, draw=orange!80!black, thick, fill=orange!8, text width=3.8cm, align=center, font=\footnotesize},
  arr/.style={-{Stealth[length=2.2mm]}, thick}
]
  \node[proc] (start) {Reservation Reaches Check-In Time (\texttt{booked\_end\_time})};
  \node[dec, below=0.6cm of start] (d1) {\texttt{now <= booked\_end}?};
  \node[proc, right=1.2cm of d1, text width=4.2cm, fill=green!10, draw=green!60!black] (ok) {\textbf{Within Booking Time}\\Penalty = Rs. 0};
  \node[dec, below=0.8cm of d1] (d2) {\texttt{now <= booked\_end + 15m}?};
  \node[proc, right=1.2cm of d2, text width=4.2cm, fill=yellow!15, draw=orange!80!black] (grace) {\textbf{Grace Period Active}\\Penalty = Rs. 0 (15m buffer)};
  \node[proc, below=0.8cm of d2, fill=red!8, draw=red!70!black] (viol) {\textbf{Overstay Violation Flagged (\texttt{overstay\_records})}\\Apply Fixed Penalty: Car Rs. 60 | Bike Rs. 30 | Other Rs. 80};
  \node[proc, below=0.5cm of viol] (notif) {Insert In-App Alert + Dispatch Async Email (\texttt{overstay\_alert.html})};

  \draw[arr] (start) -- (d1);
  \draw[arr] (d1) -- node[above,font=\scriptsize]{Yes} (ok);
  \draw[arr] (d1) -- node[right,font=\scriptsize]{No} (d2);
  \draw[arr] (d2) -- node[above,font=\scriptsize]{Yes} (grace);
  \draw[arr] (d2) -- node[right,font=\scriptsize]{No} (viol);
  \draw[arr] (viol) -- (notif);
\end{tikzpicture}
\caption{Deterministic Overstay Grace Period and Vehicle-Tiered Penalty Flowchart}
\label{fig:overstay_flow}
\end{figure}

\section{Database Schema \& Dataset Description}

\subsection{MongoDB Collections Schema (\texttt{smart\_parking})}
The application uses pure MongoDB persistence across \textbf{15 collections} coordinated via sequential atomic integer counters (\texttt{db.counters} with collision-guarded \texttt{get\_next\_sequence()} in \texttt{core/database.py}).

\begin{longtable}{>{\bfseries\ttfamily}p{3.6cm} p{4.2cm} p{6.2cm}}
\caption{MongoDB Collections Schema Summary}
\label{tab:mongo_schema}\\
\toprule
\textbf{Collection} & \textbf{Primary Keys / Indexes} & \textbf{Key Stored Document Attributes} \\
\midrule
\endfirsthead
\toprule
\textbf{Collection} & \textbf{Primary Keys / Indexes} & \textbf{Key Stored Document Attributes} \\
\midrule
\endhead
users & \texttt{user\_id} (uniq), \texttt{email} (uniq) & \texttt{name}, \texttt{email} (normalized lowercase), \texttt{password\_hash} (scrypt), \texttt{phone}, \texttt{role} (\texttt{user}/\texttt{admin}/\texttt{security}), \texttt{gate}, \texttt{lot\_id}, \texttt{is\_active} \\
vehicles & \texttt{vehicle\_id} (uniq), \texttt{user\_id} & \texttt{vehicle\_number}, \texttt{vehicle\_type} (\texttt{Car}/\texttt{Bike}/\texttt{EV}/\texttt{SUV}/\texttt{Other}), \texttt{model}, \texttt{is\_default} \\
parking\_lots & \texttt{lot\_id} (uniq) & \texttt{lot\_name}, \texttt{category}, \texttt{total\_slots}, \texttt{hourly\_rate}, \texttt{operating\_hours} \\
parking\_slots & \texttt{slot\_id} (uniq), \texttt{lot\_id} & \texttt{slot\_number}, \texttt{floor} (\texttt{Ground Floor}/\texttt{Upper Floor}), \texttt{zone}, \texttt{slot\_type}, \texttt{status}, \texttt{distance\_to\_entry\_m}, \texttt{distance\_to\_elevator\_m}, \texttt{booked\_slots[]}, \texttt{place\_id} \\
reservations & \texttt{reservation\_id} (uniq), \texttt{user\_id}, \texttt{slot\_id} & \texttt{booking\_id}, \texttt{slot\_number}, \texttt{vehicle\_number}, \texttt{date}, \texttt{start\_time}, \texttt{end\_time}, \texttt{duration\_hours}, \texttt{amount}, \texttt{status}, \texttt{is\_walkin}, \texttt{payment\_status} \\
bookings & \texttt{booking\_id} (uniq), \texttt{date} & Synchronized booking ledger doc (\texttt{booked\_slots} mirror, \texttt{booking\_date}, \texttt{slot\_id}, \texttt{user\_id}, \texttt{status}) with rollback cleanup on reservation error \\
overstay\_records & \texttt{overstay\_id} (uniq), \texttt{reservation\_id} & \texttt{overstay\_minutes}, \texttt{penalty\_amount}, \texttt{vehicle\_type}, \texttt{status} (\texttt{Pending}/\texttt{Paid}/\texttt{Cleared}), \texttt{grace\_end\_time}, \texttt{alert\_sent} \\
slot\_exchange\_listings & \texttt{listing\_id} (uniq), \texttt{reservation\_id} & \texttt{user\_id}, \texttt{slot\_number}, \texttt{desired\_preferences}, \texttt{status} (\texttt{open}/\texttt{completed}/\texttt{cancelled}) \\
slot\_exchange\_requests & \texttt{request\_id} (uniq), \texttt{listing\_id} & \texttt{requester\_id}, \texttt{requester\_reservation\_id}, \texttt{status} (\texttt{pending}/\texttt{accepted}/\texttt{rejected}) \\
slot\_exchange\_history & \texttt{history\_id} (uniq) & Atomic audit record of old vs. swapped \texttt{slot\_id} and \texttt{slot\_number} between both drivers \\
notifications & \texttt{notification\_id} (uniq), \texttt{user\_id} & \texttt{type}, \texttt{title}, \texttt{message}, \texttt{related\_id}, \texttt{is\_read} (\texttt{0}/\texttt{1}), \texttt{created\_at} \\
payment\_orders & \texttt{id} (\texttt{order\_*}) & \texttt{amount} (paise), \texttt{amount\_in\_rupees}, \texttt{currency} (\texttt{INR}), \texttt{receipt}, \texttt{status} \\
payment\_transactions & \texttt{payment\_id} (\texttt{pay\_*}) & \texttt{order\_id}, \texttt{signature} (HMAC-SHA256), \texttt{method}, \texttt{verified}, \texttt{reservation\_id} \\
system\_settings & \texttt{setting\_key} (uniq) & \texttt{simulated\_time}, \texttt{sim\_offset\_seconds}, global simulation \& penalty parameters \\
counters & \texttt{\_id} (collection name) & Atomic \texttt{seq} integer synchronized against existing documents \\
\bottomrule
\end{longtable}

\subsection{Historical Dataset Description (\texttt{data/historical\_parking\_data.csv})}
The dataset generated by \texttt{generate\_synthetic\_dataset(num\_days=180)} contains \textbf{4,320 hourly observations} across \textbf{19 columns} (\texttt{2026-01-01 00:00:00} to \texttt{2026-06-29 23:00:00}). Baseline curves model dual commuter rush hours on weekdays (08:00--10:00 AM around $78\%$ and 17:00--20:00 PM around $75\%$) vs. single afternoon-evening shopping curves on weekends ($65\% + 15\sin(\dots)$), modulated by Gaussian noise, national holiday suppression ($\times 0.65$), rainy-weather private-vehicle surges ($\times 1.22$), and special event spikes ($\times 1.30$). All values are clamped within $[5.0\%, 98.5\%]$ (dataset mean: $46.33\%$, standard deviation: $29.42\%$).

\begin{table}[H]
\centering
\caption{Engineered Feature Set Passed to Regression Pipeline (16 Features)}
\label{tab:features}
\small
\begin{tabularx}{\textwidth}{>{\ttfamily}p{4.0cm} p{3.2cm} X}
\toprule
\textbf{Feature Name} & \textbf{Data Type} & \textbf{Modeling Purpose} \\
\midrule
hour, day\_of\_week, month & Integer (0--23, 0--6, 1--12) & Raw calendar positioning across day and week \\
sin\_hour, cos\_hour & Float $[-1, 1]$ & Eliminates 23:00-to-00:00 wraparound discontinuity ($\sin/\cos(2\pi h/24)$) \\
sin\_day, cos\_day & Float $[-1, 1]$ & Smooth 7-day weekly periodicity ($\sin/\cos(2\pi d/7)$) \\
is\_weekend, is\_holiday & Binary $\{0,1\}$ & Distinguishes commuter vs. weekend/holiday demand profiles \\
has\_event & Binary $\{0,1\}$ & Captures $+30\%$ demand surges during campus/city events \\
weather\_Clear/Cloudy/Rainy & One-Hot $\{0,1\}$ & Encodes $+22\%$ private-car surge during rain \\
lag\_1h\_occ, lag\_24h\_occ & Float (\%) & 1-hour autocorrelation and 24-hour diurnal persistence \\
rolling\_mean\_3h & Float (\%) & 3-hour moving average trend smoother \\
\bottomrule
\end{tabularx}
\end{table}

% ==============================================================================
% CHAPTER 5: IMPLEMENTATION & METHODOLOGY
% ==============================================================================
\chapter{Implementation \& Methodology}

\section{Algorithm Selection and Justification}
\begin{enumerate}[leftmargin=*]
  \item \textbf{Occupancy Forecasting --- Gradient Boosting Regressor (vs. Random Forest, Decision Tree, Ridge):}
  We benchmarked four Scikit-Learn regressors on the identical chronological 80/20 split. \texttt{Ridge} ($R^2 = 0.9182$) underfits sharp rush-hour nonlinearities. A single \texttt{DecisionTreeRegressor} ($R^2 = 0.9723$) exhibits higher variance. Both \texttt{RandomForestRegressor} ($R^2 = 0.9824$) and \texttt{GradientBoostingRegressor} ($R^2 = 0.9826$, \texttt{n_estimators=100, learning_rate=0.08, max_depth=5}) achieve sub-3\% MAE; \texttt{GradientBoostingRegressor} is automatically selected by maximizing test $R^2$ because sequential residual boosting learns combined weather-event-lag interactions more sharply while serializing to only 471 KB.
  \item \textbf{Traffic Regime Discovery --- K-Means Clustering ($k=3$):}
  Features \texttt{['hour', 'occupancy\_percentage', 'day\_of\_week', 'rolling\_mean\_3h']} are standardized via \texttt{StandardScaler} before fitting \texttt{KMeans(n\_clusters=3, n\_init=10, random\_state=42)}. Sorting centroids by mean occupancy automatically labels clusters as \textit{Off-Peak}, \textit{Moderate Flow}, and \textit{Peak Rush} for advisory badges.
  \item \textbf{Slot Recommendation --- Multi-Criteria Weighted Suitability Scoring:}
  Rather than a black-box ranker, \texttt{calculate\_slot\_suitability()} computes a deterministic weighted score over 6 operational factors:
  \[
    S_{\text{raw}} = 0.25 S_{\text{entry}} + 0.20 S_{\text{elev}} + 0.25 S_{\text{vtype}} + 0.15 S_{\text{pref}} + 0.10 S_{\text{cong}} + 0.05 S_{\text{dur}}
  \]
  and scales $S_{\text{raw}}$ to $[65.0\%, 98.5\%]$, paired with explicit explanatory bullets (walking distance in meters, estimated walk minutes, coverage status, and EV compatibility).
\end{enumerate}

\section{Module-by-Module Explanation}
\begin{itemize}[leftmargin=*]
  \item \textbf{\texttt{app.py} \& \texttt{config.py}:} Application factory initializing Flask, CORS, environment configuration (\texttt{.env}), native email transport, automatic initial MongoDB seeding (\texttt{init\_db()}), overstay check sweep, and registration of all 13 Blueprints (\texttt{auth}, \texttt{web}, \texttt{booking}, \texttt{payment}, \texttt{admin}, \texttt{user}, \texttt{lot}, \texttt{ai}, \texttt{overstay}, \texttt{simulation}, \texttt{exchange}, \texttt{email}, \texttt{security}).
  \item \textbf{\texttt{core/database.py} \& \texttt{core/mongo\_engine.py}:} Pure MongoDB connection pool supporting both local MongoDB (\texttt{127.0.0.1:27017}) and cloud Atlas (\texttt{MONGO\_URI}), atomic \texttt{get\_next\_sequence()} with duplicate-ID collision skipping (\texttt{\_SEQUENCE\_ID\_FIELD\_MAP}), transaction-like booking insertion with rollback cleanup if reservation insertion fails, and time-interval overlap prevention across \texttt{booked\_slots}.
  \item \textbf{\texttt{core/overstay\_engine.py} \& \texttt{core/simulation\_engine.py}:} Computes time relative to actual system clock plus stored \texttt{sim\_offset\_seconds}. Enforces zero penalty during active booking and 15-minute grace window, then triggers \texttt{overstay\_records}, in-app notifications, and templated emails.
  \item \textbf{\texttt{core/payment\_service.py}:} Generates Razorpay-compatible \texttt{order\_*} and \texttt{pay\_*} identifiers, validates \texttt{HMAC-SHA256(order\_id|payment\_id, secret)}, updates booking/overstay payment status, and issues receipt emails.
  \item \textbf{\texttt{routes/security\_routes.py}:} Dedicated Gate Operator endpoints for facility/floor-filtered slot queries, walk-in spot booking (bypassing standard driver single-booking limits while keeping global ID counters synchronized), live radar, checkout, and slot reassignment.
  \item \textbf{\texttt{routes/exchange\_routes.py}:} Peer-to-peer marketplace allowing drivers to list confirmed slots for swap, submit exchange proposals, and perform atomic dual-reservation bay swaps.
\end{itemize}

\section{Core Code Snippets (Verified System Extracts)}

\begin{lstlisting}[caption={ML Training and Benchmarking Pipeline (Excerpt from \texttt{core/ml\_engine.py})},label={lst:ml_train}]
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, shuffle=False
)
models = {
    'RandomForestRegressor': RandomForestRegressor(
        n_estimators=120, max_depth=14, random_state=42, n_jobs=-1),
    'GradientBoostingRegressor': GradientBoostingRegressor(
        n_estimators=100, learning_rate=0.08, max_depth=5, random_state=42),
    'DecisionTreeRegressor': DecisionTreeRegressor(max_depth=10, random_state=42),
    'RidgeRegression': Ridge(alpha=1.0)
}
for name, model in models.items():
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    r2 = r2_score(y_test, preds)
    mae = mean_absolute_error(y_test, preds)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    if r2 > best_r2:
        best_r2, best_model_name = r2, name
\end{lstlisting}

\begin{lstlisting}[caption={Multi-Criteria Slot Suitability Scoring (Excerpt from \texttt{core/recommendation\_engine.py})},label={lst:suitability}]
entry_score = max(0.0, 1.0 - (entry_dist / 60.0))
elev_score  = max(0.0, 1.0 - (elev_dist / 50.0))
congestion_score = max(0.0, 1.0 - (predicted_occupancy / 100.0))

raw_score = (
    (entry_score * 0.25) +
    (elev_score * 0.20) +
    (vtype_score * 0.25) +
    (pref_score * 0.15) +
    (congestion_score * 0.10) +
    (duration_score * 0.05)
)
suitability_pct = min(98.5, max(60.0, round(65.0 + (raw_score * 33.5), 1)))
\end{lstlisting}

\begin{lstlisting}[caption={Overstay Grace Period & Vehicle-Tiered Penalty Calculation (\texttt{core/overstay\_engine.py})},label={lst:overstay}]
def get_vehicle_penalty_amount(vehicle_type):
    norm = normalize_vehicle_type(vehicle_type)
    if norm == 'Bike':
        return 30.0
    elif norm == 'Other vehicles':
        return 80.0
    return 60.0  # Standard Car / SUV / EV

# Fixed Grace Period: 15 minutes after booked_end
if now <= booked_end:
    status, penalty = 'Within Booking Time', 0.0
elif now <= booked_end + timedelta(minutes=15):
    status, penalty = 'Grace Period', 0.0
else:
    status, penalty = 'Penalty Applicable', get_vehicle_penalty_amount(vehicle_type)
\end{lstlisting}

\begin{lstlisting}[caption={Atomic Counter Collision Guard \& Rollback Safety (\texttt{core/database.py} \& \texttt{core/mongo\_engine.py})},label={lst:rollback}]
# From core/database.py: prevent counter collisions after partial seeds/imports
def get_next_sequence(sequence_name):
    db = get_mongo_db()
    id_field = _SEQUENCE_ID_FIELD_MAP.get(sequence_name)
    for _ in range(100):
        ret = db.counters.find_one_and_update(
            {'_id': sequence_name}, {'$inc': {'seq': 1}},
            upsert=True, return_document=ReturnDocument.AFTER
        )
        candidate = int(ret['seq'])
        if not id_field or db[sequence_name].find_one({id_field: candidate}, {'_id': 1}) is None:
            return candidate
    return int(ret['seq'])

# From core/mongo_engine.py: rollback booking & slot interval on failure
try:
    db.reservations.insert_one(res_doc)
except Exception:
    db.bookings.delete_one({'booking_id': new_res_id})
    db.parking_slots.update_one({'slot_id': s_id}, {'$pull': {'booked_slots': interval_doc}})
    raise
\end{lstlisting}

\begin{lstlisting}[caption={HMAC-SHA256 Razorpay Signature Verification (\texttt{core/payment\_service.py})},label={lst:payment}]
def compute_signature(self, order_id: str, payment_id: str) -> str:
    msg = f"{order_id}|{payment_id}".encode('utf-8')
    secret = self.key_secret.encode('utf-8')
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()
\end{lstlisting}

% ==============================================================================
% CHAPTER 6: RESULTS AND PERFORMANCE EVALUATION
% ==============================================================================
\chapter{Results and Performance Evaluation}

\section{Regression Evaluation Metrics (Occupancy Forecasting)}
All four candidate Scikit-Learn regressors were trained on the 3,456-row chronological training partition and evaluated on the unseen 864-row out-of-time test split. As summarized in Table \ref{tab:reg_metrics}, \textbf{GradientBoostingRegressor} achieved the best generalization accuracy with $R^2 = 0.9826$ and $\text{RMSE} = 3.856\%$.

\begin{table}[H]
\centering
\caption{Regression Model Benchmark Results on Unseen Test Split ($N = 864$)}
\label{tab:reg_metrics}
\begin{tabular}{lcccc}
\toprule
\textbf{Model} & \textbf{$R^2$ Score} & \textbf{MAE (\%)} & \textbf{MSE} & \textbf{RMSE (\%)} \\
\midrule
\textbf{GradientBoostingRegressor (Selected)} & \textbf{0.9826} & \textbf{2.897} & \textbf{14.870} & \textbf{3.856} \\
RandomForestRegressor & 0.9824 & 2.905 & 15.050 & 3.879 \\
DecisionTreeRegressor & 0.9723 & 3.599 & 23.695 & 4.868 \\
Ridge Regression & 0.9182 & 6.349 & 69.885 & 8.360 \\
\bottomrule
\end{tabular}
\end{table}

\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    ybar,
    width=0.88\textwidth,
    height=6.2cm,
    bar width=18pt,
    ylabel={Error / Score},
    symbolic x coords={GBR, RandomForest, DecisionTree, Ridge},
    xtick=data,
    ymin=0, ymax=10,
    nodes near coords,
    nodes near coords align={vertical},
    legend pos=north west,
    grid=major,
    title={Test Set Error Comparison: MAE (\%) vs. RMSE (\%)}
]
\addplot[fill=primaryblue!75] coordinates {(GBR,2.897) (RandomForest,2.905) (DecisionTree,3.599) (Ridge,6.349)};
\addplot[fill=accentteal!75] coordinates {(GBR,3.856) (RandomForest,3.879) (DecisionTree,4.868) (Ridge,8.360)};
\legend{MAE (\%), RMSE (\%)}
\end{axis}
\end{tikzpicture}
\caption{MAE and RMSE Error Comparison Across Evaluated Regressors}
\label{fig:reg_chart}
\end{figure}

\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    xbar,
    width=0.88\textwidth,
    height=6.0cm,
    bar width=11pt,
    xlabel={Relative Feature Importance},
    symbolic y coords={has\_event, weather\_Rainy, sin\_hour, lag\_1h\_occ, cos\_hour, hour, rolling\_mean\_3h, lag\_24h\_occ},
    ytick=data,
    xmin=0, xmax=0.85,
    nodes near coords,
    nodes near coords align={horizontal},
    grid=major,
    title={Top-8 Feature Importances (GradientBoostingRegressor)}
]
\addplot[fill=primaryblue!70] coordinates {
  (0.0080,has\_event) (0.0091,weather\_Rainy) (0.0166,sin\_hour) (0.0200,lag\_1h\_occ)
  (0.0261,cos\_hour) (0.0299,hour) (0.1328,rolling\_mean\_3h) (0.7507,lag\_24h\_occ)
};
\end{axis}
\end{tikzpicture}
\caption{Top-8 Feature Importances Driving Occupancy Forecasts}
\label{fig:feat_imp}
\end{figure}

\section{Traffic-Band Classification Accuracy \& Confusion Matrix}
When continuous predictions from the selected \texttt{GradientBoostingRegressor} are mapped to the platform's four operational traffic alert badges---\textbf{Low} ($<40\%$), \textbf{Moderate} ($40\text{--}70\%$), \textbf{High} ($70\text{--}85\%$), and \textbf{Critical} ($\ge 85\%$)---the model achieves an overall accuracy of \textbf{90.97\%} (786/864) with zero cross-tier misclassifications between \textit{Low} and \textit{High/Critical}.

\begin{table}[H]
\centering
\caption{Per-Class Traffic Regime Classification Metrics ($N = 864$ Test Samples)}
\label{tab:class_metrics}
\begin{tabular}{lcccc}
\toprule
\textbf{Traffic Class} & \textbf{Precision} & \textbf{Recall} & \textbf{F1-Score} & \textbf{Support} \\
\midrule
Low ($< 40\%$) & 0.9896 & 0.9896 & 0.9896 & 383 \\
Moderate ($40\%\text{--}70\%$) & 0.8995 & 0.8834 & 0.8914 & 223 \\
High ($70\%\text{--}85\%$) & 0.7926 & 0.8731 & 0.8309 & 197 \\
Critical ($\ge 85\%$) & 0.8444 & 0.6230 & 0.7170 & 61 \\
\midrule
\textbf{Weighted Average / Overall} & \textbf{0.9112} & \textbf{0.9097} & \textbf{0.9088} & \textbf{864} \\
\bottomrule
\end{tabular}
\end{table}

\begin{table}[H]
\centering
\caption{4$\times$4 Confusion Matrix (Rows = Actual Class, Columns = Predicted Class)}
\label{tab:conf_matrix}
\begin{tabular}{lcccc}
\toprule
\textbf{Actual $\backslash$ Predicted} & \textbf{Low} & \textbf{Moderate} & \textbf{High} & \textbf{Critical} \\
\midrule
\textbf{Low}      & \textbf{379} & 4   & 0   & 0  \\
\textbf{Moderate} & 4   & \textbf{197} & 22  & 0  \\
\textbf{High}     & 0   & 18  & \textbf{172} & 7  \\
\textbf{Critical} & 0   & 0   & 23  & \textbf{38} \\
\bottomrule
\end{tabular}
\end{table}

\section{Unsupervised K-Means Clustering Performance}
Fitted over all 4,320 hourly records (\texttt{Inertia = 6516.18}, \textbf{Silhouette Score = 0.4371}), K-Means identifies three distinct operational demand regimes summarized in Table \ref{tab:kmeans_profiles}.

\begin{table}[H]
\centering
\caption{K-Means Congestion Cluster Profiles ($k = 3$)}
\label{tab:kmeans_profiles}
\begin{tabular}{lcccc}
\toprule
\textbf{Cluster Regime} & \textbf{Count} & \textbf{Share (\%)} & \textbf{Mean Occ (\%)} & \textbf{Mean Hour} \\
\midrule
Off-Peak / Low Demand & 1,560 & 36.1\% & 17.3\% & 3.9 \\
Moderate Flow / Standard Turnover & 595 & 13.8\% & 25.8\% & 21.7 \\
Peak Rush / High Congestion & 2,165 & 50.1\% & 72.9\% & 14.2 \\
\bottomrule
\end{tabular}
\end{table}

\section{Functional Test Suite Verification}
End-to-end integration testing via \texttt{python tests/run\_tests.py} executed \textbf{64 test cases across 10 modules} with \textbf{100\% success} (0 failures, 0 errors):

\begin{table}[H]
\centering
\caption{Master Automated Test Suite Verification Summary (64/64 Passed)}
\label{tab:test_summary}
\begin{tabularx}{\textwidth}{>{\ttfamily}p{5.5cm} c X}
\toprule
\textbf{Test Module} & \textbf{Cases} & \textbf{Verified Functional Coverage} \\
\midrule
test\_auth.py & 6 & Role-based access control, scrypt hashing, session lifecycle \\
test\_booking.py & 5 & Place search, interval conflict guard, tariff, QR pass, cancel \\
test\_single\_booking\_enforcement.py & 6 & Active booking cap for drivers; exempt walk-in gate bookings \\
test\_security\_guard.py & 10 & Gate login, floor filtering, walk-in spot booking, checkout, move \\
test\_overstay.py & 4 & 15m grace window, vehicle-tiered penalties (Rs. 60/30/80) \\
test\_slot\_exchange.py & 3 & Offer listing, proposal request, atomic two-driver bay swap \\
test\_ml\_simulation.py & 5 & GBR forecasts, K-Means regimes, virtual clock advances \\
test\_payment.py & 7 & Razorpay order creation, HMAC-SHA256 verification, receipts \\
test\_email\_service.py & 13 & STARTTLS/SSL parity, Jinja templates, async queue fallback \\
test\_admin\_system.py & 5 & System telemetry, admin KPI authorization, notifications \\
\midrule
\textbf{Total Verified} & \textbf{64} & \textbf{100\% Pass Rate (64 Passed, 0 Failed)} \\
\bottomrule
\end{tabularx}
\end{table}

\section{Screenshots of the Working Application}
Figures \ref{fig:login.png} through \ref{fig:admin_ai_lab.png} capture the deployed interfaces across all three user roles.

\screenshotbox{login.png}{Unified Role-Based Authentication Portal (Driver, Admin, Security Guard)}{Shows clean tabbed login gateway for Driver, Administrator, and Security Guard roles.}
\screenshotbox{booking_wizard.png}{5-Step AI Guided Booking Wizard and Interactive 2D Bay Matrix}{Shows facility selection, AI suitability ranking tags, and live Green/Blue/Red/Amber 2D slot matrix.}
\screenshotbox{qr_pass.png}{Digital Parking Pass with Dynamic QR Code and Booking Metadata}{Shows downloadable/printable digital pass generated after booking confirmation.}
\screenshotbox{security_console.png}{Security Guard Gate Console --- Walk-In Booking \& Radar Management}{Shows Floor Level dropdown (Ground Floor, Upper Floor, A Block, B Block), KPI cards, and Gate Radar table.}
\screenshotbox{admin_ai_lab.png}{Administrator AI Intelligence Lab --- 24-Hour Forecast \& K-Means Regimes}{Shows Chart.js 24-hour predicted curve, peak hour detection, and model evaluation metrics.}

% ==============================================================================
% CHAPTER 7: CONCLUSION AND FUTURE SCOPE
% ==============================================================================
\chapter{Conclusion and Future Scope}

\section{Summary of Outcome}
The \textbf{AI-Based Smart Parking Management System} successfully bridges predictive machine learning with day-to-day multi-role parking operations. By combining \texttt{GradientBoostingRegressor} ($R^2 = 0.9826$, $\text{RMSE} = 3.856\%$, discretized traffic accuracy $90.97\%$), \texttt{KMeans} regime discovery (Silhouette $= 0.4371$), and a 6-factor slot suitability algorithm atop a 13-Blueprint Flask/MongoDB backend, the platform eliminates flat static forecasting, prevents time-overlap double bookings, enforces fair 15-minute grace windows before vehicle-tiered overstay penalties, and unites online driver reservations with walk-in Security Gate barrier operations. All 64 automated unit and integration tests pass cleanly, and the codebase is prepared for cloud hosting on Render with MongoDB Atlas.

\section{Limitations and Potential Enhancements}
\begin{itemize}[leftmargin=*]
  \item \textbf{Real-Time ANPR \& Computer Vision Bay Telemetry:} Integrate YOLOv8/OpenCV automatic license plate recognition cameras at entry/exit booms to auto-populate walk-in plate numbers in the Security Guard Console and trigger real barrier relays over MQTT.
  \item \textbf{Multi-Horizon Deep Time-Series Retraining:} Once live production check-in logs accumulate in MongoDB Atlas \texttt{bookings}, establish an automated weekly pipeline retraining Gradient Boosting and LSTM/Temporal Fusion models on facility-specific arrival curves.
  \item \textbf{Dynamic Surge Pricing \& Live Payment Webhooks:} Switch \texttt{PaymentService} from sandbox mock mode to live Razorpay Checkout webhooks and couple predicted \texttt{Critical} ($\ge 85\%$) cluster hours with configurable dynamic tariff tiers.
  \item \textbf{Progressive Web App (PWA) \& Mobile Push Alerts:} Extend driver notifications with Web Push / SMS alerts 15 minutes prior to booking expiration.
\end{itemize}

% ==============================================================================
% PLAGIARISM CERTIFICATE & REFERENCES
% ==============================================================================
\chapter*{PLAGIARISM REPORT / ORIGINALITY CERTIFICATE}
\addcontentsline{toc}{chapter}{Plagiarism Report / Certificate}

\noindent\textbf{Project Title:} AI-Based Smart Parking Management System (MPRJ324) \\
\textbf{Student Name:} \studentname \hfill \textbf{Register No.:} \studentusn \\[1cm]

\begin{center}
\fbox{%
  \begin{minipage}[c][7.5cm][c]{0.92\textwidth}
    \centering
    \Large\bfseries [ATTACH UNIVERSITY PLAGIARISM / TURNITIN / DRILLBIT SIMILARITY REPORT HERE]\\[12pt]
    \normalsize
    Similarity Index: \underline{\hspace{2.5cm}} \% (Permissible University Threshold: $\le$ 15\%--20\%)\\[12pt]
    \small\textit{Replace or append the exported PDF page from your institution's plagiarism check tool before final binding.}
  \end{minipage}%
}
\end{center}
\vspace{1.8cm}
\noindent
\begin{tabularx}{\textwidth}{X X}
  \rule{6cm}{0.6pt} & \rule{6cm}{0.6pt} \\
  \textbf{\guidename} & \textbf{\hodname} \\
  Verified By (Project Guide) & Approved By (HOD) \\
\end{tabularx}

\begin{thebibliography}{9}
\addcontentsline{toc}{chapter}{References}

\bibitem{lin2017survey}
T. Lin, H. Rivano, and F. Le Mou\"el, ``A Survey of Smart Parking Solutions,'' \textit{IEEE Transactions on Intelligent Transportation Systems}, vol. 18, no. 12, pp. 3229--3253, Dec. 2017.

\bibitem{paidi2018smart}
V. Paidi, H. Fleyeh, J. H\aa kansson, and R. G. Nyberg, ``Smart parking sensors, technologies and applications for open parking lots: A review,'' \textit{IET Intelligent Transport Systems}, vol. 12, no. 8, pp. 735--741, 2018.

\bibitem{vlahogianni2016real}
E. I. Vlahogianni, K. Kepaptsoglou, V. Tsetsos, and M. G. Karlaftis, ``A Real-Time Parking Prediction System for Smart Cities,'' \textit{Journal of Intelligent Transportation Systems}, vol. 20, no. 2, pp. 192--204, 2016.

\bibitem{friedman2001gbm}
J. H. Friedman, ``Greedy Function Approximation: A Gradient Boosting Machine,'' \textit{The Annals of Statistics}, vol. 29, no. 5, pp. 1189--1232, 2001.

\bibitem{pedregosa2011sklearn}
F. Pedregosa et al., ``Scikit-learn: Machine Learning in Python,'' \textit{Journal of Machine Learning Research}, vol. 12, pp. 2825--2830, 2011.

\bibitem{flaskdocs}
Pallets Projects, ``Flask Web Development Documentation (v3.x) \& Modular Blueprints,'' \url{https://flask.palletsprojects.com/}, accessed 2026.

\bibitem{mongodbdocs}
MongoDB Inc., ``MongoDB Manual \& PyMongo Driver Documentation,'' \url{https://www.mongodb.com/docs/}, accessed 2026.

\bibitem{razorpaydocs}
Razorpay Software Pvt. Ltd., ``Payment Gateway Order Creation \& HMAC-SHA256 Signature Verification,'' \url{https://razorpay.com/docs/payments/server-integration/python/}, accessed 2026.

\end{thebibliography}

% ==============================================================================
% APPENDICES
% ==============================================================================
\appendix
\chapter{Environment Configuration \& Cloud Deployment (Render + MongoDB Atlas)}

\section{Production Runtime Configuration}
The application is pre-configured for both local development (MongoDB Community Server on \texttt{127.0.0.1:27017}) and cloud hosting via \texttt{Procfile} and \texttt{render.yaml}:

\begin{lstlisting}[language=bash,caption={Procfile and Render Start Command for 512 MB Cloud Tier},label={lst:procfile}]
web: gunicorn app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT --timeout 120
\end{lstlisting}

\begin{table}[H]
\centering
\caption{Required Environment Variables for Production Deployment}
\label{tab:env_vars}
\begin{tabularx}{\textwidth}{>{\ttfamily}p{4.5cm} p{3.2cm} X}
\toprule
\textbf{Variable} & \textbf{Default / Example} & \textbf{Description} \\
\midrule
MONGO\_URI & \texttt{mongodb+srv://...} & MongoDB Atlas connection URI (defaults locally to \texttt{127.0.0.1:27017}) \\
MONGO\_DB\_NAME & \texttt{smart\_parking} & Target MongoDB database name \\
SECRET\_KEY & Random 32+ char hex & Flask session \& CSRF cookie signing secret \\
FLASK\_ENV & \texttt{production} & Selects production runtime profile \\
MAIL\_SERVER / PORT & \texttt{smtp.gmail.com} / \texttt{587} & SMTP host and port (\texttt{587} STARTTLS or \texttt{465} SSL) \\
MAIL\_SUPPRESS\_SEND & \texttt{true} / \texttt{false} & Suppresses external SMTP during sandbox demos \\
RAZORPAY\_MOCK\_MODE & \texttt{true} & Enables built-in sandbox payment verification flow \\
\bottomrule
\end{tabularx}
\end{table}

\end{document}
````

> **Tip for Reaching 80–100 Pages Cleanly in Overleaf:**
> The complete LaTeX template above already gives you the full university layout, vector TikZ diagrams, PGFPlots charts, verified tables, real confusion matrix, and core code snippets (~35–45 pages compiled). To expand it comfortably to **80–100 pages** without generic padding:
> 1. **Chapter 4:** Add per-endpoint REST API specification tables covering all **13 Blueprints** (`routes/auth_routes.py`, `booking_routes.py`, `security_routes.py`, `ai_routes.py`, `overstay_routes.py`, `exchange_routes.py`, `payment_routes.py`, `admin_routes.py`, `user_routes.py`, `lot_routes.py`, `simulation_routes.py`, `email_routes.py`, `web_routes.py`) and sample JSON request/response payloads.
> 2. **Chapter 5:** Expand the core code snippets section to ~5–8 full pages using `\lstinputlisting` or verbatim extracts from `core/mongo_engine.py` (`mongo_create_booking`), `routes/exchange_routes.py` (atomic swap), `core/email_service.py` (SSL/TLS + ThreadPool), and `routes/security_routes.py` (walk-in + checkout).
> 3. **Chapter 6:** Capture and upload high-resolution full-page screenshots (`login.png`, `user_dashboard.png`, `booking_wizard.png`, `qr_pass.png`, `security_console.png`, `admin_ai_lab.png`, `overstay_radar.png`, `slot_exchange.png`, `email_receipt.png`, `test_runner_64.png`)—each full-width figure with detailed walkthrough captions adds ~1–1.5 pages naturally.
> 4. **Appendix B:** Include your terminal output log of `python tests/run_tests.py` (64/64 tests passed) and sample generated email HTML receipts.
