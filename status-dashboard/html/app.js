const API_URL = 'https://n8n.isnadboy.com/webhook/homelab-status';
const REFRESH_INTERVAL = 60000;

let lastData = null;
let fetchError = false;
let servicesSortBy = 'name'; // 'name' or 'host'

// ---- Tab Navigation ----

function initTabs() {
  const nav = document.getElementById('tab-nav');
  nav.addEventListener('click', (e) => {
    const btn = e.target.closest('.tab');
    if (!btn) return;
    const tabId = btn.dataset.tab;

    nav.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');

    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`${tabId}-card`).classList.add('active');
  });
}

// ---- Helpers ----

function formatUptime(seconds) {
  if (!seconds) return '0m';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function timeAgo(isoString) {
  if (!isoString) return 'never';
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins === 1) return '1m ago';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours === 1) return '1h ago';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return '1d ago';
  return `${days}d ago`;
}

function barClass(pct) {
  if (pct >= 90) return 'high';
  if (pct >= 70) return 'medium';
  return '';
}

function tunnelName(full) {
  return full.replace('cloudflare-', '').replace('cloudflared-', '');
}

function deviceTypeName(type) {
  const map = { uap: 'AP', usw: 'Switch', udm: 'Gateway', ugw: 'Gateway', udb: 'Bridge' };
  return map[type] || type;
}

// ---- Render: Network ----

