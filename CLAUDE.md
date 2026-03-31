# CLAUDE.md

## Commands

```bash
# Start all services
docker-compose up --build

# Run backend tests
docker-compose run backend pytest backend/tests/ -v

# Run frontend lint
cd frontend && npm run lint
```

## Development Workflow

When implementing a feature or fix, follow these steps automatically:

1. **Create feature branch** — `git checkout -b feat/<description>` (or `fix/`, `chore/`, `test/`)
2. **Run tests** — ensure all tests pass before committing
3. **Commit** — stage relevant files and create a descriptive commit following conventional commits format
4. **Push & open PR** — `gh pr create` targeting `main`
5. **Monitor CI** — poll with `gh run list --branch <branch>` until all checks complete
6. **Fix CI failures** — inspect with `gh run view <run-id> --log-failed`, fix, commit, push

Do this without waiting for explicit instruction — it is the expected end-to-end flow for every task in this repo.

## Branch Protection

- **Never push directly to `main`** — all changes must go through a PR
- PRs require CI (`test` job) to pass before merge
- Auto-merge (squash) is enabled — PRs merge automatically once approved and CI passes

## Rules

- **ALWAYS ensure `main` branch is stable and runnable** — every merge to `main` must leave the service in a working state; never merge broken builds, failing tests, or incomplete migrations
