# PRD: YAIT 并发锁机制设计

**Status:** Implemented
**Date:** 2026-04-27
**Author:** yait-dev

---

## 1. 现有架构分析

### 1.1 文件布局

```
.yait/
├── config.yaml          # 全局配置（next_id, milestones, defaults, display）
├── issues/
│   ├── 1.md             # 每个 issue 一个文件
│   ├── 2.md
│   └── ...
├── templates/
│   └── *.md
└── docs/
    └── *.md
```

### 1.2 写操作调用链

| CLI 命令 | store 函数 | 写入的文件 | 调用 git_commit |
|---|---|---|---|
| `yait init` | `init_store()` | config.yaml, 创建目录 | Yes |
| `yait new` | `next_id()` → `save_issue()` | config.yaml (next_id++), issues/{id}.md | Yes |
| `yait close` | `save_issue()` | issues/{id}.md | Yes (per issue) |
| `yait reopen` | `save_issue()` | issues/{id}.md | Yes (per issue) |
| `yait delete` | `delete_issue()` | 删除 issues/{id}.md | Yes |
| `yait edit` | `save_issue()` | issues/{id}.md | Yes |
| `yait comment` | `save_issue()` | issues/{id}.md | Yes |
| `yait assign` | `save_issue()` | issues/{id}.md | Yes |
| `yait unassign` | `save_issue()` | issues/{id}.md | Yes |
| `yait label add` | `save_issue()` | issues/{id}.md | Yes |
| `yait label remove` | `save_issue()` | issues/{id}.md | Yes |
| `yait link` | `add_link()` → `save_issue()` x2 | issues/{src}.md + issues/{tgt}.md | Yes |
| `yait unlink` | `remove_link()` → `save_issue()` x2 | issues/{src}.md + issues/{tgt}.md | Yes |
| `yait config set` | `set_config_value()` → `_write_config()` | config.yaml | No |
| `yait config reset` | `reset_config_value()` → `_write_config()` | config.yaml | No |
| `yait milestone create` | `save_milestone()` → `_write_config()` | config.yaml | Yes |
| `yait milestone close` | `update_milestone()` → `_write_config()` | config.yaml | Yes |
| `yait milestone reopen` | `update_milestone()` → `_write_config()` | config.yaml | Yes |
| `yait milestone edit` | `update_milestone()` → `_write_config()` | config.yaml | Yes |
| `yait milestone delete` | `delete_milestone()` → `_write_config()` + 可能 `save_issue()` x N | config.yaml + issues/*.md (force) | Yes |
| `yait template create` | `save_template()` | templates/{name}.md | Yes |
| `yait template delete` | `delete_template()` | 删除 templates/{name}.md | Yes |
| `yait doc create` | `save_doc()` | docs/{slug}.md | Yes |
| `yait doc edit` | `save_doc()` | docs/{slug}.md | Yes |
| `yait doc delete` | `delete_doc()` | 删除 docs/{slug}.md | Yes |
| `yait doc link` | `save_issue()` x N | issues/*.md | Yes |
| `yait doc unlink` | `save_issue()` | issues/{id}.md | Yes |
| `yait import` | `save_issue()` x N + `_write_config()` | issues/*.md + config.yaml | Yes (batch) |
| `yait bulk *` | `save_issue()` x N | issues/*.md | Yes (per issue) |

### 1.3 关键竞态场景

**场景 A：两个 agent 同时 `yait new`**
1. Agent A 调用 `next_id()` → 获得 id=5，config.yaml 更新到 next_id=6
2. Agent B 调用 `next_id()` → 获得 id=6，config.yaml 更新到 next_id=7
3. `next_id()` 有 `fcntl.flock` 保护，**这一步是安全的**
4. 但 `save_issue()` 和 `git_commit()` 无锁 → 两个进程同时执行 `git add .yait && git commit`
5. **结果：** 其中一个 `git commit` 会失败（nothing to commit），或两个 commit 交叉，导致某个 issue 的文件未被 commit

**场景 B：两个 agent 同时编辑不同 issue**
1. Agent A: `yait edit 1 -T "new title"` → `save_issue()` → `git_commit()`
2. Agent B: `yait close 2` → `save_issue()` → `git_commit()`
3. `git_commit()` 中的 `git add .yait` 会 stage 两个 agent 的改动
4. **结果：** Agent A 的 commit 可能包含 Agent B 的未完成修改，反之亦然

**场景 C：两个 agent 同时修改同一 issue**
1. Agent A: `yait label add 1 urgent` → `load_issue(1)` → 修改 → `save_issue(1)` → `git_commit()`
2. Agent B: `yait assign 1 bob` → `load_issue(1)` → 修改 → `save_issue(1)` → `git_commit()`
3. 如果两个 load 在两个 save 之前完成 → 后写的覆盖先写的（丢失更新）
4. **结果：** 要么 label 丢失，要么 assignee 丢失

**场景 D：config.yaml 并发写**
1. Agent A: `yait milestone create v1.0` → `_read_config()` → 修改 → `_write_config()`
2. Agent B: `yait milestone create v2.0` → `_read_config()` → 修改 → `_write_config()`
3. **结果：** 后写的覆盖先写的，v1.0 或 v2.0 的 milestone 数据丢失

### 1.4 现有 `next_id()` 锁分析

```python
def next_id(root: Path) -> int:
    cfg_path = _config_path(root)
    with open(cfg_path, 'r+') as f:
        if fcntl is not None:
            fcntl.flock(f, fcntl.LOCK_EX)
        cfg = yaml.safe_load(f.read())
        nid = cfg["next_id"]
        cfg["next_id"] = nid + 1
        f.seek(0)
        f.truncate()
        f.write(yaml.dump(cfg, default_flow_style=False))
    return nid
```

**特点：**
- 使用 `fcntl.flock` 做排他锁
- 锁的范围仅限于 `next_id` 的 read-modify-write 操作
- `with open()` 确保文件关闭时锁自动释放
- **问题 1：** Windows 上 `fcntl` 不可用（已有 `try/import` fallback，但 fallback 是无锁）
- **问题 2：** 锁的粒度太小——只保护了 next_id 的递增，没保护后续的 `save_issue()` + `git_commit()`
- **问题 3：** 其他写 config.yaml 的操作（milestone CRUD、config set/reset）完全无锁

---

## 2. 业界方案调研

### 2.1 Git 自身的 `.git/index.lock` 机制

Git 使用 lockfile 模式保护并发操作：

- 写 index 前创建 `.git/index.lock`（使用 `O_CREAT | O_EXCL` 原子创建）
- 写入完成后 rename `.git/index.lock` → `.git/index`（原子替换）
- 如果 lock 文件已存在，操作失败并提示用户
- 崩溃检测：lock 文件存在但没有进程持有 → 通过 stale lock 检测（文件年龄）或要求用户手动删除

**优点：** 跨平台（`O_CREAT | O_EXCL` 在所有 OS 上都是原子的）、简单可靠
**缺点：** 无自动重试、需要处理 stale lock

### 2.2 类似工具的做法

**pass (password-store):**
- 使用 `gpg` 加密和 `git` 管理，无显式并发保护
- 依赖 git 自身冲突检测
- 不适用于频繁并发写场景

**todo.txt:**
- 单文件设计，无并发保护
- 社区 wrapper 使用 `flock` 命令行工具

**Jujutsu (jj):**
- Git 兼容 VCS，使用 operation log + 乐观并发控制
- 每个操作记录一个 op ID，并发修改通过 operation merge 自动解决
- 过于复杂，不适合 YAIT 的简单场景

### 2.3 锁实现方式对比

| 方式 | 原子性 | 跨平台 | 崩溃恢复 | 复杂度 |
|---|---|---|---|---|
| **fcntl.flock** | 是（advisory） | macOS + Linux，Windows 不支持 | 进程退出自动释放 | 低 |
| **fcntl.lockf** | 是（POSIX） | macOS + Linux，Windows 不支持 | 进程退出自动释放 | 低 |
| **msvcrt.locking** (Windows) | 是 | 仅 Windows | 进程退出自动释放 | 低 |
| **Lockfile (O_CREAT\|O_EXCL)** | 是 | 全平台 | 需 stale 检测 | 中 |
| **Lockfile + PID** | 是 | 全平台 | PID 存活检测 | 中 |
| **Lockfile + PID + 时间戳** | 是 | 全平台 | PID + 超时双重检测 | 中高 |
| **filelock 库** | 是 | 全平台（封装） | 自动释放 | 低 |
| **SQLite WAL** | 是 | 全平台 | 自动 | 高（改架构） |

---

## 3. 锁方案设计

### 3.1 锁粒度分析

**选项 A：全局锁（`.yait/yait.lock`）**
- 一把锁保护所有写操作
- 优点：实现简单、无死锁风险、保证串行化
- 缺点：并发性低（所有写操作互斥）

**选项 B：两级锁（config.lock + per-issue lock）**
- `.yait/config.lock`：保护 config.yaml 的读写
- `.yait/issues/{id}.lock`：保护单个 issue 文件的读写
- 优点：不同 issue 的修改可以并发
- 缺点：`git_commit()` 仍然需要全局锁；`add_link()` 需要同时锁两个 issue → 死锁风险

**选项 C：操作级全局锁**
- 每个 CLI 写命令的 "read → modify → write → git commit" 全流程加全局锁
- 和选项 A 本质相同，但锁的语义更清晰

**结论：选项 A（全局锁）是最佳选择。** 理由：

1. YAIT 的写操作都很快（毫秒级）— 全局锁不会造成可感知的性能瓶颈
2. `git_commit()` 本身就是全局操作（`git add .yait`），细粒度锁无法绕过这个瓶颈
3. `add_link()` 写两个 issue + config.yaml，细粒度锁引入死锁风险
4. 简单 >> 性能（对于本地工具而言）

### 3.2 推荐方案：Lockfile + PID

**锁文件路径：** `.yait/yait.lock`

**锁文件内容：**
```json
{"pid": 12345, "timestamp": 1714200000.0, "command": "yait new"}
```

**获取锁流程：**
1. 尝试 `open(".yait/yait.lock", O_CREAT | O_EXCL | O_WRONLY)` 原子创建
2. 如果成功 → 写入 PID + 时间戳 + 命令，返回成功
3. 如果失败（文件已存在） → 读取锁文件内容
   - 检查 PID 是否仍存活（`os.kill(pid, 0)` 或 `/proc/{pid}/` 或 `psutil`）
   - 如果进程已死 → stale lock，删除后重试
   - 检查时间戳是否超过超时阈值（默认 60 秒）
   - 如果超时 → stale lock，删除后重试
   - 否则 → 等待重试

**释放锁流程：**
1. `os.unlink(".yait/yait.lock")`
2. 必须在 `finally` 块中执行，确保异常情况下也能释放

**重试策略：**
- 最大等待时间：30 秒
- 重试间隔：50ms 起步，指数退避到 500ms
- 超过最大等待时间后抛出 `LockTimeout` 异常

**Stale lock 检测：**
- 先检查 PID 存活性（快速、准确）
- 再检查时间戳超时（兜底，防止 PID 复用的极端情况）
- 超时阈值：60 秒（YAIT 单个操作不会超过几秒）

### 3.3 实现方式：Context Manager

```python
# 伪代码示意
class YaitLock:
    def __init__(self, root: Path, command: str = "",
                 timeout: float = 30.0, stale_timeout: float = 60.0):
        self.lock_path = root / ".yait" / "yait.lock"
        self.command = command
        self.timeout = timeout
        self.stale_timeout = stale_timeout

    def __enter__(self):
        self._acquire()
        return self

    def __exit__(self, *exc):
        self._release()

    def _acquire(self):
        # O_CREAT|O_EXCL atomic create → retry with backoff → stale detection
        ...

    def _release(self):
        # os.unlink(self.lock_path), ignore FileNotFoundError
        ...
```

**CLI 集成点（两种方式）：**

**方式 1：在每个 CLI 命令函数内部包裹（侵入性低）**
```python
@main.command()
def close(ids):
    root = _root()
    with YaitLock(root, "close"):
        # 原有逻辑
```

**方式 2：装饰器（更优雅）**
```python
def with_lock(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        root = _root()
        with YaitLock(root, f.__name__):
            return f(*args, **kwargs)
    return wrapper

@main.command()
@with_lock
def close(ids):
    ...
```

推荐 **方式 1**（Context Manager 直接包裹），理由：
- 更显式、更清晰
- 读操作（list, show, search, stats, export）不需要锁
- 装饰器需要额外处理 click 参数传递问题

### 3.4 跨平台兼容性

| 操作 | macOS/Linux | Windows |
|---|---|---|
| `O_CREAT \| O_EXCL` | `os.open()` 原子创建 | `os.open()` 原子创建 |
| PID 检查 | `os.kill(pid, 0)` | `os.kill(pid, 0)` (Python 3.x) |
| 锁文件删除 | `os.unlink()` | `os.unlink()`（注意：Windows 不允许删除被其他进程打开的文件，但 lockfile 写完即关闭，没问题） |

整个方案不依赖 `fcntl`，天然跨平台。

### 3.5 与现有 `next_id()` fcntl 锁的关系

引入全局锁后，`next_id()` 的 fcntl 锁变得**冗余但无害**：
- 全局锁已经确保同一时刻只有一个写操作
- fcntl 锁可以保留（defense in depth）或移除（简化代码）
- **建议：保留**。成本为零，多一层保护

### 3.6 `.gitignore` 处理

锁文件不应被 git 追踪：
- 在 `.yait/.gitignore`（或项目 `.gitignore`）中添加 `yait.lock`
- 或在 `git_commit()` 中的 `git add` 排除 lock 文件

---

## 4. 改动范围预估

### 4.1 新增文件

| 文件 | 说明 |
|---|---|
| `src/yait/lock.py` | `YaitLock` class，约 80-120 行 |

### 4.2 修改文件

| 文件 | 改动 |
|---|---|
| `src/yait/cli.py` | 在所有写命令中添加 `with YaitLock(root, "cmd"):` 包裹。约 25 个写命令需要修改，每个改动 2-3 行（添加 with 语句 + 缩进调整） |
| `src/yait/store.py` | 无需修改（锁在 CLI 层而非 store 层） |
| `src/yait/git_ops.py` | 无需修改 |
| `.gitignore` 或 `.yait/.gitignore` | 添加 `yait.lock` |

### 4.3 新增测试

| 文件 | 说明 |
|---|---|
| `tests/test_lock.py` | 锁的单元测试：获取/释放、超时、stale 检测、并发竞争。约 100-150 行 |

---

## 5. 推荐方案总结

**全局 lockfile (.yait/yait.lock) + PID/时间戳 stale 检测 + 指数退避重试**

### 理由

1. **简单可靠** — 整个方案约 100 行代码，一个新文件，无新依赖
2. **跨平台** — 不依赖 fcntl，macOS/Linux/Windows 全支持
3. **崩溃安全** — PID 检测 + 超时双重保护，不会永久死锁
4. **侵入性低** — store.py、git_ops.py 零改动，只在 CLI 层加 context manager
5. **性能足够** — YAIT 单个操作耗时毫秒级，全局串行化对用户无感知影响。即便 10 个 agent 并发，排队等待也只是几百毫秒

### Trade-offs

| 方面 | 选择 | 代价 |
|---|---|---|
| 粒度 | 全局锁 | 不同 issue 的修改不能并发（但 YAIT 操作极快，不是问题） |
| 实现 | Lockfile (非 fcntl) | 需要 stale lock 检测（比 fcntl 自动释放多一步） |
| 锁的层级 | CLI 层 | 直接调用 store API 的代码（如测试）不受保护 — 可接受，因为生产入口是 CLI |
| 兼容性 | 保留 fcntl | 极小的代码冗余 |

### 未来扩展

如果未来需要更高并发：
- 可将 lockfile 方案替换为 `filelock` 第三方库（更健壮的跨平台封装）
- 可将 git_commit 改为 batch 模式（多个操作合并一次 commit）减少 git 开销
- 可引入乐观锁（issue 文件中记录 version/hash，写前校验）解决 lost update

---

## 附录：不建议的方案

### A. 使用 `filelock` 第三方库

`filelock` 库封装了跨平台文件锁，API 简洁。但 YAIT 目前零外部依赖（只有 click 和 pyyaml），引入 filelock 增加依赖链。lockfile + PID 的自实现方案只需 ~100 行，不值得为此加依赖。如果将来需要更多跨平台工具，可以再考虑。

### B. 使用 SQLite 做后端

将 config.yaml + issue 文件全部迁移到 SQLite 数据库，利用 SQLite 的 WAL 模式天然解决并发。但这彻底改变了 YAIT 的核心设计（markdown 文件 + git 追踪），工程量巨大，且丧失了"人可读的 issue 文件"这个核心优势。

### C. 细粒度锁

为 config.yaml 和每个 issue 文件分别加锁。理论上可以提高并发度，但 `git_commit()` 的 `git add .yait` 是全局操作，锁粒度再细也没用。加上 `add_link()` 需要同时写两个 issue，引入锁排序等复杂度，投入产出比差。
