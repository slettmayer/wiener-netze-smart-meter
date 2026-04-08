# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Statistics now use monotonically increasing `sum` (no daily reset) and hourly consumption as `state`
- `stat_type: state` shows hourly consumption bars, `stat_type: change` works without negative spikes
- Queries recorder for last known sum before inserting (idempotent across restarts)

## [2.1.0] - 2026-04-08

### Added
- CI pipeline: ruff lint/format, hassfest, HACS validation on push/PR
- Release workflow: auto-creates GitHub release from CHANGELOG.md on tag push
- Ruff linter/formatter configuration (pyproject.toml)
- HACS repository config (hacs.json)
- CHANGELOG.md and CONTRIBUTING.md with documented dev workflow
- CLAUDE.md and structured documentation (architecture, conventions, domain)

### Fixed
- Removed URLs from translation strings (hassfest compliance)
- Added issue_tracker to manifest.json (HACS compliance)

## [2.0.0] - 2026-04-08

### Changed
- Complete rebuild with clean architecture
- Switch to external statistics (no more HA auto-recording conflicts)
- Timezone-correct day grouping (CET/CEST)
- aiohttp instead of blocking requests
- Two auth methods: KEYCLOAK_IDENTITY cookie or username/password
- Service action `fetch_data` instead of automatic polling

### Removed
- Energy sensor entities (total/grid/pv) -- replaced by external statistics