function renderNetwork(data) {
  const n = data.network || {};
  let html = '';

  // WAN Status with inline speedtest
  html += '<div class="section-title">WAN</div>';
  const wanOk = n.wan?.status === 'ok';
  html += `<div class="stat-row">
    <span class="stat-label"><span class="status-dot ${wanOk ? 'ok' : 'error'}"></span>WAN (${n.wan?.isp || 'Unknown'})</span>
    <span class="stat-value">${n.wan?.ip || 'N/A'} / ${n.wan?.latency || 0}ms</span>
  </div>`;
  if (n.speedtest?.wan) {
    const s = n.speedtest.wan;
    html += `<div class="stat-row sub-row">
      <span class="stat-label"></span>
      <span class="stat-value dim">${s.down}&darr; / ${s.up}&uarr; Mbps</span>
    </div>`;
  }

  if (n.wan2) {
    const wan2Label = n.wan2.ip ? `${n.wan2.ip} / ${n.wan2.latency || 0}ms` : `Standby / ${n.wan2.latency || 0}ms`;
    html += `<div class="stat-row">
      <span class="stat-label"><span class="status-dot ok"></span>WAN2 (Backup)</span>
      <span class="stat-value">${wan2Label}</span>
    </div>`;
    if (n.speedtest?.wan2) {
      const s = n.speedtest.wan2;
      html += `<div class="stat-row sub-row">
        <span class="stat-label"></span>
        <span class="stat-value dim">${s.down}&darr; / ${s.up}&uarr; Mbps</span>
      </div>`;
    }
  }

  // Gateway
  if (n.gateway) {
    html += '<div class="section-title">Gateway</div>';
    html += `<div class="stat-row">
      <span class="stat-label">${n.gateway.name || 'Gateway'}</span>
      <span class="stat-value">FW ${n.gateway.firmware || 'N/A'}</span>
    </div>`;
    html += `<div class="stat-row">
      <span class="stat-label">CPU / Mem / Uptime</span>
      <span class="stat-value">${Math.round(n.gateway.cpu || 0)}% / ${Math.round(n.gateway.mem || 0)}% / ${formatUptime(n.gateway.uptime)}</span>
    </div>`;
  }

  // Devices & WiFi — dropdowns directly under their stat rows
  if (n.devices) {
    html += '<div class="section-title">Devices & WiFi</div>';

    const aps = n.devices.list ? n.devices.list.filter(d => d.type === 'uap') : [];
    const switches = n.devices.list ? n.devices.list.filter(d => d.type === 'usw' || d.type === 'udb') : [];

    // APs stat row
    html += `<div class="stat-row">
      <span class="stat-label">APs</span>
      <span class="stat-value">${n.devices.apsOnline}/${n.devices.apsTotal} online</span>
    </div>`;

    // AP detail dropdown directly under
    if (aps.length > 0) {
      const offlineAps = aps.filter(d => d.state !== 1).length;
      const apBadge = offlineAps > 0 ? `<span class="dropdown-alert error">${offlineAps}</span>` : '';
      html += `<details class="detail-dropdown">
        <summary class="detail-summary">${aps.length} APs${apBadge}</summary>
        <table class="detail-table">
          <tr><th>Name</th><th>IP</th><th>Clients</th><th>Sat%</th><th>Uptime</th><th>Status</th></tr>`;
      for (const d of aps) {
        const online = d.state === 1;
        const cls = !online ? ' class="stopped"' : (d.satisfaction !== undefined && d.satisfaction < 50) ? ' class="warn"' : '';
        html += `<tr${cls}>
          <td>${d.name}</td>
          <td>${d.ip}</td>
          <td>${d.clients || 0}</td>
          <td>${d.satisfaction !== undefined ? d.satisfaction + '%' : '-'}</td>
          <td>${formatUptime(d.uptime)}</td>
          <td><span class="status-dot ${online ? 'ok' : 'error'}"></span>${online ? 'Online' : 'Offline'}</td>
        </tr>`;
      }
      html += '</table></details>';
    }

    // Switches stat row
    html += `<div class="stat-row">
      <span class="stat-label">Switches</span>
      <span class="stat-value">${n.devices.switchesOnline}/${n.devices.switchesTotal} online</span>
    </div>`;

    // Switch detail dropdown directly under
    if (switches.length > 0) {
      const offlineSwitches = switches.filter(d => d.state !== 1).length;
      const swBadge = offlineSwitches > 0 ? `<span class="dropdown-alert error">${offlineSwitches}</span>` : '';
      html += `<details class="detail-dropdown">
        <summary class="detail-summary">${switches.length} Switches${swBadge}</summary>
        <table class="detail-table">
          <tr><th>Name</th><th>IP</th><th>Clients</th><th>Uptime</th><th>Status</th></tr>`;
      for (const d of switches) {
        const online = d.state === 1;
        const cls = !online ? ' class="stopped"' : '';
        html += `<tr${cls}>
          <td>${d.name}</td>
          <td>${d.ip}</td>
          <td>${d.clients || 0}</td>
          <td>${formatUptime(d.uptime)}</td>
          <td><span class="status-dot ${online ? 'ok' : 'error'}"></span>${online ? 'Online' : 'Offline'}</td>
        </tr>`;
      }
      html += '</table></details>';
    }
  }

  // WiFi stats (after device entries)
  if (n.wifi) {
    html += `<div class="stat-row">
      <span class="stat-label">WiFi Clients</span>
      <span class="stat-value">${n.wifi.clients} (${n.wifi.avgSatisfaction}% avg sat)</span>
    </div>`;
    if (n.wifi.poorCount > 0 || n.wifi.weakSignal > 0) {
      let warns = [];
      if (n.wifi.poorCount > 0) warns.push(`${n.wifi.poorCount} poor`);
      if (n.wifi.weakSignal > 0) warns.push(`${n.wifi.weakSignal} weak`);
      html += `<div class="stat-row">
        <span class="stat-label"></span>
        <span class="stat-value status-warn">${warns.join(', ')}</span>
      </div>`;
    }
  }

  // Tunnels with uptime
  if (n.tunnels && n.tunnels.length > 0) {
    html += '<div class="section-title">Cloudflare Tunnels</div>';
    html += '<div class="tunnel-grid">';
    for (const t of n.tunnels) {
      const ok = t.state === 'running';
      let uptime = '';
      if (t.status) {
        const m = t.status.match(/Up\s+(.+?)(?:\s*\(|$)/);
        if (m) uptime = ` (${m[1].trim()})`;
      }
      html += `<span class="tunnel-chip ${ok ? 'ok' : 'down'}">${ok ? '&check;' : '&cross;'} ${tunnelName(t.name)}${uptime}</span>`;
    }
    html += '</div>';
  }

  // Storage (NAS)
  if (data.storage && data.storage.length > 0) {
    html += '<div class="section-title">Storage</div>';
    for (const nas of data.storage) {
      html += `<div class="stat-row">
        <span class="stat-label"><span class="status-dot ${nas.status === 'online' ? 'ok' : 'error'}"></span>${nas.name}</span>
        <span class="stat-value">${nas.status === 'online' ? 'Online' : 'Offline'}</span>
      </div>`;
      if (nas.volumes) {
        for (const vol of nas.volumes) {
          html += `<div class="pbs-ds">
            <div class="pbs-ds-header">
              <span>${vol.name}</span>
              <span>${vol.usedGB} / ${vol.totalGB} GB (${vol.usedPct}%)</span>
            </div>
            <div class="bar"><div class="bar-fill disk ${barClass(vol.usedPct)}" style="width:${vol.usedPct}%"></div></div>
          </div>`;
        }
      }
    }
  }

  document.getElementById('network-body').innerHTML = html;
}

// ---- Render: Proxmox ----

function renderProxmox(data) {
  const p = data.proxmox || {};
  let html = '';

  for (const node of (p.nodes || [])) {
    const offline = node.status !== 'online';
    html += `<div class="pve-node">
      <div class="pve-node-header">
        <span class="pve-node-name"><span class="status-dot ${offline ? 'error' : 'ok'}"></span>${node.name}</span>
        <span class="pve-node-uptime">${offline ? 'OFFLINE' : formatUptime(node.uptime)}</span>
      </div>`;

    if (!offline) {
      html += `<div class="pve-bars">
        <span class="pve-bar-label">CPU</span>
        <div class="bar"><div class="bar-fill cpu ${barClass(node.cpu)}" style="width:${node.cpu}%"></div></div>
        <span class="bar-label">${node.cpu}%</span>

        <span class="pve-bar-label">MEM</span>
        <div class="bar"><div class="bar-fill mem ${barClass(node.memPct)}" style="width:${node.memPct}%"></div></div>
        <span class="bar-label">${node.memPct}%</span>

        <span class="pve-bar-label">DISK</span>
        <div class="bar"><div class="bar-fill disk ${barClass(node.diskPct)}" style="width:${node.diskPct}%"></div></div>
        <span class="bar-label">${node.diskPct}%</span>
      </div>`;

      // Guest summary + detail table
      const guests = node.guests || [];
      const vmCount = guests.filter(g => g.type === 'VM').length;
      const ctCount = guests.filter(g => g.type === 'CT').length;
      const guestParts = [];
      if (vmCount > 0) guestParts.push(`${node.vmsRunning}/${vmCount} VMs`);
      if (ctCount > 0) guestParts.push(`${node.ctsRunning}/${ctCount} CTs`);

      if (guests.length > 0) {
        const stoppedGuests = guests.filter(g => g.status !== 'running').length;
        const guestBadge = stoppedGuests > 0 ? `<span class="dropdown-alert warn">${stoppedGuests}</span>` : '';
        html += `<details class="detail-dropdown">
          <summary class="detail-summary">${guestParts.join(', ')}${guestBadge}</summary>
          <table class="detail-table">
            <tr><th>ID</th><th>Name</th><th>Type</th><th>Status</th><th>CPU</th><th>Mem</th></tr>`;
        for (const g of guests) {
          const isStopped = g.status !== 'running';
          const rowCls = isStopped ? ' class="stopped"' : (g.cpuPct > 80 || g.memPct > 80) ? ' class="warn"' : '';
          html += `<tr${rowCls}>
            <td>${g.vmid}</td>
            <td>${g.name}</td>
            <td>${g.type}</td>
            <td><span class="status-dot ${isStopped ? 'error' : 'ok'}"></span>${g.status}</td>
            <td>${isStopped ? '-' : g.cpuPct + '%'}</td>
            <td>${isStopped ? '-' : g.memPct + '%'}</td>
          </tr>`;
        }
        html += '</table></details>';
      } else if (node.vmsTotal > 0 || node.ctsTotal > 0) {
        html += `<div class="pve-guests">${guestParts.join(' &middot; ')}</div>`;
      }
    }

    html += '</div>';
  }

  // PBS section
  const pbs = data.pbs || {};
  if (pbs.servers && pbs.servers.length > 0) {
    html += '<div class="section-title" style="margin-top:16px">Backup Servers</div>';
    for (const srv of pbs.servers) {
      html += `<div class="pbs-card">
        <div class="pbs-header">
          <span class="pbs-name"><span class="status-dot ok"></span>${srv.name}</span>
          <span class="pbs-version">PBS ${srv.version || '?'}</span>
        </div>`;
      for (const ds of (srv.datastores || [])) {
        html += `<div class="pbs-ds">
          <div class="pbs-ds-header">
            <span>${ds.name}</span>
            <span>${ds.usedGB} / ${ds.totalGB} GB (${ds.usedPct}%)</span>
          </div>
          <div class="bar"><div class="bar-fill disk ${barClass(ds.usedPct)}" style="width:${ds.usedPct}%"></div></div>`;
        if (ds.gcState) {
          const gcTime = ds.gcLastRun ? new Date(ds.gcLastRun * 1000).toLocaleDateString() : 'never';
          html += `<div class="pbs-gc">GC: ${ds.gcState} (${gcTime})</div>`;
        }
        if (ds.lastBackups && ds.lastBackups.length > 0) {
          const backupTimes = ds.lastBackups.map(b => timeAgo(new Date(b.time * 1000).toISOString())).join(' &middot; ');
          html += `<div class="pbs-gc">Last backups: ${backupTimes}</div>`;
        }
        html += '</div>';
      }
      html += '</div>';
    }
  }

  if (p.totals) {
    html += `<div class="pve-footer">${p.totals.nodesOnline} nodes &middot; ${p.totals.vmsRunning} VMs &middot; ${p.totals.ctsRunning} CTs running</div>`;
  }

  document.getElementById('proxmox-body').innerHTML = html;
}

// ---- Render: Services (flat list with sort toggle) ----

function renderServices(data) {
  const s = data.services || {};
  let html = '';

  // Flatten all containers from all hosts into one list
  const allContainers = [];
  for (const host of (s.hosts || [])) {
    for (const c of (host.containers || [])) {
      allContainers.push({ ...c, host: host.name });
    }
  }

  // Sort toggle
  const byNameActive = servicesSortBy === 'name' ? 'active' : '';
  const byHostActive = servicesSortBy === 'host' ? 'active' : '';
  html += `<div class="sort-toggle">
    <span class="sort-label">Sort:</span>
    <button class="sort-btn ${byNameActive}" data-sort="name">Service</button>
    <button class="sort-btn ${byHostActive}" data-sort="host">Host | Service</button>
  </div>`;

  // Sort the flat list
  if (servicesSortBy === 'host') {
    allContainers.sort((a, b) => {
      const hostCmp = a.host.localeCompare(b.host);
      if (hostCmp !== 0) return hostCmp;
      return a.name.localeCompare(b.name);
    });
  } else {
    allContainers.sort((a, b) => a.name.localeCompare(b.name));
  }

  // Problems float to top within sort order
  allContainers.sort((a, b) => {
    const aProblem = a.state !== 'running' || (a.status || '').includes('unhealthy');
    const bProblem = b.state !== 'running' || (b.status || '').includes('unhealthy');
    if (aProblem && !bProblem) return -1;
    if (!aProblem && bProblem) return 1;
    return 0;
  });

  // Container table
  html += `<table class="detail-table">
    <tr><th>Service</th><th>Host</th><th>Version</th><th>Up Since</th><th>Status</th></tr>`;
  for (const c of allContainers) {
    const isStopped = c.state !== 'running';
    const isUnhealthy = (c.status || '').includes('unhealthy');
    const rowCls = isStopped ? ' class="stopped"' : isUnhealthy ? ' class="warn"' : '';
    const upSince = c.status || '';
    html += `<tr${rowCls}>
      <td>${c.name}</td>
      <td>${c.host}</td>
      <td>${c.version || '-'}${c.hasUpdate ? ' <span class="update-badge">&uarr;</span>' : ''}</td>
      <td>${upSince}</td>
      <td>${c.state}</td>
    </tr>`;
  }
  html += '</table>';

  if (s.summary) {
    const sm = s.summary;
    html += `<div class="services-summary">
      <span class="status-ok">${sm.running} running</span>`;
    if (sm.stopped > 0) html += `<span class="status-error">${sm.stopped} stopped</span>`;
    if (sm.unhealthy > 0) html += `<span class="status-warn">${sm.unhealthy} unhealthy</span>`;
    html += '</div>';
  }

  document.getElementById('services-body').innerHTML = html;

  // Attach sort toggle handlers
  document.querySelectorAll('#services-body .sort-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      servicesSortBy = btn.dataset.sort;
      renderServices(lastData);
    });
  });
}

