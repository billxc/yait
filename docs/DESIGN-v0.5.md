# YAIT v0.5 设计文档

**版本**: v0.5
**日期**: 2026-04-26
**作者**: yait-pm-v2
**状态**: Implemented

---

## 1. 现状总结

### 1.1 当前版本功能清单 (v0.3.1)

| 分类 | 命令 | 说明 |
|------|------|------|
| **核心 CRUD** | `new`, `show`, `close`, `reopen`, `delete` | 创建、查看、关闭、重开、删除 |
| **编辑** | `edit`, `comment`, `label add/remove`, `assign`, `unassign` | 内联/编辑器编辑、评论、标签、分配 |
| **查询** | `list`, `search`, `stats`, `log` | 列表、搜索、统计、变更历史 |
| **数据** | `export`, `import` | JSON/CSV 导出、JSON 导入 |
| **初始化** | `init` | 初始化 .yait 目录 |

**数据模型字段**: id, title, status, type, priority, labels, assignee, milestone, created_at, updated_at, body

**输出格式**: 彩色表格、JSON

**过滤**: status, type, priority, label, assignee, milestone

**排序**: id, created, updated

### 1.2 压力测试结论

v0.3.1 通过了 5 组 AI 压力测试（1000+ 命令、149 issues）：

- **核心稳定**: YAML frontmatter 解析在各种特殊字符（CJK、RTL、emoji、YAML 注入）下表现健壮
- **已修复 Bug**: 空白标题校验 (BUG-001)、负数 ID 异常处理 (BUG-002)、`---` 参数解析 (BUG-003)、priority 选项缺失 (BUG-004)
- **边界测试全通过**: 24 个边界场景（超长文本、多语言、10+ labels、批量操作等）均无问题

### 1.3 已知局限

1. **Milestone 只是字段** — 没有独立的 milestone 管理命令，无法列出、创建、统计 milestone
2. **批量操作有限** — 只有 close/reopen 支持多 ID，label/assign/priority 不支持批量
3. **搜索功能基础** — 仅支持全文子串匹配，不支持多字段组合搜索
4. **统计单薄** — 只有 type/label 分布，缺少 milestone/assignee/priority/趋势分析
5. **无配置自定义** — 无法设置默认 type、默认 priority 等
6. **无 issue 关联** — 不支持 blocks/depends-on/relates-to 关系
7. **性能未优化** — 每次操作全量扫描目录，1000+ issues 时可能变慢

---

## 2. v0.5 目标

### 2.1 定位

保持 **"本地个人工具"** 定位不变。v0.5 的核心目标是：

> 从"能用"到"好用"——补齐日常工作流中的缺失环节，让 yait 成为个人项目管理的完整方案。

### 2.2 范围

| 优先级 | 功能 | 目标 |
|--------|------|------|
| **P0** | Milestone 管理 | 完整的 milestone 生命周期管理 |
| **P0** | 批量编辑 | label/assign/priority/milestone 的批量操作 |
| **P1** | 增强统计 | 按 milestone/assignee/priority 维度分析 |
| **P1** | 高级搜索 | 多字段组合过滤、正则搜索 |
| **P1** | Issue 模板 | 预设 issue 模板，快速创建 |
| **P1** | 设计文档关联 | 将设计文档关联到 issue，支持托管文档和外部引用 |
| **P2** | Issue 关联 | blocks/relates-to 关系 |
| **P2** | 配置文件增强 | 用户自定义默认值 |
| **P2** | 输出格式化改进 | 长标题截断、紧凑模式 |

### 2.3 不做

| 功能 | 原因 |
|------|------|
| Web UI | 偏离本地工具定位 |
| 多用户/权限 | 个人工具不需要 |
| GitHub/GitLab 同步 | 外部依赖，维护成本高 |
| Webhook/自动化 | 过度工程化 |
| Shell 自动补全 | 收益低，用户可以通过 Click 内置支持自行配置 |

---

## 3. 功能设计

### 3.1 Milestone 管理 (P0)

#### 3.1.1 功能描述

