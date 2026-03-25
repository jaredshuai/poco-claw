# autoresearch-tuning

This is an experiment to have the LLM autonomously improve code quality and test coverage.

## Setup

To set up a new tuning session:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar25`). The branch `autoresearch/<tag>` must not already exist.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**: The repo structure is defined in `AGENTS.md`. Key files:
   - `backend/app/services/*.py` - Business logic (modifiable)
   - `backend/app/repositories/*.py` - Data access (modifiable)
   - `backend/app/api/v1/*.py` - API endpoints (modifiable)
   - `backend/tests/*.py` - Test files (modifiable)
4. **Verify toolchain**: Run `uv sync` to ensure dependencies are installed.
5. **Initialize baseline.json**: Run metrics on the first module to establish baseline.
6. **Initialize results.tsv**: Create with header row only.
7. **Confirm and go**: Confirm setup looks good.

## Toolchain

All tools are from Astral (fast, Rust-based):

- **uv** - Package manager: `uv run <command>`
- **ruff** - Lint + Format: `uv run ruff check` / `uv run ruff format`
- **ty** - Type checker: `uv run ty check`

## Metrics Commands

```bash
# Lint errors
uv run ruff check backend/

# Format check
uv run ruff format --check backend/

# Type errors
uv run ty check backend/

# Test coverage (from backend directory)
cd backend && uv run pytest --cov=app tests/

# Tests only
cd backend && uv run pytest tests/
```

## Experimentation

**What you CAN do:**
- Modify files in `backend/app/services/`, `repositories/`, `api/v1/`, `schemas/`
- Add or modify test files in `backend/tests/`
- Apply lint fixes, add type annotations, refactor for clarity
- Write new tests to improve coverage

**What you CANNOT do:**
- Modify `backend/app/models/*.py` (database models)
- Modify `backend/app/core/settings.py` (configuration)
- Modify `backend/alembic/**/*.py` (migrations)
- Modify `pyproject.toml` (dependencies)
- Install new packages

## Goals

1. **Zero lint errors** - `uv run ruff check` returns clean
2. **Zero type errors** - `uv run ty check` returns clean
3. **80%+ test coverage** - `pytest --cov` shows ≥80%
4. **Simplicity** - All else equal, simpler code wins

## Output format

After running checks, extract key metrics:

```bash
# Count lint errors
uv run ruff check backend/ 2>&1 | grep -c "error"

# Count type errors (if ty outputs count)
uv run ty check backend/ 2>&1 | tail -5

# Get coverage percentage
cd backend && uv run pytest --cov=app tests/ 2>&1 | grep "TOTAL"
```

## Logging results

Record each experiment in `results.tsv`:

| Column | Description |
|--------|-------------|
| timestamp | ISO format timestamp |
| module | File path relative to project root |
| change_type | `lint_fix`, `type_fix`, `test_add`, `refactor` |
| lint_before | Lint error count before |
| lint_after | Lint error count after |
| type_before | Type error count before |
| type_after | Type error count after |
| cov_before | Test coverage % before |
| cov_after | Test coverage % after |
| status | `keep`, `discard`, or `crash` |
| description | Short description of the change |

## Branch Strategy

All experiments run on a dedicated branch, keeping main clean:

- **Branch name**: `autoresearch/<tag>` (e.g., `autoresearch/mar25`)
- **Create**: `git checkout -b autoresearch/<tag>` from main/master
- **Keep changes**: `git commit` when metrics improve
- **Discard changes**: `git reset --hard HEAD` when metrics don't improve
- **Merge**: After completing a phase or when satisfied with results

The results.tsv and baseline.json files are NOT committed to git (keep untracked).

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autoresearch/mar25`).

LOOP FOREVER:

1. Look at git state: current branch/commit
2. Select next module from priority list (see config.toml)
3. Run metrics, record baseline if first time for this module
4. Propose and apply improvement to the module
5. Run metrics again
6. Compare results:
   - If improved: `git commit`, log `keep` in results.tsv
   - If not improved: `git reset --hard HEAD`, log `discard`
7. Continue to next improvement or next module

**Crashes**: If a run crashes (OOM, bug, etc.), assess whether it's fixable. If not, log `crash` and move on.

**NEVER STOP**: Once the experiment loop has begun, do NOT pause to ask the human. Continue working indefinitely until manually stopped.

## Priority Order

See `config.toml` for the full module priority list. Core services first, then repositories, then API endpoints.