# TESTING.md — yait Test Plan

## Environment Setup

```bash
cd yet-another-issue-tracker

# Install with test dependencies
uv sync --group test

# Run tests
uv run pytest tests/ -v
```

## Running Tests

```bash
# Run all tests (49 total)
uv run pytest tests/ -v

# Run a specific test module
uv run pytest tests/test_models.py -v

# Run with coverage
uv run pytest tests/ --cov=yait -v
```

## Feature Inventory

| Feature | Module | Test File | Tests | Status |
|---|---|---|---|---|
| Issue dataclass defaults | `models.py` | `test_models.py` | 6 | Pass |
| Issue dataclass mutation | `models.py` | `test_models.py` | 2 | Pass |
| Issue create with all fields | `models.py` | `test_models.py` | 1 | Pass |
| Labels not shared between instances | `models.py` | `test_models.py` | 1 | Pass |
| Store init + idempotent | `store.py` | `test_store.py` | 3 | Pass |
| Save/load issue roundtrip | `store.py` | `test_store.py` | 3 | Pass |
| ID auto-increment | `store.py` | `test_store.py` | 2 | Pass |
| List issues (all / empty) | `store.py` | `test_store.py` | 2 | Pass |
| List filter by status | `store.py` | `test_store.py` | 1 | Pass |
| List filter by label | `store.py` | `test_store.py` | 1 | Pass |
| List filter by assignee | `store.py` | `test_store.py` | 1 | Pass |
| List combined filters | `store.py` | `test_store.py` | 1 | Pass |
| Load non-existent issue | `store.py` | `test_store.py` | 1 | Pass |
| Issue with comments (body roundtrip) | `store.py` | `test_store.py` | 1 | Pass |
| YAML special chars roundtrip | `store.py` | `test_store.py` | 1 | Pass |
| List on uninitialised dir | `store.py` | `test_store.py` | 1 | Pass |
| Git repo detection | `git_ops.py` | `test_git_ops.py` | 2 | Pass |
| git_add + git_commit | `git_ops.py` | `test_git_ops.py` | 1 | Pass |
| git_run returns CompletedProcess | `git_ops.py` | `test_git_ops.py` | 1 | Pass |
| git_commit no-op without staged | `git_ops.py` | `test_git_ops.py` | 1 | Pass |
| CLI: init | `cli.py` | `test_cli.py` | 1 | Pass |
| CLI: new (basic + options + fail) | `cli.py` | `test_cli.py` | 3 | Pass |
| CLI: list (show + empty + filter) | `cli.py` | `test_cli.py` | 3 | Pass |
| CLI: show (details + not found) | `cli.py` | `test_cli.py` | 2 | Pass |
| CLI: close + reopen | `cli.py` | `test_cli.py` | 1 | Pass |
| CLI: comment | `cli.py` | `test_cli.py` | 1 | Pass |
| CLI: label add/remove/duplicate | `cli.py` | `test_cli.py` | 3 | Pass |
| CLI: search (match + no match) | `cli.py` | `test_cli.py` | 2 | Pass |

**Total: 49 tests across 4 modules**

## Test Categories

- **test_models.py** (10 tests) — Pure unit tests for Issue dataclass, no I/O.
- **test_store.py** (18 tests) — Filesystem integration tests using `tmp_path` and `initialized_root` fixtures.
- **test_git_ops.py** (5 tests) — Git integration tests with real git repos in temp directories.
- **test_cli.py** (16 tests) — CLI end-to-end tests via Click's `CliRunner` with monkeypatched `cwd`.

## Shared Fixtures (`conftest.py`)

| Fixture | Description |
|---------|-------------|
| `yait_root` | Temp directory with `git init` + user config |
| `initialized_root` | `yait_root` with `init_store()` already called |

## Manual Test Steps

### 1. Initialize a yait project

```bash
mkdir /tmp/test-yait && cd /tmp/test-yait
git init
yait init
# Expected: .yait/ directory created, initial git commit
```

### 2. Create issues

```bash
yait new --title "First bug" --type bug
# Expected: prints "Created issue #1: First bug"

yait new --title "Add search" --type feature
# Expected: prints "Created issue #2: Add search"

yait new --title "Generic task"
# Expected: prints "Created issue #3: Generic task" (type defaults to misc)
```

### 3. List and filter

```bash
yait list                    # all open issues
yait list --status closed    # closed only
yait list --type bug         # open bugs
yait list --label urgent     # by label
```

### 4. Show, close, reopen

```bash
yait show 1
yait close 1
yait show 1   # status should be "closed"
yait reopen 1
yait show 1   # status should be "open"
```

### 5. Comment and search

```bash
yait comment 1 -m "Fixed in abc123"
yait search "bug"
```

### 6. Label management

```bash
yait label add 1 urgent
yait label remove 1 urgent
```

## Known Limitations

- No concurrency or locking tests — yait is single-user by design.
- No Windows-specific path tests.
- No test for malformed issue files (corrupt YAML, missing fields).
- `yait edit` is not tested (requires interactive `$EDITOR`).
- `--type` filter is not yet tested (v0.2 feature).
