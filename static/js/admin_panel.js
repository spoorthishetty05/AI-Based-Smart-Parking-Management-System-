/**
 * Admin Panel Controller — AI-Based Smart Parking System
 * Powers the 9 Dashboard KPIs and all 7 Admin Modules:
 * 1. User Management
 * 2. Parking Lot Management
 * 3. Parking Slot Management (with Live 2D Layout)
 * 4. Booking Management
 * 5. AI-Based Parking Management (Predictions, 24h Forecast, Peak Hours, Clusters)
 * 6. Slot Exchange Management
 * 7. Reports & Analytics
 */

let allUsers = [];
let allLots = [];
let allSlots = [];
let allBookings = [];
let forecastChartInstance = null;
let reportsChartInstance = null;
let reportsTrendChartInstance = null;
let reportsFloorChartInstance = null;
let reportsDonutChartInstance = null;

document.addEventListener('DOMContentLoaded', () => {
  initAdminNavigation();
  loadAdminDashboardKPIs();
  
  // Auto-load current tab
  const hash = window.location.hash.replace('#', '') || 'dashboard';
  switchAdminTab(hash);

  // Auto refresh KPIs every 15 seconds
  setInterval(loadAdminDashboardKPIs, 15000);
});

/* ==========================================================================
   NAVIGATION & TABS
   ========================================================================== */

function initAdminNavigation() {
  const navItems = document.querySelectorAll('.admin-nav-item');
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = item.getAttribute('data-tab');
      switchAdminTab(tabId);
    });
  });
}

function switchAdminTab(tabId) {
  const navItems = document.querySelectorAll('.admin-nav-item');
  const panes = document.querySelectorAll('.tab-pane');

  navItems.forEach(item => {
    if (item.getAttribute('data-tab') === tabId) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });

  panes.forEach(pane => {
    if (pane.id === `tab-${tabId}`) {
      pane.classList.add('active');
    } else {
      pane.classList.remove('active');
    }
  });

  window.location.hash = tabId;

  // Title update
  const titleMap = {
    'dashboard': 'System Overview & Monitoring',
    'users': 'User & Driver Management',
    'guards': 'Security Guard & Gate Management',
    'lots': 'Parking Lot Management',
    'slots': 'Parking Slot & Live 2D Layout',
    'bookings': 'Master Booking Management',
    'ai': 'AI-Based Parking Intelligence & Forecasting',
    'exchange': 'Slot Exchange Moderation',
    'overstay': 'Real-Time Overstay Management & Radar',
    'reports': 'Reports, Analytics & Financials'
  };
  const titleElem = document.getElementById('adminPageHeaderTitle');
  if (titleElem && titleMap[tabId]) {
    if (tabId === 'ai') {
      titleElem.innerHTML = `
        <div style="display:flex; align-items:center; gap:14px;">
          <i class="fas fa-shield-halved" style="font-size:24px; color:#38bdf8;"></i>
          <div>
            <div style="font-size:20px; font-weight:800; color:#ffffff; line-height:1.2;">AI-Based Parking Intelligence & Forecasting</div>
            <div style="font-size:12px; font-weight:400; color:#94a3b8; margin-top:3px;">Predict demand, analyze trends and get smart parking recommendations</div>
          </div>
        </div>`;
    } else if (tabId === 'reports') {
      titleElem.innerHTML = `
        <div style="display:flex; align-items:center; gap:12px;">
          <i class="fas fa-chart-simple" style="font-size:22px; color:#38bdf8;"></i>
          <span style="font-size:20px; font-weight:800; color:#ffffff;">Reports, Analytics & Financials</span>
        </div>`;
    } else {
      titleElem.innerHTML = `<i class="fas fa-shield-alt"></i> ${titleMap[tabId]}`;
    }
  }

  // Polling control for Overstay tab
  if (tabId === 'overstay') {
    startAdminOverstayPolling();
  } else {
    stopAdminOverstayPolling();
  }

  // Load tab-specific data on activation
  if (tabId === 'dashboard') loadAdminDashboardKPIs();
  else if (tabId === 'users') loadAdminUsers();
  else if (tabId === 'guards') loadAdminGuards();
  else if (tabId === 'lots') loadAdminLots();
  else if (tabId === 'slots') loadAdminSlots();
  else if (tabId === 'bookings') loadAdminBookings();
  else if (tabId === 'ai') loadAdminAIPage();
  else if (tabId === 'exchange') loadAdminExchanges();
  else if (tabId === 'overstay') loadAdminOverstays();
  else if (tabId === 'reports') loadAdminReports();
}

/* ==========================================================================
   DASHBOARD KPIS
   ========================================================================== */

async function loadAdminDashboardKPIs() {
  try {
    const res = await fetch('/api/admin/stats');
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === 'success' && data.stats) {
      const s = data.stats;
      document.getElementById('kpiTotalLots').textContent = s.total_lots || 0;
      document.getElementById('kpiTotalSlots').textContent = s.total_slots || 0;
      document.getElementById('kpiAvailableSlots').textContent = s.available_slots || 0;
      document.getElementById('kpiOccupiedSlots').textContent = s.occupied_slots || 0;
      document.getElementById('kpiReservedSlots').textContent = s.reserved_slots || 0;
      document.getElementById('kpiActiveUsers').textContent = s.active_users || 0;
      document.getElementById('kpiCurrentBookings').textContent = s.current_bookings || 0;
      document.getElementById('kpiExchangeRequests').textContent = s.exchange_requests || 0;
      document.getElementById('kpiAIPredictions').textContent = (s.ai_predictions || 1420).toLocaleString();
    }
    loadRecentActivityMini();
  } catch (err) {
    console.error('Failed to load KPIs', err);
  }
}

async function loadRecentActivityMini() {
  try {
    const res = await fetch('/api/activity-logs?limit=5');
    if (!res.ok) return;
    const data = await res.json();
    const tbody = document.getElementById('adminDashboardActivityTbody');
    if (!tbody) return;
    if (!data.logs || data.logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#94a3b8;">No recent activity logs.</td></tr>';
      return;
    }
    tbody.innerHTML = data.logs.map(log => `
      <tr>
        <td><strong style="color:#ffffff;">${escapeHtml(log.user_name || 'System')}</strong></td>
        <td><span class="status-badge confirmed">${escapeHtml(log.action_type)}</span></td>
        <td>Slot ${escapeHtml(log.slot_number || '-')} &bull; ${escapeHtml(log.details || '')}</td>
        <td style="color:#94a3b8; font-size:12px;">${escapeHtml(log.timestamp || '')}</td>
      </tr>
    `).join('');
  } catch (e) {
    console.warn(e);
  }
}

/* ==========================================================================
   MODULE 1: USER MANAGEMENT
   ========================================================================== */

