/**
 * User Panel Controller — AI-Based Smart Parking System
 * Powers the User Dashboard and all 9 User Modules:
 * 1. User Registration & Login (Session Context)
 * 2. User Profile & Vehicle Management
 * 3. Find Parking (Search lots, live occupancy)
 * 4. AI Parking Recommendation (Intelligent match scoring)
 * 5. Parking Slot Booking (Date/time, fare, QR pass, cancellation)
 * 6. Live 2D Parking Layout (Interactive 🟢, 🔴, 🟡 clickable grid)
 * 7. Slot Exchange (Mutual slot swapping workflow)
 * 8. My Bookings (Active, Upcoming, Completed, Cancelled)
 * 9. Parking History (Historical parking sessions)
 */

let userProfile = null;
let userVehicles = [];
let userActiveBooking = null;
let allAvailableLots = [];
let current2DSlots = [];
let selectedSlotForBooking = null;

document.addEventListener('DOMContentLoaded', () => {
  if (window.ACTIVE_USER_ID) {
    const sel = document.getElementById('userPanelDriverSelector');
    if (sel) sel.value = window.ACTIVE_USER_ID;
  }
  initUserNavigation();
  loadUserDashboard();

  // Set default dates on inputs and enforce past date/time prevention
  const padZero = (n) => String(n).padStart(2, '0');
  const dToday = new Date();
  const today = `${dToday.getFullYear()}-${padZero(dToday.getMonth() + 1)}-${padZero(dToday.getDate())}`;
  const dateInputs = document.querySelectorAll('input[type="date"]');
  dateInputs.forEach(inp => {
    inp.min = today;
    if (!inp.value || inp.value < today) inp.value = today;
  });

  const bDate = document.getElementById('bookingDate');
  const bTime = document.getElementById('bookingStartTime');
  const getNowTimeStr = () => {
    const d = new Date();
    return `${padZero(d.getHours())}:${padZero(d.getMinutes())}`;
  };

  function syncUserPanelTimeConstraints(notify = false) {
    const dLive = new Date();
    const curToday = `${dLive.getFullYear()}-${padZero(dLive.getMonth() + 1)}-${padZero(dLive.getDate())}`;
    const curNow = getNowTimeStr();
    if (bDate) {
      bDate.min = curToday;
      if (bDate.value < curToday) {
        bDate.value = curToday;
        if (notify) showUserToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'error');
      }
    }
    if (bTime && bDate) {
      if (bDate.value === curToday) {
        bTime.min = curNow;
        if (!bTime.value || bTime.value < curNow) {
          bTime.value = curNow;
          if (notify) showUserToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'error');
        }
      } else {
        bTime.removeAttribute('min');
      }
    }
  }

  if (bDate) {
    bDate.min = today;
    bDate.addEventListener('change', () => {
      syncUserPanelTimeConstraints(true);
    });
    bDate.addEventListener('input', () => {
      syncUserPanelTimeConstraints(false);
    });
  }

  if (bTime) {
    syncUserPanelTimeConstraints(false);
    bTime.addEventListener('focus', () => {
      syncUserPanelTimeConstraints(false);
    });
    bTime.addEventListener('change', () => {
      const dLive = new Date();
      const curToday = `${dLive.getFullYear()}-${padZero(dLive.getMonth() + 1)}-${padZero(dLive.getDate())}`;
      const curNow = getNowTimeStr();
      if (bDate && bDate.value === curToday) {
        if (bTime.value < curNow) {
          showUserToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'error');
          bTime.value = curNow;
        }
      }
    });
  }

  // Periodic interval to keep min attribute up to date as minutes pass
  setInterval(() => {
    syncUserPanelTimeConstraints(false);
  }, 15000);

  // Pre-load booking slots and 2D matrix immediately on startup
  loadAvailableSlotsForBooking();
  load2DLayout();

  // Notification badge initialization and live polling
  pollNotificationBadges();
  setInterval(pollNotificationBadges, 15000);

  // Handle URL hash tab switching
  const hash = window.location.hash.replace('#', '') || 'dashboard';
  switchUserTab(hash);
});

/* ==========================================================================
   NAVIGATION
   ========================================================================== */

function initUserNavigation() {
  const navItems = document.querySelectorAll('.user-nav-item');
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      const tabId = item.getAttribute('data-tab');
      if (!tabId) return; // Allow normal link navigation if no data-tab
      e.preventDefault();
      switchUserTab(tabId);
    });
  });

  window.addEventListener('hashchange', () => {
    const rawHash = window.location.hash.replace('#', '').trim();
    if (rawHash && rawHash !== 'null' && document.getElementById(`tab-${rawHash}`)) {
      switchUserTab(rawHash);
    }
  });
}

function switchUserTab(tabId) {
  if (!tabId || tabId === 'null' || !document.getElementById(`tab-${tabId}`)) {
    tabId = 'dashboard';
  }

  const navItems = document.querySelectorAll('.user-nav-item');
  const panes = document.querySelectorAll('.tab-pane');

  navItems.forEach(item => {
    if (item.getAttribute('data-tab') === tabId) item.classList.add('active');
    else item.classList.remove('active');
  });

  panes.forEach(pane => {
    if (pane.id === `tab-${tabId}`) pane.classList.add('active');
    else pane.classList.remove('active');
  });

  try {
    if (window.location.hash !== `#${tabId}`) {
      window.location.hash = tabId;
    }
  } catch (e) {}

  // Header topbar handling
  const topbar = document.querySelector('.user-topbar');
  if (topbar) {
    if (tabId === 'overstay-dashboard') {
      topbar.style.display = 'none';
    } else {
      topbar.style.display = 'flex';
    }
  }

  // Header title update
  const titles = {
    'dashboard': '<i class="fas fa-home"></i> User Dashboard',
    'profile': '<i class="fas fa-user-circle"></i> My Profile & Vehicles',
    'find': '<i class="fas fa-search-location"></i> Find Parking Lots',
    'recommendation': '<i class="fas fa-robot"></i> AI Parking Recommendation',
    'booking': '<i class="fas fa-calendar-plus"></i> Book Parking Slot',
    'layout': '<i class="fas fa-th"></i> Live 2D Parking Layout',
    'exchange': '<i class="fas fa-repeat"></i> Slot Exchange Marketplace',
    'bookings': '<i class="fas fa-ticket-simple"></i> My Bookings',
    'history': '<i class="fas fa-clock-rotate-left"></i> Parking History',
    'overstay-dashboard': '<i class="fas fa-hourglass-half"></i> Overstay Monitoring',
    'notifications': '<i class="fas fa-bell"></i> Notifications & Activity Alerts'
  };
  const titleElem = document.getElementById('userTopHeaderTitle');
  if (titleElem && titles[tabId]) titleElem.innerHTML = titles[tabId];

  // Lazy tab data loaders
  if (tabId === 'dashboard') loadUserDashboard();
  else if (tabId === 'profile') loadUserProfile();
  else if (tabId === 'find') searchParkingLots();
  else if (tabId === 'booking') prepareBookingForm();
  else if (tabId === 'layout') load2DLayout();
  else if (tabId === 'exchange') loadSlotExchangeTab();
  else if (tabId === 'bookings') loadMyBookings();
  else if (tabId === 'history') loadParkingHistory();
  else if (tabId === 'overstay-dashboard') loadOverstayDashboard();
  else if (tabId === 'notifications') loadUserNotifications();
}

/* ==========================================================================
   USER DASHBOARD
   ========================================================================== */

async function loadUserDashboard() {
  try {
    const uid = window.ACTIVE_USER_ID || '';
    const [profileRes, lotsRes, bookingsRes, exchangeRes] = await Promise.all([
      fetch('/api/users/profile'),
      fetch('/api/lots'),
      fetch(`/api/reservations/my${uid ? `?user_id=${uid}` : ''}`),
      fetch(`/api/exchange/user-active-booking${uid ? `?user_id=${uid}` : ''}`)
    ]);

    // Profile & vehicle
    if (profileRes.ok) {
      const pData = await profileRes.json();
      if (pData.status === 'success') {
        userProfile = pData.user || pData.profile || {};
        userVehicles = pData.vehicles || [];
        const nameEl = document.getElementById('dashWelcomeName');
        if (nameEl) nameEl.textContent = userProfile.name || 'User';
        
        const vehElem = document.getElementById('dashVehiclePlate');
        if (vehElem) {
          if (userVehicles.length > 0) {
            vehElem.textContent = `${userVehicles[0].license_plate} (${userVehicles[0].make_model || userVehicles[0].vehicle_type})`;
          } else {
            vehElem.textContent = 'No vehicle registered';
          }
        }
      }
    }

    // Nearby Lots & available slots
    if (lotsRes.ok) {
      const lData = await lotsRes.json();
      if (lData.status === 'success') {
        allAvailableLots = lData.lots || [];
        document.getElementById('dashNearbyLotsCount').textContent = allAvailableLots.length;
        const totalAvail = allAvailableLots.reduce((acc, l) => acc + (l.available_count || 0), 0);
        document.getElementById('dashAvailableSlotsCount').textContent = totalAvail;
        renderDashboardNearbyLots(allAvailableLots);
      }
    }

    // Active booking card
    if (bookingsRes.ok) {
      const bData = await bookingsRes.json();
      if (bData.status === 'success') {
        const reservations = bData.reservations || [];
        const activeRes = reservations.find(r => {
          const st = (r.status || '').toLowerCase();
          return st === 'confirmed' || st === 'checked_in' || st === 'reserved' || st === 'occupied' || st === 'overstayed';
        });
        userActiveBooking = activeRes;
        renderDashboardActiveBooking(activeRes);
      }
    }

    // Exchange requests count
    if (exchangeRes.ok) {
      const eData = await exchangeRes.json();
      const exElem = document.getElementById('dashExchangeCount');
      if (exElem) {
        exElem.textContent = eData.is_offered ? '1 Slot Listed' : 'None Listed';
      }
    }

    // Active Overstay check
    await checkAndRenderUserActiveOverstay();

    // Start polling timer if not already active
    if (!userOverstayPollTimer) {
      userOverstayPollTimer = setInterval(checkAndRenderUserActiveOverstay, 4000);
    }

  } catch (err) {
    console.error('Error loading dashboard data', err);
  }
}

let userOverstayPollTimer = null;

async function checkAndRenderUserActiveOverstay() {
  const container = document.getElementById('userActiveOverstayCardContainer');
  if (!container) return;

  try {
    const res = await fetch('/api/user/active-overstay');
    if (res.ok) {
      const data = await res.json();
      if (data.status === 'success' && data.has_overstay && data.overstay) {
        renderUserActiveOverstay(data.overstay);
      } else {
        container.style.display = 'none';
        container.innerHTML = '';
      }
    }
  } catch (err) {
    console.error('Error fetching active overstay', err);
  }
}

function renderUserActiveOverstay(ov) {
  const container = document.getElementById('userActiveOverstayCardContainer');
  if (!container) return;

  if (!ov) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.style.display = 'block';
  const vtypeIcon = (ov.vehicle_type === 'Bike') ? '🏍️ Bike' : '🚗 Car';
  const bid = ov.booking_id || ov.reservation_id;

  container.innerHTML = `
    <div class="active-overstay-card" style="background:#fff1f2; border:2px solid #e11d48; border-radius:12px; padding:20px; box-shadow:0 10px 25px rgba(225,29,72,0.18);">
      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1.5px solid #fecdd3; padding-bottom:12px; margin-bottom:16px;">
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="font-size:22px;">⚠️</span>
          <span style="font-size:16px; font-weight:800; color:#be123c; letter-spacing:0.05em; text-transform:uppercase;">ACTIVE OVERSTAY</span>
        </div>
        <span style="background:#be123c; color:#ffffff; font-size:11px; font-weight:800; padding:4px 10px; border-radius:12px; display:inline-flex; align-items:center; gap:6px;">
          <span style="width:7px; height:7px; background:#ffffff; border-radius:50%; display:inline-block;"></span> LIVE PENALTY
        </span>
      </div>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap:14px; margin-bottom:16px;">
        <div>
          <div style="font-size:11px; color:#64748b; font-weight:700; text-transform:uppercase;">Vehicle</div>
          <div style="font-size:14.5px; font-weight:800; color:#0f172a; margin-top:2px;">${vtypeIcon}</div>
        </div>
        <div>
          <div style="font-size:11px; color:#64748b; font-weight:700; text-transform:uppercase;">Vehicle Number</div>
          <div style="font-size:14.5px; font-weight:800; font-family:var(--font-mono); color:#0f172a; margin-top:2px;">${escapeHtml(ov.vehicle_plate)}</div>
        </div>
        <div>
          <div style="font-size:11px; color:#64748b; font-weight:700; text-transform:uppercase;">Slot</div>
          <div style="font-size:14.5px; font-weight:800; color:#0f172a; margin-top:2px;">Slot ${escapeHtml(ov.slot_number)}</div>
        </div>
        <div>
          <div style="font-size:11px; color:#64748b; font-weight:700; text-transform:uppercase;">Booked End</div>
          <div style="font-size:13.5px; font-weight:700; color:#334155; margin-top:2px;">${escapeHtml(ov.booked_end)}</div>
        </div>
        <div>
          <div style="font-size:11px; color:#64748b; font-weight:700; text-transform:uppercase;">Grace Period Ends</div>
          <div style="font-size:13.5px; font-weight:700; color:#334155; margin-top:2px;">${escapeHtml(ov.grace_end)}</div>
        </div>
        <div>
          <div style="font-size:11px; color:#64748b; font-weight:700; text-transform:uppercase;">Current Time</div>
          <div style="font-size:13.5px; font-weight:700; color:#334155; margin-top:2px;">${escapeHtml(ov.current_time)}</div>
        </div>
      </div>

      <div style="background:#ffffff; border:1px solid #fecdd3; border-radius:10px; padding:14px 18px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:14px;">
        <div>
          <div style="font-size:11.5px; color:#64748b; font-weight:700; text-transform:uppercase;">Overstay Duration</div>
          <div style="font-size:22px; font-weight:800; color:#be123c; font-family:var(--font-mono);">${escapeHtml(ov.overstay_duration)}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11.5px; color:#64748b; font-weight:700; text-transform:uppercase;">Current Penalty (₹${ov.penalty_rate}/hr)</div>
          <div style="font-size:26px; font-weight:800; color:#e11d48; font-family:var(--font-mono);">₹${ov.current_penalty.toFixed(0)}</div>
        </div>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div style="color:#9f1239; font-size:12.5px; font-weight:700; display:flex; align-items:center; gap:6px;">
          <i class="fas fa-exclamation-triangle" style="color:#e11d48;"></i>
          <span>⚠️ Penalty continues to increase until the vehicle exits.</span>
        </div>
        <button class="btn-user btn-user-danger btn-user-sm" onclick="openExitParkingModal('${bid}')" style="background:#e11d48; color:#ffffff; font-weight:800; padding:8px 16px; box-shadow:0 4px 12px rgba(225,29,72,0.3);">
          <i class="fas fa-arrow-right-from-bracket"></i> Exit Parking & Vacate Slot
        </button>
      </div>
    </div>
  `;
}

function renderDashboardActiveBooking(res) {
  const container = document.getElementById('dashActiveBookingContainer');
  if (!container) return;

  if (!res) {
    container.innerHTML = `
      <div style="text-align:center; padding:18px 10px; color:#64748b;">
        <i class="fas fa-calendar-xmark fa-2x" style="color:#cbd5e1; margin-bottom:8px;"></i>
        <p style="font-size:13.5px; margin:0;">No active parking reservation.</p>
        <button class="btn-user btn-user-primary btn-user-sm" style="margin-top:10px;" onclick="switchUserTab('find')">
          <i class="fas fa-search"></i> Find & Book a Slot
        </button>
      </div>
    `;
    return;
  }

  const st = (res.status || 'confirmed').toLowerCase();
  const isOccupied = (st === 'occupied' || st === 'checked_in' || st === 'overstayed');
  const bid = res.reservation_id || res.booking_id;
  const statusLabel = st === 'overstayed' ? 'Overstayed ⚠️' : (isOccupied ? 'Occupied / Parked' : 'Reserved / Confirmed');
  const statusColor = st === 'overstayed' ? '#e11d48' : (isOccupied ? '#0284c7' : '#15803d');
  const statusBg = st === 'overstayed' ? '#ffe4e6' : (isOccupied ? '#e0f2fe' : '#dcfce7');

  container.innerHTML = `
    <div class="active-booking-box" style="border-left: 4px solid ${statusColor};">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px;">
        <div>
          <span style="font-size:11px; text-transform:uppercase; font-weight:800; color:${statusColor}; background:${statusBg}; padding:2px 8px; border-radius:4px;">${statusLabel}</span>
          <div class="active-booking-slot">Slot ${escapeHtml(res.slot_number)}</div>
          <div style="font-size:13px; color:#334155; font-weight:600; margin-top:2px;">
            ${escapeHtml(res.lot_name || 'City Parking')} &bull; ${escapeHtml(res.floor || 'Ground Floor')}
          </div>
        </div>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
          ${(!isOccupied && st !== 'overstayed') ? `
            <button class="btn-user btn-user-success btn-user-sm" onclick="userStartParking('${bid}')" title="Start Parking session">
              <i class="fas fa-car-side"></i> Start Parking
            </button>
          ` : ''}
          <button class="btn-user btn-user-danger btn-user-sm" id="dashExitParkingBtn" onclick="openExitParkingModal('${bid}')" style="background:#fee2e2; color:#be123c; border:1px solid #fecdd3; font-weight:700;" title="Exit Parking and checkout">
            <i class="fas fa-arrow-right-from-bracket"></i> Exit Parking
          </button>
          <button class="btn-user btn-user-primary btn-user-sm" onclick="openQRPassModal('${bid}')" title="Digital QR Pass">
            <i class="fas fa-qrcode"></i> Digital QR Pass
          </button>
        </div>
      </div>
      <div style="display:flex; justify-content:space-between; margin-top:12px; padding-top:10px; border-top:1px solid rgba(0,0,0,0.08); font-size:12px; color:#475569;">
        <span><i class="fas fa-clock"></i> Booked: ${escapeHtml(res.start_time)} – ${escapeHtml(res.end_time)}</span>
        <span>Vehicle: <strong style="font-family:var(--font-mono); color:#0f172a;">${escapeHtml(res.vehicle_plate)}</strong> (${escapeHtml(res.vehicle_type || 'Car')})</span>
      </div>
    </div>
  `;
}

