# PRD: yait — Yet Another Issue Tracker

**Version:** 0.7.0
**Date:** 2026-04-27
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
- No webhook / automation
- No shell auto-completion (users can configure Click's built-in support)

---

## User Stories

1. **Initialize**: As a developer, I run `yait init` in a project root to create `.yait/` and start tracking issues.
2. **Create issue**: I run `yait new --title "Fix login bug" --type bug --label auth` to create an issue with a type and label.
3. **Create from template**: I run `yait new "Login crash" --template bug` to create an issue from a predefined template.
4. **List issues**: I run `yait list` to see all open issues, or `yait list --type bug` to filter by type.
5. **View details**: I run `yait show 1` to see issue #1 in full, including links and docs.
6. **Close issue**: I run `yait close 1` to mark it closed.
7. **Reopen**: I run `yait reopen 1` to re-open.
8. **Delete**: I run `yait delete 1` to permanently remove an issue.
9. **Comment**: I run `yait comment 1 -m "Fixed in dev branch"` to add a comment.
10. **Edit**: I run `yait edit 1` to open `$EDITOR`.
11. **Labels**: I run `yait label add 1 feature` to add a label.
12. **Search**: I run `yait search "login" --type bug --regex` to search bugs matching "login".
13. **Statistics**: I run `yait stats --by milestone` to see issue distribution by milestone.
14. **Milestones**: I run `yait milestone create v1.0 --due 2026-06-01` to manage milestones.
15. **Bulk edit**: I run `yait bulk label add urgent 1 2 3` to batch-modify issues.
16. **Issue linking**: I run `yait link 3 blocks 5` to create relationships between issues.
17. **Design docs**: I run `yait doc create auth-prd --title "Auth PRD"` to manage design documents linked to issues.
18. **Configuration**: I run `yait config set defaults.type bug` to customize defaults.
19. **Export/Import**: I run `yait export --format json` or `yait import data.json` for data portability.
20. **Cross-folder project**: I run `yait -P myapp list` to manage issues from any directory without `cd`.
21. **Create named project**: I run `yait project create myapp` to create a named project stored in `~/.yait/projects/`.
22. **Import local project**: I run `yait project import myapp` to import an existing local `.yait/` as a named project.
23. **List projects**: I run `yait project list` to see all named projects with their issue counts.
24. **Dashboard**: I run `yait dashboard` to generate a local HTML dashboard showing summary cards, breakdowns, milestone progress, and issue tables.

---

## Data Model

### Directory Structure

**Local mode (default):**

```
project-root/
└── .yait/
    ├── config.yaml        # project config (incl. milestones, defaults, display)
    ├── issues/
    │   ├── 1.md
    │   ├── 2.md
    │   └── ...
    ├── templates/
    │   ├── bug.md
    │   └── feature.md
    └── docs/
        ├── auth-prd.md
        └── auth-tech-spec.md
```

**Named project mode (`--project` / `-P`):**

```
~/.yait/
└── projects/
    └── myapp/                    # self-contained, flat layout
        ├── .git/                 # per-project git repo
        ├── .gitignore            # contains: yait.lock
        ├── config.yaml
        ├── yait.lock
        ├── issues/
        ├── templates/
        └── docs/
```

### config.yaml

```yaml
version: 1
next_id: 3
milestones:
  v1.0:
    status: open
    description: "First release"
    due_date: "2026-06-01"
    created_at: "2026-04-26T12:00:00+08:00"
defaults:
  type: misc
  priority: null
  assignee: null
  labels: []
display:
  max_title_width: 50
  date_format: short
```

### Issue File Format (`<id>.md`)

```markdown
---
id: 1
title: "Fix login bug"
status: open
type: bug
priority: p1
labels:
  - auth
assignee: "alice"
milestone: "v1.0"
docs:
  - auth-prd
links:
  - type: blocks
    target: 5
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
| title | string | yes | Title (non-blank) |
| status | enum | yes | `open` or `closed` |
| type | enum | yes | `feature`, `bug`, `enhancement`, `misc` (default: `misc`) |
| priority | enum | no | `p0`, `p1`, `p2`, `p3` or none |
| labels | list[str] | no | Labels, default `[]` |
| assignee | string | no | Responsible person |
| milestone | string | no | Milestone reference |
| docs | list[str] | no | Linked documents (slug or path) |
| links | list[dict] | no | Issue relationships (blocks/depends-on/relates-to) |
| created_at | datetime | yes | ISO 8601 |
| updated_at | datetime | yes | Updated on every change |

---

## CLI Interface

Entry command: `yait`

### Core CRUD

| Command | Description |
|---------|-------------|
| `yait init` | Initialize .yait directory |
| `yait new --title "Title" [--type bug] [--label tag] [--assign alice] [--body "text"] [--template bug] [--priority p1] [--milestone v1.0]` | Create issue |
| `yait show <id> [--json]` | View issue details |
| `yait list [--status open\|closed\|all] [--type bug] [--label tag] [--assignee name] [--milestone v1.0] [--priority p0] [--has-doc] [--no-doc] [--doc slug] [--compact\|--wide] [--json]` | List issues |
| `yait close <id>` | Close issue |
| `yait reopen <id>` | Reopen issue |
| `yait delete <id>` | Delete issue permanently |

### Editing

| Command | Description |
|---------|-------------|
| `yait edit <id>` | Open in $EDITOR |
| `yait comment <id> -m "text"` | Add comment |
| `yait label add\|remove <id> <name>` | Manage labels |
| `yait assign <id> <name>` | Assign issue |
| `yait unassign <id>` | Unassign issue |

### Search & Stats

| Command | Description |
|---------|-------------|
| `yait search <query> [--type] [--status] [--label] [--priority] [--assignee] [--milestone] [--regex] [--title-only] [--count]` | Advanced search |
| `yait stats [--by milestone\|assignee\|priority] [--json]` | Statistics by multiple dimensions |
| `yait log <id>` | View change history |

### Milestone Management

| Command | Description |
|---------|-------------|
| `yait milestone create <name> [--description] [--due YYYY-MM-DD]` | Create milestone |
| `yait milestone list [--status open\|closed] [--json]` | List milestones with progress |
| `yait milestone show <name> [--json]` | Milestone details + linked issues |
| `yait milestone close <name>` | Close milestone |
| `yait milestone reopen <name>` | Reopen milestone |
| `yait milestone edit <name> [--description] [--due]` | Edit milestone |
| `yait milestone delete <name> [--force]` | Delete milestone |

### Bulk Operations

| Command | Description |
|---------|-------------|
| `yait bulk label add\|remove <value> <IDs...>` | Batch label changes |
| `yait bulk assign <name> <IDs...>` | Batch assign |
| `yait bulk unassign <IDs...>` | Batch unassign |
| `yait bulk priority <level> <IDs...>` | Batch priority |
| `yait bulk milestone <name> <IDs...>` | Batch milestone |
| `yait bulk type <type> <IDs...>` | Batch type |
| All bulk commands support `--filter-*` options | Filter-based bulk ops |

### Issue Linking

| Command | Description |
|---------|-------------|
| `yait link <id> blocks\|depends-on\|relates-to <target>` | Create link |
| `yait unlink <id> <target>` | Remove link |

### Design Documents

| Command | Description |
|---------|-------------|
| `yait doc create <slug> --title "Title" [-b "body"\|--body-file path]` | Create managed doc |
| `yait doc show <slug> [--json]` | View doc + linked issues |
| `yait doc list [--json]` | List all docs |
| `yait doc edit <slug> [--title] [-b "body"]` | Edit doc |
| `yait doc delete <slug> [-f]` | Delete doc |
| `yait doc link <IDs...> <slug-or-path>` | Link doc to issues |
| `yait doc unlink <id> <slug-or-path>` | Unlink doc from issue |

### Issue Templates

| Command | Description |
|---------|-------------|
| `yait template create <name>` | Create template (opens $EDITOR) |
| `yait template list` | List templates |
| `yait template delete <name>` | Delete template |

### Configuration

| Command | Description |
|---------|-------------|
| `yait config` | Show current config |
| `yait config set <key> <value>` | Set config value |
| `yait config reset <key>` | Reset to default |

### Data Portability

| Command | Description |
|---------|-------------|
| `yait export [--format json\|csv]` | Export issues |
| `yait import <file>` | Import issues from JSON |

### Dashboard

| Command | Description |
|---------|-------------|
| `yait dashboard` | Generate local HTML dashboard and open in browser |
| `yait dashboard --no-open` | Generate without opening browser |
| `yait dashboard -o PATH` | Custom output file path |

Dashboard contents:
- **Summary cards** — Total, Open, Closed, Close Rate
- **Breakdown by type and priority** — issue counts per category
- **Milestone progress** — progress bars for each milestone
- **Open issues table** — sortable list of all open issues
- **Recently closed issues** — last closed issues for quick reference

### Project Management

| Command | Description |
|---------|-------------|
| `yait project create <name>` | Create a named project (with git init) |
| `yait project list [--json]` | List all named projects with stats |
| `yait project delete <name> [-f]` | Delete a named project |
| `yait project rename <old> <new>` | Rename a project |
| `yait project import <name> [--path DIR] [--move]` | Import local .yait/ as named project |
| `yait project path <name> [--check]` | Print the data directory path |

**Global option:** `--project / -P <name>` — select a named project for any command.

**Environment variables:** `YAIT_PROJECT` (default project name).

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
├── TESTING.md
├── docs/
│   ├── PRD.md
│   ├── DESIGN-v0.5.md
│   └── ...
├── src/
│   └── yait/
│       ├── __init__.py
│       ├── cli.py          # click CLI entry (all commands)
│       ├── models.py       # Issue, Milestone, Doc, Template dataclasses
│       ├── store.py        # file I/O + config + milestones + templates + docs
│       ├── lock.py         # global lockfile for concurrent write protection
│       ├── dashboard.py    # HTML dashboard generation
│       └── git_ops.py      # git operations
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_store.py
    ├── test_git_ops.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_doc_cli.py
    ├── test_doc_store.py
    ├── test_links.py
    ├── test_links_cli.py
    ├── test_output_format.py
    ├── test_lock.py
    ├── test_project.py
    └── test_security.py
```

---

## Version History

### v0.1 — Skeleton + Basic CRUD ✅

- Project structure (pyproject.toml, src layout)
- `yait init`, `yait new`, `yait list`, `yait show`
- `yait close` / `yait reopen`
- `yait comment` / `yait edit`
- `yait label add/remove`
- `yait search`
- Git auto-commit on all write operations
- Test suite (49 tests)

### v0.2 — Issue Types ✅

- `type` field (`feature`, `bug`, `enhancement`, `misc`)
- `yait new --type`, `yait list --type`, `yait search --type`

### v0.3 — Priority, Milestone field, Assign, Stats, Export/Import ✅

- `priority` field (p0–p3)
- `milestone` field (string on issue)
- `yait assign` / `yait unassign`
- `yait stats` (by type/label)
- `yait log` (change history)
- `yait export` (JSON/CSV) / `yait import` (JSON)
- `yait delete`
- Bug fixes: blank title validation, negative ID handling, `---` arg parsing, priority option

### v0.5 — Full Feature Set ✅

**Phase 1 — Core (P0):**
- Milestone management: `yait milestone create/list/show/close/reopen/edit/delete`
- Bulk editing: `yait bulk label/assign/unassign/priority/milestone/type` with ID lists and `--filter-*`

**Phase 2 — Enhance (P1):**
- Enhanced stats: `yait stats --by milestone|assignee|priority`, `--json`
- Advanced search: `--label`, `--priority`, `--assignee`, `--milestone`, `--regex`, `--title-only`, `--count`
- Issue templates: `yait template create/list/delete`, `yait new --template`
- Design document management: `yait doc create/show/list/edit/delete/link/unlink`

**Phase 3 — Polish (P2):**
- Issue linking: `yait link/unlink` with blocks/depends-on/relates-to relationships
- Config enhancement: `yait config/config set/config reset` with defaults and display settings
- Output formatting: compact/wide modes, auto-detect terminal width, title truncation

### v0.6 — Concurrency Safety ✅

- Global lockfile (`.yait/yait.lock`) for concurrent write protection
- PID + timestamp stale lock detection with exponential backoff retry
- Cross-platform (no `fcntl` dependency)
- All write CLI commands wrapped with `YaitLock` context manager

### v0.7 — Cross-Folder Projects (`--project` flag) ✅

- `--project / -P` global flag to select named projects stored under `~/.yait/projects/`
- `YAIT_PROJECT` env var for session-level default project
- `yait project` subcommand group: `create/list/delete/rename/import/path`
- Per-project git repo with isolated history
- Full backward compatibility — local `.yait/` in cwd still works unchanged
- `yait -P <name> init` delegates to `project create`
- 440 automated tests (46 new for project features)

### Future

- Web UI
- Performance optimization (indexing for 1000+ issues)

---

## Error Handling

- `.yait/` not found: `Not a yait project. Run 'yait init' first.`
- Issue ID not found: `Issue #<id> not found.`
- Duplicate init: `yait already initialized.`
- Invalid type: click Choice validation error
- Blank title: validation error
- Negative ID: validation error
- Git unavailable: warn but don't block operations
- Bulk operation failures: skip and report summary (success/failed/skipped)
- File corruption: warn and skip, don't crash

---

## Acceptance Criteria

v0.7.0 is complete when all features above are implemented and:

- 440 automated tests passing
- All v0.6.x data is readable without migration
- Local `.yait/` mode works unchanged (full backward compat)
- All new commands documented and tested