// ---- Render: Media ----

function renderMedia(data) {
  const m = data.media || {};
  let html = '';

  // Tautulli - Active Streams
  html += '<div class="media-subsection">';
  html += '<div class="section-title">Active Streams</div>';
  if (m.tautulli && m.tautulli.activeStreams > 0) {
    for (const s of m.tautulli.streams) {
      html += `<div class="stream-item">
        <span class="stream-title">${s.title}</span>
        <span class="stream-meta">${s.user} &middot; ${s.player}</span>
      </div>`;
    }
  } else {
    html += '<div class="empty-state">No active streams</div>';
  }
  html += '</div>';

  // Sonarr
  html += '<div class="media-subsection">';
  html += `<div class="section-title">Today's Episodes (${m.sonarr?.todayCount || 0})</div>`;
  if (m.sonarr && m.sonarr.episodes && m.sonarr.episodes.length > 0) {
    for (const ep of m.sonarr.episodes) {
      const se = `S${String(ep.season).padStart(2, '0')}E${String(ep.episode).padStart(2, '0')}`;
      html += `<div class="episode-item">
        <span class="episode-title">${ep.series} - ${ep.title}</span>
        <span class="episode-meta">${se}</span>
      </div>`;
    }
  } else {
    html += '<div class="empty-state">No episodes today</div>';
  }
  html += '</div>';

  // Radarr Queue
  html += '<div class="media-subsection">';
  html += `<div class="section-title">Radarr Queue (${m.radarr?.queueCount || 0})</div>`;
  if (m.radarr && m.radarr.queue && m.radarr.queue.length > 0) {
    for (const item of m.radarr.queue) {
      html += `<div class="queue-item">
        <span class="queue-title">${item.title}</span>
        <span class="queue-meta">${item.progress}%</span>
      </div>`;
    }
  } else {
    html += '<div class="empty-state">Queue empty</div>';
  }
  html += '</div>';

  // SABnzbd
  html += '<div class="media-subsection">';
  html += '<div class="section-title">SABnzbd</div>';
  if (m.sabnzbd) {
    const status = m.sabnzbd.paused ? 'Paused' : m.sabnzbd.downloading > 0 ? `${m.sabnzbd.downloading} downloading @ ${m.sabnzbd.speed}/s` : 'Idle';
    html += `<div class="stat-row">
      <span class="stat-label">Status</span>
      <span class="stat-value">${status}</span>
    </div>`;
  }
  html += '</div>';

  // Overseerr
  html += '<div class="media-subsection">';
  html += '<div class="section-title">Overseerr</div>';
  html += `<div class="stat-row">
    <span class="stat-label">Processing Requests</span>
    <span class="stat-value">${m.overseerr?.pendingRequests || 0}</span>
  </div>`;
  html += '</div>';

  document.getElementById('media-body').innerHTML = html;
}

