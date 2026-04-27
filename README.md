# yait — Yet Another Issue Tracker

A local issue tracker built on markdown files and git. Every issue is a `.md` file with YAML frontmatter; all changes are automatically committed to git history.

**v0.7.0** — cross-folder projects (`--project` / `-P`), milestones, bulk editing, templates, design docs, issue linking, concurrency lock, and more.

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

### Cross-Folder Usage (v0.7.0)

Use `--project / -P` to manage issues from any directory without `cd`:

```bash
# Create a named project (stored in ~/.yait/projects/)
yait project create myapp

# Work from anywhere
yait -P myapp new "Fix memory leak" -t bug -p p0
yait -P myapp list --status open
yait -P myapp close 3

# Set a session default
export YAIT_PROJECT=myapp
yait list   # uses myapp automatically

# Import an existing local .yait/ project
cd ~/code/myapp
yait project import myapp
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
| **Project Management** | `--project / -P` flag, `project create/list/delete/rename/import/path`, `YAIT_PROJECT` env var |
| **Config** | `config set/reset` for defaults (type, priority, assignee) and display settings |
| **Output Formats** | `--compact`, `--wide`, auto-detect terminal width, `--json` |
| **Import/Export** | `export --format json/csv`, `import` from JSON |
| **History** | `log` — git-based change history per issue |
| **Concurrency** | Multi-process safe via `yait.lock` global lock on all write ops; auto-recovers from crashes (PID check + 60s timeout) |

详细命令参考见 [docs/PRD.md](docs/PRD.md)。

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YAIT_PROJECT` | (unset) | Default project name, equivalent to `-P` |

Resolution order: `--project` flag > `YAIT_PROJECT` env > local `.yait/` in cwd.

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

### Local mode (default)

```
project-root/
└── .yait/
    ├── config.yaml          # next_id, milestones, defaults, display
    ├── yait.lock            # global lock for concurrent write protection (transient, gitignored)
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

### Named project mode (`--project` / `-P`)

```
~/.yait/                             
└── projects/
    ├── myapp/                       # self-contained, flat layout
    │   ├── .git/                    # per-project git repo
    │   ├── .gitignore               # contains: yait.lock
    │   ├── config.yaml
    │   ├── yait.lock
    │   ├── issues/
    │   │   ├── 1.md
    │   │   └── ...
    │   ├── templates/
    │   └── docs/
    └── infra/
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
