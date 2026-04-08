# Contributing

## Development Cycle

### Making Changes

1. Create a feature branch from `main`
2. Make your changes
3. Run linting locally: `ruff check . && ruff format . --check`
4. Bump `version` in `custom_components/wiener_netze_smart_meter/manifest.json`
5. Add a new `## X.Y.Z` section at the top of `CHANGELOG.md` with your changes
6. Create a PR — CI runs automatically (ruff, hassfest, HACS validation)
7. Merge PR (squash)
8. Release is created automatically after validation passes on `main`

### Releasing

Releases are fully automated. When a PR that changes the version in `manifest.json` is merged to `main`:

1. The `Validate` workflow runs (ruff, hassfest, HACS validation)
2. On success, the `Auto Release` workflow creates a git tag and GitHub release
3. Release notes are extracted from `CHANGELOG.md`
4. HACS picks up the new release

No manual tagging or release creation needed.

### Dependabot PRs

Dependabot PRs are auto-bumped: a workflow increments the patch version in `manifest.json` and prepends a changelog entry. Reviewers only need to approve and merge.

### Versioning

- **MAJOR** (3.0.0): Breaking changes (config flow changes, removed entities, stat ID changes)
- **MINOR** (2.1.0): New features (new role, new sensor, new config option)
- **PATCH** (2.0.1): Bug fixes (timezone fix, auth fix, parsing fix)

### Changelog Format

```
## X.Y.Z

- Description of change
- Another change
```

- No `[Unreleased]` section — every changelog entry ships with a version bump
- Version headers: `## X.Y.Z` (no brackets, no dates)
- Flat bullet points (no subcategory headers like `### Fixed`)
- Prefix bullets with context if helpful: `- Fix: ...`, `- Add: ...`

### Code Style

- Enforced by [Ruff](https://docs.astral.sh/ruff/) — runs in CI
- Run locally: `pip install ruff && ruff check . --fix && ruff format .`
- See `pyproject.toml` for rule configuration
