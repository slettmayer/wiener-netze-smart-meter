# Contributing

## Development Cycle

### Making Changes

1. Create a feature branch from `main`
2. Make your changes
3. Run linting locally: `ruff check . && ruff format . --check`
4. Update `CHANGELOG.md` -- add entries under `## [Unreleased]`
5. Create a PR -- CI runs automatically (ruff, hassfest, HACS validation)
6. Merge PR (squash)

### Creating a Release

1. Move `[Unreleased]` entries in `CHANGELOG.md` to a new version section:
   ```
   ## [Unreleased]

   ## [2.1.0] - 2026-04-15
   ### Added
   - ...
   ```
2. Update `version` in `custom_components/wiener_netze_smart_meter/manifest.json`
3. Commit: `Bump version to 2.1.0`
4. Tag and push: `git tag v2.1.0 && git push && git push --tags`
5. GitHub Action creates the release automatically using CHANGELOG.md notes
6. HACS picks up the new release

### Versioning

- **MAJOR** (3.0.0): Breaking changes (config flow changes, removed entities, stat ID changes)
- **MINOR** (2.1.0): New features (new role, new sensor, new config option)
- **PATCH** (2.0.1): Bug fixes (timezone fix, auth fix, parsing fix)

### Code Style

- Enforced by [Ruff](https://docs.astral.sh/ruff/) -- runs in CI
- Run locally: `pip install ruff && ruff check . --fix && ruff format .`
- See `pyproject.toml` for rule configuration
