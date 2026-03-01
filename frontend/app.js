/* ================================================================
   GreenQueue — Interactive Frontend
   Intro animation · Hover tooltips · Chart entry animations
   ================================================================ */

const API = '/api';

/* ══════════════════════════════════════════════════════
   1. INTRO TYPING ANIMATION
   ══════════════════════════════════════════════════════ */
(function introAnimation() {
    const overlay = document.getElementById('intro-overlay');
    if (!overlay) return;

    // Skip if already seen this page load (only via flag, not sessionStorage)
    if (window._introPlayed) {
        overlay.classList.add('hidden');
        initApp();
        return;
    }

    const titleEl = document.getElementById('intro-title');
    const subEl   = document.getElementById('intro-subtitle');
    const text    = 'GreenQueue';
    let i = 0;

    // Create a cursor span
    const cursor = document.createElement('span');
    cursor.className = 'cursor';

    titleEl.textContent = '';
    titleEl.appendChild(cursor);

    function typeNext() {
        if (i < text.length) {
            titleEl.insertBefore(document.createTextNode(text[i]), cursor);
            i++;
            setTimeout(typeNext, 110);
        } else {
            // Typing done — show subtitle
            setTimeout(() => subEl.classList.add('visible'), 200);
            // Fade out overlay
            setTimeout(() => {
                cursor.style.display = 'none';
                overlay.classList.add('fade-out');
                window._introPlayed = true;
                setTimeout(() => {
                    overlay.classList.add('hidden');
                    initApp();
                }, 700);
            }, 1600);
        }
    }

    setTimeout(typeNext, 400);
})();


/* ══════════════════════════════════════════════════════
   2. TOOLTIP SYSTEM
   ══════════════════════════════════════════════════════ */
const tooltipEl = document.getElementById('chart-tooltip');

function showTooltip(html, x, y) {
    tooltipEl.innerHTML = html;
    tooltipEl.classList.add('visible');
    // Position — keep on screen
    const tw = tooltipEl.offsetWidth;
    const th = tooltipEl.offsetHeight;
    let tx = x + 14;
    let ty = y - th / 2;
    if (tx + tw > window.innerWidth - 12) tx = x - tw - 14;
    if (ty < 8) ty = 8;
    if (ty + th > window.innerHeight - 8) ty = window.innerHeight - th - 8;
    tooltipEl.style.left = tx + 'px';
    tooltipEl.style.top = ty + 'px';
}

function hideTooltip() {
    tooltipEl.classList.remove('visible');
}

/* ══════════════════════════════════════════════════════
   3. CHART REGISTRY (stores point data for hit-testing)
   ══════════════════════════════════════════════════════ */
const chartRegistry = new Map(); // canvas -> { type, data, ... }


/* ══════════════════════════════════════════════════════
   4. CORE APP LOGIC
   ══════════════════════════════════════════════════════ */
function initApp() {
    loadDashboard();
}

// ── Navigation ─────────────────────────────────────────
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        showPage(link.dataset.page);
    });
});

function showPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    const pageEl = document.getElementById(`page-${name}`);
    const linkEl = document.querySelector(`.nav-link[data-page="${name}"]`);
    if (pageEl) pageEl.classList.add('active');
    if (linkEl) linkEl.classList.add('active');

    // Play subtitle typing animation only on first visit, then keep static
    const sub = pageEl?.querySelector('.page-subtitle');
    if (sub && !sub.dataset.played) {
        sub.dataset.played = '1';
    } else if (sub && sub.dataset.played) {
        sub.style.animation = 'none';
        sub.style.maxWidth = '600px';
        sub.style.borderRight = 'none';
    }

    if (name === 'dashboard') loadDashboard();
    else if (name === 'job-schedule') loadJobSchedule();
    else if (name === 'impact') loadImpact();
}

// ── Toast ──────────────────────────────────────────────
function toast(msg, type = 'info') {
    const c = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = msg;
    c.appendChild(el);
    setTimeout(() => el.remove(), 3200);
}

