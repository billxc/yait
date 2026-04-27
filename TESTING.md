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
# Run all tests (394 total)
uv run pytest tests/ -v

# Run a specific test module
uv run pytest tests/test_models.py -v

# Run with coverage
uv run pytest tests/ --cov=yait -v
```

## Feature Inventory

### Core CRUD & Editing

| Feature | Module | Test File | Tests | Status |
|---|---|---|---|---|
| Issue dataclass defaults & mutation | `models.py` | `test_models.py` | 27 | Pass |
| Store init + save/load roundtrip | `store.py` | `test_store.py` | 55 | Pass |
| Git repo detection + commit | `git_ops.py` | `test_git_ops.py` | 5 | Pass |
| CLI: init, new, list, show, close, reopen, delete | `cli.py` | `test_cli.py` | 146 | Pass |
| CLI: comment, label, assign, edit, search, stats, log | `cli.py` | `test_cli.py` | (incl. above) | Pass |

### v0.5 Features

| Feature | Module | Test File | Tests | Status |
|---|---|---|---|---|
| Milestone management (create/list/show/close/reopen/edit/delete) | `cli.py` | `test_cli.py` | (incl. above) | Pass |
| Bulk operations (label/assign/priority/milestone/type + filters) | `cli.py` | `test_cli.py` | (incl. above) | Pass |
| Enhanced stats (--by milestone/assignee/priority, --json) | `cli.py` | `test_cli.py` | (incl. above) | Pass |
| Advanced search (--regex, --title-only, --count, multi-field) | `cli.py` | `test_cli.py` | (incl. above) | Pass |
| Issue templates (create/list/delete, new --template) | `store.py` | `test_store.py` | (incl. above) | Pass |
| Config enhancement (defaults, display, set/reset) | `cli.py` | `test_config.py` | 36 | Pass |
| Design document store (save/load/list/delete docs) | `store.py` | `test_doc_store.py` | 11 | Pass |
| Design document CLI (create/show/list/edit/delete/link/unlink) | `cli.py` | `test_doc_cli.py` | 31 | Pass |
| Issue linking data model + store | `store.py` | `test_links.py` | 18 | Pass |
| Issue linking CLI (link/unlink/show) | `cli.py` | `test_links_cli.py` | 16 | Pass |
| Output formatting (compact/wide/auto-detect) | `cli.py` | `test_output_format.py` | 25 | Pass |
| Concurrency lock (acquire/release/stale/timeout/contention) | `lock.py` | `test_lock.py` | 12 | Pass |
| Security (input validation, blank title, negative ID, etc.) | various | `test_security.py` | 12 | Pass |

**Total: 394 tests across 12 test modules**

## Test Categories

- **test_models.py** (27 tests) — Unit tests for Issue/Milestone/Doc/Template dataclasses.
- **test_store.py** (55 tests) — Filesystem integration tests for issue/template/milestone store operations.
- **test_git_ops.py** (5 tests) — Git integration tests with real git repos in temp directories.
- **test_cli.py** (146 tests) — CLI end-to-end tests via Click's `CliRunner` covering all commands.
- **test_config.py** (36 tests) — Config management: defaults, display settings, set/reset commands.
- **test_doc_store.py** (11 tests) — Design document store layer tests.
- **test_doc_cli.py** (31 tests) — Design document CLI tests.
- **test_links.py** (18 tests) — Issue linking data model and store tests.
- **test_links_cli.py** (16 tests) — Issue linking CLI tests.
- **test_output_format.py** (25 tests) — Output formatting (compact/wide/auto) tests.
- **test_lock.py** (12 tests) — Concurrency lock: acquire/release, stale detection, timeout, contention.
- **test_security.py** (12 tests) — Input validation and security edge cases.

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
yait new --title "First bug" --type bug --priority p0
yait new --title "Add search" --type feature --milestone v1.0
yait new --title "Generic task"
# defaults to type=misc
```

### 3. Milestone management

```bash
yait milestone create v1.0 --description "First release" --due 2026-06-01
yait milestone list
yait milestone show v1.0
yait milestone close v1.0
```

### 4. Bulk operations

```bash
yait bulk label add urgent 1 2 3
yait bulk priority p0 1 2
yait bulk milestone v1.0 --filter-type bug --filter-status open
```

### 5. Advanced search

```bash
yait search "bug" --regex --status all
yait search "crash" --title-only --count
yait search "login" --label auth --priority p0
```

### 6. Design documents

```bash
yait doc create auth-prd --title "Auth PRD" -b "## Overview"
yait doc link 1 2 auth-prd
yait doc show auth-prd
yait list --doc auth-prd
```

### 7. Issue linking

```bash
yait link 1 blocks 2
yait link 3 relates-to 1
yait show 1
# Links section shows relationships
yait unlink 1 2
```

### 8. Configuration

```bash
yait config
yait config set defaults.type bug
yait config set display.max_title_width 60
yait config reset defaults.type
```

### 9. Output formatting

```bash
yait list --compact
yait list --wide
# Auto-detect: adapts to terminal width
```

## Known Limitations

- No Windows-specific path tests.
- `yait edit` and `yait doc edit` (without -b) are not tested (require interactive `$EDITOR`).
- `yait template create` is not tested (requires interactive `$EDITOR`).
