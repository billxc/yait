# 评审结论

> 评审人: reviewer
> 日期: 2026-04-26
> 输入: analysis-features.md, analysis-bugs.md, analysis-dx.md
> 源码验证: 全部 5 个 .py 文件逐行复核

**评审原则**: 这是一个本地 markdown+git 工具，核心价值是简单。优先修 bug 和体验，不做 Jira。

---

## ✅ 采纳（按优先级排序）

### P0 — 必须修复

| # | 建议 | 来源 | 理由 | 复杂度 |
|---|------|------|------|--------|
| 1 | 表格列对齐偏移 | bugs #2 | 已验证：`#{i.id:<{id_w}}` 中 `#` 在 format spec 外，data 行比 header 多 1 字符，所有 `list`/`search` 输出歪。最常用命令的视觉 bug | ~5 行 |
| 2 | issues 目录非数字 .md 文件导致崩溃 | bugs #3 | 已验证：`int(p.stem)` 对非数字文件名抛 ValueError。注意：分析师说 `.DS_Store` 会触发是错的（glob 是 `*.md`），但 `README.md` 等会。一行 `if not p.stem.isdigit(): continue` 搞定 | ~1 行 |

### P1 — 重要改进

| # | 建议 | 来源 | 理由 | 复杂度 |
|---|------|------|------|--------|
| 3 | `yait new "title"` positional arg | dx A1 | 最高频操作，每次少打 `--title`。保留 `--title` 做兼容 | ~5 行 |
| 4 | 输出加颜色 | dx A3 | open=绿 closed=灰 bug=红，视觉区分从 0 到 1。Click 原生支持 | ~20 行 |
| 5 | `yait list --sort` | dx A2 / features | issue 超 20 个后必需。支持 `id`/`created`/`updated` 即可 | ~15 行 |
| 6 | 批量 `yait close 1 2 3` | dx B2 / features | argument 改 `nargs=-1`，循环处理 | ~10 行 |
| 7 | `yait assign <id> <name>` / `unassign` | bugs #12 / dx B1 | 改 assignee 不该需要开编辑器 | ~15 行 |
| 8 | `edit` 支持 inline 修改 | dx C2 | `yait edit 1 --type bug --assign bill`，有 option 就直接改，无 option 才开编辑器。覆盖 80% 编辑场景 | ~25 行 |
| 9 | 优先级字段 | features / dx B3 | bug tracker 核心功能。加 `priority` 字段 (p0/p1/p2/p3/none)，改 models+store+cli | ~40 行 |
| 10 | `search` 默认 status 改为 `open` | dx A5 | 已验证：`list` 默认 open，`search` 默认 all，行为不一致。改一个 default 值 | ~2 行 |
| 11 | config.yaml 损坏时友好报错 | bugs #4 | `yaml.safe_load()` 返回 None 时报 TypeError，用户看不懂。加 isinstance 检查 | ~5 行 |
| 12 | `yait init` 检测 .gitignore 排除 .yait/ | dx C4 | 注意：分析师说"设计缺陷"有点过了——yait 项目自身的 .gitignore 排除 .yait/ 是开发需要，用户项目里正常。但 init 时检测并提示是好的防御 | ~10 行 |

### P2 — Nice to have

| # | 建议 | 来源 | 理由 | 复杂度 |
|---|------|------|------|--------|
| 13 | `--json` 输出 | dx A7 | 脚本集成必备，`dataclasses.asdict` + `json.dumps` | ~15 行 |
| 14 | close reason (completed/not_planned) | features | 简单字段扩展 | ~10 行 |
| 15 | `yait stats` | dx B5 / features | 基于 `list_issues()` 做聚合，一目了然 | ~20 行 |
| 16 | `comment` 支持 `$EDITOR` | dx C3 | `-m` 缺失时打开编辑器，`click.edit()` 现成 | ~8 行 |
| 17 | `show` 加 comment 计数 | dx A4 | `body.count("**Comment**")`，3 行改动 | ~3 行 |
| 18 | 命令短别名 ls/s/n/c | dx A6 | 重度用户效率 | ~10 行 |
| 19 | `--version` | dx C5 | `@click.version_option`，一行 | ~1 行 |
| 20 | empty state 引导 | dx C7 | "No issues found" → 加创建提示 | ~1 行 |
| 21 | 首次运行引导 | dx C1 | 未初始化时提示 `yait init` | ~10 行 |
| 22 | search 高亮匹配 | bugs #14 | `click.style()` 高亮 | ~10 行 |
| 23 | SystemExit 改 click.ClickException | bugs #15 | 更 idiomatic，测试更友好 | ~3 行 |
| 24 | `list_cmd` 直接传 label/assignee 给 store | bugs #7 | 已验证：功能正确但代码冗余 | ~2 行 |
| 25 | body split 加 maxsplit=2 | bugs #6 | 注意：验证发现当前 re-join 写法实际能正确还原 body，不是 bug。但 `split("---\n", 2)` 更清晰 | ~1 行 |
| 26 | assignee None 不转空串 | bugs #9 | YAML 美观，`null` 比 `''` 语义清晰 | ~1 行 |
| 27 | git_commit 统一用 git_run | bugs #10 | 代码一致性 | ~3 行 |
| 28 | due date 字段 | features | 简单字段添加 | ~10 行 |
| 29 | `yait export --format csv/json` | features / dx B6 | 已有 `list_issues()`，加序列化 | ~25 行 |
| 30 | `yait log <id>` 变更历史 | dx B4 | 封装 `git log --follow` | ~15 行 |

