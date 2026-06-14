# API 参考

> CLI 命令 + Python 模块 API. 仓库使用见 [README.md](../README.md), 测试见 [TESTING.md](../TESTING.md).

---

## 1. CLI 命令

### 浏览
```bash
wiki doctor [-v]
wiki list [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--tag X] \
          [--solved-min N] [--sort date|solved|rate|total] \
          [--order asc|desc] [--limit N] [--json]
wiki show <slug> [--body/--no-body]
```

### CRUD
```bash
# 手动新增 (无 flag 走交互)
wiki add
wiki add --slug X --name Y --date Z --total N --problems "O;O;.;" \
         [--tags "#icpc"] [--link URL] [--body "..."] [-y]

wiki set <slug> [--name X] [--date Z] [--total N] [--problems "O;O;."] \
                [--tags "#x #y"] [--link URL] \
                [--status A=O] [-y]   # --status 可多次

wiki rm <slug> [--keep-body] [-y]
wiki edit <slug>                       # 打开 $EDITOR
```

### QOJ 导入
```bash
# 比赛日: 从 standings 抓 (mark O / ! / .)
wiki update <cid> [--user NAME] [--slug X] [--date YYYY.M.D] [--dry-run] [-y]

# 几天后: 从 submissions 检测补题 (mark ./! → Ø)
wiki upsolve <cid> [--user NAME] [--since ISO] [--dry-run] [-y]
```

### 代码抓取
```bash
wiki codes <cid> [--oj PLATFORM] [--user X] \
              [--only-mine | --only-watchlist | --no-watchlist] \
              [--samples N] [--problem A] [--refresh] [-y]
# 默认: 自己全抓(含 WA 复盘) + watchlist AC + 每题最多 5 个 sample (watchlist 优先)
# 单 problem: --problem A
# 旧 flag (已废弃, 用 stderr warning): --platform, --sample
# 缓存: <repo>/codes/<platform>/<cid>/<problem>/<user>.<ext> (gitignored)
# 想放外面: export CODES_DIR=~/.local/share/wiki/codes

wiki codes-list <cid> [--platform X] [--problem A] [--user X] \
                  [--source mine|watchlist|sample|other] [--limit N]
wiki codes-show <cid> <user> <problem> [--platform X]   # less
```

### Config / Cookie / Watchlist
```bash
wiki cookies import <file>          # Netscape jar
wiki cookies set                   # 交互式隐藏输入 3 个值
wiki cookies status

wiki watchlist list
wiki watchlist add <user>...        # 空格分隔多个
wiki watchlist remove <user>... [--all]

wiki config show
wiki config set <key> <value>      # 例: default_user.qoj tarjen
wiki config get <key>
wiki config path
```

### 其他
```bash
wiki sync                            # 重生成 docs/index.md + data/contests.json
wiki serve                           # mkdocs preview
```

---

## 2. Python 模块

### `csv_store.CsvStore` — contests.csv
```python
from csv_store import CsvStore, Contest
store = CsvStore(Path("contests.csv"))
store.load()
store.all()                             # list[Contest]
store.get(slug) / store.exists(slug)
store.add(contest) / store.update(slug, ...) / store.delete(slug)
store.save()                            # 原子写 (tmp + rename)
```

### `md_store.MdStore` — 详情页 md
```python
md = MdStore(Path("docs/contests"))
md.exists(slug) / md.read(slug) / md.write(slug, content) / md.delete(slug)
md.placeholder(contest)                 # 默认模板
```

### `git_ops.GitOps` — git 包装
```python
git = GitOps(Path("~/wiki"))
git.status() / git.commit("msg") / git.push() / git.pull()
git.commit_and_push("msg", ["paths"])  # (sha, pushed) 或抛 GitPushError
```

