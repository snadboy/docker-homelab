# container-watchdog

Aggregate container health monitor for the homelab. Polls the
[`sb-traefik-http-provider`](https://sb-traefik.isnadboy.com) inventory and
reports a single Uptime Kuma Push monitor heartbeat — `up` when every
container is `running` and not flagged `(unhealthy)` and every host is
`connected`, `down` with a message naming the offenders otherwise.

Runs on `utilities`. Outbound HTTPS only (revp + Uptime Kuma push URL); no
Docker socket and no SSH.

## Sources

- `GET /api/containers` on revp — container `Name`, `host`, `State`, `Status`
- `GET /api/hosts` on revp — per-host SSH connection state

## Alert rules

A container is flagged when `State != "running"` or `Status` contains
`(unhealthy)`. A host is flagged when `status != "connected"`.

## Configuration

See `.env.example`. Required: `PUSH_URL` (the Uptime Kuma monitor's heartbeat
URL with token).

## Notification routing

The Uptime Kuma "Container Watchdog" Push monitor goes DOWN when this service
reports any issue; from there Uptime Kuma's own notification settings (Gotify,
etc.) handle delivery. To silence during planned work, use Uptime Kuma's
maintenance window feature.
