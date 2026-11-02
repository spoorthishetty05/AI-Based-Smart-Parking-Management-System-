/**
 * AI & Machine Learning Lab Engine
 * Live Occupancy Prediction, Model Training, EDA Analytics, Dataset Preview & Preprocessing
 */

let currentAiSubTab = 'predictor';

async function loadAiLabData() {
  try {
    const res = await fetch('/api/ai/eda-metrics');
    const data = await res.json();
    if (data.status === 'success') {
      renderModelMetrics(data.data);
      renderFeatureImportances(data.data.feature_importances);
      if (typeof initEdaCharts === 'function') {
        initEdaCharts(data.data);
      }
      if (typeof initDurationCharts === 'function' && data.data.duration_analysis) {
        initDurationCharts(data.data.duration_analysis);
      }
    }

    // Load dataset and preprocessing info
    loadDatasetPreview();
    loadPreprocessingInfo();
  } catch (err) {
    console.error("Error loading AI Lab data:", err);
  }
}

function switchAiSubTab(subTabName) {
  currentAiSubTab = subTabName;
  document.querySelectorAll('.ai-sub-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-subtab') === subTabName);
  });
  document.querySelectorAll('.ai-sub-view').forEach(view => {
    view.classList.toggle('active', view.id === `ai-subview-${subTabName}`);
  });
}

function renderModelMetrics(edaData) {
  const container = document.getElementById('modelMetricsGrid');
  if (!container) return;

  const metrics = edaData.model_metrics || {};
  const bestModel = edaData.best_model || 'GradientBoostingRegressor';

  let html = '';
  for (const [modelName, m] of Object.entries(metrics)) {
    const isBest = modelName === bestModel;
    html += `
      <div style="background:#ffffff; border:1.5px solid ${isBest ? 'var(--primary)' : 'var(--border-color)'}; border-radius:14px; padding:16px; box-shadow:var(--shadow-subtle); position:relative;">
        ${isBest ? '<span style="position:absolute; top:12px; right:12px; background:var(--primary-light); color:var(--primary); font-size:10px; font-weight:800; padding:2px 8px; border-radius:99px;">⭐ BEST MODEL</span>' : ''}
        <h4 style="font-size:14px; font-weight:800; color:#0f172a; margin-bottom:12px;"><i class="fas fa-microchip" style="color:var(--primary); margin-right:6px;"></i>${modelName}</h4>
        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:6px; text-align:center;">
          <div style="background:#f8fafc; padding:8px; border-radius:8px;">
            <div style="font-size:9px; color:#64748b; font-weight:700;">R² ACCURACY</div>
            <div style="font-size:14px; font-weight:800; color:var(--available);">${(m.r2_score * 100).toFixed(1)}%</div>
          </div>
          <div style="background:#f8fafc; padding:8px; border-radius:8px;">
            <div style="font-size:9px; color:#64748b; font-weight:700;">MAE</div>
            <div style="font-size:14px; font-weight:800; color:#3b82f6;">${m.mae}%</div>
          </div>
          <div style="background:#f8fafc; padding:8px; border-radius:8px;">
            <div style="font-size:9px; color:#64748b; font-weight:700;">RMSE</div>
            <div style="font-size:14px; font-weight:800; color:#f59e0b;">${m.rmse}%</div>
          </div>
          <div style="background:#f8fafc; padding:8px; border-radius:8px;">
            <div style="font-size:9px; color:#64748b; font-weight:700;">MSE</div>
            <div style="font-size:14px; font-weight:800; color:#64748b;">${m.mse ?? (m.rmse * m.rmse).toFixed(1)}</div>
          </div>
        </div>
      </div>
    `;
  }
  container.innerHTML = html;
}

