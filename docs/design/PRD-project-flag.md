# PRD: `--project` Flag for Cross-Folder Operation

**Status:** Implemented
**Version:** 0.7.0
**Date:** 2026-04-27
**Author:** yait-dev
**Based on:** `api-design-project-flag.md` (pm-designer) + `review-project-flag.md` (pm-reviewer, APPROVE WITH CHANGES)

---

## 1. Goal

YAIT currently resolves the data directory as `.yait/` relative to `Path.cwd()`. This forces users to `cd` into the project root before running any command. In a multi-agent workgroup (e.g., BoxAgent), the admin and specialist agents live in different directories and need to manage issues from arbitrary locations.

**This feature adds:**
- A `--project / -P` global flag to select a named project stored under `~/.yait/projects/`
- A `YAIT_PROJECT` environment variable for session-level default
- A `YAIT_HOME` environment variable to override `~/.yait/` location
- A `yait project` subcommand group for project lifecycle management
- Full backward compatibility — local `.yait/` in cwd continues to work unchanged

---

## 2. User Stories

### 2.1 Admin agent manages issues from its own workspace

```bash
# Admin is in ~/workgroup/admin/, project tracker lives elsewhere
yait -P myapp new "Fix memory leak" -t bug -p p0
yait -P myapp list --status open
yait -P myapp close 3
```

### 2.2 Multiple specialists work on the same project concurrently

```bash
# Specialist A (in ~/workgroup/specialists/backend/)
yait -P myapp new "Add caching layer" -t feature -a backend-agent

# Specialist B (in ~/workgroup/specialists/frontend/)
yait -P myapp new "Fix dark mode toggle" -t bug -a frontend-agent

# Both hit the same issue store. The existing lock mechanism handles concurrency.
```

### 2.3 User with multiple projects

```bash
yait project list
# NAME       OPEN  CLOSED  UPDATED
# myapp      23    8       2026-04-27
# infra      7     4       2026-04-25

yait -P myapp list --type bug
yait -P infra stats
```

### 2.4 Existing local `.yait/` still works (backward compat)

```bash
cd ~/code/myapp   # has .yait/ directory
yait list         # works as before, uses .yait/ in cwd
```

### 2.5 User migrates a local project to a named project

```bash
cd ~/code/myapp
yait project import myapp
# Warning: git history for issues is not migrated.
#   History remains in the original repo's git log.
# Copied .yait/ -> ~/.yait/projects/myapp/
```

### 2.6 Multi-agent workgroup with custom YAIT_HOME

```bash
export YAIT_HOME=~/workgroup/.yait
yait project create shared-tracker
yait -P shared-tracker new "Shared task" -t feature
```

---

## 3. CLI API

### 3.1 Global option: `--project` / `-P`

Added to the top-level `main` Click group, inherited by all subcommands.

```
yait [--project NAME | -P NAME] <command> [args...]
```

All existing commands work unchanged with `-P`:

```bash
yait -P myapp init                  # equivalent to: yait project create myapp
yait -P myapp new "Fix bug" -t bug
yait -P myapp list --status all --wide
yait -P myapp show 1 --json
yait -P myapp close 1 2 3
yait -P myapp edit 1 -T "New title"
yait -P myapp search "login" --regex
yait -P myapp stats --by milestone --json
yait -P myapp milestone create v2.0 --due 2026-09-01
yait -P myapp bulk assign alice --filter-type bug
yait -P myapp export --format json -o backup.json
yait -P myapp config set defaults.type bug
```

### 3.2 Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YAIT_PROJECT` | (unset) | Default project name, equivalent to `-P` |
| `YAIT_HOME` | `~/.yait` | Location of global yait directory |

### 3.3 `project` subcommand group

```bash
yait project create <name>               # Create empty named project (with git init)
yait project list [--json]               # List all named projects
yait project delete <name> [-f]          # Delete a named project
yait project rename <old> <new>          # Rename a project
yait project import <name> [--path DIR]  # Import local .yait/ as named project
                           [--move]
yait project path <name> [--check]       # Print the data directory path
```

The `project` subcommand group ignores the `-P` flag — it manages projects, not issues within a project.

### 3.4 `yait -P myapp init` behavior

`yait -P myapp init` delegates to `yait project create myapp`. If the project already exists, prints "Project 'myapp' already initialized." This avoids user confusion about having two ways to create a named project.

---

## 4. Data Storage

### 4.1 Global directory layout

