# Topic: ha

Working directory for a Remote Control topic session covering Home Assistant config,
automations, Matter/Thread, and devices. Work here is mostly **MCP tools and SSH**, not
this compose file.

## Skills
`/ha-audit` · `/home-assistant-manager` · `/ha-rename-entities` · `/matter-health` ·
`/thread-maintenance`

## Never do this
- **Never rename entities by hand.** Use `/ha-rename-entities`; direct renames break
  automation, script, scene, and dashboard references silently.
- **Don't casually delete the Nest integration.** It has no Reconfigure flow, and adding
  cameras or doorbells requires a full delete-and-re-add with a Pub/Sub subscription.

## Reads that silently lie
Logbook queries truncate without warning — never filter by `entity_id`, keep windows
≤12 h, and cross-check against `ha_get_history`. Verify any "nothing found" a second way
before deleting or renaming on it.

<!-- Deployment-specific state lives in home-assistant/CLAUDE.local.md (gitignored). -->
