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
- Python 3 (requires 3.12+; ruff `target-version = "py312"`)
- Uses `X | Y` union type syntax (Python 3.10+), `datetime.UTC` alias (Python 3.11+)

### Framework
- **Home Assistant Custom Component** following the `custom_components/<domain>/` layout
- Key HA patterns used: `ConfigFlow`, `DataUpdateCoordinator`, `CoordinatorEntity`, `SensorEntity`, external statistics via `async_add_external_statistics`, `ServiceResponse` + `SupportsResponse.OPTIONAL` for service return values
- `manifest.json` declares `"dependencies": ["recorder"]` and `"config_flow": true`

### Runtime Libraries (provided by HA)
- `aiohttp` -- async HTTP client for all API communication
- `voluptuous` -- schema validation for config flow forms and service call payloads
- `homeassistant.components.recorder` -- external statistics insertion (`async_add_external_statistics`, `get_last_statistics`, `StatisticMeanType`)

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
None. The integration is installed as a raw directory drop-in under `custom_components/`. Also installable via HACS (`hacs.json` present).

### Linting and Formatting
- **Ruff** configured in `pyproject.toml`: `target-version = "py312"`, `line-length = 120`
- Rule sets: `E`, `W`, `F` (pycodestyle/pyflakes), `I` (isort), `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify), `LOG` (logging)
- `LOG` rule set machine-enforces `%`-style logging convention
- Run locally: `ruff check . && ruff format . --check`

### CI/CD
- **Validate** (`.github/workflows/validate.yml`): triggers on push to `main` and all PRs. Three parallel jobs + gate:
  - `ruff` -- lint and format check (Python 3.12)
  - `hassfest` -- validates `manifest.json`, translations, services against HA integration requirements
  - `hacs` -- validates HACS compatibility (`ignore: brands` since no icon asset)
  - `gate` -- single required status check, passes only if all three above succeed
- **Release** (`.github/workflows/release.yml`): triggers via `workflow_run` after Validate succeeds on `main`. Extracts version from `manifest.json`, creates git tag + GitHub Release with notes from `CHANGELOG.md`
- **Dependabot** (`.github/workflows/dependabot-version-bump.yml`): monitors GitHub Actions versions only (no Python packages tracked); auto-bumps patch version in `manifest.json` and prepends changelog entry on Dependabot PRs
- **Release process**: documented in [CONTRIBUTING.md](../../CONTRIBUTING.md) -- bump version + changelog in PR, merge triggers auto-release

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
- No automated tests to catch regressions (CI covers linting and validation only)
- PKCE implementation is hand-rolled with static `state` and `nonce` values (non-compliant with CSRF/replay protections beyond the code challenge itself)

## Extension Guidelines
- New dependencies should be HA-provided where possible; if external, add to `manifest.json` `"requirements"` list
- New API endpoints follow the existing pattern in `api_client.py` using `async_get_clientsession`
- Auth flow changes must update both cookie and password paths