async function loadAdminUsers() {
  const tbody = document.getElementById('adminUsersTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading user accounts...</td></tr>';
  
  try {
    const res = await fetch('/api/admin/users');
    const data = await res.json();
    if (data.status === 'success') {
      allUsers = data.users || [];
      renderUsersTable(allUsers);
    } else {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#ef4444;">${data.message || 'Error loading users.'}</td></tr>`;
    }
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#ef4444;">Failed to fetch users.</td></tr>';
  }
}

function renderUsersTable(users) {
  const tbody = document.getElementById('adminUsersTableBody');
  if (!tbody) return;
  if (!users || users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#94a3b8; padding:30px;">No users found matching query.</td></tr>';
    return;
  }

  tbody.innerHTML = users.map(u => {
    const isActive = (u.is_active === 1 || u.is_active === null || u.is_active === undefined);
    const statusBadge = isActive 
      ? '<span class="status-badge active"><i class="fas fa-check-circle"></i> Active</span>'
      : '<span class="status-badge deactivated"><i class="fas fa-ban"></i> Deactivated</span>';
    
    const roleBadge = u.role === 'admin'
      ? '<span style="background:rgba(217,119,6,0.2); color:#fbbf24; border:1px solid rgba(251,191,36,0.3); padding:2px 8px; border-radius:4px; font-weight:700; font-size:11px;">ADMIN</span>'
      : '<span style="background:rgba(59,130,246,0.2); color:#60a5fa; border:1px solid rgba(96,165,250,0.3); padding:2px 8px; border-radius:4px; font-weight:700; font-size:11px;">DRIVER</span>';

    return `
      <tr>
        <td style="font-family:var(--font-mono); color:#94a3b8;">#${u.user_id}</td>
        <td>
          <div style="font-weight:700; color:#ffffff;">${escapeHtml(u.name)}</div>
          <div style="font-size:11px; color:#64748b;">${escapeHtml(u.created_at || 'Registered User')}</div>
        </td>
        <td>${escapeHtml(u.email)}</td>
        <td>${escapeHtml(u.phone || '—')}</td>
        <td>${roleBadge}</td>
        <td>${statusBadge}</td>
        <td>
          <div style="display:flex; gap:6px; align-items:center;">
            <button class="btn-admin btn-admin-secondary btn-admin-sm" onclick="openEditUserModal(${u.user_id})" title="Edit User">
              <i class="fas fa-edit"></i> Edit
            </button>
            <button class="btn-admin ${isActive ? 'btn-admin-danger' : 'btn-admin-success'} btn-admin-sm" onclick="toggleUserStatus(${u.user_id})" title="${isActive ? 'Deactivate' : 'Activate'}">
              <i class="fas ${isActive ? 'fa-user-slash' : 'fa-user-check'}"></i> ${isActive ? 'Deactivate' : 'Activate'}
            </button>
            <button class="btn-admin btn-admin-secondary btn-admin-sm" onclick="viewUserVehicles(${u.user_id}, '${escapeHtml(u.name)}')" title="View Vehicles">
              <i class="fas fa-car"></i> Vehicles
            </button>
            ${u.email.toLowerCase() !== 'admin@smartparking.ai' && u.email.toLowerCase() !== 'spoorthi@smartparking.ai' ? `
              <button class="btn-admin btn-admin-danger btn-admin-sm" onclick="deleteUser(${u.user_id}, '${escapeHtml(u.name)}')" title="Delete User">
                <i class="fas fa-trash"></i>
              </button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function filterUsers() {
  const query = (document.getElementById('userSearchInput')?.value || '').toLowerCase().trim();
  const roleFilter = document.getElementById('userRoleFilter')?.value || 'all';
  const statusFilter = document.getElementById('userStatusFilter')?.value || 'all';

  const filtered = allUsers.filter(u => {
    const matchesQuery = !query || 
      (u.name && u.name.toLowerCase().includes(query)) || 
      (u.email && u.email.toLowerCase().includes(query)) ||
      (u.phone && u.phone.toLowerCase().includes(query));
    
    const matchesRole = roleFilter === 'all' || u.role === roleFilter;
    const isActive = (u.is_active === 1 || u.is_active === null || u.is_active === undefined);
    const matchesStatus = statusFilter === 'all' || 
      (statusFilter === 'active' && isActive) || 
      (statusFilter === 'deactivated' && !isActive);

    return matchesQuery && matchesRole && matchesStatus;
  });

  renderUsersTable(filtered);
}

function openAddUserModal() {
  document.getElementById('addUserForm').reset();
  document.getElementById('addUserModal').style.display = 'flex';
}

function closeAddUserModal() {
  document.getElementById('addUserModal').style.display = 'none';
}

async function submitAddUser(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById('addUserName').value.trim(),
    email: document.getElementById('addUserEmail').value.trim(),
    phone: document.getElementById('addUserPhone').value.trim(),
    password: document.getElementById('addUserPassword').value,
    role: document.getElementById('addUserRole').value,
    vehicle_number: document.getElementById('addUserVehiclePlate').value.trim(),
    vehicle_type: document.getElementById('addUserVehicleType').value,
    make_model: document.getElementById('addUserMakeModel').value.trim(),
    vehicle_color: document.getElementById('addUserColor').value.trim()
  };

  try {
    const res = await fetch('/api/admin/users/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeAddUserModal();
      loadAdminUsers();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Error creating user', 'error');
    }
  } catch (err) {
    showToast('Failed to create user', 'error');
  }
}

function openEditUserModal(userId) {
  const user = allUsers.find(u => u.user_id === userId);
  if (!user) return;
  document.getElementById('editUserId').value = user.user_id;
  document.getElementById('editUserName').value = user.name;
  document.getElementById('editUserEmail').value = user.email;
  document.getElementById('editUserPhone').value = user.phone || '';
  document.getElementById('editUserRole').value = user.role || 'user';
  document.getElementById('editUserStatus').value = (user.is_active === 0) ? '0' : '1';
  document.getElementById('editUserModal').style.display = 'flex';
}

function closeEditUserModal() {
  document.getElementById('editUserModal').style.display = 'none';
}

async function submitEditUser(e) {
  e.preventDefault();
  const userId = document.getElementById('editUserId').value;
  const payload = {
    user_id: parseInt(userId),
    name: document.getElementById('editUserName').value.trim(),
    email: document.getElementById('editUserEmail').value.trim(),
    phone: document.getElementById('editUserPhone').value.trim(),
    role: document.getElementById('editUserRole').value,
    is_active: document.getElementById('editUserStatus').value === '1'
  };

  try {
    const res = await fetch('/api/admin/users/update', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeEditUserModal();
      loadAdminUsers();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Update failed', 'error');
    }
  } catch (err) {
    showToast('Failed to update user', 'error');
  }
}

async function toggleUserStatus(userId) {
  try {
    const res = await fetch('/api/admin/users/toggle-status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: userId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAdminUsers();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Status toggle failed', 'error');
    }
  } catch (err) {
    showToast('Failed to toggle status', 'error');
  }
}

async function deleteUser(userId, userName) {
  if (!confirm(`Are you sure you want to permanently delete user account '${userName}' (#${userId})? This will also remove associated vehicle and booking records.`)) {
    return;
  }
  try {
    const res = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAdminUsers();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Delete failed', 'error');
    }
  } catch (err) {
    showToast('Failed to delete user', 'error');
  }
}

async function viewUserVehicles(userId, userName) {
  const modal = document.getElementById('userVehiclesModal');
  const title = document.getElementById('userVehiclesModalTitle');
  const tbody = document.getElementById('userVehiclesModalTbody');
  title.textContent = `Vehicles for ${userName} (#${userId})`;
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:#94a3b8;">Loading vehicle records...</td></tr>';
  modal.style.display = 'flex';

  try {
    const res = await fetch('/api/admin/vehicles');
    const data = await res.json();
    if (data.status === 'success') {
      const userVehicles = (data.vehicles || []).filter(v => v.user_id === userId);
      if (userVehicles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:#94a3b8;">No registered vehicles for this user.</td></tr>';
        return;
      }
      tbody.innerHTML = userVehicles.map(v => `
        <tr>
          <td style="font-family:var(--font-mono); color:#ffffff; font-weight:700;">${escapeHtml(v.license_plate)}</td>
          <td>${escapeHtml(v.vehicle_type)}</td>
          <td>${escapeHtml(v.make_model || '—')}</td>
          <td>${escapeHtml(v.color || 'White')}</td>
          <td>
            <button class="btn-admin btn-admin-danger btn-admin-sm" onclick="adminDeleteVehicle(${v.vehicle_id}, ${userId}, '${escapeHtml(userName)}')">
              <i class="fas fa-trash"></i>
            </button>
          </td>
        </tr>
      `).join('');
    }
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#ef4444;">Failed to fetch vehicles.</td></tr>';
  }
}

async function adminDeleteVehicle(vehicleId, userId, userName) {
  if (!confirm('Remove this vehicle record?')) return;
  try {
    const res = await fetch(`/api/admin/vehicles/${vehicleId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      viewUserVehicles(userId, userName);
    } else {
      showToast(data.message || 'Error removing vehicle', 'error');
    }
  } catch (err) {
    showToast('Failed to delete vehicle', 'error');
  }
}

function closeUserVehiclesModal() {
  document.getElementById('userVehiclesModal').style.display = 'none';
}

/* ==========================================================================
   MODULE: SECURITY GUARD MANAGEMENT
   ========================================================================== */

let allGuards = [];
let allGuardsLots = [];

async function loadAdminGuards() {
  const tbody = document.getElementById('adminGuardsTableBody');
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading security guards...</td></tr>';
  }

  try {
    const res = await fetch('/api/admin/guards');
    const data = await res.json();
    if (data.status === 'success') {
      allGuards = data.guards || [];
      allGuardsLots = data.lots || [];

      // Update KPI counters
      const kpiTotal = document.getElementById('kpiTotalGuards');
      const kpiActive = document.getElementById('kpiActiveGuards');
      const kpiGates = document.getElementById('kpiAssignedGates');

      if (kpiTotal) kpiTotal.textContent = allGuards.length;
      if (kpiActive) kpiActive.textContent = allGuards.filter(g => g.is_active === 1).length;
      if (kpiGates) {
        const uniqueGates = new Set(allGuards.map(g => g.gate).filter(Boolean));
        kpiGates.textContent = uniqueGates.size || allGuards.length;
      }

      // Populate facility filter and modal lot selects
      populateGuardLotDropdowns(allGuardsLots);

      // Render table
      renderGuardsTable(allGuards);
    } else {
      if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#ef4444; padding:30px;">${escapeHtml(data.message || 'Failed to load guards.')}</td></tr>`;
    }
  } catch (err) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#ef4444; padding:30px;">Error communicating with server.</td></tr>';
  }
}

function populateGuardLotDropdowns(lots) {
  const lotFilter = document.getElementById('guardLotFilter');
  const addLotSelect = document.getElementById('addGuardLot');
  const editLotSelect = document.getElementById('editGuardLot');

  if (lotFilter) {
    const currentVal = lotFilter.value;
    lotFilter.innerHTML = '<option value="all">All Facilities</option>' +
      lots.map(l => `<option value="${escapeHtml(l.name)}">${escapeHtml(l.name)}</option>`).join('');
    if (currentVal) lotFilter.value = currentVal;
  }

  const optionsHtml = lots.map(l => `<option value="${l.lot_id}" data-name="${escapeHtml(l.name)}">${escapeHtml(l.name)} (${l.total_slots || 0} slots)</option>`).join('');

  if (addLotSelect) addLotSelect.innerHTML = optionsHtml;
  if (editLotSelect) editLotSelect.innerHTML = optionsHtml;
}

