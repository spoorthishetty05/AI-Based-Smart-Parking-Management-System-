/**
 * Main Application Controller for AI-Based Smart Parking System
 * Handles UI tab routing, reservations wizard, overstay management, user profile, and admin overrides
 */

let currentActiveTab = 'dashboard';
let currentSystemData = null;
let currentUserId = (typeof window !== 'undefined' && window.CURRENT_USER_ID) ? parseInt(window.CURRENT_USER_ID) : 1;
let currentSlotStatusFilter = 'all';
let currentSlotFloorFilter = 'All';

// Live PC Date & Time Synchronizer
function getPcDateString(offsetSeconds = (window.SIM_OFFSET_SECONDS || 0)) {
  const d = new Date(Date.now() + offsetSeconds * 1000);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function getPcTomorrowString(offsetSeconds = (window.SIM_OFFSET_SECONDS || 0)) {
  const d = new Date(Date.now() + offsetSeconds * 1000);
  d.setDate(d.getDate() + 1);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function formatPcHeaderDateTime(d) {
  const day = String(d.getDate()).padStart(2, '0');
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const month = months[d.getMonth()];
  const year = d.getFullYear();
  
  let hours = d.getHours();
  const minutes = String(d.getMinutes()).padStart(2, '0');
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12;
  hours = hours ? String(hours).padStart(2, '0') : '12';
  
  return `${day} ${month} ${year} | ${hours}:${minutes} ${ampm}`;
}

function updateLiveClock() {
  const offsetSec = window.SIM_OFFSET_SECONDS || 0;
  const now = new Date(Date.now() + offsetSec * 1000);
  
  const dateTimeEl = document.getElementById('headerDateTime');
  if (dateTimeEl) {
    dateTimeEl.innerHTML = `<i class="far fa-calendar-alt"></i> ${formatPcHeaderDateTime(now)}`;
  }

  // Detect calendar day rollover (daily change date based on PC date)
  const todayStr = getPcDateString(offsetSec);
  if (window.SYSTEM_CURRENT_DATE !== todayStr) {
    window.SYSTEM_CURRENT_DATE = todayStr;
    window.SYSTEM_TOMORROW_DATE = getPcTomorrowString(offsetSec);
    syncBookingDateConstraints();
  }
}

// Initialize system dates from live PC calendar
window.SYSTEM_CURRENT_DATE = getPcDateString();
window.SYSTEM_TOMORROW_DATE = getPcTomorrowString();

document.addEventListener('DOMContentLoaded', () => {
  if (typeof window !== 'undefined' && window.CURRENT_USER_ID) {
    currentUserId = parseInt(window.CURRENT_USER_ID);
    const userSel = document.getElementById('userSelector');
    if (userSel) userSel.value = currentUserId;
  }
  updateLiveClock();
  setInterval(updateLiveClock, 1000); // Live PC clock ticking regularly every 1s
  initApp();
  setupEventListeners();
});

async function initApp() {
  syncBookingDateConstraints();
  await refreshAllDashboardData();
  await loadParkingLotsConfig();
  await fetchNotifications();

  // Check URL hash or initial tab parameter (e.g. #system-modules)
  const hash = (window.location.hash || '').replace('#', '').trim();
  const initTab = hash || (typeof window.INITIAL_TAB !== 'undefined' ? window.INITIAL_TAB : null);
  if (initTab && document.getElementById(`view-${initTab}`)) {
    showTab(initTab);
  }

  // Live Polling every 10 seconds
  setInterval(async () => {
    if (currentActiveTab === 'dashboard' || currentActiveTab === 'map') {
      await refreshAllDashboardData(false);
    }
    await fetchNotifications();
  }, 10000);
}

// Reliable global user signout handler
window.userSignOut = function(e) {
  if (e && typeof e.preventDefault === 'function') {
    e.preventDefault();
  }
  try {
    sessionStorage.clear();
    localStorage.clear();
  } catch (err) {
    console.warn('Storage cleanup warning:', err);
  }
  try {
    fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
  } catch (_) {}
  window.location.href = '/logout';
};

function setupEventListeners() {
  // Navigation tabs - only bind items with data-tab attribute so other links (like sign out) are never intercepted
  document.querySelectorAll('.nav-item[data-tab]').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tab = item.getAttribute('data-tab');
      if (tab) showTab(tab);
    });
  });

  // Close notification dropdown when clicking outside
  document.addEventListener('click', (e) => {
    const notifContainer = document.getElementById('notifBellContainer');
    const notifDropdown = document.getElementById('notifDropdown');
    if (notifContainer && notifDropdown && !notifContainer.contains(e.target)) {
      notifDropdown.style.display = 'none';
    }
  });

  // Floor selector change on dashboard
  const floorSelect = document.getElementById('floorSelect');
  if (floorSelect) {
    floorSelect.addEventListener('change', () => {
      const zone = document.getElementById('zoneSelect') ? document.getElementById('zoneSelect').value : 'All';
      const search = document.getElementById('slotSearchInput') ? document.getElementById('slotSearchInput').value : '';
      renderParkingMap(floorSelect.value, zone, search);
    });
  }

  // Zone selector change on dashboard
  const zoneSelect = document.getElementById('zoneSelect');
  if (zoneSelect) {
    zoneSelect.addEventListener('change', () => {
      const floor = floorSelect ? floorSelect.value : 'Ground Floor';
      const search = document.getElementById('slotSearchInput') ? document.getElementById('slotSearchInput').value : '';
      renderParkingMap(floor, zoneSelect.value, search);
    });
  }

  // Search input on dashboard
  const slotSearchInput = document.getElementById('slotSearchInput');
  if (slotSearchInput) {
    slotSearchInput.addEventListener('input', () => {
      const floor = floorSelect ? floorSelect.value : 'Ground Floor';
      const zone = zoneSelect ? zoneSelect.value : 'All';
      renderParkingMap(floor, zone, slotSearchInput.value);
    });
  }

  // Zoom selector
  const zoomSelect = document.getElementById('zoomSelect');
  if (zoomSelect) {
    zoomSelect.addEventListener('change', () => {
      const mapWrap = document.getElementById('parkingMapContainer');
      if (mapWrap) {
        mapWrap.className = `parking-map-container zoom-${zoomSelect.value}`;
      }
    });
  }
}

function showTab(tabName) {
  if ((tabName === 'admin' || tabName === 'settings') && window.CURRENT_USER_ROLE !== 'admin') {
    if (typeof showToast === 'function') {
      showToast('Access Denied: Administrator privileges required.', 'error');
    }
    tabName = 'dashboard';
  }
  currentActiveTab = tabName;

  // Update sidebar active class
  document.querySelectorAll('.nav-item').forEach(item => {
    if (item.getAttribute('data-tab') === tabName) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  // Update view containers
  document.querySelectorAll('.tab-view').forEach(view => {
    if (view.id === `view-${tabName}`) {
      view.classList.add('active');
    } else {
      view.classList.remove('active');
    }
  });

  // Trigger tab-specific loader
  if (tabName === 'dashboard') {
    refreshAllDashboardData();
  } else if (tabName === 'map') {
    renderParkingMap('Ground Floor');
    loadAllSlotsTable();
  } else if (tabName === 'ai-lab') {
    if (typeof loadAiLabData === 'function') loadAiLabData();
  } else if (tabName === 'reservations') {
    initReservationWizard();
  } else if (tabName === 'my-bookings') {
    loadMyBookings();
  } else if (tabName === 'overstays') {
    loadOverstayCenter();
  } else if (tabName === 'reports') {
    loadReportsView();
  } else if (tabName === 'admin') {
    loadAdminView();
  } else if (tabName === 'exchange') {
    loadExchangeView();
  } else if (tabName === 'profile') {
    loadUserProfile();
  } else if (tabName === 'notifications') {
    fetchNotifications();
  } else if (tabName === 'search') {
    loadParkingSearchResults();
  }
}

async function handleUserSwitch(newUserId) {
  currentUserId = parseInt(newUserId);
  const userNames = {
    1: 'Spoorthi',
    2: 'Rahul',
    3: 'Priya',
    4: 'Amit'
  };
  const name = userNames[currentUserId] || 'Driver';
  const greetEl = document.getElementById('topHeaderGreeting');
  if (greetEl) greetEl.innerText = `Good Morning, ${name} 👋`;

  // Synchronize server-side session
  try {
    const res = await fetch('/api/auth/switch-demo-user', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId })
    });
    const data = await res.json();
    if (res.ok && data.user) {
      window.CURRENT_USER_ID = data.user.user_id;
      window.CURRENT_USER_NAME = data.user.name;
      window.CURRENT_USER_ROLE = data.user.role;
      const pillSpan = document.querySelector('.user-session-pill span');
      if (pillSpan) {
        pillSpan.innerHTML = `${data.user.name} <span style="font-size:10px; color:#64748b; font-weight:600;">(${data.user.role.toUpperCase()})</span>`;
      }
    }
  } catch (err) {
    console.error("Session sync error on user switch:", err);
  }

  showToast(`Switched active profile to ${name}.`, 'info');
  if (currentActiveTab === 'my-bookings') loadMyBookings();
  if (currentActiveTab === 'exchange') loadExchangeView();
  if (currentActiveTab === 'profile') loadUserProfile();
  if (currentActiveTab === 'reservations') initReservationWizard();
}

async function refreshAllDashboardData(showLoading = false) {
  try {
    const res = await fetch('/api/system/status');
    const data = await res.json();
    if (data.status === 'success') {
      currentSystemData = data;
      updateHeaderAndKpis(data);
      initCharts(data);

      const floor = document.getElementById('floorSelect') ? document.getElementById('floorSelect').value : 'Ground Floor';
      const zone = document.getElementById('zoneSelect') ? document.getElementById('zoneSelect').value : 'All';
      const search = document.getElementById('slotSearchInput') ? document.getElementById('slotSearchInput').value : '';
      renderParkingMap(floor, zone, search);

      loadActivityLogs();
      refreshMongoStatusUI();
    }
  } catch (err) {
    console.error("Dashboard refresh error:", err);
  }
}

function updateHeaderAndKpis(data) {
  if (data.sim_offset_seconds !== undefined) {
    window.SIM_OFFSET_SECONDS = data.sim_offset_seconds;
  }
  if (data.current_date) window.SYSTEM_CURRENT_DATE = data.current_date;
  if (data.tomorrow) window.SYSTEM_TOMORROW_DATE = data.tomorrow;
  syncBookingDateConstraints();

  // Update header time & greeting with live ticker
  updateLiveClock();

  const stats = data.stats || {};
  // KPI values
  const elAvail = document.getElementById('kpiAvailable');
  const elOcc = document.getElementById('kpiOccupied');
  const elRes = document.getElementById('kpiReserved');
  const elOver = document.getElementById('kpiOverstayed');
  const elTotal = document.getElementById('kpiTotal');

  if (elAvail) elAvail.innerText = stats.available ?? 36;
  if (elOcc) elOcc.innerText = stats.occupied ?? 52;
  if (elRes) elRes.innerText = stats.reserved ?? 18;
  if (elOver) elOver.innerText = stats.overstayed ?? 4;
  if (elTotal) elTotal.innerText = stats.total ?? 110;

  // Module 10: Operations & Exchanges Performance Counters
  const elExch = document.getElementById('kpiExchanged');
  const elDailyB = document.getElementById('kpiDailyBookings');
  const elDailyE = document.getElementById('kpiDailyExchanges');
  const elPeak = document.getElementById('kpiPeakHours');

  if (elExch) elExch.innerText = data.exchanged_slots_count ?? 2;
  if (elDailyB) elDailyB.innerText = data.daily_bookings_count ?? 14;
  if (elDailyE) elDailyE.innerText = data.daily_exchanges_count ?? 2;
  if (elPeak) elPeak.innerText = data.peak_hours ?? '9-11 AM & 5-7 PM';

  // Module 10: Reports View Operational Capacity Summary
  const repTot = document.getElementById('repTotalSlots');
  const repAvail = document.getElementById('repAvailSlots');
  const repRes = document.getElementById('repResSlots');
  const repOcc = document.getElementById('repOccSlots');
  const repOver = document.getElementById('repOverSlots');
  const repExch = document.getElementById('repExchSlots');
  const repDailyB = document.getElementById('repDailyBookings');
  const repDailyE = document.getElementById('repDailyExchanges');
  const repPeak = document.getElementById('repPeakHours');
  const repAvg = document.getElementById('repAvgDuration');

  if (repTot) repTot.innerText = stats.total ?? 110;
  if (repAvail) repAvail.innerText = stats.available ?? 36;
  if (repRes) repRes.innerText = stats.reserved ?? 18;
  if (repOcc) repOcc.innerText = stats.occupied ?? 52;
  if (repOver) repOver.innerText = stats.overstayed ?? 4;
  if (repExch) repExch.innerText = data.exchanged_slots_count ?? 2;
  if (repDailyB) repDailyB.innerText = data.daily_bookings_count ?? 14;
  if (repDailyE) repDailyE.innerText = data.daily_exchanges_count ?? 2;
  if (repPeak) repPeak.innerText = data.peak_hours ?? '9-11 AM & 5-7 PM';
  if (repAvg && data.parking_statistics) {
    repAvg.innerText = (data.parking_statistics.average_duration_hours || 2.2) + ' hrs';
  }
}

async function loadActivityLogs() {
  const container = document.getElementById('activityLogsList');
  if (!container) return;

  try {
    const res = await fetch('/api/activity-logs?limit=5');
    const data = await res.json();
    const logs = data.logs || [];

    let html = '';
    logs.forEach(log => {
      const badgeClass = {
        'danger': 'overstay',
        'primary': 'booked',
        'warning': 'reserved',
        'success': 'vacated',
        'info': 'info'
      }[log.badge_type] || 'info';

      const iconClass = {
        'danger': 'fa-exclamation-triangle',
        'primary': 'fa-car',
        'warning': 'fa-clock',
        'success': 'fa-check',
        'info': 'fa-info-circle'
      }[log.badge_type] || 'fa-bell';

      html += `
        <div class="activity-item">
          <div class="activity-icon ${log.badge_type || 'info'}">
            <i class="fas ${iconClass}"></i>
          </div>
          <div class="activity-content">
            <div class="activity-title-row">
              <span class="activity-title">Slot ${log.slot_number} - ${log.action_type}</span>
              <span class="activity-time">${log.timestamp}</span>
            </div>
            <div class="activity-user">${log.user_name || ''}</div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html || '<p style="font-size:12px; color:#94a3b8; text-align:center; padding:10px;">No recent activity.</p>';
  } catch (err) {
    console.error("Activity logs error:", err);
  }
}

// ==========================================
// MODULE 2: PARKING LOTS & SLOTS DIRECTORY
// ==========================================

function switchSlotSubTab(subTabName) {
  document.querySelectorAll('#view-map .sub-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-subtab') === subTabName);
  });
  document.querySelectorAll('#view-map .sub-view').forEach(view => {
    view.classList.toggle('active', view.id === `slot-subview-${subTabName}`);
  });

  if (subTabName === 'all-slots-table') {
    loadAllSlotsTable();
  } else if (subTabName === 'facility-config') {
    loadParkingLotsConfig();
  }
}

function showSlotsTabWithStatus(status) {
  showTab('map');
  switchSlotSubTab('all-slots-table');
  filterSlotsTableByStatus(status);
}

function filterSlotsTableByStatus(status, btnElement = null) {
  currentSlotStatusFilter = status;
  if (btnElement) {
    document.querySelectorAll('#slotStatusFilterBar button').forEach(b => b.classList.remove('active'));
    btnElement.classList.add('active');
  }
  loadAllSlotsTable();
}

let slotsSearchTimer = null;
function debounceSlotsSearch() {
  clearTimeout(slotsSearchTimer);
  slotsSearchTimer = setTimeout(() => {
    loadAllSlotsTable();
  }, 250);
}

let cachedLots = [];

async function loadParkingLotsConfig() {
  const container = document.getElementById('parkingLotsContainer');
  try {
    const res = await fetch('/api/lots');
    const data = await res.json();
    cachedLots = data.lots || [];

    // Populate Lot Selectors across the UI
    populateLotDropdowns(cachedLots);

    if (!container) return;

    if (cachedLots.length === 0) {
      container.innerHTML = '<p style="color:#64748b; padding:16px;">No parking lots found.</p>';
      return;
    }

    let html = '';
    cachedLots.forEach(lot => {
      let lotImageBanner = '';
      if (lot.lot_name.toLowerCase().includes('city') || (lot.location && lot.location.toLowerCase().includes('mangaluru'))) {
        lotImageBanner = `
          <div style="position:relative; height:140px; border-radius:10px; overflow:hidden; margin-bottom:14px; box-shadow:0 4px 14px rgba(0,0,0,0.08);">
            <img src="/static/images/city_parking_mangaluru.jpg" alt="${lot.lot_name}" style="width:100%; height:100%; object-fit:cover;">
            <div style="position:absolute; bottom:8px; left:8px; background:rgba(15,23,42,0.85); backdrop-filter:blur(4px); color:#ffffff; font-size:11px; font-weight:700; padding:3px 10px; border-radius:6px; display:flex; align-items:center; gap:6px;">
              <i class="fas fa-parking"></i> City Parking Facility • Mangaluru
            </div>
            <div style="position:absolute; top:8px; right:8px; background:rgba(16,185,129,0.95); color:#ffffff; font-size:11px; font-weight:800; padding:3px 10px; border-radius:6px;">
              ${lot.available_count ?? 0} Slots Free
            </div>
          </div>
        `;
      } else {
        lotImageBanner = `
          <div style="position:relative; height:90px; border-radius:10px; overflow:hidden; margin-bottom:14px; background:linear-gradient(135deg, #0d9488 0%, #1e293b 100%); display:flex; align-items:center; justify-content:space-between; padding:16px; color:#ffffff;">
            <div>
              <span class="badge" style="background:rgba(255,255,255,0.2); color:#ffffff; font-size:10px; margin-bottom:4px;">Facility #${lot.lot_id}</span>
              <div style="font-size:15px; font-weight:800;">${lot.lot_name}</div>
              <div style="font-size:11px; opacity:0.85;"><i class="fas fa-map-marker-alt"></i> ${lot.location}</div>
            </div>
            <div style="background:rgba(255,255,255,0.15); backdrop-filter:blur(4px); padding:8px 12px; border-radius:8px; text-align:center;">
              <div style="font-size:16px; font-weight:800;">${lot.available_count ?? 0}</div>
              <div style="font-size:9px; text-transform:uppercase; letter-spacing:0.5px; opacity:0.8;">Available</div>
            </div>
          </div>
        `;
      }

      html += `
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:14px; padding:18px; box-shadow:0 4px 12px rgba(15,23,42,0.04); position:relative;">
          ${lotImageBanner}
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">
            <div>
              <span class="badge badge-primary" style="font-size:11px; margin-bottom:4px;">Lot ID: #${lot.lot_id}</span>
              <h4 style="font-size:16px; font-weight:800; color:#0f172a; margin-top:2px;">${lot.lot_name}</h4>
              <p style="font-size:12px; color:#64748b; margin-top:2px;"><i class="fas fa-map-marker-alt" style="color:#ef4444;"></i> ${lot.location}</p>
            </div>
            <div style="display:flex; gap:6px;">
              <button class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="openAdminEditLotModal(${lot.lot_id})">
                <i class="fas fa-edit"></i> Edit
              </button>
              ${lot.lot_id !== 1 ? `
                <button class="btn-danger" style="padding:4px 8px; font-size:11px;" onclick="deleteParkingLotDirectly(${lot.lot_id})">
                  <i class="fas fa-trash"></i>
                </button>
              ` : ''}
            </div>
          </div>

          <!-- Specs Grid -->
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; background:#f8fafc; border-radius:10px; padding:10px; font-size:12px; margin-bottom:12px;">
            <div><span style="color:#64748b;">Floors:</span> <b>${lot.total_floors} Floors</b></div>
            <div><span style="color:#64748b;">Capacity:</span> <b>${lot.actual_slot_count || lot.total_slots} Slots</b></div>
            <div><span style="color:#64748b;">Hourly Rate:</span> <b>₹${lot.hourly_rate}/hr</b></div>
            <div><span style="color:#64748b;">Overstay Rate:</span> <b>₹${lot.overstay_penalty_rate}/hr</b></div>
            <div style="grid-column: span 2;"><span style="color:#64748b;"><i class="far fa-clock"></i> Hours:</span> <b>${lot.operating_hours || '24/7 (Open Daily)'}</b></div>
          </div>

          <!-- Live Status Pills -->
          <div style="display:flex; gap:6px; flex-wrap:wrap; font-size:11px; font-weight:700;">
            <span style="background:#ecfdf5; color:#059669; padding:3px 8px; border-radius:6px; border:1px solid #a7f3d0;">
              Available: ${lot.available_count ?? 0}
            </span>
            <span style="background:#eff6ff; color:#2563eb; padding:3px 8px; border-radius:6px; border:1px solid #bfdbfe;">
              Occupied: ${lot.occupied_count ?? 0}
            </span>
            <span style="background:#fffbeb; color:#d97706; padding:3px 8px; border-radius:6px; border:1px solid #fde68a;">
              Reserved: ${lot.reserved_count ?? 0}
            </span>
            <span style="background:#fef2f2; color:#dc2626; padding:3px 8px; border-radius:6px; border:1px solid #fecaca;">
              Overstayed: ${lot.overstayed_count ?? 0}
            </span>
            <span style="background:#f1f5f9; color:#475569; padding:3px 8px; border-radius:6px; border:1px solid #cbd5e1;">
              Maintenance: ${lot.disabled_count ?? 0}
            </span>
          </div>
        </div>
      `;
    });
    container.innerHTML = html;
  } catch (err) {
    console.error("Error loading parking lots config:", err);
  }
}

function populateLotDropdowns(lots) {
  const lotFilter = document.getElementById('slotsTableLotFilter');
  const newSlotLotSelect = document.getElementById('newSlotLotId');
  const editSlotLotSelect = document.getElementById('editSlotLotId');
  const resLotSelect = document.getElementById('resLotId');
  const exchangeLotSelect = document.getElementById('exchangeFilterLot');

  if (lotFilter) {
    const currentVal = lotFilter.value;
    let opts = '<option value="All">All Lots</option>';
    lots.forEach(l => {
      opts += `<option value="${l.lot_id}">Lot #${l.lot_id} - ${l.lot_name}</option>`;
    });
    lotFilter.innerHTML = opts;
    lotFilter.value = currentVal || 'All';
  }

  [newSlotLotSelect, editSlotLotSelect].forEach(sel => {
    if (sel) {
      const currentVal = sel.value;
      let opts = '';
      lots.forEach(l => {
        opts += `<option value="${l.lot_id}">Lot #${l.lot_id} - ${l.lot_name}</option>`;
      });
      sel.innerHTML = opts;
      if (currentVal) sel.value = currentVal;
    }
  });

  if (resLotSelect) {
    const currentVal = resLotSelect.value;
    const totalSlots = lots.reduce((acc, l) => acc + (l.actual_slot_count || l.total_slots || 0), 0);
    let opts = `<option value="all">All Parking Facilities (${totalSlots} Slots)</option>`;
    lots.forEach(l => {
      const count = l.actual_slot_count || l.total_slots;
      opts += `<option value="${l.lot_id}">Lot #${l.lot_id} - ${l.lot_name} (${count} Slots)</option>`;
    });
    resLotSelect.innerHTML = opts;
    if (currentVal && Array.from(resLotSelect.options).some(o => o.value === currentVal)) {
      resLotSelect.value = currentVal;
    } else {
      resLotSelect.value = '1';
    }
  }

  if (exchangeLotSelect) {
    const currentVal = exchangeLotSelect.value;
    let opts = '<option value="all">All Lots</option>';
    lots.forEach(l => {
      opts += `<option value="${l.lot_id}">${l.lot_name}</option>`;
    });
    exchangeLotSelect.innerHTML = opts;
    if (currentVal && Array.from(exchangeLotSelect.options).some(o => o.value === currentVal)) {
      exchangeLotSelect.value = currentVal;
    } else {
      exchangeLotSelect.value = 'all';
    }
  }
}

