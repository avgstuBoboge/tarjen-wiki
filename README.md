# Wiki Backend

> **个人编程比赛记录系统** — 终端 CLI 工具 + MkDocs 静态站点，托管在 GitHub Pages。
>
> **335 tests passing** (272 单元 + 63 平台，含真实 QOJ fixture)。

## 这是什么

一个 [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) 驱动的个人编程比赛 tracker。后端是 Python CLI（**无 HTTP 服务**），数据存本地 `contests.csv` + `docs/contests/*.md`，唯一网络出口是 QOJ 抓取和 `git push`。

```
$ wiki update 2521            # 比赛日: 从 QOJ 拉数据写 csv
$ wiki upsolve 2521           # 几天后: 检测补题
$ wiki codes 2521             # 抓代码 (自己 + watchlist + 每题最快 1 个 sample)
$ wiki add                    # 手填老比赛 / CF / AtCoder
$ mkdocs gh-deploy            # 推 GH Pages
```

## 图例

| 符号 | 含义 |
|------|------|
| `O` | 赛中通过 |
| `Ø` | 赛中没通过，**赛后补题**通过 |
| `!` | 试过没过 |
| `.` | 没提交 |

## 仓库结构

```
.
├── bin/                    # 跨平台 wrapper (bash / cmd / PowerShell)
├── docs/                   # MkDocs 输入
│   ├── contests/           # 每场比赛一个 .md
│   ├── data/contests.json  # 由 sync.py 生成 (前端用)
│   ├── editor/             # 可视化编辑器 (静态页)
│   └── index.md            # 总表 (由 sync.py 重生成)
├── tools/                  # Python CLI + 库
│   ├── cli_main.py         # 入口 (所有 wiki <command>)
│   ├── csv_store.py        # contests.csv 读写
│   ├── md_store.py         # docs/contests/<slug>.md 读写
│   ├── git_ops.py          # git commit/push 包装
│   ├── import_logic.py     # update/upsolve 业务逻辑
│   ├── codes_logic.py      # 代码抓取业务逻辑
│   ├── codes_store.py      # 本地代码缓存
│   ├── watchlist.py        # 关注列表
│   ├── sync.py             # 重生成 docs/index.md + data/contests.json
│   ├── platforms/          # OJ 客户端 (QOJ)
│   │   ├── base.py         # 抽象接口
│   │   └── qoj.py          # QOJ 实现 (cloudscraper 绕 CF)
│   └── API.md              # CLI + Python API 详细文档
├── tests/                  # 335 单元测试
│   ├── fixtures/qoj_real/  # 真实 QOJ HTML (contest 1357, 2521)
│   └── platforms/          # QOJ 客户端测试
├── contests.csv            # 唯一数据源
├── mkdocs.yml              # MkDocs 配置
└── requirements.txt        # 锁定版本
```

## 30 秒上手

```bash
# 1. 装
cd ~/wiki
./bootstrap.sh             # 建 venv + 装依赖 + 装 wrapper 到 ~/.local/bin/wiki

# 2. 配 QOJ cookie (3 个值, 一次性输入)
wiki cookies set

# 3. 配默认 user (之后不用每次传 --user)
wiki config set default_user.qoj tarjen

# 4. 跑比赛日
wiki update 2521           # 预览 + y 写入
# 或:  wiki update 2521 -y   # 跳过确认

# 5. 几天后检测补题
wiki upsolve 2521 -y

# 6. 抓代码 (自己 + watchlist + 每题最快 1 个 sample)
wiki codes 2521
wiki codes-list 2521       # 看抓到了啥

# 7. 推 GH Pages
mkdocs gh-deploy
```

详细文档见 [tools/API.md](tools/API.md)。

## 数据流

```
$ wiki update 2521
  ↓
bin/wiki (wrapper, exec venv python)
  ↓
tools/cli_main.py (Click)
  ↓
tools/import_logic.py   ← 业务逻辑
  ↓
tools/platforms/qoj.py  ← 抓 QOJ (唯一网络: qoj.ac)
tools/csv_store.py      ← contests.csv (本地)
tools/md_store.py       ← docs/contests/<slug>.md (本地)
tools/git_ops.py        ← git commit/push
  ↓
contests.csv + docs/contests/*.md + git push → GitHub → GH Pages
```

**两个网络出口**:
1. `platforms.qoj._fetch` 抓 qoj.ac（cloudscraper 绕 Cloudflare）
2. `git_ops.push` 推 GitHub

**全部本地**: CSV 读写 / md 读写 / git commit / watchlist / codes 缓存。

## 路径约定

代码缓存（不在 repo，gitignored）:
```
~/.local/share/wiki/codes/<platform>/<cid>/<problem>/<user>.<ext>
  e.g.
  ~/.local/share/wiki/codes/qoj/2521/A/tarjen.cpp       ← 自己
  ~/.local/share/wiki/codes/qoj/2521/A/fynfyn.txt      ← 别人最快 AC
```