function renderGuardsTable(guards) {
  const tbody = document.getElementById('adminGuardsTableBody');
  if (!tbody) return;

  if (!guards || guards.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#94a3b8; padding:30px;">No security guards found matching criteria.</td></tr>';
    return;
  }

  tbody.innerHTML = guards.map(g => {
    const isActive = (g.is_active === 1 || g.is_active === null || g.is_active === undefined);
    const statusBadge = isActive
      ? '<span class="status-badge active" style="background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3);"><i class="fas fa-check-circle"></i> On Duty</span>'
      : '<span class="status-badge deactivated"><i class="fas fa-ban"></i> Off Duty</span>';

    return `
      <tr>
        <td style="font-family:var(--font-mono); color:#10b981; font-weight:700;">#SG-${g.user_id}</td>
        <td>
          <div style="font-weight:700; color:#ffffff; font-size:14px;">
            <i class="fas fa-user-shield" style="color:#10b981; margin-right:6px;"></i>${escapeHtml(g.name)}
          </div>
          <div style="font-size:11px; color:#94a3b8; margin-top:2px;">
            <i class="far fa-clock"></i> ${escapeHtml(g.shift || 'Day Shift')}
          </div>
        </td>
        <td>
          <div style="color:#e2e8f0; font-size:13px;">${escapeHtml(g.email)}</div>
          <div style="font-size:11px; color:#64748b;">${escapeHtml(g.phone || '—')}</div>
        </td>
        <td>
          <span style="background:rgba(59,130,246,0.15); color:#60a5fa; border:1px solid rgba(96,165,250,0.3); padding:3px 8px; border-radius:6px; font-weight:600; font-size:12px;">
            <i class="fas fa-warehouse"></i> ${escapeHtml(g.assigned_lot || 'Main Facility')}
          </span>
        </td>
        <td>
          <span style="background:rgba(245,158,11,0.15); color:#fbbf24; border:1px solid rgba(251,191,36,0.3); padding:3px 8px; border-radius:6px; font-weight:600; font-size:12px;">
            <i class="fas fa-door-open"></i> ${escapeHtml(g.gate || 'Gate 1')}
          </span>
        </td>
        <td>${statusBadge}</td>
        <td>
          <div style="display:flex; gap:6px; align-items:center;">
            <button class="btn-admin btn-admin-secondary btn-admin-sm" onclick="openEditGuardModal(${g.user_id})" title="Edit Guard Info">
              <i class="fas fa-edit"></i> Edit
            </button>
            <button class="btn-admin ${isActive ? 'btn-admin-danger' : 'btn-admin-success'} btn-admin-sm" onclick="toggleGuardStatus(${g.user_id})" title="${isActive ? 'Set Off Duty' : 'Set On Duty'}">
              <i class="fas ${isActive ? 'fa-user-slash' : 'fa-user-check'}"></i> ${isActive ? 'Deactivate' : 'Activate'}
            </button>
            ${g.email.toLowerCase() !== 'security@smartparking.ai' ? `
              <button class="btn-admin btn-admin-danger btn-admin-sm" onclick="deleteGuard(${g.user_id}, '${escapeHtml(g.name)}')" title="Remove Guard">
                <i class="fas fa-trash"></i>
              </button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function filterGuards() {
  const query = (document.getElementById('guardSearchInput')?.value || '').toLowerCase().trim();
  const lotFilter = document.getElementById('guardLotFilter')?.value || 'all';
  const statusFilter = document.getElementById('guardStatusFilter')?.value || 'all';

  const filtered = allGuards.filter(g => {
    const matchesQuery = !query ||
      (g.name && g.name.toLowerCase().includes(query)) ||
      (g.email && g.email.toLowerCase().includes(query)) ||
      (g.gate && g.gate.toLowerCase().includes(query)) ||
      (g.assigned_lot && g.assigned_lot.toLowerCase().includes(query));

    const matchesLot = lotFilter === 'all' || (g.assigned_lot && g.assigned_lot === lotFilter);
    const isActive = (g.is_active === 1 || g.is_active === null || g.is_active === undefined);
    const matchesStatus = statusFilter === 'all' ||
      (statusFilter === 'active' && isActive) ||
      (statusFilter === 'deactivated' && !isActive);

    return matchesQuery && matchesLot && matchesStatus;
  });

  renderGuardsTable(filtered);
}

function openAddGuardModal() {
  document.getElementById('addGuardForm').reset();
  document.getElementById('addGuardModal').style.display = 'flex';
}

function closeAddGuardModal() {
  document.getElementById('addGuardModal').style.display = 'none';
}

async function submitAddGuard(e) {
  e.preventDefault();
  const name = document.getElementById('addGuardName').value.trim();
  const email = document.getElementById('addGuardEmail').value.trim();
  const phone = document.getElementById('addGuardPhone').value.trim();
  const password = document.getElementById('addGuardPassword').value;
  const lotSelect = document.getElementById('addGuardLot');
  const lot_id = lotSelect ? lotSelect.value : 1;
  const assigned_lot = lotSelect && lotSelect.selectedOptions[0] ? lotSelect.selectedOptions[0].getAttribute('data-name') : 'Institutions';
  const gate = document.getElementById('addGuardGate').value.trim();
  const shift = document.getElementById('addGuardShift').value;

  try {
    const res = await fetch('/api/admin/guards/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name, email, phone, password, lot_id, assigned_lot, gate, shift })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeAddGuardModal();
      loadAdminGuards();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Creation failed', 'error');
    }
  } catch (err) {
    showToast('Failed to create security guard', 'error');
  }
}

function openEditGuardModal(guardId) {
  const guard = allGuards.find(g => g.user_id === guardId);
  if (!guard) return;

  document.getElementById('editGuardId').value = guard.user_id;
  document.getElementById('editGuardName').value = guard.name || '';
  document.getElementById('editGuardEmail').value = guard.email || '';
  document.getElementById('editGuardPhone').value = guard.phone || '';
  document.getElementById('editGuardGate').value = guard.gate || '';
  document.getElementById('editGuardShift').value = guard.shift || 'Day Shift (08:00 - 20:00)';
  document.getElementById('editGuardStatus').value = (guard.is_active === 0 ? '0' : '1');
  document.getElementById('editGuardPassword').value = '';

  const lotSelect = document.getElementById('editGuardLot');
  if (lotSelect && guard.lot_id) {
    lotSelect.value = guard.lot_id;
  }

  document.getElementById('editGuardModal').style.display = 'flex';
}

function closeEditGuardModal() {
  document.getElementById('editGuardModal').style.display = 'none';
}

async function submitEditGuard(e) {
  e.preventDefault();
  const user_id = document.getElementById('editGuardId').value;
  const name = document.getElementById('editGuardName').value.trim();
  const email = document.getElementById('editGuardEmail').value.trim();
  const phone = document.getElementById('editGuardPhone').value.trim();
  const lotSelect = document.getElementById('editGuardLot');
  const lot_id = lotSelect ? lotSelect.value : 1;
  const assigned_lot = lotSelect && lotSelect.selectedOptions[0] ? lotSelect.selectedOptions[0].getAttribute('data-name') : '';
  const gate = document.getElementById('editGuardGate').value.trim();
  const shift = document.getElementById('editGuardShift').value;
  const is_active = document.getElementById('editGuardStatus').value === '1';
  const password = document.getElementById('editGuardPassword').value;

  const payload = { user_id, name, email, phone, lot_id, assigned_lot, gate, shift, is_active };
  if (password) payload.password = password;

  try {
    const res = await fetch('/api/admin/guards/update', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeEditGuardModal();
      loadAdminGuards();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Update failed', 'error');
    }
  } catch (err) {
    showToast('Failed to update guard', 'error');
  }
}

async function toggleGuardStatus(guardId) {
  try {
    const res = await fetch('/api/admin/guards/toggle-status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ user_id: guardId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAdminGuards();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Status toggle failed', 'error');
    }
  } catch (err) {
    showToast('Failed to toggle guard status', 'error');
  }
}

async function deleteGuard(guardId, guardName) {
  if (!confirm(`Are you sure you want to remove Security Guard '${guardName}' (#SG-${guardId})?`)) {
    return;
  }
  try {
    const res = await fetch(`/api/admin/guards/${guardId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAdminGuards();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Delete failed', 'error');
    }
  } catch (err) {
    showToast('Failed to remove guard', 'error');
  }
}

/* ==========================================================================
   MODULE 2: PARKING LOT MANAGEMENT
   ========================================================================== */

async function loadAdminLots() {
  const container = document.getElementById('adminLotsListContainer');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center; padding:40px; color:#94a3b8;"><i class="fas fa-spinner fa-spin fa-2x"></i><p style="margin-top:10px;">Loading parking facilities...</p></div>';

  try {
    const res = await fetch('/api/lots');
    const data = await res.json();
    if (data.status === 'success') {
      allLots = data.lots || [];
      renderLotsCards(allLots);
      populateLotDropdowns(allLots);
    }
  } catch (err) {
    container.innerHTML = '<div style="color:#ef4444; text-align:center; padding:20px;">Failed to load parking lots.</div>';
  }
}

function renderLotsCards(lots) {
  const container = document.getElementById('adminLotsListContainer');
  if (!container) return;
  if (!lots || lots.length === 0) {
    container.innerHTML = '<div style="color:#94a3b8; text-align:center; padding:30px;">No parking lots registered in the system.</div>';
    return;
  }

  container.innerHTML = lots.map(l => {
    const occPct = l.total_slots > 0 ? Math.round(((l.occupied_count || 0) + (l.reserved_count || 0)) / l.total_slots * 100) : 0;
    return `
      <div class="admin-card" style="margin-bottom:18px;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px;">
          <div>
            <div style="display:flex; align-items:center; gap:10px;">
              <h3 style="font-size:18px; font-weight:800; color:#ffffff;">${escapeHtml(l.lot_name)}</h3>
              <span style="font-size:11px; background:rgba(59,130,246,0.2); color:#60a5fa; padding:2px 8px; border-radius:4px; font-weight:700;">LOT #${l.lot_id}</span>
            </div>
            <div style="color:#94a3b8; font-size:13px; margin-top:4px;">
              <i class="fas fa-map-marker-alt" style="color:#ef4444; margin-right:4px;"></i> ${escapeHtml(l.location)} &bull; <strong>${l.total_floors || 2} Floors</strong> &bull; ${escapeHtml(l.operating_hours || '24/7')}
            </div>
          </div>
          <div style="display:flex; gap:8px;">
            <button class="btn-admin btn-admin-secondary btn-admin-sm" onclick="openEditLotModal(${l.lot_id})">
              <i class="fas fa-edit"></i> Edit Lot
            </button>
            <button class="btn-admin btn-admin-danger btn-admin-sm" onclick="deleteLot(${l.lot_id}, '${escapeHtml(l.lot_name)}')">
              <i class="fas fa-trash"></i> Delete
            </button>
          </div>
        </div>

        <!-- Capacity & Occupancy Bar -->
        <div style="margin-top:16px; background:#0f172a; border-radius:var(--admin-radius-sm); padding:16px; border:1px solid #1e293b;">
          <div style="display:flex; justify-content:space-between; font-size:12px; margin-bottom:8px;">
            <span style="color:#94a3b8;">Capacity Utilization: <strong style="color:#ffffff;">${occPct}%</strong></span>
            <span style="color:#94a3b8;">Total Capacity: <strong style="color:#ffffff;">${l.total_slots} Slots</strong></span>
          </div>
          <div style="height:10px; background:#334155; border-radius:6px; overflow:hidden; display:flex;">
            <div style="width:${Math.round((l.available_count || 0) / l.total_slots * 100)}%; background:#10b981;" title="Available"></div>
            <div style="width:${Math.round((l.reserved_count || 0) / l.total_slots * 100)}%; background:#f59e0b;" title="Reserved"></div>
            <div style="width:${Math.round((l.occupied_count || 0) / l.total_slots * 100)}%; background:#ef4444;" title="Occupied"></div>
          </div>
          <div style="display:flex; gap:16px; margin-top:10px; font-size:12px; flex-wrap:wrap;">
            <span style="color:#34d399;"><i class="fas fa-circle" style="font-size:8px;"></i> Available: <strong>${l.available_count || 0}</strong></span>
            <span style="color:#f87171;"><i class="fas fa-circle" style="font-size:8px;"></i> Occupied: <strong>${l.occupied_count || 0}</strong></span>
            <span style="color:#fbbf24;"><i class="fas fa-circle" style="font-size:8px;"></i> Reserved: <strong>${l.reserved_count || 0}</strong></span>
            <span style="color:#94a3b8; margin-left:auto;">Rate: <strong>₹${l.hourly_rate || 40}/hr</strong> &bull; Overstay: <strong>₹${l.overstay_penalty_rate || 100}/hr</strong></span>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function populateLotDropdowns(lots) {
  const selects = ['slotFilterLotSelect', 'addSlotLotSelect', 'aiLotSelect'];
  selects.forEach(selId => {
    const sel = document.getElementById(selId);
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = lots.map(l => `<option value="${l.lot_id}">${escapeHtml(l.lot_name)} (${l.location})</option>`).join('');
    if (currentVal) sel.value = currentVal;
  });
}

function openAddLotModal() {
  document.getElementById('addLotForm').reset();
  document.getElementById('addLotModal').style.display = 'flex';
}

function closeAddLotModal() {
  document.getElementById('addLotModal').style.display = 'none';
}

async function submitAddLot(e) {
  e.preventDefault();
  const payload = {
    lot_name: document.getElementById('addLotName').value.trim(),
    location: document.getElementById('addLotLocation').value.trim(),
    total_floors: parseInt(document.getElementById('addLotFloors').value) || 2,
    total_slots: parseInt(document.getElementById('addLotSlots').value) || 50,
    hourly_rate: parseFloat(document.getElementById('addLotRate').value) || 40.0,
    overstay_penalty_rate: parseFloat(document.getElementById('addLotPenalty').value) || 100.0,
    operating_hours: document.getElementById('addLotHours').value.trim() || '24/7 (Open Daily)'
  };

  try {
    const res = await fetch('/api/admin/lots/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeAddLotModal();
      loadAdminLots();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Failed to add lot', 'error');
    }
  } catch (err) {
    showToast('Error creating parking lot', 'error');
  }
}

function openEditLotModal(lotId) {
  const lot = allLots.find(l => l.lot_id === lotId);
  if (!lot) return;
  document.getElementById('editLotId').value = lot.lot_id;
  document.getElementById('editLotName').value = lot.lot_name;
  document.getElementById('editLotLocation').value = lot.location;
  document.getElementById('editLotFloors').value = lot.total_floors || 2;
  document.getElementById('editLotSlots').value = lot.total_slots || 100;
  document.getElementById('editLotRate').value = lot.hourly_rate || 40.0;
  document.getElementById('editLotPenalty').value = lot.overstay_penalty_rate || 100.0;
  document.getElementById('editLotHours').value = lot.operating_hours || '24/7';
  document.getElementById('editLotModal').style.display = 'flex';
}

function closeEditLotModal() {
  document.getElementById('editLotModal').style.display = 'none';
}

async function submitEditLot(e) {
  e.preventDefault();
  const payload = {
    lot_id: parseInt(document.getElementById('editLotId').value),
    lot_name: document.getElementById('editLotName').value.trim(),
    location: document.getElementById('editLotLocation').value.trim(),
    total_floors: parseInt(document.getElementById('editLotFloors').value),
    total_slots: parseInt(document.getElementById('editLotSlots').value),
    hourly_rate: parseFloat(document.getElementById('editLotRate').value),
    overstay_penalty_rate: parseFloat(document.getElementById('editLotPenalty').value),
    operating_hours: document.getElementById('editLotHours').value.trim()
  };

  try {
    const res = await fetch('/api/admin/lots/update', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeEditLotModal();
      loadAdminLots();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Update failed', 'error');
    }
  } catch (err) {
    showToast('Failed to update lot', 'error');
  }
}

async function deleteLot(lotId, lotName) {
  if (!confirm(`Are you sure you want to delete parking lot '${lotName}' (#${lotId}) and all its associated slots?`)) {
    return;
  }
  try {
    const res = await fetch(`/api/admin/lots/${lotId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAdminLots();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Delete failed', 'error');
    }
  } catch (err) {
    showToast('Failed to delete parking lot', 'error');
  }
}

/* ==========================================================================
   MODULE 3: PARKING SLOT MANAGEMENT & LIVE 2D LAYOUT
   ========================================================================== */

async function loadAdminSlots() {
  const lotSelect = document.getElementById('slotFilterLotSelect');
  const floorSelect = document.getElementById('slotFilterFloorSelect');
  const lotId = lotSelect ? lotSelect.value : '';
  const floor = floorSelect ? floorSelect.value : 'all';

  const grid = document.getElementById('admin2DSlotsGrid');
  if (!grid) return;
  grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Rendering 2D parking slots...</div>';

  try {
    let url = '/api/slots/all';
    if (lotId) url += `?lot_id=${lotId}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.status === 'success') {
      allSlots = data.slots || [];
      render2DSlotsLayout(allSlots, floor);
    }
  } catch (err) {
    grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; color:#ef4444; padding:20px;">Failed to render slots.</div>';
  }
}

function render2DSlotsLayout(slots, floorFilter = 'all') {
  const grid = document.getElementById('admin2DSlotsGrid');
  if (!grid) return;

  const filtered = slots.filter(s => floorFilter === 'all' || s.floor === floorFilter);
  if (filtered.length === 0) {
    grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; color:#94a3b8; padding:30px;">No slots found for this floor/lot.</div>';
    return;
  }

  grid.innerHTML = filtered.map(s => {
    const st = s.status.toLowerCase();
    let statusClass = 'status-available';
    let icon = '🟢';
    if (st === 'overstayed') { statusClass = 'status-overstayed'; icon = '🚨'; }
    else if (st === 'occupied') { statusClass = 'status-occupied'; icon = '🔴'; }
    else if (st === 'reserved') { statusClass = 'status-reserved'; icon = '🟡'; }
    else if (st === 'maintenance' || st === 'disabled') { statusClass = 'status-maintenance'; icon = '🔧'; }

    return `
      <div class="slot-card-2d ${statusClass}" onclick="openEditSlotStatusModal(${s.slot_id})" title="Click to manage slot status">
        <div class="slot-number-title">${escapeHtml(s.slot_number)}</div>
        <div class="slot-type-sub">${escapeHtml(s.slot_type)} &bull; ${escapeHtml(s.floor || 'G')}</div>
        <div class="slot-status-indicator">
          <span>${icon}</span>
          <span style="text-transform:capitalize;">${st}</span>
        </div>
      </div>
    `;
  }).join('');
}

function openAddSlotModal() {
  document.getElementById('addSlotForm').reset();
  document.getElementById('addSlotModal').style.display = 'flex';
}

function closeAddSlotModal() {
  document.getElementById('addSlotModal').style.display = 'none';
}

async function submitAddSlot(e) {
  e.preventDefault();
  const payload = {
    lot_id: parseInt(document.getElementById('addSlotLotSelect').value),
    slot_number: document.getElementById('addSlotNumber').value.trim().toUpperCase(),
    floor: document.getElementById('addSlotFloor').value,
    slot_type: document.getElementById('addSlotType').value,
    distance_to_entry_m: parseInt(document.getElementById('addSlotDistanceEntry').value) || 15,
    distance_to_elevator_m: parseInt(document.getElementById('addSlotDistanceElevator').value) || 20
  };

  try {
    const res = await fetch('/api/admin/slots/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeAddSlotModal();
      loadAdminSlots();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Slot creation failed', 'error');
    }
  } catch (err) {
    showToast('Failed to create slot', 'error');
  }
}

function openEditSlotStatusModal(slotId) {
  const slot = allSlots.find(s => s.slot_id === slotId);
  if (!slot) return;
  document.getElementById('editSlotId').value = slot.slot_id;
  document.getElementById('editSlotNumberDisplay').textContent = slot.slot_number;
  document.getElementById('editSlotTypeSelect').value = slot.slot_type;
  document.getElementById('editSlotStatusSelect').value = slot.status.toLowerCase();
  document.getElementById('editSlotModal').style.display = 'flex';
}

function closeEditSlotModal() {
  document.getElementById('editSlotModal').style.display = 'none';
}

async function submitUpdateSlot(e) {
  e.preventDefault();
  const slotId = parseInt(document.getElementById('editSlotId').value);
  const newType = document.getElementById('editSlotTypeSelect').value;
  const newStatus = document.getElementById('editSlotStatusSelect').value;

  try {
    const res = await fetch('/api/admin/slots/update', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        slot_id: slotId,
        slot_type: newType,
        status: newStatus
      })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeEditSlotModal();
      loadAdminSlots();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Update failed', 'error');
    }
  } catch (err) {
    showToast('Failed to update slot', 'error');
  }
}

async function deleteSlotFromModal() {
  const slotId = parseInt(document.getElementById('editSlotId').value);
  if (!confirm('Are you sure you want to delete this parking slot?')) return;
  try {
    const res = await fetch(`/api/admin/slots/${slotId}?force=1`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      closeEditSlotModal();
      loadAdminSlots();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Delete failed', 'error');
    }
  } catch (err) {
    showToast('Failed to delete slot', 'error');
  }
}

/* ==========================================================================
   MODULE 4: BOOKING MANAGEMENT
   ========================================================================== */

async function loadAdminBookings() {
  const tbody = document.getElementById('adminBookingsTableBody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading master booking records...</td></tr>';

  try {
    const res = await fetch('/api/admin/reservations');
    const data = await res.json();
    if (data.status === 'success') {
      allBookings = data.reservations || [];
      renderBookingsTable(allBookings);
    }
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color:#ef4444;">Failed to load bookings.</td></tr>';
  }
}

function renderBookingsTable(bookings) {
  const tbody = document.getElementById('adminBookingsTableBody');
  if (!tbody) return;
  if (!bookings || bookings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:#94a3b8;">No bookings match the selected filters.</td></tr>';
    return;
  }

  tbody.innerHTML = bookings.map(b => {
    const st = (b.status || 'confirmed').toLowerCase();
    let badgeClass = 'confirmed';
    if (st === 'completed') badgeClass = 'completed';
    else if (st === 'cancelled') badgeClass = 'cancelled';
    else if (st === 'overstayed') badgeClass = 'occupied';

    return `
      <tr>
        <td style="font-family:var(--font-mono); color:#94a3b8;">#${b.reservation_id}</td>
        <td>
          <div style="font-weight:700; color:#ffffff;">${escapeHtml(b.user_name || 'Driver')}</div>
          <div style="font-size:11px; color:#64748b;">${escapeHtml(b.user_email || '')}</div>
        </td>
        <td>
          <strong style="color:#ffffff;">Slot ${escapeHtml(b.slot_number || '-')}</strong>
          <div style="font-size:11px; color:#94a3b8;">Plate: ${escapeHtml(b.vehicle_plate || '')}</div>
        </td>
        <td>
          <div>${escapeHtml(b.date)}</div>
          <div style="font-size:11px; color:#64748b;">${escapeHtml(b.start_time)} – ${escapeHtml(b.end_time)}</div>
        </td>
        <td><span class="status-badge ${badgeClass}">${escapeHtml(b.status)}</span></td>
        <td style="font-weight:700; color:#ffffff;">₹${b.total_amount ? b.total_amount.toFixed(2) : '80.00'}</td>
        <td>
          <div style="display:flex; gap:6px;">
            ${st === 'confirmed' || st === 'checked_in' ? `
              <button class="btn-admin btn-admin-danger btn-admin-sm" onclick="adminForceCheckout(${b.reservation_id})" title="Force Checkout (Vacate Slot)">
                <i class="fas fa-sign-out-alt"></i> Checkout
              </button>
              <button class="btn-admin btn-admin-secondary btn-admin-sm" onclick="adminCancelBooking(${b.reservation_id})" title="Cancel Booking">
                <i class="fas fa-times"></i> Cancel
              </button>
            ` : `
              <span style="font-size:12px; color:#64748b;">Archived</span>
            `}
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function filterBookings(status) {
  const buttons = document.querySelectorAll('.booking-filter-btn');
  buttons.forEach(btn => {
    if (btn.getAttribute('data-status') === status) btn.classList.add('active');
    else btn.classList.remove('active');
  });

  if (status === 'all') {
    renderBookingsTable(allBookings);
  } else {
    const filtered = allBookings.filter(b => (b.status || '').toLowerCase() === status);
    renderBookingsTable(filtered);
  }
}

async function adminForceCheckout(resId) {
  if (!confirm(`Force checkout reservation #${resId} and restore slot to Available immediately?`)) return;
  try {
    const res = await fetch(`/api/admin/reservations/force-checkout/${resId}`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAdminBookings();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Checkout failed', 'error');
    }
  } catch (err) {
    showToast('Failed to checkout booking', 'error');
  }
}

async function adminCancelBooking(resId) {
  if (!confirm(`Cancel reservation #${resId} and release slot?`)) return;
  try {
    const res = await fetch(`/api/admin/reservations/cancel/${resId}`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAdminBookings();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Cancellation failed', 'error');
    }
  } catch (err) {
    showToast('Failed to cancel booking', 'error');
  }
}

/* ==========================================================================
   MODULE 5: AI-BASED PARKING MANAGEMENT
   ========================================================================== */

function formatDisplayDate(isoDateStr) {
  if (!isoDateStr) return '18 Sep 2026';
  const parts = isoDateStr.split('-');
  if (parts.length !== 3) return isoDateStr;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const day = parts[2];
  const monthIdx = parseInt(parts[1], 10) - 1;
  const year = parts[0];
  return `${day} ${months[monthIdx] || parts[1]} ${year}`;
}

function formatDisplayTime(timeStr) {
  if (!timeStr) return '05:00 PM';
  const parts = timeStr.split(':');
  if (parts.length < 2) return timeStr;
  let h = parseInt(parts[0], 10);
  const m = parts[1];
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12;
  h = h ? h : 12;
  return `${h < 10 ? '0' + h : h}:${m} ${ampm}`;
}

function updateAiForecastDate(val) {
  const lbl = document.getElementById('aiForecastDateLabel');
  if (lbl) lbl.textContent = formatDisplayDate(val);
  load24hOccupancyForecast();
}

function updatePredFormDate(val) {
  const disp = document.getElementById('predFormDateDisplay');
  if (disp) disp.value = formatDisplayDate(val);
}

function updatePredFormTime(val) {
  const disp = document.getElementById('predFormTimeDisplay');
  if (disp) disp.value = formatDisplayTime(val);
}

async function loadAdminAIPage() {
  const todayStr = new Date().toISOString().split('T')[0];
  const dateInput = document.getElementById('aiForecastDate');
  if (dateInput && !dateInput.value) {
    dateInput.value = todayStr;
  }
  const dateLabel = document.getElementById('aiForecastDateLabel');
  if (dateLabel && dateInput && dateInput.value) {
    dateLabel.textContent = formatDisplayDate(dateInput.value);
  }

  const predDateInput = document.getElementById('predFormDate');
  if (predDateInput && !predDateInput.value) {
    predDateInput.value = todayStr;
  }
  const predDateDisplay = document.getElementById('predFormDateDisplay');
  if (predDateDisplay && predDateInput && predDateInput.value) {
    predDateDisplay.value = formatDisplayDate(predDateInput.value);
  }

  const predTimeInput = document.getElementById('predFormTime');
  if (predTimeInput && !predTimeInput.value) {
    const now = new Date();
    const currH = String(now.getHours()).padStart(2, '0');
    predTimeInput.value = `${currH}:00`;
  }
  const predTimeDisplay = document.getElementById('predFormTimeDisplay');
  if (predTimeDisplay && predTimeInput && predTimeInput.value) {
    predTimeDisplay.value = formatDisplayTime(predTimeInput.value);
  }

  load24hOccupancyForecast();
}

async function load24hOccupancyForecast() {
  const dateInput = document.getElementById('aiForecastDate');
  const todayStr = new Date().toISOString().split('T')[0];
  const targetDate = (dateInput && dateInput.value) ? dateInput.value : todayStr;

  try {
    const res = await fetch(`/api/admin/ai/forecast?date=${targetDate}`);
    const data = await res.json();
    if (data.status === 'success') {
      // 1. Top 4 KPI Cards
      const occPct = data.current_occupancy !== undefined ? data.current_occupancy : 0;
      const totalSlots = data.total_slots || 210;
      const occSlots = data.occupied_slots !== undefined ? data.occupied_slots : Math.round((occPct / 100) * totalSlots);
      const availSlots = data.available_slots !== undefined ? data.available_slots : Math.max(0, totalSlots - occSlots);

      const occElem = document.getElementById('aiKpiOccupancy');
      if (occElem) occElem.textContent = `${occPct}%`;
      const occSub = document.getElementById('aiKpiOccupancySub');
      if (occSub) occSub.textContent = `${occSlots} / ${totalSlots} slots`;
      const occBar = document.getElementById('aiKpiOccupancyBar');
      if (occBar) occBar.style.width = `${Math.min(100, occPct)}%`;

      const availElem = document.getElementById('aiKpiAvailable');
      if (availElem) availElem.textContent = availSlots;
      const availSub = document.getElementById('aiKpiAvailableSub');
      if (availSub) availSub.textContent = `out of ${totalSlots}`;
      const availBar = document.getElementById('aiKpiAvailableBar');
      if (availBar) availBar.style.width = `${Math.min(100, Math.round((availSlots / totalSlots) * 100))}%`;

      const peakHourElem = document.getElementById('aiKpiPeakHour');
      if (peakHourElem) peakHourElem.textContent = data.predicted_peak_hour || '17:00 - 18:00';
      const peakOccElem = document.getElementById('aiKpiPeakOcc');
      if (peakOccElem) peakOccElem.textContent = `${data.predicted_peak_occupancy || 85}%`;
      const peakBar = document.getElementById('aiKpiPeakBar');
      if (peakBar) peakBar.style.width = `${Math.min(100, data.predicted_peak_occupancy || 85)}%`;

      const nextBusyElem = document.getElementById('aiKpiNextBusy');
      if (nextBusyElem) nextBusyElem.textContent = data.next_busy_period || '16:00 - 20:00';
      const busyBar = document.getElementById('aiKpiBusyBar');
      if (busyBar) busyBar.style.width = '75%';

      // 2. Busy Periods Banner
      const bannerText = document.getElementById('aiBusyPeriodsBannerText');
      if (bannerText) {
        bannerText.textContent = data.busy_periods_banner || 'Today: Peak Demand Alert';
      }

      // 3. Recommended Areas
      const recList = document.getElementById('aiRecommendedLotsList');
      if (recList && Array.isArray(data.recommended_areas) && data.recommended_areas.length > 0) {
        recList.innerHTML = data.recommended_areas.map(item => `
          <div class="ai-rec-item">
            <div class="ai-rec-left">
              <div class="ai-rec-pin" style="background:${item.color}2e; color:${item.color};">
                <i class="fas fa-location-dot"></i>
              </div>
              <span class="ai-rec-name">${escapeHtml(item.floor || item.lot_name || 'Ground Floor')}</span>
            </div>
            <div class="ai-rec-right">
              <span class="ai-rec-avail" style="color:${item.color};">${item.available !== undefined ? item.available : 0} / ${item.total || 0} available</span>
              <i class="fas fa-chevron-right"></i>
            </div>
          </div>
        `).join('');
      }

      // 4. Render 24H Forecast Chart
      renderForecastChart(data.forecast || []);
    } else {
      renderForecastChart([]);
    }
  } catch (e) {
    console.error('Failed to load forecast', e);
    renderForecastChart([]);
  }
}

function renderForecastChart(forecastPoints) {
  const canvas = document.getElementById('aiForecastChartCanvas');
  if (!canvas) return;

  const defaultHours = ['00:00', '02:00', '04:00', '06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00'];
  let valuesMap = {};
  let maxHourFromData = null;
  let maxValFromData = -1;

  if (Array.isArray(forecastPoints) && forecastPoints.length > 0) {
    forecastPoints.forEach(p => {
      const val = Number(p.occupancy_percentage || 0);
      valuesMap[p.hour] = val;
      if (val > maxValFromData) {
        maxValFromData = val;
        maxHourFromData = p.hour;
      }
    });
  }

  // Build chart hours: include default 2-hour slots plus the actual peak hour if distinct
  let hours = [...defaultHours];
  if (maxHourFromData && !hours.includes(maxHourFromData)) {
    hours.push(maxHourFromData);
    hours.sort();
  }

  const values = hours.map(h => {
    if (valuesMap[h] !== undefined) return valuesMap[h];
    return 15;
  });

  // Identify peak point index dynamically
  let peakVal = -1;
  let peakHour = hours[0];
  let peakIndex = 0;
  values.forEach((v, idx) => {
    if (v > peakVal) {
      peakVal = v;
      peakHour = hours[idx];
      peakIndex = idx;
    }
  });

  if (forecastChartInstance) {
    forecastChartInstance.destroy();
  }

  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, 'rgba(56, 189, 248, 0.45)');
  gradient.addColorStop(0.7, 'rgba(56, 189, 248, 0.08)');
  gradient.addColorStop(1, 'rgba(56, 189, 248, 0.0)');

  // Peak callout badge custom plugin dynamically positioned on real peak
  const peakCalloutPlugin = {
    id: 'peakCallout',
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      const meta = chart.getDatasetMeta(0);
      if (peakIndex === -1 || !meta.data[peakIndex]) return;

      const point = meta.data[peakIndex];
      const x = point.x;
      const y = point.y;

      const boxW = 90;
      const boxH = 36;
      const boxX = x - boxW / 2;
      const boxY = Math.max(10, y - boxH - 12);

      ctx.save();
      ctx.fillStyle = 'rgba(11, 20, 37, 0.95)';
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(boxX, boxY, boxW, boxH, 6);
      } else {
        ctx.rect(boxX, boxY, boxW, boxH);
      }
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px "Plus Jakarta Sans", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`Peak: ${peakHour}`, x, boxY + 13);

      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 12px "Plus Jakarta Sans", sans-serif';
      ctx.fillText(`● ${Math.round(peakVal)}%`, x, boxY + 28);
      ctx.restore();
    }
  };

  forecastChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: hours,
      datasets: [{
        label: 'Occupancy (%)',
        data: values,
        borderColor: '#38bdf8',
        borderWidth: 2.5,
        backgroundColor: gradient,
        fill: true,
        tension: 0.4,
        pointBackgroundColor: hours.map((h, i) => i === peakIndex ? '#ffffff' : '#38bdf8'),
        pointBorderColor: hours.map((h, i) => i === peakIndex ? '#0284c7' : '#ffffff'),
        pointBorderWidth: hours.map((h, i) => i === peakIndex ? 3 : 1.5),
        pointRadius: hours.map((h, i) => i === peakIndex ? 6 : 3.5),
        pointHoverRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#ffffff',
          bodyColor: '#38bdf8',
          borderColor: 'rgba(56, 189, 248, 0.3)',
          borderWidth: 1,
          callbacks: {
            label: (ctx) => `Occupancy: ${ctx.parsed.y}%`
          }
        }
      },
      scales: {
        x: {
          title: {
            display: true,
            text: 'Time (Hour)',
            color: '#64748b',
            font: { size: 11, weight: '600' }
          },
          ticks: {
            color: '#64748b',
            font: { size: 11 },
            callback: function(val, index) {
              const lbl = hours[index];
              return index === peakIndex && lbl !== '00:00' && lbl !== '22:00' ? '' : lbl;
            }
          },
          grid: { display: false }
        },
        y: {
          min: 0,
          max: 100,
          title: {
            display: true,
            text: 'Occupancy (%)',
            color: '#64748b',
            font: { size: 11, weight: '600' }
          },
          ticks: {
            color: '#64748b',
            stepSize: 20,
            callback: v => v + '%'
          },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        }
      }
    },
    plugins: [peakCalloutPlugin]
  });
}

