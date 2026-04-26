# TESTING.md — yait Test Plan

## Environment Setup

```bash
# Clone and enter the repo
cd yet-another-issue-tracker

# Run tests with uv (no venv needed)
uv run --with pytest --with pyyaml --with click pytest tests/ -v

# Or with pip in a venv
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
pytest tests/ -v
```

## Running Tests

```bash
# Run all tests (~60 total)
uv run --with pytest --with pyyaml --with click pytest tests/ -v

# Run a specific test module
uv run --with pytest --with pyyaml --with click pytest tests/test_models.py -v

# Run with coverage
uv run --with pytest --with pyyaml --with click --with pytest-cov pytest tests/ --cov=yait -v
```

## Feature Inventory

| Feature | Module | Test File | Tests | Status |
|---|---|---|---|---|
| Issue dataclass | `models.py` | `test_models.py` | 8 | Pass |
| Issue type field | `models.py` | `test_models.py` | ~4 | Pass |
| Store init | `store.py` | `test_store.py` | 2 | Pass |
| Save/load issue | `store.py` | `test_store.py` | 2 | Pass |
| Save/load with type | `store.py` | `test_store.py` | ~2 | Pass |
| List/filter issues | `store.py` | `test_store.py` | 2 | Pass |
| Filter by type | `store.py` | `test_store.py` | ~2 | Pass |
| ID auto-increment | `store.py` | `test_store.py` | 1 | Pass |
| Git repo detection | `git_ops.py` | `test_git_ops.py` | 2 | Pass |
| Git commit | `git_ops.py` | `test_git_ops.py` | 1 | Pass |
| CLI: init | `cli.py` | `test_cli.py` | 1 | Pass |
| CLI: new | `cli.py` | `test_cli.py` | 2 | Pass |
| CLI: new --type | `cli.py` | `test_cli.py` | ~3 | Pass |
| CLI: list | `cli.py` | `test_cli.py` | 1 | Pass |
| CLI: list --type | `cli.py` | `test_cli.py` | ~2 | Pass |
| CLI: show | `cli.py` | `test_cli.py` | 1 | Pass |
| CLI: close | `cli.py` | `test_cli.py` | ~2 | Pass |
| CLI: reopen | `cli.py` | `test_cli.py` | ~2 | Pass |
| CLI: comment | `cli.py` | `test_cli.py` | ~2 | Pass |
| CLI: label add/remove | `cli.py` | `test_cli.py` | ~2 | Pass |
| CLI: search | `cli.py` | `test_cli.py` | ~2 | Pass |
| CLI: search --type | `cli.py` | `test_cli.py` | ~2 | Pass |

## Manual Test Steps

### 1. Initialize a yait project

```bash
mkdir /tmp/test-yait && cd /tmp/test-yait
git init
yait init
# Expected: .yait/ directory created, initial git commit
```

### 2. Create an issue

```bash
yait new --title "First bug"
# Expected: prints "Created issue #1: First bug"
```

### 3. Create an issue with --type

```bash
yait new --title "Login crash" --type bug
# Expected: prints "Created issue #2: Login crash"

yait new --title "Add search" --type feature
# Expected: prints "Created issue #3: Add search"

yait new --title "Generic task"
# Expected: prints "Created issue #4: Generic task" (type defaults to misc)
```

### 4. Verify type in issue file

```bash
cat .yait/issues/2.md
# Expected: frontmatter contains "type: bug"

cat .yait/issues/4.md
# Expected: frontmatter contains "type: misc"
```

### 5. List issues

```bash
yait list
# Expected: shows all 4 open issues
```

### 6. Filter by type

```bash
yait list --type bug
# Expected: shows only issue #2 (Login crash)

yait list --type feature
# Expected: shows only issue #3 (Add search)

yait list --type misc
# Expected: shows issues #1 and #4
```

### 7. Show issue details

```bash
yait show 2
# Expected: full issue with type=bug, status, created/updated timestamps
```

### 8. Verify issue file on disk

```bash
cat .yait/issues/1.md
# Expected: YAML frontmatter with title, status, type, labels, etc.
```

### 9. Filter by status

```bash
yait list --status open
yait list --status closed
```

### 10. Close and reopen

```bash
yait close 1
yait show 1   # status should be "closed"
yait reopen 1
yait show 1   # status should be "open"
```

### 11. Search with --type filter

```bash
yait search "crash" --type bug
# Expected: shows only issue #2

yait search "crash" --type feature
# Expected: no matching issues
```

### 12. Invalid type value

```bash
yait new --title "bad" --type invalid
# Expected: error — invalid choice "invalid"
```

## Test Categories

- **test_models.py** (~12 tests) — Pure unit tests, no I/O. Covers Issue dataclass including type field.
- **test_store.py** (~12 tests) — Filesystem integration tests using tmp_path fixtures. Covers save/load/list with type.
- **test_git_ops.py** (3 tests) — Git integration tests with real git repos.
- **test_cli.py** (~15 tests) — CLI end-to-end tests via CliRunner. Covers all commands including --type.

## Known Limitations

- No concurrency or locking tests — yait is single-user by design.
- No Windows-specific path tests.
- No negative tests for `load_issue` with non-existent ID (FileNotFoundError path).
- No test for malformed issue files.
