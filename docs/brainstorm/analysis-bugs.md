# yait 代码审查报告

**审查人**: brainstorm-2 (QA)
**日期**: 2026-04-26
**版本**: v0.2.0

---

## A. 潜在 Bug

### 1. `next_id()` 竞态条件 — 高

**位置**: `store.py:45-50`

Read-modify-write `config.yaml` 无任何文件锁。两个进程同时调用 `next_id()` 会读到相同的 `next_id` 值，导致两个 issue 拿到相同 ID，后写入的文件覆盖先写入的，造成数据丢失。

```python
def next_id(root: Path) -> int:
    cfg = _read_config(root)     # 读
    nid = cfg["next_id"]
    cfg["next_id"] = nid + 1
    _write_config(root, cfg)     # 写 — 无锁
    return nid
```

**影响**: 并发场景下 issue 数据丢失。

**建议修复**: 用 `fcntl.flock` 或 `filelock` 库对 config.yaml 加排他锁：

```python
import fcntl

def next_id(root: Path) -> int:
    cfg_path = _config_path(root)
    with open(cfg_path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        cfg = yaml.safe_load(f.read())
        nid = cfg["next_id"]
        cfg["next_id"] = nid + 1
        f.seek(0)
        f.truncate()
        f.write(yaml.dump(cfg, default_flow_style=False))
    return nid
```

---

### 2. 表格列对齐偏移 — 中

**位置**: `cli.py:31-40`

`_print_issue_table()` 的 header 用 `'#'` 占 `id_w` 列宽，但 data 行的 `#{i.id:<{id_w}}` 中 `#` 在 format spec 外面，实际宽度 = 1 + id_w。所有列向右错位。

```
#  STATUS  TYPE  TITLE       LABELS        ASSIGNEE   ← header
#1  open    misc  my issue    —             —          ← data（多出 1 字符）
```

**影响**: 所有 `list` 和 `search` 输出的表格列不对齐。

**建议修复**:

```python
id_w = max(len(f"#{i.id}") for i in issues)
header = f"{'ID':<{id_w}}  {'STATUS':<{st_w}}  ..."
# data:
click.echo(f"{'#'+str(i.id):<{id_w}}  {i.status:<{st_w}}  ...")
```

---

### 3. issues 目录中非数字文件名会崩溃 — 中

**位置**: `store.py:108`

`list_issues()` 对 `.yait/issues/*.md` 做 `int(p.stem)`，如果目录中存在非数字命名文件（如 macOS 的 `.DS_Store`、用户手动创建的 `notes.md`），直接抛 `ValueError` 导致整个命令崩溃。

```python
for p in sorted(issues_path.glob("*.md")):
    issue = load_issue(root, int(p.stem))  # ValueError if stem is not numeric
```

**影响**: 日常使用中遇到即崩溃，macOS 用户尤其容易触发。

**建议修复**:

```python
for p in sorted(issues_path.glob("*.md")):
    if not p.stem.isdigit():
        continue
    issue = load_issue(root, int(p.stem))
```

---

### 4. config.yaml 损坏时 TypeError — 中

**位置**: `store.py:38`

如果 `config.yaml` 为空或被破坏，`yaml.safe_load()` 返回 `None`，后续 `cfg["next_id"]` 抛出 `TypeError: 'NoneType' object is not subscriptable`，用户看不懂。

**影响**: 配置损坏后所有命令不可用，且错误信息无法帮助用户修复。

**建议修复**:

```python
def _read_config(root: Path) -> dict:
    cfg = yaml.safe_load(_config_path(root).read_text())
    if not isinstance(cfg, dict) or "next_id" not in cfg:
        raise RuntimeError(
            f"Corrupted config: {_config_path(root)}. "
            "Delete .yait/config.yaml and run 'yait init' to reset."
        )
    return cfg
```

---

### 5. `edit` 命令 title 解析歧义 — 低

**位置**: `cli.py:221-227`

如果用户想要的 title 字面以 `"title:"` 开头（如 `"Title: Best Practices for API Design"`），`title:` 前缀会被误剥离，实际保存为 `"Best Practices for API Design"`。

```python
if first_line.lower().startswith("title:"):
    issue.title = first_line[len("title:"):].strip()
```

**影响**: 特定 title 被静默截断。

**建议修复**: 不要自动剥离 `title:` 前缀，改用 YAML frontmatter 格式或明确的分隔符。

---

### 6. body 首行为 `---` 时 split 行为异常 — 低

**位置**: `store.py:79-82`

`content.split("---\n")` 无限制地拆分所有 `---\n`。当 body 的第一行恰好是 `---` 时，`parts` 中出现多余空串，`body.strip()` 可能丢失有意义的空行。

**建议修复**: 使用 `content.split("---\n", 2)` 限制拆分次数：

```python
parts = content.split("---\n", 2)
fm = yaml.safe_load(parts[1])
body = parts[2].strip() if len(parts) > 2 else ""
```

---

## B. 代码质量问题

### 7. `list_cmd()` 未传递 label/assignee 给 `list_issues()` — 中