async function runInteractivePrediction(e) {
  if (e) {
    if (typeof e.preventDefault === 'function') e.preventDefault();
    if (typeof e.stopPropagation === 'function') e.stopPropagation();
  }
  const todayStr = new Date().toISOString().split('T')[0];
  const dateElem = document.getElementById('predFormDate');
  const dateVal = (dateElem && dateElem.value) ? dateElem.value : todayStr;

  const timeElem = document.getElementById('predFormTime');
  const timeVal = (timeElem && timeElem.value) ? timeElem.value : '17:00';

  const floorElem = document.getElementById('predFormFloor');
  const floorVal = (floorElem && floorElem.value) ? floorElem.value : 'Ground Floor';

  const btn = document.getElementById('btnRunAiModel');
  if (btn) btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';

  try {
    const res = await fetch('/api/ai/predict', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        target_date: dateVal,
        date: dateVal,
        target_time: timeVal,
        time: timeVal,
        floor: floorVal
      })
    });
    const data = await res.json();
    let pct = 50;
    let totalSlots = 210;
    let estOcc = 0;
    let availSlots = 0;

    if (data.status === 'success' && data.prediction) {
      pct = Math.round(data.prediction.predicted_occupancy || data.prediction.predicted_occupancy_percentage || 50);
      totalSlots = data.prediction.total_slots || 210;
      estOcc = data.prediction.estimated_occupancy !== undefined ? data.prediction.estimated_occupancy : Math.round((pct / 100) * totalSlots);
      availSlots = data.prediction.available_slots !== undefined ? data.prediction.available_slots : Math.max(0, totalSlots - estOcc);
    } else {
      estOcc = Math.round((pct / 100) * totalSlots);
      availSlots = Math.max(0, totalSlots - estOcc);
    }

    // Update conic gauge
    const gauge = document.getElementById('aiSimGaugeRing');
    if (gauge) {
      gauge.style.background = `conic-gradient(#14b8a6 0% ${pct}%, rgba(255,255,255,0.08) ${pct}% 100%)`;
    }
    const valElem = document.getElementById('aiSimResultPct');
    if (valElem) valElem.textContent = `${pct}%`;

    const occElem = document.getElementById('aiSimEstimatedOcc');
    if (occElem) occElem.textContent = `${estOcc} / ${totalSlots} slots`;

    const availElem = document.getElementById('aiSimAvailableSlots');
    if (availElem) availElem.textContent = `${availSlots} slots`;

    const areaElem = document.getElementById('aiSimSuggestedArea');
    if (areaElem) areaElem.textContent = floorVal;

    const adviceElem = document.getElementById('aiSimCongestionText');
    if (adviceElem) {
      adviceElem.textContent = (pct >= 80) 
        ? 'High occupancy anticipated - advance reservation suggested' 
        : (pct <= 40 ? 'Abundant slots available with optimal flow' : 'Best availability and lower congestion');
    }

    showToast(`AI Availability: ${pct}% Occupancy predicted for ${floorVal}`, 'success');
  } catch (err) {
    console.error('Failed to run AI prediction', err);
    showToast('Failed to compute prediction', 'error');
  } finally {
    if (btn) btn.innerHTML = '<i class="fas fa-play"></i> Run AI Model';
  }
}

