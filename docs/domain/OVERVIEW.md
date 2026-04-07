# Domain Overview

## Purpose
Documents the business domain, core entities, terminology, external integrations, and data flow of the Wiener Netze Smart Meter integration.

## Responsibilities
- Defining domain concepts and their relationships
- Documenting the glossary of Austrian energy metering terms
- Describing feature boundaries and external integration points

## Non-Responsibilities
- Technical implementation details -- see [Architecture](../tech/ARCHITECTURE.md)
- API endpoints and auth flows -- see [Tech Stack](../tech/TECH-STACK.md)

## Overview

### Domain Classification
Smart home / energy management integration. Bridges the Wiener Netze utility portal to Home Assistant's Energy Dashboard, making Austrian smart meter consumption data visible and usable for energy tracking and automations.

### Core Entities

**Zaehlpunkt (Meter Point)** -- The physical electricity meter, identified by a Zaehlpunktnummer (33-character AT-prefix string, e.g. `AT0010000000000000001000015444485`). Primary keying entity for all data. One config entry per Zaehlpunkt.

**Geschaeftspartner (Business Partner)** -- Customer account identifier at Wiener Netze (numeric string, e.g. `1202381355`). Scopes all API calls to a specific customer.

**Bewegungsdaten (Movement Data)** -- Raw 15-minute interval energy measurement records. Each record carries a `zeitpunktVon` (ISO timestamp) and a `wert` (float, kWh).

**Rolle (Energy Role)** -- Code distinguishing the type of energy flow in a measurement series:
- `V002` -- Gesamtverbrauch (total consumption)
- `G001` -- Restnetzbezug (grid draw)
- `G003` -- Eigendeckung (PV self-coverage)

**Zaehlwerk/Messwert (Meter Reading)** -- Cumulative counter value on the physical meter. Monotonically increasing float in kWh.

**Hourly Statistics** -- Aggregated output unit. 15-minute Bewegungsdaten summed into hourly buckets, accumulated into daily-resetting cumulative sums, inserted as HA external statistics.

**External Statistic** -- HA recorder concept for data from outside HA's sensor history. Identified by `wiener_netze_smart_meter:{role_name}_{zpn_suffix}` (e.g. `wiener_netze_smart_meter:total_15444485`).

### Terminology Glossary

| Term | Translation | Meaning |
|------|-------------|---------|
| Bewegungsdaten | Movement data | 15-minute interval metering records |
| Zaehlpunktnummer (ZPN) | Meter point number | Austrian energy market identifier for a physical metering point |
| Geschaeftspartner | Business partner | Customer/account ID in the Wiener Netze system |
| Rolle | Role | Data role code (V002/G001/G003) for energy flow type |
| Restnetzbezug (G001) | Grid consumption | Electricity drawn from the public grid |
| Eigendeckung (G003) | PV self-coverage | Electricity from rooftop PV consumed on-site |
| Gesamtverbrauch (V002) | Total consumption | Total electricity consumption regardless of source |
| Messwert | Measurement value | Individual measurement -- counter reading or interval delta |
| KEYCLOAK_IDENTITY | -- | Session cookie from log.wien Keycloak realm |

### Feature Boundaries

- **Authentication**: Owns both auth paths (cookie PKCE, password grant). Produces Bearer token. Depends on: Keycloak endpoints at log.wien.
- **API Data Fetching**: Owns HTTP calls to Wiener Netze API endpoints. Parses JSON to Python dicts. Depends on: access token, aiohttp session.
- **Data Aggregation & Statistics**: Owns transformation pipeline: raw 15-min records -> hourly sums -> daily-resetting cumulative sums -> HA external statistics. Depends on: api_client, HA recorder, HA timezone config.
- **Sensor Entities**: Read-only views over coordinator data. Two sensors per meter: diagnostic (last import timestamp) and meter reading (cumulative kWh).
- **Service Action**: Owns `fetch_data` service. Iterates all coordinators. Triggered by HA automations.
- **Configuration Flow**: Two-step UI flow with live credential validation. Deduplicates by Zaehlpunktnummer.

### External Integrations

- **Wiener Netze Smart Meter API** (`service.wienernetze.at/sm/api`) -- Primary data source for consumption data and meter readings
- **log.wien Keycloak** (`log.wien/auth/realms/logwien`) -- Authentication authority issuing Bearer tokens
- **Home Assistant Recorder** -- Receives external statistics for the Energy Dashboard

### Data Timing
- Wiener Netze data can be delayed 2-7 days from the actual consumption date
- Fetching 7 days covers the typical delay window
- Cumulative sums reset to 0 each calendar day at midnight (local time)
- HA Energy Dashboard handles daily-resetting meters natively

## Dependencies
- Austrian smart metering data format conventions (Energiewirtschaft)
- Wiener Netze API availability and response format
- log.wien Keycloak session management

## Design Decisions
- Daily-resetting cumulative sums rather than monotonically increasing totals. Rationale: HA Energy Dashboard handles daily resets natively; avoids complex state management across days.
- Three sequential API calls per fetch (one per role). Roles are independent data streams from the same endpoint.
- KEYCLOAK_IDENTITY cookie as primary auth. Rationale: simpler than password flow; avoids issues with Keycloak client support for resource owner password grant.

## Known Risks
- KEYCLOAK_IDENTITY cookie expires periodically, requiring manual re-entry
- Wiener Netze API format changes could break parsing without warning
- No documented SLA or rate limits for the Wiener Netze API

## Extension Guidelines
- New energy roles: Add role code to `const.py`, add to the fetch loop in `coordinator.py`
- New data types from Wiener Netze: Add endpoint to `api_client.py`, processing to `coordinator.py`
- Additional sensor types: Add entity class to `sensor.py` reading from coordinator data