```
$YAIT_HOME/                          # default: ~/.yait/, overrideable via YAIT_HOME
  projects/
    myapp/                           # self-contained, flat (no nested .yait/)
      .git/                          # per-project git repo
      .gitignore                     # contains: yait.lock
      config.yaml
      yait.lock                      # transient, gitignored
      issues/
        1.md
        2.md
      templates/
        bug.md
      docs/
        auth-prd.md
    infra/
      .git/
      .gitignore
      config.yaml
      issues/
        ...
```

### 4.2 Key design decisions

**Flat layout (no nested `.yait/`):** Each named project's data dir is `$YAIT_HOME/projects/<name>/`, and files live directly inside it (`config.yaml`, `issues/`, etc.). This requires refactoring `store.py` to not hardcode the `.yait/` subdirectory, but produces a clean, unsurprising layout.

**Per-project git repo:** Each named project gets its own git repo, initialized by `yait project create`. This preserves per-project `yait log` and clean isolated history.

**`.gitignore` for `yait.lock`:** `yait project create` writes a `.gitignore` containing `yait.lock` into the project data dir. In project mode, `git_commit` stages with `git add .` (everything in the data dir), so without `.gitignore` the lock file would be committed on every write operation.

**Directory permissions:** `$YAIT_HOME/` is created with `0o700` (owner-only access) since issue data may contain sensitive information.

### 4.3 Local mode (unchanged)

```
project-root/
  .yait/                             # same as before
    config.yaml
    yait.lock
    issues/
    templates/
    docs/
```

Local mode is unchanged. `git_commit` continues to stage `.yait/` from the project root.

---

## 5. Resolution Logic

When a yait command is invoked, the data directory is resolved in this order:

```
1. --project / -P flag       (explicit, highest priority)
2. YAIT_PROJECT env var      (session default)
3. YAIT_HOME env var         (override global dir, combined with --project/env)
4. .yait/ in cwd             (backward compat, local mode)
5. Error with help text
```

```python
def resolve_data_dir(project_flag: str | None) -> tuple[Path, bool]:
    """Resolve the yait data directory.

    Returns (data_dir, is_project_mode) where:
    - data_dir: Path to the directory containing config.yaml, issues/, etc.
    - is_project_mode: True if using a named project (affects git staging)
    """
    yait_home = Path(os.environ.get("YAIT_HOME", "~/.yait")).expanduser()

    # 1. Explicit --project flag
    name = project_flag or os.environ.get("YAIT_PROJECT")
    if name:
        p = yait_home / "projects" / name
        if not p.is_dir():
            raise click.ClickException(
                f"Project '{name}' not found.\n"
                f"  Create it:      yait project create {name}\n"
                f"  List projects:  yait project list\n"
                f"  Import local:   yait project import {name}"
            )
        return p, True

    # 2. Local .yait/ in cwd
    local = Path.cwd() / ".yait"
    if local.is_dir():
        return local, False

    # 3. No project found
    raise click.ClickException(
        "No yait project found.\n\n"
        "  Use one of:\n"
        "    yait -P <name> <command>     Use a named project\n"
        "    export YAIT_PROJECT=<name>   Set default project for this shell\n"
        "    yait init                    Create local .yait/ in current directory\n"
        "    yait project create <name>   Create a new named project\n\n"
        "  List existing projects: yait project list"
    )
```

### 5.1 Special case: `init`

- `yait init` (no `-P`): creates `.yait/` in cwd (backward compat)
- `yait -P myapp init`: delegates to `yait project create myapp`
- The `init` command checks if `--project` was provided; if so, calls the project create logic instead of local init

---

## 6. Project Management Commands

### 6.1 `yait project create <name>`

1. Validates name: `[a-zA-Z0-9][a-zA-Z0-9_-]*`, max 64 chars
2. Creates `$YAIT_HOME/` with permissions `0o700` if it doesn't exist
3. Creates `$YAIT_HOME/projects/<name>/` with standard structure (config.yaml, issues/, templates/, docs/)
4. Writes `.gitignore` containing `yait.lock`
5. Runs `git init` + initial commit in the project dir

```
$ yait project create myapp
Created project 'myapp' at ~/.yait/projects/myapp/
```

Error if name already exists: `Error: Project 'myapp' already exists at ~/.yait/projects/myapp/`

### 6.2 `yait project list [--json]`

```
$ yait project list
NAME       OPEN  CLOSED  UPDATED
myapp      15    8       2026-04-27
infra      3     4       2026-04-25
```