async function loadAIClustersOverview() {
  try {
    const res = await fetch('/api/ai/kmeans');
    const data = await res.json();
    const container = document.getElementById('aiClustersContainer');
    if (!container || !data.clusters) return;

    container.innerHTML = data.clusters.map(c => `
      <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:14px; flex:1; min-width:200px;">
        <div style="font-size:11px; text-transform:uppercase; font-weight:700; color:#38bdf8;">Cluster ${c.cluster_id}: ${c.cluster_name}</div>
        <div style="font-size:18px; font-weight:800; color:#ffffff; margin:4px 0;">~${c.mean_occupancy_pct}% Occupancy</div>
        <div style="font-size:11px; color:#94a3b8;">Mean Hour: ${c.mean_hour}:00 &bull; Profile: ${c.demand_profile}</div>
      </div>
    `).join('');
  } catch (e) {
    console.warn(e);
  }
}

/* ==========================================================================
   MODULE 6: SLOT EXCHANGE MANAGEMENT
   ========================================================================== */

async function loadAdminExchanges() {
  const container = document.getElementById('adminExchangeRequestsTbody');
  if (!container) return;
  container.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:30px; color:#94a3b8;"><i class="fas fa-spinner fa-spin"></i> Loading exchange listings and requests...</td></tr>';

  try {
    const res = await fetch('/api/admin/exchange/overview');
    const data = await res.json();
    if (data.status === 'success') {
      renderExchangeRequests(data.requests || []);
      renderExchangeHistory(data.history || []);
    }
  } catch (err) {
    container.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#ef4444;">Failed to load slot exchanges.</td></tr>';
  }
}

