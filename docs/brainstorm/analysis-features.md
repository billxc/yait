# yait vs GitHub Issues — Feature Gap Analysis

> Date: 2026-04-26
> yait version: 0.2.0

## Background

yait (yet-another-issue-tracker) is a markdown + git-based local issue tracker with a Python CLI. This document compares it against GitHub Issues to identify functional gaps, organized by priority.

### yait Current State Summary

- **CLI commands:** init, new, list, show, close, reopen, comment, edit, label add/remove, search
- **Data model:** id, title, status (open/closed), type (feature/bug/enhancement/misc), labels, assignee (single), created_at, updated_at, body
- **Storage:** `.yait/issues/<id>.md` (YAML frontmatter + markdown body), `.yait/config.yaml` (next_id)
- **Git integration:** every write operation auto-commits to git
- **Dependencies:** click, pyyaml, Python >= 3.10

---

## 1. Core Missing (without these, incomplete as an issue tracker)

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Priority** | No built-in priority field. As a bug tracker, P0/P1/P2 is a fundamental need. Currently only achievable via labels (unstructured) | Low |
| **Milestone** | No way to group issues by version/iteration/sprint. GitHub Issues uses milestones as a core organizing concept for release planning | Medium |
| **Issue cross-references** | Issues are completely isolated — no `#123` references, no duplicate marking, no parent/child relationships | Medium |
| **Batch operations** | Can only operate on one issue at a time. Need `yait close 1 2 3`, bulk label, bulk assign | Low |
| **Sort options** | `yait list` has no `--sort` flag. Output order depends on filesystem listing, not by time/priority/update | Low |
| **Independent comment storage** | Comments are appended directly to the body text with `---` separators (`cli.py`). Cannot edit/delete individual comments, no comment author tracking, no comment timestamps as structured data | Medium |

## 2. Worth Adding (not essential, but users expect them)

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Due date** | No deadline tracking. Useful for time-sensitive issues | Low |
| **Issue templates** | No predefined formats for bug reports / feature requests. GitHub has `.github/ISSUE_TEMPLATE/` | Low |
| **Import/Export** | No JSON/CSV import or export. Blocks migration and external tooling integration | Low |
| **Multiple assignees** | `assignee` field in `models.py` is a single `str \| None`. No way to assign multiple people | Low |
| **Activity log / changelog** | Beyond `git log`, no in-issue record of state changes (who closed/reopened/relabeled and when) | Medium |
| **Custom fields** | Different projects need different metadata (severity, component, platform, etc.). Currently hardcoded schema | Medium |
| **Statistics / reports** | No open/closed counts, trend views, or group-by-label/type summaries | Low |
| **`yait delete`** | Only `close` exists — no way to truly remove an issue | Low |
| **Close reason** | GitHub distinguishes "completed" vs "not planned". yait only has binary open/closed | Low |
| **Pinned issues** | No way to mark important issues as pinned/sticky at the top of list output | Low |

## 3. Not Needed (overkill for a local CLI tool)

| Feature | Description | Why Skip |
|---------|-------------|----------|
| **Web UI / REST API** | GitHub's browser interface | CLI tool — terminal is the interface |
| **Notifications / email** | @mentions, subscriptions, email push | Single-user / small team; `git log` suffices |
| **Permissions / RBAC** | Role-based access control | Rely on git repo permissions |
| **Projects / Board view** | Kanban boards, project planning views | Too heavy for CLI; use dedicated tools if needed |
| **GitHub Apps / Webhooks** | Third-party integrations | Not a platform, just a local tool |
| **Reactions / emoji voting** | Thumbs-up, etc. | Purely social feature |
| **Issue-to-PR linking** | GitHub's "Development" panel | Git branch naming conventions handle this |
| **GraphQL API** | Programmatic query interface | Filesystem _is_ the API |
| **Lock conversation** | Prevent further comments | No need in local/small-team context |
| **Saved searches / custom views** | Persist filter combinations | Shell aliases (`alias ybugs='yait list --type bug'`) cover this |

---

## Recommended Roadmap

### Phase 1 — Quick wins (all low complexity)

1. **Priority field** — add `priority: str = "none"` to `models.py`, CLI `--priority` flag
2. **Sort options** — `yait list --sort created|updated|priority`
3. **Batch operations** — accept multiple IDs: `yait close 1 2 3`
4. **Close reason** — extend status to `open / closed:completed / closed:not_planned`

### Phase 2 — Medium effort (requires data model changes)

5. **Milestone** — new `milestone` field + `yait milestone` subcommand group
6. **Comment restructuring** — store comments as separate entries (list of dicts in frontmatter or separate files), enabling edit/delete per comment
7. **Issue cross-references** — parse `#N` in body/comments, build a reference index

### Phase 3 — Nice-to-haves

8. **Due date** — `due: YYYY-MM-DD` field
9. **Issue templates** — `.yait/templates/` directory with predefined frontmatter
10. **Import/Export** — `yait export --format json|csv`, `yait import <file>`
11. **Statistics** — `yait stats` command with counts and breakdowns
