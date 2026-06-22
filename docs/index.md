# 比赛记录

记录每一场比赛的练习情况。点击比赛名可查看题解。

## 图例

- `O` = 赛中过题
- `Ø` = 赛后补过
- `!` = 尝试没过
- `.` = 未做

## 全部比赛

<!-- SYNC:CONTESTS-START -->
| 比赛 | 日期 | 题数 |  | A | B | C | D | E | F | G | H | I | J | K | L | M |
|:-----|:----:|:----:|:---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| [2026 年山东省大学生程序设计竞赛](contests/2026.md) | 2026.06.22 | 0/0/13 | [✎](editor/?slug=2026&_t=4679a9) | . | . | . | . | . | . | . | . | . | . | . | . | . |
| [2026 年山东省大学生程序设计竞赛](contests/2026-shandong-provincial-collegiate-programming-contest.md) | 2026.06.22 | 7/7/13 | [✎](editor/?slug=2026-shandong-provincial-collegiate-programming-contest&_t=4679a9) | O | . | O | . | O | . | O | . | O | . | O | O | . |
| [The 2019 Polish Collegiate Programming Contest (AMPPZ 2019)](contests/2026-the-2019-polish-collegiate-programming-contest-amppz-2019.md) | 2026.06.19 | 5/5/12 | [✎](editor/?slug=2026-the-2019-polish-collegiate-programming-contest-amppz-2019&_t=4679a9) | O | . | O | O | . | O | . | O | . | . | . | . |  |
<!-- SYNC:CONTESTS-END -->

## 统计

- 累计场次：<!-- SYNC:COUNT -->3<!-- /SYNC:COUNT -->
- 累计通过：约 <!-- SYNC:SOLVED -->12<!-- /SYNC:SOLVED --> 题

## 维护说明

### 最快：网页编辑器（点一下保存到 GitHub）

打开 [/editor/](editor/)，或点表格里比赛名右边的 **✎** 直接进编辑模式。

1. 填比赛名、日期、题目总数
2. 点格子循环切状态：**未做 → O（赛中过题）→ Ø（赛后补过）→ !（尝试没过）→ 未做**
3. 滚到底部「💾 保存修改」面板
4. **首次用**：点「⚙ GitHub Token 配置」生成 fine-grained PAT（仓库选 `tarjen/tarjen-wiki`，权限只勾 Contents: Read and write），粘进去点保存（明文存 localStorage，不上传服务器）
5. 之后每次：点 **💾 保存到 GitHub** 就直接 PUT 到 `contests.csv`，完事

配了 GitHub Actions 自动跑 `mkdocs build + gh-deploy` 的话，commit 完几秒后刷新页面就能看到新表。

「题数」列里的 `9/9/14` 含义：**赛时+补题=9**，**赛时过题=9**，**总题数=14**。
底部三段统计卡也会同步：赛时+补题 / 赛时过题 / 总题数。

### 从 QOJ 一键导入

打开 [editor/?view=table](editor/?view=table)，滚到「📥 从 QOJ 导入」卡片：

1. 粘 QOJ 比赛链接（如 `https://qoj.ac/contest/2564` 或只填 `2564`）
2. 填 QOJ 用户名（如 `tarjen`）
3. 点「📥 导入」—— 浏览器**一按就自己 fetch qoj.ac**，几秒出预览
4. 看一眼映射：AC + 赛中 → `O`，AC + 赛后 → `Ø`，WA/TLE/RE → `!`，没提交 → `.`
5. 点「✅ 填入表单」→ 编辑器填好 → 自己再点格子微调 → 「💾 保存到 GitHub」

整个过程在**你家浏览器**里跑，Cloudflare 信任家用 IP，不被卡。**不依赖 GitHub Actions**。

**前置条件 1：QOJ cookie**（只一次）：

打开 [qoj.ac](https://qoj.ac) 登录 → F12 → Application → Cookies → `qoj.ac` → 逐个点开 `uoj_remember_token` / `uoj_remember_token_checksum` / `UOJSESSID` → Value 列复制 → 在编辑器「🍪 QOJ Cookie」3 个对应输入框里分别粘进去 → 点保存（存浏览器 localStorage）。

> cookie 过期了（一般 7–30 天）再来更新一次。

**前置条件 2：CORS 扩展**（只一次）：

qoj.ac 没设 CORS 头，浏览器默认拒掉跨域 response。装个 [Allow CORS](https://chromewebstore.google.com/search/CORS) 类扩展，对 `qoj.ac` enable，刷新本页面。

**没反应 / 报 CORS 错**：去「🍪 QOJ Cookie」检查 cookie 是不是过期了；CORS 扩展是否对 qoj.ac enable。

如果哪天 CF 升级把 `/results/QOJ{cid}` 也卡了，**cache entry 会加 `cf_blocked: true` 标记**——编辑器看到后告诉你要手动点格子。

### 直接改仓库

适合想用本地编辑器/脚本批量改、或习惯 git 工作流的人：

1. `git clone git@github.com:tarjen/tarjen-wiki.git`（或 HTTPS）
2. `./bootstrap.sh` — 装 venv + 依赖；带 `--serve` 直接起本地预览
3. 改源文件：
   - [contests.csv](https://github.com/tarjen/tarjen-wiki/blob/main/contests.csv) — 加新比赛就补一行，`problems` 列写 `O/Ø/!/.` 分号分隔，日期用 `2024.11.24` 这种点分格式
   - `docs/contests/<slug>.md` — 写题解
4. `python3 tools/sync.py` — 重新生成上方表格、`docs/data/contests.json`、统计数据；**只**给 CSV 里新增的 slug 创建空的详情页
5. `git add . && git commit -m "..." && git push`

GitHub Actions 自动 `mkdocs build + gh-deploy`，几秒后刷新生效。

> 表格在 `<!-- SYNC:CONTESTS-START/END -->` 标记之间，是 `sync.py` 生成的，**别手改**，下次跑 sync 会被覆盖。
