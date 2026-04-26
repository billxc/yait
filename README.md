# yait — Yet Another Issue Tracker

A local issue tracker built on markdown files and git. Every issue is a `.md` file with YAML frontmatter; all changes are automatically committed to git history.

## Install

**Requirements:** Python 3.10+, git

```bash
# With pip
pip install -e .

# With uv (no venv needed)
uv pip install -e .
```

After installation, the `yait` command is available in your shell.

## Quick Start

```bash
# Initialize yait in a git repo
cd my-project
yait init
# → Initialized yait in .yait/

# Create issues
yait new --title "Fix login bug" --type bug -l auth -a bill
# → Created issue #1: Fix login bug

yait new --title "Add dark mode" --type feature
# → Created issue #2: Add dark mode

# List open issues
yait list
# #   STATUS  TITLE              LABELS  ASSIGNEE
# #1  open    Fix login bug      auth    bill
# #2  open    Add dark mode      —       —

# View details
yait show 1

# Close an issue
yait close 1
# → Closed issue #1: Fix login bug

# Search
yait search "login"
```

## Command Reference

### `yait init`

Initialize yait in the current directory. Creates `.yait/` directory structure and commits.

```bash
yait init
```

Fails if `.yait/` already exists.

### `yait new`

Create a new issue.

```bash
yait new --title "Title" [--type bug] [-l label] [-a assignee] [-b "body text"]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--title` | | Issue title (required) |
| `--type` | | Issue type: `feature`, `bug`, `enhancement`, `misc` (default: `misc`) |
| `--label` | `-l` | Add label (repeatable) |
| `--assign` | `-a` | Assignee name |
| `--body` | `-b` | Issue body text |

Examples:

```bash
yait new --title "Crash on startup" --type bug -l urgent -l crash -a alice
yait new --title "Improve docs" --type enhancement
yait new --title "Random note"  # type defaults to misc
```

### `yait list`

List issues with optional filters.

```bash
yait list [--status open|closed|all] [--type bug] [--label x] [--assignee x]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--status` | `open` | Filter by status: `open`, `closed`, `all` |
| `--type` | | Filter by issue type |
| `--label` | | Filter by label |
| `--assignee` | | Filter by assignee |

Examples:

```bash
yait list                    # all open issues
yait list --status all       # everything
yait list --status closed    # closed only
yait list --type bug         # open bugs
yait list --label urgent     # open issues labeled "urgent"
yait list --assignee alice   # open issues assigned to alice
```

### `yait show <id>`

Show full details of an issue including frontmatter fields and body.

```bash
yait show 1
# #1  [open]  Fix login bug
# Labels: urgent, auth
# Assignee: bill
# Created: 2026-04-26T16:00:00+08:00
# Updated: 2026-04-26T16:00:00+08:00
#
# Issue description here.
```

### `yait close <id>`

Close an issue. Updates status to `closed`, sets `updated_at`, and commits.

```bash
yait close 1
# → Closed issue #1: Fix login bug
```

No-op if already closed.

### `yait reopen <id>`

Reopen a closed issue. Updates status back to `open` and commits.

```bash
yait reopen 1
# → Reopened issue #1: Fix login bug
```

No-op if already open.

### `yait comment <id> -m "text"`

Append a comment to an issue. The comment is added to the markdown body with a timestamp separator.

```bash
yait comment 1 -m "Fixed in commit abc123"
# → Added comment to issue #1
```

### `yait edit <id>`

Open the issue in `$EDITOR` for freeform editing. The editor receives the title and body; on save, both are updated and committed.

```bash
yait edit 1
```

If the editor exits without changes, the edit is cancelled.

### `yait label add <id> <name>` / `yait label remove <id> <name>`

Add or remove a label from an issue.

```bash
yait label add 1 urgent
yait label remove 1 urgent
```

Duplicate adds are rejected with a message; removing a non-existent label is also a no-op.

### `yait search <query>`

Full-text search across issue titles and bodies (case-insensitive).

```bash
yait search "login" [--status open|closed|all]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--status` | `all` | Filter results by status |

## Issue Types

Each issue has a `type` field. Valid types:

| Type | Use case |
|------|----------|
| `feature` | New functionality |
| `bug` | Something broken |
| `enhancement` | Improvement to existing functionality |
| `misc` | Everything else (default) |

Set at creation with `--type`. When omitted, defaults to `misc`. Can also be changed via `yait edit`.

## Data Format

### Directory structure

```
project-root/
└── .yait/
    ├── config.yaml        # next_id counter, version
    └── issues/
        ├── 1.md
        ├── 2.md
        └── ...
```

### config.yaml

```yaml
version: 1
next_id: 3
```

### Issue file (`.yait/issues/<id>.md`)

```markdown
---
id: 1
title: "Fix login bug"
status: open
type: bug
labels: [urgent, auth]
assignee: bill
created_at: "2026-04-26T16:00:00+08:00"
updated_at: "2026-04-26T16:00:00+08:00"
---

Issue description here.

---
**Comment** (2026-04-26 16:30):
This is a comment.
```

### Frontmatter fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | int | yes | Auto-incrementing, starts at 1 |
| `title` | string | yes | Issue title |
| `status` | enum | yes | `open` or `closed` |
| `type` | enum | yes | `feature`, `bug`, `enhancement`, `misc` |
| `labels` | list[str] | no | Tags, default `[]` |
| `assignee` | string | no | Responsible person |
| `created_at` | datetime | yes | ISO 8601 with timezone |
| `updated_at` | datetime | yes | Updated on every change |

### Git integration

Every write operation (`new`, `close`, `reopen`, `comment`, `edit`, `label add/remove`) automatically stages `.yait/` and creates a git commit. If the working directory is not a git repo, git operations are silently skipped.

Commit message format:

| Operation | Message |
|-----------|---------|
| init | `yait: init` |
| new | `yait: create issue #<id> — <title>` |
| close | `yait: close issue #<id>` |
| reopen | `yait: reopen issue #<id>` |
| comment | `yait: comment on issue #<id>` |
| edit | `yait: edit #<id>` |
| label add | `yait: label #<id> +<name>` |
| label remove | `yait: label #<id> -<name>` |

## Development

```bash
git clone https://github.com/user/yet-another-issue-tracker.git
cd yet-another-issue-tracker

# Install with test dependencies
pip install -e ".[test]"

# Run tests
pytest tests/ -v

# Or without a venv, using uv
uv run --with pytest --with pyyaml --with click pytest tests/ -v
```

### Project layout

```
yet-another-issue-tracker/
├── pyproject.toml
├── README.md
├── TESTING.md
├── docs/
│   └── PRD.md
├── src/
│   └── yait/
│       ├── __init__.py
│       ├── cli.py          # Click CLI entry point
│       ├── git_ops.py      # Git operations
│       ├── models.py       # Issue dataclass
│       └── store.py        # File I/O and config
└── tests/
    ├── conftest.py         # Shared fixtures
    ├── test_cli.py         # CLI end-to-end tests
    ├── test_git_ops.py     # Git integration tests
    ├── test_models.py      # Unit tests for Issue dataclass
    └── test_store.py       # Store integration tests
```

## License

MIT