async function loadAllSlotsTable() {
  const container = document.getElementById('allSlotsTableContainer');
  if (!container) return;

  const lotFilterVal = document.getElementById('slotsTableLotFilter')?.value || 'All';
  const floorFilterVal = document.getElementById('slotsTableFloorFilter')?.value || 'All';
  const typeFilterVal = document.getElementById('slotsTableTypeFilter')?.value || 'All';
  const searchVal = document.getElementById('slotsTableSearchInput')?.value || '';

  try {
    let url = `/api/slots?status=${encodeURIComponent(currentSlotStatusFilter)}`;
    if (lotFilterVal !== 'All') url += `&lot_id=${encodeURIComponent(lotFilterVal)}`;
    if (floorFilterVal !== 'All') url += `&floor=${encodeURIComponent(floorFilterVal)}`;
    if (typeFilterVal !== 'All') url += `&slot_type=${encodeURIComponent(typeFilterVal)}`;
    if (searchVal) url += `&search=${encodeURIComponent(searchVal)}`;

    const res = await fetch(url);
    const data = await res.json();
    const slots = data.slots || [];

    const totalDisplay = document.getElementById('slotsTotalCountDisplay');
    if (totalDisplay) totalDisplay.innerText = data.count || slots.length;

    if (slots.length === 0) {
      container.innerHTML = '<p style="text-align:center; color:#64748b; padding:24px;">No slots found matching filter criteria.</p>';
      return;
    }

    let html = `
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Slot ID</th>
              <th>Slot No.</th>
              <th>Parking Lot</th>
              <th>Floor</th>
              <th>Zone / Bay</th>
              <th>Slot Type</th>
              <th>Status</th>
              <th>Current Plate / Vehicle</th>
              <th>Quick Status Override</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
    `;

    slots.forEach(s => {
      const statusLower = (s.status || 'available').toLowerCase();
      const badgeType = {
        'available': 'badge-success',
        'occupied': 'badge-primary',
        'reserved': 'badge-warning',
        'overstayed': 'badge-danger',
        'disabled': 'badge-light'
      }[statusLower] || 'badge-light';

      const typeBadgeColor = {
        'Standard': '#0f766e',
        'EV': '#0284c7',
        'Compact': '#7c3aed',
        'Disabled': '#ea580c',
        'VIP': '#b45309'
      }[s.slot_type] || '#475569';

      html += `
        <tr>
          <td><span style="font-family:'JetBrains Mono',monospace; font-size:12px; color:#64748b;">#SLT-${s.slot_id}</span></td>
          <td><b style="font-size:14px; color:#0f172a;">${s.slot_number}</b></td>
          <td><span style="font-size:12px; font-weight:600; color:#334155;">${s.lot_name || 'Lot #' + s.lot_id}</span></td>
          <td>${s.floor}</td>
          <td><span style="font-size:12px; color:#64748b;">${s.zone}</span></td>
          <td><span class="badge" style="background:#f1f5f9; color:${typeBadgeColor}; font-weight:700; border:1px solid #cbd5e1;">${s.slot_type}</span></td>
          <td><span class="badge ${badgeType}">${statusLower.toUpperCase()}</span></td>
          <td>${s.current_plate ? `<b style="color:#0f172a;">${s.current_plate}</b> ${s.user_name ? `<span style="font-size:11px; color:#64748b;">(${s.user_name})</span>` : ''}` : '<span style="color:#94a3b8;">-- Empty --</span>'}</td>
          <td>
            <select onchange="adminChangeSlotStatusDirectly(${s.slot_id}, this.value)" style="font-size:11px; padding:3px 6px; border-radius:6px; border:1.5px solid #cbd5e1; background:#ffffff; font-weight:600;">
              <option value="available" ${statusLower==='available'?'selected':''}>Available</option>
              <option value="reserved" ${statusLower==='reserved'?'selected':''}>Reserved</option>
              <option value="occupied" ${statusLower==='occupied'?'selected':''}>Occupied</option>
              <option value="overstayed" ${statusLower==='overstayed'?'selected':''}>Overstayed</option>
              <option value="disabled" ${statusLower==='disabled'?'selected':''}>Maintenance</option>
            </select>
          </td>
          <td>
            <div style="display:flex; gap:5px;">
              ${statusLower === 'available' ? `<button class="btn-primary" style="padding:4px 8px; font-size:11px;" onclick="openReservationForSlot(${s.slot_id}, '${s.slot_number}')">Book</button>` : ''}
              <button class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="openAdminEditSlotModal(${s.slot_id})" title="Edit Slot Details">
                <i class="fas fa-edit"></i>
              </button>
              <button class="btn-danger" style="padding:4px 8px; font-size:11px;" onclick="deleteSlotDirectly(${s.slot_id})" title="Delete Slot">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
  } catch (err) {
    console.error("All slots table error:", err);
  }
}

// -------------------------------------------------------------
// ADMIN LOT & SLOT MODAL ACTIONS
// -------------------------------------------------------------

function openAdminAddLotModal() {
  const modal = document.getElementById('adminAddLotModal');
  if (modal) modal.classList.add('active');
}

function closeAdminAddLotModal() {
  const modal = document.getElementById('adminAddLotModal');
  if (modal) modal.classList.remove('active');
}

async function submitAdminAddLot() {
  const lotName = document.getElementById('newLotName')?.value?.trim();
  const location = document.getElementById('newLotLocation')?.value?.trim();
  const totalFloors = parseInt(document.getElementById('newLotFloors')?.value || 1);
  const totalSlots = parseInt(document.getElementById('newLotSlots')?.value || 0);
  const hourlyRate = parseFloat(document.getElementById('newLotHourlyRate')?.value || 40);
  const penaltyRate = parseFloat(document.getElementById('newLotPenaltyRate')?.value || 100);

  if (!lotName || !location) {
    showToast('Please fill in both Lot Name and Location.', 'error');
    return;
  }

  const operatingHours = document.getElementById('newLotHours')?.value?.trim() || '24/7 (Open Daily)';

  try {
    const res = await fetch('/api/admin/lots/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lot_name: lotName,
        location: location,
        total_floors: totalFloors,
        total_slots: totalSlots,
        hourly_rate: hourlyRate,
        overstay_penalty_rate: penaltyRate,
        operating_hours: operatingHours
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeAdminAddLotModal();
      document.getElementById('newLotName').value = '';
      document.getElementById('newLotLocation').value = '';
      loadParkingLotsConfig();
      if (typeof loadAdminView === 'function') loadAdminView();
    } else {
      showToast(data.message || 'Failed to create parking lot.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error while creating parking lot.', 'error');
  }
}

async function openAdminEditLotModal(lotId) {
  try {
    const res = await fetch(`/api/lots/${lotId}`);
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || 'Lot not found.', 'error');
      return;
    }
    const lot = data.lot;
    document.getElementById('editLotId').value = lot.lot_id;
    document.getElementById('editLotName').value = lot.lot_name;
    document.getElementById('editLotLocation').value = lot.location;
    document.getElementById('editLotFloors').value = lot.total_floors;
    document.getElementById('editLotSlots').value = lot.total_slots;
    document.getElementById('editLotHourlyRate').value = lot.hourly_rate;
    document.getElementById('editLotPenaltyRate').value = lot.overstay_penalty_rate;
    const elHours = document.getElementById('editLotHours');
    if (elHours) elHours.value = lot.operating_hours || '24/7 (Open Daily)';

    const modal = document.getElementById('adminEditLotModal');
    if (modal) modal.classList.add('active');
  } catch (err) {
    console.error(err);
  }
}

function closeAdminEditLotModal() {
  const modal = document.getElementById('adminEditLotModal');
  if (modal) modal.classList.remove('active');
}

async function submitAdminEditLot() {
  const lotId = document.getElementById('editLotId')?.value;
  const lotName = document.getElementById('editLotName')?.value?.trim();
  const location = document.getElementById('editLotLocation')?.value?.trim();
  const totalFloors = parseInt(document.getElementById('editLotFloors')?.value || 1);
  const totalSlots = parseInt(document.getElementById('editLotSlots')?.value || 0);
  const hourlyRate = parseFloat(document.getElementById('editLotHourlyRate')?.value || 40);
  const penaltyRate = parseFloat(document.getElementById('editLotPenaltyRate')?.value || 100);
  const operatingHours = document.getElementById('editLotHours')?.value?.trim() || '24/7 (Open Daily)';

  if (!lotName || !location) {
    showToast('Lot Name and Location are required.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/admin/lots/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lot_id: lotId,
        lot_name: lotName,
        location: location,
        total_floors: totalFloors,
        total_slots: totalSlots,
        hourly_rate: hourlyRate,
        overstay_penalty_rate: penaltyRate,
        operating_hours: operatingHours
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeAdminEditLotModal();
      loadParkingLotsConfig();
      if (typeof loadAdminView === 'function') loadAdminView();
    } else {
      showToast(data.message || 'Failed to update parking lot.', 'error');
    }
  } catch (err) {
    console.error(err);
  }
}

async function deleteParkingLotDirectly(lotId) {
  if (!confirm(`Are you sure you want to delete Parking Lot #${lotId}?`)) return;
  try {
    const res = await fetch(`/api/admin/lots/${lotId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadParkingLotsConfig();
      loadAllSlotsTable();
      refreshAllDashboardData();
    } else {
      showToast(data.message || 'Failed to delete parking lot.', 'error');
    }
  } catch (err) {
    console.error(err);
  }
}

async function openAdminAddSlotModal() {
  await loadParkingLotsConfig();
  const modal = document.getElementById('adminAddSlotModal');
  if (modal) {
    modal.classList.add('active');
    modal.style.display = 'flex';
  }
}

function closeAdminAddSlotModal() {
  const modal = document.getElementById('adminAddSlotModal');
  if (modal) {
    modal.classList.remove('active');
    modal.style.display = '';
  }
}

async function submitAdminAddSlot() {
  const slotNumber = document.getElementById('newSlotNumber')?.value?.trim().toUpperCase();
  const lotId = parseInt(document.getElementById('newSlotLotId')?.value || 1);
  const floor = document.getElementById('newSlotFloor')?.value?.trim();
  const zone = document.getElementById('newSlotZone')?.value?.trim();
  const slotType = document.getElementById('newSlotType')?.value?.trim();
  const status = document.getElementById('newSlotStatus')?.value?.trim();
  const distEntry = parseInt(document.getElementById('newSlotDistEntry')?.value || 15);
  const distElev = parseInt(document.getElementById('newSlotDistElev')?.value || 20);
  const plate = document.getElementById('newSlotPlate')?.value?.trim().toUpperCase() || null;

  if (!slotNumber) {
    showToast('Slot Number is required.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/admin/slots/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        slot_number: slotNumber,
        lot_id: lotId,
        floor: floor,
        zone: zone,
        slot_type: slotType,
        status: status,
        distance_to_entry_m: distEntry,
        distance_to_elevator_m: distElev,
        current_plate: plate
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeAdminAddSlotModal();
      document.getElementById('newSlotNumber').value = '';
      if (document.getElementById('newSlotPlate')) document.getElementById('newSlotPlate').value = '';
      loadAllSlotsTable();
      refreshAllDashboardData();
      if (typeof loadAdminView === 'function') loadAdminView();
    } else {
      showToast(data.message || 'Failed to create slot.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error creating slot.', 'error');
  }
}

async function openAdminEditSlotModal(slotId) {
  try {
    const res = await fetch(`/api/slots/${slotId}`);
    const data = await res.json();
    if (!res.ok) {
      showToast(data.message || 'Slot not found.', 'error');
      return;
    }
    const slot = data.slot;
    document.getElementById('editSlotId').value = slot.slot_id;
    document.getElementById('editSlotNumber').value = slot.slot_number;
    document.getElementById('editSlotFloor').value = slot.floor;
    document.getElementById('editSlotZone').value = slot.zone;
    document.getElementById('editSlotType').value = slot.slot_type;
    document.getElementById('editSlotStatus').value = slot.status.toLowerCase();
    document.getElementById('editSlotPlate').value = slot.current_plate || '';

    populateLotDropdowns(cachedLots);
    if (document.getElementById('editSlotLotId')) {
      document.getElementById('editSlotLotId').value = slot.lot_id;
    }

    const modal = document.getElementById('adminEditSlotModal');
    if (modal) modal.classList.add('active');
  } catch (err) {
    console.error(err);
  }
}

function closeAdminEditSlotModal() {
  const modal = document.getElementById('adminEditSlotModal');
  if (modal) modal.classList.remove('active');
}

async function submitAdminEditSlot() {
  const slotId = document.getElementById('editSlotId')?.value;
  const slotNumber = document.getElementById('editSlotNumber')?.value?.trim().toUpperCase();
  const lotId = parseInt(document.getElementById('editSlotLotId')?.value || 1);
  const floor = document.getElementById('editSlotFloor')?.value?.trim();
  const zone = document.getElementById('editSlotZone')?.value?.trim();
  const slotType = document.getElementById('editSlotType')?.value?.trim();
  const status = document.getElementById('editSlotStatus')?.value?.trim();
  const plate = document.getElementById('editSlotPlate')?.value?.trim().toUpperCase();

  if (!slotNumber) {
    showToast('Slot number cannot be empty.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/admin/slots/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        slot_id: slotId,
        slot_number: slotNumber,
        lot_id: lotId,
        floor: floor,
        zone: zone,
        slot_type: slotType,
        status: status,
        current_plate: plate
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeAdminEditSlotModal();
      loadAllSlotsTable();
      refreshAllDashboardData();
      if (typeof loadAdminView === 'function') loadAdminView();
    } else {
      showToast(data.message || 'Failed to update slot.', 'error');
    }
  } catch (err) {
    console.error(err);
  }
}

async function adminChangeSlotStatusDirectly(slotId, newStatus) {
  try {
    const res = await fetch('/api/admin/slots/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot_id: slotId, status: newStatus })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Slot status updated to ${newStatus.toUpperCase()}.`, 'success');
      loadAllSlotsTable();
      refreshAllDashboardData();
      if (typeof loadAdminView === 'function') loadAdminView();
    } else {
      showToast(data.message || 'Status update failed.', 'error');
      loadAllSlotsTable();
    }
  } catch (err) {
    console.error(err);
  }
}

async function deleteSlotDirectly(slotId) {
  if (!confirm(`Are you sure you want to delete slot #${slotId}?`)) return;
  try {
    const res = await fetch(`/api/admin/slots/${slotId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAllSlotsTable();
      refreshAllDashboardData();
      if (typeof loadAdminView === 'function') loadAdminView();
    } else {
      showToast(data.message || 'Failed to delete slot.', 'error');
    }
  } catch (err) {
    console.error(err);
  }
}

async function saveLotConfiguration() {
  const lotName = document.getElementById('configLotName').value;
  const hourlyRate = document.getElementById('configHourlyRate').value;
  const penaltyRate = document.getElementById('configPenaltyRate').value;

  try {
    const res = await fetch('/api/lots/config/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lot_name: lotName, hourly_rate: hourlyRate, overstay_penalty_rate: penaltyRate })
    });
    const data = await res.json();
    showToast(data.message, 'success');
    loadParkingLotsConfig();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// MODULE 6: INTELLIGENT SLOT ALLOCATION
// ==========================================

let activePreferences = ['near_elevator', 'low_congestion', 'covered'];
let currentAllocationResult = null;
let currentSelectedAllocSlot = null;

function syncBookingDateConstraints() {
  const curDate = window.SYSTEM_CURRENT_DATE || getPcDateString();
  const dateInput = document.getElementById('resDate');
  if (dateInput) {
    dateInput.min = curDate;
    if (!dateInput.value || dateInput.value < curDate) {
      dateInput.value = curDate;
    }
    updateQuickDateButtonsHighlight(dateInput.value);
  }
  const predDate = document.getElementById('predDate');
  if (predDate) {
    predDate.min = curDate;
    if (!predDate.value || predDate.value < curDate) {
      predDate.value = curDate;
    }
  }
  const exchDate = document.getElementById('exchangeFilterDate');
  if (exchDate) {
    exchDate.min = curDate;
  }
}

function selectBookingDate(type) {
  const dateInput = document.getElementById('resDate');
  if (!dateInput) return;
  const curDateStr = window.SYSTEM_CURRENT_DATE || getPcDateString();
  const [y, m, d] = curDateStr.split('-').map(Number);
  const baseDt = new Date(y, m - 1, d);

  if (type === 'today') {
    dateInput.value = curDateStr;
  } else if (type === 'tomorrow') {
    baseDt.setDate(baseDt.getDate() + 1);
    const ty = baseDt.getFullYear();
    const tm = String(baseDt.getMonth() + 1).padStart(2, '0');
    const td = String(baseDt.getDate()).padStart(2, '0');
    dateInput.value = `${ty}-${tm}-${td}`;
  } else if (type === 'advance') {
    baseDt.setDate(baseDt.getDate() + 7);
    const ay = baseDt.getFullYear();
    const am = String(baseDt.getMonth() + 1).padStart(2, '0');
    const ad = String(baseDt.getDate()).padStart(2, '0');
    dateInput.value = `${ay}-${am}-${ad}`;
  }

  updateQuickDateButtonsHighlight(dateInput.value);
  findAiRecommendations();
}

function updateQuickDateButtonsHighlight(selectedDate) {
  const curDateStr = window.SYSTEM_CURRENT_DATE || getPcDateString();
  const [y, m, d] = curDateStr.split('-').map(Number);
  const tmDt = new Date(y, m - 1, d);
  tmDt.setDate(tmDt.getDate() + 1);
  const tmStr = `${tmDt.getFullYear()}-${String(tmDt.getMonth() + 1).padStart(2, '0')}-${String(tmDt.getDate()).padStart(2, '0')}`;

  const btnToday = document.getElementById('btnQuickDateToday');
  const btnTomorrow = document.getElementById('btnQuickDateTomorrow');
  const btnAdvance = document.getElementById('btnQuickDateAdvance');

  const styleActive = 'flex:1; padding:4px 6px; font-size:11px; font-weight:700; border-radius:6px; border:1px solid var(--primary); background:var(--primary); color:#ffffff; cursor:pointer;';
  const styleInactive = 'flex:1; padding:4px 6px; font-size:11px; font-weight:700; border-radius:6px; border:1px solid #cbd5e1; background:#f8fafc; color:#475569; cursor:pointer;';

  if (btnToday) btnToday.style.cssText = (selectedDate === curDateStr) ? styleActive : styleInactive;
  if (btnTomorrow) btnTomorrow.style.cssText = (selectedDate === tmStr) ? styleActive : styleInactive;
  if (btnAdvance) btnAdvance.style.cssText = (selectedDate > tmStr) ? styleActive : styleInactive;
}

function handleBookingDateChange() {
  const dateInput = document.getElementById('resDate');
  const timeInput = document.getElementById('resTime');
  if (!dateInput) return;
  const curDateStr = window.SYSTEM_CURRENT_DATE || getPcDateString();
  const pad = (n) => String(n).padStart(2, '0');
  const now = new Date();
  const nowTime = `${pad(now.getHours())}:${pad(now.getMinutes())}`;

  if (dateInput.value < curDateStr) {
    if (typeof showToast === 'function') {
      showToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'danger');
    }
    dateInput.value = curDateStr;
  }

  if (timeInput) {
    if (dateInput.value === curDateStr) {
      timeInput.min = nowTime;
      if (timeInput.value < nowTime) {
        timeInput.value = nowTime;
        if (typeof showToast === 'function') {
          showToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'danger');
        }
      }
    } else {
      timeInput.removeAttribute('min');
    }
  }

  updateQuickDateButtonsHighlight(dateInput.value);
  findAiRecommendations();
}

function calculateEndTime(start, durationHours) {
  if (!start) return '12:00';
  const parts = start.split(':');
  let h = parseInt(parts[0], 10) || 10;
  let m = parseInt(parts[1] || '0', 10);
  const totalMins = Math.round(h * 60 + m + parseFloat(durationHours || 2.0) * 60);
  const endH = Math.floor(totalMins / 60) % 24;
  const endM = totalMins % 60;
  return `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`;
}

function formatTimeRange(start, end) {
  if (!start) return '';
  const formatSingle = (t) => {
    if (!t) return '';
    const parts = t.split(':');
    let h = parseInt(parts[0], 10);
    const m = parts[1] || '00';
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    if (h === 0) h = 12;
    return `${h}:${m} ${ampm}`;
  };
  return `${formatSingle(start)} – ${formatSingle(end)}`;
}

function updateExpectedTimeRangeDisplay() {
  const time = document.getElementById('resTime')?.value || '10:00';
  const duration = parseFloat(document.getElementById('resDuration')?.value || 2.0);
  const end = calculateEndTime(time, duration);
  const el = document.getElementById('resExpectedTimeRange');
  if (el) {
    el.innerHTML = `<i class="far fa-clock"></i> Expected: <b>${formatTimeRange(time, end)}</b>`;
  }
}

function initReservationWizard() {
  const dateInput = document.getElementById('resDate');
  const timeInput = document.getElementById('resTime');
  const curDate = window.SYSTEM_CURRENT_DATE || getPcDateString();
  const pad = (n) => String(n).padStart(2, '0');
  const now = new Date();
  const nowTime = `${pad(now.getHours())}:${pad(now.getMinutes())}`;

  if (dateInput) {
    dateInput.min = curDate;
    if (!dateInput.value || dateInput.value < curDate) {
      dateInput.value = curDate;
    }
    updateQuickDateButtonsHighlight(dateInput.value);
  }
  if (timeInput) {
    if (dateInput && dateInput.value === curDate) {
      timeInput.min = nowTime;
      if (!timeInput.value || timeInput.value < nowTime) {
        timeInput.value = nowTime;
      }
    } else {
      timeInput.removeAttribute('min');
    }
    if (!timeInput.dataset.boundPastValidation) {
      timeInput.dataset.boundPastValidation = 'true';
      timeInput.addEventListener('focus', () => {
        handleBookingDateChange();
      });
      timeInput.addEventListener('change', () => {
        if (dateInput && dateInput.value === curDate) {
          const curNowTime = `${pad(new Date().getHours())}:${pad(new Date().getMinutes())}`;
          if (timeInput.value < curNowTime) {
            if (typeof showToast === 'function') {
              showToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'danger');
            }
            timeInput.value = curNowTime;
          }
        }
        updateExpectedTimeRangeDisplay();
        findAiRecommendations();
      });
    }
  }
  updateExpectedTimeRangeDisplay();
  findAiRecommendations();
}

function togglePrefPill(el) {
  const pref = el.getAttribute('data-pref');
  el.classList.toggle('active');
  if (el.classList.contains('active')) {
    if (!activePreferences.includes(pref)) activePreferences.push(pref);
  } else {
    activePreferences = activePreferences.filter(p => p !== pref);
  }
}

function handleLotPreferenceChange() {
  const lotId = document.getElementById('resLotId')?.value || 'all';
  const floorSelect = document.getElementById('resFloor');
  if (floorSelect) {
    if (lotId === '1') {
      floorSelect.value = 'Ground Floor';
    } else if (lotId === '2' || lotId === '3') {
      floorSelect.value = 'Upper Floor';
    } else if (lotId === '5') {
      floorSelect.value = 'Ground Floor';
    } else {
      floorSelect.value = 'All';
    }
  }
  updateExpectedTimeRangeDisplay();
  findAiRecommendations();
}

function updateAllocationStepIndicators(activeStep) {
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById(`stepIndicator${i}`);
    const sub = document.getElementById(`stepSub${i}`);
    if (!el || !sub) continue;

    el.classList.remove('completed', 'active');
    if (i < activeStep) {
      el.classList.add('completed');
      el.querySelector('.alloc-step-circle').innerHTML = '<i class="fas fa-check"></i>';
      sub.innerText = 'Completed';
    } else if (i === activeStep) {
      el.classList.add('active');
      el.querySelector('.alloc-step-circle').innerText = i;
      sub.innerText = 'In Progress';
    } else {
      el.querySelector('.alloc-step-circle').innerText = i;
      sub.innerText = 'Pending';
    }
  }
}

async function findAiRecommendations() {
  updateAllocationStepIndicators(3);

  const lotId = document.getElementById('resLotId')?.value || 'all';
  const date = document.getElementById('resDate')?.value || getPcDateString();
  const time = document.getElementById('resTime')?.value || '10:00';
  const duration = parseFloat(document.getElementById('resDuration')?.value || 2.0);
  const vehicleType = document.getElementById('resVehicleType')?.value || 'Car';
  const floor = document.getElementById('resFloor')?.value || 'All';

  const placeholder = document.getElementById('allocInitialPlaceholder');
  const banner = document.getElementById('allocTopMetricBanner');
  const visualMapContainer = document.getElementById('allocVisualMapAndDetailsContainer');
  const summarySection = document.getElementById('allocAiSummarySection');
  const rankedSection = document.getElementById('allocRankedCardsSection');
  const altSection = document.getElementById('allocAlternativesSection');

  if (placeholder) {
    placeholder.innerHTML = `
      <div style="text-align:center; padding:30px;"><i class="fas fa-spinner fa-spin fa-2x" style="color:var(--primary);"></i><p style="margin-top:10px; font-size:13px; color:#64748b;">Evaluating multi-factor suitability, gate distances, elevator access & checking double-booking guards...</p></div>
    `;
    placeholder.style.display = 'block';
  }
  if (banner) banner.style.display = 'none';
  if (visualMapContainer) visualMapContainer.style.display = 'none';
  if (summarySection) summarySection.style.display = 'none';
  if (rankedSection) rankedSection.style.display = 'none';
  if (altSection) altSection.style.display = 'none';

  try {
    const res = await fetch('/api/ai/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lot_id: lotId,
        date: date,
        time: time,
        duration: duration,
        vehicle_type: vehicleType,
        floor: floor,
        preferences: activePreferences,
        top_n: 6
      })
    });
    const data = await res.json();

    if (data.status === 'no_slots') {
      if (placeholder) placeholder.style.display = 'none';
      renderAllocAlternatives(data);
      updateAllocationStepIndicators(3);
      return;
    }

    currentAllocationResult = data;
    const bestSlot = data.best_slot;
    currentSelectedAllocSlot = bestSlot;

    if (placeholder) placeholder.style.display = 'none';
    if (banner) banner.style.display = 'block';
    if (visualMapContainer) visualMapContainer.style.display = 'grid';
    if (summarySection) summarySection.style.display = 'block';
    if (rankedSection) rankedSection.style.display = 'block';

    updateAllocationStepIndicators(4);

    // Render components
    selectAllocSlot(bestSlot ? bestSlot.slot_id : null);
    renderAllocAiSummary(data.analysis_summary);
    renderAllocRankedGrid(data.recommendations, bestSlot ? bestSlot.slot_id : null);

  } catch (err) {
    console.error("AI recommendation error:", err);
    if (placeholder) {
      placeholder.innerHTML = `<p style="font-size:12px; color:#ef4444;">Network error while computing slot allocation.</p>`;
    }
  }
}

function selectAllocSlot(slotId) {
  if (!currentAllocationResult || !currentAllocationResult.recommendations) return;
  const slot = currentAllocationResult.recommendations.find(s => s.slot_id === slotId) || currentAllocationResult.best_slot;
  if (!slot) return;

  currentSelectedAllocSlot = slot;

  // 1. Update Top Banner (Matching Screenshot 1)
  const banner = document.getElementById('allocTopMetricBanner');
  if (banner) {
    banner.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px;">
        <div>
          <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
            <div style="width:24px; height:24px; border-radius:50%; background:#ecfdf5; color:#059669; display:flex; align-items:center; justify-content:center; font-size:12px;">
              <i class="fas fa-check"></i>
            </div>
            <h3 style="font-size:16px; font-weight:800; color:#0f172a; margin:0;">Best Slot Allocated!</h3>
          </div>
          <p style="font-size:12px; color:#64748b; margin:0 0 12px 32px;">Based on AI analysis, this slot best matches your vehicle and preferences.</p>

          <div style="display:flex; gap:10px; flex-wrap:wrap; margin-left:32px;">
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:6px 12px; font-size:11px;">
              <span style="color:#64748b; display:block; font-size:10px;">Match Score</span>
              <strong style="color:#059669; font-size:13px;">${slot.suitability_score}%</strong>
            </div>

            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:6px 12px; font-size:11px;">
              <span style="color:#64748b; display:block; font-size:10px;">Walk Distance</span>
              <strong style="color:#0f172a; font-size:13px;"><i class="fas fa-walking" style="color:var(--primary); font-size:11px;"></i> ${slot.walk_distance_m || slot.distance_to_entry_m} m</strong>
            </div>

            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:6px 12px; font-size:11px;">
              <span style="color:#64748b; display:block; font-size:10px;">Congestion Level</span>
              <strong style="color:#059669; font-size:13px;"><i class="fas fa-users" style="font-size:11px;"></i> ${slot.congestion_level || 'Low'}</strong>
            </div>

            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:6px 12px; font-size:11px;">
              <span style="color:#64748b; display:block; font-size:10px;">Near Elevator</span>
              <strong style="color:#0f172a; font-size:13px;">${slot.near_elevator || 'Yes'}</strong>
            </div>

            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:6px 12px; font-size:11px;">
              <span style="color:#64748b; display:block; font-size:10px;">Coverage</span>
              <strong style="color:#2563eb; font-size:13px;"><i class="fas fa-shield-alt" style="font-size:11px;"></i> ${slot.coverage || 'Covered'}</strong>
            </div>
          </div>
        </div>

        <div style="text-align:right; border-left:1px solid #e2e8f0; padding-left:20px; min-width:180px;">
          <span style="font-size:11px; text-transform:uppercase; color:#94a3b8; font-weight:700;">Recommended Slot</span>
          <div style="font-size:24px; font-weight:900; color:#0f172a; line-height:1.1;">Slot ${slot.slot_number}</div>
          <span style="font-size:12px; color:#64748b;">${slot.floor} • ${slot.lot_name || 'City Parking'}</span>
          <div style="margin-top:6px;">
            <span style="background:#ecfdf5; color:#059669; border:1px solid #a7f3d0; padding:2px 8px; border-radius:99px; font-size:10px; font-weight:800;">
              <i class="fas fa-check-circle" style="font-size:9px;"></i> Available (Best Match)
            </span>
          </div>
          <div style="margin-top:6px; font-size:11px; color:#475569;">
            <b>Distance:</b> ${slot.walk_distance_m || slot.distance_to_entry_m || 50}m from entrance
          </div>
        </div>
      </div>

      <!-- Module 6: Other Available Slots Row (Matching Card 6 Mockup) -->
      <div style="margin-top:12px; padding-top:10px; border-top:1px solid #f1f5f9; display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
        <span style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase;">Other Available Slots:</span>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          ${(allocRecommendationList || []).slice(0, 6).map(r => `
            <button type="button" class="btn-sim-tick ${r.slot_id === slot.slot_id ? 'active' : ''}" style="font-size:11px; padding:3px 10px; border-radius:6px; font-weight:800;" onclick="selectAllocSlot(${r.slot_id})">
              ${r.slot_number}
            </button>
          `).join('')}
        </div>
      </div>
    `;
  }

  // 2. Update Visual Map
  renderAllocInteractiveMap(slot);

  // 3. Update Why Recommended Checklist
  const whyList = document.getElementById('allocWhyRecommendedList');
  if (whyList) {
    const bullets = slot.why_recommended || [
      `Nearest to elevator (${slot.distance_to_elevator_m}m)`,
      'Low congestion in this area',
      'Covered parking area',
      'Matches your duration',
      'High availability',
      'Good entry & exit path'
    ];
    let html = '';
    bullets.forEach(b => {
      html += `
        <li style="display:flex; align-items:center; gap:8px;">
          <i class="fas fa-check" style="color:#059669; font-size:11px;"></i>
          <span>${b}</span>
        </li>
      `;
    });
    whyList.innerHTML = html;
  }

  // 4. Update Slot Details
  const detailsBox = document.getElementById('allocSlotDetailsBox');
  if (detailsBox) {
    detailsBox.innerHTML = `
      <div style="display:flex; justify-content:space-between;"><span style="color:#64748b;">Slot Number:</span><strong style="color:#0f172a;">${slot.slot_number}</strong></div>
      <div style="display:flex; justify-content:space-between;"><span style="color:#64748b;">Floor:</span><span>${slot.floor}</span></div>
      <div style="display:flex; justify-content:space-between;"><span style="color:#64748b;">Zone:</span><span>${slot.zone}</span></div>
      <div style="display:flex; justify-content:space-between;"><span style="color:#64748b;">Type:</span><span class="badge badge-info" style="font-size:10px;">${slot.slot_type}</span></div>
      <div style="display:flex; justify-content:space-between;"><span style="color:#64748b;">Distance to Elevator:</span><span>${slot.distance_to_elevator_m} meters</span></div>
      <div style="display:flex; justify-content:space-between;"><span style="color:#64748b;">Hourly Rate:</span><strong style="color:#059669;">₹${slot.hourly_rate || 40} / hr</strong></div>
      <div style="display:flex; justify-content:space-between;"><span style="color:#64748b;">Availability:</span><span style="color:#059669; font-weight:700;">● Available</span></div>
    `;
  }

  // Highlight selected card in the ranked grid below
  document.querySelectorAll('.ranked-slot-card').forEach(c => {
    if (parseInt(c.getAttribute('data-slot-id')) === slot.slot_id) {
      c.classList.add('selected');
      const btn = c.querySelector('.btn-slot-select');
      if (btn) btn.innerText = 'Selected ✔';
    } else {
      c.classList.remove('selected');
      const btn = c.querySelector('.btn-slot-select');
      if (btn) btn.innerText = 'Select Slot';
    }
  });
}

function renderAllocInteractiveMap(selectedSlot) {
  const canvas = document.getElementById('allocInteractiveMapCanvas');
  const titleEl = document.getElementById('allocLayoutMapTitle');
  const floorTag = document.getElementById('allocLayoutFloorTag');
  const elevEl = document.getElementById('allocMapElevDistance');
  const congEl = document.getElementById('allocMapCongestion');

  if (titleEl) titleEl.innerText = `Parking Layout — ${selectedSlot.lot_name || 'Parking Facility'}`;
  if (floorTag) floorTag.innerText = selectedSlot.floor || 'Ground Floor';
  if (elevEl) elevEl.innerHTML = `<i class="fas fa-walking"></i> ${selectedSlot.distance_to_elevator_m || 12} meters from Elevator`;
  if (congEl) congEl.innerHTML = `<i class="fas fa-users"></i> ${selectedSlot.congestion_level || 'Low'} congestion area`;

  if (!canvas) return;

  const lotIdStr = String(selectedSlot.lot_id || document.getElementById('resLotId')?.value || '');
  const isCityParking = lotIdStr === '5' || 
    (selectedSlot.lot_name && selectedSlot.lot_name.toLowerCase().includes('city parking')) ||
    (selectedSlot.slot_number && /^[A-H]\d+$/i.test(selectedSlot.slot_number));

  if (isCityParking) {
    // City Parking Physical Layout (Rows A, B, C with 4 slots each)
    const rows = [
      {
        name: 'Row A',
        slots: [
          { num: 'A1', type: 'Regular', status: 'available', label: '🟢 Available' },
          { num: 'A2', type: 'VIP', status: 'reserved', label: '🟡 Reserved' },
          { num: 'A3', type: 'Accessible', status: 'occupied', label: '🔴 Occupied' },
          { num: 'A4', type: 'EV', status: 'overstayed', label: '🔴 Overstayed' }
        ]
      },
      {
        name: 'Row B',
        slots: [
          { num: 'B1', type: 'Regular', status: 'available', label: '🟢 Available' },
          { num: 'B2', type: 'VIP', status: 'available', label: '🟢 Available' },
          { num: 'B3', type: 'Accessible', status: 'available', label: '🟢 Available' },
          { num: 'B4', type: 'EV', status: 'available', label: '🟢 Available' }
        ]
      },
      {
        name: 'Row C',
        slots: [
          { num: 'C1', type: 'Regular', status: 'available', label: '🟢 Available' },
          { num: 'C2', type: 'VIP', status: 'available', label: '🟢 Available' },
          { num: 'C3', type: 'Accessible', status: 'available', label: '🟢 Available' },
          { num: 'C4', type: 'EV', status: 'available', label: '🟢 Available' }
        ]
      }
    ];

    let html = `<div style="display:flex; flex-direction:column; gap:8px; width:100%;">`;
    rows.forEach(r => {
      html += `
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:11px; font-weight:800; color:#94a3b8; width:45px; text-transform:uppercase;">${r.name}</span>
          <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:8px; flex:1;">
            ${r.slots.map(s => {
              const isSel = selectedSlot.slot_number === s.num;
              let bg = '#10b981'; // available
              if (isSel) bg = '#f59e0b'; // selected
              else if (s.status === 'occupied') bg = '#ef4444'; // occupied
              else if (s.status === 'reserved') bg = '#eab308'; // reserved
              else if (s.status === 'overstayed') bg = '#dc2626'; // overstayed

              return `
                <div style="background:${bg}; border-radius:6px; padding:6px 4px; text-align:center; cursor:pointer; position:relative; box-shadow:0 2px 4px rgba(0,0,0,0.25); transition:transform 0.15s;" 
                     onclick="selectAllocSlotByNumber('${s.num}')" 
                     title="${s.num}: ${s.status.toUpperCase()} (${s.type})">
                  <div style="font-size:12px; font-weight:900; color:#ffffff;">${s.num}</div>
                  <div style="font-size:9px; font-weight:700; color:rgba(255,255,255,0.95);">${s.label}</div>
                  <div style="font-size:8px; color:rgba(255,255,255,0.75); text-transform:uppercase;">${s.type}</div>
                  ${isSel ? `<div class="slot-pin-marker" style="top:-22px; left:50%; margin-left:-14px;"><i class="fas fa-map-marker-alt"></i></div>` : ''}
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
      if (r.name !== 'Row C') {
        html += `
          <div style="height:12px; background:#0f172a; border-top:1px dashed #475569; border-bottom:1px dashed #475569; border-radius:2px; display:flex; align-items:center; justify-content:center; color:#94a3b8; font-size:9px; font-weight:800; letter-spacing:1px;">
            ================ DRIVE LANE ================
          </div>
        `;
      }
    });
    html += `</div>`;
    canvas.innerHTML = html;
    return;
  }

  // Fallback for default layout (Institutions S/R bays)
  canvas.innerHTML = `
    <!-- Top Perimeter Bay -->
    <div style="display:flex; justify-content:space-between; gap:6px; margin-bottom:8px;">
      ${['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8'].map((snum, idx) => {
        const isSel = selectedSlot.slot_number === snum;
        const isOcc = (idx === 3 || idx === 7) && !isSel;
        const isRes = idx === 5 && !isSel;
        let bg = '#10b981';
        if (isSel) bg = '#f59e0b';
        else if (isOcc) bg = '#ef4444';
        else if (isRes) bg = '#3b82f6';
        return `
          <div style="flex:1; height:36px; background:${bg}; border-radius:4px; font-size:11px; font-weight:800; color:#ffffff; display:flex; align-items:center; justify-content:center; cursor:pointer; position:relative; box-shadow:0 1px 3px rgba(0,0,0,0.3);" onclick="selectAllocSlotByNumber('${snum}')">
            ${snum}
            ${isSel ? `<div class="slot-pin-marker" style="top:-22px; left:50%; margin-left:-14px;"><i class="fas fa-map-marker-alt"></i></div>` : ''}
          </div>
        `;
      }).join('')}
    </div>

    <!-- Middle Driveway with Center Island (Elevator & Stairs) -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin:10px 0; padding:0 8px;">
      <!-- Left Side Bay -->
      <div style="display:flex; flex-direction:column; gap:6px; width:44px;">
        ${['R1', 'R2'].map(snum => {
          const isSel = selectedSlot.slot_number === snum;
          return `
            <div style="height:32px; background:${isSel ? '#f59e0b' : '#10b981'}; border-radius:4px; font-size:10px; font-weight:800; color:#ffffff; display:flex; align-items:center; justify-content:center; cursor:pointer; position:relative;" onclick="selectAllocSlotByNumber('${snum}')">
              ${snum}
              ${isSel ? `<div class="slot-pin-marker" style="top:-20px; left:50%; margin-left:-14px;"><i class="fas fa-map-marker-alt"></i></div>` : ''}
            </div>
          `;
        }).join('')}
      </div>

      <!-- Center Island: Elevator Lobby / Driveway -->
      <div style="flex:1; margin:0 14px; background:#0f172a; border:1.5px dashed #475569; border-radius:8px; padding:10px 14px; display:flex; flex-direction:column; align-items:center; justify-content:center;">
        <div style="display:flex; gap:10px; margin-bottom:8px; width:100%; justify-content:center;">
          ${['R4', 'R5', 'R6', 'R7'].map((snum, idx) => {
            const isSel = selectedSlot.slot_number === snum;
            const isOcc = idx === 1 && !isSel;
            let bg = '#10b981';
            if (isSel) bg = '#f59e0b';
            else if (isOcc) bg = '#ef4444';
            return `
              <div style="width:48px; height:34px; background:${bg}; border-radius:4px; font-size:11px; font-weight:800; color:#ffffff; display:flex; align-items:center; justify-content:center; cursor:pointer; position:relative;" onclick="selectAllocSlotByNumber('${snum}')">
                ${snum}
                ${isSel ? `<div class="slot-pin-marker" style="top:-22px; left:50%; margin-left:-14px;"><i class="fas fa-map-marker-alt"></i></div>` : ''}
              </div>
            `;
          }).join('')}
        </div>
        
        <div style="display:flex; align-items:center; gap:8px; color:#cbd5e1; font-size:11px; font-weight:800; letter-spacing:0.5px; text-transform:uppercase;">
          <i class="fas fa-bars" style="font-size:10px;"></i>
          <span>LIFT / ELEVATOR / STAIRS</span>
          <i class="fas fa-bars" style="font-size:10px;"></i>
        </div>
      </div>

      <!-- Right Side Bay -->
      <div style="display:flex; flex-direction:column; gap:6px; width:44px;">
        ${['R10', 'R11'].map(snum => {
          const isSel = selectedSlot.slot_number === snum;
          return `
            <div style="height:32px; background:${isSel ? '#f59e0b' : '#10b981'}; border-radius:4px; font-size:10px; font-weight:800; color:#ffffff; display:flex; align-items:center; justify-content:center; cursor:pointer; position:relative;" onclick="selectAllocSlotByNumber('${snum}')">
              ${snum}
              ${isSel ? `<div class="slot-pin-marker" style="top:-20px; left:50%; margin-left:-14px;"><i class="fas fa-map-marker-alt"></i></div>` : ''}
            </div>
          `;
        }).join('')}
      </div>
    </div>

    <!-- Bottom Perimeter Bay -->
    <div style="display:flex; justify-content:space-between; gap:6px; margin-top:8px;">
      ${['R22', 'R23', 'R24', 'R25', 'R26', 'R27', 'R28', 'R29'].map((snum, idx) => {
        const isSel = selectedSlot.slot_number === snum;
        const isOcc = idx === 4 && !isSel;
        let bg = '#10b981';
        if (isSel) bg = '#f59e0b';
        else if (isOcc) bg = '#ef4444';
        return `
          <div style="flex:1; height:36px; background:${bg}; border-radius:4px; font-size:11px; font-weight:800; color:#ffffff; display:flex; align-items:center; justify-content:center; cursor:pointer; position:relative; box-shadow:0 1px 3px rgba(0,0,0,0.3);" onclick="selectAllocSlotByNumber('${snum}')">
            ${snum}
            ${isSel ? `<div class="slot-pin-marker" style="top:-22px; left:50%; margin-left:-14px;"><i class="fas fa-map-marker-alt"></i></div>` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;
}

async function selectAllocSlotByNumber(slotNumber) {
  if (currentAllocationResult && currentAllocationResult.recommendations) {
    const found = currentAllocationResult.recommendations.find(s => s.slot_number === slotNumber);
    if (found) {
      selectAllocSlot(found.slot_id);
      return;
    }
  }

  // Fetch slot from API if not in current top recommendations
  try {
    const lotId = document.getElementById('resLotId')?.value || '5';
    let url = `/api/slots?search=${encodeURIComponent(slotNumber)}`;
    if (lotId !== 'all') url += `&lot_id=${encodeURIComponent(lotId)}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.slots && data.slots.length > 0) {
      const slot = data.slots[0];
      const duration = parseFloat(document.getElementById('resDuration')?.value || 2.0);
      slot.suitability_score = slot.status === 'available' ? 95 : 60;
      slot.walk_distance_m = slot.distance_to_entry_m || 12;
      slot.congestion_level = 'Low';
      slot.near_elevator = (slot.distance_to_elevator_m <= 15) ? 'Yes' : 'No';
      slot.coverage = 'Covered';
      slot.total_amount = Math.round(duration * (slot.hourly_rate || 40.0) * 100) / 100;
      slot.why_recommended = [
        `Selected slot ${slot.slot_number} in ${slot.lot_name}`,
        `${slot.slot_type} parking bay on ${slot.floor}`,
        `Current Status: ${slot.status.toUpperCase()}`
      ];
      
      if (currentAllocationResult) {
        if (!currentAllocationResult.recommendations) currentAllocationResult.recommendations = [];
        if (!currentAllocationResult.recommendations.some(s => s.slot_id === slot.slot_id)) {
          currentAllocationResult.recommendations.unshift(slot);
        }
      }
      selectAllocSlot(slot.slot_id);
      
      if (slot.status !== 'available') {
        showToast(`Note: Slot ${slot.slot_number} is currently ${slot.status}. Availability for your chosen time will be checked upon confirmation.`, 'warning');
      }
    }
  } catch (err) {
    console.error("Error selecting slot by number:", err);
  }
}

function renderAllocAiSummary(summary) {
  const container = document.getElementById('allocAiSummaryGrid');
  if (!container || !summary) return;

  container.innerHTML = `
    <div class="ai-kpi-summary-card">
      <div class="ai-kpi-icon-box" style="background:#eff6ff; color:#2563eb;">
        <i class="fas fa-users"></i>
      </div>
      <div>
        <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">Current Occupancy</span>
        <strong style="font-size:15px; color:#0f172a;">${summary.current_occupancy}</strong>
        <span style="font-size:10px; color:${summary.occupancy_status === 'High' ? '#ef4444' : '#059669'}; font-weight:700; margin-left:4px;">${summary.occupancy_status}</span>
      </div>
    </div>

    <div class="ai-kpi-summary-card">
      <div class="ai-kpi-icon-box" style="background:#fef3c7; color:#d97706;">
        <i class="far fa-clock"></i>
      </div>
      <div>
        <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">Peak Time</span>
        <strong style="font-size:12px; color:#0f172a; display:block;">${summary.peak_time}</strong>
      </div>
    </div>

    <div class="ai-kpi-summary-card">
      <div class="ai-kpi-icon-box" style="background:#ecfdf5; color:#059669;">
        <i class="fas fa-chart-line"></i>
      </div>
      <div>
        <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">Demand Forecast</span>
        <strong style="font-size:14px; color:#0f172a;">${summary.demand_forecast}</strong>
        <span style="font-size:10px; color:#64748b; display:block;">For Requested Time</span>
      </div>
    </div>

    <div class="ai-kpi-summary-card">
      <div class="ai-kpi-icon-box" style="background:#eff6ff; color:#3b82f6;">
        <i class="fas fa-bullseye"></i>
      </div>
      <div>
        <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">Optimal Slot Fit</span>
        <strong style="font-size:15px; color:#2563eb;">${summary.optimal_slot_fit}</strong>
        <span style="font-size:10px; color:#64748b; display:block;">Match Score</span>
      </div>
    </div>

    <div class="ai-kpi-summary-card">
      <div class="ai-kpi-icon-box" style="background:#faf5ff; color:#7c3aed;">
        <i class="fas fa-brain"></i>
      </div>
      <div>
        <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">AI Recommendation</span>
        <strong style="font-size:12px; color:#0f172a; display:block;">Best Available Slot</strong>
        <span style="font-size:10px; color:#7c3aed; font-weight:600;">Based on real-time data</span>
      </div>
    </div>
  `;
}

function renderAllocRankedGrid(recs, selectedSlotId) {
  const container = document.getElementById('allocRankedSlotsContainer');
  if (!container || !recs) return;

  let html = '';
  recs.slice(0, 4).forEach((r, idx) => {
    const isSelected = r.slot_id === selectedSlotId;
    html += `
      <div class="ranked-slot-card ${isSelected ? 'selected' : ''}" data-slot-id="${r.slot_id}">
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <h4 style="font-size:14px; font-weight:800; color:#0f172a; margin:0;">${r.lot_name ? r.lot_name.substring(0, 10) : 'Bay'} - ${r.floor} - Slot ${r.slot_number}</h4>
            <span class="badge badge-success" style="font-size:10px; padding:2px 6px;">Available</span>
          </div>

          <!-- Mini Layout Graphic -->
          <div class="mini-map-preview">
            <div style="display:flex; gap:4px;">
              <div style="width:28px; height:45px; background:#e2e8f0; border-radius:3px;"></div>
              <div style="width:34px; height:45px; background:#10b981; border-radius:3px; display:flex; align-items:center; justify-content:center; color:#ffffff; font-weight:800; font-size:10px; box-shadow:0 2px 5px rgba(16,185,129,0.3);">
                ${r.slot_number}
              </div>
              <div style="width:28px; height:45px; background:#e2e8f0; border-radius:3px;"></div>
            </div>
          </div>

          <div style="font-size:11px; color:#64748b; line-height:1.6; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between;">
              <span><i class="fas fa-location-arrow" style="font-size:10px; margin-right:4px;"></i> Distance:</span>
              <strong style="color:#0f172a;">${r.walk_distance_m || r.distance_to_entry_m} meters</strong>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span><i class="fas fa-walking" style="font-size:10px; margin-right:4px;"></i> Walking Time:</span>
              <span>${r.walking_time_mins || 1} min${(r.walking_time_mins || 1) > 1 ? 's' : ''}</span>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span><i class="fas fa-check-circle" style="color:#059669; font-size:10px; margin-right:4px;"></i> Suitability Score:</span>
              <strong style="color:#059669;">${r.suitability_score}%</strong>
            </div>
          </div>
        </div>

        <button class="btn-secondary btn-slot-select" style="width:100%; font-size:12px; font-weight:800; padding:8px;" onclick="selectAllocSlot(${r.slot_id})">
          ${isSelected ? 'Selected ✔' : 'Select Slot'}
        </button>
      </div>
    `;
  });

  container.innerHTML = html;
}

function renderAllocAlternatives(data) {
  const altSection = document.getElementById('allocAlternativesSection');
  if (!altSection) return;

  altSection.style.display = 'block';
  const alts = data.alternatives || [];

  let altsHtml = `
    <div style="display:flex; align-items:flex-start; gap:14px; margin-bottom:12px;">
      <div style="width:40px; height:40px; border-radius:50%; background:#fee2e2; color:#ef4444; display:flex; align-items:center; justify-content:center; font-size:18px; flex-shrink:0;">
        <i class="fas fa-exclamation-circle"></i>
      </div>
      <div>
        <h4 style="font-size:15px; font-weight:800; color:#991b1b; margin:0 0 4px 0;">No suitable parking slot is available for your selected requirements.</h4>
        <p style="font-size:12px; color:#7f1d1d; margin:0;">All slots matching this lot, floor, and time window are either booked or conflict with existing reservations.</p>
      </div>
    </div>
  `;

  if (alts.length > 0) {
    altsHtml += `
      <h5 style="font-size:12px; font-weight:800; color:#92400e; margin:12px 0 8px 0; text-transform:uppercase;">Suggested Alternatives:</h5>
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:10px;">
    `;
    alts.forEach(a => {
      altsHtml += `
        <div style="background:#ffffff; border:1px solid #fde68a; border-radius:8px; padding:10px 14px; display:flex; flex-direction:column; justify-content:space-between;">
          <div>
            <strong style="font-size:12px; color:#92400e; display:block;">${a.title}</strong>
            <span style="font-size:11px; color:#78350f;">${a.description}</span>
          </div>
          <button class="btn-secondary" style="font-size:11px; padding:4px 8px; margin-top:8px; font-weight:700;" onclick="applyAlternativeSuggestion('${a.type}', '${a.suggested_lot_id || a.suggested_floor || a.suggested_time}')">
            Apply Suggestion
          </button>
        </div>
      `;
    });
    altsHtml += `</div>`;
  }

  altSection.innerHTML = altsHtml;
}

function applyAlternativeSuggestion(type, value) {
  if (type === 'lot') {
    const lotSel = document.getElementById('resLotId');
    if (lotSel) lotSel.value = value;
  } else if (type === 'floor') {
    const floorSel = document.getElementById('resFloor');
    if (floorSel) floorSel.value = value;
  } else if (type === 'time') {
    const timeIn = document.getElementById('resTime');
    if (timeIn) timeIn.value = value;
  }
  findAiRecommendations();
}

function openReviewBookingSummaryModal() {
  if (!currentSelectedAllocSlot) {
    showToast('Please select a parking slot first.', 'warning');
    return;
  }

  const slot = currentSelectedAllocSlot;
  const date = document.getElementById('resDate')?.value || getPcDateString();
  const startTime = document.getElementById('resTime')?.value || '10:00';
  const duration = parseFloat(document.getElementById('resDuration')?.value || 2.0);
  const plate = (document.getElementById('resPlate')?.value || 'KA01AB1234').trim().toUpperCase();
  const driverName = document.getElementById('resDriverName')?.value || 'Spoorthi Shetty';

  if (!plate) {
    showToast('Please enter your vehicle license plate number.', 'error');
    return;
  }

  const modal = document.getElementById('reviewBookingSummaryModal');
  const body = document.getElementById('reviewBookingSummaryBody');

  if (body) {
    body.innerHTML = `
      <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; margin-bottom:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <div>
            <span style="font-size:11px; text-transform:uppercase; color:#94a3b8; font-weight:700;">Selected Slot</span>
            <div style="font-size:18px; font-weight:800; color:#0f172a;">Slot ${slot.slot_number} (${slot.floor})</div>
          </div>
          <span class="badge badge-success" style="font-size:12px; padding:4px 10px;">${slot.suitability_score}% Match</span>
        </div>
        <p style="font-size:12px; color:#64748b; margin:0;">${slot.lot_name || 'Parking Facility'}</p>
      </div>

      <div style="grid-template-columns:1fr 1fr; gap:10px; font-size:12px; margin-bottom:14px; background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px;">
        <div><span style="color:#64748b;">Parking:</span> <strong>${slot.lot_name || 'City Parking'}</strong></div>
        <div><span style="color:#64748b;">Slot:</span> <strong>Slot ${slot.slot_number}</strong> (${slot.floor})</div>
        <div><span style="color:#64748b;">Date:</span> <strong>${date}</strong></div>
        <div><span style="color:#64748b;">Time:</span> <strong>${formatTimeRange(startTime, calculateEndTime(startTime, duration))}</strong></div>
        <div><span style="color:#64748b;">Duration:</span> <strong>${duration} Hours</strong></div>
        <div><span style="color:#64748b;">Slot Type:</span> <strong>${slot.slot_type}</strong></div>
        <div><span style="color:#64748b;">Vehicle Plate:</span> <strong>${plate}</strong></div>
        <div><span style="color:#64748b;">Status:</span> <strong style="color:#059669;">Confirmed Upon Booking</strong></div>
      </div>

      <div style="background:#ecfdf5; border:1px solid #a7f3d0; border-radius:8px; padding:10px 14px; display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
        <div>
          <span style="font-size:11px; color:#065f46; font-weight:700;">Total Parking Amount</span>
          <div style="font-size:18px; font-weight:900; color:#059669;">₹${slot.total_amount || (duration * (slot.hourly_rate || 40))}</div>
        </div>
        <span style="font-size:11px; color:#047857;"><i class="fas fa-lock"></i> Free Cancellation</span>
      </div>

      <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:8px 12px; font-size:11px; color:#1e40af; display:flex; align-items:center; gap:8px;">
        <i class="fas fa-shield-alt" style="color:#2563eb;"></i>
        <span>Live Availability Check: No conflicting booking detected for this slot.</span>
      </div>
    `;
  }

  if (modal) {
    modal.classList.add('active');
    modal.style.display = 'flex';
  }
}

function closeReviewBookingSummaryModal() {
  const modal = document.getElementById('reviewBookingSummaryModal');
  if (modal) {
    modal.classList.remove('active');
    modal.style.display = '';
  }
}

async function confirmFinalBooking() {
  if (!currentSelectedAllocSlot) return;

  const slot = currentSelectedAllocSlot;
  const date = document.getElementById('resDate')?.value || getPcDateString();
  const startTime = document.getElementById('resTime')?.value || '10:00';
  const duration = parseFloat(document.getElementById('resDuration')?.value || 2.0);
  const plate = (document.getElementById('resPlate')?.value || 'KA01AB1234').trim().toUpperCase();
  const driverName = document.getElementById('resDriverName')?.value || 'Spoorthi Shetty';
  const driverPhone = document.getElementById('resDriverPhone')?.value || '+91 9876543210';

  const curDateStr = window.SYSTEM_CURRENT_DATE || getPcDateString();
  const pad = (n) => String(n).padStart(2, '0');
  const now = new Date();
  const nowTime = `${pad(now.getHours())}:${pad(now.getMinutes())}`;

  if (date < curDateStr || (date === curDateStr && startTime < nowTime)) {
    if (typeof showToast === 'function') {
      showToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'danger');
    }
    return;
  }

  try {
    const res = await fetch('/api/reservations/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUserId,
        slot_id: slot.slot_id,
        vehicle_plate: plate,
        driver_name: driverName,
        driver_phone: driverPhone,
        date: date,
        start_time: startTime,
        duration_hours: duration,
        ai_recommended: true,
        suitability_score: slot.suitability_score
      })
    });
    const data = await res.json();

    if (res.status === 409) {
      showToast(data.message || 'Double booking collision detected. Please select another slot.', 'error');
      closeReviewBookingSummaryModal();
      findAiRecommendations();
      return;
    }

    if (res.ok && data.status === 'success') {
      closeReviewBookingSummaryModal();
      showToast(`Slot ${slot.slot_number} booked successfully!`, 'success');
      showParkingPassModal(data);
      refreshAllDashboardData();
      loadMyBookings();
      updateAllocationStepIndicators(5);
      const step5Sub = document.getElementById('stepSub5');
      if (step5Sub) step5Sub.innerText = 'Verified & Created ✔';
    } else {
      showToast(data.message || 'Failed to create reservation.', 'error');
    }
  } catch (err) {
    console.error("Final booking error:", err);
    showToast('Network error confirming booking.', 'error');
  }
}


function showParkingPassModal(booking) {
  const modal = document.getElementById('parkingPassModal');
  const body = document.getElementById('parkingPassBody');

  const passId = booking.reservation_id ? `PK-${String(booking.reservation_id).padStart(5, '0')}-${booking.slot_number}` : 'PK-00088-R4';

  body.innerHTML = `
    <div style="text-align:center; padding:10px 0 16px 0;">
      <div style="width:60px; height:60px; background:var(--available-light); color:var(--available); border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-size:26px; margin-bottom:8px;">
        <i class="fas fa-check-circle"></i>
      </div>
      <h3 style="font-size:18px; font-weight:800; color:#0f172a;">Digital Parking Pass Confirmed</h3>
      <p style="font-size:13px; color:#64748b; margin-top:2px;">Pass Code: <b>${passId}</b></p>
    </div>

    <!-- Ticket Pass Container -->
    <div style="background:#f8fafc; border:2px dashed #cbd5e1; border-radius:14px; padding:18px; margin-bottom:14px;">
      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e2e8f0; padding-bottom:12px; margin-bottom:12px;">
        <div>
          <div style="font-size:11px; color:#64748b; text-transform:uppercase; font-weight:700;">Allocated Slot</div>
          <div style="font-size:26px; font-weight:800; color:var(--primary);">${booking.slot_number}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px; color:#64748b; text-transform:uppercase; font-weight:700;">Vehicle Plate</div>
          <div style="font-size:16px; font-weight:800; color:#0f172a;">${booking.vehicle_plate}</div>
        </div>
      </div>

      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:12.5px; margin-bottom:14px;">
        <div><span style="color:#64748b;">Date:</span> <b>${booking.date}</b></div>
        <div><span style="color:#64748b;">Duration:</span> <b>${booking.duration_hours || 2} Hours</b></div>
        <div><span style="color:#64748b;">Window:</span> <b>${booking.start_time} - ${booking.end_time}</b></div>
        <div><span style="color:#64748b;">Total Fee:</span> <b>₹${booking.total_amount}</b></div>
      </div>

      <!-- QR Code Simulation -->
      <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:10px; display:flex; align-items:center; justify-content:center; gap:14px;">
        <div style="width:68px; height:68px; background:repeating-linear-gradient(45deg, #0f172a, #0f172a 4px, #ffffff 4px, #ffffff 8px); border-radius:6px;"></div>
        <div style="font-size:11px; color:#64748b;">
          <b>Auto-Gate Access QR</b><br>
          Scan at Gate A Boom Barrier on entry & exit.
        </div>
      </div>
    </div>
  `;

  modal.classList.add('active');
}

function closeParkingPassModal() {
  const modal = document.getElementById('parkingPassModal');
  if (modal) modal.classList.remove('active');
}

// ==========================================
// MODULE 1 & 4: MY BOOKINGS CONTROLLER
// ==========================================

async function loadMyBookings() {
  const container = document.getElementById('myBookingsList');
  if (!container) return;

  try {
    const res = await fetch(`/api/reservations/my?user_id=${currentUserId}`);
    const data = await res.json();
    const bookings = data.reservations || [];

    if (bookings.length === 0) {
      container.innerHTML = '<p style="text-align:center; color:#64748b; padding:20px;">No bookings found for active user profile.</p>';
      return;
    }

    let html = '<div style="display:flex; flex-direction:column; gap:12px;">';
    bookings.forEach(b => {
      const isOverstay = b.status === 'overstayed';
      const isConfirmed = b.status === 'confirmed';
      const isCheckedIn = b.status === 'checked_in';
      const timeRangeStr = formatTimeRange(b.start_time, b.end_time);

      html += `
        <div style="background:#ffffff; border:1px solid var(--border-color); border-radius:14px; padding:16px; box-shadow:var(--shadow-subtle); display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:14px;">
          <div style="flex:1; min-width:280px;">
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:6px;">
              <span style="font-size:16px; font-weight:800; color:#0f172a;"><i class="fas fa-parking" style="color:var(--primary);"></i> ${b.lot_name || 'City Parking'} — Slot ${b.slot_number}</span>
              <span class="badge ${isOverstay ? 'badge-danger' : (isCheckedIn ? 'badge-primary' : 'badge-success')}" style="text-transform:capitalize;">
                ${isConfirmed ? 'Confirmed' : b.status.toUpperCase()}
              </span>
              ${b.ai_recommended ? '<span style="font-size:11px; font-weight:700; color:var(--primary);"><i class="fas fa-magic"></i> AI Pick (' + b.suitability_score + '%)</span>' : ''}
            </div>

            <!-- Syllabus Matching Booking Details Grid -->
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:6px 12px; font-size:12px; color:#475569; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px 12px; margin-top:6px;">
              <div><span style="color:#64748b;">Parking:</span> <strong>${b.lot_name || 'City Parking'}</strong></div>
              <div><span style="color:#64748b;">Slot:</span> <strong>Slot ${b.slot_number}</strong> (${b.floor})</div>
              <div><span style="color:#64748b;">Date:</span> <strong>${b.date}</strong></div>
              <div><span style="color:#64748b;">Time:</span> <strong>${timeRangeStr}</strong></div>
              <div><span style="color:#64748b;">Vehicle:</span> <strong>${b.vehicle_plate}</strong></div>
              <div><span style="color:#64748b;">Status:</span> <strong style="color:${isConfirmed ? '#059669' : '#d97706'};">${isConfirmed ? 'Confirmed' : b.status}</strong></div>
            </div>
          </div>

          <div style="display:flex; align-items:center; gap:8px;">
            ${isConfirmed ? `<button class="btn-secondary" onclick="openModifyReservationModal(${b.reservation_id}, '${b.vehicle_plate}')"><i class="fas fa-clock"></i> Extend</button>` : ''}
            ${isConfirmed ? `<button class="btn-secondary" onclick="cancelBookingDirectly(${b.reservation_id})"><i class="fas fa-times"></i> Cancel</button>` : ''}
            ${isConfirmed ? `<button class="btn-secondary" style="border-color:#2563eb; color:#2563eb;" onclick="goToExchangeForBooking(${b.reservation_id})"><i class="fas fa-exchange-alt"></i> Exchange</button>` : ''}
            ${isOverstay ? `<span style="color:#ef4444; font-size:12px; font-weight:700;">⚠️ Overstay Fine Accruing</span>` : ''}
            <button class="btn-primary" onclick='showParkingPassModal(${JSON.stringify(b)})'>
              <i class="fas fa-qrcode"></i> View Pass
            </button>
          </div>
        </div>
      `;
    });
    html += '</div>';
    container.innerHTML = html;
  } catch (err) {
    console.error("Error loading my bookings:", err);
  }
}

function goToExchangeForBooking(resId) {
  showTab('exchange');
  loadUserActiveBookingForExchange(resId);
}

function openModifyReservationModal(resId, plate) {
  document.getElementById('modifyResId').value = resId;
  document.getElementById('modifyVehiclePlate').value = plate;
  document.getElementById('modifyReservationModal').classList.add('active');
}

function closeModifyReservationModal() {
  document.getElementById('modifyReservationModal').classList.remove('active');
}

async function submitModifyReservation() {
  const resId = document.getElementById('modifyResId').value;
  const addedHours = document.getElementById('modifyAddedHours').value;
  const plate = document.getElementById('modifyVehiclePlate').value;

  try {
    const res = await fetch(`/api/reservations/modify/${resId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ added_hours: addedHours, vehicle_plate: plate })
    });
    const data = await res.json();
    showToast(data.message, 'success');
    closeModifyReservationModal();
    loadMyBookings();
    refreshAllDashboardData();
  } catch (err) {
    console.error(err);
  }
}

async function cancelBookingDirectly(resId) {
  if (!confirm("Are you sure you want to cancel this reservation?")) return;
  try {
    const res = await fetch(`/api/reservations/cancel/${resId}`, { method: 'POST' });
    const data = await res.json();
    showToast(data.message, 'info');
    loadMyBookings();
    refreshAllDashboardData();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// MODULE 6: OVERSTAY DETECTION & ALERT CENTER
// ==========================================

async function loadOverstayCenter() {
  const container = document.getElementById('overstaysTableContainer');
  if (!container) return;

  try {
    const res = await fetch('/api/overstays');
    const data = await res.json();
    const overstays = data.overstays || [];

    if (overstays.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding:32px; background:#ffffff; border-radius:14px; border:1px solid var(--border-color);">
          <i class="fas fa-shield-alt fa-3x" style="color:var(--available);"></i>
          <h3 style="margin-top:12px; font-size:16px; font-weight:800; color:#0f172a;">No Active Overstay Violations</h3>
          <p style="font-size:13px; color:#64748b;">All parked vehicles are currently within their scheduled booking windows.</p>
        </div>
      `;
      return;
    }

    let html = `
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Slot No.</th>
              <th>Vehicle License Plate</th>
              <th>Registered Driver</th>
              <th>Scheduled Exit</th>
              <th>Overstay Extra Time</th>
              <th>Accrued Penalty</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
    `;

    overstays.forEach(o => {
      html += `
        <tr>
          <td><b style="font-size:14px; color:#ef4444;"><i class="fas fa-exclamation-triangle"></i> Slot ${o.slot_number}</b></td>
          <td><b>${o.vehicle_plate}</b></td>
          <td>${o.user_name || 'Driver'}</td>
          <td>${o.end_time || o.expected_exit}</td>
          <td><span class="badge badge-danger">+${o.extra_duration_minutes} Mins</span></td>
          <td><b style="color:#b91c1c; font-size:14px;">₹${o.penalty_amount.toFixed(2)}</b></td>
          <td>
            <div style="display:flex; gap:6px;">
              <button class="btn-danger" style="padding:5px 10px; font-size:11px;" onclick="settleOverstayDirectly(${o.overstay_id}, 'settled')">
                Settle & Vacate
              </button>
              <button class="btn-secondary" style="padding:5px 10px; font-size:11px;" onclick="settleOverstayDirectly(${o.overstay_id}, 'waived')">
                Waive Fine
              </button>
            </div>
          </td>
        </tr>
      `;
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
  } catch (err) {
    console.error("Error loading overstay center:", err);
  }
}

async function triggerManualOverstayCheck() {
  try {
    const res = await fetch('/api/overstays/check-now', { method: 'POST' });
    const data = await res.json();
    showToast(`Overstay sweep complete. Scanned at ${data.simulated_time}.`, 'info');
    loadOverstayCenter();
    refreshAllDashboardData();
  } catch (err) {
    console.error(err);
  }
}

async function settleOverstayDirectly(overstayId, type = 'settled') {
  try {
    const res = await fetch(`/api/overstays/resolve/${overstayId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution_type: type })
    });
    const data = await res.json();
    showToast(data.message, 'success');
    closeSlotDetailModal();
    loadOverstayCenter();
    refreshAllDashboardData();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// MODULE 9: REPORTS & ANALYTICS
// ==========================================

async function loadReportsView() {
  try {
    const res = await fetch('/api/reports/summary');
    const data = await res.json();
    if (data.status === 'success') {
      const f = data.financials;
      document.getElementById('revParking').innerText = `₹${f.parking_revenue.toFixed(0)}`;
      document.getElementById('revOverstay').innerText = `₹${f.overstay_penalties.toFixed(0)}`;
      document.getElementById('revTotal').innerText = `₹${f.total_revenue.toFixed(0)}`;

      if (typeof initReportCharts === 'function') {
        initReportCharts(data);
      }

      // Render top utilized slots
      const topContainer = document.getElementById('topSlotsTableContainer');
      if (topContainer && data.top_utilized_slots) {
        let html = `
          <div class="table-responsive">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Slot Number</th>
                  <th>Floor</th>
                  <th>Zone</th>
                  <th>Total Reservations</th>
                  <th>Avg AI Suitability</th>
                </tr>
              </thead>
              <tbody>
        `;
        data.top_utilized_slots.forEach((s, idx) => {
          html += `
            <tr>
              <td>#${idx + 1}</td>
              <td><b>Slot ${s.slot_number}</b></td>
              <td>${s.floor}</td>
              <td>${s.zone}</td>
              <td><b>${s.booking_count} Bookings</b></td>
              <td><span class="badge badge-success">${s.avg_suitability ? s.avg_suitability.toFixed(1) : 89.5}% Match</span></td>
            </tr>
          `;
        });
        html += '</tbody></table></div>';
        topContainer.innerHTML = html;
      }

      // Load Module 10: Parking History & Activity Ledger
      await loadParkingHistory('all');
    }
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// MODULE 10: PARKING HISTORY LEDGER
// ==========================================

let currentHistoryStatusFilter = 'all';

async function filterParkingHistory(status) {
  currentHistoryStatusFilter = status;
  document.querySelectorAll('.history-filter-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-status') === status);
  });
  await loadParkingHistory(status);
}

async function loadParkingHistory(status = 'all') {
  try {
    const container = document.getElementById('reportsHistoryTableContainer');
    const badge = document.getElementById('historyCountBadge');
    if (!container) return;

    container.innerHTML = '<div style="padding:20px; text-align:center; color:#64748b;"><i class="fas fa-spinner fa-spin"></i> Loading parking history ledger...</div>';
    
    const res = await fetch(`/api/reports/history?status=${encodeURIComponent(status)}&limit=50`);
    const data = await res.json();
    if (data.status === 'success') {
      const records = data.history || [];
      if (badge) badge.innerText = `${data.total_count} Records`;

      if (records.length === 0) {
        container.innerHTML = '<div style="padding:24px; text-align:center; color:#94a3b8;"><i class="fas fa-inbox" style="font-size:24px; margin-bottom:8px; display:block;"></i>No historical parking transactions found for this filter.</div>';
        return;
      }

      let html = `
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Booking #</th>
                <th>Date</th>
                <th>Time Window</th>
                <th>Slot Details</th>
                <th>Driver / User</th>
                <th>Vehicle Plate</th>
                <th>Fee</th>
                <th>AI Match</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
      `;
      records.forEach(r => {
        let badgeClass = 'badge-primary';
        if (r.status === 'completed') badgeClass = 'badge-success';
        else if (r.status === 'overstayed') badgeClass = 'badge-danger';
        else if (r.status === 'cancelled') badgeClass = 'badge-light';

        html += `
          <tr>
            <td>#BK-${r.reservation_id}</td>
            <td><b>${r.date}</b></td>
            <td><i class="far fa-clock" style="color:#64748b; margin-right:4px;"></i>${r.start_time} - ${r.end_time}</td>
            <td><b>Slot ${r.slot_number}</b> <span style="font-size:11px; color:#64748b;">(${r.floor}, ${r.slot_type || 'Standard'})</span></td>
            <td>${r.user_name || 'Driver'}</td>
            <td><code style="background:#f1f5f9; padding:2px 6px; border-radius:4px; font-weight:700; color:#0f172a;">${r.vehicle_plate}</code></td>
            <td><b>₹${Number(r.total_amount || 40).toFixed(0)}</b></td>
            <td><span class="badge ${r.suitability_score >= 80 ? 'badge-success' : 'badge-light'}">${r.suitability_score ? Number(r.suitability_score).toFixed(0) : '90'}%</span></td>
            <td><span class="badge ${badgeClass}">${r.status.toUpperCase()}</span></td>
          </tr>
        `;
      });
      html += '</tbody></table></div>';
      container.innerHTML = html;
    }
  } catch (err) {
    console.error("Error loading parking history:", err);
  }
}

// ==========================================
// MODULE 7 & 9: ADMIN MANAGEMENT
// ==========================================

async function loadAdminView() {
  try {
    // 1. Users
    const uRes = await fetch('/api/admin/users');
    const uData = await uRes.json();
    const users = uData.users || [];
    const uContainer = document.getElementById('adminUsersTable');
    if (uContainer) {
      let html = `
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>User ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Total Bookings</th>
                <th>Overstay Infractions</th>
                <th>Change Role</th>
              </tr>
            </thead>
            <tbody>
      `;
      users.forEach(u => {
        html += `
          <tr>
            <td>#USR-${u.user_id}</td>
            <td><b>${u.name}</b></td>
            <td>${u.email}</td>
            <td><span class="badge ${u.role === 'admin' ? 'badge-primary' : 'badge-light'}">${u.role.toUpperCase()}</span></td>
            <td>${u.total_bookings}</td>
            <td><span style="color:${u.total_overstays > 0 ? '#ef4444' : '#10b981'}; font-weight:700;">${u.total_overstays}</span></td>
            <td>
              <select onchange="updateUserRoleDirectly(${u.user_id}, this.value)" style="padding:4px; font-size:11px; border-radius:6px; border:1px solid #cbd5e1;">
                <option value="user" ${u.role==='user'?'selected':''}>User</option>
                <option value="admin" ${u.role==='admin'?'selected':''}>Admin</option>
              </select>
            </td>
          </tr>
        `;
      });
      html += '</tbody></table></div>';
      uContainer.innerHTML = html;
    }

    // 2. Module 9: Admin Vehicle Management
    await loadAdminVehicles();

    // 3. Master Reservations
    const rRes = await fetch('/api/admin/reservations');
    const rData = await rRes.json();
    const resList = rData.reservations || [];
    const rContainer = document.getElementById('adminReservationsTable');
    if (rContainer) {
      let html = `
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Res ID</th>
                <th>Slot</th>
                <th>Driver</th>
                <th>Plate</th>
                <th>Date & Time</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
      `;
      resList.forEach(r => {
        html += `
          <tr>
            <td>#${r.reservation_id}</td>
            <td><b>Slot ${r.slot_number}</b></td>
            <td>${r.user_name}</td>
            <td><b>${r.vehicle_plate}</b></td>
            <td>${r.date} (${r.start_time} - ${r.end_time})</td>
            <td><span class="badge ${r.status==='completed'?'badge-success':(r.status==='cancelled'?'badge-light':'badge-primary')}">${r.status.toUpperCase()}</span></td>
            <td>
              ${r.status !== 'completed' && r.status !== 'cancelled' ? `
                <button class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="forceCheckoutDirectly(${r.reservation_id})">
                  Force Vacate
                </button>
              ` : '<span style="color:#94a3b8;">Closed</span>'}
            </td>
          </tr>
        `;
      });
      html += '</tbody></table></div>';
      rContainer.innerHTML = html;
    }

    // 4. Parking Lots & Slots Management Console
    await loadAdminParkingLotsAndSlots();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// MODULE 9: ADMIN VEHICLE FLEET MANAGEMENT
// ==========================================

async function loadAdminVehicles() {
  try {
    const container = document.getElementById('adminVehiclesTable');
    const badge = document.getElementById('adminVehiclesCountBadge');
    if (!container) return;

    const res = await fetch('/api/admin/vehicles');
    const data = await res.json();
    if (data.status === 'success') {
      const vehicles = data.vehicles || [];
      if (badge) badge.innerText = `${vehicles.length} Vehicles`;

      if (vehicles.length === 0) {
        container.innerHTML = '<div style="padding:20px; text-align:center; color:#94a3b8;">No registered vehicles in the system fleet.</div>';
        return;
      }

      let html = `
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Vehicle ID</th>
                <th>License Plate</th>
                <th>Category</th>
                <th>Make / Model</th>
                <th>Color</th>
                <th>Registered Driver</th>
                <th>Contact</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
      `;
      vehicles.forEach(v => {
        let typeBadge = 'badge-light';
        if (v.vehicle_type === 'EV') typeBadge = 'badge-success';
        else if (v.vehicle_type === 'SUV') typeBadge = 'badge-warning';
        else if (v.vehicle_type === 'Compact') typeBadge = 'badge-primary';

        html += `
          <tr>
            <td>#VEH-${v.vehicle_id}</td>
            <td><b style="font-family:'JetBrains Mono',monospace; letter-spacing:0.5px;">${v.license_plate}</b></td>
            <td><span class="badge ${typeBadge}">${v.vehicle_type || 'Car'}</span></td>
            <td>${v.make_model || '--'}</td>
            <td><span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:${(v.color || 'white').toLowerCase()}; border:1px solid #cbd5e1; margin-right:4px;"></span>${v.color || 'White'}</td>
            <td><b>${v.owner_name}</b> <span style="font-size:11px; color:#64748b;">(#USR-${v.user_id})</span></td>
            <td>${v.owner_email}</td>
            <td>
              <button class="btn-danger" style="padding:4px 8px; font-size:11px;" onclick="adminRemoveVehicleDirectly(${v.vehicle_id}, '${v.license_plate}')">
                <i class="fas fa-trash"></i> Remove
              </button>
            </td>
          </tr>
        `;
      });
      html += '</tbody></table></div>';
      container.innerHTML = html;
    }
  } catch (err) {
    console.error("Error loading admin vehicles:", err);
  }
}

async function adminRemoveVehicleDirectly(vehicleId, plate) {
  if (!confirm(`Are you sure you want to remove vehicle '${plate}' from the fleet database?`)) return;
  try {
    const res = await fetch(`/api/admin/vehicles/${vehicleId}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(data.message || 'Vehicle removed.', 'success');
      loadAdminVehicles();
    } else {
      showToast(data.message || 'Failed to remove vehicle.', 'error');
    }
  } catch (err) {
    showToast('Network error while removing vehicle.', 'error');
  }
}

async function loadAdminParkingLotsAndSlots() {
  const lotsGrid = document.getElementById('adminLotsSummaryGrid');
  const slotsTable = document.getElementById('adminSlotsManagementTable');
  if (!lotsGrid && !slotsTable) return;

  try {
    const lRes = await fetch('/api/lots');
    const lData = await lRes.json();
    const lots = lData.lots || [];

    if (lotsGrid) {
      let lHtml = '';
      lots.forEach(l => {
        lHtml += `
          <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span class="badge badge-primary">Lot #${l.lot_id}</span>
              <span style="font-size:12px; font-weight:700; color:#0f172a;">${l.actual_slot_count || l.total_slots} Slots</span>
            </div>
            <h4 style="font-size:15px; font-weight:800; color:#0f172a; margin:6px 0 2px 0;">${l.lot_name}</h4>
            <p style="font-size:11.5px; color:#64748b; margin-bottom:8px;">${l.location}</p>
            <div style="display:flex; gap:6px; flex-wrap:wrap; font-size:10.5px; font-weight:700;">
              <span style="color:#059669;">Avail: ${l.available_count ?? 0}</span> •
              <span style="color:#2563eb;">Occ: ${l.occupied_count ?? 0}</span> •
              <span style="color:#d97706;">Res: ${l.reserved_count ?? 0}</span> •
              <span style="color:#dc2626;">Overstay: ${l.overstayed_count ?? 0}</span>
            </div>
          </div>
        `;
      });
      lotsGrid.innerHTML = lHtml;
    }

    if (slotsTable) {
      const sRes = await fetch('/api/slots');
      const sData = await sRes.json();
      const slots = sData.slots || [];

      let sHtml = `
        <h4 style="font-size:14px; font-weight:800; margin-bottom:8px; color:#0f172a;">Slot Control & Type/Status Override</h4>
        <div class="table-responsive" style="max-height:380px; overflow-y:auto;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Slot ID</th>
                <th>Slot Number</th>
                <th>Lot</th>
                <th>Floor</th>
                <th>Slot Type</th>
                <th>Status</th>
                <th>Plate</th>
                <th>Quick Actions</th>
              </tr>
            </thead>
            <tbody>
      `;
      slots.forEach(s => {
        const stLower = (s.status || 'available').toLowerCase();
        sHtml += `
          <tr>
            <td>#SLT-${s.slot_id}</td>
            <td><b>${s.slot_number}</b></td>
            <td>${s.lot_name || 'Lot #'+s.lot_id}</td>
            <td>${s.floor}</td>
            <td>
              <select onchange="adminChangeSlotTypeDirectly(${s.slot_id}, this.value)" style="font-size:11px; padding:2px 4px; border-radius:4px; border:1px solid #cbd5e1;">
                <option value="Standard" ${s.slot_type==='Standard'?'selected':''}>Standard</option>
                <option value="EV" ${s.slot_type==='EV'?'selected':''}>EV</option>
                <option value="Compact" ${s.slot_type==='Compact'?'selected':''}>Compact</option>
                <option value="Disabled" ${s.slot_type==='Disabled'?'selected':''}>Disabled</option>
                <option value="VIP" ${s.slot_type==='VIP'?'selected':''}>VIP</option>
              </select>
            </td>
            <td>
              <select onchange="adminChangeSlotStatusDirectly(${s.slot_id}, this.value)" style="font-size:11px; padding:2px 4px; border-radius:4px; border:1px solid #cbd5e1; font-weight:600;">
                <option value="available" ${stLower==='available'?'selected':''}>Available</option>
                <option value="reserved" ${stLower==='reserved'?'selected':''}>Reserved</option>
                <option value="occupied" ${stLower==='occupied'?'selected':''}>Occupied</option>
                <option value="overstayed" ${stLower==='overstayed'?'selected':''}>Overstayed</option>
                <option value="disabled" ${stLower==='disabled'?'selected':''}>Maintenance</option>
              </select>
            </td>
            <td>${s.current_plate || '<span style="color:#94a3b8;">--</span>'}</td>
            <td>
              <button class="btn-secondary" style="padding:2px 6px; font-size:10px;" onclick="openAdminEditSlotModal(${s.slot_id})" title="Edit Slot"><i class="fas fa-edit"></i></button>
              <button class="btn-danger" style="padding:2px 6px; font-size:10px;" onclick="deleteSlotDirectly(${s.slot_id})" title="Delete Slot"><i class="fas fa-trash"></i></button>
            </td>
          </tr>
        `;
      });
      sHtml += '</tbody></table></div>';
      slotsTable.innerHTML = sHtml;
    }
  } catch (err) {
    console.error("Error loading admin parking lots and slots:", err);
  }
}

async function adminChangeSlotTypeDirectly(slotId, newType) {
  try {
    const res = await fetch('/api/admin/slots/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot_id: slotId, slot_type: newType })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Slot type changed to ${newType}.`, 'success');
      loadAllSlotsTable();
      refreshAllDashboardData();
    } else {
      showToast(data.message || 'Failed to update slot type.', 'error');
    }
  } catch (err) {
    console.error(err);
  }
}

async function updateUserRoleDirectly(userId, role) {
  try {
    const res = await fetch('/api/admin/users/update-role', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, role: role })
    });
    const data = await res.json();
    showToast(data.message, 'success');
  } catch (err) {
    console.error(err);
  }
}