function renderDashboardNearbyLots(lots) {
  const container = document.getElementById('dashNearbyLotsList');
  if (!container) return;
  if (!lots || lots.length === 0) {
    container.innerHTML = '<div style="color:#94a3b8; font-size:13px;">No lots found nearby.</div>';
    return;
  }

  container.innerHTML = lots.map(l => {
    const lotIcon = (l.lot_name || '').toLowerCase().includes('mall') ? 'fa-bag-shopping'
      : ((l.lot_name || '').toLowerCase().includes('institution') || (l.lot_name || '').toLowerCase().includes('campus')) ? 'fa-graduation-cap'
      : ((l.lot_name || '').toLowerCase().includes('public') || (l.lot_name || '').toLowerCase().includes('metro')) ? 'fa-train-subway'
      : 'fa-square-parking';
    return `
    <div style="display:flex; justify-content:space-between; align-items:center; padding:11px 14px; background:#f8fafc; border-radius:10px; border:1px solid #e2e8f0; margin-bottom:8px;">
      <div style="display:flex; align-items:center; gap:10px;">
        <div style="width:34px; height:34px; border-radius:8px; background:#e0f2fe; color:#0284c7; display:flex; align-items:center; justify-content:center; font-size:15px; flex-shrink:0;">
          <i class="fas ${lotIcon}"></i>
        </div>
        <div>
          <strong style="color:#0f172a; font-size:13.5px; display:block;">${escapeHtml(l.lot_name)}</strong>
          <span style="font-size:11.5px; color:#64748b;"><i class="fas fa-clock" style="color:#0ea5e9; font-size:10.5px;"></i> ${escapeHtml(l.operating_hours || '24/7 (Open Daily)')}</span>
        </div>
      </div>
      <div style="text-align:right;">
        <span style="color:#10b981; font-weight:800; font-size:13px;">${l.available_count || 0} Open</span>
      </div>
    </div>
  `;
  }).join('');
}

/* ==========================================================================
   MODULE 2: USER PROFILE & VEHICLE MANAGEMENT
   ========================================================================== */

async function loadUserProfile() {
  try {
    const res = await fetch('/api/users/profile');
    const data = await res.json();
    if (data.status === 'success') {
      userProfile = data.user || data.profile || {};
      userVehicles = data.vehicles || [];

      const nameEl = document.getElementById('profileName');
      const emailEl = document.getElementById('profileEmail');
      const phoneEl = document.getElementById('profilePhone');
      if (nameEl) nameEl.value = userProfile.name || '';
      if (emailEl) emailEl.value = userProfile.email || '';
      if (phoneEl) phoneEl.value = userProfile.phone || '';

      renderUserVehiclesTable(userVehicles);
    } else {
      showUserToast(data.message || 'Failed to load profile', 'error');
    }
  } catch (err) {
    showUserToast('Failed to load profile', 'error');
  }
}

async function submitUpdateProfile(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById('profileName').value.trim(),
    email: document.getElementById('profileEmail').value.trim(),
    phone: document.getElementById('profilePhone').value.trim()
  };

  try {
    const res = await fetch('/api/users/profile/update', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast('Profile updated successfully!', 'success');
      loadUserProfile();
    } else {
      showUserToast(data.message || 'Update failed', 'error');
    }
  } catch (err) {
    showUserToast('Failed to update profile', 'error');
  }
}

function renderUserVehiclesTable(vehicles) {
  const tbody = document.getElementById('userVehiclesTbody');
  if (!tbody) return;
  if (!vehicles || vehicles.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:#94a3b8;">No vehicles registered yet. Add one below!</td></tr>';
    return;
  }

  tbody.innerHTML = vehicles.map(v => `
    <tr>
      <td><strong style="font-family:var(--font-mono); color:#0f172a;">${escapeHtml(v.license_plate)}</strong></td>
      <td>${escapeHtml(v.vehicle_type)}</td>
      <td>${escapeHtml(v.make_model || '—')}</td>
      <td>${escapeHtml(v.color || 'White')}</td>
      <td>
        <button class="btn-user btn-user-danger" style="padding:4px 10px; font-size:12px;" onclick="deleteUserVehicle(${v.vehicle_id})">
          <i class="fas fa-trash"></i> Remove
        </button>
      </td>
    </tr>
  `).join('');
}

function openAddVehicleModal() {
  document.getElementById('addVehicleForm').reset();
  document.getElementById('addVehicleModal').style.display = 'flex';
}

function closeAddVehicleModal() {
  document.getElementById('addVehicleModal').style.display = 'none';
}

async function submitAddVehicle(e) {
  e.preventDefault();
  const payload = {
    license_plate: document.getElementById('newVehiclePlate').value.trim().toUpperCase(),
    vehicle_type: document.getElementById('newVehicleType').value,
    make_model: document.getElementById('newVehicleModel').value.trim(),
    color: document.getElementById('newVehicleColor').value.trim() || 'White'
  };

  try {
    const res = await fetch('/api/users/vehicles/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      closeAddVehicleModal();
      loadUserProfile();
    } else {
      showUserToast(data.message || 'Failed to add vehicle', 'error');
    }
  } catch (err) {
    showUserToast('Error adding vehicle', 'error');
  }
}

