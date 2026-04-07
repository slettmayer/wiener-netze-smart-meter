# Architecture

## Purpose
Documents the project structure, module boundaries, layering, and data flow of the integration.

## Responsibilities
- Defining the module layout and each module's role
- Describing dependency direction between modules
- Documenting data flow from API to HA Energy Dashboard

## Non-Responsibilities
- Technology choices and library details -- see [TECH-STACK.md](TECH-STACK.md)
- Naming and style rules -- see [CONVENTIONS.md](CONVENTIONS.md)
- Domain terminology and business concepts -- see [Domain Overview](../domain/OVERVIEW.md)

## Overview

### Project Layout

```
custom_components/wiener_netze_smart_meter/
    __init__.py        # Entry setup, teardown, service registration
    api_client.py      # External API communication and authentication
    config_flow.py     # UI-driven config entry flow (2-step)
    const.py           # All constants, URLs, role codes, config keys
    coordinator.py     # DataUpdateCoordinator: fetch, aggregate, insert stats
    sensor.py          # SensorEntity definitions backed by coordinator
    manifest.json      # HA integration metadata
    services.yaml      # Service action schema for HA UI
    strings.json       # UI strings (English, canonical)
    translations/
        de.json
        en.json
```

All modules live flat inside one integration package. No sub-packages or feature folders.

### Layering

The integration follows a strict one-way dependency chain:

```
__init__.py (entry point, service registration)
    |
    v
coordinator.py (business logic: fetch, aggregate, insert)
    |
    v
api_client.py (HTTP client: auth + data fetch)
    |
    v
const.py (constants: URLs, keys, roles)

sensor.py --> coordinator.py (read-only view over coordinator data)
config_flow.py --> api_client.py (credential validation during setup)
```

No circular imports exist. Dependency direction is strictly downward.

### Module Responsibilities

- **`__init__.py`**: Wires coordinator to config entry lifecycle (`async_setup_entry`, `async_unload_entry`). Registers `wiener_netze_smart_meter.fetch_data` service. Iterates all configured coordinators on service call.
- **`api_client.py`**: Owns all HTTP communication. Two auth flows (cookie PKCE, password grant). Two data endpoints (bewegungsdaten, meterReading). Raises `AuthenticationError` and `ApiError`. Stateless -- no internal state caching.
- **`coordinator.py`**: Extends `DataUpdateCoordinator[dict]` with `update_interval=None`. `async_fetch(days)` orchestrates: authenticate, fetch 3 roles sequentially + meter reading, aggregate 15-min to hourly, compute daily-resetting cumulative sums, insert external statistics, update sensor data dict.
- **`sensor.py`**: Two entity classes (`SmartMeterDiagnosticSensor`, `SmartMeterReadingSensor`). Both extend `CoordinatorEntity` and read from `self.coordinator.data`. No independent state.
- **`config_flow.py`**: Two-step `ConfigFlow` (`async_step_user` -> `async_step_credentials`). Validates credentials live. Deduplicates by Zaehlpunktnummer as unique ID.
- **`const.py`**: Single source of truth for all string constants, URLs, role codes, config keys, defaults. No inline literals in other modules.

### Data Flow

1. HA automation calls `wiener_netze_smart_meter.fetch_data` service with `days` parameter
2. `__init__.py` iterates all coordinators (one per config entry / meter)
3. Coordinator authenticates via `api_client` (produces Bearer token)
4. Coordinator calls API sequentially for each role (V002, G001, G003) + meter reading
5. Raw 15-minute Bewegungsdaten are aggregated to hourly sums (`_aggregate_to_hourly`)
6. Hourly values are accumulated into daily-resetting cumulative sums
7. Statistics inserted into HA recorder via `async_add_external_statistics`
8. Sensor entities read latest values from coordinator data dict

### Multi-Meter Support

Each meter (Zaehlpunkt) gets its own config entry and coordinator instance. The service action iterates all coordinators, enabling multiple meters to be fetched in one call.

## Dependencies
- All modules depend on `const.py`
- `coordinator.py` depends on `api_client.py` and `homeassistant.components.recorder`
- `sensor.py` depends on `coordinator.py`
- `config_flow.py` depends on `api_client.py`
- `__init__.py` depends on `coordinator.py`

## Design Decisions
- Flat module structure (no sub-packages) is intentional -- the integration is small enough that a single-level layout is clearer than nested packages
- `update_interval=None` means HA's built-in polling is disabled; all fetches are explicit, preventing unnecessary API calls
- Stateless API client avoids token caching issues; a fresh token is obtained on each fetch cycle

## Known Risks
- All business logic (aggregation, cumulative sums, statistics insertion) is concentrated in `coordinator.py` -- if this grows, it should be split
- No abstraction layer between the API response format and the coordinator -- API changes require coordinator changes

## Extension Guidelines
- New data sources: Add methods to `api_client.py`, call from `coordinator.py`
- New sensor types: Add entity class to `sensor.py`, register in `async_setup_entry`
- New service actions: Register in `__init__.py`, follow existing `fetch_data` pattern
- New config options: Add to `config_flow.py` steps and `const.py` keys
