# Tech Stack

## Purpose
Documents the languages, frameworks, libraries, API patterns, and runtime dependencies of the Wiener Netze Smart Meter integration.

## Responsibilities
- Listing all technology choices and their roles in the system
- Documenting API communication patterns and auth flows
- Tracking runtime dependencies provided by Home Assistant

## Non-Responsibilities
- Project structure and module boundaries -- see [ARCHITECTURE.md](ARCHITECTURE.md)
- Coding style and naming rules -- see [CONVENTIONS.md](CONVENTIONS.md)

## Overview

### Language
- Python 3 (requires 3.11+ for modern HA compatibility)
- Uses `X | Y` union type syntax (Python 3.10+), `zoneinfo` (Python 3.9+)

### Framework
- **Home Assistant Custom Component** following the `custom_components/<domain>/` layout
- Key HA patterns used: `ConfigFlow`, `DataUpdateCoordinator`, `CoordinatorEntity`, `SensorEntity`, external statistics via `async_add_external_statistics`
- `manifest.json` declares `"dependencies": ["recorder"]` and `"config_flow": true`

### Runtime Libraries (provided by HA)
- `aiohttp` -- async HTTP client for all API communication
- `voluptuous` -- schema validation for config flow forms and service call payloads
- `homeassistant.components.recorder` -- external statistics insertion

### API Communication
The integration acts as an HTTP client consuming two external REST APIs:

1. **Wiener Netze Smart Meter API** (`service.wienernetze.at/sm/api`)
   - `/bewegungsdaten` -- 15-minute interval energy data per role
   - `/meterReading` -- cumulative meter counter value
   - Authorized with Bearer token

2. **log.wien Keycloak OIDC** (`log.wien/auth/realms/logwien/protocol/openid-connect/`)
   - Cookie-based PKCE authorization code flow (primary)
   - Resource owner password grant (secondary)
   - PKCE implemented inline using `base64`, `hashlib`, `os.urandom`

All HTTP I/O is async via the HA-managed shared `ClientSession` from `async_get_clientsession`.

### Build Tools
None. The integration is installed as a raw directory drop-in under `custom_components/`.

### CI/CD
None detected.

### Testing
No test framework, test files, or test dependencies present.

### Infrastructure
- MCP server (`ha-mcp`) in `.mcp.json` connects Claude tooling to a live HA instance for development
- No Docker, Kubernetes, or cloud deployment configs

## Dependencies
- Home Assistant core runtime (provides aiohttp, voluptuous, recorder)
- Wiener Netze Smart Meter API (external)
- log.wien Keycloak identity provider (external)

## Design Decisions
- No third-party OAuth library -- PKCE helpers are implemented inline to avoid extra dependencies in a custom component context
- No automatic polling (`update_interval=None`) -- all data fetching is user-triggered via service action, giving full control to HA automations
- No separate `requirements` declaration -- all dependencies are provided by HA runtime

## Known Risks
- No automated tests to catch regressions
- No CI pipeline to enforce code quality
- No linter or formatter configuration; style is maintained manually
- PKCE implementation is hand-rolled rather than using a vetted library

## Extension Guidelines
- New dependencies should be HA-provided where possible; if external, add to `manifest.json` `"requirements"` list
- New API endpoints follow the existing pattern in `api_client.py` using `async_get_clientsession`
- Auth flow changes must update both cookie and password paths
