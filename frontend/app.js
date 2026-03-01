/**
 * app.js — Frontend logic for GreenQueue dashboard.
 *
 * Uses vanilla JS + Canvas API for charts (no libraries needed).
 * Talks to the FastAPI backend at /api/*.
 */

const API = "";  // same origin, no prefix needed

// ---------------------------------------------------------------------------
// Fetch current grid status
// ---------------------------------------------------------------------------
async function fetchCurrent() {
  try {
    const res = await fetch(`${API}/api/energy/current`);
    const data = await res.json();

    const el = document.getElementById("current-intensity");
    el.textContent = data.carbon_intensity;

    // Color-code based on intensity
    el.className = "big-number";
    if (data.carbon_intensity < 200) el.classList.add("intensity-low");
    else if (data.carbon_intensity < 350) el.classList.add("intensity-medium");
    else el.classList.add("intensity-high");

    // Energy mix chips
    const mixEl = document.getElementById("energy-mix");
    const sources = [
      ["☀️ Solar", data.solar_pct],
      ["💨 Wind", data.wind_pct],
      ["🔥 Gas", data.gas_pct],
      ["🪨 Coal", data.coal_pct],
      ["⚛️ Nuclear", data.nuclear_pct],
      ["💧 Hydro", data.hydro_pct],
    ];
    mixEl.innerHTML = sources
      .map(([label, val]) =>
        `<div class="mix-item"><span class="label">${label}</span> <span class="value">${val.toFixed(1)}%</span></div>`
      )
      .join("");
  } catch (err) {
    console.error("Failed to fetch current energy:", err);
  }
}

// ---------------------------------------------------------------------------
// Fetch and draw 24h forecast
// ---------------------------------------------------------------------------
async function fetchForecast() {
  const status = document.getElementById("forecast-status");
  status.textContent = "Loading forecast...";

  try {
    const res = await fetch(`${API}/api/forecast/next24h`);
    const data = await res.json();
    status.textContent = `Showing ${data.length} hourly predictions`;
    drawChart("forecast-chart", data.map(d => ({
      label: new Date(d.timestamp).getHours() + ":00",
      value: d.carbon_intensity,
    })));
  } catch (err) {
    status.textContent = "Error loading forecast. Train the model first?";
    console.error(err);
  }
}

// ---------------------------------------------------------------------------
// Train model
// ---------------------------------------------------------------------------
async function trainModel() {
  const status = document.getElementById("forecast-status");
  status.textContent = "Training model...";

  try {
    const res = await fetch(`${API}/api/forecast/train`, { method: "POST" });
    const data = await res.json();
    status.textContent = `Trained on ${data.rows_used} rows — MAE: ${data.mae} gCO₂/kWh`;
  } catch (err) {
    status.textContent = "Training failed.";
    console.error(err);
  }
}

// ---------------------------------------------------------------------------
// Fetch and draw history chart
// ---------------------------------------------------------------------------
async function fetchHistory() {
  try {
    const res = await fetch(`${API}/api/energy/history?limit=168`);
    const data = await res.json();
    // data comes newest-first, reverse it for the chart
    const reversed = data.reverse();
    drawChart("history-chart", reversed.map(d => ({
      label: new Date(d.timestamp).toLocaleDateString("en", { weekday: "short", hour: "numeric" }),
      value: d.carbon_intensity,
    })));
  } catch (err) {
    console.error("Failed to fetch history:", err);
  }
}

// ---------------------------------------------------------------------------
// Simple canvas bar/line chart (no libraries needed)
// ---------------------------------------------------------------------------
function drawChart(canvasId, points) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");

  // High-DPI support
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const W = rect.width;
  const H = rect.height;
  const PAD = { top: 20, right: 20, bottom: 40, left: 50 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const values = points.map(p => p.value);
  const minVal = Math.min(...values) * 0.9;
  const maxVal = Math.max(...values) * 1.1;

  // Clear
  ctx.clearRect(0, 0, W, H);

  // Y-axis labels
  ctx.fillStyle = "#64748b";
  ctx.font = "11px sans-serif";
  ctx.textAlign = "right";
  for (let i = 0; i <= 4; i++) {
    const val = minVal + (maxVal - minVal) * (i / 4);
    const y = PAD.top + plotH - (plotH * (i / 4));
    ctx.fillText(Math.round(val), PAD.left - 8, y + 4);
    // Grid line
    ctx.strokeStyle = "#1e293b";
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(W - PAD.right, y);
    ctx.stroke();
  }

  // Draw filled area + line
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = PAD.left + (i / (points.length - 1)) * plotW;
    const y = PAD.top + plotH - ((p.value - minVal) / (maxVal - minVal)) * plotH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });

  // Fill under the line
  const lastX = PAD.left + plotW;
  ctx.lineTo(lastX, PAD.top + plotH);
  ctx.lineTo(PAD.left, PAD.top + plotH);
  ctx.closePath();
  ctx.fillStyle = "rgba(74, 222, 128, 0.15)";
  ctx.fill();

  // Draw the line itself
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = PAD.left + (i / (points.length - 1)) * plotW;
    const y = PAD.top + plotH - ((p.value - minVal) / (maxVal - minVal)) * plotH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#4ade80";
  ctx.lineWidth = 2;
  ctx.stroke();

  // X-axis labels (show every Nth)
  const step = Math.max(1, Math.floor(points.length / 8));
  ctx.fillStyle = "#64748b";
  ctx.textAlign = "center";
  ctx.font = "10px sans-serif";
  for (let i = 0; i < points.length; i += step) {
    const x = PAD.left + (i / (points.length - 1)) * plotW;
    ctx.fillText(points[i].label, x, H - PAD.bottom + 20);
  }
}

// ---------------------------------------------------------------------------
// Load current data on page load
// ---------------------------------------------------------------------------
fetchCurrent();