将 milestone 从"issue 上的一个字段"提升为一等公民，支持独立的 milestone 管理命令组。

#### 3.1.2 数据模型

在 `.yait/config.yaml` 中新增 `milestones` 部分：

```yaml
version: 1
next_id: 33
milestones:
  v1.0:
    status: open        # open | closed
    description: "第一个正式发布版本"
    due_date: "2026-06-01"
    created_at: "2026-04-26T12:00:00+08:00"
  v0.5:
    status: closed
    description: "功能增强版本"
    due_date: "2026-05-15"
    created_at: "2026-04-20T10:00:00+08:00"
```

Issue 的 `milestone` 字段保持为字符串引用。

#### 3.1.3 CLI 命令

```bash
# 创建 milestone
yait milestone create v1.0 --description "First release" --due 2026-06-01

# 列出所有 milestone
yait milestone list
yait milestone list --status open       # 仅 open
yait milestone list --json

# 输出示例:
# MILESTONE  STATUS  DUE         OPEN  CLOSED  PROGRESS
# v1.0       open    2026-06-01  12    5       29%
# v0.5       closed  2026-05-15  0     17      100%

# 查看 milestone 详情
yait milestone show v1.0
yait milestone show v1.0 --json

# 输出示例:
# Milestone: v1.0
# Status: open
# Description: First release
# Due: 2026-06-01
# Issues: 17 total (12 open, 5 closed, 29% done)
#
# Open issues:
#   #3  bug   Fix login crash     p0  alice
#   #7  feat  Add dark mode       p1  bob
#   ...

# 关闭/重开 milestone
yait milestone close v1.0
yait milestone reopen v1.0

# 编辑 milestone
yait milestone edit v1.0 --description "Updated" --due 2026-07-01

# 删除 milestone（仅当无 issue 引用时）
yait milestone delete v1.0
```

#### 3.1.4 实现方案

- **store.py**: 新增 `Milestone` dataclass，`save_milestone()`, `load_milestones()`, `delete_milestone()` 函数。Milestone 数据存储在 `config.yaml` 中。
- **cli.py**: 新增 `milestone` 命令组（类似 `label`），子命令 `create/list/show/close/reopen/edit/delete`
- **stats 增强**: `yait milestone show` 自动统计关联 issue 数量和完成度
- **向后兼容**: 旧 config.yaml 无 `milestones` 字段时默认为空 dict

#### 3.1.5 边界情况

- 创建重名 milestone: 报错 "Milestone 'v1.0' already exists"
- 删除被 issue 引用的 milestone: 报错 "Cannot delete milestone 'v1.0': 12 issues still reference it. Use --force to remove references."
- `--force` 删除: 移除 milestone 定义，同时将所有引用该 milestone 的 issue 的 milestone 字段置为 null
- Issue 引用不存在的 milestone: 允许（宽松模式，不强制引用完整性）
- Due date 格式: YYYY-MM-DD，可选，无 due date 显示 "—"

---

### 3.2 批量编辑 (P0)

#### 3.2.1 功能描述

扩展批量操作能力，支持对多个 issue 同时修改 label、assignee、priority、milestone。

#### 3.2.2 CLI 命令

使用 `bulk` 子命令组：

```bash
# 批量添加标签
yait bulk label add urgent 1 2 3 4 5
yait bulk label remove urgent 1 2 3

# 批量分配
yait bulk assign alice 1 2 3
yait bulk unassign 1 2 3

# 批量设置优先级
yait bulk priority p0 1 2 3

# 批量设置 milestone
yait bulk milestone v1.0 1 2 3

# 批量修改类型
yait bulk type bug 1 2 3

# 基于过滤条件的批量操作（高级用法）
yait bulk label add release-blocker --filter-priority p0 --filter-status open
yait bulk milestone v2.0 --filter-label deferred
yait bulk assign alice --filter-milestone v1.0 --filter-status open
```

#### 3.2.3 实现方案

