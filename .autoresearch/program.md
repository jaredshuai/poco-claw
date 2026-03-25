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

---

## Execution Details

### Environment Setup Commands

```bash
# From project root (E:/codespace/poco-claw)
cd backend && uv sync

# Verify tools are available
uv run ruff --version
uv run ty --version
uv run pytest --version
```

### Running Checks per Module

```bash
# Check single file for lint errors
uv run ruff check backend/app/services/task_service.py

# Auto-fix lint errors (safe fixes only)
uv run ruff check --fix backend/app/services/task_service.py

# Check single file for type errors
uv run ty check backend/app/services/capability_recommendation_service.py

# Run tests with coverage for specific module
cd backend && uv run pytest --cov=app/services/session_service tests/ -v
```

### IMPORTANT: VIRTUAL_ENV Workaround

**Problem**: `ty` may fail with "broken venv" error if `VIRTUAL_ENV` environment variable is set incorrectly.

**Solution**: Unset the variable before running `ty`:

```bash
# PowerShell
$env:VIRTUAL_ENV = $null; uv run ty check backend/

# Bash/Git Bash
unset VIRTUAL_ENV && uv run ty check backend/
```

This is a known issue with ty when the shell has a stale VIRTUAL_ENV pointing to a different environment.

---

## Common Fix Patterns

### Pattern 1: F811 Redefinition Error

**Error**: `F811 Redefinition of unused 'variable_name'`

**Cause**: Variable redefined in the same scope without being used between definitions.

**Fix**: Usually auto-fixable. If not, rename the variable or merge the definitions.

```bash
# Auto-fix
uv run ruff check --fix backend/app/services/file.py
```

### Pattern 2: Type Narrowing with isinstance(x, dict)

**Error**: `ty` narrows `isinstance(x, dict)` to `dict[Never, Never]`, causing type mismatches.

**Solution**: Use `typing.cast` to provide explicit type annotation:

```python
from typing import cast

# Before (causes error)
if isinstance(result, dict):
    value = result.get("key")  # Error: dict[Never, Never] has no get

# After (works)
if isinstance(result, dict):
    typed_result = cast(dict[str, Any], result)
    value = typed_result.get("key")  # OK
```

### Pattern 3: Optional Type Handling

**Error**: Type checker complains about accessing attribute of `None`.

**Solution**: Add explicit None check or use `typing.cast`:

```python
# Option 1: Guard clause
if user is None:
    return None
# Now ty knows user is not None

# Option 2: Cast (use sparingly)
user = cast(User, maybe_user)
```

---

## Experiment 1 Learnings (mar25 run)

### Time Estimates

| Activity | Average Time |
|----------|--------------|
| Lint error fix (auto-fixable) | 1-2 minutes |
| Lint error fix (manual) | 3-5 minutes |
| Type error fix (simple cast) | 2-3 minutes |
| Type error fix (complex) | 5-10 minutes |
| Baseline measurement | 2-3 minutes per module |

### Common Pitfalls

1. **VIRTUAL_ENV issue**: Always unset before running `ty`
2. **Ruff auto-fix is safe**: `--fix` only applies safe fixes by default
3. **Type narrowing surprises**: `isinstance(x, dict)` narrows to `dict[Never, Never]`
4. **Run metrics before and after**: Never assume a fix worked without re-running checks

### Files Successfully Improved

| File | Lint Before | Lint After | Type Before | Type After |
|------|-------------|------------|-------------|------------|
| session_service.py | 0 | 0 | 0 | 0 |
| task_service.py | 3 | 0 | - | - |
| capability_recommendation_service.py | - | - | 3 | 0 |

### Key Takeaway

Always run checks on the entire `backend/` directory at the end of a session to catch any regressions introduced by partial fixes.