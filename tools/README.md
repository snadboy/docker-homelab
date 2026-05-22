# Tools

Misc helper scripts.

## wan-pin

Switch a client between WAN1 / WAN2 / WAN3 via UniFi traffic routes.

Each managed device has three traffic routes (one per WAN), all with kill-switch
on; exactly one is enabled at a time. The script just toggles the `enabled` flag
via the UniFi API — no route rewrites — so the routes stay visible / auditable
in the UniFi UI.

### Usage

```
wan-pin add <device>             # create wan1/wan2/wan3 routes (all disabled)
wan-pin <device> <1|2|3|off>     # enable that WAN, disable the others
wan-pin status <device>          # show current pin state
wan-pin list                     # all wan-pin routes (across devices)
wan-pin remove <device>          # delete all wan-pin routes for device
```

`<device>` is a MAC, a UniFi client name (the one you set in the controller), or
the device's reported hostname.

### Auth

Reads `UNIFI_URL`, `UNIFI_USER`, `UNIFI_PASSWORD` from env, falling back to
`$SHAREABLES_ROOT/.claude/.env` (default `/mnt/shareables/.claude/.env`).

### WAN labels

The WAN number → controller-name map is hardcoded near the top of the script:

```python
WAN_NAMES = {
    "1": "Internet 1",
    "2": "Internet 2",
    "3": "UniFi 5G A",
}
```

Edit if your WAN networks are labelled differently.