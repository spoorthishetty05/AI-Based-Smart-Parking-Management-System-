/**
 * 2D Interactive Parking Map Engine
 * Renders physical bays, car silhouettes, slot states and click interactions
 */

let allCurrentSlots = [];

async function renderParkingMap(floor = 'Ground Floor', zone = 'All', search = '') {
  const mapContainer = document.getElementById('parkingMapContent');
  if (!mapContainer) return;

  try {
    const res = await fetch(`/api/slots?floor=${encodeURIComponent(floor)}&zone=${encodeURIComponent(zone)}&search=${encodeURIComponent(search)}`);
    const data = await res.json();
    allCurrentSlots = data.slots || [];

    if (floor === 'Ground Floor') {
      renderGroundFloorLayout(allCurrentSlots, mapContainer);
    } else {
      renderUpperFloorLayout(allCurrentSlots, mapContainer);
    }
  } catch (err) {
    console.error("Error loading parking map:", err);
  }
}

function renderGroundFloorLayout(slots, container) {
  const slotMap = {};
  slots.forEach(s => slotMap[s.slot_number] = s);

  const hasRowSlots = slots.some(s => s.slot_number && /^[A-D]\d+/.test(s.slot_number));
  if (hasRowSlots) {
    // Physical arrangement for Row A, B, C, D (e.g. City Parking A1-A4, B1-B4, C1-C4)
    const rows = ['A', 'B', 'C', 'D'];
    let gridLayoutHtml = '';
    
    rows.forEach(rLetter => {
      const rowSlots = slots.filter(s => s.slot_number.startsWith(rLetter));
      if (rowSlots.length > 0) {
        rowSlots.sort((a, b) => parseInt(a.slot_number.slice(1)) - parseInt(b.slot_number.slice(1)));
        gridLayoutHtml += `
          <div style="margin-bottom:12px;">
            <div style="font-size:11px; font-weight:800; color:#64748b; margin-bottom:6px; letter-spacing:0.5px;">ROW ${rLetter}</div>
            <div class="slots-row-grid" style="grid-template-columns: repeat(auto-fill, minmax(70px, 1fr)); gap: 8px;">
              ${rowSlots.map(s => createSlotCellHtml(s)).join('')}
            </div>
          </div>
        `;
        if (rLetter === 'B') {
          gridLayoutHtml += `
            <div class="drive-lane" style="margin: 12px 0;">
              <span>CENTRAL DRIVE LANE</span>
            </div>
          `;
        }
      }
    });

    container.innerHTML = `
      <div class="map-floor-header">
        <i class="fas fa-map-marked-alt"></i> Parking Slot Layout — Physical Arrangement (${slots.length} Slots)
      </div>
      <div class="parking-lot-canvas" style="padding: 18px;">
        ${gridLayoutHtml}
      </div>
      <!-- Status Legend -->
      <div class="map-status-legend">
        <div class="legend-item"><span class="legend-dot available"></span> Available</div>
        <div class="legend-item"><span class="legend-dot occupied"></span> Occupied</div>
        <div class="legend-item"><span class="legend-dot reserved"></span> Reserved</div>
        <div class="legend-item"><span class="legend-dot overstayed"></span> Overstayed</div>
        <div class="legend-item"><span class="legend-dot disabled"></span> Disabled</div>
        <div class="legend-item" style="border-left:1px solid #cbd5e1; padding-left:10px;"><i class="fas fa-car" style="color:#0284c7;"></i> Car</div>
        <div class="legend-item"><i class="fas fa-motorcycle" style="color:#16a34a;"></i> Bike/Scooter</div>
      </div>
    `;
    return;
  }

  // S-Bay: S1 - S11
  let sBayHtml = '<div class="slots-row-grid grid-11">';
  for (let i = 1; i <= 11; i++) {
    const sNum = `S${i}`;
    const slot = slotMap[sNum] || { slot_number: sNum, status: 'available', slot_id: null };
    sBayHtml += createSlotCellHtml(slot);
  }
  sBayHtml += '</div>';

  // R-Bay Upper: R22 - R32
  let rUpperHtml = '<div class="slots-row-grid grid-11">';
  for (let i = 22; i <= 32; i++) {
    const rNum = `R${i}`;
    const slot = slotMap[rNum] || { slot_number: rNum, status: 'available', slot_id: null };
    rUpperHtml += createSlotCellHtml(slot);
  }
  rUpperHtml += '</div>';

  // R-Bay Lower: R1 - R11
  let rLowerHtml = '<div class="slots-row-grid grid-11">';
  for (let i = 1; i <= 11; i++) {
    const rNum = `R${i}`;
    const slot = slotMap[rNum] || { slot_number: rNum, status: 'available', slot_id: null };
    rLowerHtml += createSlotCellHtml(slot);
  }
  rLowerHtml += '</div>';

  container.innerHTML = `
    <div class="map-floor-header">
      <i class="fas fa-map-marked-alt"></i> Ground Floor — Long Term Parking
    </div>
    <div class="parking-lot-canvas">
      <!-- Top S-Bay -->
      ${sBayHtml}

      <!-- Drive Lane -->
      <div class="drive-lane">
        <span>DRIVE LANE</span>
      </div>

      <!-- Entry Indicator -->
      <div class="entry-indicator">
        <i class="fas fa-chevron-up"></i>
        <i class="fas fa-chevron-up"></i>
        <span>ENTRY</span>
      </div>

      <!-- Bottom Double Row Bay -->
      <div class="double-row-bay">
        ${rUpperHtml}
        ${rLowerHtml}
      </div>
    </div>

    <!-- Status Legend -->
    <div class="map-status-legend">
      <div class="legend-item"><span class="legend-dot available"></span> Available</div>
      <div class="legend-item"><span class="legend-dot occupied"></span> Occupied</div>
      <div class="legend-item"><span class="legend-dot reserved"></span> Reserved</div>
      <div class="legend-item"><span class="legend-dot overstayed"></span> Overstayed</div>
      <div class="legend-item"><span class="legend-dot disabled"></span> Disabled</div>
      <div class="legend-item" style="border-left:1px solid #cbd5e1; padding-left:10px;"><i class="fas fa-car" style="color:#0284c7;"></i> Car</div>
      <div class="legend-item"><i class="fas fa-motorcycle" style="color:#16a34a;"></i> Bike/Scooter</div>
    </div>
  `;
}

