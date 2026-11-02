/**
 * Guided 5-Step Booking Wizard Controller
 * Workflow:
 * Step 1: Select Facility Category (Institutions, Mall, Public Places, City Parking)
 * Step 2: Select Vehicle Number (User's registered vehicles only + Add Vehicle option)
 * Step 3: Select Specific Parking Place (3 configurable locations per category with live MongoDB counts)
 * Step 4: Date, Time, Duration & Available Slot (Real-time 2D Slot Matrix & tariff calculation)
 * Step 5: Review & Confirm Booking (Summary with all booking parameters, atomic MongoDB reservation)
 * Plus Quick Booking Mode Support
 */

(function () {
  // Global booking wizard state
  window.guidedBookingState = {
    categoryId: 'institutions',
    categoryName: 'Institutions',
    placeId: 'inst_univ',
    placeName: 'University Campus',
    placeAddress: 'Campus Block A, Central University Road, Bangalore',
    lotId: 1,
    hourlyRate: 30.0,
    vehiclePlate: '',
    vehicleType: 'Car',
    bookingDate: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`,
    startTime: `${String(new Date().getHours()).padStart(2, '0')}:${String(new Date().getMinutes()).padStart(2, '0')}`,
    durationHours: 1.0,
    durationLabel: '1 Hour',
    selectedSlot: null,
    confirmedBooking: null,
    currentStep: 1
  };

  const state = window.guidedBookingState;
  let allLoadedWizardSlots = [];

  // Helper: Format slot number like R1 -> R01, A1 -> A01 (matching layout design)
  function displaySlotNumber(num) {
    if (!num) return '';
    const s = String(num).trim();
    if (/^[A-Za-z]\d$/.test(s)) {
      return s[0].toUpperCase() + '0' + s.slice(1);
    }
    return s;
  }
  window.displaySlotNumber = displaySlotNumber;

  // Real-Time Date & Time Utilities for preventing past bookings
  function getLocalDateStr(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  window.getLocalDateStr = getLocalDateStr;

  function getLocalTimeStr(d = new Date()) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  window.getLocalTimeStr = getLocalTimeStr;

  function getNextRoundedTimeStr(minutesToAdd = 15) {
    const d = new Date();
    d.setMinutes(d.getMinutes() + minutesToAdd);
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  window.getNextRoundedTimeStr = getNextRoundedTimeStr;

  function normalizeDateStr(dateStr) {
    if (!dateStr) return '';
    const s = String(dateStr).trim();
    const dmy = s.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
    if (dmy) {
      const pad = (n) => String(n).padStart(2, '0');
      return `${dmy[3]}-${pad(dmy[2])}-${pad(dmy[1])}`;
    }
    return s;
  }
  window.normalizeDateStr = normalizeDateStr;

  function calculateEndTimeStr(startTimeStr, durationHours) {
    try {
      const parts = (startTimeStr || '12:00').split(':');
      let h = parseInt(parts[0], 10);
      let m = parseInt(parts[1] || '0', 10);
      const totalMinutes = Math.round(durationHours * 60);
      m += totalMinutes;
      h = (h + Math.floor(m / 60)) % 24;
      m = m % 60;
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    } catch (e) {
      return startTimeStr;
    }
  }

  function validateBookingDateTime(dateStr, timeStr, graceMinutes = 0) {
    const todayStr = getLocalDateStr();
    const cleanDate = normalizeDateStr(dateStr);
    const nowTimeStr = getLocalTimeStr();

    if (!cleanDate || cleanDate < todayStr) {
      return { valid: false, message: 'Please select the current time or a future time. (Please select a current or future date and time.)' };
    }
    if (cleanDate === todayStr) {
      const t = (timeStr || '00:00').slice(0, 5);
      if (t < nowTimeStr) {
        return { valid: false, message: 'Please select the current time or a future time. (Please select a current or future date and time.)' };
      }
    }
    return { valid: true };
  }
  window.validateBookingDateTime = validateBookingDateTime;

  function syncDateTimeRestrictions(showToastOnAutoFix = false) {
    const dateInp = document.getElementById('wizardBookingDate');
    const timeInp = document.getElementById('wizardStartTime');
    if (!dateInp) return;

    const todayStr = getLocalDateStr();
    const nowTimeStr = getLocalTimeStr();

    // 1. Enforce min attribute on date picker (Disable past dates)
    dateInp.min = todayStr;

    // Normalize date format if present
    if (dateInp.value) {
      const norm = normalizeDateStr(dateInp.value);
      if (norm !== dateInp.value) dateInp.value = norm;
    }

    // If date is before today, clamp to today
    if (dateInp.value && dateInp.value < todayStr) {
      dateInp.value = todayStr;
      if (showToastOnAutoFix) {
        showWizardToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'error');
      }
    }

    // 2. Prevent past times if today is selected
    if (dateInp.value === todayStr) {
      if (timeInp) {
        timeInp.min = nowTimeStr;
        if (!timeInp.value || timeInp.value < nowTimeStr) {
          timeInp.value = nowTimeStr;
          if (showToastOnAutoFix) {
            showWizardToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'error');
          }
        }
      }
    } else {
      if (timeInp) {
        timeInp.removeAttribute('min');
      }
    }

    if (dateInp) state.bookingDate = normalizeDateStr(dateInp.value);
    if (timeInp) state.startTime = timeInp.value;
  }
  window.syncDateTimeRestrictions = syncDateTimeRestrictions;

  // Initialize wizard on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    initGuidedWizardDefaults();
  });

  function initGuidedWizardDefaults() {
    // 1. Initialize Category
    const firstCategoryCard = document.querySelector('.facility-card-pick.selected') || 
                              document.querySelector('.category-card-pick.selected') || 
                              document.querySelector('.facility-card-pick') || 
                              document.querySelector('.category-card-pick');
    if (firstCategoryCard) {
      const cname = firstCategoryCard.getAttribute('data-lot-name') || firstCategoryCard.getAttribute('data-category-name') || 'Institutions';
      const cid = firstCategoryCard.getAttribute('data-category-id') || cname.toLowerCase().replace(/\s+/g, '_');
      const lid = parseInt(firstCategoryCard.getAttribute('data-lot-id') || '1');
      const rate = parseFloat(firstCategoryCard.getAttribute('data-rate') || '30.0');
      state.categoryId = cid;
      state.categoryName = cname;
      state.lotId = lid;
      state.hourlyRate = rate;
      firstCategoryCard.classList.add('selected');
      const selCatEl = document.getElementById('wizardStep1SelectedCategoryName') || document.getElementById('wizardStep1SelectedName');
      if (selCatEl) selCatEl.textContent = cname;
      const catBadge = document.getElementById('wizardStep3CategoryBadge');
      if (catBadge) catBadge.textContent = cname;
    }

    const durSelect = document.getElementById('wizardDurationSelect');
    if (durSelect) {
      const val = parseFloat(durSelect.value || '1');
      state.durationHours = val;
      state.durationLabel = `${val} Hour${val > 1 ? 's' : ''}`;
    }

    // 2. Initialize Places for selected category
    userWizardFilterPlacesByCategory();

    // 3. Initialize Vehicle (Current user's registered vehicles)
    const firstVehicleCard = document.querySelector('.vehicle-card-pick');
    if (firstVehicleCard) {
      const plate = firstVehicleCard.getAttribute('data-plate') || '';
      const vtype = firstVehicleCard.getAttribute('data-type') || 'Car';
      state.vehiclePlate = plate;
      state.vehicleType = vtype;
      firstVehicleCard.classList.add('selected');
      const selPlateEl = document.getElementById('wizardStep2SelectedPlate');
      if (selPlateEl) selPlateEl.textContent = plate;
      const btnStep2 = document.getElementById('btnWizardStep2Next');
      if (btnStep2) btnStep2.disabled = false;
    } else {
      const btnStep2 = document.getElementById('btnWizardStep2Next');
      if (btnStep2) btnStep2.disabled = true;
      const alertEl = document.getElementById('noVehiclesAlert');
      if (alertEl) alertEl.style.display = 'block';
    }

    // 4. Initialize Date & Time pickers
    const startInp = document.getElementById('wizardBookingDate');
    const timeInp = document.getElementById('wizardStartTime');
    const todayStr = getLocalDateStr();
    if (startInp) {
      startInp.min = todayStr;
      if (!startInp.value || startInp.value < todayStr) {
        startInp.value = todayStr;
      }
      state.bookingDate = startInp.value;
    }
    if (timeInp) {
      const nowTimeStr = getLocalTimeStr();
      if (!timeInp.value || (startInp && startInp.value === todayStr && timeInp.value < nowTimeStr)) {
        timeInp.value = nowTimeStr;
      }
      state.startTime = timeInp.value;
    }

    syncDateTimeRestrictions(false);

    // Bind event listeners for date/time validation
    if (startInp && !startInp.dataset.boundPastValidation) {
      startInp.dataset.boundPastValidation = 'true';
      startInp.addEventListener('change', () => {
        syncDateTimeRestrictions(true);
        userWizardOnScheduleChange();
      });
      startInp.addEventListener('input', () => {
        syncDateTimeRestrictions(false);
      });
    }

    if (timeInp && !timeInp.dataset.boundPastValidation) {
      timeInp.dataset.boundPastValidation = 'true';
      timeInp.addEventListener('input', () => {
        state.startTime = timeInp.value;
        userWizardUpdateTariff();
      });
      timeInp.addEventListener('focus', () => {
        syncDateTimeRestrictions(false);
      });
      timeInp.addEventListener('change', () => {
        const todayStr = getLocalDateStr();
        const cleanD = normalizeDateStr(startInp ? startInp.value : state.bookingDate);
        const curNow = getLocalTimeStr();
        if (cleanD === todayStr) {
          if (timeInp.value && timeInp.value < curNow) {
            showWizardToast('Please select the current time or a future time. (Please select a current or future date and time.)', 'error');
            timeInp.value = curNow;
          }
        }
        userWizardOnScheduleChange();
      });
    }

    if (!window._wizardIntervalBound) {
      window._wizardIntervalBound = true;
      setInterval(() => {
        syncDateTimeRestrictions(false);
      }, 15000);
    }

    const activePill = document.querySelector('#wizardDurationPills .duration-pill.active');
    if (activePill) {
      state.durationHours = parseFloat(activePill.getAttribute('data-hours') || '1');
      const titleEl = activePill.querySelector('.duration-pill-title');
      state.durationLabel = titleEl ? titleEl.textContent.trim() : `${state.durationHours} Hour${state.durationHours > 1 ? 's' : ''}`;
    }

    userWizardUpdateTariff();
  }

  // Booking Mode Switcher: 5-Step Guided Wizard vs Quick Booking
  window.switchBookingMode = function (mode) {
    const wizardView = document.getElementById('bookingWizardView');
    const quickView = document.getElementById('bookingQuickView');
    const btnWizard = document.getElementById('modeBtnWizard');
    const btnQuick = document.getElementById('modeBtnQuick');

    if (mode === 'quick') {
      if (wizardView) wizardView.style.display = 'none';
      if (quickView) quickView.style.display = 'block';
      if (btnWizard) {
        btnWizard.className = 'btn-user btn-user-secondary booking-mode-pill';
        btnWizard.style.boxShadow = 'none';
      }
      if (btnQuick) {
        btnQuick.className = 'btn-user btn-user-primary booking-mode-pill';
        btnQuick.style.boxShadow = '0 3px 10px rgba(37,99,235,0.25)';
      }
      if (typeof window.loadAvailableSlotsForBooking === 'function') {
        window.loadAvailableSlotsForBooking();
      } else if (typeof window.loadAvailableSlotsForQuickBooking === 'function') {
        window.loadAvailableSlotsForQuickBooking();
      }
    } else {
      if (wizardView) wizardView.style.display = 'block';
      if (quickView) quickView.style.display = 'none';
      if (btnWizard) {
        btnWizard.className = 'btn-user btn-user-primary booking-mode-pill';
        btnWizard.style.boxShadow = '0 3px 10px rgba(37,99,235,0.25)';
      }
      if (btnQuick) {
        btnQuick.className = 'btn-user btn-user-secondary booking-mode-pill';
        btnQuick.style.boxShadow = 'none';
      }
    }
  };

  // ============================================================
  // STEP 1: SELECT FACILITY CATEGORY
  // ============================================================
  window.userWizardSelectCategory = function (el, categoryId, categoryName, lotId, rate) {
    const prevCategory = state.categoryName;
    state.categoryId = categoryId || (categoryName ? categoryName.toLowerCase().replace(/\s+/g, '_') : 'institutions');
    state.categoryName = categoryName;
    state.lotId = parseInt(lotId || 1);
    if (rate) state.hourlyRate = parseFloat(rate);

    document.querySelectorAll('.category-card-pick, .facility-card-pick').forEach(c => c.classList.remove('selected'));
    if (el) el.classList.add('selected');

    const selEl = document.getElementById('wizardStep1SelectedCategoryName') || document.getElementById('wizardStep1SelectedName');
    if (selEl) selEl.textContent = categoryName;

    const catBadge = document.getElementById('wizardStep3CategoryBadge');
    if (catBadge) catBadge.textContent = categoryName;

    const btnNext = document.getElementById('btnWizardStep1Next');
    if (btnNext) btnNext.disabled = false;

    // Filter places in Step 3
    userWizardFilterPlacesByCategory();
  };

  window.userWizardSelectFacility = function (el, lotId, lotName, loc, rate) {
    const catId = (lotName || 'Institutions').toLowerCase().replace(/\s+/g, '_');
    userWizardSelectCategory(el, catId, lotName, lotId, rate);
  };

  // ============================================================
  // STEP 2: SELECT VEHICLE NUMBER & ADD VEHICLE
  // ============================================================
  window.userWizardSelectVehicle = function (el, plate, type) {
    state.vehiclePlate = plate;
    state.vehicleType = type || 'Car';

    document.querySelectorAll('.vehicle-card-pick').forEach(c => c.classList.remove('selected'));
    if (el) el.classList.add('selected');

    const selPlateEl = document.getElementById('wizardStep2SelectedPlate');
    if (selPlateEl) selPlateEl.textContent = plate;

    const btnNext = document.getElementById('btnWizardStep2Next');
    if (btnNext) btnNext.disabled = false;
  };

  window.openAddVehicleModal = function () {
    const modal = document.getElementById('addVehicleModal');
    if (modal) modal.style.display = 'flex';
  };

  window.closeAddVehicleModal = function () {
    const modal = document.getElementById('addVehicleModal');
    if (modal) modal.style.display = 'none';
    const form = document.getElementById('addVehicleForm');
    if (form) form.reset();
  };

  window.submitAddVehicleWizard = async function (e) {
    if (e && e.preventDefault) e.preventDefault();
    const plateInput = document.getElementById('newVehiclePlate');
    const typeInput = document.getElementById('newVehicleType');
    const modelInput = document.getElementById('newVehicleModel');
    const colorInput = document.getElementById('newVehicleColor');
    const btnSubmit = document.getElementById('btnSubmitNewVehicle');

    const plate = (plateInput ? plateInput.value : '').trim().toUpperCase();
    const vType = typeInput ? typeInput.value : 'Car';
    const model = modelInput ? modelInput.value.trim() : '';
    const color = colorInput ? colorInput.value.trim() : '';

    if (!plate) {
      showWizardToast('Please enter a valid license plate number.', 'error');
      return;
    }

    if (btnSubmit) {
      btnSubmit.disabled = true;
      btnSubmit.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    }

    try {
      const res = await fetch('/api/users/vehicles/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          license_plate: plate,
          vehicle_type: vType,
          make_model: model || 'Registered Vehicle',
          color: color || 'Standard'
        })
      });
      const data = await res.json();
      if (res.status === 200 && data.status === 'success') {
        const alertEl = document.getElementById('noVehiclesAlert');
        if (alertEl) alertEl.style.display = 'none';

        const grid = document.getElementById('wizardVehicleGrid');
        const addBox = document.getElementById('btnAddVehicleCard');
        const newCard = document.createElement('div');
        newCard.className = 'vehicle-card-pick selected';
        newCard.setAttribute('data-plate', plate);
        newCard.setAttribute('data-type', vType);
        const icon = vType.toLowerCase() === 'bike' ? '🏍️' : (vType.toLowerCase() === 'ev' ? '⚡' : (vType.toLowerCase() === 'suv' ? '🚙' : '🚗'));
        newCard.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div style="display:flex; align-items:center; gap:8px;">
              <div style="font-size:24px;">${icon}</div>
              <span class="badge" style="background:#e0f2fe; color:#0369a1; padding:3px 8px; border-radius:6px; font-weight:700; font-size:11px;">
                ${escapeHtml(vType)}
              </span>
            </div>
            <div class="facility-radio-mark" style="border-color:#2563eb; background:#2563eb; color:#ffffff;"><i class="fas fa-check"></i></div>
          </div>
          <div style="margin-top:10px;">
            <div class="vehicle-card-plate">${escapeHtml(plate)}</div>
            <div class="vehicle-card-sub">${escapeHtml(model || 'Registered Vehicle')} &bull; ${escapeHtml(color || 'Standard')}</div>
          </div>
        `;
        newCard.onclick = () => userWizardSelectVehicle(newCard, plate, vType);

        document.querySelectorAll('.vehicle-card-pick').forEach(c => c.classList.remove('selected'));
        if (grid && addBox) {
          grid.insertBefore(newCard, addBox);
        }

        userWizardSelectVehicle(newCard, plate, vType);
        closeAddVehicleModal();
        showWizardToast(`Vehicle '${plate}' registered successfully!`, 'success');
      } else {
        showWizardToast(data.message || 'Failed to register vehicle.', 'error');
      }
    } catch (err) {
      console.error(err);
      showWizardToast('Error connecting to server to add vehicle.', 'error');
    } finally {
      if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.innerHTML = '<i class="fas fa-check"></i> Register &amp; Select';
      }
    }
  };

  // ============================================================
  // STEP 3: SELECT SPECIFIC PARKING PLACE / INSTITUTION
  // ============================================================
  window.userWizardFilterPlacesByCategory = function () {
    const rawCat = (state.categoryName || state.categoryId || 'institutions').toLowerCase();
    
    // Normalize category term
    let normTerm = 'institutions';
    if (rawCat.includes('institution') || rawCat.includes('campus')) {
      normTerm = 'institutions';
    } else if (rawCat.includes('mall')) {
      normTerm = 'mall';
    } else if (rawCat.includes('public')) {
      normTerm = 'public places';
    } else if (rawCat.includes('city')) {
      normTerm = 'city parking';
    }

    // Dynamic section title, subheading, and icon
    const sectionHeading = document.getElementById('wizardStep3PlaceSectionHeading');
    const sectionSubheading = document.getElementById('wizardStep3PlaceSectionSubheading');
    const sectionIcon = document.getElementById('wizardStep3PlaceSectionIcon');

    if (sectionHeading && sectionSubheading && sectionIcon) {
      if (normTerm === 'institutions') {
        sectionHeading.textContent = 'Select Your Institution';
        sectionSubheading.textContent = 'Choose from the available institutions near your destination.';
        sectionIcon.className = 'fa-solid fa-building-columns';
      } else if (normTerm === 'mall') {
        sectionHeading.textContent = 'Select Your Mall';
        sectionSubheading.textContent = 'Choose from the available malls near your destination.';
        sectionIcon.className = 'fa-solid fa-bag-shopping';
      } else if (normTerm === 'public places') {
        sectionHeading.textContent = 'Select Your Public Place';
        sectionSubheading.textContent = 'Choose from the available public places near your destination.';
        sectionIcon.className = 'fa-solid fa-tree-city';
      } else {
        sectionHeading.textContent = 'Select Your City Parking Facility';
        sectionSubheading.textContent = 'Choose from the available municipal parking facilities near your destination.';
        sectionIcon.className = 'fa-solid fa-square-parking';
      }
    }

    let visibleCount = 0;
    let firstVisible = null;
    let currentSelectedVisible = false;

    // Filter cards in #wizardStep3PlacesGrid and #wizardPlaceGrid
    const cards = document.querySelectorAll('#wizardStep3PlacesGrid .institution-card-pick, #wizardPlaceGrid .place-card-pick');
    cards.forEach(card => {
      const pCat = (card.getAttribute('data-category') || '').toLowerCase();
      const pCatId = (card.getAttribute('data-category-id') || '').toLowerCase();
      const pid = (card.getAttribute('data-place-id') || '').toLowerCase();
      const supportedVehicles = (card.getAttribute('data-supported-vehicles') || 'Car,Bike').toLowerCase();

      // Category matching
      let matchesCategory = false;
      if (normTerm === 'institutions' && (pCat.includes('institution') || pCatId.includes('institution') || pid.startsWith('inst_'))) {
        matchesCategory = true;
      } else if (normTerm === 'mall' && (pCat.includes('mall') || pCatId.includes('mall') || pid.startsWith('mall_'))) {
        matchesCategory = true;
      } else if (normTerm === 'public places' && (pCat.includes('public') || pCatId.includes('pub') || pid.startsWith('pub_'))) {
        matchesCategory = true;
      } else if (normTerm === 'city parking' && (pCat.includes('city') || pCatId.includes('city') || pid.startsWith('city_'))) {
        matchesCategory = true;
      }

      // Vehicle matching
      let matchesVehicle = true;
      if (state.vehicleType) {
        const vTypeLower = state.vehicleType.toLowerCase();
        if (vTypeLower.includes('bike') && !supportedVehicles.includes('bike')) {
          matchesVehicle = false;
        } else if ((vTypeLower.includes('car') || vTypeLower.includes('suv') || vTypeLower.includes('ev')) && !supportedVehicles.includes('car')) {
          matchesVehicle = false;
        }
      }

      if (matchesCategory && matchesVehicle) {
        card.style.display = 'flex';
        visibleCount++;
        if (!firstVisible) firstVisible = card;
        if (state.placeId && pid === state.placeId.toLowerCase()) {
          currentSelectedVisible = true;
        }
      } else {
        card.style.display = 'none';
        card.classList.remove('selected');
      }
    });

    const noPlacesMsg = document.getElementById('wizardStep3NoPlacesMessage');
    if (noPlacesMsg) {
      noPlacesMsg.style.display = visibleCount === 0 ? 'block' : 'none';
    }

    // Preserve or auto-select place
    if (currentSelectedVisible && state.placeId) {
      const activeCard = document.querySelector(`.institution-card-pick[data-place-id="${state.placeId}"], .place-card-pick[data-place-id="${state.placeId}"]`);
      if (activeCard) {
        activeCard.classList.add('selected');
      }
    } else if (firstVisible) {
      const pid = firstVisible.getAttribute('data-place-id');
      const pname = firstVisible.getAttribute('data-place-name');
      const addr = firstVisible.getAttribute('data-address');
      const rate = parseFloat(firstVisible.getAttribute('data-rate') || '30.0');
      const lotId = parseInt(firstVisible.getAttribute('data-lot-id') || '1');
      const cat = firstVisible.getAttribute('data-category');
      userWizardSelectPlace(firstVisible, pid, pname, addr, rate, lotId, cat);
    } else {
      state.placeId = '';
      state.placeName = '';
      userWizardUpdateTariff();
    }
  };

  window.userWizardSelectPlace = function (el, placeId, placeName, address, rate, lotId, category) {
    state.placeId = placeId;
    state.placeName = placeName;
    state.placeAddress = address || '';
    state.hourlyRate = parseFloat(rate || 30.0);
    state.lotId = parseInt(lotId || 1);
    if (category) state.categoryName = category;

    document.querySelectorAll('.institution-card-pick, .place-card-pick').forEach(c => c.classList.remove('selected'));
    document.querySelectorAll(`[data-place-id="${placeId}"]`).forEach(c => c.classList.add('selected'));
    if (el) el.classList.add('selected');

    const selEl = document.getElementById('wizardStep3SelectedPlaceName');
    if (selEl) selEl.textContent = placeName;

    const bannerEl = document.getElementById('wizardStep4PlaceBanner');
    if (bannerEl) bannerEl.textContent = placeName;

    const lotTitle = document.getElementById('wizard2DLotTitle');
    if (lotTitle) lotTitle.textContent = `${placeName.toUpperCase()} MATRIX`;

    const btnNext = document.getElementById('btnWizardStep3Next');
    if (btnNext) btnNext.disabled = false;

    // Reset selected slot
    state.selectedSlot = null;
    const btnSlotNext = document.getElementById('btnWizardStep4Next');
    if (btnSlotNext) btnSlotNext.disabled = true;

    const slotDisp = document.getElementById('wizardSelectedSlotDisplay');
    if (slotDisp) {
      slotDisp.innerHTML = 'None Selected &mdash; <span style="font-size:13.5px; font-weight:600; color:#64748b;">Click any green (🟢 Available) slot in the matrix above</span>';
    }

    userWizardUpdateTariff();
  };

  window.userWizardRefreshPlaceCounts = async function () {
    if (!state.categoryName) return;
    try {
      const res = await fetch(`/api/booking/places?category=${encodeURIComponent(state.categoryName)}&date=${state.bookingDate}&start_time=${state.startTime}`);
      const data = await res.json();
      if (data.status === 'success' && data.places) {
        data.places.forEach(p => {
          document.querySelectorAll(`[data-place-id="${p.place_id}"]`).forEach(card => {
            const availEl = card.querySelector('.place-avail-count');
            const totalEl = card.querySelector('.place-total-count');
            if (availEl) availEl.textContent = p.available_slots;
            if (totalEl) totalEl.textContent = p.total_slots;
          });
        });
      }
    } catch (e) {
      console.log('Error refreshing place counts', e);
    }
  };

  // ============================================================
  // STEP 4: DATE, TIME, DURATION & LIVE 2D SLOT MATRIX
  // ============================================================
  window.userWizardSelectDuration = function (hours, label) {
    state.durationHours = parseFloat(hours);
    state.durationLabel = label;

    // Sync select dropdown if present
    const durSelect = document.getElementById('wizardDurationSelect');
    if (durSelect && durSelect.value !== String(hours)) {
      durSelect.value = String(hours);
    }

    document.querySelectorAll('#wizardDurationPills .duration-pill').forEach(pill => {
      const h = parseFloat(pill.getAttribute('data-hours'));
      pill.classList.toggle('active', h === state.durationHours);
    });

    userWizardUpdateTariff();
    if (state.currentStep === 4) {
      userWizardFetchLiveSlots();
    }
  };

  window.userWizardOnDurationSelectChange = function (selectEl) {
    if (!selectEl) return;
    const hours = parseFloat(selectEl.value || 1);
    const label = `${hours} Hour${hours > 1 ? 's' : ''}`;
    userWizardSelectDuration(hours, label);
  };

  window.userWizardOnScheduleChange = function () {
    const dateInp = document.getElementById('wizardBookingDate');
    const timeInp = document.getElementById('wizardStartTime');
    syncDateTimeRestrictions(false);
    if (dateInp) state.bookingDate = normalizeDateStr(dateInp.value);
    if (timeInp) state.startTime = timeInp.value;

    userWizardUpdateTariff();
    userWizardRefreshPlaceCounts();
    if (state.currentStep === 4) {
      userWizardFetchLiveSlots();
    }
  };

  window.userWizardUpdateTariff = function () {
    const dateInp = document.getElementById('wizardBookingDate');
    const timeInp = document.getElementById('wizardStartTime');
    syncDateTimeRestrictions(false);
    if (dateInp) state.bookingDate = normalizeDateStr(dateInp.value);
    if (timeInp) state.startTime = timeInp.value;

    const fee = (state.hourlyRate * state.durationHours).toFixed(2);
    const feeDisplay = document.getElementById('wizardEstimatedFeeDisplay');
    const tariffSummary = document.getElementById('wizardTariffBreakdown');

    if (feeDisplay) feeDisplay.textContent = `₹${fee}`;
    if (tariffSummary) {
      const displayName = state.categoryName || state.placeName || 'Institutions';
      tariffSummary.textContent = `${displayName} (₹${Math.round(state.hourlyRate)}/hr) × ${state.durationLabel}`;
    }
  };

  window.userWizardFetchLiveSlots = async function () {
    const container = document.getElementById('wizardSlotGridContainer');
    const lotTitle = document.getElementById('wizard2DLotTitle');
    const subtitle = document.getElementById('wizardSlotMatrixSubtitle');

    if (typeof syncDateTimeRestrictions === 'function') {
      syncDateTimeRestrictions(false);
    }

    if (lotTitle) {
      lotTitle.textContent = (state.placeName || state.categoryName || 'PARKING PLACE').toUpperCase();
    }
    if (subtitle) {
      subtitle.textContent = `${state.placeName || ''} • ${state.bookingDate} (${state.startTime}, ${state.durationLabel})`;
    }

    if (container) {
      container.innerHTML = `
        <div style="grid-column: 1/-1; text-align:center; padding:36px; color:#94a3b8;">
          <i class="fas fa-circle-notch fa-spin fa-2x"></i>
          <p style="margin-top:12px; font-weight:600;">Querying live available slots from MongoDB...</p>
        </div>
      `;
    }

    try {
      const url = `/booking/search?place_id=${encodeURIComponent(state.placeId || '')}&lot_id=${state.lotId || 1}&date=${state.bookingDate}&start_time=${state.startTime}&duration=${encodeURIComponent(state.durationLabel)}`;
      const res = await fetch(url);
      const data = await res.json();

      if (data.status === 'success' && data.slots && data.slots.length > 0) {
        allLoadedWizardSlots = data.slots;
        populateSectionFilter(data.slots);
        userWizardFilterSlotsBySection();
      } else {
        const errorMsg = data.message || 'No parking slots currently found for this location.';
        container.innerHTML = `
          <div style="grid-column: 1/-1; text-align:center; padding:30px; color:#f87171;">
            <i class="fas fa-triangle-exclamation fa-2x"></i>
            <p style="margin-top:8px;">${errorMsg}</p>
          </div>
        `;
      }
    } catch (err) {
      console.error('Error fetching live slots:', err);
      if (container) {
        container.innerHTML = `
          <div style="grid-column: 1/-1; text-align:center; padding:30px; color:#f87171;">
            <i class="fas fa-circle-exclamation fa-2x"></i>
            <p style="margin-top:8px;">Failed to load live 2D slot layout. Please click "Refresh Matrix".</p>
          </div>
        `;
      }
    }
  };

  function populateSectionFilter(slots) {
    const filterEl = document.getElementById('wizardSectionFilter');
    if (!filterEl) return;
    const currentVal = filterEl.value;

    const sections = new Set();
    slots.forEach(s => {
      const num = (s.slot_number || '').trim().toUpperCase();
      const match = num.match(/^([A-Za-z]+)/);
      if (match) sections.add(match[1]);
    });

    let opts = '<option value="ALL">All Slots</option>';
    Array.from(sections).sort().forEach(sec => {
      opts += `<option value="${sec}">${sec}-Bay</option>`;
    });
    filterEl.innerHTML = opts;
    if (currentVal && currentVal !== 'ALL' && Array.from(sections).includes(currentVal)) {
      filterEl.value = currentVal;
    } else {
      filterEl.value = 'ALL';
    }
  }

  window.userWizardFilterSlotsBySection = function () {
    const filterEl = document.getElementById('wizardSectionFilter');
    const filterVal = filterEl ? filterEl.value : 'ALL';

    let filtered = allLoadedWizardSlots;
    if (filterVal && filterVal !== 'ALL') {
      filtered = allLoadedWizardSlots.filter(s => {
        const snum = (s.slot_number || '').toUpperCase();
        return snum.startsWith(filterVal);
      });
    }
    renderFilteredWizardSlots(filtered);
  };

  function renderFilteredWizardSlots(slots) {
    const container = document.getElementById('wizardSlotGridContainer');
    if (!container) return;
    container.innerHTML = '';

    if (!slots || slots.length === 0) {
      container.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:30px; color:#94a3b8;">No slots found matching this section filter.</div>';
      return;
    }

    slots.forEach(slot => {
      const slotId = parseInt(slot.slot_id);
      const slotNumRaw = slot.slot_number || '';
      const slotNumDisp = displaySlotNumber(slotNumRaw);
      const status = (slot.status || 'available').toLowerCase();
      const isAvailable = status === 'available';
      const isSelected = state.selectedSlot && (parseInt(state.selectedSlot.slot_id) === slotId || state.selectedSlot.slot_number === slotNumRaw);

      const isBike = !!(
        (slot.vehicle_type && /bike|scooter|motorcycle|two-wheeler/i.test(slot.vehicle_type)) ||
        (slot.slot_type && /bike|scooter|motorcycle|two-wheeler/i.test(slot.slot_type)) ||
        (slot.slot_number && /^B\d+/i.test(slot.slot_number) && (!slot.vehicle_type || !slot.vehicle_type.toLowerCase().includes('car')))
      );
      const vehicleImg = isBike ? '/static/images/bike-top.svg' : '/static/images/car-top.svg';

      const cell = document.createElement('div');
      cell.id = `wizardSlotBox_${slotId}`;

      let visualHtml = '';
      let statusClass = status;

      if (status === 'reserved') {
        statusClass = 'reserved';
        visualHtml = `
          <div class="slot-box-vehicle-wrap">
            <img src="${vehicleImg}" alt="Reserved" class="slot-box-vehicle-img" />
          </div>
          <div class="slot-box-status-tag reserved">RESERVED</div>
        `;
        cell.title = `Slot ${slotNumDisp}: Reserved for incoming driver`;
      } else if (status === 'occupied') {
        statusClass = 'occupied';
        visualHtml = `
          <div class="slot-box-vehicle-wrap">
            <img src="${vehicleImg}" alt="Occupied" class="slot-box-vehicle-img" />
          </div>
          <div class="slot-box-status-tag occupied">OCCUPIED</div>
        `;
        cell.title = `Slot ${slotNumDisp}: Occupied`;
      } else if (status === 'overstayed') {
        statusClass = 'overstayed';
        visualHtml = `
          <div class="slot-box-vehicle-wrap">
            <img src="${vehicleImg}" alt="Overstayed" class="slot-box-vehicle-img" />
          </div>
          <div class="slot-box-status-tag overstayed">⚠️ OVERSTAY</div>
        `;
        cell.title = `Slot ${slotNumDisp}: Overstayed`;
      } else {
        statusClass = 'available eligible-exchange';
        if (isSelected) {
          statusClass += ' selected';
          visualHtml = `
            <div class="slot-box-empty-bay" style="border-color:#38bdf8; background:rgba(56,189,248,0.2); color:#38bdf8;">
              <i class="fas fa-check" style="font-size:18px;"></i>
            </div>
            <div class="slot-exchange-tag" style="color:#38bdf8; font-weight:800; letter-spacing:0.5px;">SELECTED</div>
          `;
          cell.title = `Slot ${slotNumDisp}: Selected for your booking`;
        } else {
          visualHtml = `
            <div class="slot-box-empty-bay"><i class="fas fa-parking"></i></div>
            <div class="slot-exchange-tag">ELIGIBLE</div>
          `;
          cell.title = `Slot ${slotNumDisp}: Available for reservation. Click to select!`;
        }
      }

      cell.className = `slot-box-2d ${statusClass}`;
      cell.innerHTML = `
        <div class="slot-box-name">${escapeHtml(slotNumDisp)}</div>
        ${visualHtml}
      `;

      if (isAvailable) {
        cell.onclick = () => userWizardPickSlot(cell, slot);
      }

      container.appendChild(cell);
    });
  }

  window.userWizardPickSlot = function (cellEl, slot) {
    state.selectedSlot = slot;
    const slotNumDisp = displaySlotNumber(slot.slot_number);

    document.querySelectorAll('#wizardSlotGridContainer .slot-box-2d').forEach(c => {
      c.classList.remove('selected');
      const tag = c.querySelector('.slot-exchange-tag');
      const bay = c.querySelector('.slot-box-empty-bay');
      if (tag && c.classList.contains('available')) {
        tag.textContent = 'ELIGIBLE';
        tag.style.color = '#34d399';
        tag.style.fontWeight = '800';
      }
      if (bay && c.classList.contains('available')) {
        bay.innerHTML = '<i class="fas fa-parking"></i>';
        bay.style.borderColor = 'rgba(255, 255, 255, 0.2)';
        bay.style.background = 'transparent';
        bay.style.color = '#64748b';
      }
    });

    if (cellEl) {
      cellEl.classList.add('selected');
      const tag = cellEl.querySelector('.slot-exchange-tag');
      const bay = cellEl.querySelector('.slot-box-empty-bay');
      if (tag) {
        tag.textContent = 'SELECTED';
        tag.style.color = '#38bdf8';
        tag.style.fontWeight = '800';
      }
      if (bay) {
        bay.innerHTML = '<i class="fas fa-check" style="font-size:18px;"></i>';
        bay.style.borderColor = '#38bdf8';
        bay.style.background = 'rgba(56,189,248,0.2)';
        bay.style.color = '#38bdf8';
      }
    }

    const display = document.getElementById('wizardSelectedSlotDisplay');
    if (display) {
      display.innerHTML = `
        <span style="color:#10b981;"><i class="fas fa-check-circle"></i> Slot ${escapeHtml(slotNumDisp)} (${escapeHtml(slot.slot_number)})</span>
        <span style="color:#64748b; font-size:13.5px; font-weight:600;"> &bull; ${escapeHtml(slot.slot_type || 'Standard')} Bay &bull; Floor: ${escapeHtml(slot.floor || 'Ground Floor')}</span>
      `;
    }

    const btnNext = document.getElementById('btnWizardStep4Next');
    if (btnNext) btnNext.disabled = false;
  };

  // ============================================================
  // STEP NAVIGATION CONTROLLER
  // ============================================================
  window.userWizardGoToStep = function (stepNumber) {
    if (stepNumber === 2 && !state.categoryId) {
      showWizardToast('Please select a facility category first.', 'error');
      return;
    }
    if (stepNumber === 3) {
      if (!state.vehiclePlate) {
        showWizardToast('Please select or register a vehicle first.', 'error');
        return;
      }
    }
    if (stepNumber === 4) {
      if (!state.placeId) {
        showWizardToast('Please select a specific parking place first.', 'error');
        return;
      }
    }
    if (stepNumber === 5) {
      const dateInp = document.getElementById('wizardBookingDate');
      const timeInp = document.getElementById('wizardStartTime');
      if (dateInp && dateInp.value) state.bookingDate = normalizeDateStr(dateInp.value);
      if (timeInp && timeInp.value) state.startTime = timeInp.value;

      if (!state.selectedSlot) {
        showWizardToast('Please select an available parking slot from the live 2D grid.', 'error');
        return;
      }

      const check = validateBookingDateTime(state.bookingDate, state.startTime);
      if (!check.valid) {
        showWizardToast(check.message, 'error');
        syncDateTimeRestrictions(false);
        userWizardGoToStep(4);
        return;
      }
    }

    state.currentStep = stepNumber;

    for (let i = 1; i <= 5; i++) {
      const panel = document.getElementById(`wizardStepPanel${i}`);
      const indicator = document.getElementById(`wizardStepIndicator${i}`);
      const circle = document.getElementById(`circleStep${i}`);

      if (panel) panel.classList.toggle('active', i === stepNumber);
      if (indicator) {
        indicator.classList.toggle('active', i === stepNumber);
        indicator.classList.toggle('completed', i < stepNumber);
      }
      if (circle) {
        if (i < stepNumber) {
          circle.innerHTML = '<i class="fas fa-check"></i>';
        } else {
          circle.textContent = i;
        }
      }
    }

    const wizardCont = document.getElementById('userWizardStepper');
    if (wizardCont) {
      wizardCont.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // Trigger step hooks
    if (stepNumber === 3) {
      userWizardFilterPlacesByCategory();
      userWizardRefreshPlaceCounts();
    } else if (stepNumber === 4) {
      userWizardFetchLiveSlots();
    } else if (stepNumber === 5) {
      userWizardPopulateReview();
    }
  };

  // ============================================================
  // STEP 5: REVIEW & CONFIRM BOOKING
  // ============================================================
  window.userWizardPopulateReview = function () {
    const slot = state.selectedSlot;
    if (!slot) return;

    const setField = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    const slotNumDisp = displaySlotNumber(slot.slot_number);
    const endTime = calculateEndTimeStr(state.startTime, state.durationHours);

    setField('wizardRevFacility', `${state.categoryName} • ${state.placeName}`);
    setField('wizardRevAddress', state.placeAddress || 'Bangalore Central Hub');
    setField('wizardRevVehicle', `${state.vehiclePlate} (${state.vehicleType})`);
    setField('wizardRevDate', state.bookingDate);
    setField('wizardRevTimeInterval', `${state.startTime} – ${endTime}`);
    setField('wizardRevDuration', state.durationLabel);
    setField('wizardRevSlot', `Slot ${slotNumDisp} (${slot.slot_number})`);
    setField('wizardRevFloor', `${slot.floor || 'Ground Floor'} (${slot.zone || slot.slot_type || 'Standard Bay'})`);
    setField('wizardRevHourlyRate', `₹${state.hourlyRate.toFixed(2)} / hr`);
    setField('wizardRevDurationText', state.durationLabel);

    const totalFee = (state.hourlyRate * state.durationHours).toFixed(2);
    setField('wizardRevTotalFee', `₹${totalFee}`);
  };

  window.userWizardSubmitBooking = async function () {
    const btn = document.getElementById('btnWizardFinalConfirm');
    if (!btn || !state.selectedSlot) return;

    // Real-time date/time validation right before confirming
    const check = validateBookingDateTime(state.bookingDate, state.startTime);
    if (!check.valid) {
      showWizardToast(check.message, 'error');
      syncDateTimeRestrictions(false);
      userWizardGoToStep(4);
      return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Reserving Slot in MongoDB...';

    const payload = {
      slot_id: state.selectedSlot.slot_id,
      lot_id: state.lotId,
      place_id: state.placeId,
      place_name: state.placeName,
      category: state.categoryName,
      facility_category: state.categoryName,
      booking_date: state.bookingDate,
      date: state.bookingDate,
      start_time: state.startTime,
      duration: state.durationLabel,
      vehicle_plate: state.vehiclePlate,
      vehicle_number: state.vehiclePlate,
      vehicle_type: state.vehicleType
    };

    try {
      const res = await fetch('/booking/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (res.status === 201 && data.status === 'success') {
        state.confirmedBooking = data.booking;
        userWizardShowSuccess(data.booking);
        showWizardToast('Booking confirmed successfully! Digital Barrier Pass issued.', 'success');

        if (typeof window.loadUserNotifications === 'function') {
          window.loadUserNotifications();
        }
        if (typeof window.loadUserDashboard === 'function') {
          window.loadUserDashboard();
        }
      } else if (res.status === 400) {
        showWizardToast(data.message || 'Please select a current or future date and time.', 'error');
        syncDateTimeRestrictions(false);
        userWizardGoToStep(4);
      } else if (res.status === 409) {
        showWizardToast(data.message || 'Slot was just booked by another user! Please pick another slot.', 'error');
        userWizardGoToStep(4);
      } else {
        showWizardToast(data.message || 'Failed to complete reservation.', 'error');
      }
    } catch (err) {
      console.error(err);
      showWizardToast('Network error while creating booking.', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-check-circle"></i> Confirm Booking';
      }
    }
  };

  // Pass Date and Time formatters for Pixel-Perfect Parking Pass
  function formatPassDate(dateStr) {
    if (!dateStr) return '';
    try {
      const parts = String(dateStr).trim().split('-');
      if (parts.length === 3) {
        const year = parts[0];
        const monthIdx = parseInt(parts[1], 10) - 1;
        const day = parseInt(parts[2], 10);
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        if (!isNaN(day) && monthIdx >= 0 && monthIdx < 12) {
          return `${day} ${months[monthIdx]} ${year}`;
        }
      }
    } catch (e) {}
    return String(dateStr);
  }

  function formatPassTime(timeStr) {
    if (!timeStr) return '';
    timeStr = String(timeStr).trim();
    if (timeStr.toUpperCase().includes('AM') || timeStr.toUpperCase().includes('PM')) {
      return timeStr;
    }
    const parts = timeStr.split(':');
    if (parts.length >= 2) {
      let hours = parseInt(parts[0], 10);
      const minutes = parts[1].slice(0, 2).padStart(2, '0');
      if (!isNaN(hours)) {
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        if (hours === 0) hours = 12;
        const hoursStr = hours < 10 ? `0${hours}` : `${hours}`;
        return `${hoursStr}:${minutes} ${ampm}`;
      }
    }
    return timeStr;
  }

  function formatPassTimeRange(startTime, endTime) {
    const s = formatPassTime(startTime);
    const e = formatPassTime(endTime);
    if (s && e) {
      return `${s} – ${e}`;
    }
    return s || e || '';
  }

  let successPassQrInstance = null;
  function renderSuccessPassQr(text) {
    const container = document.getElementById('wizardSuccessQrContainer');
    if (!container) return;
    container.innerHTML = '';
    const passPayload = String(text || 'BK-CONFIRMED').trim();
    if (typeof QRCode !== 'undefined') {
      try {
        successPassQrInstance = new QRCode(container, {
          text: passPayload,
          width: 116,
          height: 116,
          colorDark: '#0f172a',
          colorLight: '#ffffff',
          correctLevel: QRCode.CorrectLevel.M
        });
      } catch (err) {
        console.error('Error generating pass QR code:', err);
      }
    }
  }

  function userWizardShowSuccess(b) {
    const revCont = document.getElementById('wizardReviewContainer');
    const succCard = document.getElementById('wizardSuccessCard');
    if (revCont) revCont.style.display = 'none';
    if (succCard) succCard.style.display = 'block';

    for (let i = 1; i <= 5; i++) {
      const ind = document.getElementById(`wizardStepIndicator${i}`);
      const cir = document.getElementById(`circleStep${i}`);
      if (ind) {
        ind.classList.remove('active');
        ind.classList.add('completed');
      }
      if (cir) {
        cir.innerHTML = '<i class="fas fa-check"></i>';
      }
    }

    const setField = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    const slotNum = b.slot_number || (state.selectedSlot ? state.selectedSlot.slot_number : 'A01');
    const rawSlotDisp = displaySlotNumber(slotNum);
    // Strip redundant "Slot " prefix so only slot code (e.g. "R12") is shown inside the slot box
    const cleanSlotDisp = String(rawSlotDisp || 'A01').replace(/^Slot\s*/i, '').trim();

    const endTime = b.end_time || calculateEndTimeStr(b.start_time || state.startTime, state.durationHours);
    const dateVal = b.booking_date || b.date || state.bookingDate;
    const startTimeVal = b.start_time || state.startTime;
    const bookingId = b.booking_id || (b.reservation_id ? `BK-${b.reservation_id}` : 'BK-CONFIRMED');
    const passCode = b.pass_code || bookingId;
    const vehicle = b.vehicle_plate || b.vehicle_number || state.vehiclePlate || 'KA01AB1234';
    const facility = b.place_name || b.parking_place || b.lot_name || state.placeName || state.categoryName || 'Parking Facility';
    const rawFee = (b.total_amount !== undefined && b.total_amount !== null) ? Number(b.total_amount) : (state.hourlyRate * state.durationHours);
    const feeStr = isNaN(rawFee) ? '35.00' : rawFee.toFixed(2);

    setField('wizardSuccessSlot', cleanSlotDisp);
    setField('wizardSuccessFacility', facility);
    setField('wizardSuccessBookingId', bookingId);
    setField('wizardSuccessPassCode', passCode);
    setField('wizardSuccessVehicle', vehicle);
    setField('wizardSuccessDate', formatPassDate(dateVal));
    setField('wizardSuccessTime', formatPassTimeRange(startTimeVal, endTime));
    setField('wizardSuccessDateTime', `${dateVal} (${startTimeVal} – ${endTime})`);
    setField('wizardSuccessFee', `₹${feeStr}`);

    // Generate genuine QR code encoding confirmed booking/pass code
    renderSuccessPassQr(bookingId);
  }

  window.userWizardReset = function () {
    state.selectedSlot = null;
    state.confirmedBooking = null;

    const revCont = document.getElementById('wizardReviewContainer');
    const succCard = document.getElementById('wizardSuccessCard');
    if (revCont) revCont.style.display = 'block';
    if (succCard) succCard.style.display = 'none';

    const qrContainer = document.getElementById('wizardSuccessQrContainer');
    if (qrContainer) qrContainer.innerHTML = '';

    const btnSlotNext = document.getElementById('btnWizardStep4Next');
    if (btnSlotNext) btnSlotNext.disabled = true;

    const display = document.getElementById('wizardSelectedSlotDisplay');
    if (display) {
      display.innerHTML = 'None Selected &mdash; <span style="font-size:13.5px; font-weight:600; color:#64748b;">Click any green (🟢 Available) slot in the matrix above</span>';
    }

    userWizardGoToStep(1);
  };

  // ============================================================
  // QUICK BOOKING MODE CONTROLLERS
  // ============================================================
  window.loadAvailableSlotsForQuickBooking = async function () {
    const lotSelect = document.getElementById('bookingLotSelect');
    const slotSelect = document.getElementById('bookingSlotSelect');
    if (!slotSelect) return;
    const lotId = lotSelect ? (lotSelect.value || 1) : 1;
    slotSelect.innerHTML = '<option value="">Loading available slots...</option>';

    try {
      const res = await fetch(`/booking/search?lot_id=${lotId}&date=${getLocalDateStr()}&start_time=${getLocalTimeStr()}&duration=2%20Hours`);
      const data = await res.json();
      if (data.status === 'success') {
        const avail = (data.slots || []).filter(s => (s.status || '').toLowerCase() === 'available');
        if (avail.length === 0) {
          slotSelect.innerHTML = '<option value="">No vacant slots available in this facility</option>';
        } else {
          slotSelect.innerHTML = avail.map(s => {
            const num = displaySlotNumber(s.slot_number);
            return `<option value="${s.slot_id}">Slot ${num} (${escapeHtml(s.slot_number)}) &bull; ${escapeHtml(s.slot_type || 'Standard')} &bull; Floor: ${escapeHtml(s.floor || 'G')}</option>`;
          }).join('');
        }
      }
    } catch (e) {
      console.error('Error fetching quick slots:', e);
      slotSelect.innerHTML = '<option value="">Failed to fetch slots</option>';
    }
  };

  window.userSubmitQuickBooking = async function (e) {
    if (e && e.preventDefault) e.preventDefault();
    const lotSelect = document.getElementById('bookingLotSelect');
    const slotSelect = document.getElementById('bookingSlotSelect');
    const dateInput = document.getElementById('bookingDate');
    const startInput = document.getElementById('bookingStartTime');
    const endInput = document.getElementById('bookingEndTime');
    const vehicleSelect = document.getElementById('bookingVehicleSelect');

    const slotId = slotSelect ? slotSelect.value : '';
    const lotId = lotSelect ? lotSelect.value : '1';
    const dateVal = dateInput && dateInput.value ? dateInput.value : getLocalDateStr();
    const startTime = startInput && startInput.value ? startInput.value : getLocalTimeStr();
    let plate = vehicleSelect ? vehicleSelect.value : '';

    if (!slotId) {
      showWizardToast('Please choose an available slot.', 'error');
      return;
    }
    if (!plate || plate === '__custom__') {
      plate = prompt('Enter vehicle license plate (e.g. KA01AB1234):');
      if (!plate) return;
    }

    const check = validateBookingDateTime(dateVal, startTime);
    if (!check.valid) {
      showWizardToast(check.message, 'error');
      return;
    }

    try {
      const res = await fetch('/booking/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slot_id: parseInt(slotId),
          lot_id: parseInt(lotId),
          parking_lot_id: parseInt(lotId),
          booking_date: dateVal,
          date: dateVal,
          start_time: startTime,
          duration: '2 Hours',
          vehicle_plate: plate.toUpperCase().trim(),
          vehicle_number: plate.toUpperCase().trim(),
          vehicle_type: 'Car'
        })
      });
      const data = await res.json();
      if (res.status === 201 && data.status === 'success') {
        showWizardToast('Quick Booking Confirmed!', 'success');
        
        if (document.getElementById('wizardSuccessCard')) {
          switchBookingMode('wizard');
          userWizardGoToStep(5);
          userWizardShowSuccess(data.booking || {
            booking_id: data.booking_id,
            pass_code: data.qr_pass_code || data.booking_id,
            slot_number: data.slot_number,
            place_name: data.lot_name,
            lot_name: data.lot_name,
            vehicle_plate: plate.toUpperCase().trim(),
            booking_date: dateVal,
            start_time: startTime,
            end_time: calculateEndTimeStr(startTime, 2.0),
            total_amount: data.fee || 80.0
          });
        } else {
          window.location.href = '/booking/my-bookings';
        }
      } else {
        showWizardToast(data.message || 'Quick booking failed.', 'error');
      }
    } catch (err) {
      console.error(err);
      showWizardToast('Error creating quick booking.', 'error');
    }
  };

  function showWizardToast(msg, type = 'success') {
    if (typeof window.showUserToast === 'function') {
      window.showUserToast(msg, type);
      return;
    }
    const toast = document.getElementById('bookingToast') || document.getElementById('userToast');
    if (!toast) {
      alert(msg);
      return;
    }
    toast.style.display = 'block';
    toast.className = `user-toast ${type === 'error' ? 'user-toast-error' : 'user-toast-success'}`;
    toast.innerHTML = `<i class="fas ${type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-check'}"></i> <span>${escapeHtml(msg)}</span>`;
    setTimeout(() => { toast.style.display = 'none'; }, 3800);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, m => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[m]);
  }
})();
