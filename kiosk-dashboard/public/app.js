// Strip kiosk dashboard — rotating alerts + per-host metrics views.

const KIOSK_VERSION = "1.3.0";
const KIOSK_VERSION_DATE = "2026-04-29";

const HOSTS = ["utilities", "cadre", "sdevs"];
const ROTATION = ["alerts", ...HOSTS, "proxmox", "wifi"];
const STATUS_PAGE_SLUG = "homelab";

// --- settings (persisted in localStorage) ---
const DEFAULT_SETTINGS = {
	rotationMs: 8000,
	metricsMs: 3000,
	alertsMs: 5000,
	historyPoints: 60,
};
const SETTINGS_KEY = "kiosk-dashboard.settings.v1";
function loadSettings() {
	try {
		const raw = localStorage.getItem(SETTINGS_KEY);
		if (!raw) return { ...DEFAULT_SETTINGS };
		const parsed = JSON.parse(raw);
		return { ...DEFAULT_SETTINGS, ...parsed };
	} catch { return { ...DEFAULT_SETTINGS }; }
}
function saveSettings(s) {
	try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)); } catch {}
}
const settings = loadSettings();

// --- state ---
let HISTORY_POINTS = settings.historyPoints;
const history = {};
HOSTS.forEach(h => {
	history[h] = {
		t: [], cpu: [], mem: [], netRx: [], netTx: [], lastNet: null,
	};
});
let alertsState = { down: [], pending: [], total: 0 };
let currentViewIdx = 0;
let alarming = false;
let paused = false;
let metricsCharts = {};

// --- view rotation ---
function setView(id) {
	document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === `${id}-view`));
	const idx = ROTATION.indexOf(id);
	const labels = {
		alerts: "Alerts",
		proxmox: "Proxmox · forbin",
		wifi: "WiFi · WLANs",
	};
	document.getElementById("view-name").textContent = labels[id] || `${id} · system`;
	const dots = document.getElementById("dots");
	if (dots.children.length !== ROTATION.length) {
		dots.innerHTML = ROTATION.map(() => '<span></span>').join("");
	}
	[...dots.children].forEach((d, i) => d.classList.toggle("active", i === idx));
}

function rotate() {
	if (paused) return;
	if (alarming) {
		setView("alerts");
		return;
	}
	currentViewIdx = (currentViewIdx + 1) % ROTATION.length;
	setView(ROTATION[currentViewIdx]);
}
setView(ROTATION[0]);

// Pause / Prev / Next — touchable controls
const pauseBtn = document.getElementById("pause-btn");
const prevBtn = document.getElementById("prev-btn");
const nextBtn = document.getElementById("next-btn");

function setPaused(p) {
	paused = p;
	pauseBtn.classList.toggle("paused", paused);
	pauseBtn.textContent = paused ? "▶" : "❚❚";
	pauseBtn.setAttribute("aria-label", paused ? "resume rotation" : "pause rotation");
	prevBtn.disabled = !paused;
	nextBtn.disabled = !paused;
}
function step(delta) {
	if (!paused) return;
	currentViewIdx = (currentViewIdx + delta + ROTATION.length) % ROTATION.length;
	setView(ROTATION[currentViewIdx]);
}
function bindToggle(el, fn) {
	el.addEventListener("click", fn);
	el.addEventListener("touchstart", e => { e.preventDefault(); fn(); }, { passive: false });
}
bindToggle(pauseBtn, () => setPaused(!paused));
bindToggle(prevBtn, () => step(-1));
bindToggle(nextBtn, () => step(1));

