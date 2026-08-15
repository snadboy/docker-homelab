# PeaNUT — UPS web dashboard

Web dashboard for the NUT server on rpi-nut (CyberPower PR1500LCDRT2U).

- Host: **utilities**
- URL: https://peanut.swallow-spectrum.ts.net (DockTail; PeaNUT auth disabled — tailnet-only)
- NUT server: `192.168.86.79:3493` (rpi-nut), user `monuser`
- Config: `peanut-data` volume → `/config/settings.yml`, seeded manually
  (contains the NUT password from shareables `.env: NUT_MONUSER_PASSWORD` — not in git)
- See `~/projects/git/nut` for the NUT server itself
