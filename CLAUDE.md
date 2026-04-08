# Wiener Netze Smart Meter
> Home Assistant custom component that fetches energy consumption data from the Wiener Netze Smart Meter portal and inserts it as hourly statistics for the Energy Dashboard.

## Quick Reference
- **Install**: Copy `custom_components/wiener_netze_smart_meter/` into HA's `custom_components/` directory, restart HA
- **Test**: No automated tests configured
- **Lint**: `ruff check . && ruff format . --check` (config in `pyproject.toml`)

## Architecture Overview
Standard Home Assistant custom component with flat module layout under `custom_components/wiener_netze_smart_meter/`. Strict one-way dependency chain:

- `__init__.py` -- entry point, service registration, lifecycle
- `coordinator.py` -- DataUpdateCoordinator: fetch orchestration, aggregation, statistics insertion
- `api_client.py` -- HTTP client: auth (cookie PKCE + password grant) and API calls
- `sensor.py` -- read-only CoordinatorEntity sensors (diagnostic + meter reading)
- `config_flow.py` -- two-step UI config flow with live credential validation
- `const.py` -- all constants, URLs, role codes, config keys (single source of truth)

Data flow: HA automation triggers `fetch_data` service -> coordinator authenticates -> fetches 3 roles sequentially -> aggregates 15-min to hourly -> inserts external statistics into HA recorder.

## Tech Stack
- Python 3.11+ (Home Assistant custom component)
- aiohttp for async HTTP (HA-provided)
- voluptuous for schema validation (HA-provided)
- HA Recorder for external statistics (`async_add_external_statistics`)
- Consumes Wiener Netze Smart Meter REST API and log.wien Keycloak OIDC

## Core Conventions
- All constants in `const.py` with `UPPER_SNAKE_CASE` and prefixes (`CONF_`, `SERVICE_`, `ROLLE_`)
- Public async methods use `async_` prefix; private methods use `_` prefix
- Double quotes for strings; `%`-style formatting for `_LOGGER` calls
- Full type annotations with `X | Y` union syntax
- One-line docstrings on every module, class, and method
- Custom exceptions: `AuthenticationError`, `ApiError` in `api_client.py` with `raise ... from err` chaining
- See [CONVENTIONS.md](docs/tech/CONVENTIONS.md) for full detail

## Business Domain
Austrian smart meter energy integration. Fetches 15-minute Bewegungsdaten (consumption records) from Wiener Netze for three energy roles -- Total (V002), Grid/Restnetzbezug (G001), PV/Eigendeckung (G003) -- aggregates to hourly statistics with daily-resetting cumulative sums for the HA Energy Dashboard. See [Domain Overview](docs/domain/OVERVIEW.md) for terminology and entity details.

## Structural Risks
- No automated tests (CI runs linting and validation only)
- Hand-rolled PKCE implementation rather than vetted OAuth library
- KEYCLOAK_IDENTITY cookie expires periodically, requiring manual re-entry
- All business logic concentrated in `coordinator.py`

## Detailed Guides
- [Technical Context](docs/tech/README.md) -- architecture, tech stack, conventions
- [Domain Context](docs/domain/README.md) -- business domain, entities, terminology
- [Documentation Guide](docs/README.md) -- how to maintain these docs
