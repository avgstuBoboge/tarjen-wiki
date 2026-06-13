# Wiki Backend — API

> **CLI + Python API 参考** — 完整命令列表 + 模块导入接口。
>
> 架构/数据流/安装见 [README.md](../README.md)，测试见 [docs/TESTING.md](TESTING.md)。

---

# 1. CLI API

> **上手**: 大多数命令支持 `<no flag>` 走交互式 prompt。`--dry-run` 永远只预览不写。
> 所有命令都有 `wiki <command> --help`。

## 1.1 健康检查

```bash
wiki doctor [-v]
```

输出:
```
✓ 数据 store 加载完成
  仓库: /home/tarjen/wiki
  比赛: 23
  watchlist: 2 人
  git: main clean, ahead=0
  QOJ cookie: ~/.config/wiki/cookies/qoj.txt (240 bytes)
```
`-v` 还会显示 CSV 警告 (字段缺失, 行号等)。

## 1.2 浏览

```bash
wiki list [--since YYYY-MM-DD] [--until YYYY-MM-DD] \
          [--tag X] (可重复) \
          [--solved-min N] [--sort date|solved|rate|total] \
          [--order asc|desc] [--limit N] [--json]

wiki show <slug> [--body/--no-body]   # 默认含 body
```

## 1.3 CRUD — 手工 & 改

### 1.3.1 手动新增 (无 cookie, 无网络)

```bash
# 交互模式 (零 flag) — 一路回车就行
wiki add

# 全 flag 模式 — 一次给齐, 适合脚本
wiki add --slug X --name Y --date Z --total N --problems "O;O;.;" \
         [--tags "#icpc #regional"] [--link URL] [--body "..."] [-y]
```

交互模式问: `slug → name → date → total → (逐题 O/Ø/!/.) → link`.
**不需要 QOJ cookie, 不需要联网** — 适合手填老比赛 / CF / AtCoder.

### 1.3.2 改字段

```bash
wiki set <slug> [--name X] [--date Z] [--total N] [--problems "O;O;."] \
                [--tags "#x #y"] [--link URL] \
                [--status A=O] (可重复, 按位置改) \
                [-y]
```

### 1.3.3 删

```bash
wiki rm <slug> [--keep-body] [-y]
```

### 1.3.4 编辑 md (开 $EDITOR)

```bash
wiki edit <slug>
```

## 1.4 QOJ 导入（核心日常）

```bash
# 比赛日: 从 standings 抓当前状态
wiki update <cid> [--platform X] [--user NAME] [--slug X] [--date YYYY.M.D] \
                 [--dry-run] [-y]

# 几天后: 从 submissions 检测补题
wiki upsolve <cid_or_slug> [--platform X] [--user NAME] [--since ISO] \
                   [--dry-run] [-y]
```

| 命令 | 数据源 | 用途 |
|---|---|---|
| `update` | `/contest/<cid>/standings` (JS 数组) | 当前状态 (含 upsolve) |
| `upsolve` | `/contest/<cid>/submissions?user=X` (HTML) | 赛后补题检测 |

行为:
- `update`: 把 standings 映射为 O/!/.，自动 create_new 或 update_existing
- `upsolve`: 把比赛后新 AC 的题从 ./! 升级为 Ø
- 默认每次有 Y/n 确认; `--yes` / `-y` 跳过
- `--dry-run` 只预览
- `--user X` 覆盖 config 里的默认 user
- `--date X` 覆盖 CSV date (QOJ 不公开 start_time 时手动设)

## 1.5 代码抓取

```bash
wiki codes <cid> [--platform X] [--user NAME] \
              [--only-mine] [--only-watchlist] [--no-watchlist] \
              [--sample N] (默认 1, others 每题抽几个) \
              [--problem A,B,C] [--status AC|WA|ALL] [--refresh] [-y]

wiki codes-list <cid> [--platform X] [--problem A] [--user X] \
              [--source mine|watchlist|sample|other]

wiki codes-show <cid> <user> <problem> [--platform X]   # 打开 (less)
```

策略 (默认):
- 自己: 全部 verdict (含 WA/TLE, 复盘用)
- watchlist 用户: 所有 AC
- 其他人: 每题最早 AC 的前 N 个

缓存路径: `~/.local/share/wiki/codes/<platform>/<cid>/<problem>/<user>.<ext>`

## 1.6 Cookie / Watchlist / Config

