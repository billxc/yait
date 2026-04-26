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
# Run all tests (23 total)
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
| Store init | `store.py` | `test_store.py` | 2 | Pass |
| Save/load issue | `store.py` | `test_store.py` | 2 | Pass |
| List/filter issues | `store.py` | `test_store.py` | 2 | Pass |
| ID auto-increment | `store.py` | `test_store.py` | 1 | Pass |
| Git repo detection | `git_ops.py` | `test_git_ops.py` | 2 | Pass |
| Git commit | `git_ops.py` | `test_git_ops.py` | 1 | Pass |
| CLI: init | `cli.py` | `test_cli.py` | 1 | Pass |
| CLI: new | `cli.py` | `test_cli.py` | 2 | Pass |
| CLI: list | `cli.py` | `test_cli.py` | 1 | Pass |
| CLI: show | `cli.py` | `test_cli.py` | 1 | Pass |

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
yait new "First bug"
# Expected: prints "Created issue #1: First bug"
```

### 3. List issues

```bash
yait list
# Expected: shows "#1 [open] First bug"
```

### 4. Show issue details

```bash
yait show 1
# Expected: full issue with status, created/updated timestamps
```

### 5. Verify issue file on disk

```bash
cat .yait/issues/1.md
# Expected: YAML frontmatter with title, status, labels, etc.
```

### 6. Filter by status

```bash
yait list --status open
yait list --status closed
```

### 7. Close and reopen

```bash
yait close 1
yait show 1   # status should be "closed"
yait reopen 1
yait show 1   # status should be "open"
```

## Test Categories

- **test_models.py** (8 tests) — Pure unit tests, no I/O.
- **test_store.py** (7 tests) — Filesystem integration tests using tmp_path fixtures.
- **test_git_ops.py** (3 tests) — Git integration tests with real git repos.
- **test_cli.py** (5 tests) — CLI end-to-end tests via CliRunner with monkeypatched cwd.

## Known Limitations

- No concurrency or locking tests — yait is single-user by design.
- No Windows-specific path tests.
- CLI tests for `close`, `reopen`, `comment`, `edit`, `label`, `search` commands are not yet covered.
- No negative tests for `load_issue` with non-existent ID (FileNotFoundError path).
- No test for malformed issue files.
