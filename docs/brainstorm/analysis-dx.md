# yait CLI 设计与开发者体验分析

> 分析日期: 2026-04-26
> 版本: v0.2.0 (302 行 CLI, 119 行 store, 44 行 git_ops, 18 行 models)

---

## A. CLI 设计对比（vs gh / jira-cli / todo.txt / taskwarrior）

### A1. `yait new "title"` — positional title

| | |
|---|---|
| **现状** | `yait new --title "Fix login bug" --type bug` |
| **建议** | `yait new "Fix login bug" --type bug`（title 改为 positional arg，保留 `--title` 兼容） |
| **对比** | gh: `gh issue create -t "title"`；todo.txt: `todo add "title"` |
| **用户价值** | **高** — 最高频操作，每次少打 8 个字符 |
| **实现复杂度** | **低** — Click `@click.argument("title")` + 保留 `--title` 作 fallback，~5 行 |

### A2. `yait list` 加 `--sort` 和 `--limit`

| | |
|---|---|
| **现状** | 按文件名（即 ID）升序，无分页 |
| **建议** | `yait list --sort updated --limit 10`，支持 `id`/`updated`/`created` 排序 |
| **对比** | gh: `gh issue list --sort updated -L 10` |
| **用户价值** | **中** — issue 超过 20 个后变重要 |
| **实现复杂度** | **低** — 对 `list_issues()` 结果做 `sorted()` + `[:limit]`，~15 行 |

### A3. 输出加颜色

| | |
|---|---|
| **现状** | 纯文本表格，无颜色区分 |
| **建议** | open=绿色, closed=灰色, bug=红色, feature=蓝色, labels=cyan |
| **对比** | gh 全线彩色输出；taskwarrior 按优先级/类型着色 |
| **用户价值** | **高** — 视觉区分度从 0 到 1 的跃升，扫一眼就能定位 |
| **实现复杂度** | **低** — Click 原生 `click.style(text, fg="green")`，~20 行改动 |

### A4. `show` 输出加 comment 计数

| | |
|---|---|
| **现状** | `show` 只显示完整 body，不知道有几条 comment |
| **建议** | header 区域加 `Comments: 3`，通过计数 body 中 `**Comment**` 出现次数 |
| **对比** | gh: `gh issue view` 显示 "3 comments" |
| **用户价值** | **中** — 快速判断讨论活跃度 |
| **实现复杂度** | **低** — `body.count("**Comment**")`，~3 行 |

### A5. `list` 和 `search` 默认 status 不一致

| | |
|---|---|
| **现状** | `list` 默认 `--status open`，`search` 默认 `--status all` |
| **建议** | 统一：`search` 也默认 open，加 `--all` 快捷 flag 覆盖 |
| **对比** | gh: `list` 默认 open，`search` 也默认 open |
| **用户价值** | **中** — 减少认知负担，行为可预期 |
| **实现复杂度** | **低** — 改一个 default 值，~2 行 |

### A6. 高频命令短别名

| | |
|---|---|
| **现状** | 所有命令必须全拼 |
| **建议** | `ls` → list, `s` → show, `n` → new, `c` → close |
| **对比** | taskwarrior: `task ls`, `task add`；todo.txt 全用短命令 |
| **用户价值** | **中** — 重度用户效率提升 |
| **实现复杂度** | **低** — Click `@main.command(name="ls")` 或自定义 AliasedGroup，~10 行 |

### A7. `--json` 输出

| | |
|---|---|
| **现状** | 只有人类可读的表格输出 |
| **建议** | `yait list --json` 输出 JSON 数组，`yait show 1 --json` 输出单个 JSON |
| **对比** | gh: `gh issue list --json id,title,status`；jira-cli 支持 `--output json` |
| **用户价值** | **高** — 脚本集成和管道操作必备，`yait list --json \| jq '.[] \| .title'` |
| **实现复杂度** | **低** — `json.dumps(dataclasses.asdict(issue))`，~15 行 |

---

## B. 工作流缺失

### B1. `yait assign <id> <name>` 快速分配

| | |
|---|---|
| **现状** | 改 assignee 只能：(1) 创建时 `-a`，(2) `yait edit` 打开编辑器 |
| **建议** | `yait assign 1 bill`，一行命令搞定 |
| **用户价值** | **高** — 从 30 秒（开编辑器）变 2 秒 |
| **实现复杂度** | **低** — 新增 command，加载 → 修改 assignee → 保存 → commit，~15 行 |

