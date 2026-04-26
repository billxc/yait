# PRD: yait — Yet Another Issue Tracker

**Version:** 0.1  
**Date:** 2026-04-26  
**Status:** Draft

---

## 概述

yait 是一个基于 markdown + git 的本地 issue 追踪工具。每个 issue 是一个 markdown 文件，元数据存在 YAML frontmatter 中，所有变更通过 git commit 自动记录历史。

## 目标

- 零依赖外部服务，完全本地运行
- Issue 数据是纯文本，人类可读，git 友好
- CLI 操作简单直觉，和 git 工作流自然融合
- 可通过 `pip install .` 一键安装

## 非目标

- 不做 Web UI（M1 范围外）
- 不做多用户协作/权限管理
- 不做远程同步（用户自己 push/pull）
- 不做看板/甘特图等可视化
- 不做 GitHub/GitLab 同步

---

## 用户故事

1. **初始化**: 作为开发者，我在项目根目录执行 `yait init`，创建 `.yait/` 目录开始追踪 issues。
2. **创建 issue**: 我执行 `yait new --title "修复登录 bug" --label bug`，系统创建一个 markdown 文件并自动 commit。
3. **查看列表**: 我执行 `yait list` 查看所有 open issues，也可以 `yait list --label bug` 过滤。
4. **查看详情**: 我执行 `yait show 1` 查看 issue #1 的完整内容。
5. **关闭 issue**: 我执行 `yait close 1`，状态变为 closed 并自动 commit。
6. **重新打开**: 我执行 `yait reopen 1`，状态变回 open。
7. **添加评论**: 我执行 `yait comment 1 "已在 dev 分支修复"`，文本追加到 markdown body。
8. **编辑**: 我执行 `yait edit 1`，打开 `$EDITOR` 编辑 issue 文件。
9. **管理标签**: 我执行 `yait label 1 add feature` 给 issue 加标签。
10. **搜索**: 我执行 `yait search "登录"` 全文搜索 issues。

---

## 数据模型

### 目录结构

```
project-root/
└── .yait/
    ├── config.yaml        # 项目配置
    └── issues/
        ├── 1.md
        ├── 2.md
        └── ...
```

### config.yaml

```yaml
version: 1
next_id: 3
```

### Issue 文件格式 (`<id>.md`)

```markdown
---
id: 1
title: "修复登录 bug"
status: open          # open | closed
labels:
  - bug
assignee: ""
created_at: "2026-04-26T10:00:00+08:00"
updated_at: "2026-04-26T10:00:00+08:00"
---

issue 正文内容（可选，创建时为空）

---
**Comment** by @user at 2026-04-26 11:00

已在 dev 分支修复
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | int | 是 | 自增 ID，从 1 开始 |
| title | string | 是 | 标题 |
| status | enum | 是 | `open` 或 `closed` |
| labels | list[str] | 否 | 标签列表，默认空 |
| assignee | string | 否 | 负责人，默认空 |
| created_at | datetime | 是 | ISO 8601 格式 |
| updated_at | datetime | 是 | 每次修改自动更新 |

---

## CLI 接口设计

入口命令: `yait`

### `yait init`

初始化当前目录为 yait 项目。

- 创建 `.yait/` 目录和 `config.yaml`
- 创建 `.yait/issues/` 目录
- 如果已存在则报错
- 自动 git commit

### `yait new`

创建新 issue。

```
yait new --title "标题" [--label bug] [--label feature] [--assign alice]
```

- `--title` 必填
- `--label` 可多次使用
- `--assign` 可选
- 从 `config.yaml` 读取 `next_id`，创建文件后递增
- 自动 git commit，message: `yait: create issue #<id> — <title>`
- 输出: `Created issue #<id>: <title>`

### `yait list`

列出 issues。

```
yait list [--status open|closed|all] [--label bug] [--assignee alice]
```

- 默认只显示 `status=open`
- 支持按 label、assignee 过滤
- 输出表格格式:

```
#   STATUS  TITLE                LABELS       ASSIGNEE
1   open    修复登录 bug          bug          alice
3   open    添加搜索功能          feature      —
```

### `yait show <id>`

显示 issue 详情，渲染完整 markdown 内容（frontmatter 格式化显示 + body）。

### `yait close <id>`

- 将 status 改为 `closed`，更新 `updated_at`
- 自动 git commit，message: `yait: close issue #<id>`

### `yait reopen <id>`

- 将 status 改为 `open`，更新 `updated_at`
- 自动 git commit，message: `yait: reopen issue #<id>`

### `yait comment <id> <text>`

- 将评论追加到 markdown body 末尾
- 格式: `---\n**Comment** at <timestamp>\n\n<text>`
- 更新 `updated_at`
- 自动 git commit，message: `yait: comment on issue #<id>`

### `yait edit <id>`

- 打开 `$EDITOR`（默认 `vi`）编辑 issue 文件
- 保存后更新 `updated_at`
- 自动 git commit，message: `yait: edit issue #<id>`

### `yait label <id> add|remove <label>`

- 添加或移除标签
- 更新 `updated_at`
- 自动 git commit

### `yait search <query>`

- 对所有 issue 文件进行全文搜索（title + body）
- 大小写不敏感
- 输出匹配的 issue 列表（同 list 格式）

---

## 技术方案

- **语言**: Python 3.10+
- **依赖**: PyYAML（frontmatter 解析），click（CLI 框架）
- **打包**: pyproject.toml，`pip install .` 安装
- **Git 操作**: 调用 `subprocess.run(["git", ...])` 执行 git 命令
- **Frontmatter 解析**: 用 `---` 分隔符手动解析，或用 `python-frontmatter` 库

### 项目结构

```
yet-another-issue-tracker/
├── pyproject.toml
├── README.md
├── src/
│   └── yait/
│       ├── __init__.py
│       ├── cli.py          # click CLI 入口
│       ├── core.py         # issue CRUD 逻辑
│       ├── git.py          # git 操作封装
│       ├── models.py       # Issue 数据类
│       └── storage.py      # 文件读写
└── tests/
    ├── test_core.py
    └── test_cli.py
```

---

## Milestone 划分

### M1: 项目骨架 + 基础 CRUD

**目标**: 能创建、查看 issues

- 项目结构搭建（pyproject.toml, src layout）
- `yait init` — 初始化 .yait 目录
- `yait new` — 创建 issue
- `yait list` — 列出 issues（支持 --status 过滤）
- `yait show` — 查看 issue 详情
- Issue 数据模型 + 文件读写
- 基础测试

### M2: 状态管理 + Git 集成

**目标**: 完整的 issue 生命周期 + 自动 git commit

- `yait close` / `yait reopen`
- `yait comment`
- `yait edit`
- Git 自动提交封装
- 所有写操作加上 git commit

### M3: 标签 / 搜索 / 过滤

**目标**: 完善检索和组织能力

- `yait label add/remove`
- `yait search` 全文搜索
- `yait list` 支持 `--label`, `--assignee` 过滤
- `yait new` 支持 `--assign`

---

## 错误处理

- `.yait/` 不存在时提示 `Not a yait project. Run 'yait init' first.`
- Issue ID 不存在时提示 `Issue #<id> not found.`
- 重复 init 时提示 `Already initialized.`
- git 不可用时给出警告但不阻断操作（M2 处理）

---

## 验收标准

M1 完成时应能执行以下流程:

```bash
cd my-project
yait init
yait new --title "第一个 issue"
yait new --title "第二个 issue" --label bug
yait list
yait show 1
```