Scans `$YAIT_HOME/projects/` for directories with a valid `config.yaml`.

### 6.3 `yait project delete <name> [-f]`

Prompts for confirmation unless `--force`. Deletes `$YAIT_HOME/projects/<name>/` entirely.

### 6.4 `yait project rename <old> <new>`

Renames the directory. Fails if `<new>` already exists. Prints warning after rename:

```
Renamed project 'old' -> 'new'.
Note: Update any scripts or YAIT_PROJECT env vars that reference 'old'.
```

### 6.5 `yait project import <name> [--path DIR] [--move]`

Imports a local `.yait/` directory into a named project.

1. Validates local `.yait/` exists (in cwd or `--path DIR`)
2. Creates the named project directory
3. Copies all contents (config.yaml, issues/, templates/, docs/)
4. Writes `.gitignore` containing `yait.lock`
5. Initializes git repo and makes initial commit
6. **Prints warning:** "Note: git history for issues is not migrated. History remains in the original repo's git log."
7. If `--move`: removes local `.yait/` after successful copy

Default behavior: **copy** (safe). `--move` removes local `.yait/`.

### 6.6 `yait project path <name> [--check]`

Prints absolute path. With `--check`, exits non-zero if project doesn't exist (useful for scripting).

```bash
yait project path myapp --check && yait -P myapp list
```

---

## 7. Git Integration

### 7.1 Project mode

Each named project is its own git repo. `git_commit` in project mode:
- Runs `git add .` in the project data dir (stages everything except gitignored `yait.lock`)
- Commits with the standard `yait: ...` message format

### 7.2 Local mode (unchanged)

`git_commit` continues to run `git add .yait` from the project root (cwd).

### 7.3 `yait log` with named projects

Works within the project's own git repo. Shows history scoped to that project.

The `log` command (cli.py:1366-1378) currently uses hardcoded paths like `.yait/issues/{id}.md` and `.yait/`. After the refactor:
- **Local mode:** git root = `data_dir.parent`, path = `.yait/issues/{id}.md` (unchanged)
- **Project mode:** git root = `data_dir`, path = `issues/{id}.md`

---

## 8. Concurrency

The existing `YaitLock` mechanism works per-project. Each named project has its own `yait.lock` file. Multiple agents can work on different projects simultaneously without blocking each other. Same-project concurrency is handled by the existing PID check + 60s timeout mechanism.

The `YaitLock.__init__` must be refactored to accept the data dir directly instead of hardcoding `.yait/`:
- Current: `self.lock_path = root / ".yait" / "yait.lock"` (lock.py:32)
- New: `self.lock_path = data_dir / "yait.lock"`

---

## 9. Implementation Plan

### 9.1 Overview

The core refactor changes the `root` convention: currently `root` means "project root directory" and every function appends `.yait/` to get the data dir. After the refactor, all internal functions receive the data dir directly.

### 9.2 File-by-file changes

#### 9.2.1 `src/yait/store.py` (541 lines) — ~20 LOC changed

**Current:** `_yait_root(root)` at line 32 returns `root / ".yait"`. Five helper functions call it:
- `_issues_dir(root)` (line 36)
- `_templates_dir(root)` (line 40)
- `_config_path(root)` (line 44)
- `_docs_dir(root)` (line 48)
- `init_store(root)` (line 52, via the helpers)

**Change:** Rename the `root` parameter to `data_dir` throughout (for clarity), and make `_yait_root()` return the argument unchanged:

```python
# Before (line 32-33):
def _yait_root(root: Path) -> Path:
    return root / YAIT_DIR

# After:
def _yait_root(data_dir: Path) -> Path:
    return data_dir
```

This is a single-line semantic change. All 5 helper functions continue to work because they call `_yait_root()`. The `YAIT_DIR` constant is no longer used in `_yait_root` but remains for `init_store` (local mode) and import logic.

**Downstream:** All 30+ public functions in `store.py` take `root: Path` as their first parameter. After this change, callers must pass the data dir instead of the project root. Since all callers come from `cli.py`, only `cli.py` needs updating (see below).

No changes to function signatures beyond renaming `root` → `data_dir` (optional, for clarity).

**Estimated delta:** ~5 lines changed (the `_yait_root` function + removing the constant usage).

#### 9.2.2 `src/yait/cli.py` (2156 lines) — ~120 LOC changed