### B2. 批量操作 `yait close 1 2 3`

| | |
|---|---|
| **现状** | close/reopen 只接受单个 ID |
| **建议** | `yait close 1 2 3` 或 `yait close --all --label done` |
| **用户价值** | **高** — sprint 结束批量清理必备 |
| **实现复杂度** | **低** — argument 改 `nargs=-1`，循环处理，~10 行 |

### B3. 优先级字段

| | |
|---|---|
| **现状** | 无优先级概念，无法区分紧急/重要 |
| **建议** | 新增 `priority` 字段 (p0/p1/p2/p3)，`yait new "Fix crash" -p p0`，`yait list --priority p0` |
| **用户价值** | **高** — issue tracker 核心功能 |
| **实现复杂度** | **中** — 需改 models、store、cli，加过滤逻辑，~40 行 |

### B4. `yait log <id>` 查看变更历史

| | |
|---|---|
| **现状** | 需要手动 `git log --follow .yait/issues/1.md` |
| **建议** | `yait log 1` 封装 git log，显示格式化的变更时间线 |
| **用户价值** | **中** — 审计和回溯场景 |
| **实现复杂度** | **低** — 封装 `git log --follow`，~15 行 |

### B5. `yait stats` 统计概览

| | |
|---|---|
| **现状** | 无法快速了解项目全貌 |
| **建议** | `yait stats` → `open: 12, closed: 8 | bugs: 5, features: 7 | unassigned: 3` |
| **用户价值** | **中** — 项目健康度一目了然 |
| **实现复杂度** | **低** — 基于 `list_issues()` 做聚合，~20 行 |

### B6. 导出 `yait export --format csv/json`

| | |
|---|---|
| **现状** | 无导出功能 |
| **建议** | `yait export --format csv > issues.csv`，`yait export --format json > issues.json` |
| **用户价值** | **中** — 迁移到其他工具，或生成报告给非技术人员 |
| **实现复杂度** | **低** — 已有 `list_issues()`，加 CSV/JSON 序列化，~25 行 |

### B7. 里程碑 / milestone

| | |
|---|---|
| **现状** | 无法按版本或迭代组织 issue |
| **建议** | `yait milestone create "v1.0"` + `yait new "title" --milestone v1.0` |
| **用户价值** | **中** — 项目规划场景 |
| **实现复杂度** | **高** — 需要新的数据结构、存储、关联逻辑 |

### B8. 关联 issue

| | |
|---|---|
| **现状** | issue 间无关联 |
| **建议** | `yait link 1 2 --type blocks`，在 frontmatter 加 `related` 字段 |
| **用户价值** | **低** — 本地 tracker 场景下关联需求不强 |
| **实现复杂度** | **中** |

### B9. 导入 `yait import`

| | |
|---|---|
| **现状** | 无法从 GitHub Issues/CSV 迁移 |
| **建议** | `yait import github owner/repo` 或 `yait import csv issues.csv` |
| **用户价值** | **中** — 降低迁移成本 |
| **实现复杂度** | **高** — 需处理多种数据源格式映射 |

---

## C. 开发者体验（DX）

### C1. 首次运行无引导

| | |
|---|---|
| **现状** | `yait`（无参数）只显示 Click 默认 help，新用户不知从何开始 |
| **建议** | 检测未初始化时显示 quick-start 引导：`Run 'yait init' to get started, then 'yait new "My first issue"'` |
| **用户价值** | **高** — 降低上手门槛 |
| **实现复杂度** | **低** — 自定义 `main()` 的 `invoke_without_command` 行为，~10 行 |

### C2. `edit` 命令只能改 title 和 body

| | |
|---|---|
| **现状** | `yait edit 1` 只打开编辑器改 title/body，改 type/assignee/labels 需手动 |
| **建议** | 支持 inline 修改：`yait edit 1 --type bug --assign bill`，无 option 时才开编辑器 |
| **用户价值** | **高** — 覆盖 80% 的编辑场景，不用开编辑器 |
| **实现复杂度** | **低** — 加 options，有任何 option 就直接修改不开编辑器，~25 行 |

### C3. `comment` 不支持 `$EDITOR`

