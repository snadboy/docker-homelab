# Topic: unifi

Working directory for a Remote Control topic session covering the network: WANs,
switches, APs, firewall zones. API work, not this compose file.

## Skills
`/unifi` · `/unifi-audit` · `/wan-pin`

## Never do this
- **Never retry a failed controller login quickly.** It IP-locks for >10 min and each
  retry *refreshes* the lockout. Back off ≥30 min.
- **Never point an Uptime Kuma ping monitor at a Tailscale or mDNS name.** The container
  cannot resolve them and reports a false `down`. Target a reserved LAN IP and verify
  from inside the container.

<!-- Site-specific state lives in unifi-toolkit/CLAUDE.local.md (gitignored). -->