---

## ⚠️ 延后

| # | 建议 | 来源 | 理由 |
|---|------|------|------|
| 1 | next_id() 竞态条件 | bugs #1 | 分析师标"高"但对本地 CLI 而言概率趋近于零——你得两个终端同一毫秒 `yait new`。且 `fcntl.flock` 是 Unix-only，要做得做跨平台。等真有用户反馈再说 |
| 2 | Issue model __post_init__ 校验 | bugs #8 | CLI 层已有 `click.Choice` 校验，store API 只有 CLI 调用。加了也没坏处但现在不急 |
| 3 | edit 命令 title: 前缀解析歧义 | bugs #5 | title 以 "title:" 开头的概率极低。要改的话改整个 edit 模板格式，和 #8 (edit inline) 一起做 |
| 4 | Milestone | features / dx B7 | 复杂度高，本地场景用 label 模拟即可（如 `v1.0` label）。等项目长到真需要再加 |
| 5 | Issue 交叉引用 | features | 需要解析+索引，投入大，本地工具场景弱 |
| 6 | Comment 独立存储 | features | 当前 body 追加方式能用，重构需改数据格式+迁移逻辑。等 comment 量真成问题再做 |
| 7 | Issue templates | features | `.yait/templates/` 好主意但不急 |
| 8 | Multiple assignees | features | 本地工具通常单人使用 |
| 9 | `yait delete` | features | `close` 够用，真要删 `rm .yait/issues/N.md && git commit` |
| 10 | 用户偏好配置 (defaults) | dx C6 | 好主意，但需改 config 读写+参数 fallback，等核心功能稳定后做 |
| 11 | 关联 issue (link/blocks) | dx B8 | 本地 tracker 场景关联需求弱，DX 分析师自己也标了低价值 |

---

## ❌ 拒绝

| # | 建议 | 来源 | 理由 |
|---|------|------|------|
| 1 | `_now()` 统一存 UTC | bugs #11 | **分析有误**。本地工具存本地时区是正确选择——用户想看到自己的时间，不想心算 UTC+8。多机器场景下 git 已有自己的时间戳 |
| 2 | Activity log / changelog | features | **过度设计**。`git log --follow .yait/issues/N.md` 就是 changelog，不需要在 issue 里重复记录。P2 的 `yait log` 命令封装 git log 即可 |
| 3 | Custom fields | features | **Jira 化**。本地工具固定 schema 是特性不是缺陷，加了 custom fields 就要加 UI、验证、迁移 |
| 4 | Pinned issues | features | 过度设计。`--sort priority` 加上 P0 标记已经够用 |
| 5 | `yait import` | features / dx B9 | 投入产出比太低。多种数据源格式映射复杂，用户可以写脚本调用 `yait new` |
| 6 | Web UI / REST API / Notifications / RBAC / Board / Webhooks / GraphQL / Lock / Reactions / Saved searches | features §3 | 分析师自己已标"不需要"，同意 |

---

## 执行建议

**第一批（约 60 行改动，修 bug + 最痛 UX）:**
- P0 #1-2: 表格对齐 + 非数字文件崩溃
- P1 #3: positional title
- P1 #10: search 默认 status
- P1 #11: config 损坏友好报错

**第二批（约 80 行，核心体验提升）:**
- P1 #4: 颜色输出
- P1 #6: 批量操作
- P1 #7: assign/unassign
- P1 #8: edit inline

**第三批（约 60 行，功能补全）:**
- P1 #5: sort
- P1 #9: 优先级字段
- P1 #12: gitignore 检测

> 三批总计约 200 行代码，覆盖 2 个 bug、10 个体验改进、1 个核心功能。