function renderUpperFloorLayout(slots, container) {
  let slotsHtml = '<div class="slots-row-grid" style="grid-template-columns: repeat(auto-fill, minmax(68px, 1fr)); gap: 10px;">';
  slots.forEach(slot => {
    slotsHtml += createSlotCellHtml(slot);
  });
  slotsHtml += '</div>';

  container.innerHTML = `
    <div class="map-floor-header">
      <i class="fas fa-layer-group"></i> Upper Floor — Short Term & EV Charging Hub (${slots.length} Slots)
    </div>
    <div class="parking-lot-canvas" style="padding: 18px;">
      ${slotsHtml}
    </div>
    <div class="map-status-legend">
      <div class="legend-item"><span class="legend-dot available"></span> Available</div>
      <div class="legend-item"><span class="legend-dot occupied"></span> Occupied</div>
      <div class="legend-item"><span class="legend-dot reserved"></span> Reserved</div>
      <div class="legend-item"><span class="legend-dot overstayed"></span> Overstayed</div>
      <div class="legend-item"><span class="legend-dot disabled"></span> Disabled</div>
      <div class="legend-item" style="border-left:1px solid #cbd5e1; padding-left:10px;"><i class="fas fa-car" style="color:#0284c7;"></i> Car</div>
      <div class="legend-item"><i class="fas fa-motorcycle" style="color:#16a34a;"></i> Bike/Scooter</div>
    </div>
  `;
}