async function deleteUserVehicle(vehicleId) {
  if (!confirm('Are you sure you want to remove this vehicle from your account?')) return;
  try {
    const res = await fetch(`/api/users/vehicles/${vehicleId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      loadUserProfile();
    } else {
      showUserToast(data.message || 'Error removing vehicle', 'error');
    }
  } catch (err) {
    showUserToast('Failed to delete vehicle', 'error');
  }
}

/* ==========================================================================
   MODULE 3: FIND PARKING
   ========================================================================== */

async function searchParkingLots() {
  const query = (document.getElementById('lotSearchInput')?.value || '').trim();
  const container = document.getElementById('findParkingLotsContainer');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Searching parking lots...</div>';

  try {
    const res = await fetch(`/api/lots/search?query=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (data.status === 'success') {
      const lots = data.lots || [];
      if (lots.length === 0) {
        container.innerHTML = '<div style="text-align:center; padding:30px; color:#64748b;">No parking lots found matching your query.</div>';
        return;
      }

      container.innerHTML = lots.map(l => {
        const occPct = l.total_slots > 0 ? Math.round(((l.occupied_count || 0) + (l.reserved_count || 0)) / l.total_slots * 100) : 0;
        const lotIcon = (l.lot_name || '').toLowerCase().includes('mall') ? 'fa-bag-shopping'
          : ((l.lot_name || '').toLowerCase().includes('institution') || (l.lot_name || '').toLowerCase().includes('campus')) ? 'fa-graduation-cap'
          : ((l.lot_name || '').toLowerCase().includes('public') || (l.lot_name || '').toLowerCase().includes('metro')) ? 'fa-train-subway'
          : 'fa-square-parking';
        return `
          <div class="user-card" style="margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px;">
              <div>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="display:inline-flex; align-items:center; justify-content:center; width:30px; height:30px; border-radius:8px; background:#eff6ff; color:#2563eb; font-size:14px;">
                    <i class="fas ${lotIcon}"></i>
                  </span>
                  <h3 style="font-size:17px; font-weight:800; color:#0f172a; margin:0;">${escapeHtml(l.lot_name)}</h3>
                  <span style="font-size:11px; background:#dbeafe; color:#1d4ed8; font-weight:700; padding:2px 8px; border-radius:4px;">₹${l.hourly_rate || 40}/hr</span>
                </div>
                <div style="font-size:13px; color:#64748b; margin-top:6px; display:flex; align-items:center; gap:8px;">
                  <span><i class="fas fa-layer-group" style="color:#6366f1;"></i> ${l.total_floors || 2} Floors</span>
                  <span style="color:#cbd5e1;">&bull;</span>
                  <span><i class="fas fa-clock" style="color:#0ea5e9;"></i> ${escapeHtml(l.operating_hours || '24/7 (Open Daily)')}</span>
                </div>
              </div>
              <div style="display:flex; gap:8px;">
                <button class="btn-user btn-user-secondary" onclick="viewLotIn2DLayout(${l.lot_id})">
                  <i class="fas fa-th"></i> View 2D Layout
                </button>
                <button class="btn-user btn-user-primary" onclick="startBookingForLot(${l.lot_id}, '${escapeHtml(l.lot_name)}')">
                  <i class="fas fa-bookmark"></i> Book Now
                </button>
              </div>
            </div>

            <!-- Occupancy Progress Bar -->
            <div style="margin-top:14px; background:#f1f5f9; padding:12px 14px; border-radius:8px;">
              <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:6px;">
                <span style="font-weight:700; color:#0f172a;">Occupancy: ${occPct}%</span>
                <span style="color:#10b981; font-weight:800;"><i class="fas fa-circle-check"></i> ${l.available_count || 0} Slots Available</span>
              </div>
              <div style="height:8px; background:#e2e8f0; border-radius:4px; overflow:hidden;">
                <div style="height:100%; width:${occPct}%; background:${occPct > 80 ? '#ef4444' : (occPct > 50 ? '#f59e0b' : '#10b981')};"></div>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }
  } catch (err) {
    container.innerHTML = '<div style="color:#ef4444; text-align:center;">Failed to search lots.</div>';
  }
}

/* ==========================================================================
   MODULE 4: AI PARKING RECOMMENDATION
   ========================================================================== */

async function getAIRecommendation(e) {
  if (e) e.preventDefault();
  const container = document.getElementById('aiRecResultContainer');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center; padding:20px; color:#0284c7;"><i class="fas fa-robot fa-spin fa-2x"></i><p style="margin-top:10px; font-weight:700;">Evaluating optimal slots using Multi-Factor AI Engine...</p></div>';

  const payload = {
    vehicle_type: document.getElementById('aiVehicleType')?.value || 'Car',
    preferred_floor: document.getElementById('aiPreferredFloor')?.value || 'Any',
    needs_ev: document.getElementById('aiNeedsEV')?.checked || false,
    needs_accessible: document.getElementById('aiNeedsAccessible')?.checked || false,
    duration_hours: parseFloat(document.getElementById('aiDuration')?.value) || 2.0
  };

  try {
    const res = await fetch('/api/ai/recommend', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === 'success' && data.recommendations && data.recommendations.length > 0) {
      const topSlot = data.recommendations[0];
      container.innerHTML = `
        <div class="ai-recommendation-card">
          <div>
            <div class="ai-match-badge">
              <i class="fas fa-wand-magic-sparkles"></i> ${topSlot.suitability_score || 98}% AI Match Score
            </div>
            <h3 style="font-size:22px; font-weight:800; color:#0f172a; margin:10px 0 4px;">
              Slot ${escapeHtml(topSlot.slot_number)} &bull; ${escapeHtml(topSlot.floor)}
            </h3>
            <p style="font-size:13px; color:#475569; margin:0;">
              <strong>${escapeHtml(topSlot.slot_type)}</strong> &bull; Distance to entry: ${topSlot.distance_to_entry_m}m &bull; ${escapeHtml(topSlot.rationale || 'Closest to entry with optimal ingress')}
            </p>
          </div>
          <button class="btn-user btn-user-primary" style="padding:10px 20px; font-size:14px;" onclick="bookRecommendedSlot(${topSlot.slot_id}, '${escapeHtml(topSlot.slot_number)}')">
            <i class="fas fa-bolt"></i> Instant 1-Click Book
          </button>
        </div>
      `;
    } else {
      container.innerHTML = '<div style="text-align:center; padding:20px; color:#64748b;">No vacant slots currently match strict AI filters. Please try standard booking.</div>';
    }
  } catch (err) {
    container.innerHTML = '<div style="color:#ef4444; text-align:center;">AI Recommendation engine offline.</div>';
  }
}

function bookRecommendedSlot(slotId, slotNumber) {
  switchUserTab('booking');
  setTimeout(() => {
    const slotSelect = document.getElementById('bookingSlotSelect');
    if (slotSelect) {
      slotSelect.value = slotId;
    }
  }, 300);
}

/* ==========================================================================
   MODULE 5: PARKING SLOT BOOKING
   ========================================================================== */

async function prepareBookingForm() {
  if (!allAvailableLots || allAvailableLots.length === 0) {
    try {
      const res = await fetch('/api/lots');
      const data = await res.json();
      if (data.status === 'success') {
        allAvailableLots = data.lots || [];
      }
    } catch (e) {
      console.error('Failed to load lots for booking form', e);
    }
  }
  if (!userVehicles || userVehicles.length === 0) {
    try {
      const vRes = await fetch('/api/users/profile');
      const vData = await vRes.json();
      if (vData.status === 'success') {
        userVehicles = vData.vehicles || [];
      }
    } catch (e) {
      console.error('Failed to load vehicles for booking form', e);
    }
  }
  populateBookingLots();
  populateBookingVehicles();
}

function populateBookingLots() {
  const lotSelect = document.getElementById('bookingLotSelect');
  if (!lotSelect || allAvailableLots.length === 0) return;
  lotSelect.innerHTML = allAvailableLots.map(l => `<option value="${l.lot_id}">${escapeHtml(l.lot_name)} (₹${l.hourly_rate || 40}/hr)</option>`).join('');
  loadAvailableSlotsForBooking();
}

function populateBookingVehicles() {
  const vehSelect = document.getElementById('bookingVehicleSelect');
  if (!vehSelect) return;
  if (userVehicles.length === 0) {
    vehSelect.innerHTML = '<option value="">No registered vehicles (Enter plate manually)</option>';
    return;
  }
  vehSelect.innerHTML = userVehicles.map(v => `<option value="${v.license_plate}">${escapeHtml(v.license_plate)} (${v.make_model || v.vehicle_type})</option>`).join('');
}

async function loadAvailableSlotsForBooking() {
  const lotSelect = document.getElementById('bookingLotSelect');
  const lotId = lotSelect ? (lotSelect.value || 1) : 1;
  const slotSelect = document.getElementById('bookingSlotSelect');
  if (!slotSelect) return;

  // Update tariff subtext if lot has data-rate
  if (lotSelect && lotSelect.options[lotSelect.selectedIndex]) {
    const opt = lotSelect.options[lotSelect.selectedIndex];
    const rate = opt.getAttribute('data-rate') || '40';
    const subtext = document.getElementById('bookingRateSubtext');
    if (subtext) subtext.innerHTML = `Standard tariff: ₹${rate}/hr &bull; Overstay grace: 15m`;
  }

  slotSelect.innerHTML = '<option value="">Loading available slots...</option>';

  try {
    const res = await fetch(`/api/slots?lot_id=${lotId}`);
    const data = await res.json();
    if (data.status === 'success') {
      const availSlots = (data.slots || []).filter(s => (s.status || 'available').toLowerCase() === 'available');
      if (availSlots.length === 0) {
        slotSelect.innerHTML = '<option value="">No vacant slots available in this facility</option>';
        return;
      }
      slotSelect.innerHTML = availSlots.map(s => `
        <option value="${s.slot_id}">Slot ${escapeHtml(s.slot_number)} (${escapeHtml(s.slot_type || 'Standard')} - ${escapeHtml(s.floor || 'Ground')})</option>
      `).join('');

      if (selectedSlotForBooking) {
        slotSelect.value = selectedSlotForBooking;
      }
      updateEstimatedFare();
    }
  } catch (err) {
    console.error('Error fetching available slots:', err);
    slotSelect.innerHTML = '<option value="">Failed to fetch slots</option>';
  }
}

function startBookingForLot(lotId, lotName) {
  switchUserTab('booking');
  setTimeout(() => {
    const sel = document.getElementById('bookingLotSelect');
    if (sel) {
      sel.value = lotId;
      loadAvailableSlotsForBooking();
    }
  }, 200);
}

function onBookingDurationChange() {
  const durSelect = document.getElementById('bookingDurationSelect');
  const customWrapper = document.getElementById('customDurationWrapper');
  if (!durSelect) return;

  if (durSelect.value === 'custom') {
    if (customWrapper) customWrapper.style.display = 'block';
  } else {
    if (customWrapper) customWrapper.style.display = 'none';
  }
  calculateExpectedEndTime();
}

function onCustomDurationInput() {
  calculateExpectedEndTime();
}

function onBookingTimingChange() {
  calculateExpectedEndTime();
}

function onBookingEndTimeManualChange() {
  updateEstimatedFare();
  updateGracePeriodPreview();
}

function getSelectedDurationHours() {
  const durSelect = document.getElementById('bookingDurationSelect');
  if (!durSelect) return 2.0;
  if (durSelect.value === 'custom') {
    const customInp = document.getElementById('customDurationInput');
    const val = parseFloat(customInp?.value || '2.0');
    return isNaN(val) || val <= 0 ? 2.0 : val;
  }
  const val = parseFloat(durSelect.value);
  return isNaN(val) || val <= 0 ? 2.0 : val;
}

function getSelectedDurationText() {
  const durSelect = document.getElementById('bookingDurationSelect');
  if (!durSelect) return '2 hours';
  if (durSelect.value === '0.5') return '30 minutes';
  if (durSelect.value === '1') return '1 hour';
  if (durSelect.value === '2') return '2 hours';
  if (durSelect.value === '3') return '3 hours';
  if (durSelect.value === '4') return '4 hours';
  if (durSelect.value === 'custom') {
    const h = getSelectedDurationHours();
    return `${h} hours (Custom)`;
  }
  return `${durSelect.value} hours`;
}

function calculateExpectedEndTime() {
  const startTimeInp = document.getElementById('bookingStartTime');
  const endTimeInp = document.getElementById('bookingEndTime');
  if (!startTimeInp || !endTimeInp) return;

  const startVal = startTimeInp.value || '10:00';
  const parts = startVal.split(':');
  const startMins = parseInt(parts[0] || '10', 10) * 60 + parseInt(parts[1] || '00', 10);
  const durHours = getSelectedDurationHours();
  const totalMins = Math.round(startMins + durHours * 60);

  const endH = Math.floor(totalMins / 60) % 24;
  const endM = totalMins % 60;
  const endStr = `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`;
  endTimeInp.value = endStr;

  updateGracePeriodPreview();
  updateEstimatedFare();
}

function updateGracePeriodPreview() {
  const endTimeInp = document.getElementById('bookingEndTime');
  const preview = document.getElementById('overstayDetectionPreview');
  if (!endTimeInp || !preview) return;

  const endVal = endTimeInp.value || '12:00';
  const parts = endVal.split(':');
  const endMins = parseInt(parts[0] || '12', 10) * 60 + parseInt(parts[1] || '00', 10);
  const graceMins = endMins + 15;

  const gH = Math.floor(graceMins / 60) % 24;
  const gM = graceMins % 60;
  const ampm = gH >= 12 ? 'PM' : 'AM';
  const gH12 = gH % 12 || 12;
  const gStr = `${gH12}:${String(gM).padStart(2, '0')} ${ampm}`;

  preview.innerHTML = `Overstay penalty triggers at: <strong style="color:#dc2626;">${gStr}</strong> (15-min grace)`;
}

function updateEstimatedFare() {
  const lotSel = document.getElementById('bookingLotSelect');
  let rate = 40.0;
  if (lotSel && lotSel.selectedOptions && lotSel.selectedOptions[0]) {
    rate = parseFloat(lotSel.selectedOptions[0].getAttribute('data-rate') || '40.0');
  }

  const durationHours = getSelectedDurationHours();
  const fareDisplay = document.getElementById('bookingEstimatedFare');
  if (!fareDisplay) return;

  const total = (durationHours * rate).toFixed(2);
  fareDisplay.textContent = `₹${total}`;
}

async function submitSlotBooking(e) {
  e.preventDefault();
  const slotId = document.getElementById('bookingSlotSelect')?.value;
  const dateVal = document.getElementById('bookingDate')?.value;
  const startTime = document.getElementById('bookingStartTime')?.value;
  const endTime = document.getElementById('bookingEndTime')?.value;
  let plate = document.getElementById('bookingVehicleSelect')?.value;

  if (!plate || plate === '__custom__') {
    plate = prompt('Enter vehicle license plate (e.g. KA01AB1234):');
    if (!plate) return;
  }

  if (!slotId) {
    showUserToast('Please choose an available parking slot.', 'error');
    return;
  }

  // Real-time validation: prevent past dates and times
  const pad = (n) => String(n).padStart(2, '0');
  const dNow = new Date();
  const todayStr = `${dNow.getFullYear()}-${pad(dNow.getMonth() + 1)}-${pad(dNow.getDate())}`;
  const nowTime = `${pad(dNow.getHours())}:${pad(dNow.getMinutes())}`;

  if (!dateVal || dateVal < todayStr) {
    showUserToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'error');
    return;
  }
  if (dateVal === todayStr && startTime && startTime < nowTime) {
    showUserToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'error');
    return;
  }

  const durHours = getSelectedDurationHours();
  const durText = getSelectedDurationText();

  const payload = {
    slot_id: parseInt(slotId),
    date: dateVal,
    start_time: startTime,
    end_time: endTime,
    duration_hours: durHours,
    duration: durText,
    selected_duration: durText,
    vehicle_plate: plate.toUpperCase().trim()
  };

  try {
    const res = await fetch('/api/reservations/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast('Booking Confirmed Successfully!', 'success');
      openQRPassModal(data.reservation_id);
      loadUserDashboard();
      switchUserTab('bookings');
    } else {
      showUserToast(data.message || 'Booking failed', 'error');
    }
  } catch (err) {
    showUserToast('Error creating booking', 'error');
  }
}

/* ==========================================================================
   MODULE: OVERSTAY MONITORING DASHBOARD (Requirement 4 & 7 & 8)
   ========================================================================== */

let activeOverstayRecords = [];
let currentOverstayFilter = 'all';

async function loadOverstayDashboard(silent = false) {
  const tbody = document.getElementById('overstayDashboardTableBody');
  if (!tbody) return;

  if (!silent && tbody.children.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:36px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading overstay radar data...</td></tr>';
  }

  try {
    const res = await fetch('/api/overstay/dashboard');
    if (!res.ok) throw new Error('Network response not ok');
    const data = await res.json();

    if (data.status === 'success') {
      // 1. Update 4 Summary Cards from screenshot
      if (data.summary) {
        const s = data.summary;
        const elTotOv = document.getElementById('ovSummaryTotalOverstays');
        const elExp = document.getElementById('ovSummaryExpiringSoon');
        const elCurOv = document.getElementById('ovSummaryOverstayed');
        const elResOv = document.getElementById('ovSummaryResolved');

        if (elTotOv) elTotOv.textContent = s.total_overstays ?? 3;
        if (elExp) elExp.textContent = s.expiring_soon ?? 1;
        if (elCurOv) elCurOv.textContent = s.overstayed ?? 2;
        if (elResOv) elResOv.textContent = s.resolved ?? 4;

        // Backward compatibility
        const elTot = document.getElementById('ovSummaryTotalActive');
        const elAct = document.getElementById('ovSummaryActiveParking');
        const elApp = document.getElementById('ovSummaryApproaching');
        const elCur = document.getElementById('ovSummaryCurrent');
        if (elTot) elTot.textContent = s.total_active_reservations ?? 0;
        if (elAct) elAct.textContent = s.active_parking ?? 0;
        if (elApp) elApp.textContent = s.approaching_overstay ?? 0;
        if (elCur) elCur.textContent = s.current_overstays ?? 0;
      }

      // 2. Cache records & render table
      activeOverstayRecords = data.records || [];
      renderOverstayTable(activeOverstayRecords);
    }
  } catch (err) {
    console.error('Error loading overstay dashboard', err);
    if (!silent) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:20px; color:#ef4444;">Failed to load overstay radar data.</td></tr>';
    }
  }
}

function renderOverstayTable(records) {
  const tbody = document.getElementById('overstayDashboardTableBody');
  if (!tbody) return;

  // Filter records
  let filtered = records || [];
  const fLower = (currentOverstayFilter || 'all').toLowerCase();
  if (fLower === 'penalty_applicable' || fLower === 'overstay' || fLower === 'overstayed') {
    filtered = filtered.filter(r => {
      const st = (r.status || '').toLowerCase();
      return st === 'penalty applicable' || st === 'overstay' || st === 'overstayed';
    });
  } else if (fLower === 'grace_period' || fLower === 'expiring' || fLower === 'expiring soon') {
    filtered = filtered.filter(r => (r.status || '').toLowerCase().includes('grace') || (r.status || '').toLowerCase().includes('expir'));
  } else if (fLower === 'within_booking' || fLower === 'active') {
    filtered = filtered.filter(r => (r.status || '').toLowerCase().includes('booking') || (r.status || '').toLowerCase() === 'active');
  } else if (fLower === 'completed' || fLower === 'resolved') {
    filtered = filtered.filter(r => (r.status || '').toLowerCase().includes('completed') || (r.status || '').toLowerCase() === 'resolved');
  }

  // Search filter
  const query = (document.getElementById('overstaySearchInput')?.value || '').toLowerCase().trim();
  if (query) {
    filtered = filtered.filter(r =>
      (r.driver || r.user_name || r.driver_name || '').toLowerCase().includes(query) ||
      (r.vehicle || r.vehicle_plate || '').toLowerCase().includes(query) ||
      (r.slot || r.slot_number || '').toLowerCase().includes(query) ||
      (r.parking_lot || r.lot_name || '').toLowerCase().includes(query)
    );
  }

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="14" style="text-align:center; padding:36px; color:#94a3b8;"><i class="fas fa-circle-check" style="color:#10b981; margin-right:6px;"></i> No records match the selected filter.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map((r, idx) => {
    const rawVType = (r.vehicle_type || 'Car').toLowerCase();
    let vtypeDisplay = `<span class="ov-vtype-badge"><i class="fas fa-car" style="color:#3b82f6;"></i> Car</span>`;
    if (rawVType.includes('bike') || rawVType.includes('motorcycle')) {
      vtypeDisplay = `<span class="ov-vtype-badge"><i class="fas fa-motorcycle" style="color:#10b981;"></i> Bike</span>`;
    } else if (rawVType.includes('other') || rawVType.includes('truck') || rawVType.includes('ev') || rawVType.includes('van')) {
      vtypeDisplay = `<span class="ov-vtype-badge"><i class="fas fa-truck-pickup" style="color:#8b5cf6;"></i> Other</span>`;
    }
    
    // Status visual badge matching required statuses
    let statusBadgeHtml = '';
    const st = r.status || r.overstay_status || 'Within Booking Time';
    const stLower = st.toLowerCase();
    if (st === 'Penalty Applicable' || stLower === 'overstay' || stLower === 'overstayed') {
      statusBadgeHtml = `<span class="ov-status-badge ov-status-overstayed"><span class="ov-dot dot-red"></span> Penalty Applicable</span>`;
    } else if (st === 'Grace Period' || stLower.includes('expiring')) {
      statusBadgeHtml = `<span class="ov-status-badge ov-status-expiring"><span class="ov-dot dot-yellow"></span> Grace Period</span>`;
    } else if (st === 'Completed' || stLower === 'resolved') {
      statusBadgeHtml = `<span class="ov-status-badge ov-status-resolved"><span class="ov-dot dot-green"></span> Completed</span>`;
    } else {
      statusBadgeHtml = `<span class="ov-status-badge ov-status-active"><span class="ov-dot dot-blue"></span> Within Booking Time</span>`;
    }

    const isCompleted = st === 'Completed' || stLower === 'resolved';
    const isNotified = (r.notification === 'Sent' || r.notification_status === 'Sent');
    const uName = r.user_name || r.driver_name || r.driver || 'Driver';
    const vPlate = r.vehicle_plate || r.vehicle || '—';
    const lotName = r.lot_name || r.parking_lot || 'City Parking';
    const vSlot = r.slot_number || r.slot || '—';
    const vStart = r.start_time || r.parking_start_time || '—';
    const bookedEnd = r.booked_end || r.booked_end_time || r.expected_end || '—';
    const selDuration = r.selected_duration || r.current_duration || '—';
    const gracePeriod = '15 mins';
    const graceEnd = r.grace_end || r.grace_end_time || r.grace_end_display || '—';
    const overstayDur = (st === 'Penalty Applicable' || stLower.includes('overstay')) ? (r.overstay_duration || r.actual_overstay_duration || '0m') : '0m';

    // Row visual distinction class
    let rowClass = 'ov-row';
    if (st === 'Penalty Applicable' || stLower === 'overstay' || stLower === 'overstayed') {
      rowClass += ' ov-row-overstay';
    } else if (st === 'Grace Period' || stLower.includes('expiring')) {
      rowClass += ' ov-row-grace';
    } else if (isCompleted) {
      rowClass += ' ov-row-completed';
    } else {
      rowClass += ' ov-row-active';
    }

    const isPaidPenalty = Boolean(r.penalty_paid || (r.payment_status && String(r.payment_status).trim().toLowerCase() === 'paid'));

    // Penalty amount display in INR (₹)
    const penaltyAmt = Number(r.penalty || r.current_penalty || 0);
    let penaltyDisplay = '';
    if (isPaidPenalty && penaltyAmt > 0) {
      penaltyDisplay = `<span class="ov-penalty-badge" style="background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0; padding:3px 8px; border-radius:6px; font-weight:700;">₹${penaltyAmt.toFixed(0)} <span style="font-size:10px; color:#10b981; font-weight:800;">✓ PAID</span></span>`;
    } else if (penaltyAmt > 0) {
      penaltyDisplay = `<span class="ov-penalty-badge ov-penalty-due">₹${penaltyAmt.toFixed(0)}</span>`;
    } else {
      penaltyDisplay = `<span class="ov-penalty-badge ov-penalty-zero">₹0</span>`;
    }

    // Slot badge
    const slotDisplay = `<span class="ov-slot-badge">${escapeHtml(vSlot)}</span>`;

    // Action button with direct Razorpay payment clearance
    const targetBookingId = r.booking_id || r.reservation_id || '';
    let actionHtml = '';
    if (isCompleted || isPaidPenalty) {
      actionHtml = `<span style="background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0; padding:5px 10px; border-radius:6px; font-weight:700; font-size:11.5px; display:inline-flex; align-items:center; gap:4px;"><i class="fas fa-check-circle" style="color:#10b981;"></i> Cleared</span>`;
    } else if (penaltyAmt > 0) {
      actionHtml = `
        <div style="display:flex; gap:6px; align-items:center; justify-content:center; flex-wrap:wrap;">
          <button type="button" class="btn-ov-pay-penalty"
            onclick="payOverstayDirectly('${escapeHtml(vPlate)}', '${targetBookingId}', ${penaltyAmt}, ${r.overstay_id || 'null'}, this)"
            title="Pay Overstay Penalty ₹${penaltyAmt.toFixed(0)} with Razorpay">
            <i class="fas fa-credit-card"></i> Pay ₹${penaltyAmt.toFixed(0)}
          </button>
          <button type="button" class="btn-ov-notify ${isNotified ? 'notified' : ''}" onclick="notifyOverstay('${escapeHtml(vPlate)}', '${targetBookingId}', this)" title="${isNotified ? 'Notified' : 'Notify Driver'}">
            <i class="${isNotified ? 'fas fa-check' : 'far fa-bell'}"></i>
          </button>
        </div>
      `;
    } else {
      actionHtml = `<button type="button" class="btn-ov-notify ${isNotified ? 'notified' : ''}" onclick="notifyOverstay('${escapeHtml(vPlate)}', '${targetBookingId}', this)">
        <i class="${isNotified ? 'fas fa-check' : 'far fa-bell'}"></i> ${isNotified ? 'Notified' : 'Notify'}
      </button>`;
    }

    return `
      <tr class="${rowClass}">
        <td class="ov-num-cell">${idx + 1}</td>
        <td>
          <div style="font-weight:700; color:#0f172a; line-height:1.2;">${escapeHtml(uName)}</div>
          <div style="font-size:11.5px; color:#64748b; font-weight:600; margin-top:2px;">${escapeHtml(vPlate)}</div>
        </td>
        <td>${vtypeDisplay}</td>
        <td style="color:#334155; font-weight:600;">${escapeHtml(lotName)}</td>
        <td style="text-align:center;">${slotDisplay}</td>
        <td style="color:#475569; font-size:12.5px;">${escapeHtml(vStart)}</td>
        <td style="color:#0f172a; font-weight:600; font-size:12.5px;">${escapeHtml(bookedEnd)}</td>
        <td style="color:#475569; font-size:12.5px;">${escapeHtml(selDuration)}</td>
        <td style="font-weight:600; color:#475569; font-size:12.5px;">${gracePeriod}</td>
        <td style="color:#d97706; font-weight:700; font-size:12.5px;">${escapeHtml(graceEnd)}</td>
        <td style="font-weight:700; color:${penaltyAmt > 0 ? '#dc2626' : '#64748b'}; font-size:12.5px;">${escapeHtml(overstayDur)}</td>
        <td>${statusBadgeHtml}</td>
        <td>${penaltyDisplay}</td>
        <td style="text-align:center;">${actionHtml}</td>
      </tr>
    `;
  }).join('');
}

function onOverstayFilterDropdownChange(filterValue) {
  currentOverstayFilter = filterValue;
  renderOverstayTable(activeOverstayRecords);
}

function filterOverstayTable(filter, btn) {
  currentOverstayFilter = filter;
  const sel = document.getElementById('overstayFilterDropdown');
  if (sel) sel.value = filter;
  document.querySelectorAll('.ov-filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderOverstayTable(activeOverstayRecords);
}

async function notifyOverstay(vehiclePlate, resId, btn) {
  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Notifying...';
    }

    const res = await fetch('/api/overstay/notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vehicle: vehiclePlate, reservation_id: resId })
    });
    const data = await res.json();

    if (res.ok && data.status === 'success') {
      showUserToast(`Notification sent to driver of ${vehiclePlate}!`, 'success');
      if (btn) {
        btn.innerHTML = '<i class="fas fa-check"></i> Notified';
        btn.classList.add('notified');
      }
      // Update topbar badges
      const topBadge = document.getElementById('ovTopBellBadge');
      if (topBadge) {
        const cur = parseInt(topBadge.textContent || '0', 10);
        topBadge.textContent = cur + 1;
      }
    } else {
      showUserToast(data.message || 'Failed to dispatch notification', 'error');
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="far fa-bell"></i> Notify';
      }
    }
  } catch (err) {
    console.error('Error notifying driver:', err);
    showUserToast('Failed to connect to notification service', 'error');
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="far fa-bell"></i> Notify';
    }
  }
}

window.payOverstayDirectly = function (vehiclePlate, bookingId, amount, overstayId, btn) {
  const penalty = parseFloat(amount) || 0.0;
  if (penalty <= 0) {
    showUserToast('No overstay penalty due.', 'info');
    return;
  }

  if (typeof window.openRazorpayModal === 'function') {
    window.openRazorpayModal({
      amount: penalty,
      title: 'Smart Parking AI',
      description: `Overstay Penalty Clearance (${vehiclePlate})`,
      bookingId: bookingId,
      type: 'overstay_penalty',
      onSuccess: async function (paymentResult) {
        if (btn) {
          btn.disabled = true;
          btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Clearing...';
        }

        try {
          const res = await fetch(`/api/reservations/${bookingId}/pay-penalty`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              payment_id: paymentResult.razorpay_payment_id,
              order_id: paymentResult.razorpay_order_id,
              signature: paymentResult.razorpay_signature,
              amount: penalty,
              method: paymentResult.method || 'Razorpay',
              overstay_id: overstayId
            })
          });
          const data = await res.json();
          if (res.ok && data.status === 'success') {
            showUserToast(`Penalty ₹${penalty.toFixed(2)} for ${vehiclePlate} cleared successfully via Razorpay!`, 'success');
            if (btn) {
              btn.disabled = true;
              btn.style.background = '#059669';
              btn.innerHTML = '<i class="fas fa-check-circle"></i> Paid';
            }
            setTimeout(() => {
              if (typeof loadOverstayDashboard === 'function') {
                loadOverstayDashboard(true);
              }
            }, 600);
          } else {
            showUserToast(data.message || 'Payment recorded but status update failed.', 'error');
            if (btn) {
              btn.disabled = false;
              btn.innerHTML = `<i class="fas fa-credit-card"></i> Pay ₹${penalty.toFixed(0)}`;
            }
          }
        } catch (err) {
          console.error(err);
          showUserToast('Network error updating penalty status.', 'error');
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fas fa-credit-card"></i> Pay ₹${penalty.toFixed(0)}`;
          }
        }
      },
      onFailure: function () {
        showUserToast('Penalty payment cancelled.', 'info');
      }
    });
  } else {
    showUserToast('Payment checkout system is unavailable.', 'error');
  }
};