### `import_logic` — QOJ 导入
```python
from import_logic import (
    build_update_preview, apply_update,
    build_upsolve_preview, apply_upsolve,
)
preview = build_update_preview(platform="qoj", contest_id="2521", user="tarjen",
                                csv_store=csv, config_dir=cfg, slug_override=None)
result = apply_update(preview=preview, csv_store=csv, md_store=md, git_ops=git,
                     create_body=True, run_sync=True, push=True)
```

### `codes_logic` — 代码抓取
```python
from codes_logic import FetchRequest, fetch_codes
req = FetchRequest(
    platform="qoj",        # = --oj (默认 qoj)
    cid="2521", username="tarjen",
    fetch_self=True, fetch_watchlist=True,
    fetch_others="top_n_fastest",
    samples_per_problem=5, # 每题 watchlist+others 池上限 (默认 5)
    skip_existing=True, request_interval=1.5,
    # 旧字段 others_n 已废弃, 仍可传 (DeprecationWarning, 转发到 samples_per_problem)
)
result = fetch_codes(req, platform_client_factory, codes_store, watchlist)
# result.fetched / skipped_existing / errors / files / error_details
# 抓取策略: 自己全抓 (含 WA) + watchlist AC + 每题 watchlist 优先补到 samples_per_problem.
```

### `codes_store.CodesStore` — 本地代码缓存
```python
store = CodesStore(Path("codes").expanduser())   # 默认 <repo>/codes/ (gitignored)
store.save(platform="qoj", cid=2521, problem="A", user="alice",
           code="#include...", language="GNU C++17", submission_id=12345,
           source="mine", contest_time="1:23")
store.read(platform="qoj", cid=2521, problem="A", user="alice")
store.list_files(platform="qoj", cid=2521)        # 接受 problem/user/source 过滤
store.clean(platform="qoj", cid=2521)
```

### `platforms.qoj.QojClient` — QOJ 客户端
```python
from platforms.qoj import QojClient
client = QojClient(cookies={"uoj_remember_token": "...", ...})
client.cookies_valid()
client.get_contest_meta("2521")
client.get_user_standings("2521", "tarjen")           # dict[letter, StandingsEntry]
client.get_all_user_standings("2521", {"tarjen"})     # dict[letter, [FastestACEntry]]
client.get_user_submissions("2521", "tarjen")         # list[Submission]
client.get_submission_code("12345")                   # (code, language)
```

### `watchlist.Watchlist`
```python
wl = Watchlist(Path("~/.config/wiki/watchlist.txt"))
wl.load() / wl.save()
wl.users() / wl.contains("alice")
wl.add(["carol"]) / wl.remove(["alice"])
```

### 平台抽象 (加新 OJ)
```python
class PlatformClient(ABC):
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
    @abstractmethod
    def get_problem_letters(self, contest_id: str) -> list[str]: ...   # 题目列表

    # URL 助手 (concrete) — 子类覆盖 BASE_URL + URL_TEMPLATES 即可:
    client.contest_url("2521")                # "https://qoj.ac/contest/2521"
    client.standings_url("2521")              # "...standings"
    client.problem_url("2521", "A")           # "...problem/A"
    client.submission_url("12345")            # ".../submission/12345"
    client.parse_problem_ref(raw, "2521")     # OJ-native problem 引用 → canonical letter
```

---

## 3. 错误处理

| 错误 | 修法 |
|------|------|
| `✗ slug 不存在: X` | `wiki list` 找对 slug |
| `✗ cookie 未配置` | `wiki cookies set` |
| `✗ QOJ cookie 失效` | 重新 `wiki cookies set` |
| `✗ CF challenge detected` | 等几分钟, 或换 IP |
| `✗ git push 失败` | `git remote -v` 检查 |
| `✗ 仓库有其他未提交改动` | 先 `git status` / commit |

---

## 4. 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `REPO_PATH` | `cwd` | wiki git 仓库 |
| `CONFIG_DIR` | `~/.config/wiki` | cookie / config / watchlist |
| `CODES_DIR` | `<repo>/codes` | 代码缓存 (gitignored) |
| `EDITOR` | `vi` | `wiki edit` |