// ── API Helper ─────────────────────────────────────────
async function api(path, opts = {}) {
    try {
        const res = await fetch(`${API}${path}`, {
            headers: { 'Content-Type': 'application/json' }, ...opts,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (err) {
        toast(`Request failed: ${err.message}`, 'error');
        throw err;
    }
}

// ── Animated Number Counter ────────────────────────────
function animateValue(el, end, duration = 600, suffix = '') {
    const start = parseFloat(el.textContent) || 0;
    if (start === end) { el.textContent = end + suffix; return; }
    const t0 = performance.now();
    function step(now) {
        const p = Math.min((now - t0) / duration, 1);
        const e = 1 - Math.pow(1 - p, 3);
        el.textContent = (Math.round((start + (end - start) * e) * 10) / 10) + suffix;
        if (p < 1) requestAnimationFrame(step);
        else { el.textContent = end + suffix; el.classList.add('count-animate'); setTimeout(() => el.classList.remove('count-animate'), 300); }
    }
    requestAnimationFrame(step);
}


/* ══════════════════════════════════════════════════════
   5. CANVAS HELPERS
   ══════════════════════════════════════════════════════ */
const COLORS = {
    green: '#10b981', greenLt: '#34d399', accent: '#6366f1', accentLt: '#818cf8',
    red: '#f87171', amber: '#fbbf24', blue: '#60a5fa', text: '#e2e8f0',
    muted: '#5a6e8f', grid: '#1e293b', surface: '#1a2234',
};

function setupCanvas(canvas) {
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    return { ctx, w: rect.width, h: rect.height };
}

function drawGrid(ctx, w, h, pad, rows = 4) {
    ctx.strokeStyle = COLORS.grid; ctx.lineWidth = 0.5;
    for (let i = 0; i <= rows; i++) {
        const y = pad.top + (i / rows) * (h - pad.top - pad.bottom);
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w - pad.right, y); ctx.stroke();
    }
}

function roundedRect(ctx, x, y, w, h, r) {
    if (h <= 0) return;
    r = Math.min(r, w / 2, h / 2);
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h);
    ctx.lineTo(x, y + h);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
}


/* ══════════════════════════════════════════════════════
   6. ANIMATED AREA/LINE CHART (with hover)
   ══════════════════════════════════════════════════════ */
function drawAreaChart(canvas, data, { color = COLORS.green, label = '', showDots = false, xLabel = '', yLabel = '' } = {}) {
    if (!data.length) return;
    const { ctx, w, h } = setupCanvas(canvas);
    const pad = { top: 20, right: 16, bottom: 44, left: 58 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;

    const maxVal = Math.max(...data.map(d => d.y)) * 1.1 || 1;
    const minVal = Math.min(0, Math.min(...data.map(d => d.y)));

    // Build points array
    const points = data.map((d, i) => ({
        px: pad.left + (i / Math.max(data.length - 1, 1)) * cw,
        py: pad.top + (1 - (d.y - minVal) / (maxVal - minVal)) * ch,
        x: d.x, y: d.y,
    }));

    // Register for tooltip
    chartRegistry.set(canvas, { type: 'area', points, color, pad, cw, ch, w, h, maxVal, minVal, label, showDots, xLabel, yLabel });

    // Animate: progressive reveal left-to-right
    const duration = 800;
    const t0 = performance.now();

    function frame(now) {
        const progress = Math.min((now - t0) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const clipX = pad.left + cw * eased;

        ctx.clearRect(0, 0, w, h);
        ctx.save();

        drawGrid(ctx, w, h, pad);

        // Y-axis labels
        ctx.fillStyle = COLORS.muted; ctx.font = '10px Inter, sans-serif'; ctx.textAlign = 'right';
        for (let i = 0; i <= 4; i++) {
            const val = minVal + (maxVal - minVal) * (1 - i / 4);
            ctx.fillText(Math.round(val), pad.left - 8, pad.top + (i / 4) * ch + 3);
        }
        // X-axis labels
        ctx.textAlign = 'center';
        const step = Math.max(1, Math.floor(data.length / 8));
        for (let i = 0; i < data.length; i += step) {
            const x = pad.left + (i / Math.max(data.length - 1, 1)) * cw;
            if (x <= clipX) ctx.fillText(data[i].x || '', x, h - 8);
        }

        // Clip to animated region
        ctx.beginPath();
        ctx.rect(0, 0, clipX, h);
        ctx.clip();

        // Fill area
        ctx.beginPath();
        ctx.moveTo(points[0].px, points[0].py);
        for (let i = 1; i < points.length; i++) {
            const xc = (points[i - 1].px + points[i].px) / 2;
            const yc = (points[i - 1].py + points[i].py) / 2;
            ctx.quadraticCurveTo(points[i - 1].px, points[i - 1].py, xc, yc);
        }
        ctx.lineTo(points[points.length - 1].px, points[points.length - 1].py);
        ctx.lineTo(points[points.length - 1].px, pad.top + ch);
        ctx.lineTo(points[0].px, pad.top + ch);
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
        grad.addColorStop(0, color + '30');
        grad.addColorStop(1, color + '05');
        ctx.fillStyle = grad;
        ctx.fill();

        // Line
        ctx.beginPath();
        ctx.moveTo(points[0].px, points[0].py);
        for (let i = 1; i < points.length; i++) {
            const xc = (points[i - 1].px + points[i].px) / 2;
            const yc = (points[i - 1].py + points[i].py) / 2;
            ctx.quadraticCurveTo(points[i - 1].px, points[i - 1].py, xc, yc);
        }
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Dots
        if (showDots) {
            points.forEach(p => {
                if (p.px > clipX) return;
                ctx.beginPath(); ctx.arc(p.px, p.py, 3.5, 0, Math.PI * 2);
                ctx.fillStyle = color; ctx.fill();
                ctx.strokeStyle = COLORS.surface; ctx.lineWidth = 1.5; ctx.stroke();
            });
        }

        // Axis labels
        if (yLabel) {
            ctx.save();
            ctx.fillStyle = COLORS.muted; ctx.font = 'bold 10px Inter, sans-serif'; ctx.textAlign = 'center';
            ctx.translate(12, pad.top + ch / 2);
            ctx.rotate(-Math.PI / 2);
            ctx.fillText(yLabel, 0, 0);
            ctx.restore();
        }
        if (xLabel) {
            ctx.fillStyle = COLORS.muted; ctx.font = 'bold 10px Inter, sans-serif'; ctx.textAlign = 'center';
            ctx.fillText(xLabel, pad.left + cw / 2, h - 1);
        }

        ctx.restore();

        if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    // Attach hover listener (once)
    attachAreaHover(canvas);
}

function attachAreaHover(canvas) {
    if (canvas._hoverAttached) return;
    canvas._hoverAttached = true;

    canvas.addEventListener('mousemove', e => {
        const reg = chartRegistry.get(canvas);
        if (!reg || reg.type !== 'area') return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;

        // Find closest point
        let closest = null, minDist = Infinity;
        for (const p of reg.points) {
            const d = Math.abs(p.px - mx);
            if (d < minDist) { minDist = d; closest = p; }
        }
        if (!closest || minDist > 40) { hideTooltip(); redrawAreaStatic(canvas); return; }

        // Redraw with crosshair + highlighted dot
        redrawAreaStatic(canvas);
        const ctx = canvas.getContext('2d');
        ctx.save();

        // Vertical crosshair
        ctx.strokeStyle = COLORS.muted + '60'; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
        ctx.beginPath(); ctx.moveTo(closest.px, reg.pad.top); ctx.lineTo(closest.px, reg.pad.top + reg.ch); ctx.stroke();
        ctx.setLineDash([]);

        // Highlight dot
        ctx.beginPath(); ctx.arc(closest.px, closest.py, 5, 0, Math.PI * 2);
        ctx.fillStyle = reg.color; ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();

        ctx.restore();

        showTooltip(
            `<div class="tt-label">${closest.x}</div><div class="tt-value" style="color:${reg.color}">${closest.y.toFixed(1)} ${reg.yLabel || 'gCO\u2082/kWh'}</div>`,
            e.clientX, e.clientY
        );
    });

    canvas.addEventListener('mouseleave', () => {
        hideTooltip();
        redrawAreaStatic(canvas);
    });
}

/** Redraw area chart without animation (for hover updates) */
function redrawAreaStatic(canvas) {
    const reg = chartRegistry.get(canvas);
    if (!reg || reg.type !== 'area') return;
    const { points, color, pad, cw, ch, w, h, maxVal, minVal, label, showDots, xLabel, yLabel } = reg;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    ctx.save();

    drawGrid(ctx, w, h, pad);

    ctx.fillStyle = COLORS.muted; ctx.font = '10px Inter, sans-serif'; ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {
        const val = minVal + (maxVal - minVal) * (1 - i / 4);
        ctx.fillText(Math.round(val), pad.left - 8, pad.top + (i / 4) * ch + 3);
    }
    ctx.textAlign = 'center';
    const step = Math.max(1, Math.floor(points.length / 8));
    for (let i = 0; i < points.length; i += step) {
        ctx.fillText(points[i].x || '', points[i].px, h - 8);
    }

    // Fill
    ctx.beginPath(); ctx.moveTo(points[0].px, points[0].py);
    for (let i = 1; i < points.length; i++) {
        const xc = (points[i - 1].px + points[i].px) / 2;
        const yc = (points[i - 1].py + points[i].py) / 2;
        ctx.quadraticCurveTo(points[i - 1].px, points[i - 1].py, xc, yc);
    }
    ctx.lineTo(points[points.length - 1].px, points[points.length - 1].py);
    ctx.lineTo(points[points.length - 1].px, pad.top + ch);
    ctx.lineTo(points[0].px, pad.top + ch);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
    grad.addColorStop(0, color + '30'); grad.addColorStop(1, color + '05');
    ctx.fillStyle = grad; ctx.fill();

    // Line
    ctx.beginPath(); ctx.moveTo(points[0].px, points[0].py);
    for (let i = 1; i < points.length; i++) {
        const xc = (points[i - 1].px + points[i].px) / 2;
        const yc = (points[i - 1].py + points[i].py) / 2;
        ctx.quadraticCurveTo(points[i - 1].px, points[i - 1].py, xc, yc);
    }
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();

    if (showDots) {
        points.forEach(p => {
            ctx.beginPath(); ctx.arc(p.px, p.py, 3.5, 0, Math.PI * 2);
            ctx.fillStyle = color; ctx.fill();
            ctx.strokeStyle = COLORS.surface; ctx.lineWidth = 1.5; ctx.stroke();
        });
    }
    // Axis labels
    if (yLabel) {
        ctx.save();
        ctx.fillStyle = COLORS.muted; ctx.font = 'bold 10px Inter, sans-serif'; ctx.textAlign = 'center';
        ctx.translate(12, pad.top + ch / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(yLabel, 0, 0);
        ctx.restore();
    }
    if (xLabel) {
        ctx.fillStyle = COLORS.muted; ctx.font = 'bold 10px Inter, sans-serif'; ctx.textAlign = 'center';
        ctx.fillText(xLabel, pad.left + cw / 2, h - 1);
    }
    ctx.restore();
}


/* ══════════════════════════════════════════════════════
   6b. FORECAST vs ACTUAL DUAL-LINE CHART
   ══════════════════════════════════════════════════════ */
function drawForecastChart(canvas, actuals, forecast, { yLabel = '' } = {}) {
    if (!forecast.length) return;
    const { ctx, w, h } = setupCanvas(canvas);
    const pad = { top: 20, right: 16, bottom: 44, left: 58 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;

    const colorActual = COLORS.accent;
    const colorForecast = COLORS.green;

    // Build unified x-axis: actuals then forecast
    // Format hour labels
    function fmtHour(ts) {
        const d = new Date(ts);
        let hr = d.getHours(); const ampm = hr >= 12 ? 'pm' : 'am';
        hr = hr % 12 || 12;
        return `${hr} ${ampm}`;
    }

    const actualPts = actuals.map(a => ({ x: fmtHour(a.timestamp), y: a.carbon_intensity, type: 'actual' }));
    const forecastPts = forecast.map(f => ({ x: fmtHour(f.timestamp), y: f.carbon_intensity, type: 'forecast' }));

    // The last actual point and first forecast point should connect visually
    // so we duplicate the last actual as the start of the forecast series
    const allPts = [...actualPts, ...forecastPts];
    const dividerIdx = actualPts.length; // index where forecast starts

    const allY = allPts.map(p => p.y);
    const maxVal = Math.max(...allY) * 1.1 || 1;
    const minVal = Math.min(0, Math.min(...allY));

    // Compute pixel positions
    const points = allPts.map((d, i) => ({
        px: pad.left + (i / Math.max(allPts.length - 1, 1)) * cw,
        py: pad.top + (1 - (d.y - minVal) / (maxVal - minVal)) * ch,
        x: d.x, y: d.y, type: d.type,
    }));

    const dividerX = dividerIdx > 0 ? (points[dividerIdx - 1].px + points[dividerIdx].px) / 2 : pad.left;

    // Register for hover
    chartRegistry.set(canvas, {
        type: 'forecast', points, colorActual, colorForecast,
        pad, cw, ch, w, h, maxVal, minVal, dividerX, yLabel,
    });

    // Animate
    const duration = 800;
    const t0 = performance.now();

    function frame(now) {
        const progress = Math.min((now - t0) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const clipX = pad.left + cw * eased;

        ctx.clearRect(0, 0, w, h);
        ctx.save();
        drawGrid(ctx, w, h, pad);

        // Y-axis labels
        ctx.fillStyle = COLORS.muted; ctx.font = '10px Inter, sans-serif'; ctx.textAlign = 'right';
        for (let i = 0; i <= 4; i++) {
            const val = minVal + (maxVal - minVal) * (1 - i / 4);
            ctx.fillText(Math.round(val), pad.left - 8, pad.top + (i / 4) * ch + 3);
        }
        // X-axis labels
        ctx.textAlign = 'center';
        const step = Math.max(1, Math.floor(allPts.length / 8));
        for (let i = 0; i < allPts.length; i += step) {
            const x = points[i].px;
            if (x <= clipX) ctx.fillText(allPts[i].x || '', x, h - 8);
        }

        // Clip to animated region
        ctx.beginPath(); ctx.rect(0, 0, clipX, h); ctx.clip();

        // "Now" divider line
        if (dividerX <= clipX) {
            ctx.save();
            ctx.strokeStyle = COLORS.muted + '80';
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 3]);
            ctx.beginPath();
            ctx.moveTo(dividerX, pad.top);
            ctx.lineTo(dividerX, pad.top + ch);
            ctx.stroke();
            ctx.setLineDash([]);
            // "Now" label
            ctx.fillStyle = COLORS.muted;
            ctx.font = 'bold 9px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('NOW', dividerX, pad.top - 6);
            ctx.restore();
        }

        // ── Draw actual line (solid, with fill) ──
        const actPts = points.filter(p => p.type === 'actual');
        if (actPts.length > 1) {
            // Fill
            ctx.beginPath();
            ctx.moveTo(actPts[0].px, actPts[0].py);
            for (let i = 1; i < actPts.length; i++) {
                const xc = (actPts[i - 1].px + actPts[i].px) / 2;
                const yc = (actPts[i - 1].py + actPts[i].py) / 2;
                ctx.quadraticCurveTo(actPts[i - 1].px, actPts[i - 1].py, xc, yc);
            }
            ctx.lineTo(actPts[actPts.length - 1].px, actPts[actPts.length - 1].py);
            ctx.lineTo(actPts[actPts.length - 1].px, pad.top + ch);
            ctx.lineTo(actPts[0].px, pad.top + ch);
            ctx.closePath();
            const gA = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
            gA.addColorStop(0, colorActual + '25');
            gA.addColorStop(1, colorActual + '03');
            ctx.fillStyle = gA;
            ctx.fill();

            // Solid line
            ctx.beginPath();
            ctx.moveTo(actPts[0].px, actPts[0].py);
            for (let i = 1; i < actPts.length; i++) {
                const xc = (actPts[i - 1].px + actPts[i].px) / 2;
                const yc = (actPts[i - 1].py + actPts[i].py) / 2;
                ctx.quadraticCurveTo(actPts[i - 1].px, actPts[i - 1].py, xc, yc);
            }
            ctx.strokeStyle = colorActual;
            ctx.lineWidth = 2.5;
            ctx.stroke();

            // Dots
            actPts.forEach(p => {
                ctx.beginPath(); ctx.arc(p.px, p.py, 3.5, 0, Math.PI * 2);
                ctx.fillStyle = colorActual; ctx.fill();
                ctx.strokeStyle = COLORS.surface; ctx.lineWidth = 1.5; ctx.stroke();
            });
        }

        // ── Draw forecast line (with fill) ──
        // Start the forecast from the last actual point for continuity
        const fcStart = actPts.length ? [actPts[actPts.length - 1]] : [];
        const fcPts = [...fcStart, ...points.filter(p => p.type === 'forecast')];
        if (fcPts.length > 1) {
            // Fill
            ctx.beginPath();
            ctx.moveTo(fcPts[0].px, fcPts[0].py);
            for (let i = 1; i < fcPts.length; i++) {
                const xc = (fcPts[i - 1].px + fcPts[i].px) / 2;
                const yc = (fcPts[i - 1].py + fcPts[i].py) / 2;
                ctx.quadraticCurveTo(fcPts[i - 1].px, fcPts[i - 1].py, xc, yc);
            }
            ctx.lineTo(fcPts[fcPts.length - 1].px, fcPts[fcPts.length - 1].py);
            ctx.lineTo(fcPts[fcPts.length - 1].px, pad.top + ch);
            ctx.lineTo(fcPts[0].px, pad.top + ch);
            ctx.closePath();
            const gF = ctx.createLinearGradient(0, pad.top, 0, pad.top + ch);
            gF.addColorStop(0, colorForecast + '25');
            gF.addColorStop(1, colorForecast + '03');
            ctx.fillStyle = gF;
            ctx.fill();

            // Solid line
            ctx.beginPath();
            ctx.moveTo(fcPts[0].px, fcPts[0].py);
            for (let i = 1; i < fcPts.length; i++) {
                const xc = (fcPts[i - 1].px + fcPts[i].px) / 2;
                const yc = (fcPts[i - 1].py + fcPts[i].py) / 2;
                ctx.quadraticCurveTo(fcPts[i - 1].px, fcPts[i - 1].py, xc, yc);
            }
            ctx.strokeStyle = colorForecast;
            ctx.lineWidth = 2;
            ctx.stroke();
        }

        // Y-axis label
        if (yLabel) {
            ctx.save();
            ctx.fillStyle = COLORS.muted; ctx.font = 'bold 10px Inter, sans-serif'; ctx.textAlign = 'center';
            ctx.translate(12, pad.top + ch / 2);
            ctx.rotate(-Math.PI / 2);
            ctx.fillText(yLabel, 0, 0);
            ctx.restore();
        }

        // Legend (top-right)
        ctx.save();
        const legendX = w - pad.right - 160;
        const legendY = pad.top + 4;
        ctx.font = '10px Inter, sans-serif';
        // Actual
        ctx.fillStyle = colorActual;
        ctx.fillRect(legendX, legendY, 14, 3);
        ctx.fillStyle = COLORS.text;
        ctx.textAlign = 'left';
        ctx.fillText('Actual', legendX + 20, legendY + 4);
        // Forecast
        ctx.fillStyle = colorForecast;
        ctx.fillRect(legendX + 75, legendY, 14, 3);
        ctx.fillStyle = COLORS.text;
        ctx.fillText('Forecast', legendX + 95, legendY + 4);
        ctx.restore();

        ctx.restore();
        if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    // Hover
    attachForecastHover(canvas);
}

function attachForecastHover(canvas) {
    if (canvas._hoverAttached) return;
    canvas._hoverAttached = true;

    canvas.addEventListener('mousemove', e => {
        const reg = chartRegistry.get(canvas);
        if (!reg || reg.type !== 'forecast') return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;

        let closest = null, minDist = Infinity;
        for (const p of reg.points) {
            const d = Math.abs(p.px - mx);
            if (d < minDist) { minDist = d; closest = p; }
        }
        if (!closest || minDist > 40) { hideTooltip(); return; }

        const tag = closest.type === 'actual' ? 'Actual' : 'Forecast';
        const color = closest.type === 'actual' ? reg.colorActual : reg.colorForecast;
        showTooltip(
            `<div class="tt-label">${closest.x} · ${tag}</div><div class="tt-value" style="color:${color}">${closest.y.toFixed(1)} gCO₂/kWh</div>`,
            e.clientX, e.clientY
        );
    });

    canvas.addEventListener('mouseleave', hideTooltip);
}


/* ══════════════════════════════════════════════════════
   7. ANIMATED DONUT CHART (with hover)
   ══════════════════════════════════════════════════════ */
function drawDonut(canvas, segments) {
    if (!segments.length) return;
    const { ctx, w, h } = setupCanvas(canvas);
    const cx = w * 0.4, cy = h / 2;
    const outer = Math.min(cx, cy) - 20;
    const inner = outer * 0.6;
    const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;

    // Pre-calculate angles
    let cum = -Math.PI / 2;
    const arcs = segments.map(seg => {
        const start = cum;
        const sweep = (seg.value / total) * Math.PI * 2;
        cum += sweep;
        return { ...seg, startAngle: start, endAngle: start + sweep };
    });

    chartRegistry.set(canvas, { type: 'donut', arcs, cx, cy, outer, inner, total, w, h });

    // Animate: sweep from 0 to full
    const duration = 700;
    const t0 = performance.now();

    function frame(now) {
        const progress = Math.min((now - t0) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const sweepLimit = eased * Math.PI * 2;

        ctx.clearRect(0, 0, w, h);
        ctx.save();

        let cumAngle = -Math.PI / 2;
        arcs.forEach(arc => {
            const sweep = (arc.value / total) * Math.PI * 2;
            const visibleSweep = Math.min(sweep, Math.max(0, sweepLimit - (cumAngle + Math.PI / 2)));
            if (visibleSweep <= 0) { cumAngle += sweep; return; }

            ctx.beginPath();
            ctx.arc(cx, cy, outer, cumAngle, cumAngle + visibleSweep);
            ctx.arc(cx, cy, inner, cumAngle + visibleSweep, cumAngle, true);
            ctx.closePath();
            ctx.fillStyle = arc.color;
            ctx.fill();
            cumAngle += sweep;
        });

        // Center text (always)
        ctx.fillStyle = COLORS.text; ctx.font = 'bold 20px Inter, sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('100%', cx, cy - 6);
        ctx.font = '10px Inter, sans-serif'; ctx.fillStyle = COLORS.muted;
        ctx.fillText('Total', cx, cy + 12);

        // Legend — centred vertically in right half
        const legendItemH = 28;
        const totalLegendH = arcs.length * legendItemH;
        const legendX = w * 0.68;
        let legendY = (h - totalLegendH) / 2;
        ctx.textAlign = 'left';
        arcs.forEach(arc => {
            ctx.fillStyle = arc.color;
            ctx.fillRect(legendX, legendY + 2, 12, 12);
            ctx.fillStyle = COLORS.text; ctx.font = 'bold 13px Inter, sans-serif';
            ctx.fillText(`${arc.label}  ${arc.value.toFixed(1)}%`, legendX + 20, legendY + 12);
            legendY += legendItemH;
        });

        ctx.restore();
        if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    attachDonutHover(canvas);
}

function attachDonutHover(canvas) {
    if (canvas._hoverAttached) return;
    canvas._hoverAttached = true;

    canvas.addEventListener('mousemove', e => {
        const reg = chartRegistry.get(canvas);
        if (!reg || reg.type !== 'donut') return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const dx = mx - reg.cx, dy = my - reg.cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < reg.inner || dist > reg.outer) { hideTooltip(); return; }

        let angle = Math.atan2(dy, dx);
        if (angle < -Math.PI / 2) angle += Math.PI * 2;

        const hit = reg.arcs.find(a => angle >= a.startAngle && angle < a.endAngle);
        if (!hit) { hideTooltip(); return; }

        showTooltip(
            `<div class="tt-row"><div class="tt-dot" style="background:${hit.color}"></div><span>${hit.label}</span></div><div class="tt-value">${hit.value.toFixed(1)}%</div>`,
            e.clientX, e.clientY
        );
    });

    canvas.addEventListener('mouseleave', hideTooltip);
}


/* ══════════════════════════════════════════════════════
   8. ANIMATED GROUPED BAR CHART (with hover)
   ══════════════════════════════════════════════════════ */
function drawGroupedBars(canvas, data, { colors = [COLORS.accent, COLORS.green], labels = ['Naive', 'Smart'] } = {}) {
    if (!data.length) return;
    const { ctx, w, h } = setupCanvas(canvas);
    const pad = { top: 36, right: 16, bottom: 44, left: 58 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;
    const maxVal = Math.max(...data.flatMap(d => [d.v1, d.v2])) * 1.15 || 1;
    const n = data.length;
    const groupW = cw / n;
    const barW = Math.min(groupW * 0.3, 48);
    const gap = groupW * 0.1;

    // Strip any alpha suffix to base 7-char hex for consistent gradient building
    function baseHex(c) { return c.length > 7 ? c.slice(0, 7) : c; }

    // Pre-calculate bar positions
    const bars = [];
    data.forEach((d, i) => {
        const gx = pad.left + i * groupW + groupW / 2;
        bars.push(
            { x: gx - barW - gap / 2, fullH: (d.v1 / maxVal) * ch, baseColor: baseHex(colors[0]), label: d.label, value: d.v1, group: labels[0] },
            { x: gx + gap / 2,        fullH: (d.v2 / maxVal) * ch, baseColor: baseHex(colors[1]), label: d.label, value: d.v2, group: labels[1] }
        );
    });

    chartRegistry.set(canvas, { type: 'bars', bars, barW, pad, ch, cw, w, h, maxVal, colors: colors.map(baseHex), labels, data });

    // Animate: bars grow from bottom
    const duration = 700;
    const t0 = performance.now();

    function frame(now) {
        const progress = Math.min((now - t0) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);

        ctx.clearRect(0, 0, w, h);
        ctx.save();

        drawGrid(ctx, w, h, pad);

        // Y labels
        ctx.fillStyle = COLORS.muted; ctx.font = '10px Inter, sans-serif'; ctx.textAlign = 'right';
        for (let i = 0; i <= 4; i++) {
            ctx.fillText(Math.round(maxVal * (1 - i / 4)), pad.left - 8, pad.top + (i / 4) * ch + 3);
        }

        bars.forEach(b => {
            const bh = b.fullH * eased;
            if (bh <= 0) return;

            // Gradient fill (matches dashboard region-bar style)
            const grad = ctx.createLinearGradient(0, pad.top + ch - bh, 0, pad.top + ch);
            grad.addColorStop(0, b.baseColor);
            grad.addColorStop(1, b.baseColor + '88');
            ctx.fillStyle = grad;

            // Subtle glow
            ctx.shadowColor = b.baseColor + '60';
            ctx.shadowBlur = 6;

            ctx.beginPath();
            roundedRect(ctx, b.x, pad.top + ch - bh, barW, bh, 4);
            ctx.fill();

            ctx.shadowColor = 'transparent';
            ctx.shadowBlur = 0;
        });

        // X labels
        ctx.fillStyle = COLORS.muted; ctx.font = '9px Inter, sans-serif'; ctx.textAlign = 'center';
        data.forEach((d, i) => {
            const gx = pad.left + i * groupW + groupW / 2;
            const lbl = d.label.length > 12 ? d.label.slice(0, 12) + '..' : d.label;
            ctx.fillText(lbl, gx, h - 8);
        });

        // Y-axis label
        ctx.save();
        ctx.fillStyle = COLORS.muted; ctx.font = 'bold 10px Inter, sans-serif'; ctx.textAlign = 'center';
        ctx.translate(12, pad.top + ch / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('gCO\u2082/kWh', 0, 0);
        ctx.restore();

        // Legend (top-right, matches dashboard forecast chart style)
        ctx.save();
        const legendX = w - pad.right - 220;
        const legendY = 10;
        ctx.font = '10px Inter, sans-serif';
        labels.forEach((lbl, i) => {
            const lx = legendX + i * 130;
            ctx.fillStyle = baseHex(colors[i]);
            ctx.fillRect(lx, legendY, 14, 4);
            ctx.fillStyle = COLORS.text;
            ctx.textAlign = 'left';
            ctx.fillText(lbl, lx + 20, legendY + 5);
        });
        ctx.restore();

        ctx.restore();
        if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    attachBarHover(canvas);
}

function attachBarHover(canvas) {
    if (canvas._hoverAttached) return;
    canvas._hoverAttached = true;

    canvas.addEventListener('mousemove', e => {
        const reg = chartRegistry.get(canvas);
        if (!reg || reg.type !== 'bars') return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const hit = reg.bars.find(b => mx >= b.x && mx <= b.x + reg.barW && my >= reg.pad.top + reg.ch - b.fullH && my <= reg.pad.top + reg.ch);

        if (!hit) { hideTooltip(); return; }

        showTooltip(
            `<div class="tt-label">${hit.label}</div><div class="tt-row"><div class="tt-dot" style="background:${hit.baseColor}"></div><span>${hit.group}</span></div><div class="tt-value">${hit.value.toFixed(1)} gCO\u2082/kWh</div>`,
            e.clientX, e.clientY
        );
    });

    canvas.addEventListener('mouseleave', hideTooltip);
}


/* ══════════════════════════════════════════════════════
   9. ANIMATED HEATMAP (with hover)
   ══════════════════════════════════════════════════════ */
function drawHeatmap(canvas, data) {
    if (!data.length) return;
    const { ctx, w, h } = setupCanvas(canvas);
    const pad = { top: 20, right: 16, bottom: 40, left: 48 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const cellW = cw / 24;
    const cellH = ch / 7;
    const vals = data.map(d => d.avg_carbon).filter(v => v > 0);
    const minC = Math.min(...vals);
    const maxC = Math.max(...vals);

    // Pre-compute cell colors and positions
    const cells = data.filter(d => d.avg_carbon > 0).map(d => {
        const t = (d.avg_carbon - minC) / (maxC - minC || 1);
        const r = Math.round(16 + t * 230);
        const g = Math.round(185 - t * 85);
        const b = Math.round(129 - t * 80);
        return {
            x: pad.left + d.hour * cellW,
            y: pad.top + d.day * cellH,
            w: cellW, h: cellH,
            color: `rgb(${r},${g},${b})`,
            day: days[d.day], hour: d.hour, value: d.avg_carbon,
        };
    });

    chartRegistry.set(canvas, { type: 'heatmap', cells, pad, cw, ch, w, h, cellW, cellH, days });

    // Animate: fade in cells with stagger
    const duration = 600;
    const t0 = performance.now();

    function frame(now) {
        const progress = Math.min((now - t0) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 2);

        ctx.clearRect(0, 0, w, h);
        ctx.save();

        cells.forEach((c, idx) => {
            // Stagger: each cell has a slight delay based on position
            const cellDelay = ((c.x - pad.left) / cw) * 0.3 + ((c.y - pad.top) / ch) * 0.3;
            const cellProgress = Math.max(0, Math.min(1, (eased - cellDelay) / (1 - 0.6)));
            if (cellProgress <= 0) return;

            ctx.globalAlpha = cellProgress;
            ctx.fillStyle = c.color;
            const scale = 0.5 + cellProgress * 0.5;
            const cx = c.x + cellW / 2;
            const cy = c.y + cellH / 2;
            const sw = (cellW - 2) * scale;
            const sh = (cellH - 2) * scale;
            ctx.beginPath();
            roundedRect(ctx, cx - sw / 2, cy - sh / 2, sw, sh, 2);
            ctx.fill();
        });

        ctx.globalAlpha = 1;

        // Day labels
        ctx.fillStyle = COLORS.muted; ctx.font = '9px Inter, sans-serif'; ctx.textAlign = 'right';
        days.forEach((d, i) => {
            ctx.fillText(d, pad.left - 6, pad.top + i * cellH + cellH / 2 + 3);
        });

        // Hour labels
        ctx.textAlign = 'center';
        for (let hr = 0; hr < 24; hr += 3) {
            const ampm = hr >= 12 ? 'pm' : 'am';
            const h12 = hr % 12 || 12;
            ctx.fillText(`${h12} ${ampm}`, pad.left + hr * cellW + cellW / 2, pad.top + ch + 14);
        }

        ctx.restore();
        if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    attachHeatmapHover(canvas);
}

function attachHeatmapHover(canvas) {
    if (canvas._hoverAttached) return;
    canvas._hoverAttached = true;

    canvas.addEventListener('mousemove', e => {
        const reg = chartRegistry.get(canvas);
        if (!reg || reg.type !== 'heatmap') return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const hit = reg.cells.find(c => mx >= c.x && mx <= c.x + c.w && my >= c.y && my <= c.y + c.h);
        if (!hit) { hideTooltip(); return; }

        const ampm = hit.hour >= 12 ? 'pm' : 'am';
        const h12 = hit.hour % 12 || 12;
        showTooltip(
            `<div class="tt-label">${hit.day} at ${h12} ${ampm}</div><div class="tt-value" style="color:${hit.color}">${hit.value.toFixed(1)} gCO\u2082/kWh</div>`,
            e.clientX, e.clientY
        );
    });

    canvas.addEventListener('mouseleave', hideTooltip);
}


/* ══════════════════════════════════════════════════════
   9b. HORIZONTAL BAR CHART — GCP Region Carbon Comparison
   ══════════════════════════════════════════════════════ */
function drawRegionBars(canvas, regions) {
    if (!regions.length) return;
    const { ctx, w, h } = setupCanvas(canvas);

    const pad = { top: 20, right: 90, bottom: 10, left: 180 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;
    const barH = Math.min(32, ch / regions.length - 6);
    const gap = (ch - barH * regions.length) / (regions.length + 1);

    const maxVal = Math.max(...regions.map(r => r.carbon_intensity)) * 1.15;

    // Color palette: green → yellow → red based on intensity
    function barColor(ci) {
        const t = Math.min(ci / 500, 1); // 0 = green, 1 = red
        if (t < 0.3) return '#34d399';  // green
        if (t < 0.5) return '#fbbf24';  // yellow
        if (t < 0.7) return '#fb923c';  // orange
        return '#f87171';               // red
    }

    // Store layout for hover
    const bars = regions.map((r, i) => {
        const y = pad.top + gap + i * (barH + gap);
        const barW = (r.carbon_intensity / maxVal) * cw;
        return { ...r, x: pad.left, y, barW, barH, color: barColor(r.carbon_intensity) };
    });

    chartRegistry.set(canvas, { type: 'regionBars', bars, w, h, pad });

    // Animate
    const duration = 600;
    const t0 = performance.now();

    function frame(now) {
        const progress = Math.min((now - t0) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);

        ctx.clearRect(0, 0, w, h);
        ctx.save();

        // Faint grid lines
        ctx.strokeStyle = COLORS.grid;
        ctx.lineWidth = 0.5;
        for (let i = 0; i <= 4; i++) {
            const x = pad.left + (i / 4) * cw;
            ctx.beginPath();
            ctx.moveTo(x, pad.top);
            ctx.lineTo(x, pad.top + ch);
            ctx.stroke();
        }

        // Grid value labels at top
        ctx.fillStyle = COLORS.muted;
        ctx.font = '10px Inter, sans-serif';
        ctx.textAlign = 'center';
        for (let i = 0; i <= 4; i++) {
            const val = Math.round((i / 4) * maxVal);
            const x = pad.left + (i / 4) * cw;
            ctx.fillText(val, x, pad.top - 6);
        }

        bars.forEach(bar => {
            const animW = bar.barW * eased;

            // Bar (rounded right end)
            const radius = Math.min(5, barH / 2);
            ctx.beginPath();
            ctx.moveTo(bar.x, bar.y);
            ctx.lineTo(bar.x + Math.max(0, animW - radius), bar.y);
            ctx.arcTo(bar.x + animW, bar.y, bar.x + animW, bar.y + radius, radius);
            ctx.arcTo(bar.x + animW, bar.y + bar.barH, bar.x + animW - radius, bar.y + bar.barH, radius);
            ctx.lineTo(bar.x, bar.y + bar.barH);
            ctx.closePath();

            // Gradient fill
            const grad = ctx.createLinearGradient(bar.x, 0, bar.x + bar.barW, 0);
            grad.addColorStop(0, bar.color + 'cc');
            grad.addColorStop(1, bar.color);
            ctx.fillStyle = grad;
            ctx.fill();

            // Active region glow
            if (bar.is_active) {
                ctx.shadowColor = bar.color;
                ctx.shadowBlur = 8;
                ctx.fill();
                ctx.shadowBlur = 0;
            }

            // Region label (left side)
            ctx.fillStyle = bar.is_active ? '#fff' : COLORS.text;
            ctx.font = bar.is_active ? 'bold 12px Inter, sans-serif' : '12px Inter, sans-serif';
            ctx.textAlign = 'right';
            ctx.textBaseline = 'middle';
            const labelY = bar.y + bar.barH / 2;
            ctx.fillText(bar.gcp_region, pad.left - 8, labelY);

            // Active badge
            if (bar.is_active) {
                const tag = '★ active';
                const tagW = ctx.measureText(tag).width + 10;
                const tx = pad.left - 8 - ctx.measureText(bar.gcp_region).width - tagW - 4;
                ctx.fillStyle = COLORS.green + '30';
                ctx.beginPath();
                ctx.roundRect(tx, labelY - 8, tagW, 16, 4);
                ctx.fill();
                ctx.fillStyle = COLORS.green;
                ctx.font = 'bold 9px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(tag, tx + tagW / 2, labelY + 1);
            }

            // Value label (right of bar)
            ctx.fillStyle = COLORS.text;
            ctx.font = 'bold 11px JetBrains Mono, monospace';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            if (eased > 0.5) {
                ctx.globalAlpha = (eased - 0.5) * 2;
                ctx.fillText(`${bar.carbon_intensity.toFixed(0)} gCO₂/kWh`, bar.x + animW + 8, bar.y + bar.barH / 2);
                ctx.globalAlpha = 1;
            }
        });

        ctx.restore();
        if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    // Hover
    attachRegionBarHover(canvas);
}

function attachRegionBarHover(canvas) {
    if (canvas._hoverAttached) return;
    canvas._hoverAttached = true;

    canvas.addEventListener('mousemove', e => {
        const reg = chartRegistry.get(canvas);
        if (!reg || reg.type !== 'regionBars') return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const hit = reg.bars.find(b => mx >= b.x && mx <= b.x + b.barW && my >= b.y && my <= b.y + b.barH);
        if (!hit) { hideTooltip(); return; }

        const liveTag = hit.is_live ? '<span style="color:#34d399">● Live</span>' : '<span style="color:#fbbf24">● Estimate</span>';
        showTooltip(
            `<div class="tt-label">${hit.gcp_region} — ${hit.label}</div>
             <div class="tt-value" style="color:${hit.color}">${hit.carbon_intensity.toFixed(1)} gCO₂/kWh</div>
             <div style="font-size:0.7rem;margin-top:2px">${liveTag} · Grid: ${hit.respondent}</div>`,
            e.clientX, e.clientY
        );
    });

    canvas.addEventListener('mouseleave', hideTooltip);
}


/* ══════════════════════════════════════════════════════
   10. PAGE LOADERS
   ══════════════════════════════════════════════════════ */

// ── Dashboard ──────────────────────────────────────────
async function loadDashboard() {
    const [current, stats, forecastResp, history, heatmap, jobStats, regions] = await Promise.all([
        api('/energy/current'),
        api('/energy/stats'),
        api('/forecast/next24h').catch(() => ({ forecast: [], actuals: [] })),
        api('/energy/history?limit=168'),
        api('/energy/heatmap'),
        api('/jobs/stats'),
        api('/regions/carbon').catch(() => []),
    ]);

    const forecast = forecastResp.forecast || [];
    const recentActuals = forecastResp.actuals || [];

    animateValue(document.getElementById('kpi-current'), Math.round(current.carbon_intensity));
    animateValue(document.getElementById('kpi-avg24'), stats.last_24h.avg);
    animateValue(document.getElementById('kpi-min24'), stats.last_24h.min);
    animateValue(document.getElementById('kpi-saved'), jobStats.total_carbon_saved);

    if (forecast.length) {
        drawForecastChart(document.getElementById('chart-forecast'), recentActuals, forecast, { yLabel: 'gCO₂/kWh' });
    }

    const sourceSegments = [
        { label: 'Solar',   value: current.solar_pct || 0,   color: '#fbbf24' },
        { label: 'Wind',    value: current.wind_pct || 0,    color: '#60a5fa' },
        { label: 'Gas',     value: current.gas_pct || 0,     color: '#f87171' },
        { label: 'Nuclear', value: current.nuclear_pct || 0, color: '#a78bfa' },
        { label: 'Hydro',   value: current.hydro_pct || 0,   color: '#34d399' },
        { label: 'Coal',    value: current.coal_pct || 0,    color: '#94a3b8' },
        { label: 'Other',   value: current.other_pct || 0,   color: '#cbd5e1' },
    ].filter(s => s.value > 0);
    drawDonut(document.getElementById('chart-sources'), sourceSegments);

    if (history.length) {
        const hData = history.reverse().map(h => ({
            x: new Date(h.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric' }),
            y: h.carbon_intensity,
        }));
        const step = Math.max(1, Math.floor(hData.length / 72));
        const sampled = hData.filter((_, i) => i % step === 0);
        drawAreaChart(document.getElementById('chart-history'), sampled, { color: COLORS.accent, yLabel: 'gCO₂/kWh' });
    }

    if (heatmap.length) drawHeatmap(document.getElementById('chart-heatmap'), heatmap);

    // GCP Region Carbon Comparison
    if (regions.length) {
        drawRegionBars(document.getElementById('chart-regions'), regions);
        // Update badge based on data liveness
        const allLive = regions.every(r => r.is_live);
        const badge = document.getElementById('region-badge');
        if (badge) {
            badge.textContent = allLive ? 'Live EIA Data' : 'Mixed Live + Estimates';
            badge.className = allLive ? 'badge badge-info' : 'badge badge-neutral';
        }
    }
}
// ── Scheduler Mode Toggle ─────────────────────────────────
let schedulerMode = 'windows'; // 'windows' or 'geas'

function setMode(mode) {
    schedulerMode = mode;
    document.getElementById('windows-panel').classList.toggle('hidden', mode !== 'windows');
    document.getElementById('geas-panel').classList.toggle('hidden', mode !== 'geas');
    // GEAS-only elements
    document.querySelectorAll('.geas-only').forEach(el => el.classList.toggle('hidden', mode !== 'geas'));
    // Toggle buttons
    const wBtn = document.getElementById('mode-btn-windows');
    const gBtn = document.getElementById('mode-btn-geas');
    if (mode === 'windows') {
        wBtn.style.background = 'var(--accent)'; wBtn.style.color = '#fff';
        gBtn.style.background = 'transparent'; gBtn.style.color = 'var(--text-muted)';
    } else {
        gBtn.style.background = 'var(--accent)'; gBtn.style.color = '#fff';
        wBtn.style.background = 'transparent'; wBtn.style.color = 'var(--text-muted)';
    }
    loadJobSchedule();
}

document.getElementById('mode-btn-windows').addEventListener('click', () => setMode('windows'));
document.getElementById('mode-btn-geas').addEventListener('click', () => setMode('geas'));

// ── Green Windows form toggle ─────────────────────────────
document.getElementById('btn-open-windows').addEventListener('click', () => {
    const card = document.getElementById('windows-form-card');
    const btn = document.getElementById('btn-open-windows');
    if (card.classList.contains('hidden')) {
        card.classList.remove('hidden');
        btn.innerHTML = '<span>Cancel</span>';
        btn.classList.add('btn-danger');
    } else {
        card.classList.add('hidden');
        document.getElementById('suggestions-card').classList.add('hidden');
        btn.innerHTML = '<span>+ Schedule a Job</span>';
        btn.classList.remove('btn-danger');
    }
});

// ── GPU Slider Sync ─────────────────────────────────────
const gpuRange = document.getElementById('win-gpu-range');
const gpuInput = document.getElementById('win-gpu-scale');
const gpuPreview = document.getElementById('gpu-energy-preview');
function updateGpuPreview() {
    const n = parseInt(gpuRange.value) || 1;
    gpuInput.value = n;
    gpuRange.value = n;
    const kwh = (300 * n * 1) / 1000;  // 1-hour job duration
    gpuPreview.textContent = `≈ ${kwh.toFixed(1)} kWh per run`;
}
gpuRange.addEventListener('input', updateGpuPreview);
gpuInput.addEventListener('input', () => { gpuRange.value = gpuInput.value; updateGpuPreview(); });

// ── File Upload ─────────────────────────────────────────
let uploadedFilename = '';
document.getElementById('win-demo-file').addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;
    document.getElementById('file-name').textContent = file.name;
    const form = new FormData();
    form.append('file', file);
    try {
        const data = await fetch('/api/jobs/upload-demo', { method: 'POST', body: form }).then(r => r.json());
        uploadedFilename = data.filename;
        toast(`Uploaded "${data.filename}"`, 'success');
    } catch { toast('File upload failed', 'error'); }
});

// ── Green Windows: Schedule Optimally ───────────────────
document.getElementById('form-windows').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('btn-find-windows');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Finding green windows...';
    document.getElementById('brown-warning').classList.add('hidden');
    try {
        const payload = {
            name: document.getElementById('win-name').value,
            task_type: document.getElementById('win-type').value,
            flexibility_hours: parseInt(document.getElementById('win-flexibility').value),
            priority_class: document.getElementById('win-priority').value,
            gpu_scale: parseInt(gpuRange.value) || 1,
        };
        if (uploadedFilename) payload.demo_file = uploadedFilename;
        const data = await api('/jobs/suggest', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        window._pendingJobId = data.job_id;
        renderSuggestions(data);
        toast(`Found ${data.suggestions.length} green windows for "${data.job_name}"`, 'success');
    } catch(err) { /* toast by api() */ }
    finally { btn.disabled = false; btn.innerHTML = '<span>⚡ Schedule Optimally</span>'; }
});

// ── Run Immediately ─────────────────────────────────────
document.getElementById('btn-run-now').addEventListener('click', async () => {
    const btn = document.getElementById('btn-run-now');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Starting...';
    try {
        let jobId = window._pendingJobId;
        if (!jobId) {
            // Create the job first
            const payload = {
                name: document.getElementById('win-name').value,
                task_type: document.getElementById('win-type').value,
                flexibility_hours: parseInt(document.getElementById('win-flexibility').value),
                priority_class: document.getElementById('win-priority').value,
                gpu_scale: parseInt(gpuRange.value) || 1,
            };
            if (uploadedFilename) payload.demo_file = uploadedFilename;
            const created = await api('/jobs/suggest', { method: 'POST', body: JSON.stringify(payload) });
            jobId = created.job_id;
        }
        const data = await api('/jobs/run-now', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId }),
        });
        toast(`"${data.name}" running immediately at ${data.avg_carbon.toFixed(0)} gCO₂/kWh`, 'info');
        resetFormAndClose();
        loadJobSchedule();
    } catch(err) { /* toast by api() */ }
    finally { btn.disabled = false; btn.innerHTML = '<span>▶ Run Immediately</span>'; }
});

function resetFormAndClose() {
    document.getElementById('form-windows').reset();
    document.getElementById('suggestions-card').classList.add('hidden');
    document.getElementById('windows-form-card').classList.add('hidden');
    document.getElementById('brown-warning').classList.add('hidden');
    document.getElementById('btn-open-windows').innerHTML = '<span>+ Schedule a Job</span>';
    document.getElementById('btn-open-windows').classList.remove('btn-danger');
    document.getElementById('file-name').textContent = '';
    uploadedFilename = '';
    window._pendingJobId = null;
    gpuRange.value = 1; gpuInput.value = 1;
    updateGpuPreview();
}

function renderSuggestions(data) {
    const card = document.getElementById('suggestions-card');
    const list = document.getElementById('suggestions-list');
    card.classList.remove('hidden');
    list.innerHTML = '';

    // Show brown warning if applicable
    if (data.brown_warning) {
        const bw = document.getElementById('brown-warning');
        bw.classList.remove('hidden');
        bw.innerHTML = `<strong>⚠ High Carbon Alert:</strong> Current intensity is <strong>${data.brown_warning.current_ci.toFixed(0)} gCO₂/kWh</strong>. Consider scheduling for a greener window to save up to <strong>${data.brown_warning.potential_savings.toFixed(0)} gCO₂</strong>.`;
    }

    data.suggestions.forEach((s, idx) => {
        const start = new Date(s.start).toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
        const el = document.createElement('div');
        el.className = 'suggestion-card';
        el.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:var(--surface);border:1px solid var(--border);border-radius:8px;cursor:pointer;transition:border-color .2s;';
        el.innerHTML = `
            <div>
                <div style="font-weight:600;color:var(--text);margin-bottom:4px;">Start at ${start}</div>
                <div style="font-size:12px;color:var(--text-muted);">Carbon: ${s.avg_carbon.toFixed(1)} gCO₂/kWh · Saves ${s.savings_vs_naive.toFixed(1)} gCO₂/kWh vs now</div>
                <div style="font-size:11px;color:var(--accent);margin-top:2px;">${data.gpu_scale} GPU${data.gpu_scale > 1 ? 's' : ''} · ${data.energy_kwh.toFixed(1)} kWh</div>
            </div>
            <button class="btn btn-primary" style="white-space:nowrap;" onclick="scheduleJob(${data.job_id}, ${idx})">Schedule Here</button>`;
        el.addEventListener('mouseenter', () => el.style.borderColor = 'var(--accent)');
        el.addEventListener('mouseleave', () => el.style.borderColor = 'var(--border)');
        list.appendChild(el);
    });
}

window.scheduleJob = async function(jobId, windowIndex) {
    try {
        const data = await api('/jobs/schedule', {
            method: 'POST',
            body: JSON.stringify({ job_id: jobId, window_index: windowIndex }),
        });
        toast(`"${data.name}" scheduled — saves ${(data.co2_saved_g || 0).toFixed(1)} gCO₂`, 'success');
        resetFormAndClose();
        loadJobSchedule();
    } catch (err) { /* toast by api() */ }
};

// ── GEAS form toggle ──────────────────────────────────────
document.getElementById('btn-open-geas').addEventListener('click', () => {
    const card = document.getElementById('geas-form-card');
    const btn = document.getElementById('btn-open-geas');
    if (card.classList.contains('hidden')) {
        card.classList.remove('hidden');
        btn.innerHTML = '<span>Cancel</span>';
        btn.classList.add('btn-danger');
    } else {
        card.classList.add('hidden');
        btn.innerHTML = '<span>+ Submit Task to GEAS</span>';
        btn.classList.remove('btn-danger');
    }
});

// ── GEAS: Submit task ──────────────────────────────────────
document.getElementById('form-geas').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-geas');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Submitting...';
    try {
        const payload = {
            name: document.getElementById('geas-name').value,
            task_type: document.getElementById('geas-type').value,
            command: document.getElementById('geas-command').value,
        };
        const earliest = document.getElementById('geas-earliest').value;
        if (earliest) payload.earliest_start = new Date(earliest).toISOString();
        const deadline = document.getElementById('geas-deadline').value;
        if (deadline) payload.deadline = new Date(deadline).toISOString();

        const data = await api('/geas/submit', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        toast(`"${data.name}" submitted to GEAS (${data.status})`, 'success');
        document.getElementById('form-geas').reset();
        document.getElementById('geas-form-card').classList.add('hidden');
        document.getElementById('btn-open-geas').innerHTML = '<span>+ Submit Task to GEAS</span>';
        document.getElementById('btn-open-geas').classList.remove('btn-danger');
        loadJobSchedule();
    } catch (err) { /* toast fired by api() */ }
    finally { btn.disabled = false; btn.innerHTML = '<span>Submit to GEAS</span>'; }
});

// ── Job Schedule Page ─────────────────────────────────────
async function loadJobSchedule() {
    const [jobs, stats] = await Promise.all([api('/jobs'), api('/jobs/stats')]);

    // KPI metrics
    animateValue(document.getElementById('js-kpi-scheduled'), stats.total_scheduled);
    animateValue(document.getElementById('js-kpi-running'), stats.running_count);
    animateValue(document.getElementById('js-kpi-queued'), stats.queued_count || 0);
    animateValue(document.getElementById('js-kpi-completed'), stats.completed_count);
    animateValue(document.getElementById('js-kpi-saved'), stats.total_carbon_saved || 0);

    // GEAS capacity bar (only relevant in GEAS mode, but update anyway)
    const capBar = document.getElementById('geas-cap-bar');
    const capLabel = document.getElementById('geas-cap-label');
    if (capBar && stats.capacity > 0) {
        const pct = Math.min(100, Math.round((stats.ti / stats.capacity) * 100));
        capBar.style.width = pct + '%';
        capBar.style.background = pct > 80 ? '#ef4444' : pct > 50 ? '#f5a623' : 'var(--accent)';
    }
    if (capLabel) capLabel.textContent = `TI ${stats.ti?.toFixed(1) || 0} / ${stats.capacity?.toFixed(1) || 0}`;

    // Update table columns based on mode
    const thead = document.getElementById('jobs-thead');
    if (schedulerMode === 'windows') {
        thead.innerHTML = '<tr><th>ID</th><th>Name</th><th>Priority</th><th>GPUs</th><th>Status</th><th>Mode</th><th>Scheduled</th><th>CO₂ (g)</th><th>Saved (g)</th><th>Actions</th></tr>';
    } else {
        thead.innerHTML = '<tr><th>ID</th><th>Name</th><th>Command</th><th>Status</th><th>PID</th><th>CPU</th><th>Carbon</th><th>Saved</th><th>Started</th><th>Actions</th></tr>';
    }

    // Jobs table
    const tbody = document.getElementById('jobs-tbody');
    const empty = document.getElementById('jobs-empty');
    tbody.innerHTML = '';

    // Filter jobs based on mode
    const filtered = schedulerMode === 'windows'
        ? jobs.filter(j => !j.command)  // Green Windows jobs have no command
        : jobs.filter(j => !!j.command); // GEAS jobs have a command

    if (!filtered.length) { empty.classList.remove('hidden'); return; }
    empty.classList.add('hidden');

    const statusColors = {
        pending: '#888', scheduled: '#3b82f6', queued: '#f5a623', running: '#3b82f6',
        paused: '#f97316', completed: '#22c55e', failed: '#ef4444',
    };

    filtered.forEach((j, idx) => {
        const tr = document.createElement('tr');
        tr.style.animation = `fadeSlideIn 0.3s ease ${idx * 50}ms both`;
        const canDelete = ['pending', 'scheduled', 'queued', 'paused', 'running'].includes(j.status);
        const statusStyle = j.status === 'running' ? 'animation:pulse 1.5s infinite' : '';

        if (schedulerMode === 'windows') {
            const schedStr = j.scheduled_start
                ? new Date(j.scheduled_start).toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
                : '--';
            const priorityColor = j.priority_class === 'latency-critical' ? '#ef4444' : j.priority_class === 'flexible' ? '#3b82f6' : '#f5a623';
            const modeColor = j.run_mode === 'optimized' ? 'var(--accent)' : '#ef4444';
            const co2Str = j.co2_total_g ? j.co2_total_g.toFixed(1) : '--';
            const savedStr = j.co2_saved_g ? j.co2_saved_g.toFixed(1) : (j.status === 'completed' ? '0' : '--');
            tr.innerHTML = `
                <td>#${j.id}</td>
                <td>${j.name}</td>
                <td><span class="priority-pill" style="background:${priorityColor}">${j.priority_class || 'flexible'}</span></td>
                <td>${j.gpu_scale || 1}</td>
                <td><span class="status-pill" style="background:${statusColors[j.status] || '#888'};${statusStyle}">${j.status}</span></td>
                <td><span class="mode-pill" style="background:${modeColor}">${j.run_mode || 'optimized'}</span></td>
                <td>${schedStr}</td>
                <td>${co2Str}</td>
                <td style="color:${COLORS.green}">${savedStr}</td>
                <td>${canDelete ? `<button class="btn-remove" onclick="deleteJob(${j.id})">Remove</button>` : ''}</td>`;
        } else {
            const cmdShort = j.command.length > 36 ? j.command.slice(0, 36) + '...' : j.command;
            const startStr = j.actual_start
                ? new Date(j.actual_start).toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
                : '--';
            tr.innerHTML = `
                <td>#${j.id}</td>
                <td>${j.name}</td>
                <td style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-muted)" title="${j.command}">${cmdShort}</td>
                <td><span class="status-pill" style="background:${statusColors[j.status] || '#888'};${statusStyle}">${j.status}</span></td>
                <td style="font-family:'JetBrains Mono',monospace;font-size:12px;">${j.pid || '--'}</td>
                <td>${j.cpu_intensity ? j.cpu_intensity.toFixed(1) : '--'}</td>
                <td>${carbonStr}</td>
                <td style="color:${COLORS.green}">${savedStr}</td>
                <td>${startStr}</td>
                <td>${canDelete ? `<button class="btn-remove" onclick="deleteJob(${j.id})">Cancel</button>` : (j.exit_code != null ? 'exit ' + j.exit_code : '')}</td>`;
        }
        tbody.appendChild(tr);
    });
}

// ── Delete Job ──────────────────────────────────────────
window.deleteJob = async function(id) {
    if (!confirm('Remove this job?')) return;
    try {
        await api(`/jobs/${id}`, { method: 'DELETE' });
        toast('Job removed', 'success');
        loadJobSchedule();
    } catch (err) { /* handled by api() */ }
};

// ── Impact Page ────────────────────────────────────────
function drawEmptyChart(canvas, message) {
    const { ctx, w, h } = setupCanvas(canvas);
    ctx.clearRect(0, 0, w, h);

    // Faint grid for visual structure
    const pad = { top: 20, right: 16, bottom: 44, left: 58 };
    drawGrid(ctx, w, h, pad);

    // Icon (chart outline)
    const cx = w / 2, cy = h / 2 - 12;
    ctx.strokeStyle = COLORS.muted + '40';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(cx - 24, cy + 18);
    ctx.lineTo(cx - 24, cy - 18);
    ctx.lineTo(cx + 24, cy - 18);
    ctx.stroke();
    // Small bar outlines
    [[-14, 8], [-2, -4], [10, 2]].forEach(([dx, dy]) => {
        ctx.strokeStyle = COLORS.muted + '30';
        ctx.strokeRect(cx + dx - 4, cy + dy, 8, 18 - dy);
    });

    // Message
    ctx.fillStyle = COLORS.muted;
    ctx.font = '12px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(message, cx, cy + 40);
}

/** Horizontal bar chart showing per-job CO₂ savings — styled like the dashboard region bars */
function drawSavingsBars(canvas, impact) {
    if (!impact.length) return;
    const { ctx, w, h } = setupCanvas(canvas);

    const pad = { top: 24, right: 80, bottom: 10, left: 140 };
    const cw = w - pad.left - pad.right;
    const ch = h - pad.top - pad.bottom;
    const n = impact.length;
    const barH = Math.min(32, ch / n - 6);
    const gap = (ch - barH * n) / (n + 1);

    const maxVal = Math.max(...impact.map(j => j.total_saved)) * 1.15 || 1;

    // Color based on savings magnitude
    function barColor(saved, maxS) {
        const t = saved / maxS;
        if (t > 0.7) return COLORS.green;
        if (t > 0.4) return COLORS.greenLt;
        return COLORS.accent;
    }

    const bars = impact.map((j, i) => {
        const y = pad.top + gap + i * (barH + gap);
        const barW = (j.total_saved / maxVal) * cw;
        const color = barColor(j.total_saved, maxVal / 1.15);
        return { ...j, x: pad.left, y, barW, barH, color, pct: j.naive_carbon > 0 ? ((j.naive_carbon - j.smart_carbon) / j.naive_carbon * 100).toFixed(1) : '0' };
    });

    chartRegistry.set(canvas, { type: 'savingsBars', bars, w, h, pad });

    // Animate
    const duration = 600;
    const t0 = performance.now();

    function frame(now) {
        const progress = Math.min((now - t0) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);

        ctx.clearRect(0, 0, w, h);
        ctx.save();

        // Vertical grid lines
        ctx.strokeStyle = COLORS.grid; ctx.lineWidth = 0.5;
        for (let i = 0; i <= 4; i++) {
            const x = pad.left + (i / 4) * cw;
            ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, pad.top + ch); ctx.stroke();
        }

        // Grid value labels at top
        ctx.fillStyle = COLORS.muted; ctx.font = '10px Inter, sans-serif'; ctx.textAlign = 'center';
        for (let i = 0; i <= 4; i++) {
            const val = Math.round((i / 4) * maxVal);
            const x = pad.left + (i / 4) * cw;
            ctx.fillText(val, x, pad.top - 8);
        }

        bars.forEach(bar => {
            const animW = bar.barW * eased;

            // Rounded right end
            const radius = Math.min(5, barH / 2);
            ctx.beginPath();
            ctx.moveTo(bar.x, bar.y);
            ctx.lineTo(bar.x + Math.max(0, animW - radius), bar.y);
            ctx.arcTo(bar.x + animW, bar.y, bar.x + animW, bar.y + radius, radius);
            ctx.arcTo(bar.x + animW, bar.y + barH, bar.x + animW - radius, bar.y + barH, radius);
            ctx.lineTo(bar.x, bar.y + barH);
            ctx.closePath();

            // Gradient fill (matches region bars)
            const grad = ctx.createLinearGradient(bar.x, 0, bar.x + bar.barW, 0);
            grad.addColorStop(0, bar.color + 'cc');
            grad.addColorStop(1, bar.color);
            ctx.fillStyle = grad;

            // Glow
            ctx.shadowColor = bar.color;
            ctx.shadowBlur = 6;
            ctx.fill();
            ctx.shadowColor = 'transparent';
            ctx.shadowBlur = 0;

            // Job name (left)
            ctx.fillStyle = COLORS.text; ctx.font = '11px Inter, sans-serif'; ctx.textAlign = 'right';
            const lbl = bar.name.length > 16 ? bar.name.slice(0, 16) + '..' : bar.name;
            ctx.fillText(lbl, pad.left - 10, bar.y + barH / 2 + 4);

            // Value + % label (right of bar)
            if (progress > 0.5) {
                ctx.fillStyle = COLORS.text; ctx.font = 'bold 11px Inter, sans-serif'; ctx.textAlign = 'left';
                ctx.fillText(`${bar.total_saved} gCO\u2082`, bar.x + animW + 8, bar.y + barH / 2 + 1);
                ctx.fillStyle = COLORS.muted; ctx.font = '9px Inter, sans-serif';
                ctx.fillText(`\u2193${bar.pct}%`, bar.x + animW + 8, bar.y + barH / 2 + 13);
            }
        });

        // Y-axis label
        ctx.save();
        ctx.fillStyle = COLORS.muted; ctx.font = 'bold 10px Inter, sans-serif'; ctx.textAlign = 'center';
        ctx.translate(pad.left + cw / 2, pad.top - 20);
        ctx.fillText('gCO\u2082 Saved (total per job)', 0, 0);
        ctx.restore();

        ctx.restore();
        if (progress < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    // Hover
    if (!canvas._hoverAttached) {
        canvas._hoverAttached = true;
        canvas.addEventListener('mousemove', e => {
            const reg = chartRegistry.get(canvas);
            if (!reg || reg.type !== 'savingsBars') return;
            const rect = canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;

            const hit = reg.bars.find(b => mx >= b.x && mx <= b.x + b.barW && my >= b.y && my <= b.y + b.barH);
            if (!hit) { hideTooltip(); return; }

            showTooltip(
                `<div class="tt-label">${hit.name}</div>` +
                `<div class="tt-row"><div class="tt-dot" style="background:${hit.color}"></div><span>Saved</span></div>` +
                `<div class="tt-value">${hit.total_saved} gCO\u2082</div>` +
                `<div class="tt-row" style="margin-top:4px;font-size:11px;color:${COLORS.muted}">` +
                `${hit.smart_carbon.toFixed(1)} vs ${hit.naive_carbon.toFixed(1)} gCO\u2082/kWh &middot; ${hit.pct}% reduction</div>`,
                e.clientX, e.clientY
            );
        });
        canvas.addEventListener('mouseleave', hideTooltip);
    }
}

async function loadImpact() {
    const impact = await api('/jobs/impact');

    if (!impact.length) {
        document.getElementById('impact-total-jobs').textContent = '0';
        document.getElementById('impact-total-saved').textContent = '0';
        document.getElementById('impact-avg-pct').textContent = '0';
        drawEmptyChart(document.getElementById('chart-comparison'), 'Schedule jobs to see carbon comparison');
        drawEmptyChart(document.getElementById('chart-savings-bars'), 'Per-job savings will appear here');
        return;
    }

    const totalJobs = impact.length;
    const totalSaved = impact[impact.length - 1].cumulative_saved;
    const avgPct = impact.reduce((sum, j) => {
        if (j.naive_carbon > 0) return sum + ((j.naive_carbon - j.smart_carbon) / j.naive_carbon) * 100;
        return sum;
    }, 0) / totalJobs;

    animateValue(document.getElementById('impact-total-jobs'), totalJobs);
    animateValue(document.getElementById('impact-total-saved'), totalSaved);
    animateValue(document.getElementById('impact-avg-pct'), Math.round(avgPct));

    drawGroupedBars(document.getElementById('chart-comparison'),
        impact.map(j => ({ label: j.name, v1: j.naive_carbon, v2: j.smart_carbon })),
        { colors: [COLORS.red, COLORS.green], labels: ['Naive (run now)', 'Smart (GreenQueue)'] }
    );

    drawSavingsBars(document.getElementById('chart-savings-bars'), impact);
}

// ── Auto-refresh every 30s — keeps data fresh as new readings arrive ──
setInterval(() => {
    const pg = document.querySelector('.page.active')?.id?.replace('page-', '');
    if (pg === 'dashboard') loadDashboard();
    else if (pg === 'job-schedule') loadJobSchedule();
    else if (pg === 'impact') loadImpact();
}, 30000);