function onOverstaySearch() {
  renderOverstayTable(activeOverstayRecords);
}

async function runManualOverstayCheck() {
  try {
    showUserToast('Scanning reservations for overstays...', 'info');
    const res = await fetch('/api/overstay/check', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      if (data.alerts_generated > 0) {
        showUserToast(`Detected ${data.alerts_generated} overstay violation(s)! Alert notifications sent.`, 'warning');
      } else {
        showUserToast('Overstay check completed. No new violations.', 'success');
      }
      loadOverstayDashboard();
    } else {
      showUserToast(data.message || 'Check failed', 'error');
    }
  } catch (err) {
    showUserToast('Error running overstay scan', 'error');
  }
}

async function completeOverstaySession(resId) {
  if (!confirm(`Complete parking session #${resId} and vacate the slot?`)) return;

  try {
    const res = await fetch('/api/overstay/complete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ reservation_id: resId })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message || 'Parking session completed successfully!', 'success');
      loadOverstayDashboard();
      if (typeof loadMyBookings === 'function') loadMyBookings();
      if (typeof loadUserDashboard === 'function') loadUserDashboard();
    } else {
      showUserToast(data.message || 'Failed to complete session', 'error');
    }
  } catch (err) {
    showUserToast('Error completing parking session', 'error');
  }
}

/* ==========================================================================
   MODULE 6: LIVE 2D PARKING LAYOUT & VISUAL SLOT SWAPPING ENGINE
   ========================================================================== */

let userActive2DBooking = null;
let activeExchangeListingsMap = new Map();
let selectedSwapSourceSlot = null;
let selectedSwapTargetSlot = null;
let isSwapProcessing = false;

function displaySlotNumber(num) {
  if (!num) return '';
  const s = String(num).trim();
  // If letter followed by single digit like A1..A9, format as A01..A09
  if (/^[A-Za-z]\d$/.test(s)) {
    return s[0].toUpperCase() + '0' + s.slice(1);
  }
  return s;
}

async function load2DLayout() {
  const lotSelect = document.getElementById('layoutLotSelect');
  const lotId = lotSelect ? parseInt(lotSelect.value || 1) : 1;
  const grid = document.getElementById('interactive2DGrid');
  if (!grid) return;

  const lotTitle = document.getElementById('layoutLotTitleDisplay') || document.querySelector('.layout-lot-title');
  if (lotTitle && lotSelect && lotSelect.options[lotSelect.selectedIndex]) {
    lotTitle.textContent = lotSelect.options[lotSelect.selectedIndex].text.toUpperCase();
  }

  // Ensure rowFilter options match the current facility
  syncRowFilterForLot(lotId);

  // Clear any existing swap preview on reload
  cancelVisualSlotSwap(false);

  grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Rendering 2D parking matrix...</div>';

  try {
    const uid = window.ACTIVE_USER_ID || '';

    // Parallel fetch: slots, user active booking, and marketplace listings
    const [slotsRes, userBookingRes, browseRes] = await Promise.all([
      fetch(`/api/slots?lot_id=${lotId}`),
      fetch(`/api/exchange/user-active-booking${uid ? `?user_id=${uid}` : ''}`),
      fetch(`/api/exchange/browse${uid ? `?user_id=${uid}` : ''}`)
    ]);

    const slotsData = await slotsRes.json();
    const userBookingData = await userBookingRes.json();
    const browseData = await browseRes.json();

    // 1. Process User Booking
    userActive2DBooking = null;
    selectedSwapSourceSlot = null;
    if (userBookingData.status === 'success' && userBookingData.has_booking) {
      const allB = userBookingData.all_bookings || [userBookingData.booking];
      // Find booking in this specific lot if possible, else active booking
      const matchInLot = allB.find(b => parseInt(b.lot_id) === lotId);
      userActive2DBooking = matchInLot || userBookingData.booking;
    }

    // 2. Process Marketplace Listings
    activeExchangeListingsMap.clear();
    if (browseData.status === 'success') {
      const listings = browseData.listings || browseData.opportunities || [];
      listings.forEach(l => {
        activeExchangeListingsMap.set(parseInt(l.slot_id), l);
      });
    }

    // 3. Update Header Swap Bar
    updateLayoutSwapHeaderBar(lotId);

    // 4. Render slots
    if (slotsData.status === 'success') {
      current2DSlots = slotsData.slots || [];
      filter2DSlotsByRow();
    } else {
      grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; color:#ef4444;">No slots found for this facility.</div>';
    }
  } catch (err) {
    console.error('Error loading 2D layout:', err);
    grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; color:#ef4444;">Failed to load 2D layout.</div>';
  }
}

function updateLayoutSwapHeaderBar(currentLotId) {
  const headerBar = document.getElementById('layoutSwapHeaderBar');
  const slotDisplay = document.getElementById('swapUserSlotDisplay');
  const subtext = document.getElementById('swapUserSlotSubtext');
  const userIcon = document.getElementById('layoutSwapUserIcon');
  const userLabel = document.getElementById('layoutSwapUserLabel');
  if (!headerBar || !slotDisplay) return;

  const isBike = userActive2DBooking && /bike|scooter|motorcycle|two-wheeler/i.test(userActive2DBooking.vehicle_type || '');
  if (userIcon) {
    userIcon.className = isBike ? 'fas fa-motorcycle' : 'fas fa-car-side';
  }
  if (userLabel) {
    userLabel.textContent = isBike ? 'YOUR BIKE SLOT:' : 'YOUR SLOT:';
  }

  if (userActive2DBooking && parseInt(userActive2DBooking.lot_id) === currentLotId) {
    selectedSwapSourceSlot = {
      slot_id: parseInt(userActive2DBooking.slot_id),
      slot_number: userActive2DBooking.slot_number,
      reservation_id: userActive2DBooking.reservation_id
    };
    slotDisplay.textContent = displaySlotNumber(userActive2DBooking.slot_number);
    if (subtext) {
      subtext.innerHTML = `Your ${isBike ? 'bike/scooter' : 'car'} slot <strong>${displaySlotNumber(userActive2DBooking.slot_number)}</strong> is highlighted below with <span class="legend-dot-you">YOU</span>. Click another slot or drag to visually swap!`;
    }
    headerBar.style.display = 'flex';
  } else if (userActive2DBooking) {
    headerBar.style.display = 'flex';
    slotDisplay.textContent = `${displaySlotNumber(userActive2DBooking.slot_number)} (${userActive2DBooking.lot_name || 'Other Lot'})`;
    if (subtext) {
      subtext.innerHTML = `You have an active booking in <strong>${escapeHtml(userActive2DBooking.lot_name)}</strong>. <a href="javascript:void(0)" onclick="viewLotIn2DLayout(${userActive2DBooking.lot_id})" style="color:#38bdf8; font-weight:700; text-decoration:underline;">Switch Facility to Visual Swap</a>`;
    }
  } else {
    headerBar.style.display = 'none';
  }
}

function get2DFacilityType(lotId, lotSelect) {
  const optText = (lotSelect && lotSelect.options[lotSelect.selectedIndex]) ? lotSelect.options[lotSelect.selectedIndex].text : '';
  const lotName = optText.split('•')[0].trim().toLowerCase();

  if (lotId === 1 || lotName.includes('institution')) {
    return 'institution';
  }
  if (lotId === 4 || lotName === 'city parking' || lotName.startsWith('city parking')) {
    return 'city';
  }
  // Public places (lotId === 3), Mall (lotId === 2), or any other
  return 'general';
}

function syncRowFilterForLot(lotId) {
  const lotSelect = document.getElementById('layoutLotSelect');
  const rowFilter = document.getElementById('layoutRowFilter');
  if (!rowFilter) return;

  const fType = get2DFacilityType(lotId, lotSelect);
  const hasR = !!rowFilter.querySelector('option[value="R"]');
  const hasA = !!rowFilter.querySelector('option[value="A"]');

  if (fType === 'institution') {
    if (!hasR) {
      rowFilter.innerHTML = `
        <option value="ALL">All Slots</option>
        <option value="R" selected>R-Bay (R1-R32)</option>
        <option value="S">S-Bay (S1-S11)</option>
      `;
    }
  } else if (fType === 'city') {
    if (!hasA) {
      rowFilter.innerHTML = `
        <option value="ALL">All Slots</option>
        <option value="A" selected>Row A (A1-A12)</option>
        <option value="B">Row B (B1-B12)</option>
        <option value="C">Row C (C1-C13)</option>
        <option value="D">Row D (D1-D13)</option>
      `;
    }
  } else {
    // For Public places, Mall, etc. — just keep "All Slots" and remove Row A, B, C, D
    if (hasR || hasA || rowFilter.options.length !== 1 || rowFilter.value !== 'ALL') {
      rowFilter.innerHTML = `<option value="ALL" selected>All Slots</option>`;
    }
  }
}

function onFacilityChange2D() {
  const lotSelect = document.getElementById('layoutLotSelect');
  const rowFilter = document.getElementById('layoutRowFilter');
  const lotId = lotSelect ? parseInt(lotSelect.value || 1) : 1;

  if (rowFilter) {
    const fType = get2DFacilityType(lotId, lotSelect);

    if (fType === 'institution') {
      rowFilter.innerHTML = `
        <option value="ALL">All Slots</option>
        <option value="R" selected>R-Bay (R1-R32)</option>
        <option value="S">S-Bay (S1-S11)</option>
      `;
    } else if (fType === 'city') {
      rowFilter.innerHTML = `
        <option value="ALL">All Slots</option>
        <option value="A" selected>Row A (A1-A12)</option>
        <option value="B">Row B (B1-B12)</option>
        <option value="C">Row C (C1-C13)</option>
        <option value="D">Row D (D1-D13)</option>
      `;
    } else {
      // Public places, Mall, etc. — keep only All Slots
      rowFilter.innerHTML = `<option value="ALL" selected>All Slots</option>`;
    }
  }

  cancelVisualSlotSwap(false);
  load2DLayout();
}

function filter2DSlotsByRow() {
  const rowFilter = document.getElementById('layoutRowFilter');
  const filterVal = rowFilter ? rowFilter.value : 'ALL';

  let filtered = current2DSlots;
  if (filterVal && filterVal !== 'ALL') {
    filtered = current2DSlots.filter(s => {
      const snum = (s.slot_number || '').toUpperCase();
      return snum.startsWith(filterVal);
    });
  }

  render2DInteractiveMatrix(filtered);
}

