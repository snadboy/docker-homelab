// Strip kiosk dashboard — rotating alerts + per-host metrics views.

const HOSTS = ["utilities", "cadre", "sdevs"];
const ROTATION = ["alerts", ...HOSTS]; // view ids
const VIEW_DURATION_MS = 8000;
const ALERTS_POLL_MS = 5000;
const METRICS_POLL_MS = 3000;
const STATUS_PAGE_SLUG = "homelab";
const HISTORY_POINTS = 60;

// --- state ---
const history = {};
HOSTS.forEach(h => {
	history[h] = {
		t: [], cpu: [], mem: [], netRx: [], netTx: [], lastNet: null,
	};
});
let alertsState = { down: [], pending: [], total: 0 };
let currentViewIdx = 0;
let alarming = false;
let metricsCharts = {};

// --- view rotation ---
function setView(id) {
	document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === `${id}-view`));
	const idx = ROTATION.indexOf(id);
	document.getElementById("view-name").textContent =
		id === "alerts" ? "Alerts" : `${id} · system`;
	const dots = document.getElementById("dots");
	if (dots.children.length !== ROTATION.length) {
		dots.innerHTML = ROTATION.map(() => '<span></span>').join("");
	}
	[...dots.children].forEach((d, i) => d.classList.toggle("active", i === idx));
}

function rotate() {
	if (alarming) {
		setView("alerts");
		return;
	}
	currentViewIdx = (currentViewIdx + 1) % ROTATION.length;
	setView(ROTATION[currentViewIdx]);
}
setView(ROTATION[0]);

// --- alerts ---
async function fetchAlerts() {
	try {
		const r = await fetch(`/api/alerts/api/status-page/heartbeat/${STATUS_PAGE_SLUG}`, { cache: "no-store" });
		if (!r.ok) throw new Error(`HTTP ${r.status}`);
		const data = await r.json();
		const monitorList = data.publicGroupList ? null : data; // varies by Kuma version
		// Kuma /api/status-page/heartbeat returns { heartbeatList: { <monitorId>: [{status, time, ping, msg}, ...] }, uptimeList: {...} }
		const heartbeats = data.heartbeatList || {};
		const down = [], pending = [];
		for (const [mid, beats] of Object.entries(heartbeats)) {
			if (!beats.length) continue;
			const last = beats[beats.length - 1];
			if (last.status === 0) down.push({ id: mid, msg: last.msg, time: last.time });
			else if (last.status === 2) pending.push({ id: mid, msg: last.msg, time: last.time });
		}
		// also fetch monitor names for human-friendly display
		const namesResp = await fetch(`/api/alerts/api/status-page/${STATUS_PAGE_SLUG}`, { cache: "no-store" });
		const namesData = namesResp.ok ? await namesResp.json() : {};
		const idToName = {};
		(namesData.publicGroupList || []).forEach(g => (g.monitorList || []).forEach(m => { idToName[m.id] = m.name; }));
		alertsState = {
			down: down.map(d => ({ ...d, name: idToName[d.id] || `monitor ${d.id}` })),
			pending: pending.map(p => ({ ...p, name: idToName[p.id] || `monitor ${p.id}` })),
			total: Object.keys(heartbeats).length,
		};
		renderAlerts();
	} catch (e) {
		console.warn("alerts fetch", e);
	}
}

function renderAlerts() {
	const downCount = alertsState.down.length;
	document.getElementById("alerts-count").textContent = downCount;
	document.getElementById("alert-counter").textContent =
		downCount === 0 ? `all ${alertsState.total} ok` : `${downCount} down`;
	const list = document.getElementById("alerts-list");
	const items = [...alertsState.down.map(a => ({ ...a, klass: "down" })),
	               ...alertsState.pending.map(a => ({ ...a, klass: "pending" }))];
	if (!items.length) {
		list.innerHTML = `<li class="empty">all monitors green</li>`;
	} else {
		list.innerHTML = items.slice(0, 8).map(a =>
			`<li class="${a.klass}"><span class="name">${escapeHtml(a.name)}</span><span class="meta">${escapeHtml(a.msg || a.klass)}</span></li>`
		).join("");
	}
	const wasAlarming = alarming;
	alarming = downCount > 0;
	document.getElementById("alerts-view").classList.toggle("alarming", alarming);
	document.getElementById("ftr").classList.toggle("alarming", alarming);
	if (alarming && !wasAlarming) setView("alerts");
}

function escapeHtml(s) {
	return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
}