- **cli.py**: 新增 `bulk` 命令组，每个子命令接受 `value + IDs` 或 `value + --filter-*` 参数
- 基于 ID 列表: 逐个加载、修改、保存、commit
- 基于 filter: 调用 `list_issues()` 获取匹配 issue，逐个修改
- 每个 issue 独立 commit（保持 git history 清晰）
- 输出汇总: `Updated 5 issues. Failed: 0.`

#### 3.2.4 边界情况

- ID 不存在: 跳过并警告，继续处理其余
- 重复 label add: 跳过（已有该 label）
- filter 无匹配: 输出 "No issues match the filter criteria."
- filter + ID 同时指定: 报错 "Cannot use both issue IDs and --filter options."

---

### 3.3 增强统计 (P1)

#### 3.3.1 功能描述

扩展 `yait stats` 命令，增加多维度分析。

#### 3.3.2 CLI 命令

```bash
# 基础统计（增强版）
yait stats

# 输出示例:
# Issues: 32 total (18 open, 14 closed)
#
# By type:     bug=12, feature=8, enhancement=6, misc=6
# By priority: p0=3, p1=8, p2=15, p3=4, none=2
# By milestone:
#   v1.0    12 open / 5 closed  (29%)
#   v0.5    0 open / 17 closed  (100%)
#   (none)  6 open / 4 closed
# By assignee:
#   alice   8 open / 3 closed
#   bob     6 open / 5 closed
#   (none)  4 open / 6 closed

# JSON 输出
yait stats --json

# 按指定维度分析
yait stats --by milestone
yait stats --by assignee
yait stats --by priority
```

#### 3.3.3 实现方案

- 扩展 `stats` 命令，默认输出增加 priority/milestone/assignee 分布
- `--by` 选项聚焦单个维度，显示更详细的分解
- `--json` 输出结构化数据，供外部工具消费
- 复用 `list_issues(status=None)` 全量加载

---

### 3.4 高级搜索 (P1)

#### 3.4.1 功能描述

增强 `yait search` 命令，支持多字段组合过滤和正则搜索。

#### 3.4.2 CLI 命令

```bash
# 现有功能保持不变
yait search "login"
yait search "crash" --status all

# 新增：多字段组合过滤
yait search "login" --label auth --priority p0 --assignee alice
yait search "bug" --milestone v1.0 --status open

# 新增：正则搜索
yait search --regex "crash|oom|kill" --status all

# 新增：仅搜索标题
yait search "login" --title-only

# 新增：搜索结果计数
yait search "bug" --count
# 输出: 12 issues match "bug"
```

#### 3.4.3 实现方案

- 扩展 `search` 命令的 Click options，添加 `--label`, `--priority`, `--assignee`, `--milestone` 过滤
- 传递到 `list_issues()` 做预过滤，再在结果上做文本匹配
- `--regex`: 用 `re.search()` 替代 `in` 操作符
- `--title-only`: 仅匹配 `issue.title`
- `--count`: 输出匹配数量而非表格

---

### 3.5 Issue 模板 (P1)

#### 3.5.1 功能描述

支持预设 issue 模板，快速创建格式统一的 issue。

#### 3.5.2 数据模型

模板存储在 `.yait/templates/` 目录：

```
.yait/
├── config.yaml
├── issues/
└── templates/
    ├── bug.md
    └── feature.md
```

模板文件格式（YAML frontmatter + body template）：

```markdown
---
name: bug
type: bug
priority: p1
labels:
  - needs-triage
---

## Description

[Describe the bug]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]

## Expected Behavior

[What should happen]

## Actual Behavior

[What actually happens]
```

#### 3.5.3 CLI 命令

```bash
# 创建模板
yait template create bug
# 打开 $EDITOR 编辑模板内容

# 从现有模板创建 issue
yait new "Login crash on iOS" --template bug
# 自动填充 type=bug, priority=p1, labels=[needs-triage], body=模板内容

# 列出模板
yait template list

# 删除模板
yait template delete bug
```

#### 3.5.4 实现方案

- **store.py**: `save_template()`, `load_template()`, `list_templates()`, `delete_template()` — 类似 issue 的 file I/O
- **cli.py**: `template` 命令组 + `new` 命令增加 `--template` 选项
- `--template` 加载模板后，CLI 参数覆盖模板中的值（CLI 参数优先）

