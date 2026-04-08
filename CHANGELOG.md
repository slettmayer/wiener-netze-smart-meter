# Changelog

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