```bash
# Cookie
wiki cookies import <file>          # Netscape jar 文件
wiki cookies set [--platform X]    # 交互式输入 3 个值 (隐藏)
wiki cookies status [--platform X]

# Watchlist
wiki watchlist list
wiki watchlist add <user>...       # 空格分隔多个
wiki watchlist remove <user>... [--all]

# Config
wiki config show                   # 显示 ~/.config/wiki/config.json
wiki config set <key> <value>      # 例: wiki config set default_user.qoj tarjen
wiki config get <key>
wiki config path                   # 显示路径
```

## 1.7 其他

```bash
wiki sync                            # 跑 tools/sync.py (重建 docs/index.md + data/contests.json)
wiki serve                           # mkdocs preview (前端, 不是后端)
```

---

# 2. Python API

CLI 直接 import 这些, 所以是事实上的 API。

## 2.1 `csv_store.CsvStore` — CSV 持久层

```python
from csv_store import CsvStore, Contest

store = CsvStore(Path("contests.csv"))
store.load()                                    # 加载所有

# 查询
store.all()                                     # list[Contest], 按日期倒序
store.get(slug)                                 # Contest | None
store.exists(slug)                              # bool
len(store)                                      # int

# 修改
store.add(contest)                              # 写内存
store.update(slug, name=..., problems=[...])    # 改字段
store.delete(slug)                              # 删
store.save()                                    # 原子写盘 (tmp + rename)
```

## 2.2 `md_store.MdStore` — 详情页 md

```python
from md_store import MdStore

md = MdStore(Path("docs/contests"))
md.exists(slug)                                 # bool
md.read(slug)                                   # str
md.write(slug, content)                         # 原子写
md.delete(slug)                                 # bool
md.placeholder(contest)                         # str (默认模板)
```

## 2.3 `git_ops.GitOps` — git 包装

```python
from git_ops import GitOps, GitPushError

git = GitOps(Path("~/wiki"))
git.status()                                    # RepoStatus (clean, ahead, ...)
git.add(["contests.csv"])
git.commit("add(xxx)")                          # sha
git.push()                                      # 可能抛 GitPushError
git.commit_and_push("msg", ["paths"])           # (sha, pushed) 或抛 GitPushError
git.pull()                                      # 本地脏时抛 GitConflictError
```

## 2.4 `import_logic` — QOJ 导入

```python
from import_logic import (
    build_update_preview, apply_update,
    build_upsolve_preview, apply_upsolve,
    UpdatePreview, UpsolvePreview, ApplyResult,
)

# 比赛日
preview = build_update_preview(
    platform="qoj", contest_id="2521", user="tarjen",
    csv_store=csv, config_dir=cfg, slug_override=None,
)
result = apply_update(
    preview=preview, csv_store=csv, md_store=md, git_ops=git,
    create_body=True, run_sync=True, push=True,
)
# ApplyResult(slug, record_state, csv_written, body_written,
#             committed, commit_sha, pushed, problems_before, problems_after)

# 几天后补题
preview = build_upsolve_preview(
    platform="qoj", contest_id="2521", slug=None, user="tarjen",
    csv_store=csv, config_dir=cfg, since_override=None,
)
result = apply_upsolve(preview, csv_store=csv, md_store=md, git_ops=git)
```

## 2.5 `platforms.qoj.QojClient` — QOJ 客户端

```python
from platforms.qoj import QojClient

client = QojClient(cookies={"uoj_remember_token": "...", ...})
client.cookies_valid()                          # bool
client.get_contest_meta("2521")                 # ContestMeta
client.get_user_standings("2521", "tarjen")     # dict[letter, StandingsEntry]
client.get_all_user_standings(                  # dict[letter, [FastestACEntry, ...]]
    "2521", exclude_users={"tarjen"}
)                                                # 用于"每题最快"采样
client.get_user_submissions("2521", "tarjen")   # list[Submission]
client.get_submission_code("12345")             # (code, language)
```

注: 工厂 `from platforms import get_client_class` 按 platform 名分发。未来加 CF/AtCoder 不变 API。

## 2.6 `codes_logic` — 代码抓取

```python
from codes_logic import FetchRequest, fetch_codes

req = FetchRequest(
    platform="qoj", cid="2521", username="tarjen",
    fetch_self=True, fetch_watchlist=True,
    fetch_others="top_n_fastest", others_n=1,
    problems=None, skip_existing=True, request_interval=1.5,
)
result = fetch_codes(req, platform_client_factory, codes_store, watchlist)
# result.fetched, result.skipped_existing, result.errors, result.files, result.error_details
```

## 2.7 `codes_store.CodesStore` — 代码缓存

