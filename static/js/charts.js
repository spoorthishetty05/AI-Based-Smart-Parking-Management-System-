/**
 * Chart.js Integration for Smart Parking Dashboard
 * Renders Donut Summary & Hourly Occupancy Overview
 */

let summaryDonutChart = null;
let occupancyBarChart = null;

function initCharts(systemData) {
  const stats = systemData.stats || {};
  const hourlyData = systemData.hourly_overview || [];

  // 1. Donut Chart - Parking Summary
  const donutCtx = document.getElementById('parkingSummaryChart');
  if (donutCtx) {
    if (summaryDonutChart) summaryDonutChart.destroy();

    const avail = stats.available || 36;
    const occ = stats.occupied || 52;
    const res = stats.reserved || 18;
    const over = stats.overstayed || 4;

    summaryDonutChart = new Chart(donutCtx, {
      type: 'doughnut',
      data: {
        labels: ['Available', 'Occupied', 'Reserved', 'Overstayed'],
        datasets: [{
          data: [avail, occ, res, over],
          backgroundColor: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'],
          borderWidth: 2,
          borderColor: '#ffffff',
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        plugins: {
          legend: {
            position: 'right',
            labels: {
              boxWidth: 10,
              boxHeight: 10,
              usePointStyle: true,
              pointStyle: 'circle',
              font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' },
              color: '#475569',
              padding: 10,
              generateLabels: function(chart) {
                const data = chart.data;
                if (data.labels.length && data.datasets.length) {
                  return data.labels.map((label, i) => {
                    const val = data.datasets[0].data[i];
                    return {
                      text: `${label} (${val})`,
                      fillStyle: data.datasets[0].backgroundColor[i],
                      strokeStyle: data.datasets[0].backgroundColor[i],
                      lineWidth: 0,
                      hidden: isNaN(val),
                      index: i
                    };
                  });
                }
                return [];
              }
            }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                const total = avail + occ + res + over;
                const val = context.raw || 0;
                const pct = total ? ((val / total) * 100).toFixed(1) : 0;
                return ` ${context.label}: ${val} slots (${pct}%)`;
              }
            }
          }
        }
      }
    });
  }

  // 2. Bar Chart - Occupancy Overview
  const barCtx = document.getElementById('occupancyBarChart');
  if (barCtx) {
    if (occupancyBarChart) occupancyBarChart.destroy();

    const labels = hourlyData.map(d => d.label || `${d.hour}:00`);
    const values = hourlyData.map(d => d.occupancy_rate || 50);

    occupancyBarChart = new Chart(barCtx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Occupancy Rate (%)',
          data: values,
          backgroundColor: '#10b981',
          hoverBackgroundColor: '#059669',
          borderRadius: 6,
          borderSkipped: false,
          barThickness: 16
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#0f172a',
            titleFont: { family: 'Plus Jakarta Sans', size: 11, weight: '700' },
            bodyFont: { family: 'Plus Jakarta Sans', size: 12, weight: '600' },
            padding: 8,
            cornerRadius: 8,
            callbacks: {
              label: function(context) {
                return ` ${context.label} Occupancy: ${context.raw}%`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              font: { family: 'Plus Jakarta Sans', size: 10, weight: '600' },
              color: '#94a3b8'
            }
          },
          y: {
            min: 0,
            max: 100,
            ticks: {
              stepSize: 25,
              font: { family: 'Plus Jakarta Sans', size: 10, weight: '600' },
              color: '#94a3b8'
            },
            grid: {
              color: '#f1f5f9',
              drawBorder: false
            }
          }
        }
      }
    });
  }
}

function updateCharts(systemData) {
  const stats = systemData.stats || {};
  if (summaryDonutChart) {
    summaryDonutChart.data.datasets[0].data = [
      stats.available || 0,
      stats.occupied || 0,
      stats.reserved || 0,
      stats.overstayed || 0
    ];
    summaryDonutChart.update();
  }
}

// ==========================================
// EDA & ADVANCED ANALYTICS CHARTS
// ==========================================

let edaHourlyChartInstance = null;
let edaDayChartInstance = null;
let edaWeatherChartInstance = null;
let edaWeekdayWeekendChartInstance = null;
let reportTrendChartInstance = null;