**Current:** `_root()` at line 58-59 returns `Path.cwd()`. It's called at **47 call sites** across all command functions. Each call site does `root = _root()` and passes `root` to store functions, `git_commit()`, and `YaitLock()`.

**Changes:**

1. **Add `--project` to `main` group** (~10 LOC):
   ```python
   @click.group(...)
   @click.option("--project", "-P", default=None, envvar="YAIT_PROJECT",
                 help="Named project (stored in ~/.yait/projects/)")
   @click.pass_context
   def main(ctx, project):
       ctx.ensure_object(dict)
       ctx.obj["project"] = project
   ```

2. **Replace `_root()` with `_resolve(ctx)` returning `(data_dir, is_project_mode)`** (~25 LOC):
   - New function `_resolve(ctx)` implements the resolution logic from Section 5
   - Returns a tuple so `git_commit` knows which staging strategy to use

3. **Update all 47 `root = _root()` call sites** to `data_dir, is_project = _resolve(ctx)` (~47 lines, mechanical). Each command function gains `@click.pass_context` decorator and `ctx` parameter. The `root` variable is renamed to `data_dir`.

4. **Update all 35 `git_commit(root, msg)` call sites** to `git_commit(data_dir, msg, project_mode=is_project)` (~35 lines, mechanical).

5. **Update all 36 `YaitLock(root, cmd)` call sites** — no change needed if `YaitLock` accepts data dir directly (which it will after the lock.py refactor).

6. **Add `project` subcommand group** (~120 LOC):
   - `project create` — create dir structure, `.gitignore`, git init
   - `project list` — scan `$YAIT_HOME/projects/`, load configs, count issues
   - `project delete` — rmtree with confirmation
   - `project rename` — rename dir + warning message
   - `project import` — copy `.yait/` contents, git init, warning about history loss
   - `project path` — print path, `--check` flag

7. **Update `init` command** (~10 LOC): Check if `--project` was provided; if so, delegate to `project create` logic.

**Estimated delta:** ~120 lines new code (project commands), ~50 lines changed (call site updates).

#### 9.2.3 `src/yait/git_ops.py` (54 lines) — ~15 LOC changed

**Current:** `git_commit(root, message)` at line 38 hardcodes the staging path:
```python
yait_dir = root / ".yait"        # line 42
if yait_dir.exists():
    git_run(root, "add", ".yait")  # line 44
```

**Changes:**

1. **Add `project_mode` parameter to `git_commit()`**:
   ```python
   def git_commit(data_dir: Path, message: str, project_mode: bool = False) -> None:
       if project_mode:
           # Named project: data_dir IS the git root
           if not is_git_repo(data_dir):
               return
           git_run(data_dir, "add", ".")
           # check staged, commit
       else:
           # Local mode: data_dir is cwd/.yait, git root is cwd
           git_root = data_dir.parent
           if not is_git_repo(git_root):
               return
           git_run(git_root, "add", ".yait")
           # check staged, commit
   ```

2. **Update `git_log()`** to accept data_dir and derive the correct path:
   - Local mode: path is `.yait/issues/{id}.md` relative to git root (parent)
   - Project mode: path is `issues/{id}.md` relative to data_dir (git root)

**Estimated delta:** ~15 lines changed.

#### 9.2.4 `src/yait/lock.py` (131 lines) — ~3 LOC changed

**Current:** `YaitLock.__init__` at line 32 hardcodes:
```python
self.lock_path = root / ".yait" / "yait.lock"
```

**Change:** Accept data dir directly:
```python
self.lock_path = data_dir / "yait.lock"
```

Since cli.py already passes the resolved data dir after the refactor, `YaitLock(data_dir, "command")` just works.

**Estimated delta:** ~3 lines changed (parameter rename + path change).

### 9.3 Subtask breakdown

