# Homepage Collapsible Groups

## Overview

Homepage groups can be configured to be expanded or collapsed by default, reducing visual clutter and improving dashboard organization.

## Configuration

In `settings.yaml`, add the `expanded` property to each group in the layout section:

```yaml
layout:
  Group Name:
    style: row
    columns: 3
    expanded: true   # Always expanded
    # or
    expanded: false  # Collapsed by default (click to expand)
```

## Current Configuration

### Always Expanded (frequently accessed)
- **Media Management** - Sonarr, Radarr, Prowlarr, Overseerr, SABnzbd, Agregarr
- **Media Server** - Plex, Tautulli
- **Smart Home** - Home Assistant

### Collapsed by Default (infrastructure/monitoring)
- **Proxmox Cluster** - 3 Proxmox VE nodes
- **Backup Storage** - PBS Alexandria, PBS Svalbard
- **Infrastructure** - Traefik, Dockhand, Uptime Kuma, Gotify, etc.

## Benefits

1. **Reduced Visual Clutter** - Only show what you need most often
2. **Faster Loading** - Collapsed groups don't render widgets initially
3. **Better Organization** - Logical separation of frequently vs. occasionally accessed services
4. **User Control** - Click any group header to expand/collapse on demand

## Customization

To change which groups are expanded:

1. Edit `settings.yaml` in the Homepage config volume
2. Change `expanded: true` or `expanded: false` for any group
3. Restart the Homepage container or wait for auto-reload

Example:
```yaml
layout:
  Infrastructure:
    style: row
    columns: 3
    expanded: true  # Change to true to always show
```

## Group Interaction

- **Collapsed groups** show only the group header
- **Click the header** to expand and view services
- **State persists** during the browser session (resets on page reload)
- **Widgets in collapsed groups** don't make API calls until expanded (improves performance)

---

**Last Updated:** 2026-02-07
**Feature:** Collapsible groups for better dashboard organization