| | |
|---|---|
| **现状** | `yait comment 1 -m "text"` 必须 `-m`，长评论体验差 |
| **建议** | `-m` 缺失时自动打开 `$EDITOR`，类似 `git commit` 行为 |
| **用户价值** | **中** — 写长评论/分析时很有用 |
| **实现复杂度** | **低** — Click 已有 `click.edit()`，~8 行 |

### C4. `.gitignore` 与 auto-commit 矛盾 (**设计缺陷**)

| | |
|---|---|
| **现状** | 项目 `.gitignore` 排除了 `.yait/`，但 `git_ops.py` 每次操作都 `git add .yait && git commit` |
| **问题** | 如果用户在已有项目中 `yait init`，`.yait/` 被 ignore，auto-commit 机制完全失效 |
| **建议** | `yait init` 时检测 `.gitignore` 是否排除 `.yait/`，提示用户选择：(1) 移除排除规则，(2) 独立 git repo |
| **用户价值** | **高** — 当前是静默失败，用户以为数据有 git 保护实际没有 |
| **实现复杂度** | **低** — init 时加检查逻辑，~10 行 |

### C5. 没有 `--version`

| | |
|---|---|
| **现状** | `yait --version` 不可用 |
| **建议** | `@click.version_option(version=__version__)` |
| **用户价值** | **低** — 标准 CLI 规范 |
| **实现复杂度** | **低** — 1 行 |

### C6. 无用户偏好配置

| | |
|---|---|
| **现状** | 默认 assignee、默认 type 每次都要手动指定 |
| **建议** | `.yait/config.yaml` 加 `defaults:` 段：`default_assignee: bill`，`default_type: bug` |
| **用户价值** | **中** — 个人使用时几乎总是同一个 assignee |
| **实现复杂度** | **中** — 需改 config 读写 + CLI 参数 fallback 逻辑 |

### C7. empty state 无引导

| | |
|---|---|
| **现状** | `yait list` 空项目只显示 "No issues found." |
| **建议** | 加提示：`No issues found. Create one with: yait new "My first issue"` |
| **用户价值** | **低** — 小改善 |
| **实现复杂度** | **低** — 改一行 echo，~1 行 |

---

## 投入产出比排序

### Tier 1: 必做（高价值 + 低复杂度）

| 优先级 | 改进 | 估计改动 | 核心理由 |
|:---:|------|:---:|---------|
| **1** | A1: `yait new "title"` positional arg | ~5 行 | 最高频操作，立竿见影 |
| **2** | A3: 输出加颜色 | ~20 行 | 视觉体验质变 |
| **3** | B1: `yait assign <id> <name>` | ~15 行 | 填补核心工作流缺口 |
| **4** | B2: 批量 `yait close 1 2 3` | ~10 行 | sprint 清理必备 |
| **5** | C2: `edit` 支持 inline 字段修改 | ~25 行 | 覆盖 80% 编辑场景 |

> **总计约 75 行代码，覆盖日常使用最痛的 5 个点。**

### Tier 2: 应该做（中价值 + 低复杂度）

| 优先级 | 改进 | 估计改动 |
|:---:|------|:---:|
| 6 | A7: `--json` 输出 | ~15 行 |
| 7 | C4: `.gitignore` 矛盾检测 | ~10 行 |
| 8 | B5: `yait stats` | ~20 行 |
| 9 | A5: search 默认 status 统一 | ~2 行 |
| 10 | C1: 首次运行引导 | ~10 行 |

### Tier 3: 可以做（中价值 + 中/高复杂度）

| 优先级 | 改进 | 估计改动 |
|:---:|------|:---:|
| 11 | B3: 优先级字段 | ~40 行 |
| 12 | C6: 用户偏好配置 | ~30 行 |
| 13 | B6: 导出 CSV/JSON | ~25 行 |
| 14 | B4: `yait log` 变更历史 | ~15 行 |

### 不建议现在做

| 改进 | 原因 |
|------|------|
| B7: 里程碑 | 复杂度高，本地 tracker 场景下需求不强 |
| B8: 关联 issue | 同上 |
| B9: 导入 | 需要处理多种数据源，投入大 |

---

## 附：设计缺陷提醒

**`.gitignore` 问题是唯一需要立即修复的 bug 级问题。** 项目自身的 `.gitignore` 排除了 `.yait/`（这对 yait 项目本身的开发是合理的），但如果用户在其他项目中使用 yait，auto-commit 机制是正常工作的。需要在 README 或 `yait init` 时明确说明这一行为，避免用户误解。