| # | Subtask | Files | Est. LOC | Depends |
|---|---------|-------|----------|---------|
| S1 | Refactor `_yait_root()` to identity function | `store.py` | 5 | — |
| S2 | Refactor `git_commit()` to accept `project_mode` | `git_ops.py` | 15 | — |
| S3 | Refactor `YaitLock.__init__` to accept data dir | `lock.py` | 3 | — |
| S4 | Add `--project` to `main` group + `_resolve()` | `cli.py` | 35 | S1 |
| S5 | Update all 47 `_root()` call sites in cli.py | `cli.py` | 50 | S4 |
| S6 | Update all 35 `git_commit()` call sites | `cli.py` | 35 | S2, S5 |
| S6b | Update `log` command hardcoded `.yait/` paths (cli.py:1371-1374) | `cli.py` | 8 | S5 |
| S7 | Add `project create` + `project list` commands | `cli.py` | 60 | S4 |
| S8 | Add `project delete/rename/path` commands | `cli.py` | 40 | S7 |
| S9 | Add `project import` with history warning | `cli.py` | 40 | S7 |
| S10 | Update `init` to delegate to `project create` when `-P` given | `cli.py` | 10 | S7 |
| S11 | Write tests for all new functionality | `tests/` | 200+ | S1-S10 |
| S12 | Update README and docs | docs/ | 30 | S11 |

### 9.4 Recommended implementation order

```
Phase 1a (Refactor internals — no visible behavior change):
  S1 → S3 → S2 → S4 → S5 → S6
  Run full test suite after each step. All 394 existing tests must pass.

Phase 1b (New commands):
  S7 → S8 → S9 → S10

Phase 1c (Tests + docs):
  S11 → S12
```

---

## 10. Test Plan

### 10.1 Resolution logic tests

| # | Scenario | Setup | Command | Expected |
|---|----------|-------|---------|----------|
| T1 | `-P` flag resolves to named project | Create project `foo` | `yait -P foo list` | Uses `$YAIT_HOME/projects/foo/` |
| T2 | `YAIT_PROJECT` env resolves | `YAIT_PROJECT=foo` | `yait list` | Uses named project `foo` |
| T3 | `-P` overrides env var | `YAIT_PROJECT=foo` | `yait -P bar list` | Uses `bar`, not `foo` |
| T4 | Local `.yait/` fallback | `.yait/` exists in cwd | `yait list` | Uses local `.yait/` |
| T5 | `YAIT_PROJECT` overrides local | `.yait/` exists + `YAIT_PROJECT=foo` | `yait list` | Uses `foo` |
| T6 | No project found | No `.yait/`, no env | `yait list` | Error with help text |
| T7 | Named project not found | No project `missing` | `yait -P missing list` | Error suggesting `project create` |
| T8 | `YAIT_HOME` override | `YAIT_HOME=/tmp/test` | `yait project create x` | Creates under `/tmp/test/projects/x/` |

### 10.2 Project CRUD tests

| # | Scenario | Expected |
|---|----------|----------|
| T9 | `project create myapp` | Dir created, config.yaml present, `.gitignore` has `yait.lock`, git repo initialized |
| T10 | `project create myapp` (already exists) | Error message |
| T11 | `project create` with invalid name (`../bad`, `a b`, `x` * 65) | Validation error |
| T12 | `project list` with 0, 1, 3 projects | Correct table output |
| T13 | `project list --json` | Valid JSON array |
| T14 | `project delete myapp` | Dir removed |
| T15 | `project delete myapp` (not found) | Error |
| T16 | `project rename old new` | Dir renamed, warning printed |
| T17 | `project rename old new` (target exists) | Error |
| T18 | `project path myapp` | Prints absolute path |
| T19 | `project path missing --check` | Exit code 1 |

### 10.3 Project import tests

| # | Scenario | Expected |
|---|----------|----------|
| T20 | `project import myapp` from cwd with `.yait/` | Files copied, git initialized, history warning printed |
| T21 | `project import myapp --move` | `.yait/` removed after copy |
| T22 | `project import myapp --path /other/dir` | Imports from specified path |
| T23 | `project import myapp` (no `.yait/` in cwd) | Error |
| T24 | `project import myapp` (name already exists) | Error |

### 10.4 Existing commands with `-P` tests

| # | Scenario | Expected |
|---|----------|----------|
| T25 | `yait -P foo new "Test" -t bug` | Issue created in named project |
| T26 | `yait -P foo list` | Lists issues from named project |
| T27 | `yait -P foo show 1` | Shows issue from named project |
| T28 | `yait -P foo close 1` | Closes issue, git commits in project repo |
| T29 | `yait -P foo search "test"` | Searches within named project |
| T30 | `yait -P foo stats` | Stats from named project |
| T31 | `yait -P foo milestone create v1.0` | Milestone in named project |
| T32 | `yait -P foo bulk assign alice 1 2` | Bulk op in named project |
| T33 | `yait -P foo config set defaults.type bug` | Config for named project |
| T34 | `yait -P foo export --format json` | Exports from named project |
| T35 | `yait -P foo log 1` | Shows log from project's git repo |