#### 3.5.5 边界情况

- 模板不存在: 报错 "Template 'xxx' not found. Available: bug, feature"
- `--template` + `--type` 同时指定: CLI 参数覆盖模板值
- 模板 body 中的占位符: v0.5 不做变量替换，保持纯文本

---

### 3.6 Issue 关联 (P2)

#### 3.6.1 功能描述

支持 issue 之间的关联关系：blocks、depends-on、relates-to。

#### 3.6.2 数据模型

在 issue frontmatter 中新增 `links` 字段：

```yaml
---
id: 3
title: "Fix login"
links:
  - type: blocks
    target: 5
  - type: relates-to
    target: 7
---
```

#### 3.6.3 CLI 命令

```bash
# 添加关联
yait link 3 blocks 5          # issue #3 blocks issue #5
yait link 3 relates-to 7      # issue #3 relates to #7
yait link 3 depends-on 1      # issue #3 depends on #1

# 删除关联
yait unlink 3 5

# 查看关联（在 show 输出中自动显示）
yait show 3
# ...
# Links:
#   blocks #5 (open): Deploy to staging
#   relates-to #7 (closed): Update docs
```

#### 3.6.4 实现方案

- **models.py**: Issue 增加 `links: list[dict]` 字段，每个 dict 有 `type` 和 `target` 键
- **store.py**: save/load 处理 links 字段，向后兼容（缺失时默认 `[]`）
- **cli.py**: `link`/`unlink` 命令，`show` 输出增加 Links 部分
- 关联是**双向存储**的——`link 3 blocks 5` 会同时在 #3 添加 `blocks: 5` 和在 #5 添加 `blocked-by: 3`

#### 3.6.5 边界情况

- 自引用: 禁止 `yait link 3 blocks 3`
- 重复关联: 跳过并提示 "Link already exists"
- 目标不存在: 报错 "Issue #99 not found"
- 删除被关联 issue: 保持关联（dangling reference），`show` 时标注 "(deleted)"

---

### 3.7 配置文件增强 (P2)

#### 3.7.1 功能描述

扩展 `.yait/config.yaml`，支持用户自定义默认值和行为。

#### 3.7.2 配置格式

```yaml
version: 1
next_id: 33
milestones: { ... }

# 新增配置
defaults:
  type: bug              # 默认 issue type（default: misc）
  priority: p2           # 默认 priority（default: none）
  assignee: alice        # 默认 assignee（default: null）
  labels: []             # 默认 labels

display:
  max_title_width: 50    # list 表格中标题最大宽度（截断显示）
  date_format: short     # short=仅日期, full=含时间
```

#### 3.7.3 CLI 命令

```bash
# 查看配置
yait config

# 设置单个配置
yait config set defaults.type bug
yait config set display.max_title_width 60

# 重置为默认
yait config reset defaults.type
```

#### 3.7.4 实现方案

- 扩展 `_read_config()` / `_write_config()` 处理新字段
- `new` 命令读取 `defaults` 作为未指定参数的后备值
- `_print_issue_table()` 读取 `display.max_title_width` 截断标题
- 向后兼容: 缺失的配置项使用硬编码默认值

---

### 3.8 输出格式化改进 (P2)

#### 3.8.1 功能描述

改善 `list` 和 `search` 的表格输出，处理长标题和窄终端。

#### 3.8.2 改进项

1. **标题截断**: 超过 `max_title_width`（默认 50）时截断并追加 `...`
2. **紧凑模式**: `yait list --compact` 只显示 ID + Status + Title
3. **宽模式**: `yait list --wide` 显示所有字段（含 priority, milestone, dates）
4. **自适应宽度**: 检测终端宽度 (`os.get_terminal_size()`)，自动选择紧凑/标准/宽模式

#### 3.8.3 实现方案

- `_print_issue_table()` 增加 `mode` 参数 (compact/normal/wide)
- `list` 和 `search` 命令增加 `--compact` / `--wide` 选项
- 自适应逻辑: 终端 < 80 列用 compact，80-120 用 normal，>120 用 wide