function renderFeatureImportances(importances) {
  const container = document.getElementById('featureImportanceList');
  if (!container || !importances) return;

  const prettyLabels = {
    'hour': 'Hour of Day (Diurnal Rush Hours)',
    'is_weekend': 'Weekend vs Weekday Commuter Dynamic',
    'has_event': 'Nearby Special Events & Expo Surge',
    'weather_Rainy': 'Inclement Rainy Weather Traffic Spike',
    'lag_1h_occ': 'Autoregressive 1-Hour Occupancy Lag',
    'sin_hour': 'Cyclical Sine Transform (Hour)',
    'cos_hour': 'Cyclical Cosine Transform (Hour)',
    'month': 'Seasonal Month Multiplier',
    'day_of_week': 'Day of Week Baseline'
  };

  let html = '';
  const entries = Object.entries(importances).sort((a,b) => b[1] - a[1]);
  const maxVal = entries[0] ? entries[0][1] : 1.0;

  for (const [feat, val] of entries) {
    const label = prettyLabels[feat] || feat;
    const pct = ((val / maxVal) * 100).toFixed(1);
    const weightPct = (val * 100).toFixed(1);

    html += `
      <div style="margin-bottom:12px;">
        <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:700; margin-bottom:4px;">
          <span>${label}</span>
          <span style="color:var(--primary); font-weight:800;">${weightPct}%</span>
        </div>
        <div style="background:#f1f5f9; height:8px; border-radius:99px; overflow:hidden;">
          <div style="background:linear-gradient(90deg, #0d9488, #10b981); width:${pct}%; height:100%; border-radius:99px;"></div>
        </div>
      </div>
    `;
  }
  container.innerHTML = html;
}

async function loadDatasetPreview() {
  const container = document.getElementById('datasetPreviewTable');
  if (!container) return;

  try {
    const res = await fetch('/api/ai/dataset-preview?limit=15');
    const data = await res.json();
    if (data.status === 'success') {
      const stats = data.stats;
      const records = data.records;

      // Render stats badges
      const statsEl = document.getElementById('datasetStatsSummary');
      if (statsEl) {
        statsEl.innerHTML = `
          <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:16px;">
            <div class="kpi-mini-card">
              <span class="label">Total Records</span>
              <span class="val">${stats.total_rows.toLocaleString()}</span>
            </div>
            <div class="kpi-mini-card">
              <span class="label">Mean Occupancy</span>
              <span class="val" style="color:var(--primary);">${stats.mean_occupancy}%</span>
            </div>
            <div class="kpi-mini-card">
              <span class="label">Peak Peak</span>
              <span class="val" style="color:#ef4444;">${stats.max_occupancy}%</span>
            </div>
            <div class="kpi-mini-card">
              <span class="label">Time Span</span>
              <span class="val" style="font-size:12px; font-weight:700;">180 Days</span>
            </div>
          </div>
        `;
      }

      let html = `
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Day</th>
                <th>Hour</th>
                <th>Weather</th>
                <th>Event</th>
                <th>Occupancy %</th>
                <th>Occupied Slots</th>
                <th>Available</th>
              </tr>
            </thead>
            <tbody>
      `;

      records.forEach(r => {
        const occColor = r.occupancy_percentage >= 80 ? '#ef4444' : (r.occupancy_percentage >= 50 ? '#f59e0b' : '#10b981');
        html += `
          <tr>
            <td><code>${r.timestamp}</code></td>
            <td><b>${r.day_name}</b></td>
            <td>${r.hour}:00</td>
            <td><span class="badge ${r.weather === 'Rainy' ? 'badge-primary' : 'badge-light'}">${r.weather}</span></td>
            <td>${r.has_event ? '<span class="badge badge-danger">Expo/Event</span>' : '<span style="color:#94a3b8;">--</span>'}</td>
            <td><b style="color:${occColor};">${r.occupancy_percentage}%</b></td>
            <td>${r.occupied_slots} / 110</td>
            <td><span class="badge badge-success">${r.available_slots}</span></td>
          </tr>
        `;
      });

      html += `</tbody></table></div>`;
      container.innerHTML = html;
    }
  } catch (err) {
    console.error("Dataset preview error:", err);
  }
}

async function loadPreprocessingInfo() {
  const container = document.getElementById('preprocessingPipelineContent');
  if (!container) return;

  try {
    const res = await fetch('/api/ai/preprocessing-info');
    const data = await res.json();
    if (data.status === 'success') {
      let html = '<div style="display:flex; flex-direction:column; gap:12px; margin-bottom:20px;">';
      data.pipeline_steps.forEach(step => {
        html += `
          <div style="background:#f8fafc; border-left:4px solid var(--primary); padding:10px 14px; border-radius:0 8px 8px 0;">
            <b style="font-size:13px; color:#0f172a;">${step.step}</b>
            <p style="font-size:12px; color:#64748b; margin-top:3px; line-height:1.5;">${step.description}</p>
          </div>
        `;
      });
      html += '</div>';

      html += '<h4 style="font-size:13px; font-weight:800; color:#0f172a; margin-bottom:8px;">Extracted Feature Matrix (10 Signals)</h4>';
      html += '<div class="table-responsive"><table class="data-table"><thead><tr><th>Feature Name</th><th>Encoding Type</th><th>Predictive Role</th></tr></thead><tbody>';
      data.features.forEach(f => {
        html += `<tr><td><code>${f.name}</code></td><td>${f.type}</td><td>${f.role}</td></tr>`;
      });
      html += '</tbody></table></div>';
      container.innerHTML = html;
    }
  } catch (err) {
    console.error("Preprocessing info error:", err);
  }
}

