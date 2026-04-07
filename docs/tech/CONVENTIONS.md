# Conventions

## Purpose
Documents the coding conventions, naming patterns, error handling strategy, and style rules used in this integration.

## Responsibilities
- Defining naming conventions for files, classes, methods, and constants
- Documenting code style expectations
- Describing error handling and logging patterns

## Non-Responsibilities
- Module boundaries and data flow -- see [ARCHITECTURE.md](ARCHITECTURE.md)
- Technology and library choices -- see [TECH-STACK.md](TECH-STACK.md)

## Overview

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files | `snake_case.py` | `api_client.py`, `config_flow.py` |
| Classes | `PascalCase` with HA-aligned suffix | `SmartMeterCoordinator`, `SmartMeterDiagnosticSensor` |
| Exceptions | `PascalCase` + `Error` suffix | `AuthenticationError`, `ApiError` |
| Public async methods | `async_` prefix | `async_setup_entry`, `async_fetch` |
| Private methods | `_` prefix | `_authenticate_cookie`, `_insert_statistics` |
| Module-level helpers | `_` prefix | `_generate_code_verifier`, `_aggregate_to_hourly` |
| Constants | `UPPER_SNAKE_CASE` | `CONF_ZAEHLPUNKTNUMMER`, `ROLLE_TOTAL` |
| Constant prefixes | `CONF_` (config), `SERVICE_` (service), `ROLLE_` (role), `*_ENDPOINT` (URL) | `CONF_GESCHAEFTSPARTNER`, `BEWEGUNGSDATEN_ENDPOINT` |
| Logger | Module-level | `_LOGGER = logging.getLogger(__name__)` |

### Code Style

- 4-space indentation (PEP 8)
- Double quotes for strings throughout
- Import ordering: stdlib, third-party, HA framework, local relative (PEP 8 / isort)
- Full type annotations on function signatures using `X | Y` union syntax
- One-line docstrings (`"""..."""`) on every module, class, and method
- f-strings for dynamic string formatting in application code
- `%`-style formatting in `_LOGGER` calls (avoids unnecessary interpolation)
- No linter or formatter config files present; style maintained manually

### Error Handling

Two custom exceptions in `api_client.py`:
- `AuthenticationError(Exception)` -- all auth failures
- `ApiError(Exception)` -- all data-fetch failures

Exception chaining: `raise X(...) from err` used consistently.

Translation in coordinator:
- `AuthenticationError` -> `ConfigEntryAuthFailed` (triggers HA re-auth UI flow)
- `ApiError` -> logged as warning per-role, allows partial success

Config flow: `AuthenticationError` -> `errors["base"] = "invalid_auth"`; bare `Exception` -> `errors["base"] = "cannot_connect"` with `_LOGGER.exception(...)`.

### Logging Levels

| Level | Usage |
|-------|-------|
| `debug` | HTTP response details, raw data, internal state |
| `info` | Successful operations (fetch counts, meter readings, service calls) |
| `warning` | Recoverable failures allowing partial success |
| `exception` | Unexpected errors in config flow (full traceback) |

### Constants Management

All magic strings, URLs, role codes, config keys, and defaults are defined in `const.py`. No inline string literals appear in other modules.

## Dependencies
- PEP 8 (de facto style guide)
- Home Assistant naming conventions for integration components

## Design Decisions
- `%`-style logging over f-strings for `_LOGGER` calls to avoid string interpolation cost when log level is disabled. Rationale: HA best practice.
- One-line docstrings on all items rather than selective documentation. Rationale: consistency over verbosity.
- No formatter/linter tooling configured. Rationale not documented -- needs team input.

## Known Risks
- Without linter enforcement, style drift is possible as the codebase grows
- Manual style maintenance increases review burden

## Extension Guidelines
- New constants go in `const.py` with the appropriate prefix
- New exceptions follow the `PascalCase` + `Error` pattern in `api_client.py`
- New async public methods must use the `async_` prefix
- Logging must follow the established level conventions