// --- metrics ---
async function fetchHostMetrics(host) {
	try {
		const r = await fetch(`/api/metrics/${host}/api/4/all`, { cache: "no-store" });
		if (!r.ok) return;
		const data = await r.json();
		const now = Date.now() / 1000;
		const h = history[host];

		const cpu = data.cpu?.total ?? 0;
		const mem = data.mem?.percent ?? 0;
		// network: sum over interfaces (skip lo and docker)
		let rx = 0, tx = 0;
		for (const iface of (data.network || [])) {
			if (iface.interface_name === "lo" || iface.interface_name?.startsWith("docker") || iface.interface_name?.startsWith("br-") || iface.interface_name?.startsWith("veth")) continue;
			rx += iface.bytes_recv || 0;
			tx += iface.bytes_sent || 0;
		}
		let netRx = 0, netTx = 0;
		if (h.lastNet) {
			const dt = now - h.lastNet.t;
			if (dt > 0) {
				netRx = Math.max(0, (rx - h.lastNet.rx) / dt);
				netTx = Math.max(0, (tx - h.lastNet.tx) / dt);
			}
		}
		h.lastNet = { t: now, rx, tx };

		h.t.push(now);
		h.cpu.push(cpu);
		h.mem.push(mem);
		h.netRx.push(netRx / 1e6); // MB/s
		h.netTx.push(netTx / 1e6);
		while (h.t.length > HISTORY_POINTS) {
			h.t.shift(); h.cpu.shift(); h.mem.shift(); h.netRx.shift(); h.netTx.shift();
		}
		renderHostView(host);
	} catch (e) {
		console.warn(`metrics ${host}`, e);
	}
}

function ensureHostView(host) {
	const view = document.getElementById(`${host}-view`);
	if (view.dataset.built) return;
	view.innerHTML = `
		<div class="metric" data-metric="cpu">
			<div class="metric-head"><span class="metric-label">cpu</span><span class="metric-value">–</span></div>
			<div class="metric-chart"></div>
		</div>
		<div class="metric" data-metric="mem">
			<div class="metric-head"><span class="metric-label">mem</span><span class="metric-value">–</span></div>
			<div class="metric-chart"></div>
		</div>
		<div class="metric" data-metric="netRx">
			<div class="metric-head"><span class="metric-label">net rx (MB/s)</span><span class="metric-value">–</span></div>
			<div class="metric-chart"></div>
		</div>
		<div class="metric" data-metric="netTx">
			<div class="metric-head"><span class="metric-label">net tx (MB/s)</span><span class="metric-value">–</span></div>
			<div class="metric-chart"></div>
		</div>`;
	view.dataset.built = "1";
}

function makeChart(el, color) {
	const opts = {
		width: el.clientWidth, height: el.clientHeight,
		legend: { show: false },
		cursor: { show: false },
		scales: { x: { time: true } },
		axes: [
			{ stroke: "#3a3f4b", grid: { stroke: "#21242c" }, ticks: { stroke: "#21242c" } },
			{ stroke: "#3a3f4b", grid: { stroke: "#21242c" }, ticks: { stroke: "#21242c" } },
		],
		series: [
			{},
			{ stroke: color, width: 2, fill: color + "33", points: { show: false } },
		],
	};
	return new uPlot(opts, [[], []], el);
}

const COLORS = { cpu: "#6cc5ff", mem: "#a78bfa", netRx: "#4ade80", netTx: "#fb923c" };

function renderHostView(host) {
	ensureHostView(host);
	const h = history[host];
	if (!h.t.length) return;
	const view = document.getElementById(`${host}-view`);
	const series = { cpu: h.cpu, mem: h.mem, netRx: h.netRx, netTx: h.netTx };
	const fmt = { cpu: v => `${v.toFixed(0)}%`, mem: v => `${v.toFixed(0)}%`, netRx: v => v.toFixed(2), netTx: v => v.toFixed(2) };
	for (const [k, v] of Object.entries(series)) {
		const block = view.querySelector(`[data-metric="${k}"]`);
		const valEl = block.querySelector(".metric-value");
		const chartEl = block.querySelector(".metric-chart");
		const last = v[v.length - 1] ?? 0;
		valEl.textContent = fmt[k](last);
		const key = `${host}-${k}`;
		if (!metricsCharts[key]) {
			metricsCharts[key] = makeChart(chartEl, COLORS[k]);
		}
		metricsCharts[key].setData([h.t, v]);
		metricsCharts[key].setSize({ width: chartEl.clientWidth, height: chartEl.clientHeight });
	}
}

// --- clock / footer ---
function tickClock() {
	const d = new Date();
	const hh = String(d.getHours()).padStart(2, "0");
	const mm = String(d.getMinutes()).padStart(2, "0");
	document.getElementById("clock").textContent = `${hh}:${mm}`;
	document.getElementById("last-update").textContent = `updated ${hh}:${mm}:${String(d.getSeconds()).padStart(2,"0")}`;
}

// --- boot ---
fetchAlerts();
HOSTS.forEach(h => fetchHostMetrics(h));
tickClock();

setInterval(fetchAlerts, ALERTS_POLL_MS);
setInterval(() => HOSTS.forEach(h => fetchHostMetrics(h)), METRICS_POLL_MS);
setInterval(tickClock, 1000);
setInterval(rotate, VIEW_DURATION_MS);
