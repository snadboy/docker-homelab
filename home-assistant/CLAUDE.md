# Topic: ha

Home Assistant config, automations, Matter/Thread, devices, and the notification stack.
Work here is mostly **MCP tools and SSH**, not this compose file.

## Ask me things like
- "Why is \<device\> unavailable?" / "what happened to the FP300s?"
- "Did the bathroom fan latch on again last night?"
- "Is the Thread mesh healthy?" / "which border routers are up?"
- "Why didn't I get a notification for X?" / "is my phone still a live notify target?"
- "What automations fired between 2 and 4 AM?"
- "Rename this device's entities without breaking anything"

## What's open

Device names, entity IDs, VM numbers, and current trials live in `CLAUDE.local.md`
(gitignored — this repo is public). Read it first; it carries the running state and the
deployment-specific "never do this" entries that matter more than anything below.

Structural facts that aren't site-specific:

- **Notifications are one-way.** Replace-in-place, grouping, `alert_once`, and the
  ongoing status card are live (see `~/projects/docs/notifications.md`). The next step
  is **actionable notifications** — `actions:` in the payload →
  `mobile_app_notification_action` events — so a push can carry [Restart] / [Snooze]
  instead of only reporting.
- 5 of 31 automations are clock-driven; two of them are the only dead-man's switches in
  the whole homelab (Kuma heartbeat pushes). See
  `~/projects/docs/scheduled-work.md`.

## Skills
`/ha-audit` · `/home-assistant-manager` · `/ha-rename-entities` · `/matter-health` ·
`/thread-maintenance`

## Never do this
- **Never rename entities by hand.** Use `/ha-rename-entities`; direct renames break
  automation, script, scene, and dashboard references silently.
- **Don't casually delete the Nest integration.** It has no Reconfigure flow, and adding
  cameras or doorbells requires a full delete-and-re-add with a Pub/Sub subscription.
- **More, and more important, in `CLAUDE.local.md`** — the deployment-specific ones
  (which add-ons are stopped on purpose, which scenes must never be activated) are the
  ones that actually cause damage here.

## Reads that silently lie
- **Logbook queries truncate without warning** — never filter by `entity_id`, keep
  windows ≤12 h, and cross-check against `ha_get_history`.
- BusyBox `grep` rejects `--binary-files=`; `xargs grep` masks matches via exit status;
  `entity_registry/list` hides `device_class` overrides; group helpers don't inherit
  `device_class`/icon.
- A re-commissioned Matter device returns with its prior `disabled_by: user` flag intact
  — it looks like commissioning failed but didn't. Fix with `disabled_by: null` + reload.
- Verify any "nothing found" a second way before deleting or renaming on it.
- **Nest Hubs reboot nightly ~2–4 AM.** Brief Thread blips every night are normal, not an
  outage. The garage Eve voltage sensor is the no-UPS canary for ruling out a real one.

## Deeper
`~/projects/docs/home-assistant.md` · `~/projects/docs/notifications.md` ·
`~/projects/docs/thread-matter.md` · `~/projects/docs/scheduled-work.md`