### 10.5 Concurrency tests

| # | Scenario | Expected |
|---|----------|----------|
| T36 | Lock file in named project | `yait.lock` created in project dir during write |
| T37 | Lock file NOT committed | `.gitignore` prevents `yait.lock` from being staged |
| T38 | Two projects lock independently | Write to project A doesn't block project B |

### 10.6 `init` delegation test

| # | Scenario | Expected |
|---|----------|----------|
| T39 | `yait -P myapp init` | Creates named project (same as `project create`) |
| T40 | `yait -P myapp init` (already exists) | "already initialized" message |

### 10.7 Regression tests

All 394 existing tests must continue to pass. The refactor changes the `root` convention but local mode behavior must be identical.

---

## 11. Migration

### 11.1 `project import` command

```bash
cd ~/code/myapp
yait project import myapp
```

**What it does:**
1. Copies `.yait/` contents into `$YAIT_HOME/projects/myapp/`
2. Writes `.gitignore` (containing `yait.lock`)
3. Runs `git init` + initial commit in the new project dir
4. Prints warning about git history

**What it does NOT do:**
- Does not migrate git history. The original project's git log retains the full `yait: ...` commit history for `.yait/` files. The named project starts with a fresh git repo and initial commit.

**Why:** Git history migration (cherry-picking commits that touch `.yait/`) is complex and fragile. The local repo still has the full history accessible via `git log -- .yait/`. For a future release, a `--include-history` flag could be added that replays the git log, but this is not in scope for v0.7.0.

### 11.2 No mandatory migration

Existing users are not required to migrate. Local `.yait/` continues to work exactly as before. Migration is opt-in.

---

## 12. Edge Cases

### 12.1 From original design

| # | Scenario | Behavior |
|---|----------|----------|
| E1 | `--project` with `init` | Delegates to `project create` |
| E2 | Both `--project` and local `.yait/` exist | `--project` wins |
| E3 | `YAIT_PROJECT` set + local `.yait/` exists | Env var wins |
| E4 | Project name validation | `[a-zA-Z0-9][a-zA-Z0-9_-]*`, max 64 chars |
| E5 | Git integration with local mode | Unchanged |
| E6 | Templates/docs per-project | No cross-project sharing |
| E7 | Config per-project | No global config overrides (future) |
| E8 | Export/import with `-P` | Works same as local mode |
| E9 | `~/.yait/` doesn't exist | Created on first `project create` |
| E10 | External doc refs in `show` (cli.py:531) | In local mode, `data_dir.parent / doc_ref` resolves correctly. In project mode, external refs have no local context — print "(external ref, not available in project mode)" |

### 12.2 From reviewer

| # | Scenario | Behavior |
|---|----------|----------|
| E11 | `yait -P foo project list` | `project` subgroup ignores `-P`, lists all projects |
| E12 | `project rename` breaks downstream | Warning message printed after rename |
| E13 | `project import` loses git history | Warning printed; history remains in original repo |
| E14 | `$YAIT_HOME` on shared system | Allows custom location for multi-agent setups |
| E15 | Sensitive data in `~/.yait/` | Dir created with `0o700` permissions |
| E16 | `project path --check` for scripting | Exit 1 if not found, exit 0 if found |

---

## 13. Version

This feature constitutes **v0.7.0**.

| Aspect | Current (v0.6.0) | v0.7.0 |
|--------|-------------------|--------|
| Data location | `.yait/` in cwd | `$YAIT_HOME/projects/<name>/` or `.yait/` in cwd |
| Project selection | Implicit (cwd) | `--project` > `YAIT_PROJECT` > cwd > error |
| Global dir override | n/a | `YAIT_HOME` env var |
| Git integration | Auto-commit in project repo | Per-project git repo (named) or project repo (local) |
| Concurrency | Per-directory lock | Per-project lock (same mechanism) |
| Cross-directory use | Not supported | Fully supported via `--project` |
| Backward compat | n/a | Full — local `.yait/` still works |

---

## 14. Future Considerations (not in scope)

- `~/.yait/global-config.yaml` — default project, aliases
- Cross-project queries: `yait --all-projects list --status open`
- `project import --include-history` — replay git history
- Cross-project template sharing
- Bulk commit batching for bulk operations (existing issue, not new to this design)
- Shell tab completion for `--project` (Click built-in, deferred to post-launch polish)
