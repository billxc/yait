# yait — Yet Another Issue Tracker

A local issue tracker built on markdown files and git. Every issue is a `.md` file with YAML frontmatter; all changes are automatically committed to git history.

**v0.5.0** — milestones, bulk editing, templates, design docs, issue linking, and more.

## Install

**Requirements:** Python 3.10+, git, [uv](https://docs.astral.sh/uv/)

### Install (recommended)

```bash
uv tool install git+https://github.com/billxc/yait
```

This installs `yait` globally — use it directly from any directory.

### Install (development)

```bash
git clone https://github.com/billxc/yait.git
cd yait
uv sync
```

After installation, use `uv run yait` or activate the venv (`source .venv/bin/activate`) to use `yait` directly.

## Quick Start

```bash
cd my-project
yait init

# Create issues
yait new "Fix login bug" -t bug -l auth -a bill --priority p0
yait new "Add dark mode" -t feature --milestone v1.0

# List & search
yait list
yait list --type bug --milestone v1.0 --wide
yait search "login" --label auth --title-only

# Manage
yait close 1
yait edit 1 -T "New title" --priority p1
yait assign 1 alice

# Stats
yait stats
yait stats --by milestone --json
```

## Features

| Category | Features |
|----------|----------|
| **Core CRUD** | `new`, `show`, `close`, `reopen`, `delete`, `edit`, `comment` |
| **Labels & Assignment** | `label add/remove`, `assign`, `unassign` |
| **Milestones** | `milestone create/list/show/close/reopen/edit/delete` |
| **Bulk Editing** | `bulk label/assign/unassign/priority/milestone/type` with ID list or `--filter-*` |
| **Search** | Full-text, `--regex`, `--title-only`, `--count`, multi-field filters |
| **Statistics** | `stats` with `--by type/priority/label/milestone/assignee`, `--json` |
| **Templates** | `template create/list/delete`, `new --template` |
| **Design Docs** | `doc create/show/list/edit/delete/link/unlink` |
| **Issue Linking** | `link` (blocks/depends-on/relates-to), `unlink` |
| **Config** | `config set/reset` for defaults (type, priority, assignee) and display settings |
| **Output Formats** | `--compact`, `--wide`, auto-detect terminal width, `--json` |
| **Import/Export** | `export --format json/csv`, `import` from JSON |
| **History** | `log` — git-based change history per issue |

## Command Reference

### Core

```bash
yait init                              # Initialize .yait/ in current repo
yait new "Title" [options]             # Create issue
yait show <id> [--json]                # Show issue details
yait close <id> [id...]                # Close issue(s)
yait reopen <id> [id...]               # Reopen issue(s)
yait delete <id> [-f]                  # Delete issue permanently
yait edit <id> [options]               # Edit inline or open $EDITOR
yait comment <id> -m "text"            # Add comment
yait assign <id> <name>                # Assign issue
yait unassign <id>                     # Remove assignee
```

**`new` options:** `--title`, `--type/-t`, `--priority/-p`, `--label/-l` (repeatable), `--assign/-a`, `--body/-b` (`-` for stdin), `--body-file`, `--milestone/-m`, `--template`

**`edit` options:** `--title/-T`, `--type/-t`, `--priority/-p`, `--assign/-a`, `--body/-b`, `--body-file`, `--milestone/-m`

### List & Search

```bash
yait list [--status open|closed|all] [--type X] [--priority X]
          [--label X] [--assignee X] [--milestone X]
          [--sort id|created|updated] [--json]
          [--compact | --wide]
          [--has-doc | --no-doc | --doc <slug>]

yait search "query" [--status X] [--type X] [--priority X]
            [--label X] [--assignee X] [--milestone X]
            [--regex] [--title-only] [--count] [--json]
            [--compact | --wide]

yait stats [--by type|priority|label|milestone|assignee] [--json]
```

### Milestones

```bash
yait milestone create <name> [--description X] [--due YYYY-MM-DD]
yait milestone list [--status open|closed] [--json]
yait milestone show <name> [--json]
yait milestone close <name>
yait milestone reopen <name>
yait milestone edit <name> [--description X] [--due X]
yait milestone delete <name> [--force]
```

### Bulk Operations

Accepts issue IDs or `--filter-*` options (status, type, priority, label, assignee, milestone).

```bash
yait bulk label add <name> <ids...>
yait bulk label remove <name> <ids...>
yait bulk assign <name> <ids...>
yait bulk unassign <ids...>
yait bulk priority <p0-p3|none> <ids...>
yait bulk milestone <name> <ids...>
yait bulk type <type> <ids...>

# Filter mode example
yait bulk label add release-blocker --filter-priority p0 --filter-status open
yait bulk assign alice --filter-milestone v1.0
```

### Templates

```bash
yait template create <name>       # Opens $EDITOR
yait template list
yait template delete <name>
yait new "Title" --template bug   # Create from template
```

### Design Documents

```bash
yait doc create <slug> --title "Title" [-b "body" | --body-file X]
yait doc show <slug> [--json]
yait doc list [--json]
yait doc edit <slug> [--title X] [-b "body"]
yait doc delete <slug> [-f]
yait doc link <id> [id...] <slug-or-path>    # Link doc to issue(s)
yait doc unlink <id> <slug-or-path>
```

Supports managed docs (stored in `.yait/docs/`) and external file references (paths with `/`).

### Issue Linking

```bash
yait link <source> blocks <target>
yait link <source> depends-on <target>
yait link <source> relates-to <target>
yait unlink <source> <target>
```

Links are bidirectional — `link 3 blocks 5` also adds `blocked-by` on #5.

### Config

```bash
yait config                            # Show all settings
yait config set defaults.type bug      # Set default issue type
yait config set defaults.priority p2
yait config set display.max_title_width 60
yait config reset defaults.type        # Reset to default
```

### Import/Export

```bash
yait export [--format json|csv] [-o file]
yait import issues.json
```

### History

```bash
yait log [<id>] [-n 20]     # Git-based change log
```

## Issue Types

| Type | Use case |
|------|----------|
| `feature` | New functionality |
| `bug` | Something broken |
| `enhancement` | Improvement to existing functionality |
| `misc` | Everything else (default) |

## Priority Levels

`p0` (critical), `p1` (high), `p2` (medium), `p3` (low), `none` (default)

## Data Format

```
project-root/
└── .yait/
    ├── config.yaml          # next_id, milestones, defaults, display
    ├── issues/
    │   ├── 1.md
    │   └── ...
    ├── templates/
    │   ├── bug.md
    │   └── ...
    └── docs/
        ├── auth-prd.md
        └── ...
```

### Issue frontmatter fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Auto-incrementing |
| `title` | string | Issue title |
| `status` | enum | `open` / `closed` |
| `type` | enum | `feature`, `bug`, `enhancement`, `misc` |
| `priority` | enum | `p0`–`p3`, `none` |
| `labels` | list | Tags |
| `assignee` | string | Responsible person |
| `milestone` | string | Milestone reference |
| `docs` | list | Linked doc slugs/paths |
| `links` | list | Issue relationships (blocks, depends-on, relates-to) |
| `created_at` | datetime | ISO 8601 |
| `updated_at` | datetime | Updated on every change |

### Git integration

Every write operation automatically commits to git. If the working directory is not a git repo, git operations are silently skipped.

## Development

```bash
git clone https://github.com/billxc/yait.git
cd yait
uv sync --group test
uv run pytest tests/ -v
```

## License

MIT
