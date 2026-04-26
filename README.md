# yait — Yet Another Issue Tracker

A local issue tracker built on markdown files and git. Every issue is a `.md` file with YAML frontmatter; all changes are automatically committed to git history.

## Install

```bash
# With pip
pip install -e .

# With uv (no venv needed)
uv pip install -e .
```

**Requirements:** Python 3.10+

## Quick Start

```bash
# 1. Initialize yait in a git repo
cd my-project
yait init
# → Initialized yait in .yait/

# 2. Create issues
yait new --title "Fix login bug" --type bug -l auth -a bill
# → Created issue #1: Fix login bug

yait new --title "Add dark mode" --type feature
# → Created issue #2: Add dark mode

# 3. List open issues
yait list
# #   STATUS  TITLE              LABELS  ASSIGNEE
# #1  open    Fix login bug      auth    bill
# #2  open    Add dark mode      —       —

# 4. View details
yait show 1

# 5. Close an issue
yait close 1
# → Closed issue #1: Fix login bug
```

## Commands

### `yait init`

Initialize yait in the current directory. Creates `.yait/` and commits.

```bash
yait init
```

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
| `--status` | `open` | Filter by status |
| `--type` | | Filter by issue type |
| `--label` | | Filter by label |
| `--assignee` | | Filter by assignee |

```bash
yait list                    # all open issues
yait list --status all       # all issues
yait list --type bug         # open bugs only
yait list --label urgent     # open issues with "urgent" label
```

### `yait show <id>`

Show full details of an issue.

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

Close an issue. Updates status to `closed` and commits.

```bash
yait close 1
# → Closed issue #1: Fix login bug
```

### `yait reopen <id>`

Reopen a closed issue.

```bash
yait reopen 1
# → Reopened issue #1: Fix login bug
```

### `yait comment <id> -m "text"`

Add a comment to an issue. Appended to the markdown body.

```bash
yait comment 1 -m "Fixed in commit abc123"
# → Added comment to issue #1
```

### `yait edit <id>`

Open issue in `$EDITOR` for freeform editing.

```bash
yait edit 1
# Opens editor with title + body; saves and commits on exit.
```

### `yait label add <id> <name>` / `yait label remove <id> <name>`

Add or remove a label.

```bash
yait label add 1 urgent
yait label remove 1 urgent
```

### `yait search <query>`

Full-text search across titles and bodies (case-insensitive).

```bash
yait search "login" [--type bug] [--status open]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--status` | `all` | Filter by status |
| `--type` | | Filter by issue type |

## Issue Types

Each issue has a `type` field. Valid types:

| Type | Use case |
|------|----------|
| `feature` | New functionality |
| `bug` | Something broken |
| `enhancement` | Improvement to existing functionality |
| `misc` | Everything else (default) |

The type is set at creation with `--type` and can be changed via `yait edit`. When omitted, defaults to `misc`.

## Data Format

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
| `created_at` | datetime | yes | ISO 8601 |
| `updated_at` | datetime | yes | Updated on every change |

## Directory Structure

```
project-root/
└── .yait/
    ├── config.yaml        # next_id counter, version
    └── issues/
        ├── 1.md
        ├── 2.md
        └── ...
```

`config.yaml` contents:

```yaml
version: 1
next_id: 3
```

## Development

```bash
git clone https://github.com/user/yet-another-issue-tracker.git
cd yet-another-issue-tracker
pip install -e ".[test]"

# Run tests
pytest tests/ -v

# Or with uv
uv run --with pytest --with pyyaml --with click pytest tests/ -v
```

## License

MIT