function renderExchangeRequests(requests) {
  const tbody = document.getElementById('adminExchangeRequestsTbody');
  if (!tbody) return;
  if (!requests || requests.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:24px; color:#94a3b8;">No slot exchange requests currently pending.</td></tr>';
    return;
  }

  tbody.innerHTML = requests.map(r => `
    <tr>
      <td style="font-family:var(--font-mono); color:#94a3b8;">#${r.request_id}</td>
      <td>
        <strong style="color:#ffffff;">${escapeHtml(r.requester_name)}</strong>
        <div style="font-size:11px; color:#38bdf8;">Offers: Slot ${escapeHtml(r.requester_slot_number || '')}</div>
      </td>
      <td style="text-align:center; font-size:16px; color:#94a3b8;">
        <i class="fas fa-exchange-alt"></i>
      </td>
      <td>
        <strong style="color:#ffffff;">${escapeHtml(r.owner_name)}</strong>
        <div style="font-size:11px; color:#fbbf24;">Target: Slot ${escapeHtml(r.owner_slot_number || '')}</div>
      </td>
      <td>
        <span class="status-badge ${r.status === 'accepted' ? 'completed' : (r.status === 'rejected' ? 'cancelled' : 'reserved')}">
          ${escapeHtml(r.status)}
        </span>
      </td>
      <td>
        ${r.status === 'pending' ? `
          <div style="display:flex; gap:6px;">
            <button class="btn-admin btn-admin-success btn-admin-sm" onclick="moderateExchange(${r.request_id}, 'approve')">
              <i class="fas fa-check"></i> Approve
            </button>
            <button class="btn-admin btn-admin-danger btn-admin-sm" onclick="moderateExchange(${r.request_id}, 'reject')">
              <i class="fas fa-times"></i> Reject
            </button>
          </div>
        ` : `
          <span style="font-size:12px; color:#64748b;">Processed</span>
        `}
      </td>
    </tr>
  `).join('');
}

function renderExchangeHistory(history) {
  const tbody = document.getElementById('adminExchangeHistoryTbody');
  if (!tbody) return;
  if (!history || history.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:#94a3b8;">No historical completed exchanges yet.</td></tr>';
    return;
  }

  tbody.innerHTML = history.map(h => `
    <tr>
      <td style="font-family:var(--font-mono); color:#94a3b8;">#${h.history_id}</td>
      <td>${escapeHtml(h.user1_name)} &harr; ${escapeHtml(h.user2_name)}</td>
      <td>Slot ${escapeHtml(h.user1_old_slot)} switched to Slot ${escapeHtml(h.user1_new_slot)}</td>
      <td><span class="status-badge completed">${escapeHtml(h.status)}</span></td>
      <td style="color:#94a3b8; font-size:11.5px;">${escapeHtml(h.exchanged_at || '')}</td>
    </tr>
  `).join('');
}

async function moderateExchange(requestId, action) {
  try {
    const res = await fetch('/api/admin/exchange/moderate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ request_id: requestId, action: action })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadAdminExchanges();
      loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Action failed', 'error');
    }
  } catch (err) {
    showToast('Failed to moderate exchange', 'error');
  }
}

/* ==========================================================================
   MODULE 7: REPORTS & ANALYTICS
   ========================================================================== */

async function loadAdminReports() {
  try {
    const res = await fetch('/api/reports/summary');
    const data = await res.json();
    if (data.status === 'success') {
      // 1. Top 4 KPI Cards
      const bookingsElem = document.getElementById('repKpiTotalBookings');
      if (bookingsElem) bookingsElem.textContent = data.total_bookings !== undefined ? Number(data.total_bookings).toLocaleString() : '0';

      const occElem = document.getElementById('repKpiOccupancy');
      if (occElem) occElem.textContent = `${data.current_occupancy !== undefined ? data.current_occupancy : 0}%`;

      const revElem = document.getElementById('repKpiRevenue');
      if (revElem) {
        const rev = data.total_revenue !== undefined ? data.total_revenue : 0;
        revElem.textContent = `₹ ${Number(rev).toLocaleString()}`;
      }

      const overstayElem = document.getElementById('repKpiOverstayCount');
      if (overstayElem) overstayElem.textContent = data.overstay_incidents !== undefined ? data.overstay_incidents : 0;

      // 2. Mini metrics in Overstay Summary
      if (data.overstay_summary) {
        const miniCnt = document.getElementById('repMiniOverstayCnt');
        if (miniCnt) miniCnt.textContent = data.overstay_summary.incidents !== undefined ? data.overstay_summary.incidents : 0;
        const miniPen = document.getElementById('repMiniTotalPenalty');
        if (miniPen) miniPen.textContent = `₹ ${Number(data.overstay_summary.total_penalty || 0).toLocaleString()}`;
        const miniDur = document.getElementById('repMiniAvgDuration');
        if (miniDur) miniDur.textContent = data.overstay_summary.avg_duration || '0m';
      }

      // Update date range banner if labels exist
      const dateRangeDisp = document.getElementById('repDateRangeDisplay');
      if (dateRangeDisp && data.trend && Array.isArray(data.trend.labels) && data.trend.labels.length > 0) {
        const lbls = data.trend.labels;
        dateRangeDisp.innerHTML = `${lbls[0]} &nbsp;–&nbsp; ${lbls[lbls.length - 1]}`;
      }

      // 3. Render 3 Charts
      renderReportsTrendChart(data.trend);
      renderReportsFloorChart(data.floor_occupancy);
      renderReportsStatusDonut(data.booking_breakdown);

      // 4. Populate Recent Overstay Records Table
      const overstayTbody = document.getElementById('repOverstayRecordsTbody');
      if (overstayTbody && Array.isArray(data.recent_overstays)) {
        if (data.recent_overstays.length === 0) {
          overstayTbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#94a3b8; padding:18px;">No active overstay violations.</td></tr>';
        } else {
          overstayTbody.innerHTML = data.recent_overstays.map(o => `
            <tr>
              <td style="font-weight:600; color:#ffffff;">${escapeHtml(o.vehicle_number)}</td>
              <td>${escapeHtml(o.slot_number)}</td>
              <td>${escapeHtml(o.floor)}</td>
              <td>${escapeHtml(o.duration)}</td>
              <td>₹ ${Number(o.penalty).toLocaleString()}</td>
              <td><span class="rep-status-badge ${o.status === 'Paid' ? 'rep-status-paid' : 'rep-status-pending'}">${escapeHtml(o.status)}</span></td>
            </tr>
          `).join('');
        }
      }

      // 5. Populate Recent Activity Table
      const actTbody = document.getElementById('repRecentActivityTbody');
      if (actTbody && Array.isArray(data.recent_activities)) {
        if (data.recent_activities.length === 0) {
          actTbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#94a3b8; padding:18px;">No recent activities logged.</td></tr>';
        } else {
          actTbody.innerHTML = data.recent_activities.map(a => `
            <tr>
              <td style="color:#94a3b8;">${escapeHtml(a.date_time)}</td>
              <td style="font-weight:600; color:#ffffff;">${escapeHtml(a.vehicle_number)}</td>
              <td>${escapeHtml(a.action)}</td>
              <td><span class="rep-pill-outline-green">${escapeHtml(a.status || 'Active')}</span></td>
            </tr>
          `).join('');
        }
      }
    } else {
      renderReportsTrendChart();
      renderReportsFloorChart();
      renderReportsStatusDonut();
    }
  } catch (e) {
    console.error('Failed to load reports', e);
    renderReportsTrendChart();
    renderReportsFloorChart();
    renderReportsStatusDonut();
  }
}

function renderReportsTrendChart(trendData) {
  const canvas = document.getElementById('repTrendChartCanvas');
  if (!canvas) return;

  const labels = (trendData && trendData.labels && trendData.labels.length) ? trendData.labels : ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6', 'Day 7'];
  const bookings = (trendData && trendData.bookings) ? trendData.bookings : [0, 0, 0, 0, 0, 0, 0];
  const revenue = (trendData && trendData.revenue) ? trendData.revenue : [0, 0, 0, 0, 0, 0, 0];

  const maxBookings = Math.max(10, Math.ceil(Math.max(...bookings, 1) * 1.3));
  const maxRevenue = Math.max(500, Math.ceil(Math.max(...revenue, 100) * 1.3));

  if (reportsTrendChartInstance) {
    reportsTrendChartInstance.destroy();
  }

  const ctx = canvas.getContext('2d');
  const revGradient = ctx.createLinearGradient(0, 0, 0, 240);
  revGradient.addColorStop(0, 'rgba(168, 85, 247, 0.25)');
  revGradient.addColorStop(1, 'rgba(168, 85, 247, 0.0)');

  reportsTrendChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Bookings',
          data: bookings,
          yAxisID: 'y',
          borderColor: '#38bdf8',
          backgroundColor: 'transparent',
          borderWidth: 2.2,
          pointBackgroundColor: '#38bdf8',
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          pointRadius: 3.5,
          pointHoverRadius: 5.5,
          tension: 0.4
        },
        {
          label: 'Revenue (₹)',
          data: revenue,
          yAxisID: 'y1',
          borderColor: '#a855f7',
          backgroundColor: revGradient,
          fill: true,
          borderWidth: 2.2,
          pointBackgroundColor: '#a855f7',
          pointBorderColor: '#ffffff',
          pointBorderWidth: 1.5,
          pointRadius: 3.5,
          pointHoverRadius: 5.5,
          tension: 0.4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#ffffff',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1
        }
      },
      scales: {
        x: {
          ticks: { color: '#64748b', font: { size: 10 } },
          grid: { display: false }
        },
        y: {
          type: 'linear',
          display: true,
          position: 'left',
          min: 0,
          max: maxBookings,
          ticks: { color: '#64748b', font: { size: 10 } },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        y1: {
          type: 'linear',
          display: true,
          position: 'right',
          min: 0,
          max: maxRevenue,
          ticks: {
            color: '#64748b',
            font: { size: 10 },
            callback: v => (v === 0 ? '0' : (v >= 1000 ? (v / 1000).toFixed(1) + 'K' : v))
          },
          grid: { drawOnChartArea: false }
        }
      }
    }
  });
}