function createSlotCellHtml(slot) {
  const status = (slot.status || 'available').toLowerCase();
  const hasVehicle = ['occupied', 'overstayed', 'reserved'].includes(status);
  const slotType = slot.slot_type || 'Regular';

  const vType = (slot.vehicle_type || '').toLowerCase();
  const sType = slotType.toLowerCase();
  const isBike = vType.includes('bike') || vType.includes('scooter') || vType.includes('motorcycle') || vType.includes('two-wheeler') ||
                 sType.includes('bike') || sType.includes('scooter') || sType.includes('two-wheeler') ||
                 (slot.slot_number && /^B\d+/i.test(slot.slot_number) && !vType.includes('car'));

  let typeBadgeHtml = '';
  const stLower = slotType.toLowerCase();
  if (stLower === 'vip') {
    typeBadgeHtml = '<span class="slot-mini-type vip" style="font-size:9px; font-weight:800; color:#d97706; background:#fef3c7; padding:1px 4px; border-radius:4px; margin-bottom:2px;">⭐ VIP</span>';
  } else if (['accessible', 'disabled'].includes(stLower)) {
    typeBadgeHtml = '<span class="slot-mini-type acc" style="font-size:9px; font-weight:800; color:#ec4899; background:#eff6ff; padding:1px 4px; border-radius:4px; margin-bottom:2px;">♿ ACC</span>';
  } else if (stLower === 'ev') {
    typeBadgeHtml = '<span class="slot-mini-type ev" style="font-size:9px; font-weight:800; color:#db2777; background:#ecfdf5; padding:1px 4px; border-radius:4px; margin-bottom:2px;">⚡ EV</span>';
  } else if (stLower.includes('bike') || stLower.includes('scooter') || stLower.includes('two-wheeler') || isBike) {
    typeBadgeHtml = '<span class="slot-mini-type bike" style="font-size:9px; font-weight:800; color:#16a34a; background:#f0fdf4; padding:1px 4px; border-radius:4px; margin-bottom:2px;">🏍️ BIKE</span>';
  } else {
    typeBadgeHtml = '<span class="slot-mini-type reg" style="font-size:9px; font-weight:700; color:#64748b; background:#f1f5f9; padding:1px 4px; border-radius:4px; margin-bottom:2px;">REG</span>';
  }

  let vehicleImgHtml = '';
  if (hasVehicle) {
    const imgSrc = isBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';
    const altText = isBike ? 'Bike / Scooter' : 'Car';
    const wrapClass = isBike ? 'slot-vehicle-wrap slot-bike-wrap' : 'slot-vehicle-wrap slot-car-wrap';
    const imgClass = isBike ? 'slot-vehicle-img slot-bike-img' : 'slot-vehicle-img slot-car-img';
    const titleText = slot.current_plate ? `${slot.current_plate} (${altText})` : `Occupied ${altText}`;
    vehicleImgHtml = `
      <div class="${wrapClass}" title="${titleText}">
        <img src="${imgSrc}" alt="${altText}" class="${imgClass}" />
      </div>
    `;
  }

  return `
    <div class="parking-slot-cell ${status} ${isBike ? 'is-bike-slot' : 'is-car-slot'}" 
         onclick="openSlotDetailModal('${slot.slot_number}')" 
         id="slot-cell-${slot.slot_number}"
         title="Slot ${slot.slot_number} • ${isBike ? 'Bike / Scooter' : slotType} • ${status.toUpperCase()}">
      <span class="slot-label">${slot.slot_number}</span>
      ${typeBadgeHtml}
      ${vehicleImgHtml}
    </div>
  `;
}

