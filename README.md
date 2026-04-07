# Wiener Netze Smart Meter — Home Assistant Integration

Home Assistant custom component that fetches energy consumption data from the Wiener Netze Smart Meter portal and inserts it as hourly statistics for the Energy Dashboard.

## Features

- Fetches 15-minute interval data from Wiener Netze, aggregates to hourly values
- Three energy roles: **Total** (V002), **Grid/Restnetzbezug** (G001), **PV/Eigendeckung** (G003)
- Inserts **external statistics** for the HA Energy Dashboard — no conflicts with HA's auto-recorded statistics
- Timezone-correct day grouping — cumulative sums reset at local midnight (handles CET/CEST automatically)
- Meter reading sensor showing the current counter value (kWh)
- Diagnostic sensor showing last import timestamp
- Service action `wiener_netze_smart_meter.fetch_data` with configurable `days` parameter — no automatic polling, fully controlled via HA automations
- Two auth methods: KEYCLOAK_IDENTITY cookie or username/password

## Installation

1. Copy the `custom_components/wiener_netze_smart_meter` folder into the `custom_components` directory of your Home Assistant instance.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for "Wiener Netze Smart Meter".
3. **Step 1:** Choose authentication method:
   - **KEYCLOAK_IDENTITY Cookie** — visit https://smartmeter-web.wienernetze.at/, open browser developer tools, and copy the `KEYCLOAK_IDENTITY` cookie value.
   - **Username & Password** — enter your log.wien credentials (may not be supported by the Keycloak client).
4. **Step 2:** Enter your credentials and meter details:
   - **Geschaeftspartner** — your user ID (e.g., `1202381355`)
   - **Zaehlpunktnummer** — your meter number (e.g., `AT0010000000000000001000015444485`)

## Usage

The integration does **not** poll automatically. Use the service action to fetch data:

### Service: `wiener_netze_smart_meter.fetch_data`

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `days`    | 7       | 1–365 | Number of days in the past to fetch data for |

### Daily automation example

```yaml
automation:
  - alias: "Fetch Smart Meter Data Daily"
    trigger:
      - platform: time
        at: "04:00:00"
    action:
      - service: wiener_netze_smart_meter.fetch_data
        data:
          days: 7
```

### Initial bulk import

Call the service once manually with a larger window to backfill historical data:

```yaml
service: wiener_netze_smart_meter.fetch_data
data:
  days: 60
```

### Entities

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.smart_meter_reading_*` | Energy | Meter counter value (kWh) |
| `sensor.smart_meter_import_status_*` | Diagnostic | Last import timestamp + imported hours per role |

### External Statistics (Energy Dashboard)

The integration inserts external statistics visible in **Developer Tools → Statistics** and usable in the **Energy Dashboard**:

| Statistic ID | Role | Description |
|-------------|------|-------------|
| `wiener_netze_smart_meter:total_*` | V002 | Total consumption |
| `wiener_netze_smart_meter:grid_*` | G001 | Grid consumption (Restnetzbezug) |
| `wiener_netze_smart_meter:pv_*` | G003 | PV self-consumption (Eigendeckung) |

To use in the Energy Dashboard: **Settings → Dashboards → Energy → Add consumption/production** and search for `wiener_netze_smart_meter`.

## Upgrading from v1.x

If upgrading from a version that used entity-linked statistics (`sensor.smart_meter_total_*`, `sensor.smart_meter_grid_*`, `sensor.smart_meter_pv_*`):

1. **Delete old statistics**: Developer Tools → Statistics → search "smart_meter" → delete old entries
2. **Remove stale entities**: The old energy sensor entities will show as "unavailable" — delete them from the entity registry
3. **Re-import**: Call `wiener_netze_smart_meter.fetch_data` service
4. **Reconfigure Energy Dashboard**: Add the new external statistics (`wiener_netze_smart_meter:total_*`, etc.)

## Notes

- Data from Wiener Netze can be delayed by 2–7 days. Fetching 7 days covers the typical delay.
- Cumulative sums reset at local midnight each day (timezone-aware, handles CET/CEST). The HA Energy Dashboard handles daily-resetting meters natively.
- The KEYCLOAK_IDENTITY cookie expires periodically — you'll need to re-enter it when authentication fails.
