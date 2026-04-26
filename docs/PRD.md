# PRD: yait — Yet Another Issue Tracker

**Version:** 0.2
**Date:** 2026-04-26
**Status:** Active

---

## Overview

yait is a local issue tracker built on markdown files and git. Each issue is a markdown file with YAML frontmatter. All changes are automatically committed to git history.

## Goals

- Zero external service dependencies, fully local
- Issue data is plain text, human-readable, git-friendly
- Simple CLI that integrates naturally with git workflow
- Install with `uv sync`

## Non-goals

- No web UI (future consideration)
- No multi-user / permissions
- No remote sync (user does their own push/pull)
- No kanban / gantt visualization
- No GitHub / GitLab sync

---

## User Stories

1. **Initialize**: As a developer, I run `yait init` in a project root to create `.yait/` and start tracking issues.
2. **Create issue**: I run `yait new --title "Fix login bug" --type bug --label auth` to create an issue with a type and label.
3. **List issues**: I run `yait list` to see all open issues, or `yait list --type bug` to filter by type.
4. **View details**: I run `yait show 1` to see issue #1 in full.
5. **Close issue**: I run `yait close 1` to mark it closed.
6. **Reopen**: I run `yait reopen 1` to re-open.
7. **Comment**: I run `yait comment 1 -m "Fixed in dev branch"` to add a comment.
8. **Edit**: I run `yait edit 1` to open `$EDITOR`.
9. **Labels**: I run `yait label add 1 feature` to add a label.
10. **Search**: I run `yait search "login" --type bug` to search bugs matching "login".

---

## Data Model

### Directory Structure

```
project-root/
└── .yait/
    ├── config.yaml        # project config
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

### Issue File Format (`<id>.md`)

```markdown
---
id: 1
title: "Fix login bug"
status: open
type: bug
labels:
  - auth
assignee: ""
created_at: "2026-04-26T10:00:00+08:00"
updated_at: "2026-04-26T10:00:00+08:00"
---

Issue body (optional, empty at creation)

---
**Comment** (2026-04-26 11:00):
Fixed in dev branch
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | int | yes | Auto-increment from 1 |
| title | string | yes | Title |
| status | enum | yes | `open` or `closed` |
| type | enum | yes | `feature`, `bug`, `enhancement`, `misc` (default: `misc`) |
| labels | list[str] | no | Labels, default `[]` |
| assignee | string | no | Responsible person |
| created_at | datetime | yes | ISO 8601 |
| updated_at | datetime | yes | Updated on every change |

---

## CLI Interface

Entry command: `yait`

### `yait init`

Initialize current directory as a yait project.

- Creates `.yait/` directory and `config.yaml`
- Creates `.yait/issues/` directory
- Errors if already initialized
- Auto git commit

### `yait new`

Create a new issue.

```
yait new --title "Title" [--type bug] [--label tag] [--assign alice] [--body "text"]
```

- `--title` required
- `--type` optional, one of `feature|bug|enhancement|misc`, default `misc`
- `--label` repeatable
- `--assign` optional
- `--body` optional
- Reads `next_id` from config, increments after creation
- Auto git commit: `yait: create issue #<id> — <title>`

### `yait list`

List issues.

```
yait list [--status open|closed|all] [--type bug] [--label tag] [--assignee name]
```

- Default: `status=open`
- Supports filtering by type, label, assignee
- Table output format

### `yait show <id>`

Show full issue details: formatted frontmatter + body.

### `yait close <id>`

Set status to `closed`, update `updated_at`, auto commit.

### `yait reopen <id>`

Set status to `open`, update `updated_at`, auto commit.

### `yait comment <id> -m "text"`

Append comment to markdown body, update `updated_at`, auto commit.

### `yait edit <id>`

Open `$EDITOR` (default: `vi`) to edit issue. Updates `updated_at` and commits on save.

### `yait label add|remove <id> <name>`

Add or remove a label. Updates `updated_at`, auto commit.

### `yait search <query>`

Full-text search across all issue titles and bodies (case-insensitive).

```
yait search <query> [--type bug] [--status open]
```

---

## Technical Design

- **Language**: Python 3.10+
- **Dependencies**: PyYAML (frontmatter), click (CLI)
- **Packaging**: pyproject.toml with hatchling, `uv sync`
- **Git ops**: `subprocess.run(["git", ...])` for git commands
- **Frontmatter**: Manual `---` delimiter parsing

### Project Structure

```
yet-another-issue-tracker/
├── pyproject.toml
├── README.md
├── src/
│   └── yait/
│       ├── __init__.py
│       ├── cli.py          # click CLI entry
│       ├── models.py       # Issue dataclass
│       ├── store.py        # file I/O + config
│       └── git_ops.py      # git operations
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_store.py
    ├── test_git_ops.py
    └── test_cli.py
```

---

## Milestones

### M1: Skeleton + Basic CRUD (v0.1) ✅

- Project structure (pyproject.toml, src layout)
- `yait init` — initialize .yait directory
- `yait new` — create issue
- `yait list` — list issues with --status filter
- `yait show` — view issue details
- Issue data model + file I/O
- `yait close` / `yait reopen`
- `yait comment` / `yait edit`
- `yait label add/remove`
- `yait search`
- Git auto-commit on all write operations
- Test suite (49 tests)

### M2: Issue Types (v0.2) — In Progress

- Add `type` field to Issue model (`feature`, `bug`, `enhancement`, `misc`)
- Default type: `misc`
- `yait new --type bug` support
- `yait list --type bug` filter
- `yait search --type bug` filter
- Update test suite (~60 tests)

### Future

- Web UI
- Export (JSON, CSV)
- Templates for issue types
- Bulk operations

---

## Error Handling

- `.yait/` not found: `Not a yait project. Run 'yait init' first.`
- Issue ID not found: `Issue #<id> not found.`
- Duplicate init: `yait already initialized.`
- Invalid type: click Choice validation error
- Git unavailable: warn but don't block operations

---

## Acceptance Criteria

v0.2 is complete when:

```bash
cd my-project
yait init
yait new --title "Bug report" --type bug -l urgent
yait new --title "New feature" --type feature
yait new --title "Note"  # defaults to misc
yait list --type bug     # shows only bug
yait search "feature" --type feature
```
