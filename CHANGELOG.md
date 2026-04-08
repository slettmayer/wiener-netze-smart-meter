# Changelog

## 2.3.0

- Automate releases: version change in manifest.json triggers tag + GitHub release after validation passes
- Add dependabot auto-bump: patch version and changelog entry created automatically on Dependabot PRs
- Rename CI workflow to Validate with gate job for branch protection
- Simplify changelog format: flat bullets, no Unreleased section

## 2.2.2

- Fix: use recorder's dedicated executor for DB queries

## 2.2.1

- Fix: sensors stuck on "unavailable" — run get_last_statistics in executor thread

## 2.2.0

- Statistics now use monotonically increasing sum (no daily reset) and hourly consumption as state
- stat_type: state shows hourly consumption bars, stat_type: change works without negative spikes
- Query recorder for last known sum before inserting (idempotent across restarts)

## 2.1.0

- Add CI pipeline: ruff lint/format, hassfest, HACS validation on push/PR
- Add release workflow: auto-creates GitHub release from CHANGELOG.md on tag push
- Add ruff linter/formatter configuration (pyproject.toml)
- Add HACS repository config (hacs.json)
- Add CHANGELOG.md and CONTRIBUTING.md with documented dev workflow
- Add CLAUDE.md and structured documentation (architecture, conventions, domain)
- Fix: removed URLs from translation strings (hassfest compliance)
- Fix: added issue_tracker to manifest.json (HACS compliance)

## 2.0.0

- Complete rebuild with clean architecture
- Switch to external statistics (no more HA auto-recording conflicts)
- Timezone-correct day grouping (CET/CEST)
- aiohttp instead of blocking requests
- Two auth methods: KEYCLOAK_IDENTITY cookie or username/password
- Service action fetch_data instead of automatic polling
- Removed energy sensor entities (total/grid/pv) — replaced by external statistics