function initEdaCharts(edaData) {
  if (!edaData) return;

  // 1. Hourly Occupancy Curve (24 Hours)
  const hourlyCtx = document.getElementById('edaHourlyCanvas');
  if (hourlyCtx && edaData.hourly_profile) {
    if (edaHourlyChartInstance) edaHourlyChartInstance.destroy();
    
    const hours = Array.from({ length: 24 }, (_, i) => i);
    const labels = hours.map(h => `${h}:00`);
    const values = hours.map(h => edaData.hourly_profile[h] ?? 50);

    edaHourlyChartInstance = new Chart(hourlyCtx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Avg Occupancy (%)',
          data: values,
          borderColor: '#0d9488',
          backgroundColor: 'rgba(13, 148, 136, 0.12)',
          fill: true,
          tension: 0.4,
          borderWidth: 2.5,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: '#0d9488'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` Occupancy: ${ctx.raw}%`
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#94a3b8' } },
          y: { min: 0, max: 100, ticks: { stepSize: 25, font: { size: 10 }, color: '#94a3b8' }, grid: { color: '#f1f5f9' } }
        }
      }
    });
  }

  // 2. Day of Week Profile
  const dayCtx = document.getElementById('edaDayCanvas');
  if (dayCtx && edaData.day_profile) {
    if (edaDayChartInstance) edaDayChartInstance.destroy();

    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    const values = days.map(d => edaData.day_profile[d] ?? 60);

    edaDayChartInstance = new Chart(dayCtx, {
      type: 'bar',
      data: {
        labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        datasets: [{
          label: 'Avg Occupancy (%)',
          data: values,
          backgroundColor: ['#3b82f6', '#3b82f6', '#3b82f6', '#3b82f6', '#0d9488', '#f59e0b', '#f59e0b'],
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#94a3b8' } },
          y: { min: 0, max: 100, ticks: { stepSize: 25, font: { size: 10 }, color: '#94a3b8' }, grid: { color: '#f1f5f9' } }
        }
      }
    });
  }

  // 3. Weather Impact Comparison
  const weatherCtx = document.getElementById('edaWeatherCanvas');
  if (weatherCtx && edaData.weather_impact) {
    if (edaWeatherChartInstance) edaWeatherChartInstance.destroy();

    const weathers = ['Clear', 'Cloudy', 'Rainy'];
    const values = weathers.map(w => edaData.weather_impact[w] ?? 50);

    edaWeatherChartInstance = new Chart(weatherCtx, {
      type: 'bar',
      data: {
        labels: ['Clear / Sunny', 'Cloudy', 'Rainy (Surge)'],
        datasets: [{
          data: values,
          backgroundColor: ['#10b981', '#64748b', '#3b82f6'],
          borderRadius: 6,
          barThickness: 28
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#94a3b8' } },
          y: { min: 0, max: 100, ticks: { stepSize: 25, font: { size: 10 }, color: '#94a3b8' }, grid: { color: '#f1f5f9' } }
        }
      }
    });
  }

  // 4. Weekday vs Weekend Comparison
  const compCtx = document.getElementById('edaComparisonCanvas');
  if (compCtx && edaData.weekday_hourly && edaData.weekend_hourly) {
    if (edaWeekdayWeekendChartInstance) edaWeekdayWeekendChartInstance.destroy();

    const hours = Array.from({ length: 24 }, (_, i) => i);
    const labels = hours.map(h => `${h}:00`);
    const weekdayVals = hours.map(h => edaData.weekday_hourly[h] ?? 50);
    const weekendVals = hours.map(h => edaData.weekend_hourly[h] ?? 40);

    edaWeekdayWeekendChartInstance = new Chart(compCtx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Weekday (Commuter Peak)',
            data: weekdayVals,
            borderColor: '#3b82f6',
            backgroundColor: 'transparent',
            tension: 0.35,
            borderWidth: 2.2,
            pointRadius: 2
          },
          {
            label: 'Weekend (Leisure Peak)',
            data: weekendVals,
            borderColor: '#f59e0b',
            backgroundColor: 'transparent',
            tension: 0.35,
            borderWidth: 2.2,
            pointRadius: 2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 10, font: { size: 11, weight: '600' } } }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#94a3b8' } },
          y: { min: 0, max: 100, ticks: { stepSize: 25, font: { size: 10 }, color: '#94a3b8' }, grid: { color: '#f1f5f9' } }
        }
      }
    });
  }
}