// ---- Render: Smart Home ----

function renderSmartHome(data) {
  const sh = data.smarthome || {};
  let html = '';

  // Thread Topology (tree layout)
  const thread = sh.thread || {};
  const matter = sh.matter || {};
  const networkName = thread.networkName || 'Unknown';
  html += `<div class="section-title">Thread Network &mdash; ${networkName}</div>`;

  // Build RLOC16 -> device name map from Matter devices
  const rlocToName = {};
  for (const d of (matter.devices || [])) {
    if (d.rloc16) rlocToName[d.rloc16] = d.name;
  }

  const allRouters = thread.routers || [];
  if (allRouters.length > 0) {
    let totalChildren = 0;
    html += '<div class="thread-tree">';
    for (const r of allRouters) {
      const isSelf = thread.selfRloc16 !== undefined &&
        parseInt(r.rloc16, 16) === thread.selfRloc16;
      const label = r.name || `Router ${r.rloc16}`;
      const selfBadge = isSelf ? ' <span class="transport-chip thread">Self</span>' : '';
      const children = r.children || [];
      totalChildren += children.length;
      html += `<div class="tree-router">
        <div class="tree-router-header">
          <span class="status-dot ok"></span>
          <span class="tree-router-name">${label}${selfBadge}</span>
          <span class="tree-router-meta">${r.rloc16}</span>
        </div>`;
      if (children.length > 0) {
        html += '<div class="tree-children">';
        for (let i = 0; i < children.length; i++) {
          const c = children[i];
          const resolved = rlocToName[c.rloc16];
          const childName = resolved || c.rloc16;
          const isLast = i === children.length - 1;
          const connector = isLast ? 'tree-connector-last' : 'tree-connector';
          const rlocLabel = resolved ? `<span class="tree-child-rloc">${c.rloc16}</span>` : '';
          html += `<div class="tree-child ${connector}">
            <span class="tree-child-name">${childName}</span>
            ${rlocLabel}
          </div>`;
        }
        html += '</div>';
      }
      html += '</div>';
    }
    html += '</div>';
    html += `<div class="stat-row">
      <span class="stat-label">Topology</span>
      <span class="stat-value">${allRouters.length} routers &middot; ${totalChildren} end devices</span>
    </div>`;
  } else {
    html += '<div class="empty-state">No Thread routers detected</div>';
  }

  // Matter Devices
  const summary = matter.summary || {};
  html += '<div class="section-title" style="margin-top:16px">Matter Devices</div>';

  html += '<div class="smarthome-summary">';
  html += `<span class="stat-chip"><strong>${summary.total || 0}</strong> devices</span>`;
  html += `<span class="stat-chip"><strong>${summary.thread || 0}</strong> thread</span>`;
  html += `<span class="stat-chip"><strong>${summary.wifi || 0}</strong> wifi</span>`;
  if (summary.offline > 0) {
    html += `<span class="stat-chip" style="color:var(--status-warn)"><strong>${summary.offline}</strong> offline</span>`;
  }
  html += '</div>';

  const devices = matter.devices || [];
  if (devices.length > 0) {
    // Preserve details open state across re-renders
    const detailsEl = document.querySelector('#smarthome-body .detail-dropdown');
    const wasOpen = detailsEl ? detailsEl.open : false;
    const offlineCount = devices.filter(d => !d.available).length;
    const badge = offlineCount > 0 ? `<span class="dropdown-alert warn">${offlineCount}</span>` : '';
    html += `<details class="detail-dropdown"${wasOpen ? ' open' : ''}>
      <summary class="detail-summary">${devices.length} Matter devices${badge}</summary>
      <div class="detail-scroll-container">
      <table class="detail-table">
        <tr><th>Name</th><th>Transport</th><th>Info</th><th>Vendor</th><th>Status</th></tr>`;
    const sorted = [...devices].sort((a, b) => {
      if (a.available !== b.available) return a.available ? 1 : -1;
      return a.name.localeCompare(b.name);
    });
    for (const d of sorted) {
      const cls = !d.available ? ' class="stopped"' : '';
      const transportCls = d.transport || 'unknown';
      let info = '-';
      if (d.transport === 'thread' && d.parentRouter) {
        info = d.parentRouter;
      } else if (d.transport === 'wifi' && d.ipv4) {
        info = d.ipv4;
      }
      html += `<tr${cls}>
        <td>${d.name}</td>
        <td><span class="transport-chip ${transportCls}">${d.transport}</span></td>
        <td class="info-cell">${info}</td>
        <td>${d.vendor || '-'}</td>
        <td><span class="status-dot ${d.available ? 'ok' : 'error'}"></span>${d.available ? 'Online' : 'Offline'}</td>
      </tr>`;
    }
    html += '</table></div></details>';
  }

  document.getElementById('smarthome-body').innerHTML = html;
}

// ---- Render All ----

function render(data) {
  renderNetwork(data);
  renderProxmox(data);
  renderServices(data);
  renderMedia(data);
  renderSmartHome(data);
}

function updateHeader(data) {
  const pulse = document.getElementById('pulse');
  const updated = document.getElementById('updated');

  if (fetchError) {
    pulse.classList.add('error');
    updated.textContent = 'Connection error';
    return;
  }

  pulse.classList.remove('error');
  updated.textContent = `Updated ${timeAgo(data?.lastUpdated)}`;
}

async function fetchData() {
  try {
    const resp = await fetch(API_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    lastData = data;
    fetchError = false;
    render(data);
    updateHeader(data);
  } catch (err) {
    console.error('Fetch error:', err);
    fetchError = true;
    updateHeader(lastData);
  }
}

// Init
initTabs();

// Update the "Updated Xm ago" text every 10 seconds
setInterval(() => updateHeader(lastData), 10000);

// Initial fetch
fetchData();

// Auto-refresh
setInterval(fetchData, REFRESH_INTERVAL);