function openSlotDetailModal(slotNumber) {
  const slot = allCurrentSlots.find(s => s.slot_number === slotNumber);
  if (!slot) return;

  const modal = document.getElementById('slotDetailModal');
  const body = document.getElementById('slotModalBody');
  const title = document.getElementById('slotModalTitle');

  title.innerText = `Parking Slot ${slot.slot_number}`;

  const status = (slot.status || 'available').toLowerCase();
  const vType = (slot.vehicle_type || '').toLowerCase();
  const sType = (slot.slot_type || '').toLowerCase();
  const isBike = vType.includes('bike') || vType.includes('scooter') || vType.includes('motorcycle') || vType.includes('two-wheeler') ||
                 sType.includes('bike') || sType.includes('scooter') || sType.includes('two-wheeler') ||
                 (slot.slot_number && /^B\d+/i.test(slot.slot_number) && !vType.includes('car'));

  const statusBadge = {
    'available': '<span class="activity-badge vacated" style="font-size:12px; padding:4px 10px;">Available</span>',
    'occupied': '<span class="activity-badge booked" style="font-size:12px; padding:4px 10px;">Occupied</span>',
    'reserved': '<span class="activity-badge reserved" style="font-size:12px; padding:4px 10px;">Reserved</span>',
    'overstayed': '<span class="activity-badge overstay" style="font-size:12px; padding:4px 10px;">⚠️ OVERSTAYED</span>',
    'disabled': '<span class="activity-badge info" style="font-size:12px; padding:4px 10px;">Maintenance</span>'
  }[status] || status;

  let detailsHtml = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
      <div>
        <div style="font-size:12px; color:#64748b;">Floor & Zone</div>
        <div style="font-weight:700; font-size:14px;">${slot.floor} • ${slot.zone}</div>
      </div>
      <div>${statusBadge}</div>
    </div>

    <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; margin-bottom:16px;">
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; font-size:13px;">
        <div><span style="color:#64748b;">Vehicle Category:</span> <b>${isBike ? '🏍️ Bike / Scooter' : '🚗 Car'}</b></div>
        <div><span style="color:#64748b;">Slot Type:</span> <b>${slot.slot_type || 'Standard'}</b></div>
        <div><span style="color:#64748b;">Rate:</span> <b>₹40 / hr</b></div>
        <div><span style="color:#64748b;">Distance to Gate:</span> <b>${slot.distance_to_entry_m || 20}m</b></div>
        <div><span style="color:#64748b;">Distance to Lift:</span> <b>${slot.distance_to_elevator_m || 25}m</b></div>
      </div>
    </div>
  `;

  if (status === 'overstayed') {
    detailsHtml += `
      <div style="background:#fef2f2; border:1px solid #fecaca; border-radius:12px; padding:14px; margin-bottom:16px;">
        <h4 style="color:#ef4444; font-size:13px; font-weight:800; margin-bottom:6px;"><i class="fas fa-exclamation-triangle"></i> Overstay Violation Alert</h4>
        <p style="font-size:12px; color:#991b1b; margin-bottom:8px;">${isBike ? '🏍️ Bike/Scooter' : '🚗 Vehicle'} <b>${slot.current_plate || 'KA01AB1234'}</b> exceeded booking duration.</p>
        <div style="display:flex; justify-content:space-between; font-size:13px; font-weight:700;">
          <span>Extra Time: <b style="color:#b91c1c;">${slot.extra_duration_minutes || 30} mins</b></span>
          <span>Accrued Penalty: <b style="color:#b91c1c;">₹${slot.penalty_amount || 100.00}</b></span>
        </div>
      </div>
      <button class="btn-danger" style="width:100%;" onclick="settleOverstayDirectly(${slot.overstay_id})">
        <i class="fas fa-receipt"></i> Settle Penalty & Free Slot
      </button>
    `;
  } else if (status === 'occupied') {
    detailsHtml += `
      <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:12px; padding:14px; margin-bottom:16px;">
        <div style="font-size:12px; color:#1e40af; margin-bottom:4px;">Current Vehicle (${isBike ? '🏍️ Bike / Scooter' : '🚗 Car'})</div>
        <div style="font-size:16px; font-weight:800; color:#1e3a8a;">${slot.current_plate || 'Active Vehicle'}</div>
        <div style="font-size:12px; color:#ec4899; margin-top:4px;">Occupant: ${slot.user_name || 'Driver'}</div>
      </div>
      <button class="btn-secondary" style="width:100%;" onclick="vacateSlotDirectly(${slot.slot_id})">
        <i class="fas fa-sign-out-alt"></i> Simulate Vehicle Departure
      </button>
    `;
  } else if (status === 'reserved') {
    detailsHtml += `
      <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:12px; padding:14px; margin-bottom:16px;">
        <div style="font-size:12px; color:#92400e; margin-bottom:4px;">Reservation Confirmed (${isBike ? '🏍️ Bike / Scooter' : '🚗 Car'})</div>
        <div style="font-size:15px; font-weight:800; color:#78350f;">${slot.current_plate || 'Reserved Vehicle'}</div>
        <div style="font-size:12px; color:#b45309; margin-top:4px;">Booked for: ${slot.start_time || '09:30'} - ${slot.end_time || '12:30'}</div>
      </div>
      <button class="btn-primary" style="width:100%;" onclick="checkInSlotDirectly(${slot.slot_id})">
        <i class="fas fa-check-circle"></i> Check In Vehicle Now
      </button>
    `;
  } else if (status === 'available') {
    detailsHtml += `
      <p style="font-size:13px; color:#64748b; margin-bottom:16px;">This slot is currently empty and available for immediate booking or reservation.</p>
      <button class="btn-primary" style="width:100%; margin-bottom:8px;" onclick="openReservationForSlot(${slot.slot_id}, '${slot.slot_number}')">
        <i class="fas fa-calendar-check"></i> Book / Reserve This Slot
      </button>
    `;
  }

  body.innerHTML = detailsHtml;
  modal.classList.add('active');
}

function closeSlotDetailModal() {
  const modal = document.getElementById('slotDetailModal');
  if (modal) modal.classList.remove('active');
}
