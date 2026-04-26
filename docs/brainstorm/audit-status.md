# 实施审计 — v0.3.0 vs review-verdict

> 审计人: reviewer
> 日期: 2026-04-26
> 方法: 逐行对照 review-verdict.md 30 条采纳建议 vs 当前源码 + 测试

**总结: 7/30 已实现，0 部分实现，23 未实现。两个 P0 bug 均未修。**

另外：开发者实现了评审明确「延后」的 `next_id()` fcntl.flock (#延后1)，却跳过了两个 P0 bug 修复。建议重新对齐优先级。

---

## 已实现 (7/30)

| # | 建议 | 优先级 | 验证方式 |
|---|------|--------|---------|
| 4 | 输出加颜色 | P1 | `cli.py:28-33` 新增 `_status_color()` / `_type_color()`；`cli.py:45` header bold；`cli.py:49-52` 表格着色；`cli.py:165-167` show 着色。open=green, closed=red, bug=red, feature=blue, enhancement=yellow |
| 5 | `yait list --sort` | P1 | `cli.py:126` 新增 `--sort` option (id/created/updated)；`cli.py:137-142` sort 逻辑。测试: `TestListSort` |
| 6 | 批量 `yait close 1 2 3` | P1 | `cli.py:181` close 改为 `nargs=-1`；`cli.py:201` reopen 同理。测试: `TestCloseMultiple`, `TestReopenMultiple` |
| 13 | `--json` 输出 | P2 | list (`cli.py:125`), show (`cli.py:156`), search (`cli.py:317`) 均支持 `--json`；`models.py:18-29` 新增 `to_dict()`。测试: `TestListJson`, `TestShowJson`, `TestSearchJson` |
| 15 | `yait stats` | P2 | `cli.py:340-364` 新增 stats 命令，含 open/closed 计数、按 type/label 分组。测试: `TestStats` |
| 25 | body split 改 maxsplit=2 | P2 | `store.py:79-100` load_issue 完全重写为 `text.index("---\n", 4)` 方案，比建议的 `split("---\n", 2)` 更优——精确定位 frontmatter 结尾，不依赖 split 语义。同时增加了缺失 frontmatter 的错误检测 (line 84-85) |
| — | (额外) next_id fcntl.flock | 延后 | `store.py:45-55` 实现了评审建议「延后」的竞态条件修复。注意 `fcntl` 是 Unix-only，Windows 不兼容。测试: `test_next_id_file_locking` |

---

## 未实现 (23/30)

### P0 — 必须修复 (2 条，均未实现)

| # | 建议 | 缺了什么 |
|---|------|---------|
| 1 | 表格列对齐偏移 | `cli.py:40` `id_w = max(len(str(i.id))...)` 计算纯数字宽度，`cli.py:44` header `{'#':<{id_w}}` 占 id_w，但 `cli.py:52` data `#{i.id:<{id_w}}` 中 `#` 在 format spec 外，实际宽度 = 1 + id_w。**所有 list/search 表格列仍然错位。** 修复: `id_w = max(len(f"#{i.id}") for i in issues)` 并统一 header/data 格式 |
| 2 | 非数字 .md 文件导致崩溃 | `store.py:114-115` 仍然是 `for p in sorted(...glob("*.md")): load_issue(root, int(p.stem))`，无 `isdigit()` 守卫。任何非数字 `.md` 文件（如手动创建的 `notes.md`）都会 ValueError 崩溃 |

### P1 — 重要改进 (7 条未实现)

| # | 建议 | 缺了什么 |
|---|------|---------|
| 3 | `yait new "title"` positional arg | `cli.py:87` title 仍是 `@click.option("--title", required=True)`，未改为 positional argument |
| 7 | `yait assign` / `unassign` 命令 | cli.py 中无 assign/unassign 命令 |
| 8 | `edit` 支持 inline 修改 | `cli.py:239-261` edit 命令未变——仅接受 ID 参数，打开 $EDITOR。无 `--type`/`--assign`/`--label` 等 inline options |
| 9 | 优先级字段 | `models.py` Issue 无 `priority` 字段；CLI 无 `--priority` filter；无 priority 相关逻辑 |
| 10 | `search` 默认 status 改为 `open` | `cli.py:312` search 的 `--status` default 仍为 `"all"`，与 list (default `"open"`) 不一致 |
| 11 | config.yaml 损坏时友好报错 | `store.py:37-38` `_read_config` 无验证；`store.py:49` next_id 内的 `yaml.safe_load(f.read())` 也无验证。空文件/损坏文件仍会抛 TypeError |
| 12 | `yait init` 检测 .gitignore | `cli.py:72-81` init 命令无 .gitignore 检查逻辑 |

### P2 — Nice to have (14 条未实现)

| # | 建议 | 缺了什么 |
|---|------|---------|
| 14 | close reason | 无 close reason 字段或 CLI 参数 |
| 16 | `comment` 支持 $EDITOR | `cli.py:222` `-m` 仍为 required=True，无 click.edit() fallback |
| 17 | `show` 加 comment 计数 | `cli.py:154-175` show 输出无 comment 数量 |
| 18 | 命令短别名 ls/s/n/c | 无别名注册 |
| 19 | `--version` | `cli.py:65-67` main group 无 `@click.version_option` |
| 20 | empty state 引导 | `cli.py:147` 仍输出 `"No issues found."` 无创建提示 |
| 21 | 首次运行引导 | main() 无 `invoke_without_command` 引导逻辑 |
| 22 | search 高亮匹配 | search 直接调用 `_print_issue_table()`，无关键词高亮 |
| 23 | SystemExit 改 click.ClickException | `cli.py:25,60` 仍用 `raise SystemExit(1)` |
| 24 | list_cmd 传 label/assignee 给 store | `cli.py:132` 仍只传 status/type，`cli.py:133-136` 手动过滤 |
| 26 | assignee None 不转空串 | `store.py:69` 仍为 `issue.assignee or ""`，YAML 中存为空串 |
| 27 | git_commit 统一用 git_run | `git_ops.py:36-40` 仍用 raw `subprocess.run()` 检查 staged changes |
| 28 | due date 字段 | models.py 无 due_date 字段 |
| 29 | `yait export` | 无 export 命令 |
| 30 | `yait log <id>` | 无 log 命令 |

---

## 部分实现 (0/30)

无。

---

## 备注

1. **优先级偏差**: 开发者实现了评审明确延后的 `fcntl.flock` (Unix-only, 本地 CLI 几乎不可能并发)，但跳过了两个 P0 bug——表格对齐和非数字文件崩溃。建议下一轮先修 P0。
2. **load_issue 重写质量好**: 新的 `text.index("---\n", 4)` 方案比评审建议的 `split("---\n", 2)` 更健壮，同时附带了 frontmatter 缺失检测。
3. **list_cmd 过滤冗余依旧**: #24 (传 label/assignee 给 store) 未修。当前是 store 做 status+type 过滤，Python 侧再做 label+assignee 过滤。功能正确但逻辑分散。
4. **fcntl 跨平台风险**: `import fcntl` 在 Windows 上直接 ImportError。如果要支持 Windows 需要用 `filelock` 库或条件导入。