function renderReportsFloorChart(floorData) {
  const canvas = document.getElementById('repFloorChartCanvas');
  if (!canvas) return;

  const floors = (floorData && floorData.length) ? floorData.map(f => f.floor) : ['Ground Floor', 'Upper Floor'];
  const values = (floorData && floorData.length) ? floorData.map(f => f.pct) : [0, 0];
  const barColors = (floorData && floorData.length) ? floorData.map(f => f.color || '#38bdf8') : ['#06b6d4', '#3b82f6'];

  if (reportsFloorChartInstance) {
    reportsFloorChartInstance.destroy();
  }

  const ctx = canvas.getContext('2d');

  // Custom plugin to draw values on top of bars
  const barTopLabelsPlugin = {
    id: 'barTopLabels',
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((dataset, datasetIndex) => {
        const meta = chart.getDatasetMeta(datasetIndex);
        meta.data.forEach((bar, index) => {
          const val = dataset.data[index];
          ctx.save();
          ctx.fillStyle = '#ffffff';
          ctx.font = 'bold 11px "Plus Jakarta Sans", sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(`${val}%`, bar.x, bar.y - 6);
          ctx.restore();
        });
      });
    }
  };

  reportsFloorChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: floors,
      datasets: [{
        label: 'Occupancy %',
        data: values,
        backgroundColor: barColors,
        borderRadius: 4,
        barPercentage: 0.5
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 18 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#ffffff',
          callbacks: {
            label: (ctx) => `Occupancy: ${ctx.parsed.y}%`
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#64748b', font: { size: 11, weight: '600' } },
          grid: { display: false }
        },
        y: {
          min: 0,
          max: 100,
          ticks: {
            color: '#64748b',
            stepSize: 25,
            callback: v => v + '%',
            font: { size: 10 }
          },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        }
      }
    },
    plugins: [barTopLabelsPlugin]
  });
}