**位置**: `cli.py:118-122`

`list_issues()` 已有 `label` 和 `assignee` 参数，但 `list_cmd()` 只传了 `status` 和 `type`，然后在 Python 侧重复过滤。功能冗余，API 使用不一致。

```python
issues = list_issues(root, status=st, type=type)  # 没传 label/assignee
if label:
    issues = [i for i in issues if label in i.labels]  # 手动再过滤
```

**建议修复**: 直接传全部参数：

```python
issues = list_issues(root, status=st, type=type, label=label, assignee=assignee)
```

---

### 8. Issue model 无任何字段校验 — 中

**位置**: `models.py`

- `status` 可以是任意字符串（不限于 open/closed）
- `type` 不校验是否在 `ISSUE_TYPES` 中
- `id` 可以是 0 或负数
- `title` 可以是空字符串

校验完全依赖 CLI 层的 `click.Choice`，直接用 store API 的调用方无任何保护。

**建议修复**: 在 `__post_init__` 中加基本校验：

```python
def __post_init__(self):
    if self.id < 1:
        raise ValueError(f"Invalid issue id: {self.id}")
    if self.status not in ("open", "closed"):
        raise ValueError(f"Invalid status: {self.status}")
    if self.type not in ISSUE_TYPES:
        raise ValueError(f"Invalid type: {self.type}")
    if not self.title.strip():
        raise ValueError("Title cannot be empty")
```

---

### 9. assignee 存储 None/空串不一致 — 低

**位置**: `store.py:65, 89`

- `save_issue`: `None` → 写为 `""` (YAML `assignee: ''`)
- `load_issue`: `""` → 读回为 `None`

Round-trip 正确，但 YAML 文件中 `assignee: ''` 看起来像有值，手动编辑时容易混淆。

**建议修复**: save 时保留 `None` → YAML `null`：

```python
"assignee": issue.assignee,  # None → YAML null
```

---

### 10. `git_commit()` 内 subprocess 调用风格不一致 — 低

**位置**: `git_ops.py:37-41`

检查 staged changes 时直接用 `subprocess.run()` 而非已有的 `git_run()` 封装。

**建议修复**: 给 `git_run` 增加 `check` 参数支持，统一调用入口。

---

### 11. `_now()` 时间格式依赖本地时区 — 低

**位置**: `cli.py:18`

`datetime.now(timezone.utc).astimezone().isoformat()` 输出本地时区 offset（如 `+08:00`），不同机器上创建的 issue 时间格式不一致，diff/排序不友好。

**建议修复**: 统一存 UTC：

```python
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
```

---

## C. 用户体验问题

### 12. 无 `assign` / `unassign` 子命令 — 中

创建时可以 `--assign`，但创建后无法直接修改 assignee，需要通过 `edit` 打开编辑器手动改。对于常见操作来说太重了。

**建议修复**: 增加专用命令：

```
yait assign <id> <user>
yait unassign <id>
```

---

### 13. `close` / `reopen` 无批量操作 — 低

一次只能关闭/重开一个 issue，批量操作需要多次调用。

**建议修复**: 支持多 ID 参数 `yait close 1 2 3`。

---

### 14. `search` 不高亮匹配关键词 — 低

搜索结果和普通 `list` 输出完全一样，用户无法看出哪里匹配了。

**建议修复**: 用 `click.style()` 高亮匹配部分。

---

### 15. 错误退出方式不够 Click-idiomatic — 低

**位置**: `cli.py:22-24`

`_require_init` 用 `raise SystemExit(1)` 退出，而非 Click 惯用的 `raise click.ClickException(...)` 或 `ctx.exit(1)`。在测试中 `SystemExit` 需要特殊处理。

---

## D. 测试覆盖盲区

| 盲区 | 风险 | 说明 |
|---|---|---|
| `edit` 命令 | 高 | 完全未测试，可 mock `click.edit` |
| issues 目录有非数字文件 | 中 | `.DS_Store` 等会导致崩溃 |
| config.yaml 损坏/空文件 | 中 | 无友好错误处理 |
| 空 title 创建 issue | 低 | model 不校验 |
| `search` 匹配 body 内容 | 低 | 只测了 title 匹配 |
| `comment` 多次追加后 body 格式 | 低 | 仅测了单次 comment |
| `list_cmd` 的 `--label` / `--assignee` CLI 过滤 | 低 | store 层有测试但 CLI 层没有 |

---

## 总结

| 优先级 | 问题编号 | 简述 |
|---|---|---|
| **高** | #1, #8 | next_id 竞态条件, model 无校验 |
| **中** | #2, #3, #4, #7, #12 | 表格对齐, 非数字文件崩溃, config 损坏, API 不一致, 缺 assign 命令 |
| **低** | #5, #6, #9, #10, #11, #13, #14, #15 | edit 解析歧义, body 边界, None/空串, subprocess 风格, 时间格式, UX 细节 |

**最需优先修复**: #1 (竞态 — 数据丢失风险) 和 #3 (非数字文件 — macOS 日常必触发)。