async function forceCheckoutDirectly(resId) {
  if (!confirm("Admin Override: Are you sure you want to force checkout this vehicle and restore slot to Available?")) return;
  try {
    const res = await fetch(`/api/admin/reservations/force-checkout/${resId}`, { method: 'POST' });
    const data = await res.json();
    showToast(data.message, 'success');
    loadAdminView();
    refreshAllDashboardData();
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// MODULE 1: USER PROFILE & VEHICLES GARAGE
// ==========================================

async function loadUserProfile() {
  try {
    const res = await fetch(`/api/users/profile?user_id=${currentUserId}`);
    const data = await res.json();
    if (data.status === 'success') {
      const p = data.profile;
      document.getElementById('profileName').innerText = p.name;
      document.getElementById('profileRole').innerText = (p.role || 'user').toUpperCase();
      document.getElementById('profileInputName').value = p.name || '';
      document.getElementById('profileInputEmail').value = p.email || '';
      document.getElementById('profileInputPhone').value = p.phone || '';

      const vGrid = document.getElementById('userVehiclesGrid');
      if (vGrid && data.vehicles) {
        let html = '';
        data.vehicles.forEach(v => {
          const vJson = JSON.stringify(v).replace(/"/g, '&quot;');
          let badgeClass = 'badge-light';
          const vt = (v.vehicle_type || '').toUpperCase();
          if (vt.includes('EV') || vt.includes('ELECTRIC')) badgeClass = 'badge-primary';
          else if (vt.includes('SUV')) badgeClass = 'badge-warning';
          else if (vt.includes('TWO') || vt.includes('BIKE')) badgeClass = 'badge-info';
          html += `
            <div class="kpi-mini-card" style="border:1px solid #cbd5e1; background:#ffffff; position:relative; border-radius:12px; padding:14px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="badge ${badgeClass}">
                  ${v.vehicle_type}
                </span>
                <div style="display:flex; gap:8px; align-items:center;">
                  <button onclick="openEditVehicleModal(${vJson})" style="border:none; background:transparent; color:var(--primary); cursor:pointer; font-size:13px;" title="Edit Vehicle">
                    <i class="fas fa-edit"></i>
                  </button>
                  <button onclick="deleteVehicleDirectly(${v.vehicle_id})" style="border:none; background:transparent; color:#ef4444; cursor:pointer; font-size:13px;" title="Remove Vehicle">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </div>
              <h4 style="font-size:16px; font-weight:800; color:#0f172a; margin-top:8px; letter-spacing:0.5px;">${v.license_plate}</h4>
              <p style="font-size:12px; color:#64748b; margin-top:2px;">${v.make_model || 'Sedan'} • <span style="color:#475569;">${v.color || 'White'}</span></p>
            </div>
          `;
        });
        vGrid.innerHTML = html || '<p style="color:#64748b; font-size:12px; grid-column:span 2; text-align:center; padding:16px;">No registered vehicles found. Click "+ Add Vehicle" to register one.</p>';
      }
    } else if (res.status === 401 || res.status === 403) {
      showToast(data.message || "Unauthorized access.", "danger");
    }
  } catch (err) {
    console.error("Error loading user profile:", err);
  }
}

async function saveUserProfile() {
  const name = document.getElementById('profileInputName').value.trim();
  const email = document.getElementById('profileInputEmail').value.trim();
  const phone = document.getElementById('profileInputPhone').value.trim();

  if (!name) {
    showToast("Full name is required.", "danger");
    return;
  }
  if (!email) {
    showToast("Email address is required.", "danger");
    return;
  }

  try {
    const res = await fetch('/api/users/profile/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId, name, email, phone })
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast(data.message, 'success');
      // Update top header greeting and session badge dynamically
      const greetingEl = document.getElementById('topHeaderGreeting');
      if (greetingEl) greetingEl.innerHTML = `Welcome, ${data.profile.name} 👋`;
      const badgeEl = document.getElementById('sessionUserBadgeName');
      if (badgeEl) badgeEl.innerText = data.profile.name;
      loadUserProfile();
    } else {
      showToast(data.message || 'Failed to update profile.', 'danger');
    }
  } catch (err) {
    console.error("Error saving user profile:", err);
    showToast("Network error updating profile.", "danger");
  }
}

function openAddVehicleModal() {
  document.getElementById('newVehiclePlate').value = '';
  document.getElementById('newVehicleMake').value = '';
  document.getElementById('newVehicleColor').value = '';
  document.getElementById('addVehicleModal').classList.add('active');
}

function closeAddVehicleModal() {
  document.getElementById('addVehicleModal').classList.remove('active');
}

async function submitAddVehicle() {
  const plate = document.getElementById('newVehiclePlate').value.trim().toUpperCase();
  const type = document.getElementById('newVehicleType').value;
  const make = document.getElementById('newVehicleMake').value.trim();
  const color = document.getElementById('newVehicleColor').value.trim();

  if (!plate) {
    showToast("License plate number is required.", "danger");
    return;
  }

  try {
    const res = await fetch('/api/users/vehicles/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId, license_plate: plate, vehicle_type: type, make_model: make, color: color })
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast(data.message, 'success');
      closeAddVehicleModal();
      loadUserProfile();
    } else {
      showToast(data.message || 'Failed to register vehicle.', 'danger');
    }
  } catch (err) {
    console.error("Error registering vehicle:", err);
    showToast("Network error registering vehicle.", "danger");
  }
}

function openEditVehicleModal(vehicle) {
  if (!vehicle) return;
  document.getElementById('editVehicleId').value = vehicle.vehicle_id;
  document.getElementById('editVehiclePlate').value = vehicle.license_plate || '';
  document.getElementById('editVehicleType').value = vehicle.vehicle_type || 'Car';
  document.getElementById('editVehicleMake').value = vehicle.make_model || '';
  document.getElementById('editVehicleColor').value = vehicle.color || '';
  document.getElementById('editVehicleModal').classList.add('active');
}

function closeEditVehicleModal() {
  document.getElementById('editVehicleModal').classList.remove('active');
}

async function submitEditVehicle() {
  const vId = document.getElementById('editVehicleId').value;
  const plate = document.getElementById('editVehiclePlate').value.trim().toUpperCase();
  const type = document.getElementById('editVehicleType').value;
  const make = document.getElementById('editVehicleMake').value.trim();
  const color = document.getElementById('editVehicleColor').value.trim();

  if (!plate) {
    showToast("License plate number cannot be empty.", "danger");
    return;
  }

  try {
    const res = await fetch(`/api/users/vehicles/${vId}/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ license_plate: plate, vehicle_type: type, make_model: make, color: color })
    });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast(data.message, 'success');
      closeEditVehicleModal();
      loadUserProfile();
    } else {
      showToast(data.message || 'Failed to update vehicle.', 'danger');
    }
  } catch (err) {
    console.error("Error updating vehicle:", err);
    showToast("Network error updating vehicle.", "danger");
  }
}

async function deleteVehicleDirectly(vehicleId) {
  if (!confirm("Are you sure you want to remove this vehicle from your garage?")) return;
  try {
    const res = await fetch(`/api/users/vehicles/${vehicleId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok && data.status === 'success') {
      showToast(data.message, 'info');
      loadUserProfile();
    } else {
      showToast(data.message || 'Failed to remove vehicle.', 'danger');
    }
  } catch (err) {
    console.error("Error deleting vehicle:", err);
    showToast("Network error deleting vehicle.", "danger");
  }
}

// ==========================================
// SYSTEM SETTINGS
// ==========================================

async function saveSystemSettings() {
  const hourly = document.getElementById('settingHourlyRate').value;
  const penalty = document.getElementById('settingPenaltyRate').value;
  const grace = document.getElementById('settingGracePeriod').value;

  try {
    const res = await fetch('/api/admin/settings/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hourly_rate: hourly, penalty_rate: penalty, grace_period_mins: grace })
    });
    const data = await res.json();
    showToast(data.message, 'success');
  } catch (err) {
    console.error(err);
  }
}

// ==========================================
// MONGODB STATUS & PERSISTENCE MANAGEMENT
// ==========================================

async function refreshMongoStatusUI() {
  try {
    const res = await fetch('/api/mongo/status');
    const data = await res.json();
    if (data.status === 'success') {
      const badge = document.getElementById('mongoHeaderBadge');
      const badgeDot = document.getElementById('mongoLiveDot');
      const badgeText = document.getElementById('mongoBadgeText');
      const pill = document.getElementById('mongoServerStatusPill');

      if (data.is_connected) {
        if (badge) {
          badge.style.background = '#f0fdf4';
          badge.style.borderColor = '#86efac';
          badge.style.color = '#166534';
        }
        if (badgeDot) {
          badgeDot.style.background = '#22c55e';
          badgeDot.style.boxShadow = '0 0 6px #22c55e';
        }
        if (badgeText) badgeText.innerText = 'MongoDB Live';
        if (pill) {
          pill.style.background = '#22c55e';
          pill.innerText = '● Live Connected';
        }
      } else {
        if (badge) {
          badge.style.background = '#fffbeb';
          badge.style.borderColor = '#fde68a';
          badge.style.color = '#92400e';
        }
        if (badgeDot) {
          badgeDot.style.background = '#f59e0b';
          badgeDot.style.boxShadow = '0 0 6px #f59e0b';
        }
        if (badgeText) badgeText.innerText = 'MongoDB Cache';
        if (pill) {
          pill.style.background = '#f59e0b';
          pill.innerText = '● Decoupled Store';
        }
      }

      const totalDocs = document.getElementById('mongoTotalDocsCount');
      if (totalDocs) totalDocs.innerText = data.total_documents || 0;

      const colls = data.collections || {};
      const setEl = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val !== undefined ? val : 0;
      };

      setEl('mongoCountUsers', colls.users);
      setEl('mongoCountVehicles', colls.vehicles);
      setEl('mongoCountReservations', colls.reservations);
      setEl('mongoCountSlots', colls.parking_slots);
      setEl('mongoCountLogins', colls.login_logs);
      setEl('mongoCountLogs', colls.activity_logs);
      setEl('mongoCountOverstays', colls.overstay_records);
      setEl('mongoCountExchanges', (colls.slot_exchange_listings || 0) + (colls.slot_exchange_requests || 0));
    }
  } catch (err) {
    console.error("Failed fetching MongoDB status:", err);
  }
}

async function triggerMongoManualSync() {
  try {
    showToast('Synchronizing all data into MongoDB...', 'info');
    const res = await fetch('/api/mongo/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(`MongoDB Sync Complete! ${data.total_synced_documents} documents synchronized.`, 'success');
      refreshMongoStatusUI();
    } else {
      showToast(data.message || 'Sync failed', 'error');
    }
  } catch (err) {
    console.error("MongoDB Sync error:", err);
    showToast('Network error triggering MongoDB sync.', 'error');
  }
}

// Helpers
function openReservationForSlot(slotId, slotNumber) {
  closeSlotDetailModal();
  showTab('reservations');
  findAiRecommendations();
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div class="toast-content">
      <p>${message}</p>
    </div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, 4500);
}

// ==========================================================================
// MODULE 7: PARKING SLOT EXCHANGE CLIENT
// ==========================================================================

let activeUserBookingForExchange = null;
let currentSelectedExchangeListing = null;
let currentExchangeOpportunitiesMap = new Map();

async function loadExchangeView() {
  await loadUserActiveBookingForExchange();
  await searchExchangeOpportunities();
  await loadExchangeRequests();
}

function clearExchangeDateFilter() {
  const dateInput = document.getElementById('exchangeFilterDate');
  if (dateInput) {
    dateInput.value = '';
  }
  searchExchangeOpportunities();
}

async function loadUserActiveBookingForExchange(targetResId = null) {
  const container = document.getElementById('exchangeCurrentBookingContainer');
  if (!container) return;

  try {
    let url = `/api/exchange/user-active-booking?user_id=${currentUserId}`;
    if (targetResId) url += `&reservation_id=${targetResId}`;
    const res = await fetch(url);
    const data = await res.json();
    
    if (data.has_booking && data.booking) {
      activeUserBookingForExchange = data.booking;
      const b = data.booking;
      const isOffered = data.is_offered;
      const listing = data.listing;
      const allBookings = data.all_bookings || [b];

      // Badge color based on slot type
      let badgeClass = 'badge-blue';
      if (b.slot_type === 'EV') badgeClass = 'badge-emerald';
      else if (b.slot_type === 'VIP') badgeClass = 'badge-purple';
      else if (b.slot_type === 'Compact') badgeClass = 'badge-amber';

      let bookingSelectorHtml = '';
      if (allBookings.length > 1) {
        bookingSelectorHtml = `
          <div style="margin-bottom:12px; background:#f1f5f9; padding:8px 10px; border-radius:8px;">
            <label style="font-size:11px; font-weight:700; color:#475569; display:block; margin-bottom:4px;">
              <i class="fas fa-layer-group" style="color:var(--primary); margin-right:4px;"></i> You have ${allBookings.length} bookings. Selected:
            </label>
            <select class="form-control" style="font-size:12px; padding:4px 8px; width:100%; background:#ffffff;" onchange="loadUserActiveBookingForExchange(this.value)">
              ${allBookings.map(bk => `<option value="${bk.reservation_id}" ${bk.reservation_id === b.reservation_id ? 'selected' : ''}>Slot ${bk.slot_number} (${bk.date}, ${bk.start_time}-${bk.end_time})</option>`).join('')}
            </select>
          </div>
        `;
      }

      container.innerHTML = `
        ${bookingSelectorHtml}
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px;">
          <div style="display:flex; align-items:center; gap:12px;">
            <div class="slot-circle-badge ${badgeClass}">
              ${b.slot_number}
            </div>
            <div>
              <h4 style="font-size:15px; font-weight:800; color:#0f172a; margin:0;">Slot ${b.slot_number} - ${b.floor}</h4>
              <p style="font-size:12px; color:#64748b; margin:2px 0 0 0;">${b.lot_name} Parking</p>
            </div>
          </div>
          <span style="background:#e0f2fe; color:#0284c7; padding:3px 10px; border-radius:99px; font-size:11px; font-weight:700;">You</span>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; background:#f8fafc; padding:12px; border-radius:10px; border:1px solid #e2e8f0;">
          <div>
            <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">Date</span>
            <span style="font-size:12px; font-weight:700; color:#1e293b;"><i class="far fa-calendar-alt" style="color:var(--primary); margin-right:4px;"></i> ${b.date}</span>
          </div>
          <div>
            <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">Time Window</span>
            <span style="font-size:12px; font-weight:700; color:#1e293b;"><i class="far fa-clock" style="color:var(--primary); margin-right:4px;"></i> ${b.start_time} - ${b.end_time}</span>
          </div>
          <div>
            <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">Duration</span>
            <span style="font-size:12px; font-weight:700; color:#1e293b;"><i class="fas fa-hourglass-half" style="color:#d97706; margin-right:4px;"></i> 2 Hours</span>
          </div>
          <div>
            <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block;">Amount Paid</span>
            <span style="font-size:12px; font-weight:700; color:#059669;"><i class="fas fa-rupee-sign" style="margin-right:2px;"></i> ₹${b.total_amount || 80}</span>
          </div>
        </div>

        <div>
          ${isOffered ? `
            <div style="background:#ecfdf5; border:1px solid #a7f3d0; border-radius:8px; padding:10px; text-align:center; margin-bottom:10px;">
              <span style="font-size:12px; font-weight:800; color:#059669;"><i class="fas fa-check-circle"></i> Listed for Exchange</span>
              <p style="font-size:11px; color:#047857; margin:2px 0 0 0;">Waiting for other drivers to propose a swap</p>
            </div>
            <button class="btn-primary" style="width:100%; font-weight:700; font-size:12px; padding:8px; margin-bottom:8px; background:#10b981; border-color:#10b981;" onclick="simulateIncomingExchangeRequest()">
              <i class="fas fa-magic"></i> Simulate Incoming Swap Request
            </button>
            <button class="btn-secondary" style="width:100%; font-weight:700; font-size:12px; padding:8px;" onclick="cancelCurrentSlotOffer(${listing.listing_id})">
              <i class="fas fa-undo"></i> Cancel Exchange Offer
            </button>
          ` : `
            <button class="btn-primary" style="width:100%; font-weight:700; font-size:13px; padding:10px;" onclick="offerCurrentSlotForExchange(${b.reservation_id})">
              <i class="fas fa-exchange-alt"></i> Offer This Slot for Exchange
            </button>
          `}
        </div>

        <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:8px 12px; font-size:11px; color:#1e40af; margin-top:14px; display:flex; align-items:center; gap:8px;">
          <i class="fas fa-info-circle" style="font-size:14px; flex-shrink:0;"></i>
          <span>You can exchange this slot before <strong>${b.date}, ${b.start_time}</strong></span>
        </div>
      `;
    } else {
      activeUserBookingForExchange = null;
      container.innerHTML = `
        <div style="text-align:center; padding:24px 15px;">
          <div style="width:50px; height:50px; border-radius:50%; background:#f1f5f9; color:#94a3b8; display:flex; align-items:center; justify-content:center; margin:0 auto 10px; font-size:20px;">
            <i class="fas fa-calendar-times"></i>
          </div>
          <h4 style="font-size:14px; font-weight:800; color:#1e293b; margin-bottom:4px;">No Active Booking Found</h4>
          <p style="font-size:12px; color:#64748b; margin-bottom:12px;">You need a confirmed reservation to offer or request an exchange.</p>
          <div style="display:flex; flex-direction:column; gap:8px; max-width:240px; margin:0 auto;">
            <button class="btn-primary" style="font-size:12px; padding:7px 12px;" onclick="quickSeedBookingForExchange()">
              <i class="fas fa-bolt"></i> Quick Seed Test Booking
            </button>
            <button class="btn-secondary" style="font-size:12px; padding:7px 12px;" onclick="showTab('reservations')">
              <i class="fas fa-plus-circle"></i> Reserve a Parking Slot
            </button>
          </div>
        </div>
      `;
    }
  } catch (err) {
    console.error(err);
    container.innerHTML = `<p style="font-size:12px; color:#ef4444;">Failed to load booking status.</p>`;
  }
}

async function offerCurrentSlotForExchange(resId) {
  try {
    const res = await fetch('/api/exchange/offer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUserId,
        reservation_id: resId,
        notes: 'Seeking convenient swap'
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadExchangeView();
    } else {
      showToast(data.message || 'Failed to list slot for exchange.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error listing slot.', 'error');
  }
}

async function cancelCurrentSlotOffer(listingId) {
  try {
    const res = await fetch('/api/exchange/cancel-offer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUserId,
        listing_id: listingId
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'info');
      loadExchangeView();
    } else {
      showToast(data.message || 'Failed to cancel listing.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error cancelling listing.', 'error');
  }
}

async function searchExchangeOpportunities() {
  const container = document.getElementById('exchangeOpportunitiesList');
  if (!container) return;

  const dateVal = document.getElementById('exchangeFilterDate')?.value?.trim() || '';
  const timeVal = document.getElementById('exchangeFilterTime')?.value || 'all';
  const lotVal = document.getElementById('exchangeFilterLot')?.value || 'all';
  const floorVal = document.getElementById('exchangeFilterFloor')?.value || 'all';

  let url = `/api/exchange/search?user_id=${currentUserId}`;
  if (dateVal && dateVal.toLowerCase() !== 'all') url += `&date=${encodeURIComponent(dateVal)}`;
  if (timeVal && timeVal !== 'all') url += `&time=${encodeURIComponent(timeVal)}`;
  if (lotVal !== 'all') url += `&lot_id=${encodeURIComponent(lotVal)}`;
  if (floorVal !== 'all') url += `&floor=${encodeURIComponent(floorVal)}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    const opps = data.opportunities || [];
    currentExchangeOpportunitiesMap.clear();

    if (opps.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding:24px 10px; color:#94a3b8;">
          <i class="fas fa-search" style="font-size:22px; margin-bottom:6px; display:block;"></i>
          <p style="font-size:12px; margin:0 0 6px;">No other drivers have offered slots matching your filters right now.</p>
          <div style="display:flex; justify-content:center; gap:8px; margin-top:8px;">
            <button class="btn-secondary" style="font-size:11px; padding:5px 10px;" onclick="clearExchangeDateFilter()">
              <i class="fas fa-globe"></i> View All Dates
            </button>
            <button class="btn-primary" style="font-size:11px; padding:5px 12px; background:#8b5cf6; border-color:#8b5cf6;" onclick="seedDemoExchangeSlot()">
              <i class="fas fa-wand-magic-sparkles"></i> Generate Swap Offer
            </button>
          </div>
          <span style="font-size:11px; color:#94a3b8; display:block; margin-top:8px;">Tip: Switch active driver from header dropdown to trade between profiles.</span>
        </div>
      `;
      return;
    }

    let html = '';
    opps.forEach(o => {
      currentExchangeOpportunitiesMap.set(o.listing_id, o);

      let badgeColor = 'badge-emerald';
      if (o.slot_type === 'Standard') badgeColor = 'badge-blue';
      else if (o.slot_type === 'Compact') badgeColor = 'badge-amber';
      else if (o.slot_type === 'VIP') badgeColor = 'badge-purple';

      // Feature highlights
      let features = [];
      if (o.distance_to_elevator_m <= 15) features.push('Near Elevator');
      if (o.distance_to_entry_m <= 18) features.push('Near Exit Gate');
      features.push('Low Congestion');
      const featureStr = features.slice(0, 2).join(' • ');

      html += `
        <div class="exchange-opp-card">
          <div style="display:flex; align-items:center; gap:12px;">
            <div class="slot-circle-badge ${badgeColor}">
              ${o.slot_number}
            </div>
            <div>
              <div style="display:flex; align-items:center; gap:6px;">
                <h5 style="font-size:13px; font-weight:800; color:#0f172a; margin:0;">Slot ${o.slot_number} - ${o.floor}</h5>
                <span style="font-size:10px; background:#eff6ff; color:#2563eb; padding:2px 6px; border-radius:6px; font-weight:700;" title="Transparent Rule-Based Matching">${o.match_score}% Match</span>
                ${o.status === 'pending' ? '<span style="font-size:9px; background:#fff7ed; color:#c2410c; padding:1px 5px; border-radius:4px; font-weight:700;">Open Proposals</span>' : ''}
              </div>
              <p style="font-size:11px; color:#64748b; margin:2px 0 0 0;">
                ${featureStr} <span style="color:#cbd5e1;">•</span> ${o.lot_name} • ${o.date}
              </p>
            </div>
          </div>

          <div style="display:flex; align-items:center; gap:16px;">
            <div style="text-align:right;">
              <span style="font-size:13px; font-weight:800; color:#0f172a; display:block;">₹${(o.hourly_rate || 40) * 2}</span>
              <span style="font-size:10px; color:#94a3b8;">${o.start_time} - ${o.end_time}</span>
            </div>
            <button class="btn-exchange-request" onclick="openRequestExchangeModalById(${o.listing_id})">
              Request
            </button>
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (err) {
    console.error(err);
    container.innerHTML = `<p style="font-size:12px; color:#ef4444;">Failed to load exchange opportunities.</p>`;
  }
}

function openRequestExchangeModalById(listingId) {
  const o = currentExchangeOpportunitiesMap.get(listingId);
  if (!o) {
    showToast('Listing details not found.', 'error');
    return;
  }
  openRequestExchangeModal(listingId, o.slot_number, o.floor, o.lot_name, o.match_score, o.match_rationale, o.owner_name);
}

function openRequestExchangeModal(listingId, slotNumber, floor, lotName, matchScore, matchRationale, ownerName) {
  if (!activeUserBookingForExchange) {
    showToast('You must have an active confirmed future booking to request an exchange.', 'error');
    return;
  }

  currentSelectedExchangeListing = listingId;
  const modal = document.getElementById('requestExchangeModal');
  const body = document.getElementById('requestExchangeModalBody');

  if (body) {
    body.innerHTML = `
      <p style="font-size:13px; color:#475569; margin-bottom:16px;">
        Propose a direct slot swap with <strong>${ownerName || 'Driver'}</strong>. Both parties will instantly receive updated bookings upon acceptance.
      </p>

      <div style="display:grid; grid-template-columns:1fr auto 1fr; gap:10px; align-items:center; background:#f8fafc; padding:14px; border-radius:12px; border:1px solid #e2e8f0; margin-bottom:16px;">
        <div style="text-align:center;">
          <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block; margin-bottom:4px;">You Give</span>
          <div style="font-weight:800; font-size:15px; color:#2563eb;">Slot ${activeUserBookingForExchange.slot_number}</div>
          <span style="font-size:11px; color:#64748b;">${activeUserBookingForExchange.floor}</span>
        </div>

        <div style="color:#94a3b8; font-size:18px;">
          <i class="fas fa-exchange-alt"></i>
        </div>

        <div style="text-align:center;">
          <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:700; display:block; margin-bottom:4px;">You Receive</span>
          <div style="font-weight:800; font-size:15px; color:#059669;">Slot ${slotNumber}</div>
          <span style="font-size:11px; color:#64748b;">${floor}</span>
        </div>
      </div>

      <!-- Transparent Rule-Based Match Breakdown -->
      <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:10px; padding:10px 14px; margin-bottom:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <span style="font-size:11px; font-weight:800; color:#1e40af;"><i class="fas fa-check-circle"></i> Rule-Based Match Score</span>
          <span style="font-size:12px; font-weight:800; color:#2563eb;">${matchScore}%</span>
        </div>
        <p style="font-size:11px; color:#1e3a8a; margin:0;">
          <strong>Factors:</strong> ${matchRationale || 'Date, schedule window, and parking lot proximity alignment.'}
        </p>
      </div>

      <p style="font-size:11px; color:#64748b; margin:0;">
        <i class="fas fa-shield-alt" style="color:#059669;"></i> Security: Original bookings remain unchanged unless the owner explicitly accepts this request.
      </p>
    `;
  }

  if (modal) {
    modal.classList.add('active');
    modal.style.display = 'flex';
  }
}

function closeRequestExchangeModal() {
  const modal = document.getElementById('requestExchangeModal');
  if (modal) {
    modal.classList.remove('active');
    modal.style.display = '';
  }
}

async function submitExchangeRequest() {
  if (!currentSelectedExchangeListing || !activeUserBookingForExchange) {
    showToast('Missing exchange parameters.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/exchange/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requester_user_id: currentUserId,
        listing_id: currentSelectedExchangeListing,
        requester_reservation_id: activeUserBookingForExchange.reservation_id
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeRequestExchangeModal();
      // Auto switch to Sent Requests subview so the user sees their proposal
      const sentBtn = document.getElementById('btnExchangeTabSent');
      if (sentBtn) switchExchangeSubTab('sent', sentBtn);
      loadExchangeView();

      // Trigger automatic simulation of driver acceptance for immediate end-to-end satisfaction
      if (data.request_id) {
        showToast('Driver is reviewing your exchange proposal...', 'info');
        setTimeout(async () => {
          await simulateOwnerAccept(data.request_id, true);
        }, 1500);
      }
    } else {
      showToast(data.message || 'Failed to submit exchange request.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error submitting exchange request.', 'error');
  }
}

async function loadExchangeRequests() {
  const recContainer = document.getElementById('exchangeReceivedRequestsContainer');
  const sentContainer = document.getElementById('exchangeSentRequestsContainer');
  const histContainer = document.getElementById('exchangeHistoryContainer');
  const badgeEl = document.getElementById('badgeReceivedCount');
  const badgeSentEl = document.getElementById('badgeSentCount');

  try {
    const res = await fetch(`/api/exchange/requests?user_id=${currentUserId}`);
    const data = await res.json();

    const received = data.received_requests || [];
    const sent = data.sent_requests || [];
    const history = data.history || [];

    // Received Badge update
    if (badgeEl) {
      if (received.length > 0) {
        badgeEl.style.display = 'inline-block';
        badgeEl.innerText = received.length;
      } else {
        badgeEl.style.display = 'none';
      }
    }

    // Sent Badge update
    if (badgeSentEl) {
      if (sent.length > 0) {
        badgeSentEl.style.display = 'inline-block';
        badgeSentEl.innerText = sent.length;
      } else {
        badgeSentEl.style.display = 'none';
      }
    }

    // 1. Render Received Requests
    if (recContainer) {
      if (received.length === 0) {
        recContainer.innerHTML = `
          <div style="text-align:center; padding:24px 10px; color:#94a3b8;">
            <i class="fas fa-inbox" style="font-size:22px; margin-bottom:6px; display:block;"></i>
            <p style="font-size:12px; margin:0;">No pending exchange requests received for your slot.</p>
          </div>
        `;
      } else {
        let html = '';
        received.forEach(r => {
          html += `
            <div class="exchange-req-row">
              <div style="display:flex; align-items:center; gap:12px; min-width:180px;">
                <div class="user-avatar-circle">
                  ${(r.requester_name || 'Driver').substring(0, 2).toUpperCase()}
                </div>
                <div>
                  <div style="display:flex; align-items:center; gap:6px;">
                    <h5 style="font-size:13px; font-weight:800; color:#0f172a; margin:0;">${r.requester_name}</h5>
                    <span style="font-size:10px; background:#ecfdf5; color:#059669; font-weight:700; padding:1px 5px; border-radius:4px;">★ 4.8</span>
                  </div>
                  <span style="font-size:11px; color:#64748b;">Member since Feb 2024</span>
                </div>
              </div>

              <!-- Their Slot vs Your Slot with Arrows -->
              <div style="display:flex; align-items:center; gap:16px; flex:1; justify-content:center;">
                <div style="text-align:right;">
                  <span style="font-size:10px; color:#94a3b8; font-weight:700; display:block;">Their Slot</span>
                  <div style="display:flex; align-items:center; gap:8px; justify-content:flex-end;">
                    <span class="slot-circle-badge badge-emerald" style="width:34px; height:34px; font-size:12px;">${r.requester_slot_number}</span>
                    <div style="text-align:left;">
                      <span style="font-size:12px; font-weight:800; color:#0f172a; display:block;">Slot ${r.requester_slot_number} - ${r.requester_floor}</span>
                      <span style="font-size:10px; color:#64748b;">${r.requester_date}, ${r.requester_start_time} - ${r.requester_end_time}</span>
                    </div>
                  </div>
                </div>

                <div style="color:#059669; font-size:18px; padding:0 8px;">
                  <i class="fas fa-exchange-alt"></i>
                </div>

                <div>
                  <span style="font-size:10px; color:#94a3b8; font-weight:700; display:block;">Your Slot</span>
                  <div style="display:flex; align-items:center; gap:8px;">
                    <span class="slot-circle-badge badge-blue" style="width:34px; height:34px; font-size:12px;">${r.owner_slot_number}</span>
                    <div>
                      <span style="font-size:12px; font-weight:800; color:#0f172a; display:block;">Slot ${r.owner_slot_number} - ${r.owner_floor}</span>
                      <span style="font-size:10px; color:#64748b;">${r.owner_date}, ${r.owner_start_time} - ${r.owner_end_time}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div style="display:flex; align-items:center; gap:12px;">
                <span style="font-size:11px; color:#94a3b8;">Requested recently</span>
                <button class="btn-exchange-accept" onclick="respondExchangeRequest(${r.request_id}, 'accept')">
                  Accept
                </button>
                <button class="btn-exchange-reject" onclick="respondExchangeRequest(${r.request_id}, 'reject')">
                  Reject
                </button>
              </div>
            </div>
          `;
        });
        recContainer.innerHTML = html;
      }
    }

    // 2. Render Sent Requests
    if (sentContainer) {
      if (sent.length === 0) {
        sentContainer.innerHTML = `
          <div style="text-align:center; padding:24px 10px; color:#94a3b8;">
            <i class="fas fa-paper-plane" style="font-size:22px; margin-bottom:6px; display:block;"></i>
            <p style="font-size:12px; margin:0;">You haven't sent any exchange requests to other drivers yet.</p>
          </div>
        `;
      } else {
        let html = '';
        sent.forEach(s => {
          let statusBadge = `<span class="badge badge-warning">Pending Review</span>`;
          let withdrawBtn = '';
          if (s.status === 'accepted') statusBadge = `<span class="badge badge-success">Accepted & Swapped</span>`;
          else if (s.status === 'rejected') statusBadge = `<span class="badge badge-danger">Declined</span>`;
          else if (s.status === 'cancelled') statusBadge = `<span class="badge badge-secondary">Withdrawn</span>`;

          if (s.status === 'pending') {
            withdrawBtn = `
              <button class="btn-primary" style="font-size:11px; padding:4px 8px; background:#10b981; border-color:#10b981; font-weight:700;" onclick="simulateOwnerAccept(${s.request_id})" title="Simulate partner driver accepting this proposal">
                <i class="fas fa-check-double"></i> Simulate Accept
              </button>
              <button class="btn-secondary" style="font-size:11px; padding:4px 10px; color:#ef4444; border-color:#ef4444; font-weight:700;" onclick="cancelExchangeRequest(${s.request_id})">
                <i class="fas fa-times"></i> Withdraw
              </button>
            `;
          }

          html += `
            <div class="exchange-req-row">
              <div>
                <h5 style="font-size:13px; font-weight:800; color:#0f172a; margin:0;">Target Slot ${s.owner_slot_number} (${s.owner_floor})</h5>
                <span style="font-size:11px; color:#64748b;">Offered by ${s.owner_name} • ${s.owner_date} (${s.owner_start_time}-${s.owner_end_time})</span>
              </div>
              <div>
                <span style="font-size:11px; color:#475569;">In exchange for your: <strong>Slot ${s.requester_slot_number}</strong> (${s.requester_floor})</span>
              </div>
              <div style="display:flex; align-items:center; gap:10px;">
                ${statusBadge}
                ${withdrawBtn}
              </div>
            </div>
          `;
        });
        sentContainer.innerHTML = html;
      }
    }

    // 3. Render Exchange History
    if (histContainer) {
      if (history.length === 0) {
        histContainer.innerHTML = `
          <div style="text-align:center; padding:24px 10px; color:#94a3b8;">
            <i class="fas fa-history" style="font-size:22px; margin-bottom:6px; display:block;"></i>
            <p style="font-size:12px; margin:0;">No past exchange records found.</p>
          </div>
        `;
      } else {
        let html = `
          <table class="inventory-table" style="width:100%;">
            <thead>
              <tr>
                <th>Date & Time</th>
                <th>Swap Details</th>
                <th>Exchanged With</th>
                <th>Status</th>
                <th>Audit Note</th>
              </tr>
            </thead>
            <tbody>
        `;
        history.forEach(h => {
          const isUser1 = h.user1_id === currentUserId;
          const myOldSlot = isUser1 ? h.user1_old_slot_no : h.user2_old_slot_no;
          const myNewSlot = isUser1 ? h.user1_new_slot_no : h.user2_new_slot_no;
          const partnerName = isUser1 ? h.user2_name : h.user1_name;

          let statusTag = h.status === 'completed' ? `<span class="badge badge-success">Completed</span>` : `<span class="badge badge-danger">Declined</span>`;

          html += `
            <tr>
              <td>${h.exchanged_at}</td>
              <td><strong>Slot ${myOldSlot}</strong> <i class="fas fa-arrow-right" style="color:var(--primary); font-size:10px; margin:0 4px;"></i> <strong>Slot ${myNewSlot}</strong></td>
              <td>${partnerName}</td>
              <td>${statusTag}</td>
              <td style="font-size:11px; color:#64748b;">${h.action_note || 'N/A'}</td>
            </tr>
          `;
        });
        html += `</tbody></table>`;
        histContainer.innerHTML = html;
      }
    }

  } catch (err) {
    console.error(err);
  }
}

async function cancelExchangeRequest(requestId) {
  if (!confirm('Are you sure you want to withdraw this exchange proposal?')) return;
  try {
    const res = await fetch('/api/exchange/cancel-request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId, request_id: requestId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'info');
      loadExchangeView();
    } else {
      showToast(data.message || 'Failed to withdraw request.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error withdrawing request.', 'error');
  }
}

async function respondExchangeRequest(requestId, action) {
  const confirmMsg = action === 'accept'
    ? 'Are you sure you want to accept this exchange? Your parking slot will be swapped immediately.'
    : 'Are you sure you want to decline this exchange request?';

  if (!confirm(confirmMsg)) return;

  try {
    const res = await fetch('/api/exchange/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUserId,
        request_id: requestId,
        action: action
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, action === 'accept' ? 'success' : 'info');
      loadExchangeView();
      refreshAllDashboardData();
      if (typeof loadMyBookings === 'function') loadMyBookings();
    } else {
      showToast(data.message || 'Failed to respond to exchange request.', 'error');
    }
  } catch (err) {
    console.error(err);
    showToast('Network error responding to exchange request.', 'error');
  }
}

function switchExchangeSubTab(tabName, btnEl) {
  document.querySelectorAll('.exchange-subview').forEach(v => v.style.display = 'none');
  const target = document.getElementById(`exchange-subview-${tabName}`);
  if (target) target.style.display = 'block';

  // Toggle button active state
  if (btnEl && btnEl.parentElement) {
    btnEl.parentElement.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
    btnEl.classList.add('active');
  } else {
    // If called programmatically without btnEl
    const directBtn = document.getElementById(`btnExchangeTab${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`);
    if (directBtn && directBtn.parentElement) {
      directBtn.parentElement.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
      directBtn.classList.add('active');
    }
  }
}

async function quickSeedBookingForExchange() {
  try {
    const res = await fetch('/api/exchange/quick-seed-booking', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadExchangeView();
      refreshAllDashboardData();
    } else {
      showToast(data.message || 'Failed to seed booking', 'error');
    }
  } catch (err) {
    showToast('Network error seeding booking.', 'error');
  }
}

async function seedDemoExchangeSlot() {
  try {
    const res = await fetch('/api/exchange/seed-demo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      searchExchangeOpportunities();
    } else {
      showToast(data.message || 'Failed to generate demo slot', 'error');
    }
  } catch (err) {
    showToast('Network error generating demo slot.', 'error');
  }
}

async function simulateIncomingExchangeRequest() {
  try {
    const res = await fetch('/api/exchange/simulate-incoming-request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadExchangeView();
      // Auto switch to received subtab so the incoming request is front and center
      const recBtn = document.getElementById('btnExchangeTabReceived');
      if (recBtn) switchExchangeSubTab('received', recBtn);
      fetchNotifications();
    } else {
      showToast(data.message || 'Failed to simulate incoming request', 'error');
    }
  } catch (err) {
    showToast('Network error simulating incoming request.', 'error');
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
      showToast(`🎉 Slot Exchanged! ${data.message || 'Exchange successfully completed.'}`, 'success');
      loadExchangeView();
      refreshAllDashboardData();
      fetchNotifications();
      if (typeof loadMyBookings === 'function') loadMyBookings();
    } else if (!isAuto) {
      showToast(data.message || 'Failed to accept proposal.', 'error');
    }
  } catch (err) {
    if (!isAuto) showToast('Network error processing simulated acceptance.', 'error');
  }
}

// ==========================================================================
// MODULE 9: NOTIFICATION MODULE CLIENT CONTROLLER
// ==========================================================================
let allLoadedNotifications = [];
let currentNotifFilter = 'all';

async function fetchNotifications(filterType = null) {
  try {
    if (filterType) currentNotifFilter = filterType;
    let url = `/api/notifications?user_id=${currentUserId}`;
    if (currentNotifFilter && currentNotifFilter !== 'all') {
      url += `&type=${encodeURIComponent(currentNotifFilter)}`;
    }

    const res = await fetch(url);
    const data = await res.json();
    if (data.status === 'success') {
      allLoadedNotifications = data.notifications || [];
      const unreadCount = data.unread_count || 0;

      // Update Header Bell Badge
      const badgeCountEl = document.getElementById('notifBadgeCount');
      if (badgeCountEl) {
        if (unreadCount > 0) {
          badgeCountEl.innerText = unreadCount > 99 ? '99+' : unreadCount;
          badgeCountEl.style.display = 'flex';
        } else {
          badgeCountEl.style.display = 'none';
        }
      }

      // Update Sidebar Badge
      const sidebarBadge = document.getElementById('sidebarNotifBadge');
      if (sidebarBadge) {
        if (unreadCount > 0) {
          sidebarBadge.innerText = unreadCount > 99 ? '99+' : unreadCount;
          sidebarBadge.style.display = 'inline-block';
        } else {
          sidebarBadge.style.display = 'none';
        }
      }

      // Update Header Unread Text in dropdown
      const unreadText = document.getElementById('notifHeaderUnread');
      if (unreadText) {
        unreadText.innerText = `${unreadCount} unread`;
      }

      // Render Dropdown List
      renderNotificationDropdown(allLoadedNotifications);

      // Render Full View List if on notifications tab
      renderFullNotificationsView(allLoadedNotifications);
    }
  } catch (err) {
    console.error('Error fetching notifications:', err);
  }
}

function renderNotificationDropdown(notifications) {
  const container = document.getElementById('notifItemsList');
  if (!container) return;

  if (!notifications || notifications.length === 0) {
    container.innerHTML = `
      <div class="notif-empty-state">
        <i class="far fa-bell-slash"></i>
        <p>No notifications found</p>
      </div>
    `;
    return;
  }

  let html = '';
  notifications.forEach(n => {
    const iconClass = getNotifIcon(n.type);
    const timeAgo = formatTimeAgo(n.created_at);
    const isUnread = n.is_read === 0 || n.is_read === false;

    html += `
      <div class="notif-item type-${n.type} ${isUnread ? 'unread' : ''}" onclick="handleNotifClick(${n.notification_id}, '${n.type}', ${n.related_id || 'null'})">
        <div class="notif-icon-col">
          <i class="fas ${iconClass}"></i>
        </div>
        <div class="notif-body">
          <div class="notif-title">${escapeHtml(n.title)}</div>
          <div class="notif-msg">${escapeHtml(n.message)}</div>
          <div class="notif-time"><i class="far fa-clock"></i> ${timeAgo}</div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function renderFullNotificationsView(notifications) {
  const container = document.getElementById('fullNotificationsList');
  if (!container) return;

  if (!notifications || notifications.length === 0) {
    container.innerHTML = `
      <div class="notif-empty-state" style="padding: 40px 20px;">
        <i class="far fa-bell-slash" style="font-size:42px;"></i>
        <h4 style="margin: 8px 0; color:#334155;">No Notifications</h4>
        <p>You have no notifications matching this category.</p>
      </div>
    `;
    return;
  }

  let html = '';
  notifications.forEach(n => {
    const iconClass = getNotifIcon(n.type);
    const timeAgo = formatTimeAgo(n.created_at);
    const isUnread = n.is_read === 0 || n.is_read === false;

    html += `
      <div class="notif-full-card type-${n.type} ${isUnread ? 'unread' : ''}">
        <div class="notif-icon-col" style="width:42px; height:42px; font-size:18px;">
          <i class="fas ${iconClass}"></i>
        </div>
        <div class="notif-body">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
            <h4 class="notif-title" style="font-size:14px;">${escapeHtml(n.title)}</h4>
            <span class="badge ${isUnread ? 'badge-primary' : 'badge-light'}" style="font-size:10px;">
              ${isUnread ? 'New' : 'Read'}
            </span>
          </div>
          <p class="notif-msg" style="font-size:13px; margin: 4px 0 8px 0;">${escapeHtml(n.message)}</p>
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
            <span class="notif-time"><i class="far fa-clock"></i> ${n.created_at} (${timeAgo})</span>
            <div style="display:flex; gap:6px;">
              ${isUnread ? `<button class="btn-secondary" style="font-size:11px; padding:3px 8px;" onclick="markNotificationRead(${n.notification_id})"><i class="fas fa-check"></i> Mark Read</button>` : ''}
              <button class="btn-primary" style="font-size:11px; padding:3px 8px;" onclick="handleNotifAction('${n.type}', ${n.related_id || 'null'})"><i class="fas fa-external-link-alt"></i> Action</button>
            </div>
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

function getNotifIcon(type) {
  switch (type) {
    case 'booking_confirmation': return 'fa-check-circle';
    case 'booking_reminder': return 'fa-bell';
    case 'parking_expiry_alert': return 'fa-hourglass-half';
    case 'overstay_alert': return 'fa-exclamation-triangle';
    case 'exchange_request': return 'fa-exchange-alt';
    case 'exchange_accepted': return 'fa-handshake';
    case 'exchange_rejected': return 'fa-times-circle';
    case 'cancellation': return 'fa-ban';
    default: return 'fa-info-circle';
  }
}

function formatTimeAgo(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr.replace(' ', 'T'));
    const now = new Date();
    const diffSec = Math.floor((now - d) / 1000);
    if (isNaN(diffSec)) return dateStr;
    if (diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  } catch (e) {
    return dateStr;
  }
}

function toggleNotificationCenter(forceState = null) {
  const dropdown = document.getElementById('notifDropdown');
  if (!dropdown) return;
  if (forceState !== null) {
    dropdown.style.display = forceState ? 'block' : 'none';
  } else {
    dropdown.style.display = dropdown.style.display === 'none' || !dropdown.style.display ? 'block' : 'none';
  }
  if (dropdown.style.display === 'block') {
    fetchNotifications();
  }
}

async function markNotificationRead(notifId) {
  try {
    const res = await fetch(`/api/notifications/${notifId}/read`, { method: 'POST' });
    if (res.ok) {
      await fetchNotifications();
    }
  } catch (err) {
    console.error(err);
  }
}

async function markAllNotificationsRead() {
  try {
    const res = await fetch('/api/notifications/mark-all-read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId })
    });
    if (res.ok) {
      if (typeof showToast === 'function') showToast('All notifications marked as read', 'success');
      await fetchNotifications();
    }
  } catch (err) {
    console.error(err);
  }
}

async function clearUserNotifications() {
  try {
    const res = await fetch('/api/notifications/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUserId })
    });
    if (res.ok) {
      if (typeof showToast === 'function') showToast('Notifications cleared', 'info');
      await fetchNotifications();
    }
  } catch (err) {
    console.error(err);
  }
}

async function triggerCheckAlerts() {
  try {
    const res = await fetch('/api/notifications/check-alerts', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      if (typeof showToast === 'function') showToast(`Scan complete: ${data.new_alerts_generated} new alerts checked against clock`, 'info');
      await fetchNotifications();
    }
  } catch (err) {
    console.error(err);
  }
}

function filterNotifications(type, btnEl) {
  currentNotifFilter = type;
  if (btnEl && btnEl.parentElement) {
    btnEl.parentElement.querySelectorAll('.notif-pill').forEach(b => b.classList.remove('active'));
    btnEl.classList.add('active');
  }
  fetchNotifications(type);
}

function filterMainNotifications(type, btnEl) {
  currentNotifFilter = type;
  if (btnEl && btnEl.parentElement) {
    btnEl.parentElement.querySelectorAll('.notif-main-filter-btn').forEach(b => b.classList.remove('active'));
    btnEl.classList.add('active');
  }
  fetchNotifications(type);
}

function handleNotifClick(notifId, type, relatedId) {
  markNotificationRead(notifId);
  handleNotifAction(type, relatedId);
  toggleNotificationCenter(false);
}

function handleNotifAction(type, relatedId) {
  if (type === 'booking_confirmation' || type === 'booking_reminder' || type === 'parking_expiry_alert') {
    showTab('my-bookings');
    if (relatedId && typeof viewDigitalPass === 'function') {
      viewDigitalPass(relatedId);
    }
  } else if (type === 'overstay_alert') {
    showTab('overstays');
  } else if (type === 'exchange_request' || type === 'exchange_accepted' || type === 'exchange_rejected') {
    showTab('exchange');
  } else if (type === 'cancellation') {
    showTab('my-bookings');
  }
}

// ==========================================
// MODULE 5: PARKING SEARCH & DIRECTORY
// ==========================================

let allSearchLotsData = [];
let activeSearchFilterTag = 'all';

async function loadParkingSearchResults(query = '') {
  const container = document.getElementById('searchResultsListContainer');
  const countPill = document.getElementById('searchResultCountPill');
  if (!container) return;

  container.innerHTML = `
    <div style="text-align:center; padding:30px 10px; color:#64748b;">
      <i class="fas fa-spinner fa-spin" style="font-size:24px; color:var(--primary); margin-bottom:10px;"></i>
      <p style="font-size:13px; margin:0;">Scanning parking facilities across Mangaluru...</p>
    </div>
  `;

  try {
    const url = query ? `/api/lots/search?q=${encodeURIComponent(query)}` : '/api/lots';
    const res = await fetch(url);
    const data = await res.json();
    const lots = data.lots || [];
    allSearchLotsData = lots;

    if (countPill) {
      countPill.innerText = `${lots.length} Facilities Available`;
    }

    renderParkingSearchResults(lots);
    if (lots.length > 0) {
      updateSearchFacilityPreview(lots[0]);
    }
  } catch (err) {
    console.error("Error loading parking search results:", err);
    container.innerHTML = `
      <div class="panel-card" style="text-align:center; padding:24px; color:#ef4444;">
        <i class="fas fa-exclamation-circle" style="font-size:24px; margin-bottom:8px;"></i>
        <p style="font-size:13px; margin:0;">Failed to load parking facilities. Please try again.</p>
      </div>
    `;
  }
}

function renderParkingSearchResults(lots) {
  const container = document.getElementById('searchResultsListContainer');
  if (!container) return;

  if (lots.length === 0) {
    container.innerHTML = `
      <div class="panel-card" style="text-align:center; padding:36px 16px; border:2px dashed #cbd5e1;">
        <i class="fas fa-search-minus" style="font-size:32px; color:#94a3b8; margin-bottom:12px;"></i>
        <h4 style="font-size:15px; font-weight:800; color:#0f172a; margin-bottom:6px;">No Parking Lots Match Your Query</h4>
        <p style="font-size:12px; color:#64748b; max-width:380px; margin:0 auto 16px;">Try searching for "Mangaluru", "City Centre", "Mall", or "Railway Station".</p>
        <button class="btn-primary" style="font-size:12px; padding:6px 14px;" onclick="resetParkingSearch()">
          <i class="fas fa-undo"></i> Show All Mangaluru Facilities
        </button>
      </div>
    `;
    return;
  }

  const facilityImages = {
    4: '/static/images/city_parking_mangaluru.jpg',
    2: 'https://images.unsplash.com/photo-1590674899484-d5640e854abe?auto=format&fit=crop&w=600&q=80',
    3: 'https://images.unsplash.com/photo-1506521781263-d8422e82f27a?auto=format&fit=crop&w=600&q=80',
    1: 'https://images.unsplash.com/photo-1573348722427-f1d6819fdf98?auto=format&fit=crop&w=600&q=80'
  };

  let html = '';
  lots.forEach((lot) => {
    const lotId = lot.lot_id;
    const availCount = lot.available_count || (lot.total_slots - (lot.occupied_count || 0) - (lot.reserved_count || 0));
    const totalSlots = lot.total_slots || lot.actual_slot_count || 50;
    const imgSrc = facilityImages[lotId] || '/static/images/city_parking_mangaluru.jpg';
    const isCity = lotId === 4 || (lot.lot_name && lot.lot_name.toLowerCase().includes('city'));

    let displayName = lot.lot_name;
    if (isCity) displayName = 'City Centre Parking';
    else if (lot.lot_name === 'Mall') displayName = 'Central Mall Parking';
    else if (lot.lot_name === 'Public places') displayName = 'Railway Station Parking';
    else if (lot.lot_name === 'Institutions') displayName = 'Campus & Institutions Parking';

    html += `
      <div class="panel-card search-facility-card" id="searchFacilityCard-${lotId}" style="display:flex; flex-direction:column; gap:12px; border-left:4px solid ${isCity ? 'var(--primary)' : '#3b82f6'}; transition:all 0.2s ease; cursor:pointer;" onclick="highlightSearchFacility(${lotId})">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:14px;">
          <div style="width:78px; height:78px; border-radius:10px; overflow:hidden; flex-shrink:0; border:1px solid #e2e8f0; position:relative;">
            <img src="${imgSrc}" alt="${displayName}" style="width:100%; height:100%; object-fit:cover;" onerror="this.src='/static/images/city_parking_mangaluru.jpg'">
            <div style="position:absolute; bottom:3px; left:3px; background:rgba(15,23,42,0.85); color:#ffffff; font-size:8px; font-weight:800; padding:1px 4px; border-radius:3px;">
              ${lot.total_floors || 2}F
            </div>
          </div>

          <div style="flex:1; min-width:180px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
              <h4 style="font-size:15px; font-weight:800; color:#0f172a; margin:0;">${displayName}</h4>
              <span class="badge badge-success" style="font-size:11px; padding:3px 8px; font-weight:800;">
                <span class="pulse-dot" style="width:6px; height:6px; background:#10b981; border-radius:50%; display:inline-block; margin-right:4px;"></span>
                ${availCount} slots available
              </span>
            </div>
            <p style="font-size:12px; color:#64748b; margin:0 0 6px 0;">
              <i class="fas fa-map-marker-alt" style="color:var(--primary); margin-right:4px;"></i> ${lot.location || 'Mangaluru'}
            </p>
            <div style="display:flex; gap:12px; font-size:11.5px; color:#475569; flex-wrap:wrap;">
              <span><i class="far fa-clock" style="color:#d97706; margin-right:4px;"></i> ${lot.operating_hours || '24/7 Open'}</span>
              <span><i class="fas fa-tag" style="color:var(--primary); margin-right:4px;"></i> ₹${lot.hourly_rate || 40}/hr</span>
              <span><i class="fas fa-th-large" style="color:#6366f1; margin-right:4px;"></i> ${totalSlots} Total Slots</span>
            </div>
          </div>
        </div>

        <div style="display:flex; justify-content:flex-end; gap:8px; border-top:1px solid #f1f5f9; padding-top:10px; margin-top:2px;">
          <button type="button" class="btn-secondary" style="font-size:11.5px; padding:6px 12px;" onclick="event.stopPropagation(); viewFacilityInFloorMap(${lotId})">
            <i class="fas fa-th-list"></i> View Slots
          </button>
          <button type="button" class="btn-primary" style="font-size:11.5px; padding:6px 14px; font-weight:800;" onclick="event.stopPropagation(); bookFacilityDirectly(${lotId})">
            <i class="fas fa-calendar-check"></i> Book Slot <i class="fas fa-arrow-right" style="margin-left:4px;"></i>
          </button>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

let searchDebounceTimer = null;
function handleParkingSearchInput(val) {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    loadParkingSearchResults(val.trim());
  }, 250);
}

function executeParkingSearch() {
  const input = document.getElementById('parkingSearchInput');
  const val = input ? input.value.trim() : '';
  loadParkingSearchResults(val);
}

function resetParkingSearch() {
  const input = document.getElementById('parkingSearchInput');
  if (input) input.value = '';
  document.querySelectorAll('#view-search .btn-sim-tick').forEach(b => b.classList.remove('active'));
  const firstBtn = document.querySelector('#view-search .btn-sim-tick');
  if (firstBtn) firstBtn.classList.add('active');
  loadParkingSearchResults('');
}

function filterSearchByQuickTag(tag, btn) {
  document.querySelectorAll('#view-search .btn-sim-tick').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const input = document.getElementById('parkingSearchInput');
  if (tag === 'all') {
    if (input) input.value = '';
    loadParkingSearchResults('');
  } else {
    if (input) input.value = tag;
    loadParkingSearchResults(tag);
  }
}

function highlightSearchFacility(lotId) {
  const card = document.getElementById(`searchFacilityCard-${lotId}`);
  if (card) {
    document.querySelectorAll('.search-facility-card').forEach(c => {
      c.style.boxShadow = '';
      c.style.borderColor = '';
    });
    card.style.boxShadow = '0 0 0 3px rgba(13, 148, 136, 0.4)';
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  const lot = allSearchLotsData.find(l => l.lot_id === lotId);
  if (lot) {
    updateSearchFacilityPreview(lot);
  }
}

function updateSearchFacilityPreview(lot) {
  const preview = document.getElementById('searchSelectedFacilityPreview');
  if (!preview || !lot) return;

  const lotId = lot.lot_id;
  const availCount = lot.available_count || (lot.total_slots - (lot.occupied_count || 0) - (lot.reserved_count || 0));
  const isCity = lotId === 4 || (lot.lot_name && lot.lot_name.toLowerCase().includes('city'));
  let displayName = lot.lot_name;
  if (isCity) displayName = 'City Centre Parking';
  else if (lot.lot_name === 'Mall') displayName = 'Central Mall Parking';
  else if (lot.lot_name === 'Public places') displayName = 'Railway Station Parking';
  else if (lot.lot_name === 'Institutions') displayName = 'Campus & Institutions Parking';

  preview.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
      <div>
        <span style="font-size:10px; text-transform:uppercase; color:#94a3b8; font-weight:800; letter-spacing:0.5px;">SELECTED FACILITY</span>
        <h4 style="font-size:15px; font-weight:800; color:#0f172a; margin:2px 0 0 0;">${displayName}</h4>
      </div>
      <span class="badge badge-success" style="font-size:11px; font-weight:800;">
        ${availCount} Free Slots
      </span>
    </div>
    <div style="font-size:12px; color:#475569; margin-bottom:12px; line-height:1.5;">
      <div><i class="fas fa-map-pin" style="color:var(--primary); margin-right:4px;"></i> ${lot.location || 'Mangaluru'}</div>
      <div><i class="fas fa-tag" style="color:#d97706; margin-right:4px;"></i> ₹${lot.hourly_rate || 40} / hr • Operating: ${lot.operating_hours || '24/7'}</div>
    </div>
    <div style="display:flex; gap:8px;">
      <button class="btn-primary" style="flex:1; font-size:12px; padding:8px 12px; font-weight:800;" onclick="bookFacilityDirectly(${lotId})">
        <i class="fas fa-microchip"></i> Reserve Optimal Slot
      </button>
      <button class="btn-secondary" style="font-size:12px; padding:8px 12px;" onclick="viewFacilityInFloorMap(${lotId})">
        <i class="fas fa-th-list"></i> View Slots
      </button>
    </div>
  `;
}

function bookFacilityDirectly(lotId) {
  showTab('reservations');
  const sel = document.getElementById('resLotId');
  if (sel) {
    sel.value = String(lotId);
    handleLotPreferenceChange();
  }
}

function viewFacilityInFloorMap(lotId) {
  showTab('map');
  const lotFilter = document.getElementById('slotsTableLotFilter');
  if (lotFilter) {
    lotFilter.value = String(lotId);
  }
  switchSlotSubTab('all-slots-table');
}