function render2DInteractiveMatrix(slots) {
  const grid = document.getElementById('interactive2DGrid');
  if (!grid) return;

  if (!slots || slots.length === 0) {
    grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; color:#94a3b8; padding:30px;">No slots found matching this filter.</div>';
    return;
  }

  // Support up to 48 slots in viewport or full row
  const displaySlots = slots.length > 48 ? slots.slice(0, 48) : slots;

  const lotSelect = document.getElementById('layoutLotSelect');
  const currentLotId = lotSelect ? parseInt(lotSelect.value || 1) : 1;

  grid.innerHTML = displaySlots.map(s => {
    const slotId = parseInt(s.slot_id);
    const slotNumRaw = s.slot_number || '';
    const slotNumDisp = displaySlotNumber(slotNumRaw);
    const st = (s.status || 'available').toLowerCase();

    // Check if this is the logged-in user's currently assigned slot
    const isUserSlot = !!(
      userActive2DBooking &&
      parseInt(userActive2DBooking.lot_id) === currentLotId &&
      (parseInt(userActive2DBooking.slot_id) === slotId || userActive2DBooking.slot_number === slotNumRaw)
    );

    // Check if another driver listed this slot on exchange marketplace
    const listing = activeExchangeListingsMap.get(slotId);
    const hasMarketplaceListing = !!listing;

    // Check if eligible for visual swap
    const isEligible = !isUserSlot && (st === 'available' || hasMarketplaceListing);

    const isUserBike = !!(userActive2DBooking && /bike|scooter|motorcycle|two-wheeler/i.test(userActive2DBooking.vehicle_type || ''));
    const isSlotBike = !!(
      (s.vehicle_type && /bike|scooter|motorcycle|two-wheeler/i.test(s.vehicle_type)) ||
      (s.slot_type && /bike|scooter|motorcycle|two-wheeler/i.test(s.slot_type)) ||
      (s.slot_number && /^B\d+/i.test(s.slot_number) && (!s.vehicle_type || !s.vehicle_type.toLowerCase().includes('car')))
    );

    let statusClass = st;
    let titleText = `Slot ${slotNumDisp}: Available for reservation or swap`;
    let visualHtml = '';

    if (isUserSlot) {
      statusClass = 'is-user-slot';
      titleText = `Slot ${slotNumDisp}: YOUR Currently Assigned ${isUserBike ? 'Bike' : 'Car'} Slot. Click or drag to swap!`;
      const vehicleImg = isUserBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';
      const vehicleAlt = isUserBike ? 'Bike Parked' : 'Car Parked';
      visualHtml = `
        <div class="slot-box-vehicle-wrap ${isUserBike ? 'slot-box-bike' : 'slot-box-car'}">
          <img src="${vehicleImg}" alt="${vehicleAlt}" class="slot-box-vehicle-img" />
        </div>
        <div class="slot-you-badge"><i class="${isUserBike ? 'fas fa-motorcycle' : 'fas fa-user-check'}"></i> YOU</div>
      `;
    } else if (hasMarketplaceListing) {
      statusClass = 'marketplace-offer';
      titleText = `Slot ${slotNumDisp}: Listed for exchange by ${escapeHtml(listing.owner_name || 'Driver')}`;
      const listingIsBike = listing.vehicle_type && /bike|scooter|motorcycle|two-wheeler/i.test(listing.vehicle_type);
      const vehicleImg = listingIsBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';
      visualHtml = `
        <div class="slot-box-vehicle-wrap ${listingIsBike ? 'slot-box-bike' : 'slot-box-car'}">
          <img src="${vehicleImg}" alt="Listed Vehicle" class="slot-box-vehicle-img" />
        </div>
        <div class="slot-marketplace-tag"><i class="fas fa-handshake"></i> SWAP</div>
      `;
    } else if (st === 'overstayed') {
      statusClass = 'overstayed';
      titleText = `Slot ${slotNumDisp}: Overstayed ${isSlotBike ? 'bike' : 'vehicle'} (Ineligible for swap)`;
      const vehicleImg = isSlotBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';
      visualHtml = `
        <div class="slot-box-vehicle-wrap ${isSlotBike ? 'slot-box-bike' : 'slot-box-car'}">
          <img src="${vehicleImg}" alt="Overstayed" class="slot-box-vehicle-img" />
        </div>
        <div class="slot-box-status-tag overstayed">⚠️ OVERSTAY</div>
      `;
    } else if (st === 'occupied') {
      statusClass = 'occupied';
      titleText = `Slot ${slotNumDisp}: Occupied by another ${isSlotBike ? 'bike' : 'vehicle'} (Ineligible for swap)`;
      const vehicleImg = isSlotBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';
      visualHtml = `
        <div class="slot-box-vehicle-wrap ${isSlotBike ? 'slot-box-bike' : 'slot-box-car'}">
          <img src="${vehicleImg}" alt="Occupied" class="slot-box-vehicle-img" />
        </div>
        <div class="slot-box-status-tag occupied">OCCUPIED</div>
      `;
    } else if (st === 'reserved') {
      statusClass = 'reserved';
      titleText = `Slot ${slotNumDisp}: Reserved for incoming ${isSlotBike ? 'bike' : 'driver'} (Ineligible for swap)`;
      const vehicleImg = isSlotBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';
      visualHtml = `
        <div class="slot-box-vehicle-wrap ${isSlotBike ? 'slot-box-bike' : 'slot-box-car'}">
          <img src="${vehicleImg}" alt="Reserved" class="slot-box-vehicle-img" />
        </div>
        <div class="slot-box-status-tag reserved">RESERVED</div>
      `;
    } else if (isEligible) {
      statusClass = 'available eligible-exchange';
      visualHtml = `
        <div class="slot-box-empty-bay"><i class="fas fa-parking"></i></div>
        <div class="slot-exchange-tag">ELIGIBLE</div>
      `;
    } else {
      visualHtml = `
        <div class="slot-box-empty-bay"><i class="fas fa-parking"></i></div>
        <div class="slot-available-tag">AVAILABLE</div>
      `;
    }

    // Active selection highlights
    const isSelectedSource = selectedSwapSourceSlot && selectedSwapSourceSlot.slot_id === slotId;
    const isSelectedTarget = selectedSwapTargetSlot && selectedSwapTargetSlot.slot_id === slotId;
    if (isSelectedSource) statusClass += ' selected-source';
    if (isSelectedTarget) statusClass += ' selected-target';

    // Drag and Drop attributes
    const dragAttr = isUserSlot ? `draggable="true" ondragstart="handleSlotDragStart(event, ${slotId}, '${escapeHtml(slotNumRaw)}')"` : '';
    const dropAttr = isEligible ? `ondragover="handleSlotDragOver(event)" ondragleave="handleSlotDragLeave(event)" ondrop="handleSlotDrop(event, ${slotId}, '${escapeHtml(slotNumRaw)}')"` : '';

    return `
      <div class="slot-box-2d ${statusClass}" 
           id="slotBox2D_${slotId}"
           ${dragAttr}
           ${dropAttr}
           onclick="handleSlot2DMatrixClick(${slotId}, '${escapeHtml(slotNumRaw)}', '${st}', ${isUserSlot}, ${isEligible})" 
           title="${titleText}">
        <div class="slot-box-name">${escapeHtml(slotNumDisp)}</div>
        ${visualHtml}
      </div>
    `;
  }).join('');

  // Redraw SVG arrow if a target is actively selected
  if (selectedSwapSourceSlot && selectedSwapTargetSlot) {
    setTimeout(drawSwapSvgConnector, 60);
  }
}

function handleSlot2DMatrixClick(slotId, slotNumber, status, isUserSlot, isEligible) {
  const lotSelect = document.getElementById('layoutLotSelect');
  const currentLotId = lotSelect ? parseInt(lotSelect.value || 1) : 1;
  const slotDisp = displaySlotNumber(slotNumber);

  // Case 1: User clicks their own slot
  if (isUserSlot) {
    selectedSwapSourceSlot = {
      slot_id: slotId,
      slot_number: slotNumber,
      reservation_id: userActive2DBooking ? userActive2DBooking.reservation_id : null
    };
    // Re-render highlight
    document.querySelectorAll('.slot-box-2d').forEach(el => el.classList.remove('selected-source'));
    const sourceEl = document.getElementById(`slotBox2D_${slotId}`);
    if (sourceEl) sourceEl.classList.add('selected-source');

    showUserToast(`Selected your slot ${slotDisp} (YOU). Now click any eligible slot (🟢 Available) to preview the swap!`, 'info');
    if (selectedSwapTargetSlot) {
      renderVisualSwapPreview();
    }
    return;
  }

  // Case 2: User has an active booking in this lot and clicks an eligible slot
  if (userActive2DBooking && parseInt(userActive2DBooking.lot_id) === currentLotId && isEligible) {
    // Auto-select source if not already explicitly selected
    if (!selectedSwapSourceSlot) {
      selectedSwapSourceSlot = {
        slot_id: parseInt(userActive2DBooking.slot_id),
        slot_number: userActive2DBooking.slot_number,
        reservation_id: userActive2DBooking.reservation_id
      };
    }

    selectedSwapTargetSlot = {
      slot_id: slotId,
      slot_number: slotNumber,
      status: status
    };

    renderVisualSwapPreview();
    return;
  }

  // Case 3: User clicks an ineligible slot (occupied or reserved by another driver)
  if (!isEligible && status !== 'available') {
    showUserToast(`Slot ${slotDisp} is currently ${status.toUpperCase()} and ineligible for swapping. Please select an eligible (🟢) slot.`, 'error');
    return;
  }

  // Case 4: User has no booking in this lot, clicks an available slot -> Quick Book
  if (status === 'available') {
    handleSlot2DClick(slotId, slotNumber, status);
  }
}

// Drag and Drop Handling
function handleSlotDragStart(event, slotId, slotNumber) {
  selectedSwapSourceSlot = {
    slot_id: slotId,
    slot_number: slotNumber,
    reservation_id: userActive2DBooking ? userActive2DBooking.reservation_id : null
  };
  event.dataTransfer.setData('text/plain', JSON.stringify(selectedSwapSourceSlot));
  event.target.classList.add('is-dragging');
}

function handleSlotDragOver(event) {
  event.preventDefault();
  const el = event.currentTarget;
  if (!el.classList.contains('drag-over')) {
    el.classList.add('drag-over');
  }
}

function handleSlotDragLeave(event) {
  event.currentTarget.classList.remove('drag-over');
}

function handleSlotDrop(event, targetSlotId, targetSlotNumber) {
  event.preventDefault();
  event.currentTarget.classList.remove('drag-over');

  document.querySelectorAll('.is-dragging').forEach(el => el.classList.remove('is-dragging'));

  if (!selectedSwapSourceSlot && userActive2DBooking) {
    selectedSwapSourceSlot = {
      slot_id: parseInt(userActive2DBooking.slot_id),
      slot_number: userActive2DBooking.slot_number,
      reservation_id: userActive2DBooking.reservation_id
    };
  }

  if (selectedSwapSourceSlot && selectedSwapSourceSlot.slot_id === targetSlotId) {
    showUserToast('Cannot swap a slot with itself!', 'error');
    return;
  }

  selectedSwapTargetSlot = {
    slot_id: targetSlotId,
    slot_number: targetSlotNumber,
    status: 'available'
  };

  renderVisualSwapPreview();
}

function renderVisualSwapPreview() {
  const container = document.getElementById('visualSwapCardContainer');
  if (!container || !selectedSwapSourceSlot || !selectedSwapTargetSlot) return;

  const srcDisp = displaySlotNumber(selectedSwapSourceSlot.slot_number);
  const tgtDisp = displaySlotNumber(selectedSwapTargetSlot.slot_number);

  // Apply active selection CSS classes to slot cards in grid
  document.querySelectorAll('.slot-box-2d').forEach(el => {
    el.classList.remove('selected-source', 'selected-target');
  });
  const srcEl = document.getElementById(`slotBox2D_${selectedSwapSourceSlot.slot_id}`);
  const tgtEl = document.getElementById(`slotBox2D_${selectedSwapTargetSlot.slot_id}`);
  if (srcEl) srcEl.classList.add('selected-source');
  if (tgtEl) tgtEl.classList.add('selected-target');

  const isBike = userActive2DBooking && /bike|scooter|motorcycle|two-wheeler/i.test(userActive2DBooking.vehicle_type || '');
  const vehicleImg = isBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';
  const vehicleLabel = isBike ? 'Bike / Scooter' : 'Car';
  const vehicleBadge = isBike ? '🏍️ BIKE' : '🚗 CAR';

  container.innerHTML = `
    <div class="swap-preview-card">
      <div class="swap-preview-header">
        <h4><i class="fas fa-arrows-rotate"></i> Visual Slot Swap Preview — ${vehicleLabel}</h4>
        <span style="font-size:12px; color:#94a3b8; font-weight:700;">CONFIRMATION REQUIRED</span>
      </div>

      <div class="swap-slots-row">
        <!-- Current Slot (Source) -->
        <div class="swap-slot-pill current">
          <span class="pill-label">CURRENT SLOT</span>
          <div style="display:flex; align-items:center; justify-content:center; gap:8px; margin:4px 0;">
            <img src="${vehicleImg}" style="height:36px; width:18px; object-fit:contain;" alt="${vehicleLabel}">
            <strong class="pill-slot-num">${escapeHtml(srcDisp)}</strong>
          </div>
          <span class="pill-badge you"><i class="${isBike ? 'fas fa-motorcycle' : 'fas fa-user-check'}"></i> ${vehicleBadge} • YOU</span>
        </div>

        <!-- Animated Connector Arrows -->
        <div class="swap-animated-center">
          <div class="swap-arrow-circle">
            <i class="fas fa-arrow-right-arrow-left"></i>
          </div>
          <span style="font-size:12px; font-weight:800; color:#38bdf8; letter-spacing:0.5px; margin-top:4px;">
            ${escapeHtml(srcDisp)} ⇄ ${escapeHtml(tgtDisp)}
          </span>
          <span style="font-size:10px; font-weight:700; color:#10b981; letter-spacing:0.5px;">SWAP ${isBike ? 'BIKE' : 'CAR'}</span>
        </div>

        <!-- New Slot (Target) -->
        <div class="swap-slot-pill target">
          <span class="pill-label">NEW ASSIGNED SLOT</span>
          <div style="display:flex; align-items:center; justify-content:center; gap:8px; margin:4px 0;">
            <img src="${vehicleImg}" style="height:36px; width:18px; object-fit:contain; opacity:0.65; filter:drop-shadow(0 0 6px #10b981);" alt="${vehicleLabel}">
            <strong class="pill-slot-num">${escapeHtml(tgtDisp)}</strong>
          </div>
          <span class="pill-badge new"><i class="fas fa-sparkles"></i> TARGET</span>
        </div>
      </div>

      <p style="text-align:center; font-size:12.5px; color:#cbd5e1; margin:0 0 14px;">
        Swapping will reassign your <strong>${vehicleLabel}</strong> to <strong>Slot ${escapeHtml(tgtDisp)}</strong> and update the database atomically.
      </p>

      <div class="swap-action-buttons">
        <button class="btn-confirm-swap" id="btnConfirmVisualSwap" onclick="confirmVisualSlotSwap()">
          <i class="fas fa-check-circle"></i> Confirm Swap (${escapeHtml(srcDisp)} ⇄ ${escapeHtml(tgtDisp)})
        </button>
        <button class="btn-cancel-swap" onclick="cancelVisualSlotSwap(true)">
          <i class="fas fa-times-circle"></i> Cancel Swap
        </button>
      </div>
    </div>
  `;

  container.style.display = 'block';

  // Smooth scroll down to preview card
  container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  // Draw connecting SVG line between source and target slots
  setTimeout(drawSwapSvgConnector, 80);
}

function drawSwapSvgConnector() {
  const svg = document.getElementById('swapSvgOverlay');
  const container = document.getElementById('layout2DContainer');
  if (!svg || !container || !selectedSwapSourceSlot || !selectedSwapTargetSlot) {
    if (svg) svg.innerHTML = '';
    return;
  }

  const srcEl = document.getElementById(`slotBox2D_${selectedSwapSourceSlot.slot_id}`);
  const tgtEl = document.getElementById(`slotBox2D_${selectedSwapTargetSlot.slot_id}`);
  if (!srcEl || !tgtEl) {
    svg.innerHTML = '';
    return;
  }

  const cRect = container.getBoundingClientRect();
  const sRect = srcEl.getBoundingClientRect();
  const tRect = tgtEl.getBoundingClientRect();

  const x1 = sRect.left - cRect.left + sRect.width / 2;
  const y1 = sRect.top - cRect.top + sRect.height / 2;
  const x2 = tRect.left - cRect.left + tRect.width / 2;
  const y2 = tRect.top - cRect.top + tRect.height / 2;

  const dx = x2 - x1;
  const dy = y2 - y1;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2 - 28; // Curve upward

  const pathData = `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`;

  const isBike = userActive2DBooking && /bike|scooter|motorcycle|two-wheeler/i.test(userActive2DBooking.vehicle_type || '');
  const vehicleImg = isBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';

  svg.innerHTML = `
    <defs>
      <linearGradient id="swapLineGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#38bdf8" />
        <stop offset="100%" stop-color="#10b981" />
      </linearGradient>
      <filter id="swapGlow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="3" result="glow" />
        <feMerge>
          <feMergeNode in="glow" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
    <!-- Background Glow Line -->
    <path d="${pathData}" fill="none" stroke="#38bdf8" stroke-width="6" opacity="0.4" filter="url(#swapGlow)" />
    <!-- Foreground Animated Dashed Line -->
    <path id="swapTrajectory" d="${pathData}" fill="none" stroke="url(#swapLineGrad)" stroke-width="3" stroke-dasharray="8 5">
      <animate attributeName="stroke-dashoffset" from="100" to="0" dur="2s" repeatCount="indefinite" />
    </path>
    <!-- Vehicle (Bike or Car) Animated Along Swap Path -->
    <g>
      <image href="${vehicleImg}" width="22" height="42" x="-11" y="-21" opacity="0.95" style="filter:drop-shadow(0 0 6px rgba(56, 189, 248, 0.85));">
        <animateMotion path="${pathData}" dur="2.2s" repeatCount="indefinite" rotate="auto" />
      </image>
    </g>
    <!-- Center Swap Icon Badge -->
    <circle cx="${mx}" cy="${my}" r="16" fill="#0f172a" stroke="#38bdf8" stroke-width="2" />
    <text x="${mx}" y="${my + 4}" fill="#38bdf8" font-size="12" font-weight="bold" text-anchor="middle" font-family="sans-serif">⇄</text>
  `;
}

// Window resize updates SVG connector line coordinates
window.addEventListener('resize', () => {
  if (selectedSwapSourceSlot && selectedSwapTargetSlot) {
    drawSwapSvgConnector();
  }
});

async function confirmVisualSlotSwap() {
  if (isSwapProcessing) return;
  if (!selectedSwapSourceSlot || !selectedSwapTargetSlot) {
    showUserToast('Missing slot swap parameters.', 'error');
    return;
  }

  const btnConfirm = document.getElementById('btnConfirmVisualSwap');
  if (btnConfirm) {
    btnConfirm.disabled = true;
    btnConfirm.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Swapping Slots...';
  }
  isSwapProcessing = true;

  const srcDisp = displaySlotNumber(selectedSwapSourceSlot.slot_number);
  const tgtDisp = displaySlotNumber(selectedSwapTargetSlot.slot_number);

  try {
    const payload = {
      user_id: window.ACTIVE_USER_ID,
      reservation_id: selectedSwapSourceSlot.reservation_id || (userActive2DBooking ? userActive2DBooking.reservation_id : null),
      source_slot_id: selectedSwapSourceSlot.slot_id,
      target_slot_id: selectedSwapTargetSlot.slot_id
    };

    const res = await fetch('/api/exchange/visual-swap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok && data.status === 'success') {
      showUserToast(`🎉 Slot Swap Completed! You now hold Slot ${tgtDisp} (swapped from ${srcDisp}).`, 'success');

      // Clear preview card and SVG
      cancelVisualSlotSwap(false);

      // Re-load 2D layout immediately so the new slot is reflected as [YOU]
      await load2DLayout();

      // Refresh other app tabs in background
      loadUserDashboard();
      loadUserNotifications();
      pollNotificationBadges();
      if (typeof loadSlotExchangeTab === 'function') loadSlotExchangeTab();
      if (typeof filterMyBookings === 'function') filterMyBookings('all');
    } else {
      showUserToast(data.message || 'Slot swap failed.', 'error');
      if (btnConfirm) {
        btnConfirm.disabled = false;
        btnConfirm.innerHTML = `<i class="fas fa-check-circle"></i> Confirm Swap (${srcDisp} ⇄ ${tgtDisp})`;
      }
    }
  } catch (err) {
    console.error('Error confirming swap:', err);
    showUserToast('Network error while processing slot swap.', 'error');
    if (btnConfirm) {
      btnConfirm.disabled = false;
      btnConfirm.innerHTML = `<i class="fas fa-check-circle"></i> Confirm Swap (${srcDisp} ⇄ ${tgtDisp})`;
    }
  } finally {
    isSwapProcessing = false;
  }
}