---

### 3.9 设计文档关联 (P1)

#### 3.9.1 功能描述

支持将设计文档（PRD、技术方案、测试计划等）关联到 issue，形成"先设计后开发"的项目管理闭环。

**核心场景**:
- PM 写完 PRD 后创建对应的 issue，并将 PRD 关联上去
- 开发者在 issue 上追加技术方案文档
- 一个 PRD 拆分成多个 task issue，每个 issue 都关联同一份 PRD（多对多）
- 一个 issue 同时关联 PRD + 技术方案 + 测试计划

#### 3.9.2 存储模型：混合模式

支持两种文档来源：

1. **托管文档** — 存储在 `.yait/docs/<slug>.md`，由 yait 创建和管理，自动 git commit
2. **外部引用** — 引用项目中已有的文件路径（如 `docs/architecture.md`），yait 只存储路径

**目录结构**:

```
.yait/
├── config.yaml
├── issues/
│   ├── 1.md
│   └── 2.md
└── docs/
    ├── auth-prd.md
    └── auth-tech-spec.md
```

**消歧规则**: Issue 的 `docs` 字段是字符串列表。根据是否含 `/` 区分：
- **不含 `/`** → 托管文档 slug → 指向 `.yait/docs/<slug>.md`
- **含 `/`** → 外部路径 → 相对于项目根目录

```yaml
# Issue frontmatter 示例
docs:
  - auth-prd                   # → .yait/docs/auth-prd.md（托管）
  - docs/architecture.md       # → <project-root>/docs/architecture.md（外部）
```

#### 3.9.3 数据模型

**Issue 新增字段** (`models.py`):

```python
@dataclass
class Issue:
    # ... 现有字段 ...
    docs: list[str] = field(default_factory=list)   # 新增
```

向后兼容：旧 issue 无 `docs` 字段时默认为 `[]`。

**Doc dataclass** (`models.py`):

```python
@dataclass
class Doc:
    slug: str           # 文件名标识，如 "auth-prd"
    title: str          # 文档标题
    created_at: str = ""
    updated_at: str = ""
    body: str = ""

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "body": self.body,
        }
```

**托管文档文件格式** (`.yait/docs/auth-prd.md`):

```markdown
---
slug: auth-prd
title: "认证系统 PRD"
created_at: "2026-04-26T12:00:00+08:00"
updated_at: "2026-04-26T14:00:00+08:00"
---

## 概述

认证系统需要支持邮箱注册、OAuth2.0、SSO...

## 用户故事

1. 作为用户，我希望...
```

#### 3.9.4 Store 层 (`store.py`)

新增函数：

```python
def _docs_dir(root: Path) -> Path:
    return _yait_root(root) / "docs"

def save_doc(root: Path, doc: Doc) -> None:
    """保存托管文档到 .yait/docs/<slug>.md"""

def load_doc(root: Path, slug: str) -> Doc:
    """加载托管文档，slug 不含 /"""

def list_docs(root: Path) -> list[Doc]:
    """列出所有托管文档"""

def delete_doc(root: Path, slug: str) -> None:
    """删除托管文档"""
```

`init_store()` 扩展：创建 `.yait/docs/` 目录。

`save_issue()` / `load_issue()` 扩展：处理 `docs` 字段的序列化/反序列化。

#### 3.9.5 CLI 命令

**`yait doc` 命令组**:

