const API_URL = 'https://n8n.isnadboy.com/webhook/homelab-status';
const REFRESH_INTERVAL = 60000;

let lastData = null;
let fetchError = false;

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
  return `${hours}h ago`;
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

function renderNetwork(data) {
  const n = data.network || {};
  let html = '';

  // WAN Status
  html += '<div class="section-title">WAN</div>';
  const wanOk = n.wan?.status === 'ok';
  html += `<div class="stat-row">
    <span class="stat-label"><span class="status-dot ${wanOk ? 'ok' : 'error'}"></span>WAN (${n.wan?.isp || 'Unknown'})</span>
    <span class="stat-value">${n.wan?.ip || 'N/A'} / ${n.wan?.latency || 0}ms</span>
  </div>`;

  if (n.wan2) {
    html += `<div class="stat-row">
      <span class="stat-label"><span class="status-dot ok"></span>WAN2 (Backup)</span>
      <span class="stat-value">${n.wan2.ip ? n.wan2.ip + ' / ' : ''}${n.wan2.latency || 0}ms</span>
    </div>`;
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

  // Speedtest
  if (n.speedtest) {
    html += '<div class="section-title">Last Speedtest</div>';
    if (n.speedtest.wan) {
      const s = n.speedtest.wan;
      html += `<div class="stat-row">
        <span class="stat-label">WAN</span>
        <span class="stat-value">${s.down}&darr; / ${s.up}&uarr; Mbps (${s.latency}ms)</span>
      </div>`;
    }
    if (n.speedtest.wan2) {
      const s = n.speedtest.wan2;
      html += `<div class="stat-row">
        <span class="stat-label">WAN2</span>
        <span class="stat-value">${s.down}&darr; / ${s.up}&uarr; Mbps (${s.latency}ms)</span>
      </div>`;
    }
  }

  // Devices & WiFi
  if (n.devices) {
    html += '<div class="section-title">Devices & WiFi</div>';
    html += `<div class="stat-row">
      <span class="stat-label">APs</span>
      <span class="stat-value">${n.devices.apsOnline}/${n.devices.apsTotal} online</span>
    </div>`;
    html += `<div class="stat-row">
      <span class="stat-label">Switches</span>
      <span class="stat-value">${n.devices.switchesOnline}/${n.devices.switchesTotal} online</span>
    </div>`;
  }

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

  // Device detail table
  if (n.devices?.list && n.devices.list.length > 0) {
    const devCount = n.devices.list.length;
    html += `<details class="detail-dropdown">
      <summary class="detail-summary">${devCount} devices</summary>
      <table class="detail-table">
        <tr><th>Name</th><th>Type</th><th>IP</th><th>Status</th><th>Clients</th><th>Uptime</th></tr>`;
    for (const d of n.devices.list) {
      const online = d.state === 1;
      const cls = !online ? ' class="stopped"' : (d.satisfaction !== undefined && d.satisfaction < 50) ? ' class="warn"' : '';
      html += `<tr${cls}>
        <td>${d.name}</td>
        <td>${deviceTypeName(d.type)}</td>
        <td>${d.ip}</td>
        <td><span class="status-dot ${online ? 'ok' : 'error'}"></span>${online ? 'Online' : 'Offline'}</td>
        <td>${d.clients || 0}</td>
        <td>${formatUptime(d.uptime)}</td>
      </tr>`;
    }
    html += '</table></details>';
  }

  // Tunnels
  if (n.tunnels && n.tunnels.length > 0) {
    html += '<div class="section-title">Cloudflare Tunnels</div>';
    html += '<div class="tunnel-grid">';
    for (const t of n.tunnels) {
      const ok = t.state === 'running';
      html += `<span class="tunnel-chip ${ok ? 'ok' : 'down'}">${ok ? '&check;' : '&cross;'} ${tunnelName(t.name)}</span>`;
    }
    html += '</div>';
  }

  document.getElementById('network-body').innerHTML = html;
}

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
        html += `<details class="detail-dropdown">
          <summary class="detail-summary">${guestParts.join(', ')}</summary>
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

function renderServices(data) {
  const s = data.services || {};
  let html = '';

  for (const host of (s.hosts || [])) {
    const sorted = [...(host.containers || [])].sort((a, b) => {
      if (a.state === 'running' && b.state !== 'running') return -1;
      if (a.state !== 'running' && b.state === 'running') return 1;
      return a.name.localeCompare(b.name);
    });

    const containerCount = sorted.length;

    html += `<details class="detail-dropdown" open>
      <summary class="detail-summary">
        <span>${host.name}</span>
        <span style="font-size:12px">${containerCount} containers</span>
      </summary>
      <div class="chip-grid" style="margin-top:6px">`;

    for (const c of sorted) {
      const isUnhealthy = (c.status || '').includes('unhealthy');
      let cls = c.state;
      if (isUnhealthy) cls = 'unhealthy';
      const updateCls = c.hasUpdate ? ' has-update' : '';
      html += `<span class="chip ${cls}${updateCls}" title="${c.status}">${c.name}${c.hasUpdate ? '<span class="update-badge">&uarr;</span>' : ''}</span>`;
    }

    html += '</div>';

    // Container detail table
    html += `<table class="detail-table">
      <tr><th>Container</th><th>Version</th><th>Up Since</th><th>Status</th></tr>`;
    for (const c of sorted) {
      const isStopped = c.state !== 'running';
      const rowCls = isStopped ? ' class="stopped"' : '';
      // Parse uptime from status like "Up 3 hours (healthy)"
      const upSince = c.status || '';
      html += `<tr${rowCls}>
        <td>${c.name}</td>
        <td>${c.version || '-'}${c.hasUpdate ? ' <span class="update-badge">&uarr;</span>' : ''}</td>
        <td>${upSince}</td>
        <td>${c.state}</td>
      </tr>`;
    }
    html += '</table></details>';
  }

  if (s.summary) {
    const sm = s.summary;
    html += `<div class="services-summary">
      <span class="status-ok">${sm.running} running</span>`;
    if (sm.stopped > 0) html += `<span class="status-error">${sm.stopped} stopped</span>`;
    if (sm.unhealthy > 0) html += `<span class="status-warn">${sm.unhealthy} unhealthy</span>`;
    html += '</div>';
  }

  document.getElementById('services-body').innerHTML = html;
}

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
    <span class="stat-label">Pending Requests</span>
    <span class="stat-value">${m.overseerr?.pendingRequests || 0}</span>
  </div>`;
  html += '</div>';

  document.getElementById('media-body').innerHTML = html;
}

function render(data) {
  renderNetwork(data);
  renderProxmox(data);
  renderServices(data);
  renderMedia(data);
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

// Update the "Updated Xm ago" text every 10 seconds
setInterval(() => updateHeader(lastData), 10000);

// Initial fetch
fetchData();

// Auto-refresh
setInterval(fetchData, REFRESH_INTERVAL);