function cancelVisualSlotSwap(userTriggered = true) {
  selectedSwapTargetSlot = null;

  const container = document.getElementById('visualSwapCardContainer');
  if (container) {
    container.style.display = 'none';
    container.innerHTML = '';
  }

  const svg = document.getElementById('swapSvgOverlay');
  if (svg) svg.innerHTML = '';

  document.querySelectorAll('.slot-box-2d').forEach(el => {
    el.classList.remove('selected-target');
  });

  if (userTriggered) {
    showUserToast('Visual slot swap cancelled.', 'info');
  }
}

function handleSlot2DClick(slotId, slotNumber, status) {
  if (status !== 'available') {
    showUserToast(`Slot ${displaySlotNumber(slotNumber)} is currently ${status.toUpperCase()} and cannot be booked.`, 'error');
    return;
  }

  selectedSlotForBooking = slotId;
  showUserToast(`Selected 🟢 Slot ${displaySlotNumber(slotNumber)}. Opening booking form...`, 'success');
  switchUserTab('booking');
  setTimeout(() => {
    const slotSelect = document.getElementById('bookingSlotSelect');
    if (slotSelect) slotSelect.value = slotId;
  }, 250);
}

function viewLotIn2DLayout(lotId) {
  switchUserTab('layout');
  setTimeout(() => {
    const sel = document.getElementById('layoutLotSelect');
    if (sel) {
      sel.value = lotId;
      onFacilityChange2D();
    }
  }, 200);
}

function open2DVisualSwapForBooking(lotId, slotId, slotNumber) {
  switchUserTab('layout');
  setTimeout(() => {
    const sel = document.getElementById('layoutLotSelect');
    if (sel) {
      sel.value = lotId;
      onFacilityChange2D();
    }
    showUserToast(`Visual Swap: Your Slot ${displaySlotNumber(slotNumber)} is highlighted with [YOU]. Select any eligible slot to swap!`, 'info');
  }, 250);
}

/* ==========================================================================
   MODULE 7: SLOT EXCHANGE MARKETPLACE
   ========================================================================== */

async function loadSlotExchangeTab() {
  loadUserExchangeListing();
  browseExchangeListings();
  loadUserExchangeRequests();
  loadUserSentExchangeRequests();
}

async function loadUserExchangeListing() {
  const container = document.getElementById('userActiveListingBox');
  if (!container) return;

  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/exchange/user-active-booking${uid ? `?user_id=${uid}` : ''}`);
    const data = await res.json();
    if (data.status === 'success' && data.has_booking) {
      const b = data.booking;
      const slotDisp = displaySlotNumber(b.slot_number);
      if (data.is_offered) {
        container.innerHTML = `
          <div style="background:#f0fdf4; border:1px solid #86efac; border-radius:8px; padding:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
              <div>
                <span style="font-size:11px; text-transform:uppercase; font-weight:700; color:#15803d;">Your Slot Listed for Exchange</span>
                <h4 style="font-size:18px; font-weight:800; color:#0f172a; margin:2px 0;">Slot ${escapeHtml(slotDisp)} (${escapeHtml(b.lot_name)})</h4>
                <p style="font-size:12px; color:#64748b; margin:0;">Date: ${escapeHtml(b.date)} &bull; ${escapeHtml(b.start_time)} – ${escapeHtml(b.end_time)}</p>
              </div>
              <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                <button class="btn-user btn-user-primary btn-user-sm" onclick="open2DVisualSwapForBooking(${b.lot_id}, ${b.slot_id}, '${escapeHtml(b.slot_number)}')">
                  <i class="fas fa-table-cells"></i> Visual Swap in 2D
                </button>
                <button class="btn-user btn-user-secondary btn-user-sm" onclick="simulateIncomingExchangeRequest()" title="Simulate another driver proposing a swap for your slot">
                  <i class="fas fa-paper-plane"></i> Simulate Incoming Swap Request
                </button>
                <button class="btn-user btn-user-danger btn-user-sm" onclick="cancelSlotExchangeOffer('${b.reservation_id || b.booking_id}')">
                  <i class="fas fa-ban"></i> Withdraw Offer
                </button>
              </div>
            </div>
          </div>
        `;
      } else {
        container.innerHTML = `
          <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
            <div>
              <span style="font-size:11px; text-transform:uppercase; font-weight:700; color:#64748b;">Your Confirmed Booking</span>
              <h4 style="font-size:16px; font-weight:700; color:#0f172a; margin:2px 0;">Slot ${escapeHtml(slotDisp)} (${escapeHtml(b.lot_name)})</h4>
              <p style="font-size:12px; color:#64748b; margin:0;">Date: ${escapeHtml(b.date)} &bull; ${escapeHtml(b.start_time)} – ${escapeHtml(b.end_time)}</p>
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
              <button class="btn-user btn-user-secondary btn-user-sm" onclick="open2DVisualSwapForBooking(${b.lot_id}, ${b.slot_id}, '${escapeHtml(b.slot_number)}')">
                <i class="fas fa-table-cells"></i> Visual Swap in 2D
              </button>
              <button class="btn-user btn-user-primary btn-user-sm" onclick="offerBookingForExchange('${b.reservation_id || b.booking_id}')">
                <i class="fas fa-handshake"></i> Offer for Exchange
              </button>
            </div>
          </div>
        `;
      }
    } else {
      container.innerHTML = `
        <div style="background:#f8fafc; border:1.5px dashed #cbd5e1; border-radius:8px; padding:16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
          <div>
            <div style="font-weight:700; color:#475569; font-size:13.5px;"><i class="fas fa-calendar-xmark" style="color:#94a3b8; margin-right:6px;"></i> No Active Confirmed Bookings</div>
            <p style="font-size:12px; color:#94a3b8; margin:2px 0 0;">You need an active booking to participate in slot swapping. Seed a test booking instantly or book one in the booking tab.</p>
          </div>
          <button class="btn-user btn-user-primary btn-user-sm" onclick="quickSeedUserBookingForExchange()">
            <i class="fas fa-magic"></i> Quick Seed Test Booking
          </button>
        </div>
      `;
    }
  } catch (err) {
    container.innerHTML = '<div style="color:#ef4444; font-size:13px;">Failed to load booking.</div>';
  }
}

async function offerBookingForExchange(resId) {
  try {
    const res = await fetch('/api/exchange/offer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        user_id: window.ACTIVE_USER_ID,
        reservation_id: parseInt(resId),
        notes: 'Looking to swap for a convenient slot.'
      })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      loadSlotExchangeTab();
      loadUserNotifications();
      pollNotificationBadges();
    } else {
      showUserToast(data.message || 'Failed to list slot', 'error');
    }
  } catch (err) {
    showUserToast('Error offering slot', 'error');
  }
}

async function cancelSlotExchangeOffer(resId) {
  if (!confirm('Withdraw your slot from the exchange marketplace?')) return;
  try {
    const res = await fetch('/api/exchange/cancel-offer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        user_id: window.ACTIVE_USER_ID,
        reservation_id: parseInt(resId)
      })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      loadSlotExchangeTab();
      loadUserNotifications();
      pollNotificationBadges();
    } else {
      showUserToast(data.message || 'Failed to withdraw offer', 'error');
    }
  } catch (err) {
    showUserToast('Error cancelling offer', 'error');
  }
}

async function browseExchangeListings() {
  const container = document.getElementById('browseExchangeMarketplace');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center; padding:20px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Browsing marketplace...</div>';

  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/exchange/browse${uid ? `?user_id=${uid}` : ''}`);
    const data = await res.json();
    if (data.status === 'success') {
      const listings = data.listings || data.opportunities || [];
      if (listings.length === 0) {
        container.innerHTML = `
          <div style="text-align:center; padding:28px 16px; background:#f8fafc; border:1.5px dashed #cbd5e1; border-radius:10px;">
            <i class="fas fa-handshake-slash fa-2x" style="color:#94a3b8; margin-bottom:8px;"></i>
            <div style="color:#475569; font-size:14px; font-weight:700; margin-bottom:4px;">No other drivers have listed slots for exchange right now.</div>
            <p style="color:#94a3b8; font-size:12px; max-width:460px; margin:0 auto 12px;">When other drivers list their reserved slots, they will appear here with rule-based compatibility match scores. You can also generate a swap offer to test swapping instantly.</p>
            <button class="btn-user btn-user-secondary btn-user-sm" onclick="seedDemoExchangeSlot()">
              <i class="fas fa-wand-magic-sparkles"></i> Generate Swap Offer
            </button>
          </div>
        `;
        return;
      }

      container.innerHTML = listings.map(l => `
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:16px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">
          <div>
            <div style="display:flex; align-items:center; gap:8px;">
              <strong style="font-size:16px; color:#0f172a;">Slot ${escapeHtml(l.slot_number)}</strong>
              <span style="font-size:11px; background:#e0f2fe; color:#0284c7; padding:2px 8px; border-radius:4px; font-weight:700;">${escapeHtml(l.slot_type)}</span>
              ${l.match_score ? `<span style="font-size:11px; background:#f0fdf4; color:#16a34a; padding:2px 8px; border-radius:4px; font-weight:700;"><i class="fas fa-bolt"></i> ${l.match_score}% Match</span>` : ''}
            </div>
            <div style="font-size:12.5px; color:#64748b; margin-top:3px;">
              Facility: <strong>${escapeHtml(l.lot_name || 'Parking Facility')}</strong> &bull; Floor: ${escapeHtml(l.floor || 'Ground Floor')} &bull; Owner: <strong>${escapeHtml(l.owner_name)}</strong>
            </div>
            <div style="font-size:12px; color:#94a3b8; margin-top:2px;">
              Date: ${escapeHtml(l.date)} (${escapeHtml(l.start_time)} – ${escapeHtml(l.end_time)})
              ${l.match_rationale ? ` &bull; <span style="color:#0284c7;">${escapeHtml(l.match_rationale)}</span>` : ''}
            </div>
          </div>
          <button class="btn-user btn-user-primary btn-user-sm" onclick="proposeExchangeRequest('${l.listing_id}')">
            <i class="fas fa-repeat"></i> Propose Swap
          </button>
        </div>
      `).join('');
    }
  } catch (err) {
    container.innerHTML = '<div style="color:#ef4444;">Failed to load marketplace.</div>';
  }
}

async function seedDemoExchangeSlot() {
  try {
    const res = await fetch('/api/exchange/seed-demo', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: window.ACTIVE_USER_ID })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      loadSlotExchangeTab();
    } else {
      showUserToast(data.message || 'Failed to generate demo slot', 'error');
    }
  } catch (e) {
    showUserToast('Error generating demo slot', 'error');
  }
}

async function proposeExchangeRequest(listingId) {
  try {
    const res = await fetch('/api/exchange/propose', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        listing_id: parseInt(listingId),
        requester_user_id: window.ACTIVE_USER_ID
      })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      loadSlotExchangeTab();
      loadUserNotifications();
      pollNotificationBadges();

      // Trigger automatic simulation of driver acceptance for immediate end-to-end satisfaction
      if (data.request_id) {
        showUserToast('Driver is reviewing your exchange proposal...', 'info');
        setTimeout(async () => {
          await simulateOwnerAccept(data.request_id, true);
        }, 1500);
      }
    } else {
      showUserToast(data.message || 'Swap proposal failed', 'error');
    }
  } catch (err) {
    showUserToast('Error proposing exchange', 'error');
  }
}

async function loadUserExchangeRequests() {
  const container = document.getElementById('userExchangeRequestsContainer');
  if (!container) return;

  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/exchange/requests${uid ? `?user_id=${uid}` : ''}`);
    const data = await res.json();
    if (data.status === 'success') {
      const received = data.received_requests || [];
      if (received.length === 0) {
        container.innerHTML = '<div style="color:#94a3b8; font-size:13px;">No incoming exchange proposals.</div>';
        return;
      }

      container.innerHTML = received.map(r => `
        <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:14px; margin-bottom:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
              <strong style="color:#92400e;">Driver ${escapeHtml(r.requester_name)} wants to swap:</strong>
              <div style="font-size:13px; color:#451a03; margin-top:2px;">
                Offers: <strong>Slot ${escapeHtml(r.requester_slot_number)}</strong> for your <strong>Slot ${escapeHtml(r.owner_slot_number)}</strong>
              </div>
              <div style="font-size:11.5px; color:#78350f; margin-top:2px;">
                Facility: ${escapeHtml(r.requester_lot_name || 'Parking Facility')} &bull; Date: ${escapeHtml(r.requester_date || '')} (${escapeHtml(r.requester_start_time || '')} – ${escapeHtml(r.requester_end_time || '')})
              </div>
            </div>
            ${r.status === 'pending' ? `
              <div style="display:flex; gap:8px;">
                <button class="btn-user btn-user-success btn-user-sm" onclick="respondToExchange('${r.request_id}', 'accept')">
                  <i class="fas fa-check"></i> Accept
                </button>
                <button class="btn-user btn-user-danger btn-user-sm" onclick="respondToExchange('${r.request_id}', 'reject')">
                  <i class="fas fa-times"></i> Reject
                </button>
              </div>
            ` : `
              <span class="status-badge ${r.status === 'accepted' ? 'completed' : 'cancelled'}">${escapeHtml(r.status)}</span>
            `}
          </div>
        </div>
      `).join('');
    }
  } catch (err) {
    container.innerHTML = '<div style="color:#ef4444; font-size:13px;">Failed to load requests.</div>';
  }
}

async function respondToExchange(requestId, action) {
  try {
    const res = await fetch('/api/exchange/respond', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        request_id: parseInt(requestId),
        action: action,
        user_id: window.ACTIVE_USER_ID
      })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      loadSlotExchangeTab();
      loadUserDashboard();
      loadUserNotifications();
      pollNotificationBadges();
    } else {
      showUserToast(data.message || 'Action failed', 'error');
    }
  } catch (err) {
    showUserToast('Error responding to request', 'error');
  }
}

async function loadUserSentExchangeRequests() {
  const container = document.getElementById('userSentExchangeRequestsContainer');
  if (!container) return;

  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/exchange/requests${uid ? `?user_id=${uid}` : ''}`);
    const data = await res.json();
    if (data.status === 'success') {
      const sent = data.sent_requests || [];
      if (sent.length === 0) {
        container.innerHTML = '<div style="color:#94a3b8; font-size:13px; text-align:center; padding:16px;">You have not sent any exchange proposals yet. Browse slots below to propose a swap!</div>';
        return;
      }

      container.innerHTML = sent.map(s => {
        const st = (s.status || 'pending').toLowerCase();
        let statusBadgeClass = 'pending';
        if (st === 'accepted') statusBadgeClass = 'accepted';
        else if (st === 'rejected') statusBadgeClass = 'rejected';
        else if (st === 'cancelled') statusBadgeClass = 'cancelled';

        return `
          <div class="exchange-card">
            <div style="flex:1;">
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                <strong style="font-size:15px; color:#0f172a;">Requested Slot ${escapeHtml(s.owner_slot_number || '-')}</strong>
                <span class="exchange-status-pill ${statusBadgeClass}">${escapeHtml(s.status || 'pending')}</span>
              </div>
              <div style="font-size:13px; color:#475569;">
                Owner: <strong>Driver ${escapeHtml(s.owner_name || 'Driver')}</strong> &bull; Facility: ${escapeHtml(s.owner_lot_name || 'Parking Facility')}
              </div>
              <div style="font-size:12px; color:#64748b; margin-top:2px;">
                Your Offered Slot: <strong>Slot ${escapeHtml(s.requester_slot_number || '-')}</strong> (${escapeHtml(s.requester_floor || 'Ground Floor')}) &bull; Date: ${escapeHtml(s.owner_date || s.requester_date || '')}
              </div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
              ${st === 'pending' ? `
                <button class="btn-user btn-user-success btn-user-sm" onclick="simulateOwnerAccept('${s.request_id}')" title="Simulate partner driver accepting this proposal">
                  <i class="fas fa-check-double"></i> Simulate Accept
                </button>
                <button class="btn-user btn-user-danger btn-user-sm" onclick="cancelSentExchangeRequest('${s.request_id}')">
                  <i class="fas fa-ban"></i> Withdraw Request
                </button>
              ` : `
                <span style="font-size:12px; color:#64748b; font-weight:600;">Proposal ${escapeHtml(st)}</span>
              `}
            </div>
          </div>
        `;
      }).join('');
    }
  } catch (err) {
    container.innerHTML = '<div style="color:#ef4444; font-size:13px;">Failed to load sent proposals.</div>';
  }
}