function renderReportsStatusDonut(breakdownData) {
  const canvas = document.getElementById('repStatusDonutCanvas');
  if (!canvas) return;

  const total = (breakdownData && breakdownData.total) ? breakdownData.total : 0;
  const donutTotalElem = document.getElementById('repDonutTotal');
  if (donutTotalElem) {
    donutTotalElem.textContent = Number(total).toLocaleString();
  }

  const completed = (breakdownData && breakdownData.completed) ? (breakdownData.completed.count || 0) : 0;
  const confirmed = (breakdownData && breakdownData.confirmed) ? (breakdownData.confirmed.count || 0) : 0;
  const cancelled = (breakdownData && breakdownData.cancelled) ? (breakdownData.cancelled.count || 0) : 0;
  const overstay = (breakdownData && breakdownData.overstay) ? (breakdownData.overstay.count || 0) : 0;

  const labels = ['Completed', 'Confirmed', 'Cancelled', 'Overstay'];
  let dataValues = [completed, confirmed, cancelled, overstay];
  const bgColors = ['#10b981', '#38bdf8', '#f97316', '#ef4444'];

  // Update Legend HTML
  const legendElem = document.getElementById('repDonutLegend');
  if (legendElem && breakdownData) {
    const compPct = breakdownData.completed ? breakdownData.completed.pct : 0;
    const confPct = breakdownData.confirmed ? breakdownData.confirmed.pct : 0;
    const cancPct = breakdownData.cancelled ? breakdownData.cancelled.pct : 0;
    const overPct = breakdownData.overstay ? breakdownData.overstay.pct : 0;

    legendElem.innerHTML = `
      <div class="rep-donut-leg-row">
        <span class="rep-leg-dot" style="background:#10b981;"></span>
        <span class="rep-leg-name">Completed</span>
        <span class="rep-leg-stat">${compPct}% (${completed})</span>
      </div>
      <div class="rep-donut-leg-row">
        <span class="rep-leg-dot" style="background:#38bdf8;"></span>
        <span class="rep-leg-name">Confirmed</span>
        <span class="rep-leg-stat">${confPct}% (${confirmed})</span>
      </div>
      <div class="rep-donut-leg-row">
        <span class="rep-leg-dot" style="background:#f97316;"></span>
        <span class="rep-leg-name">Cancelled</span>
        <span class="rep-leg-stat">${cancPct}% (${cancelled})</span>
      </div>
      <div class="rep-donut-leg-row">
        <span class="rep-leg-dot" style="background:#ef4444;"></span>
        <span class="rep-leg-name">Overstay</span>
        <span class="rep-leg-stat">${overPct}% (${overstay})</span>
      </div>
    `;
  }

  if (reportsDonutChartInstance) {
    reportsDonutChartInstance.destroy();
  }

  const sumValues = dataValues.reduce((a, b) => a + b, 0);
  const displayValues = sumValues > 0 ? dataValues : [1];
  const displayColors = sumValues > 0 ? bgColors : ['#334155'];
  const displayLabels = sumValues > 0 ? labels : ['No Data'];

  const ctx = canvas.getContext('2d');
  reportsDonutChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: displayLabels,
      datasets: [{
        data: displayValues,
        backgroundColor: displayColors,
        borderColor: '#0d1527',
        borderWidth: 2,
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '72%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#ffffff',
          bodyColor: '#cbd5e1',
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.parsed} bookings`
          }
        }
      }
    }
  });
}

function downloadReportsCSV() {
  window.location.href = '/api/reports/export-csv';
}

/* ==========================================================================
   UTILITY & TOAST NOTIFICATIONS
   ========================================================================== */

function showToast(message, type = 'success') {
  let toast = document.getElementById('adminToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'adminToast';
    toast.className = 'admin-toast';
    document.body.appendChild(toast);
  }

  toast.className = `admin-toast ${type}`;
  toast.innerHTML = `
    <i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}" style="color:${type === 'success' ? '#34d399' : '#f87171'};"></i>
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
   MODULE: REAL-TIME OVERSTAY MANAGEMENT & RADAR (SIMPLIFIED & ROBUST)
   ========================================================================== */

let rawAdminOverstayRecords = [];
let adminOverstayPollTimer = null;

function startAdminOverstayPolling() {
  stopAdminOverstayPolling();
  adminOverstayPollTimer = setInterval(() => {
    loadAdminOverstays(true); // background silent refresh
  }, 5000);
}

function stopAdminOverstayPolling() {
  if (adminOverstayPollTimer) {
    clearInterval(adminOverstayPollTimer);
    adminOverstayPollTimer = null;
  }
}

async function loadAdminOverstays(silent = false) {
  const tbody = document.getElementById('adminOverstayTableBody');
  if (!tbody) return;

  const refreshIcon = document.getElementById('overstayRefreshIcon');
  if (refreshIcon && !silent) {
    refreshIcon.classList.add('fa-spin');
  }

  if (!silent && tbody.children.length === 0) {
    tbody.innerHTML = '<tr><td colspan="15" style="text-align:center; padding:35px; color:#94a3b8;"><i class="fas fa-spinner fa-spin" style="margin-right:8px;"></i> Loading live overstay radar...</td></tr>';
  }

  try {
    const res = await fetch('/api/overstays');
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();

    if (data.status === 'success') {
      // 1. Update 4 Summary KPI Cards (Requirement 3)
      if (data.summary) {
        const s = data.summary;
        const elAct = document.getElementById('kpiActiveOverstays');
        const elPending = document.getElementById('kpiPendingPenalties');
        const elPendingSub = document.getElementById('kpiPendingPenaltiesSub');
        const elRes = document.getElementById('kpiResolvedOverstays');
        const elTotAmt = document.getElementById('kpiTotalPenaltyAmount');
        const elTotSub = document.getElementById('kpiTotalPenaltyBreakdown');

        const activeCount = s.active_overstays ?? 0;
        const pendingCount = s.pending_penalties ?? 0;
        const pendingAmt = Number(s.pending_amount || 0);
        const resolvedCount = s.resolved_overstays ?? 0;
        const paidAmt = Number(s.paid_amount || 0);
        const totalAmt = Number(s.total_penalty_amount ?? s.total_penalties ?? (pendingAmt + paidAmt));

        if (elAct) elAct.textContent = activeCount;
        if (elPending) elPending.textContent = pendingCount;
        if (elPendingSub) {
          elPendingSub.textContent = pendingAmt > 0
            ? `₹${pendingAmt.toFixed(0)} unpaid penalties`
            : 'All penalties cleared';
        }
        if (elRes) elRes.textContent = resolvedCount;
        if (elTotAmt) elTotAmt.textContent = `₹${totalAmt.toFixed(0)}`;
        if (elTotSub) {
          elTotSub.textContent = `Pending: ₹${pendingAmt.toFixed(0)} • Paid: ₹${paidAmt.toFixed(0)}`;
        }
      }

      // 2. Cache records
      rawAdminOverstayRecords = data.overstays || [];

      // 3. Update Parking Lot Dropdown Options dynamically
      updateOverstayLotDropdown(rawAdminOverstayRecords);

      // 4. Apply current filters & search (Requirement 7)
      applyOverstayFilters();
    }
  } catch (err) {
    console.error('Error loading overstays', err);
    if (!silent) {
      tbody.innerHTML = '<tr><td colspan="15" style="text-align:center; padding:25px; color:#ef4444;"><i class="fas fa-triangle-exclamation" style="margin-right:8px;"></i> Failed to load overstay records. Please refresh again.</td></tr>';
    }
  } finally {
    if (refreshIcon && !silent) {
      setTimeout(() => refreshIcon.classList.remove('fa-spin'), 400);
    }
  }
}

function updateOverstayLotDropdown(records) {
  const lotSelect = document.getElementById('overstayLotSelect');
  if (!lotSelect) return;

  const currentVal = lotSelect.value;
  const lots = new Set();
  records.forEach(r => {
    const lot = (r.parking_lot || r.lot_name || '').trim();
    if (lot && lot !== '—') lots.add(lot);
  });

  const sortedLots = Array.from(lots).sort();
  let html = '<option value="all">All Parking Lots</option>';
  sortedLots.forEach(lot => {
    html += `<option value="${escapeHtml(lot)}">${escapeHtml(lot)}</option>`;
  });
  lotSelect.innerHTML = html;

  if (currentVal && (currentVal === 'all' || lots.has(currentVal))) {
    lotSelect.value = currentVal;
  }
}

function handleOverstaySearchFilter() {
  applyOverstayFilters();
}

function resetOverstayFilters() {
  const searchInput = document.getElementById('overstaySearchInput');
  const statusSelect = document.getElementById('overstayStatusSelect');
  const paymentSelect = document.getElementById('overstayPaymentSelect');
  const lotSelect = document.getElementById('overstayLotSelect');

  if (searchInput) searchInput.value = '';
  if (statusSelect) statusSelect.value = 'all';
  if (paymentSelect) paymentSelect.value = 'all';
  if (lotSelect) lotSelect.value = 'all';

  applyOverstayFilters();
}

function applyOverstayFilters() {
  const searchInput = document.getElementById('overstaySearchInput');
  const statusSelect = document.getElementById('overstayStatusSelect');
  const paymentSelect = document.getElementById('overstayPaymentSelect');
  const lotSelect = document.getElementById('overstayLotSelect');

  const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
  const statusFilter = statusSelect ? statusSelect.value : 'all';
  const paymentFilter = paymentSelect ? paymentSelect.value : 'all';
  const lotFilter = lotSelect ? lotSelect.value : 'all';

  let filtered = rawAdminOverstayRecords.filter(r => {
    // 1. Search Query: Booking ID, User Name, Vehicle Number, Slot Number
    if (query) {
      const bId = String(r.booking_id || '').toLowerCase();
      const uName = String(r.user_name || r.driver_name || '').toLowerCase();
      const vNum = String(r.vehicle_number || r.vehicle_plate || '').toLowerCase();
      const sNum = String(r.slot_number || '').toLowerCase();
      const lot = String(r.parking_lot || r.lot_name || '').toLowerCase();

      const matches = bId.includes(query) ||
                      uName.includes(query) ||
                      vNum.includes(query) ||
                      sNum.includes(query) ||
                      lot.includes(query);
      if (!matches) return false;
    }

    // 2. Overstay Status Filter
    const st = String(r.status || '').toLowerCase();
    const ovSt = String(r.overstay_status || '').toLowerCase();
    const isAct = (st === 'active' || ovSt === 'overstayed' || ovSt === 'penalty applicable');
    const isGrace = (st === 'grace' || r.is_grace || ovSt === 'grace period');
    const isRes = (st === 'resolved' || ovSt === 'resolved' || ovSt === 'completed' || st === 'exited');

    if (statusFilter !== 'all') {
      if (statusFilter === 'active' && !isAct) return false;
      if (statusFilter === 'grace' && !isGrace) return false;
      if (statusFilter === 'resolved' && !isRes) return false;
    }

    // 3. Payment Status Filter
    if (paymentFilter !== 'all') {
      const paySt = String(r.payment_status || '').toLowerCase();
      if (paymentFilter === 'pending') {
        const isPending = (paySt === 'pending' || isGrace);
        if (!isPending) return false;
      }
      if (paymentFilter === 'paid') {
        if (paySt !== 'paid') return false;
      }
    }

    // 4. Parking Lot Filter
    if (lotFilter !== 'all') {
      const lot = (r.parking_lot || r.lot_name || '').trim();
      if (lot !== lotFilter) return false;
    }

    return true;
  });

  // Render Table
  renderAdminOverstayTable(filtered);

  // Update Counters
  const countBadge = document.getElementById('overstayRecordsCount');
  if (countBadge) {
    countBadge.textContent = `${filtered.length} Record${filtered.length === 1 ? '' : 's'}`;
  }

  const footerText = document.getElementById('overstayFooterText');
  if (footerText) {
    footerText.textContent = `Showing ${filtered.length} of ${rawAdminOverstayRecords.length} records`;
  }
}

function renderAdminOverstayTable(records) {
  const tbody = document.getElementById('adminOverstayTableBody');
  if (!tbody) return;

  if (!records || records.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="15" style="text-align:center; padding:32px 20px; color:#94a3b8;">
          <i class="fas fa-filter" style="color:#38bdf8; font-size:22px; display:block; margin-bottom:8px;"></i>
          <span style="font-size:14px; font-weight:600; color:#e2e8f0;">No overstay records match your filters</span>
          <p style="font-size:12px; color:#64748b; margin:4px 0 12px;">Try clearing search keywords or resetting filter dropdowns.</p>
          <button type="button" class="btn-admin btn-admin-secondary" onclick="resetOverstayFilters()" style="padding:6px 14px; font-size:12px; cursor:pointer; background:rgba(56,189,248,0.12); border:1px solid #38bdf8; color:#38bdf8; border-radius:6px; font-weight:600;">
            <i class="fas fa-undo"></i> Reset All Filters
          </button>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = records.map((r, idx) => {
    const isAct = (r.status === 'active');
    const isGrace = (r.status === 'grace' || r.is_grace);
    const isRes = (r.status === 'resolved' || (!isAct && !isGrace));

    const rawPay = (r.payment_status || 'Pending').trim().toLowerCase();
    const isPaid = (rawPay === 'paid');
    const penaltyNum = Number(r.penalty_amount ?? r.current_penalty ?? 0);

    // Vehicle Type Display
    let vtypeDisplay = '🚗 Car';
    if (r.vehicle_type === 'Bike') vtypeDisplay = '🏍️ Bike';
    else if (r.vehicle_type === 'Other vehicles' || r.vehicle_type === 'Other') vtypeDisplay = '🚐 Other';

    // Status Badge (Requirement 6: Red = Active/Unpaid, Amber = Grace, Green = Resolved/Paid)
    let overstayBadge = '';
    if (isAct) {
      overstayBadge = `<span class="ov-badge ov-badge-red"><i class="fas fa-triangle-exclamation"></i> Overstayed</span>`;
    } else if (isGrace) {
      overstayBadge = `<span class="ov-badge ov-badge-amber"><i class="fas fa-clock"></i> Grace Period</span>`;
    } else {
      overstayBadge = `<span class="ov-badge ov-badge-green"><i class="fas fa-circle-check"></i> Resolved</span>`;
    }

    // Payment Badge
    let paymentBadge = '';
    if (isGrace && penaltyNum === 0) {
      paymentBadge = `<span style="color:#64748b;">—</span>`;
    } else if (isPaid) {
      paymentBadge = `<span class="ov-badge ov-badge-green"><i class="fas fa-check"></i> Paid</span>`;
    } else {
      paymentBadge = `<span class="ov-badge ov-badge-red"><i class="fas fa-circle-exclamation"></i> Pending</span>`;
    }

    // Actual Exit / Current Status Column
    let exitDisplay = '';
    if (isAct) {
      exitDisplay = `<span class="ov-badge ov-badge-red" style="font-size:11px; padding:2px 8px;"><i class="fas fa-car-side"></i> Parked (Active)</span>`;
    } else if (isGrace) {
      exitDisplay = `<span class="ov-badge ov-badge-amber" style="font-size:11px; padding:2px 8px;"><i class="fas fa-hourglass-half"></i> In Grace</span>`;
    } else {
      exitDisplay = `<span style="color:#cbd5e1; font-family:var(--font-mono, monospace); font-weight:600;">${escapeHtml(r.actual_exit_display || r.current_or_exit || '—')}</span>`;
    }

    // Overstay Duration Display
    let durDisplay = '';
    if (isGrace) {
      durDisplay = `<span style="color:#fbbf24; font-weight:600; font-size:12px;">0m</span>`;
    } else {
      const durText = r.overstay_duration_formatted || r.overstay_duration || (r.overstay_duration_minutes ? r.overstay_duration_minutes + 'm' : '—');
      durDisplay = `<span style="font-family:var(--font-mono, monospace); font-weight:800; color:${isAct ? '#f87171' : '#cbd5e1'};">${escapeHtml(durText)}</span>`;
    }

    // Penalty Display
    let penaltyDisplay = '';
    if (isGrace && penaltyNum === 0) {
      penaltyDisplay = `<span style="color:#64748b; font-weight:600;">₹0</span>`;
    } else {
      penaltyDisplay = `<span style="font-family:var(--font-mono, monospace); font-weight:800; color:${isAct ? '#f87171' : (isPaid ? '#34d399' : '#fbbf24')};">₹${penaltyNum.toFixed(0)}</span>`;
    }

    // Action Buttons
    const actionId = r.overstay_id || r.reservation_id;
    let actionButtons = '';

    if (isAct) {
      actionButtons = `
        <div style="display:flex; gap:6px; justify-content:center; flex-wrap:wrap;">
          <button class="btn-admin btn-admin-danger btn-admin-sm" onclick="adminRecordOverstayExit('${actionId}')" title="Record vehicle exit and restore slot to Available">
            <i class="fas fa-arrow-right-from-bracket"></i> Record Exit
          </button>
          ${!isPaid && penaltyNum > 0 ? `
            <button class="btn-admin btn-admin-secondary btn-admin-sm" onclick="adminMarkOverstayPaid('${actionId}')" title="Mark Penalty as Paid" style="color:#34d399; border-color:rgba(52,211,153,0.4);">
              <i class="fas fa-check"></i> Mark Paid
            </button>
          ` : ''}
        </div>
      `;
    } else if (isGrace) {
      actionButtons = `
        <div style="display:flex; gap:6px; justify-content:center; flex-wrap:wrap;">
          <button class="btn-admin btn-admin-secondary btn-admin-sm" onclick="adminRecordOverstayExit('${actionId}')" title="Vehicle departs within grace period">
            <i class="fas fa-arrow-right-from-bracket"></i> Record Exit
          </button>
        </div>
      `;
    } else {
      // Resolved
      if (!isPaid && penaltyNum > 0) {
        actionButtons = `
          <div style="display:flex; gap:6px; justify-content:center; flex-wrap:wrap;">
            <button class="btn-admin btn-admin-secondary btn-admin-sm" onclick="adminMarkOverstayPaid('${actionId}')" title="Mark Penalty as Paid" style="color:#34d399; border-color:rgba(52,211,153,0.4);">
              <i class="fas fa-check"></i> Mark Paid
            </button>
          </div>
        `;
      } else {
        actionButtons = `<span style="font-size:11.5px; color:#34d399; font-weight:700; display:inline-flex; align-items:center; gap:4px;"><i class="fas fa-check-circle"></i> Settled</span>`;
      }
    }

    // Row styling
    let rowClass = '';
    if (isAct) rowClass = 'overstay-row-active';
    else if (isGrace) rowClass = 'overstay-row-grace';

    return `
      <tr class="${rowClass}">
        <td style="color:#64748b; font-size:11.5px; font-weight:600;">${idx + 1}</td>
        <td>
          <span style="font-family:var(--font-mono, monospace); font-weight:700; color:#38bdf8;">
            ${escapeHtml(r.booking_id || '—')}
          </span>
        </td>
        <td>
          <div style="font-weight:700; color:#ffffff;">${escapeHtml(r.user_name || '—')}</div>
          ${r.user_phone ? `<div style="font-size:11px; color:#64748b;">${escapeHtml(r.user_phone)}</div>` : ''}
        </td>
        <td>
          <strong style="font-family:var(--font-mono, monospace); color:#f8fafc; letter-spacing:0.04em;">${escapeHtml(r.vehicle_number || r.vehicle_plate || '—')}</strong>
        </td>
        <td>
          <span class="ov-vtype-badge">
            ${vtypeDisplay}
          </span>
        </td>
        <td>
          <span style="color:#cbd5e1; font-weight:600;">${escapeHtml(r.parking_lot || r.lot_name || '—')}</span>
        </td>
        <td>
          <span class="ov-slot-badge">
            ${escapeHtml(r.slot_number || '—')}
          </span>
        </td>
        <td style="font-size:12px; color:#cbd5e1; font-family:var(--font-mono, monospace);">
          ${escapeHtml(r.booked_end_time || r.booked_end_display || '—')}
        </td>
        <td style="font-size:12px; color:#fbbf24; font-weight:600; font-family:var(--font-mono, monospace);">
          ${escapeHtml(r.grace_period_end || r.grace_end_display || '—')}
        </td>
        <td>
          ${exitDisplay}
        </td>
        <td>
          ${durDisplay}
        </td>
        <td>
          ${penaltyDisplay}
        </td>
        <td>
          ${paymentBadge}
        </td>
        <td>
          ${overstayBadge}
        </td>
        <td style="text-align:center;">
          ${actionButtons}
        </td>
      </tr>
    `;
  }).join('');
}

async function adminRecordOverstayExit(recordId) {
  if (!confirm(`Record vehicle exit for booking #${recordId}?\n\nThis will record the actual exit timestamp, vacate the parking slot, and mark the overstay as Resolved.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/overstays/${recordId}/exit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution_type: 'exited' })
    });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(data.message || 'Vehicle exit recorded. Slot restored to Available.', 'success');
      loadAdminOverstays();
      if (typeof loadAdminSlots === 'function') loadAdminSlots();
      if (typeof loadAdminDashboardKPIs === 'function') loadAdminDashboardKPIs();
    } else {
      showToast(data.message || 'Failed to record vehicle exit.', 'danger');
    }
  } catch (err) {
    showToast('Network error processing vehicle exit.', 'danger');
  }
}

async function adminMarkOverstayPaid(recordId) {
  try {
    const res = await fetch(`/api/overstays/${recordId}/mark-paid`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(data.message || 'Overstay penalty marked as Paid.', 'success');
      loadAdminOverstays();
    } else {
      showToast(data.message || 'Failed to mark payment status.', 'danger');
    }
  } catch (err) {
    showToast('Network error updating payment status.', 'danger');
  }
}

