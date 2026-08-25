# Topic: unifi

The network: WANs and failover, switches and PoE, APs and RF, clients, VLANs, firewall
zones, DNS. API work, not this compose file.

## Ask me things like
- "Is anything offline?" / "which AP is congested?"
- "What's WAN-pinned right now?" / "send \<host\> through WAN3"
- "Give this device a reserved IP"
- "Why can't \<client\> reach \<service\>?" (usually a zone, not a route)
- "Run a network audit" → `/unifi-audit`

## Reach
Auth is `UNIFI_USER` / `UNIFI_PASSWORD` from the shareables `.env`. The specific API
account, zone names, and current open threads are in `CLAUDE.local.md` (gitignored —
this repo is public).

Zone policy, not routing, is the usual reason cross-VLAN traffic fails. Check the zone
before you check the route.

## Skills
`/unifi` · `/unifi-audit` · `/wan-pin` · `/technitium` (DNS) · `/tailscale` ·
`/ts-service-add`

## Never do this
- **Never retry a failed controller login quickly.** It IP-locks for >10 min and each
  retry *refreshes* the lockout. Back off ≥30 min — short retries make it worse, not
  better.
- **Never point an Uptime Kuma ping monitor at a Tailscale or mDNS name.** The container
  cannot resolve them and reports a false `down`. Target a reserved **Home-VLAN** IP and
  verify from inside the container.
- **Never add individual DNS records for subdomains covered by the wildcard.** They're
  redundant and they drift. See `CLAUDE.local.md` for which zone that is.
- **Never restart an unhealthy `docktail`.** It re-registers Tailscale services, which
  then go dark pending `service-host` approval. This took 8 bedrock services down on
  2026-08-01.

## Reads that lie
`REMOTE HOST IDENTIFICATION HAS CHANGED` on a `tag:ssh` node is usually benign key churn,
not an attack. Verify with `tailscale whois <ip>` (it needs an **IP**, not a hostname —
a name returns `400 Bad Request: invalid 'addr' parameter`), then `ssh-keygen -R`.

## Deeper
`~/projects/docs/infrastructure.md` · `~/projects/docs/ts-services-migration.md` ·
`~/projects/docs/scheduled-work.md`
