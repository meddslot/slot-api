# AGENTS.md

Guidance for AI coding agents working on the **Meddslot API**.


## Definition of done

1. Tests added/updated and pass with `uv run pytest -W error::DeprecationWarning`.
2. `uv run ruff check .` and `uv run ruff format --check .` are clean.

## Deprecation policy

Always migrate away from deprecated packages/warnings (never suppress with filters/`# noqa`);


## Commit style

Short conventional commits: `type(scope): description` — lowercase, imperative, no trailing period, ≤ 72 chars. Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`; scope names the area (e.g. `auth`, `models`, `deps`). Squash housekeeping into related commits.

```
feat(auth): add register, login and jwt-protected me endpoints
fix(health): include version in health response
docs(agents): document response envelope convention
```