```bash
# ── 创建托管文档 ──────────────────────────────────
# 方式 1: 打开 $EDITOR 编写
yait doc create auth-prd --title "认证系统 PRD"

# 方式 2: 内联内容
yait doc create auth-prd --title "认证系统 PRD" -b "## 概述\n\n..."

# 方式 3: 从文件导入
yait doc create auth-prd --title "认证系统 PRD" --body-file draft.md

# ── 查看文档 ──────────────────────────────────────
yait doc show auth-prd
# 输出:
# auth-prd: 认证系统 PRD
# Created: 2026-04-26T12:00:00+08:00
# Updated: 2026-04-26T14:00:00+08:00
# Linked issues: #1 (open), #3 (open), #7 (closed)
#
# ## 概述
# 认证系统需要支持...

yait doc show auth-prd --json

# ── 列出所有文档 ──────────────────────────────────
yait doc list
# 输出:
# SLUG            TITLE                UPDATED              ISSUES
# auth-prd        认证系统 PRD          2026-04-26 14:00     #1, #3, #7
# auth-tech-spec  认证技术方案          2026-04-26 16:00     #1

yait doc list --json

# ── 编辑文档 ──────────────────────────────────────
yait doc edit auth-prd                    # 打开 $EDITOR
yait doc edit auth-prd -b "新内容"        # 替换 body
yait doc edit auth-prd --title "新标题"   # 修改标题

# ── 删除文档 ──────────────────────────────────────
yait doc delete auth-prd
# 输出: Warning: auth-prd is linked to 3 issues (#1, #3, #7).
#        Delete will remove the document but NOT the references.
#        Use 'yait doc unlink' to clean up first.
# Are you sure? [y/N]

yait doc delete auth-prd -f               # 跳过确认

# ── 关联 / 取消关联 ──────────────────────────────
# 关联托管文档
yait doc link 1 auth-prd
# 输出: Linked doc 'auth-prd' to issue #1

# 关联外部文件
yait doc link 1 docs/architecture.md
# 输出: Linked doc 'docs/architecture.md' to issue #1

# 取消关联
yait doc unlink 1 auth-prd
# 输出: Unlinked doc 'auth-prd' from issue #1

# 一次关联多个 issue（一个 PRD 拆成多个 task）
yait doc link 1 2 3 auth-prd
# 输出: Linked doc 'auth-prd' to issues #1, #2, #3
```

#### 3.9.6 与现有命令的整合

**`yait show <id>` 增强**:

```
#1  [open]  实现用户认证
Type: feature
Priority: p0
Labels: auth, backend
Milestone: v1.0
Assignee: alice
Docs:
  - auth-prd (认证系统 PRD)
  - docs/architecture.md
Created: 2026-04-26T12:00:00+08:00
Updated: 2026-04-26T14:00:00+08:00
Comments: 3

...
```

JSON 输出中 `docs` 字段直接输出字符串列表。

**`yait list` 新增过滤**:

```bash
yait list --has-doc               # 只显示有关联文档的 issue
yait list --no-doc                # 只显示无文档的 issue
yait list --doc auth-prd          # 只显示关联了指定文档的 issue
```

**`yait search` 增强**:

搜索文本时同时匹配托管文档的标题。如果 issue 关联了 `auth-prd`（标题为"认证系统 PRD"），搜索"认证"时该 issue 也会命中。

#### 3.9.7 实现方案

**store.py 变更**:
- `save_doc()` / `load_doc()`: 复用 issue 的 YAML frontmatter 模式（`---` 分隔符 + `yaml.dump/safe_load`）
- `list_docs()`: 扫描 `.yait/docs/*.md`，跳过非 `.md` 文件
- `init_store()`: 增加 `_docs_dir(root).mkdir(parents=True, exist_ok=True)`
- `save_issue()`: frontmatter dict 增加 `"docs": issue.docs`
- `load_issue()`: `fm.get("docs") or []`

**cli.py 变更**:
- 新增 `doc` Click group，子命令 `create`/`show`/`list`/`edit`/`delete`/`link`/`unlink`
- `show` 命令增加 Docs 输出部分
- `list_cmd` 增加 `--has-doc`/`--no-doc`/`--doc` 过滤选项
- `search` 命令增加托管文档标题匹配逻辑

**git_ops.py**: 无变更。`git_commit()` 已自动 stage `.yait/` 目录（包含新增的 `docs/` 子目录）。

**link/unlink 多 issue 支持**:
`yait doc link 1 2 3 auth-prd` — 最后一个参数为 doc 标识，前面的为 issue ID。通过检测最后一个参数是否为整数来消歧：如果非整数则作为 doc slug/path。

#### 3.9.8 边界情况