config / cookie / watchlist:
```
~/.config/wiki/
├── config.json                            # { "default_user": {"qoj": "tarjen"} }
├── cookies/qoj.txt                        # Netscape cookie jar
└── watchlist.txt                          # 一行一个用户
```

## CLI 命令一览

| 命令 | 作用 |
|------|------|
| `wiki doctor [-v]` | 健康检查 (env, cookie, git status) |
| `wiki list [--since YYYY-MM-DD] [--tag X] [--solved-min N] [--sort ...]` | 列表 |
| `wiki show <slug>` | 看单场比赛 |
| `wiki add` | 手动新增 (零 flag 走交互) |
| `wiki add --slug X --name Y --date Z --total N --problems "O;O;.;"` | 手动新增 (全 flag) |
| `wiki set <slug> [--status A=O] [--problems "O;O;."] ...` | 改字段 |
| `wiki rm <slug>` | 删 |
| `wiki edit <slug>` | 开 $EDITOR 编辑 md |
| `wiki update <cid> [-y] [--user X] [--date YYYY.M.D]` | 比赛日: 从 QOJ 拉数据 |
| `wiki upsolve <cid> [-y] [--user X]` | 几天后: 检测补题 |
| `wiki codes <cid> [--only-mine] [--only-watchlist] [--sample N]` | 抓代码 |
| `wiki codes-list <cid> [--problem A] [--user X] [--source mine\|watchlist\|sample]` | 列出已抓的 |
| `wiki codes-show <cid> <user> <problem>` | 看某份代码 (less) |
| `wiki cookies {import <file> \| set \| status}` | 配 cookie |
| `wiki watchlist {list \| add <user>... \| remove <user>...}` | 关注列表 |
| `wiki config {show \| set <key> <val> \| get <key> \| path}` | 管理 config.json |
| `wiki sync` | 重生成 docs/index.md + data/contests.json |
| `wiki serve` | 跑 mkdocs preview (前端, 不是后端) |

完整文档 + Python API: [tools/API.md](tools/API.md)。

## 添加新 OJ（CF / AtCoder / ...）

1. 写 `tools/platforms/codeforces.py`（继承 `PlatformClient`, 实现 4 个 abstractmethod）
2. 在 `tools/platforms/__init__.py` 加 `@register` 装饰器
3. 写 `tests/platforms/test_codeforces.py` + fixtures
4. ~200 行代码

**API / CLI 完全不变**, 只多一个 `--platform cf` 选项。

## 测试

```bash
# 跑全部
make test              # make test-py + make test-js

# 单独跑 Python
.venv/bin/python -m unittest discover tests/

# 单独跑平台测试 (QOJ parser)
.venv/bin/python -m unittest discover -s tests/platforms

# 跑单个文件
.venv/bin/python -m unittest tests.test_csv_store

# 跑单个 case
.venv/bin/python -m unittest tests.test_csv_store.TestParseProblems.test_basic -v
```

详细测试覆盖: [docs/TESTING.md](docs/TESTING.md)。

## 部署

```bash
mkdocs gh-deploy
```

首次部署后到 GitHub 仓库 `Settings → Pages`:
- Source: `Deploy from a branch`
- Branch: `gh-pages` / `(root)`

## 平台支持

| 平台 | 状态 | 启动方式 |
|---|---|---|
| macOS | ✅ 已测 | `wiki xxx` (bin/wiki bash) |
| Linux | ✅ CI 测 | `wiki xxx` |
| Windows (Git Bash) | ✅ 应该可以 | `wiki xxx` |
| Windows (cmd) | ✅ | `bin\wiki.cmd xxx` |
| Windows (PowerShell) | ✅ | `& .\bin\wiki.ps1 xxx` |

Python 部分完全跨平台（pathlib / subprocess / urllib 都 OK）。
差异只在 wrapper。

## 设计原则

1. **零网络/服务**: 没有 HTTP server，没有数据库。CLI 直接调本地模块。
2. **唯一数据源**: `contests.csv` 是 ground truth, `docs/contests/*.md` 是详情, `git` 是 history。
3. **不上传代码**: 抓的代码缓存在 `~/.local/share/wiki/` (gitignored)。
4. **不存 token**: QOJ cookie 在 `~/.config/wiki/cookies/`, 写不进 repo。
5. **失败明确**: 抓取失败不静默, 错误详情打到 stderr。

## 文档索引

- [tools/API.md](tools/API.md) — CLI + Python API 详细参考
- [docs/TESTING.md](docs/TESTING.md) — 测试覆盖 + 怎么跑
- [需求.md](需求.md) — 起源 (原始需求)
- [docs/about.md](docs/about.md) — 关于页 (站点前端用)
