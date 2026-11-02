/**
 * Simulation Controls & Real-Time Event Dispatcher
 */

async function tickSimulation(minutes = 15) {
  try {
    const res = await fetch('/api/simulate/tick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ minutes })
    });
    const data = await res.json();
    if (data.status === 'success') {
      const r = data.result;
      showToast(`Simulated Clock Advanced +${minutes}m (${r.formatted_time})`, 'info');

      if (r.alerts_triggered && r.alerts_triggered.length > 0) {
        r.alerts_triggered.forEach(a => {
          showToast(`🚨 OVERSTAY ALERT: Slot ${a.slot_number} exceeded booking by ${a.extra_minutes}m! Penalty: ₹${a.penalty_amount}`, 'danger');
        });
      }

      refreshAllDashboardData();
    }
  } catch (err) {
    console.error("Simulation tick error:", err);
  }
}

async function triggerArrival() {
  const floor = document.getElementById('floorSelect') ? document.getElementById('floorSelect').value : 'Ground Floor';
  try {
    const res = await fetch('/api/simulate/arrival', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ floor })
    });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(`🚗 ${data.message}`, 'primary');
      refreshAllDashboardData();
    } else {
      showToast(data.message, 'warning');
    }
  } catch (err) {
    console.error("Arrival trigger error:", err);
  }
}

async function triggerDeparture() {
  try {
    const res = await fetch('/api/simulate/departure', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(`🏁 ${data.message}`, 'success');
      refreshAllDashboardData();
    } else {
      showToast(data.message, 'warning');
    }
  } catch (err) {
    console.error("Departure trigger error:", err);
  }
}

async function resetSimClock() {
  try {
    const res = await fetch('/api/simulate/reset-clock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (data.status === 'success') {
      showToast('Virtual clock reset to real PC time', 'info');
      if (typeof refreshAllDashboardData === 'function') {
        refreshAllDashboardData();
      }
    }
  } catch (err) {
    console.error("Reset clock error:", err);
  }
}

async function resetSystemState() {
  if (!confirm("Are you sure you want to reset simulation back to initial mockup state?")) return;
  try {
    const res = await fetch('/api/simulate/reset', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(data.message, 'success');
      refreshAllDashboardData();
    }
  } catch (err) {
    console.error("Reset error:", err);
  }
}