async function runAiPrediction() {
  const date = document.getElementById('predDate').value;
  const time = document.getElementById('predTime').value;
  const weather = document.getElementById('predWeather').value;
  const hasEvent = document.getElementById('predEvent').checked;
  const floor = document.getElementById('predFloor').value;

  const resultContainer = document.getElementById('predictionResultCard');
  resultContainer.innerHTML = '<div style="text-align:center; padding:20px;"><i class="fas fa-spinner fa-spin fa-2x" style="color:var(--primary);"></i><p style="margin-top:8px; font-size:13px;">Computing ML Prediction...</p></div>';

  try {
    const res = await fetch('/api/ai/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, time, weather, has_event: hasEvent, floor })
    });
    const data = await res.json();
    const p = data.prediction;

    const badgeColor = {
      'Low': '#10b981',
      'Moderate': '#3b82f6',
      'High': '#f59e0b',
      'Peak / Critical': '#ef4444'
    }[p.traffic_level] || '#0d9488';

    resultContainer.innerHTML = `
      <div style="background:#ffffff; border:1.5px solid var(--primary); border-radius:14px; padding:18px; box-shadow:var(--shadow-subtle);">
        <div style="text-align:center; margin-bottom:14px;">
          <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px;">Predicted Occupancy Rate</div>
          <div style="font-size:40px; font-weight:800; color:#0f172a; margin:4px 0;">${p.predicted_occupancy}%</div>
          <span style="background:${badgeColor}22; color:${badgeColor}; font-size:12px; font-weight:800; padding:4px 12px; border-radius:99px; border:1px solid ${badgeColor}44;">
            ${p.traffic_level} Traffic
          </span>
        </div>

        <div style="background:#f8fafc; border-radius:10px; padding:12px; margin-bottom:14px; font-size:12px; line-height:1.7;">
          <div style="display:flex; justify-content:space-between;">
            <span style="color:#64748b;">Target Capacity:</span>
            <b>${p.total_slots} Slots (${p.floor})</b>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="color:#64748b;">Est. Occupied:</span>
            <b style="color:#3b82f6;">~${p.est_occupied_slots} Slots</b>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="color:#64748b;">Est. Available:</span>
            <b style="color:#10b981;">~${p.est_available_slots} Slots</b>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="color:#64748b;">95% Confidence:</span>
            <b>[${p.confidence_interval[0]}% - ${p.confidence_interval[1]}%]</b>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="color:#64748b;">Model Active:</span>
            <b>${p.model_used}</b>
          </div>
        </div>

        <button class="btn-primary" style="width:100%; justify-content:center;" onclick="openReservationWithPrediction('${date}', '${time}')">
          <i class="fas fa-magic"></i> Allocate Best Slots for this Forecast
        </button>
      </div>
    `;
  } catch (err) {
    resultContainer.innerHTML = '<p style="color:#ef4444; font-size:13px;">Error generating prediction.</p>';
  }
}

async function triggerModelRetrain() {
  const btn = document.getElementById('btnRetrainModel');
  if (btn) btn.disabled = true;
  showToast("Re-training all ML models (Random Forest, Gradient Boosting, Decision Tree, Ridge)...", "info");

  try {
    const res = await fetch('/api/ai/retrain', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'success') {
      showToast(data.message, "success");
      loadAiLabData();
    }
  } catch (err) {
    showToast("Error during model retraining", "danger");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function openReservationWithPrediction(date, time) {
  showTab('reservations');
  const dIn = document.getElementById('resDate');
  const tIn = document.getElementById('resTime');
  if (dIn) dIn.value = date;
  if (tIn) tIn.value = time;
  findAiRecommendations();
}