// --- alerts ---
async function fetchAlerts() {
	try {
		const r = await fetch(`/api/alerts/api/status-page/heartbeat/${STATUS_PAGE_SLUG}`, { cache: "no-store" });
		if (!r.ok) throw new Error(`HTTP ${r.status}`);
		const data = await r.json();
		const heartbeats = data.heartbeatList || {};
		const uptimeMap = data.uptimeList || {};  // keys like "<mid>_24" → 0..1

		// Names from public status page
		const namesResp = await fetch(`/api/alerts/api/status-page/${STATUS_PAGE_SLUG}`, { cache: "no-store" });
		const namesData = namesResp.ok ? await namesResp.json() : {};
		const idToName = {};
		(namesData.publicGroupList || []).forEach(g => (g.monitorList || []).forEach(m => { idToName[m.id] = m.name; }));

		const down = [], pending = [], up = [];
		const recentOutages = [];  // monitors with downtime in the visible (~100 beat) window
		const imperfect24h = [];   // monitors with <100% uptime over the last 24h (Kuma's longer view)

		for (const [mid, beats] of Object.entries(heartbeats)) {
			if (!beats.length) continue;
			const last = beats[beats.length - 1];
			const name = idToName[mid] || `monitor ${mid}`;
			if (last.status === 0) down.push({ id: mid, name, msg: last.msg, time: last.time });
			else if (last.status === 2) pending.push({ id: mid, name, msg: last.msg, time: last.time });
			else up.push({ id: mid, name });

			// Find most recent status=0 in the visible heartbeat window
			for (let i = beats.length - 1; i >= 0; i--) {
				if (beats[i].status === 0) {
					recentOutages.push({ id: mid, name, time: beats[i].time, msg: beats[i].msg || "" });
					break;
				}
			}

			// 24h uptime — shows scattered outages even if they're outside the heartbeat window
			const u24 = uptimeMap[`${mid}_24`];
			if (u24 != null && u24 < 1) {
				imperfect24h.push({ id: mid, name, uptime_24h: u24 });
			}
		}
		recentOutages.sort((a, b) => new Date(b.time) - new Date(a.time));
		imperfect24h.sort((a, b) => a.uptime_24h - b.uptime_24h);

		alertsState = {
			down, pending, up,
			total: Object.keys(heartbeats).length,
			recentOutages: recentOutages.slice(0, 3),
			imperfect24h,
		};
		renderAlerts();
	} catch (e) {
		console.warn("alerts fetch", e);
	}
}

function renderAlerts() {
	const downCount = alertsState.down.length;
	const upCount = alertsState.up.length;
	const total = alertsState.total;
	const labelEl = document.getElementById("alerts-label");
	const countEl = document.getElementById("alerts-count");
	const subEl = document.getElementById("alerts-sub");
	const list = document.getElementById("alerts-list");

	if (downCount === 0) {
		// Healthy state — show up count + 24h uptime story
		countEl.textContent = upCount;
		labelEl.textContent = `monitors up now`;
		const imperfect = alertsState.imperfect24h || [];
		if (imperfect.length === 0) {
			subEl.innerHTML = `<span style="opacity:0.85">all ${total} at 100% / 24h</span>`;
		} else {
			subEl.innerHTML = `<span style="opacity:0.85">${imperfect.length} of ${total} had outages / 24h</span>`;
		}
		// Right pane: 24h uptime breakdown (the "scattered outages" picture)
		if (imperfect.length === 0) {
			const last = alertsState.recentOutages[0];
			if (last) {
				list.innerHTML = `<li class="empty" style="padding:8px 0;font-size:14px">most recent (window)</li>` +
					`<li class="resolved"><span class="name">${escapeHtml(last.name)}</span><span class="meta">${timeAgo(last.time)}</span></li>`;
			} else {
				list.innerHTML = `<li class="empty">all ${total} monitors green / 24h</li>`;
			}
		} else {
			list.innerHTML = `<li class="empty" style="padding:8px 0;font-size:14px">24h uptime — outages</li>` +
				imperfect.slice(0, 6).map(m => {
					const pct = (m.uptime_24h * 100).toFixed(2);
					const klass = m.uptime_24h < 0.99 ? "down" : "resolved";
					return `<li class="${klass}"><span class="name">${escapeHtml(m.name)}</span><span class="meta">${pct}%</span></li>`;
				}).join("");
		}
	} else {
		// Alarming state — show down count + list
		countEl.textContent = downCount;
		labelEl.textContent = `monitor${downCount === 1 ? "" : "s"} down`;
		subEl.innerHTML = `<span style="opacity:0.85">${upCount} of ${total} up</span>`;
		const items = [...alertsState.down.map(a => ({ ...a, klass: "down" })),
		               ...alertsState.pending.map(a => ({ ...a, klass: "pending" }))];
		list.innerHTML = items.slice(0, 6).map(a =>
			`<li class="${a.klass}"><span class="name">${escapeHtml(a.name)}</span><span class="meta">${escapeHtml(a.msg || a.klass)}</span></li>`
		).join("");
	}

	document.getElementById("alert-counter").textContent =
		downCount === 0 ? `${total} monitors up` : `${downCount} down · ${upCount} up`;
	const wasAlarming = alarming;
	alarming = downCount > 0;
	document.getElementById("alerts-view").classList.toggle("alarming", alarming);
	document.getElementById("ftr").classList.toggle("alarming", alarming);
	if (alarming && !wasAlarming) setView("alerts");
}