async function cancelSentExchangeRequest(requestId) {
  if (!confirm('Are you sure you want to withdraw this exchange proposal?')) return;
  try {
    const res = await fetch('/api/exchange/cancel-request', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        request_id: parseInt(requestId),
        user_id: window.ACTIVE_USER_ID
      })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message || 'Request withdrawn', 'success');
      loadSlotExchangeTab();
      loadUserNotifications();
      pollNotificationBadges();
    } else {
      showUserToast(data.message || 'Failed to withdraw request', 'error');
    }
  } catch (e) {
    showUserToast('Error cancelling request', 'error');
  }
}

async function quickSeedUserBookingForExchange() {
  try {
    const res = await fetch('/api/exchange/quick-seed-booking', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: window.ACTIVE_USER_ID })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      loadSlotExchangeTab();
      loadUserDashboard();
      if (typeof loadMyBookings === 'function') loadMyBookings();
    } else {
      showUserToast(data.message || 'Failed to seed test booking', 'error');
    }
  } catch (err) {
    showUserToast('Network error seeding booking.', 'error');
  }
}

async function simulateIncomingExchangeRequest() {
  try {
    const res = await fetch('/api/exchange/simulate-incoming-request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: window.ACTIVE_USER_ID })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(data.message, 'success');
      loadSlotExchangeTab();
      loadUserNotifications();
      pollNotificationBadges();
    } else {
      showUserToast(data.message || 'Failed to simulate incoming request', 'error');
    }
  } catch (err) {
    showUserToast('Network error simulating incoming request.', 'error');
  }
}

async function simulateOwnerAccept(requestId, isAuto = false) {
  try {
    const res = await fetch('/api/exchange/simulate-owner-response', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        request_id: parseInt(requestId),
        action: 'accept'
      })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast(`🎉 Slot Exchanged! ${data.message || 'Exchange successfully completed.'}`, 'success');
      loadSlotExchangeTab();
      loadUserDashboard();
      loadUserNotifications();
      pollNotificationBadges();
      if (typeof loadMyBookings === 'function') loadMyBookings();
    } else if (!isAuto) {
      showUserToast(data.message || 'Failed to accept proposal.', 'error');
    }
  } catch (err) {
    if (!isAuto) showUserToast('Error accepting proposal.', 'error');
  }
}

async function handleUserPanelSwitch(newUserId) {
  const uid = parseInt(newUserId);
  window.ACTIVE_USER_ID = uid;

  try {
    const res = await fetch('/api/auth/switch-demo-user', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: uid })
    });
    const data = await res.json();
    if (res.ok && data.user) {
      showUserToast(`Switched active profile to ${data.user.name}.`, 'info');
      const nameEl = document.getElementById('userProfileName');
      if (nameEl) nameEl.textContent = data.user.name;
    }
  } catch (e) {
    console.error('Session sync error on user panel switch:', e);
  }

  loadUserDashboard();
  loadUserProfile();
  loadUserVehicles();
  loadMyBookings();
  loadSlotExchangeTab();
  loadUserNotifications();
  pollNotificationBadges();
}

/* ==========================================================================
   MODULE 8: MY BOOKINGS
   ========================================================================== */

let myAllBookings = [];