```python
from codes_store import CodesStore

store = CodesStore(Path("~/.local/share/wiki/codes").expanduser())
store.save(platform="qoj", cid=2521, problem="A", user="alice",
           code="#include...", language="GNU C++17", submission_id=12345,
           source="mine", contest_time="1:23")
code = store.read(platform="qoj", cid=2521, problem="A", user="alice")
files = store.list_files(platform="qoj", cid=2521)
store.clean(platform="qoj", cid=2521)
```

## 2.8 `watchlist.Watchlist` — 关注列表

```python
wl = Watchlist(Path("~/.config/wiki/watchlist.txt"))
wl.load()
wl.users()                                      # list[str]
wl.contains("alice")                            # bool
wl.add(["carol"])
wl.remove(["alice"])
wl.save()
```

---

# 3. 数据类

## 3.1 `Contest` (csv_store)

```python
@dataclass
class Contest:
    slug: str
    name: str
    date: str                # "YYYY.M.D"
    solved: int              # 0..total
    total: int               # 题数
    problems: list[str]      # ["O", ".", "Ø", "!"]
    link: str = ""
    tags: str = ""           # "#icpc #regional"
```

## 3.2 `Submission` / `StandingsEntry` / `FastestACEntry` (platforms.base)

```python
@dataclass
class Submission:
    platform: str
    submission_id: str
    user: str
    problem: str
    verdict: str
    submitted_at: str
    contest_time_seconds: int | None
    tries: int = 1
    language: str | None = None
    code_length: int | None = None

@dataclass
class StandingsEntry:
    """一道题在 standings 里的状态 (含 upsolve)."""
    platform: str
    problem_id: str             # 0-indexed, 字符串
    letter: str                 # "A", "B", ...
    score: int                  # 0-100
    contest_time_seconds: int
    submission_id: str | None
    failed_attempts: int
    verdict: str                # "AC" / "WA"

@dataclass
class FastestACEntry:
    """一道题所有 AC 之一 (用于采样)."""
    user: str
    time_seconds: int
    submission_id: str
```

## 3.3 `CodeFile` (codes_store)

```python
@dataclass
class CodeFile:
    platform: str
    user: str
    problem: str
    path: str
    size: int
    mtime: str
    language: str | None
    verdict: str | None
    submission_id: str | None
    source: Literal["mine", "watchlist", "sample", "other"]
    contest_time: str | None
```

---

# 4. 错误处理

| 错误 | 原因 | 修法 |
|---|---|---|
| `✗ slug 不存在: X` | CSV 里没这条 | `wiki list` 找对的 slug |
| `✗ cookie 未配置` | `~/.config/wiki/cookies/qoj.txt` 缺失 | `wiki cookies import` 或 `wiki cookies set` |
| `✗ QOJ cookie 失效` | cookie 过期 (7-30 天) | 重新从浏览器导出 + import |
| `✗ CF challenge detected` | qoj.ac 把请求当 bot | 等几分钟，或换家庭 IP |
| `✗ QOJ contest not found` | cid 错 | 检查 contest ID |
| `✗ git push 失败` | 没配 remote / 网络 / 权限 | `git remote -v` 检查 |
| `⚠ push 失败但 commit 成功` | commit OK, push 网络问题 | 之后手动 `git push` |
| `✗ 仓库有其他未提交改动` | working tree 脏 | `git status` 看哪些, commit 一下 |

---

# 5. 平台抽象 (加新 OJ)

```python
# tools/platforms/base.py
class PlatformClient(ABC):
    name: ClassVar[str] = ""  # "qoj" / "codeforces" / "atcoder"
    
    @abstractmethod
    def cookies_valid(self) -> bool: ...
    
    @abstractmethod
    def get_contest_meta(self, contest_id: str) -> ContestMeta: ...
    
    @abstractmethod
    def get_user_submissions(self, contest_id: str, user: str) -> list[Submission]: ...
    
    @abstractmethod
    def get_user_standings(self, contest_id: str, user: str) -> dict[str, StandingsEntry]: ...
    
    @abstractmethod
    def get_all_user_standings(self, contest_id: str, exclude_users: set[str] | None = None) -> dict[str, list[FastestACEntry]]: ...
    
    @abstractmethod
    def get_submission_code(self, submission_id: str) -> tuple[str, str]: ...
```

加新平台步骤: 写 `tools/platforms/<name>.py` + `@register` 装饰器 + tests。

---

# 6. 命令行参数全局

| 变量 | 默认 | 说明 |
|---|---|---|
| `REPO_PATH` | `cwd` | wiki git 仓库路径 |
| `CONFIG_DIR` | `~/.config/wiki` | cookie / watchlist / config.json |
| `CODES_DIR` | `~/.local/share/wiki/codes` | 代码缓存 (gitignored) |
| `EDITOR` | `vi` | `wiki edit` 用 |