function initReportCharts(summaryData) {
  const trendCtx = document.getElementById('reportTrendCanvas');
  if (trendCtx) {
    if (reportTrendChartInstance) reportTrendChartInstance.destroy();

    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const rates = [64, 72, 79, 81, 88, 62, 58];

    reportTrendChartInstance = new Chart(trendCtx, {
      type: 'line',
      data: {
        labels: days,
        datasets: [{
          label: 'Daily Utilization (%)',
          data: rates,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.12)',
          fill: true,
          tension: 0.4,
          borderWidth: 2.5,
          pointRadius: 4,
          pointBackgroundColor: '#10b981'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false } },
          y: { min: 0, max: 100, ticks: { stepSize: 25 }, grid: { color: '#f1f5f9' } }
        }
      }
    });
  }
}

// ==========================================
// MODULE 6: PARKING DURATION & DWELL TIME CHARTS
// ==========================================

let edaDurationChartInstance = null;
let edaVehicleDurationChartInstance = null;

function initDurationCharts(durationData) {
  if (!durationData) return;

  // Update KPI Tiles
  const meanEl = document.getElementById('durationMeanVal');
  const turnoverEl = document.getElementById('durationTurnoverVal');
  const shortEl = document.getElementById('durationShortPctVal');
  const longEl = document.getElementById('durationLongPctVal');

  if (meanEl && durationData.mean_duration_hours) meanEl.textContent = `${durationData.mean_duration_hours} hrs`;
  if (turnoverEl && durationData.daily_turnover_rate) turnoverEl.textContent = `${durationData.daily_turnover_rate} / slot`;
  if (shortEl && durationData.short_stay_pct) shortEl.textContent = `${durationData.short_stay_pct}%`;
  if (longEl && durationData.long_stay_pct) longEl.textContent = `${durationData.long_stay_pct}%`;

  // 1. Duration Bracket Distribution Chart
  const distCtx = document.getElementById('edaDurationCanvas');
  if (distCtx && durationData.distribution) {
    if (edaDurationChartInstance) edaDurationChartInstance.destroy();

    const labels = Object.keys(durationData.distribution);
    const values = Object.values(durationData.distribution);

    edaDurationChartInstance = new Chart(distCtx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Percentage of Sessions (%)',
          data: values,
          backgroundColor: ['#10b981', '#0d9488', '#3b82f6', '#f59e0b', '#ef4444'],
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.raw}% of bookings`
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#94a3b8' } },
          y: { min: 0, max: 45, ticks: { stepSize: 10, font: { size: 10 }, color: '#94a3b8' }, grid: { color: '#f1f5f9' } }
        }
      }
    });
  }

  // 2. Avg Duration by Vehicle Type Chart
  const vehCtx = document.getElementById('edaVehicleDurationCanvas');
  if (vehCtx && durationData.by_vehicle_type) {
    if (edaVehicleDurationChartInstance) edaVehicleDurationChartInstance.destroy();

    const vLabels = Object.keys(durationData.by_vehicle_type);
    const vValues = Object.values(durationData.by_vehicle_type);

    edaVehicleDurationChartInstance = new Chart(vehCtx, {
      type: 'bar',
      data: {
        labels: vLabels,
        datasets: [{
          label: 'Average Hours',
          data: vValues,
          backgroundColor: ['#0d9488', '#3b82f6', '#6366f1', '#10b981', '#f59e0b'],
          borderRadius: 6,
          barThickness: 24
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` Avg Dwell: ${ctx.raw} hours`
            }
          }
        },
        scales: {
          x: { min: 0, max: 4, ticks: { stepSize: 1, font: { size: 10 }, color: '#94a3b8' }, grid: { color: '#f1f5f9' } },
          y: { grid: { display: false }, ticks: { font: { size: 11, weight: '600' }, color: '#334155' } }
        }
      }
    });
  }
}