async function loadMyBookings() {
  const tbody = document.getElementById('myBookingsTbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading your bookings...</td></tr>';

  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/reservations/my${uid ? `?user_id=${uid}` : ''}`);
    const data = await res.json();
    if (data.status === 'success') {
      myAllBookings = data.reservations || [];
      renderMyBookingsTable(myAllBookings);
    }
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#ef4444;">Failed to load bookings.</td></tr>';
  }
}

function renderMyBookingsTable(bookings) {
  const tbody = document.getElementById('myBookingsTbody');
  if (!tbody) return;
  if (!bookings || bookings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:#94a3b8;">No bookings found for this category.</td></tr>';
    return;
  }

  tbody.innerHTML = bookings.map(b => {
    const st = (b.status || 'confirmed').toLowerCase();
    const isOccupied = (st === 'occupied' || st === 'checked_in' || st === 'overstayed');
    const isActive = (st === 'confirmed' || st === 'reserved' || isOccupied);
    const bid = b.reservation_id || b.booking_id;

    let badgeClass = 'confirmed';
    if (st === 'completed') badgeClass = 'completed';
    else if (st === 'cancelled') badgeClass = 'cancelled';
    else if (st === 'overstayed') badgeClass = 'occupied';
    else if (isOccupied) badgeClass = 'occupied';

    return `
      <tr>
        <td style="font-family:var(--font-mono); color:#64748b;">#${bid}</td>
        <td>
          <strong style="color:#0f172a;">Slot ${escapeHtml(b.slot_number || '-')}</strong>
          <div style="font-size:11px; color:#64748b;">${escapeHtml(b.floor || 'Ground Floor')} &bull; ${escapeHtml(b.lot_name || 'City Parking')}</div>
        </td>
        <td>
          <div>${escapeHtml(b.date || b.booking_date || '')}</div>
          <div style="font-size:11.5px; color:#64748b;">${escapeHtml(b.start_time || '')} – ${escapeHtml(b.end_time || '')}</div>
        </td>
        <td><strong style="font-family:var(--font-mono);">${escapeHtml(b.vehicle_plate || '')}</strong></td>
        <td><span class="status-badge ${badgeClass}">${escapeHtml(b.status || 'confirmed')}</span></td>
        <td style="font-weight:700; color:#0f172a;">₹${b.total_amount ? Number(b.total_amount).toFixed(2) : '80.00'}</td>
        <td>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            ${isActive ? `
              ${(!isOccupied && st !== 'overstayed') ? `
                <button class="btn-user btn-user-success btn-user-sm" onclick="userStartParking('${bid}')" title="Park Vehicle">
                  <i class="fas fa-car-side"></i> Park
                </button>
              ` : ''}
              <button class="btn-user btn-user-danger btn-user-sm" onclick="openExitParkingModal('${bid}')" style="background:#fee2e2; color:#be123c; border:1px solid #fecdd3; font-weight:700;" title="Exit Parking">
                <i class="fas fa-arrow-right-from-bracket"></i> Exit
              </button>
              <button class="btn-user btn-user-primary btn-user-sm" onclick="openQRPassModal('${bid}')" title="QR Digital Pass">
                <i class="fas fa-qrcode"></i> Pass
              </button>
              ${(!isOccupied && st !== 'overstayed') ? `
                <button class="btn-user btn-user-secondary btn-user-sm" onclick="userCancelBooking('${bid}')" title="Cancel Booking">
                  <i class="fas fa-times"></i>
                </button>
              ` : ''}
            ` : `
              <button class="btn-user btn-user-secondary btn-user-sm" onclick="openQRPassModal('${bid}')" title="View Receipt">
                <i class="fas fa-receipt"></i> Receipt
              </button>
            `}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function filterMyBookings(tab) {
  const buttons = document.querySelectorAll('.my-booking-tab-btn');
  buttons.forEach(btn => {
    if (btn.getAttribute('data-tab') === tab) btn.classList.add('active');
    else btn.classList.remove('active');
  });

  if (tab === 'all') {
    renderMyBookingsTable(myAllBookings);
  } else if (tab === 'active') {
    renderMyBookingsTable(myAllBookings.filter(b => {
      const st = (b.status || '').toLowerCase();
      return st === 'confirmed' || st === 'checked_in' || st === 'reserved' || st === 'occupied' || st === 'overstayed';
    }));
  } else if (tab === 'completed') {
    renderMyBookingsTable(myAllBookings.filter(b => (b.status || '').toLowerCase() === 'completed'));
  } else if (tab === 'cancelled') {
    renderMyBookingsTable(myAllBookings.filter(b => (b.status || '').toLowerCase() === 'cancelled'));
  }
}

async function userCancelBooking(resId) {
  if (!confirm('Are you sure you want to cancel this booking? The slot will be released immediately.')) return;
  try {
    const res = await fetch(`/api/reservations/cancel/${resId}`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      showUserToast('Booking cancelled successfully', 'success');
      loadMyBookings();
      loadUserDashboard();
    } else {
      showUserToast(data.message || 'Failed to cancel', 'error');
    }
  } catch (err) {
    showUserToast('Error cancelling booking', 'error');
  }
}

/* ==========================================================================
   MODULE 9: PARKING HISTORY (USER BOOKED SLOTS & FACILITY-WIDE BOOKINGS)
   ========================================================================== */

let currentHistoryScope = 'my';

function filterParkingHistoryScope(scope) {
  currentHistoryScope = scope;
  const myBtn = document.getElementById('historyScopeMyBtn');
  const allBtn = document.getElementById('historyScopeAllBtn');
  if (myBtn && allBtn) {
    if (scope === 'my') {
      myBtn.classList.add('active', 'btn-user-primary');
      myBtn.classList.remove('btn-user-secondary');
      allBtn.classList.remove('active', 'btn-user-primary');
      allBtn.classList.add('btn-user-secondary');
    } else {
      allBtn.classList.add('active', 'btn-user-primary');
      allBtn.classList.remove('btn-user-secondary');
      myBtn.classList.remove('active', 'btn-user-primary');
      myBtn.classList.add('btn-user-secondary');
    }
  }
  loadParkingHistory(scope);
}

function formatHistoryTime(rawTime) {
  if (!rawTime) return '—';
  if (rawTime.includes(' ')) {
    const parts = rawTime.split(' ');
    if (parts.length >= 2) return parts[1].slice(0, 5);
  }
  return rawTime;
}

async function loadParkingHistory(scope = currentHistoryScope) {
  const tbody = document.getElementById('parkingHistoryTbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading parking history...</td></tr>';

  try {
    if (scope === 'all') {
      const res = await fetch('/api/reservations/facility-history');
      const data = await res.json();
      if (data.status === 'success') {
        const history = data.reservations || [];
        if (history.length === 0) {
          tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; padding:30px; color:#94a3b8;">No bookings recorded across the facility yet.</td></tr>';
          return;
        }

        tbody.innerHTML = history.map(h => {
          const st = (h.status || 'confirmed').toLowerCase();
          const isOverstay = h.is_overstay || (h.final_status && h.final_status.includes('Overstay'));
          let badgeHtml = '';
          if (isOverstay) {
            badgeHtml = `<span class="status-badge occupied" style="background:#fff1f2; color:#be123c; border:1px solid #fda4af; font-weight:700;"><i class="fas fa-triangle-exclamation"></i> Completed + Overstay</span>`;
          } else if (st === 'completed') {
            badgeHtml = `<span class="status-badge completed">Completed</span>`;
          } else if (st === 'cancelled') {
            badgeHtml = `<span class="status-badge cancelled">Cancelled</span>`;
          } else if (st === 'occupied' || st === 'checked_in') {
            badgeHtml = `<span class="status-badge occupied">Occupied</span>`;
          } else {
            badgeHtml = `<span class="status-badge active">${escapeHtml(h.status || 'Confirmed')}</span>`;
          }

          const entryDisp = h.actual_entry_time ? formatHistoryTime(h.actual_entry_time) : (h.start_time || '—');
          const exitDisp = h.actual_exit_time ? formatHistoryTime(h.actual_exit_time) : (st === 'completed' ? (h.end_time || '—') : (st === 'cancelled' ? 'Cancelled' : 'In Session'));
          const durationDisp = h.parking_duration || h.duration || '—';
          const overstayDisp = isOverstay ? `<span style="color:#e11d48; font-weight:700;">⚠️ ${h.overstay_duration_minutes || 0}m</span>` : '<span style="color:#94a3b8;">—</span>';

          return `
            <tr>
              <td style="font-family:var(--font-mono); color:#64748b;">#${escapeHtml(h.booking_id || h.reservation_id || '-')}</td>
              <td>
                <strong style="font-family:var(--font-mono); color:#0f172a;">${escapeHtml(h.vehicle_plate || '—')}</strong>
                <div style="font-size:11px; color:#64748b;">${escapeHtml(h.vehicle_type || 'Car')}</div>
              </td>
              <td>
                <strong style="color:#0f172a;">${escapeHtml(h.lot_name || 'Institutions')}</strong>
                <div style="font-size:11px; color:#64748b;">${escapeHtml(h.user_name || 'Driver')}</div>
              </td>
              <td>
                <strong style="color:#0284c7;">Slot ${escapeHtml(h.slot_number || '-')}</strong>
                <div style="font-size:11px; color:#94a3b8;">${escapeHtml(h.floor || 'Ground Floor')}</div>
              </td>
              <td>${escapeHtml(h.date || h.booking_date || '—')}</td>
              <td><strong style="color:#10b981;">${escapeHtml(entryDisp)}</strong></td>
              <td><strong style="color:#0284c7;">${escapeHtml(exitDisp)}</strong></td>
              <td>${escapeHtml(durationDisp)}</td>
              <td>${overstayDisp}</td>
              <td>${badgeHtml}</td>
              <td style="font-weight:700; color:#0f172a;">₹${h.total_amount ? Number(h.total_amount).toFixed(2) : '60.00'}</td>
            </tr>
          `;
        }).join('');
      } else {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; color:#ef4444;">Failed to load facility history.</td></tr>';
      }
    } else {
      // My Booked Slots (All user's bookings: confirmed, completed, cancelled)
      const uid = window.ACTIVE_USER_ID || '';
      const res = await fetch(`/api/reservations/my${uid ? `?user_id=${uid}` : ''}`);
      const data = await res.json();
      if (data.status === 'success') {
        const history = (data.reservations && data.reservations.length > 0)
          ? data.reservations
          : (data.history || []);
        if (history.length === 0) {
          tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; padding:30px; color:#94a3b8;">No booked slots or past parking sessions recorded.</td></tr>';
          return;
        }

        tbody.innerHTML = history.map(h => {
          const st = (h.status || 'confirmed').toLowerCase();
          const isOverstay = h.is_overstay || (h.final_status && h.final_status.includes('Overstay'));
          let badgeHtml = '';
          if (isOverstay) {
            badgeHtml = `<span class="status-badge occupied" style="background:#fff1f2; color:#be123c; border:1px solid #fda4af; font-weight:700;"><i class="fas fa-triangle-exclamation"></i> Completed + Overstay</span>`;
          } else if (st === 'completed') {
            badgeHtml = `<span class="status-badge completed">Completed</span>`;
          } else if (st === 'cancelled') {
            badgeHtml = `<span class="status-badge cancelled">Cancelled</span>`;
          } else if (st === 'occupied' || st === 'checked_in') {
            badgeHtml = `<span class="status-badge occupied">Occupied</span>`;
          } else {
            badgeHtml = `<span class="status-badge active">${escapeHtml(h.status || 'Confirmed')}</span>`;
          }

          const entryDisp = h.actual_entry_time ? formatHistoryTime(h.actual_entry_time) : (h.start_time || '—');
          const exitDisp = h.actual_exit_time ? formatHistoryTime(h.actual_exit_time) : (st === 'completed' ? (h.end_time || '—') : (st === 'cancelled' ? 'Cancelled' : 'In Session'));
          const durationDisp = h.parking_duration || h.duration || '—';
          const overstayDisp = isOverstay ? `<span style="color:#e11d48; font-weight:700;">⚠️ ${h.overstay_duration_minutes || 0}m</span>` : '<span style="color:#94a3b8;">—</span>';

          return `
            <tr>
              <td style="font-family:var(--font-mono); color:#64748b;">#${escapeHtml(h.reservation_id || h.booking_id || '-')}</td>
              <td>
                <strong style="font-family:var(--font-mono); color:#0f172a;">${escapeHtml(h.vehicle_plate || '—')}</strong>
                <div style="font-size:11px; color:#64748b;">${escapeHtml(h.vehicle_type || 'Car')}</div>
              </td>
              <td>
                <strong style="color:#0f172a;">${escapeHtml(h.lot_name || 'City Parking')}</strong>
                <div style="font-size:11px; color:#64748b;">${escapeHtml(h.user_name || 'Driver')}</div>
              </td>
              <td>
                <strong style="color:#0284c7;">Slot ${escapeHtml(h.slot_number || '-')}</strong>
                <div style="font-size:11px; color:#94a3b8;">${escapeHtml(h.floor || 'Ground Floor')}</div>
              </td>
              <td>${escapeHtml(h.date || h.booking_date || '—')}</td>
              <td><strong style="color:#10b981;">${escapeHtml(entryDisp)}</strong></td>
              <td><strong style="color:#0284c7;">${escapeHtml(exitDisp)}</strong></td>
              <td>${escapeHtml(durationDisp)}</td>
              <td>${overstayDisp}</td>
              <td>${badgeHtml}</td>
              <td style="font-weight:700; color:#0f172a;">₹${h.total_amount ? Number(h.total_amount).toFixed(2) : '80.00'}</td>
            </tr>
          `;
        }).join('');
      } else {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; color:#ef4444;">Failed to load history.</td></tr>';
      }
    }
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; color:#ef4444;">Failed to load history.</td></tr>';
  }
}

/* ==========================================================================
   MODULE 10: NOTIFICATIONS MODULE CONTROLLER
   ========================================================================== */

let allUserNotifications = [];
let currentNotifFilter = 'all';

async function loadUserNotifications() {
  const container = document.getElementById('userNotificationsList');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading notifications...</div>';

  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/notifications${uid ? `?user_id=${uid}` : ''}`);
    const data = await res.json();
    if (data.status === 'success') {
      allUserNotifications = data.notifications || [];
      const unreadCount = data.unread_count || 0;

      // Update counters
      const totalEl = document.getElementById('notifTotalCount');
      if (totalEl) totalEl.textContent = allUserNotifications.length;
      const unreadEl = document.getElementById('notifUnreadFilterCount');
      if (unreadEl) unreadEl.textContent = unreadCount;

      updateNotificationBadges(unreadCount);
      renderNotificationsList();
    } else {
      container.innerHTML = '<div style="color:#ef4444; padding:20px; text-align:center;">Failed to load notifications.</div>';
    }
  } catch (err) {
    container.innerHTML = '<div style="color:#ef4444; padding:20px; text-align:center;">Error fetching notifications.</div>';
  }
}

function updateNotificationBadges(unreadCount) {
  const topbarBadge = document.getElementById('topbarNotifBadge');
  const sidebarBadge = document.getElementById('sidebarNotifBadge');
  if (topbarBadge) {
    topbarBadge.textContent = unreadCount;
    topbarBadge.style.display = unreadCount > 0 ? 'inline-block' : 'none';
  }
  if (sidebarBadge) {
    sidebarBadge.textContent = unreadCount;
    sidebarBadge.style.display = unreadCount > 0 ? 'inline-block' : 'none';
  }
}

async function pollNotificationBadges() {
  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/notifications${uid ? `?user_id=${uid}` : ''}`);
    const data = await res.json();
    if (data.status === 'success') {
      updateNotificationBadges(data.unread_count || 0);
    }
  } catch (e) {
    // silent background polling
  }
}

function filterNotifications(filter) {
  currentNotifFilter = filter;
  const buttons = document.querySelectorAll('.notif-filter-btn');
  buttons.forEach(btn => {
    if (btn.getAttribute('data-filter') === filter) btn.classList.add('active');
    else btn.classList.remove('active');
  });
  renderNotificationsList();
}

function renderNotificationsList() {
  const container = document.getElementById('userNotificationsList');
  if (!container) return;

  let filtered = allUserNotifications;
  if (currentNotifFilter === 'unread') {
    filtered = allUserNotifications.filter(n => Number(n.is_read) === 0);
  } else if (currentNotifFilter === 'exchange') {
    filtered = allUserNotifications.filter(n => (n.type || '').toLowerCase().includes('exchange'));
  } else if (currentNotifFilter === 'booking') {
    filtered = allUserNotifications.filter(n => {
      const t = (n.type || '').toLowerCase();
      return t.includes('booking') || t.includes('cancellation') || t.includes('pass');
    });
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="text-align:center; padding:40px 20px; background:#f8fafc; border:1px dashed #cbd5e1; border-radius:12px;">
        <i class="fas fa-bell-slash fa-3x" style="color:#cbd5e1; margin-bottom:12px;"></i>
        <h4 style="font-size:16px; color:#475569; margin:0 0 6px;">No Notifications Found</h4>
        <p style="font-size:13px; color:#94a3b8; margin:0;">You are all caught up with your alerts.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(n => {
    const isUnread = Number(n.is_read) === 0;
    const type = (n.type || '').toLowerCase();

    let iconFa = 'fa-bell';
    let iconCat = 'system';
    let actionBtn = '';

    if (type.includes('exchange')) {
      iconFa = 'fa-arrow-right-arrow-left';
      iconCat = 'exchange';
      actionBtn = `<button class="btn-notif-action primary" onclick="switchUserTab('exchange')"><i class="fas fa-repeat"></i> Go to Slot Exchange</button>`;
    } else if (type.includes('booking') || type.includes('cancellation')) {
      iconFa = 'fa-ticket';
      iconCat = 'booking';
      actionBtn = `<button class="btn-notif-action primary" onclick="switchUserTab('bookings')"><i class="fas fa-ticket"></i> View Bookings</button>`;
    } else if (type.includes('alert') || type.includes('reminder') || type.includes('expiry')) {
      iconFa = 'fa-triangle-exclamation';
      iconCat = 'alert';
    }

    return `
      <div class="notif-item ${isUnread ? 'unread' : ''}">
        <div class="notif-icon-circle ${iconCat}">
          <i class="fas ${iconFa}"></i>
        </div>
        <div class="notif-content">
          <div class="notif-header">
            <h4 class="notif-title">${escapeHtml(n.title || 'Notification')}</h4>
            <span class="notif-time"><i class="far fa-clock"></i> ${escapeHtml(n.created_at || '')}</span>
          </div>
          <div class="notif-message">${escapeHtml(n.message || '')}</div>
          <div class="notif-actions">
            ${isUnread ? `
              <button class="btn-notif-action" onclick="markNotificationAsRead(${n.notification_id})">
                <i class="fas fa-check"></i> Mark as Read
              </button>
            ` : ''}
            ${actionBtn}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function markNotificationAsRead(notificationId) {
  try {
    const res = await fetch(`/api/notifications/${notificationId}/read`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      const item = allUserNotifications.find(n => n.notification_id === notificationId);
      if (item) item.is_read = 1;
      const unreadCount = allUserNotifications.filter(n => Number(n.is_read) === 0).length;
      updateNotificationBadges(unreadCount);
      const unreadEl = document.getElementById('notifUnreadFilterCount');
      if (unreadEl) unreadEl.textContent = unreadCount;
      renderNotificationsList();
    }
  } catch (e) {
    showUserToast('Failed to mark as read', 'error');
  }
}

async function markAllNotificationsAsRead() {
  try {
    const res = await fetch('/api/notifications/mark-all-read', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: window.ACTIVE_USER_ID })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast('All notifications marked as read', 'success');
      allUserNotifications.forEach(n => n.is_read = 1);
      updateNotificationBadges(0);
      const unreadEl = document.getElementById('notifUnreadFilterCount');
      if (unreadEl) unreadEl.textContent = '0';
      renderNotificationsList();
    } else {
      showUserToast(data.message || 'Action failed', 'error');
    }
  } catch (e) {
    showUserToast('Failed to mark all as read', 'error');
  }
}

async function clearUserNotifications() {
  if (!confirm('Are you sure you want to clear all your notifications?')) return;
  try {
    const res = await fetch('/api/notifications/clear', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: window.ACTIVE_USER_ID })
    });
    const data = await res.json();
    if (res.ok) {
      showUserToast('All notifications cleared', 'success');
      allUserNotifications = [];
      updateNotificationBadges(0);
      const totalEl = document.getElementById('notifTotalCount');
      if (totalEl) totalEl.textContent = '0';
      const unreadEl = document.getElementById('notifUnreadFilterCount');
      if (unreadEl) unreadEl.textContent = '0';
      renderNotificationsList();
    } else {
      showUserToast(data.message || 'Action failed', 'error');
    }
  } catch (e) {
    showUserToast('Failed to clear notifications', 'error');
  }
}

/* ==========================================================================
   QR DIGITAL PASS MODAL
   ========================================================================== */

async function openQRPassModal(resId) {
  const modal = document.getElementById('qrPassModal');
  if (modal) modal.style.display = 'flex';

  try {
    const res = await fetch(`/api/reservations/${resId}/pass`);
    const data = await res.json();
    if (data.status === 'success' && data.pass) {
      const p = data.pass;
      const passText = p.pass_code || p.booking_id || `PASS-${resId}`;
      const codeEl = document.getElementById('passCodeDisplay');
      if (codeEl) codeEl.textContent = passText;
      const slotEl = document.getElementById('passSlotDisplay');
      if (slotEl) slotEl.textContent = `Slot ${p.slot_number}`;
      const lotEl = document.getElementById('passLotDisplay');
      if (lotEl) lotEl.textContent = p.lot_name || 'City Parking';
      const plateEl = document.getElementById('passPlateDisplay');
      if (plateEl) plateEl.textContent = p.vehicle_plate || 'Not Assigned';
      const dateEl = document.getElementById('passDateDisplay');
      if (dateEl) dateEl.textContent = `${p.date || p.booking_date || ''} (${p.start_time || '10:00'} – ${p.end_time || '12:00'})`;

      const qrBox = document.getElementById('modalQrCodeBox');
      if (qrBox) {
        qrBox.innerHTML = '';
        if (typeof QRCode !== 'undefined') {
          new QRCode(qrBox, {
            text: passText,
            width: 110,
            height: 110,
            colorDark: '#0f172a',
            colorLight: '#ffffff',
            correctLevel: QRCode.CorrectLevel.M
          });
        }
      }
    }
  } catch (e) {
    console.error('Error opening pass modal:', e);
  }
}

function closeQRPassModal() {
  document.getElementById('qrPassModal').style.display = 'none';
}

/* ==========================================================================
   TOAST
   ========================================================================== */

function showUserToast(message, type = 'success') {
  let toast = document.getElementById('userToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'userToast';
    toast.className = 'user-toast';
    document.body.appendChild(toast);
  }

  toast.innerHTML = `
    <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}" style="color:${type === 'success' ? '#34d399' : '#f87171'}; font-size:16px;"></i>
    <span>${escapeHtml(message)}</span>
  `;
  toast.style.display = 'flex';

  setTimeout(() => {
    toast.style.display = 'none';
  }, 4000);
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/* ==========================================================================
   VEHICLE EXIT / CHECKOUT CONTROLLER
   ========================================================================== */

let activeExitBookingId = null;
let activeExitPreview = null;
let activeExitPenaltyPaid = false;

window.payOverstayWithRazorpay = function() {
  if (!activeExitPreview || !activeExitBookingId) return;
  const penalty = parseFloat(activeExitPreview.overstay_penalty) || 0.0;
  if (penalty <= 0) {
    showUserToast('No overstay penalty due.', 'info');
    return;
  }

  if (typeof window.openRazorpayModal === 'function') {
    window.openRazorpayModal({
      amount: penalty,
      title: 'Smart Parking AI',
      description: `Overstay Penalty Settlement (${activeExitPreview.overstay_duration_minutes}m)`,
      bookingId: activeExitBookingId,
      type: 'overstay_penalty',
      onSuccess: function(paymentResult) {
        activeExitPenaltyPaid = true;
        const btnPay = document.getElementById('btnPayOverstayRazorpay');
        if (btnPay) {
          btnPay.disabled = true;
          btnPay.innerHTML = '<i class="fas fa-check-circle"></i> Paid via Razorpay';
          btnPay.style.background = '#059669';
        }
        const amtEl = document.getElementById('checkoutOverstayAmount');
        if (amtEl) amtEl.innerHTML = `₹${penalty.toFixed(2)} <span style="font-size:12px; color:#10b981;">(Settled)</span>`;
        showUserToast(`Penalty ₹${penalty.toFixed(2)} paid successfully via Razorpay!`, 'success');
      },
      onFailure: function() {
        showUserToast('Penalty payment cancelled or declined.', 'error');
      }
    });
  }
};

async function openExitParkingModal(bookingId) {
  activeExitBookingId = bookingId;
  const modal = document.getElementById('exitParkingModal');
  if (!modal) return;

  // Set loading placeholders
  document.getElementById('checkoutSlotDisplay').textContent = 'Loading...';
  document.getElementById('checkoutPlateDisplay').textContent = 'Loading...';
  document.getElementById('checkoutTypeDisplay').textContent = '—';
  document.getElementById('checkoutLotDisplay').textContent = '—';
  document.getElementById('checkoutDateDisplay').textContent = '—';
  document.getElementById('checkoutBookedWindowDisplay').textContent = '—';
  document.getElementById('checkoutActualEntryDisplay').textContent = '—';
  document.getElementById('checkoutExitTimeDisplay').textContent = '—';
  document.getElementById('checkoutDurationDisplay').textContent = '—';
  document.getElementById('checkoutNoticeSlot').textContent = '—';
  const ovBanner = document.getElementById('checkoutOverstayBanner');
  if (ovBanner) ovBanner.style.display = 'none';

  modal.style.display = 'flex';

  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/reservations/${bookingId}/checkout-preview${uid ? `?user_id=${uid}` : ''}`);
    const data = await res.json();
    if (data.status === 'success') {
      const p = data.preview;
      activeExitPreview = p;
      activeExitPenaltyPaid = false;
      const amtEl = document.getElementById('checkoutOverstayAmount');
      if (amtEl) amtEl.textContent = `₹${(p.overstay_penalty || 0).toFixed(2)}`;
      const btnPay = document.getElementById('btnPayOverstayRazorpay');
      if (btnPay) {
        btnPay.disabled = false;
        btnPay.innerHTML = '<i class="fas fa-lock"></i> Pay via Razorpay';
        btnPay.style.background = '#10b981';
      }
      document.getElementById('checkoutSlotDisplay').textContent = p.slot_number;
      document.getElementById('checkoutPlateDisplay').textContent = p.vehicle_number;
      document.getElementById('checkoutTypeDisplay').textContent = p.vehicle_type;
      document.getElementById('checkoutLotDisplay').textContent = p.parking_lot;
      document.getElementById('checkoutDateDisplay').textContent = p.booking_date;
      document.getElementById('checkoutBookedWindowDisplay').textContent = `${p.booked_start_time} – ${p.booked_end_time}`;
      document.getElementById('checkoutActualEntryDisplay').textContent = p.actual_entry_time;
      document.getElementById('checkoutExitTimeDisplay').textContent = p.current_exit_time;
      document.getElementById('checkoutDurationDisplay').textContent = p.parking_duration;
      document.getElementById('checkoutNoticeSlot').textContent = p.slot_number;

      const stBadge = document.getElementById('checkoutStatusBadge');
      if (stBadge) {
        let bCls = 'occupied';
        if (p.current_status === 'OVERSTAYED') bCls = 'occupied';
        else if (p.current_status === 'RESERVED') bCls = 'confirmed';
        stBadge.innerHTML = `<span class="status-badge ${bCls}">${p.current_status}</span>`;
      }

      if (ovBanner) {
        if (p.is_overstay) {
          ovBanner.style.display = 'block';
          const durEl = document.getElementById('checkoutOverstayDurationMins');
          if (durEl) durEl.textContent = `${p.overstay_duration_minutes} minutes`;
          const descEl = document.getElementById('checkoutOverstayDesc');
          if (descEl) {
            descEl.innerHTML = `Exceeded booked window and ${p.grace_period_mins}-minute grace period by <strong>${p.overstay_duration_minutes} minutes</strong>. Accrued penalty: ₹${p.overstay_penalty.toFixed(2)}.`;
          }
        } else {
          ovBanner.style.display = 'none';
        }
      }
    } else {
      showUserToast(data.message || 'Failed to fetch session preview.', 'error');
      closeExitParkingModal();
    }
  } catch (err) {
    console.error('Error opening checkout modal:', err);
    showUserToast('Failed to load checkout details.', 'error');
    closeExitParkingModal();
  }
}

function closeExitParkingModal() {
  const modal = document.getElementById('exitParkingModal');
  if (modal) modal.style.display = 'none';
  activeExitBookingId = null;
}

async function confirmExitParking() {
  if (!activeExitBookingId) return;
  const btn = document.getElementById('confirmExitBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing Exit...';
  }

  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/reservations/${activeExitBookingId}/exit`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: uid })
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      closeExitParkingModal();
      const slotName = data.slot_number || 'assigned slot';
      showUserToast(`Vehicle exited successfully. Slot ${slotName} is now available.`, 'success');

      // 1. Immediately update 2D parking layout (visually changes to available 🟢)
      if (typeof load2DLayout === 'function') {
        await load2DLayout();
      }

      // 2. Remove vehicle from Active Parking section
      if (typeof loadUserDashboard === 'function') {
        await loadUserDashboard();
      }

      // 3. Refresh My Bookings
      if (typeof loadMyBookings === 'function') {
        await loadMyBookings();
      }

      // 4. Move session to Parking History
      if (typeof loadParkingHistory === 'function') {
        await loadParkingHistory();
      }
    } else {
      showUserToast(data.message || 'Failed to checkout vehicle.', 'error');
    }
  } catch (err) {
    console.error('Error confirming exit:', err);
    showUserToast('Error connecting to server for checkout.', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-arrow-right-from-bracket"></i> Confirm Exit';
    }
  }
}

async function userStartParking(bookingId) {
  try {
    const uid = window.ACTIVE_USER_ID || '';
    const res = await fetch(`/api/reservations/${bookingId}/start-parking`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: uid })
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showUserToast(data.message || 'Vehicle parked! Status is now OCCUPIED.', 'success');
      if (typeof loadUserDashboard === 'function') await loadUserDashboard();
      if (typeof load2DLayout === 'function') await load2DLayout();
      if (typeof loadMyBookings === 'function') await loadMyBookings();
    } else {
      showUserToast(data.message || 'Failed to start parking.', 'error');
    }
  } catch (err) {
    showUserToast('Error starting parking.', 'error');
  }
}