| 场景 | 处理方式 |
|------|----------|
| slug 含 `/` | 报错: "Doc slug cannot contain '/'. Use a simple name like 'auth-prd'." |
| slug 重复创建 | 报错: "Doc 'auth-prd' already exists." |
| link 不存在的托管文档 | 允许（宽松模式，不强制引用完整性）。`show` 时标注 "(not found)" |
| link 不存在的外部文件 | 允许，`show` 时标注 "(file not found)" |
| 重复 link | 跳过并提示: "Issue #1 already linked to 'auth-prd'." |
| unlink 不存在的关联 | 提示: "Issue #1 is not linked to 'auth-prd'." |
| delete 有关联的文档 | 警告并需确认（或 `-f`），删除文档文件但不自动清理 issue 上的引用 |
| slug 合法字符 | 允许字母、数字、连字符、下划线: `[a-zA-Z0-9_-]+` |
| 旧 issue 无 `docs` 字段 | 默认 `[]`，无需迁移 |
| `yait doc show` 外部引用 | 报错: "'docs/arch.md' is an external reference, not a managed doc. View it directly." |

#### 3.9.9 使用场景示例

**场景 1: PM 写 PRD 并创建 issue**

```bash
# PM 创建 PRD
yait doc create auth-prd --title "认证系统 PRD" --body-file ~/drafts/auth-prd.md

# 从 PRD 拆分出 task issue
yait new "实现邮箱注册" -t feature --milestone v1.0 -a alice
yait new "实现 OAuth2.0" -t feature --milestone v1.0 -a bob
yait new "实现 SSO" -t feature --milestone v1.0 -a charlie

# 批量关联 PRD 到所有 task
yait doc link 1 2 3 auth-prd
```

**场景 2: 开发者追加技术方案**

```bash
# 开发者写技术方案
yait doc create auth-tech-spec --title "认证技术方案"
# (打开 $EDITOR 编写)

# 关联到对应 issue
yait doc link 1 auth-tech-spec

# 查看 issue 时可以看到所有关联文档
yait show 1
```

**场景 3: 关联项目中已有的文档**

```bash
# 项目 docs/ 下已有架构文档
yait doc link 1 docs/architecture.md
yait doc link 1 docs/api-spec.yaml
```

**场景 4: 查看文档关联的所有 issue**

```bash
yait doc show auth-prd
# 输出中包含 "Linked issues: #1 (open), #2 (open), #3 (open)"

# 或通过 list 过滤
yait list --doc auth-prd
```

---

## 4. 非功能需求

### 4.1 性能目标

| 场景 | 目标 | 当前 |
|------|------|------|
| `yait list` (100 issues) | < 200ms | ~150ms |
| `yait list` (500 issues) | < 500ms | ~400ms |
| `yait list` (1000 issues) | < 1s | 未测 |
| `yait search` (1000 issues) | < 1.5s | 未测 |
| `yait new` | < 300ms | ~200ms |
| `yait stats` (1000 issues) | < 1s | 未测 |

**优化策略**: v0.5 不做索引优化，仅在性能不达标时考虑。个人工具场景 <500 issues 是常态。

### 4.2 错误处理标准

1. **所有用户可见错误使用 `click.ClickException`**，不泄露 Python traceback
2. **批量操作**: 单个失败不中断整体，最后汇报成功/失败/跳过数量
3. **文件损坏**: 遇到无法解析的 issue 文件时 warn 并跳过，不 crash
4. **向后兼容**: 新字段缺失时始终有合理默认值

### 4.3 测试要求

- **覆盖率**: 保持 ≥ 90% 行覆盖率
- **新功能**: 每个新命令/子命令至少 3 个测试（正常、边界、错误）
- **回归测试**: 现有 105 个测试全部保持通过
- **目标总测试数**: ≥ 150

### 4.4 兼容性

- **Python**: 3.10+
- **OS**: macOS, Linux (Windows 暂不考虑, fcntl 依赖)
- **旧数据**: v0.3.x 的 `.yait/` 数据无需迁移即可被 v0.5 正确读取

---

## 5. 实现计划

### 5.1 任务拆分