function timeAgo(timeStr) {
	if (!timeStr) return "—";
	const t = new Date(timeStr.replace(" ", "T") + (timeStr.endsWith("Z") ? "" : "Z"));
	const sec = Math.floor((Date.now() - t.getTime()) / 1000);
	if (sec < 60) return `${sec}s ago`;
	if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
	if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
	return `${Math.floor(sec / 86400)}d ago`;
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
	const days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
	const months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
	document.getElementById("date").textContent =
		`${days[d.getDay()]} · ${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

async function fetchOutsideTemp() {
	try {
		const r = await fetch("/api/extras/weather", { cache: "no-store" });
		if (!r.ok) return;
		const j = await r.json();
		if (j.temp_f != null) {
			document.getElementById("temp").textContent = `${Math.round(j.temp_f)}°F`;
		}
	} catch (e) { /* swallow */ }
}

async function fetchProxmox() {
	try {
		const r = await fetch("/api/extras/proxmox", { cache: "no-store" });
		if (!r.ok) return;
		renderProxmox(await r.json());
	} catch (e) { /* swallow */ }
}

function renderProxmox(d) {
	const view = document.getElementById("proxmox-view");
	const nodes = (d.nodes || []);
	if (!nodes.length) {
		view.innerHTML = `<div class="extras-empty">no proxmox data</div>`;
		return;
	}
	view.innerHTML = nodes.map(n => {
		const offline = n.status !== "online";
		const cpu = offline ? "—" : `${n.cpu_pct.toFixed(0)}%`;
		const mem = offline ? "—" : `${n.mem_pct.toFixed(0)}%`;
		const up = offline ? "—" : fmtUptime(n.uptime_seconds);
		const memBar = offline ? 0 : Math.min(100, n.mem_pct);
		const cpuBar = offline ? 0 : Math.min(100, n.cpu_pct);
		return `
			<div class="pve-node ${offline ? "offline" : ""}">
				<div class="pve-name">${escapeHtml(n.name)}</div>
				<div class="pve-status">${offline ? "OFFLINE" : "online"}</div>
				<div class="pve-row"><span class="pve-l">cpu</span><span class="pve-v">${cpu}</span></div>
				<div class="pve-bar"><div style="width:${cpuBar}%;background:#6cc5ff"></div></div>
				<div class="pve-row"><span class="pve-l">mem</span><span class="pve-v">${mem}</span></div>
				<div class="pve-bar"><div style="width:${memBar}%;background:#a78bfa"></div></div>
				<div class="pve-row"><span class="pve-l">up</span><span class="pve-v">${up}</span></div>
			</div>`;
	}).join("");
}

function fmtUptime(sec) {
	if (!sec || sec <= 0) return "—";
	const d = Math.floor(sec / 86400);
	const h = Math.floor((sec % 86400) / 3600);
	if (d > 0) return `${d}d ${h}h`;
	const m = Math.floor((sec % 3600) / 60);
	return `${h}h ${m}m`;
}

async function fetchWifi() {
	try {
		const r = await fetch("/api/extras/wifi", { cache: "no-store" });
		if (!r.ok && r.status !== 502) return;
		renderWifi(await r.json());
	} catch (e) { /* swallow */ }
}

function renderWifi(d) {
	const view = document.getElementById("wifi-view");
	const wlans = (d.wlans || []).filter(w => w.enabled !== false);
	if (d.error || !wlans.length) {
		let msg;
		if (d.error && (d.error.includes("backoff") || d.error.includes("429"))) {
			const m = d.error.match(/(\d+)\s*s/);
			const sec = m ? Number(m[1]) : null;
			msg = sec != null
				? `UniFi controller cooling off — ${fmtCooldown(sec)} until next try`
				: "UniFi controller cooling off…";
		} else if (d.error) {
			msg = "WiFi data unavailable";
		} else {
			msg = "no wifi data";
		}
		view.innerHTML = `<div class="extras-empty">${escapeHtml(msg)}</div>`;
		return;
	}
	view.innerHTML = wlans.slice(0, 4).map(w => {
		const tx = fmtRate(w.tx_bytes_per_sec);
		const rx = fmtRate(w.rx_bytes_per_sec);
		const cu = w.channel_utilization_pct != null ? `${w.channel_utilization_pct}%` : "—";
		const sat = w.satisfaction_pct != null ? `${w.satisfaction_pct}%` : "—";
		return `
			<div class="wifi-net">
				<div class="wifi-ssid">${escapeHtml(w.ssid)}</div>
				<div class="wifi-grid">
					<div><span class="wifi-l">clients</span><span class="wifi-v">${w.num_clients}</span></div>
					<div><span class="wifi-l">tx</span><span class="wifi-v">${tx}</span></div>
					<div><span class="wifi-l">rx</span><span class="wifi-v">${rx}</span></div>
					<div><span class="wifi-l">ch util</span><span class="wifi-v">${cu}</span></div>
					<div><span class="wifi-l">sat</span><span class="wifi-v">${sat}</span></div>
					<div><span class="wifi-l">band</span><span class="wifi-v">${escapeHtml(w.band || "—")}</span></div>
				</div>
			</div>`;
	}).join("");
}

function fmtCooldown(sec) {
	if (sec <= 0) return "any moment now";
	if (sec < 60) return `~${sec}s`;
	const m = Math.floor(sec / 60);
	const s = sec % 60;
	return s > 0 ? `~${m}m ${s}s` : `~${m}m`;
}

function fmtRate(bytesPerSec) {
	if (!bytesPerSec || bytesPerSec < 0) return "0";
	const bps = bytesPerSec * 8;
	if (bps < 1e3) return `${bps.toFixed(0)} bps`;
	if (bps < 1e6) return `${(bps / 1e3).toFixed(1)} Kbps`;
	if (bps < 1e9) return `${(bps / 1e6).toFixed(1)} Mbps`;
	return `${(bps / 1e9).toFixed(2)} Gbps`;
}

// --- boot ---
fetchAlerts();
HOSTS.forEach(h => fetchHostMetrics(h));
tickClock();

fetchOutsideTemp();
fetchProxmox();
fetchWifi();

const timers = {};
function applyTimers() {
	Object.values(timers).forEach(t => clearInterval(t));
	timers.alerts = setInterval(fetchAlerts, settings.alertsMs);
	timers.metrics = setInterval(() => HOSTS.forEach(h => fetchHostMetrics(h)), settings.metricsMs);
	timers.proxmox = setInterval(fetchProxmox, 5_000);
	timers.wifi = setInterval(fetchWifi, 8_000);
	timers.clock = setInterval(tickClock, 1000);
	timers.rotate = setInterval(rotate, settings.rotationMs);
	timers.weather = setInterval(fetchOutsideTemp, 60_000);
}
applyTimers();

// --- settings modal ---
const SETTINGS_OPTIONS = {
	rotationMs: [
		[2000, "2 sec"], [5000, "5 sec"], [8000, "8 sec (default)"],
		[12000, "12 sec"], [20000, "20 sec"], [30000, "30 sec"],
	],
	metricsMs: [
		[2000, "2 sec"], [3000, "3 sec (default)"], [5000, "5 sec"],
		[10000, "10 sec"], [30000, "30 sec"],
	],
	alertsMs: [
		[3000, "3 sec"], [5000, "5 sec (default)"], [10000, "10 sec"],
		[30000, "30 sec"], [60000, "60 sec"],
	],
	historyPoints: [
		[30, "30 points"], [60, "60 points (default)"], [90, "90 points"],
		[120, "120 points"], [180, "180 points"],
	],
};
function populateSettingsUI() {
	for (const [key, opts] of Object.entries(SETTINGS_OPTIONS)) {
		const sel = document.getElementById(`opt-${key.replace("Ms","").replace("Points","")}`);
		if (!sel) continue;
		sel.innerHTML = opts.map(([v, label]) =>
			`<option value="${v}">${label}</option>`
		).join("");
		sel.value = String(settings[key]);
		sel.addEventListener("change", () => {
			settings[key] = Number(sel.value);
			saveSettings(settings);
			HISTORY_POINTS = settings.historyPoints;
			applyTimers();
		});
	}
}
populateSettingsUI();
document.getElementById("settings-version").textContent =
	`kiosk-dashboard v${KIOSK_VERSION} · ${KIOSK_VERSION_DATE}`;

const settingsModal = document.getElementById("settings-modal");
const settingsBtn = document.getElementById("settings-btn");
function openSettings() { settingsModal.hidden = false; }
function closeSettings() { settingsModal.hidden = true; }
bindToggle(settingsBtn, openSettings);
bindToggle(document.getElementById("settings-close"), closeSettings);
bindToggle(document.getElementById("settings-reset"), () => {
	Object.assign(settings, DEFAULT_SETTINGS);
	saveSettings(settings);
	HISTORY_POINTS = settings.historyPoints;
	populateSettingsUI();
	applyTimers();
});
settingsModal.addEventListener("click", e => {
	if (e.target === settingsModal) closeSettings();
});