| # | 任务 | 优先级 | 依赖 | 状态 |
|---|------|--------|------|------|
| T1 | Milestone dataclass + store 层 CRUD | P0 | — | ✅ Done |
| T2 | Milestone CLI 命令组 (create/list/show/close/reopen/edit/delete) | P0 | T1 | ✅ Done |
| T3 | `yait stats` 增加 milestone/assignee/priority 分布 | P1 | T1 | ✅ Done |
| T4 | `bulk` 命令组 (label/assign/priority/milestone/type) | P0 | — | ✅ Done |
| T5 | `bulk` 基于 filter 的批量操作 | P0 | T4 | ✅ Done |
| T6 | `search` 增加多字段过滤 + regex + title-only + count | P1 | — | ✅ Done |
| T7 | Template 数据模型 + store 层 | P1 | — | ✅ Done |
| T8 | Template CLI (create/list/delete) + `new --template` | P1 | T7 | ✅ Done |
| T9 | Issue links 数据模型 + store 层 | P2 | — | ✅ Done |
| T10 | `link`/`unlink` 命令 + show 输出 | P2 | T9 | ✅ Done |
| T11 | Doc dataclass + store 层 CRUD (.yait/docs/) | P1 | — | ✅ Done |
| T12 | `doc` CLI 命令组 (create/show/list/edit/delete/link/unlink) | P1 | T11 | ✅ Done |
| T13 | `show`/`list`/`search` 整合文档关联显示和过滤 | P1 | T12 | ✅ Done |
| T14 | Config 增强 (defaults + display) | P2 | — | ✅ Done |
| T15 | `config` CLI 命令 | P2 | T14 | ✅ Done |
| T16 | 输出格式化改进 (truncation, compact/wide) | P2 | T14 | ✅ Done |
| T17 | 测试套件更新 (所有新功能) | 贯穿 | 各任务 | ✅ Done (382 tests) |
| T18 | README + PRD 文档更新 | 收尾 | 全部 | ✅ Done |
| T19 | 并发锁 — 全局 lockfile (.yait/yait.lock) + PID/时间戳 stale 检测 | P1 | — | ✅ Done (v0.6.0) |

**Size 说明**: S=半天, M=1天, L=2天

### 5.2 推荐实施顺序

```
Phase 1 (P0 — Core):
  T1 → T2 → T4 → T5
  ↳ Milestone 管理 + 批量编辑，解决压力测试中最高频的需求

Phase 2 (P1 — Enhance):
  T3, T6 可并行
  T7 → T8
  T11 → T12 → T13
  ↳ 统计增强 + 高级搜索 + 模板 + 设计文档关联

Phase 3 (P2 — Polish):
  T9 → T10
  T14 → T15 → T16
  ↳ Issue 关联 + 配置 + 输出美化

Phase 4 (Wrap-up):
  T17 + T18
  ↳ 测试补全 + 文档更新
```

### 5.3 里程碑

| 版本 | 内容 | 状态 |
|------|------|------|
| v0.5.0-alpha | T1+T2: Milestone 管理 | ✅ Done |
| v0.5.0-beta | T4+T5: 批量编辑 | ✅ Done |
| v0.5.0-rc | T3+T6+T7+T8+T11-T13: 统计+搜索+模板+文档关联 | ✅ Done |
| v0.5.0 | T9-T10+T14-T18: 关联+配置+格式+文档 | ✅ Done |

---

## 附录: 与 v0.3 Rejected Items 的对照

v0.3 的 TODO 文档 (docs/TODO-v0.3.md) 曾拒绝了 milestone 和 templates，理由是"个人工具不需要"和"使用频率低"。经过 5 组 AI 压力测试的反馈，这两个功能在实际使用中被高频需要：

- **Milestone**: 5/5 测试者都用 label 模拟 milestone（如 `v1.0-alpha`, `Sprint-1`, `milestone:v2.0.0`），说明真实需求存在
- **Templates**: 多个测试者创建了格式高度相似的 issue（bug report 模板、feature request 模板），手动复制低效

v0.5 将这两个功能正式纳入，同时保持简洁——不引入复杂的版本管理或模板变量系统。
