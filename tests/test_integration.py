"""
tests/test_integration.py

端到端集成测试: 模拟 "每天 wiki update 2564" 完整流程, 直接调各模块.

不连真实 QOJ (用 fetch_fn 注入), 但其他一切都是真的:
  - 真 git repo (本地 + bare remote)
  - 真 CSV 文件读写
  - 真 md 文件
  - 真 cookie jar 文件

测试流程 (test_01_daily_workflow 走完整个流程):
  1. 直接 init stores
  2. update-preview (赛时数据)
  3. update-apply -> CSV + md + commit + push
  4. 验证 (CSV 内容 / md 存在 / git log / remote 收到)
  5. upsolve-preview (赛后数据)
  6. upsolve-apply -> 更新 CSV
  7. 最终状态检查
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


CONTEST_HTML = """
<html><body>
<h1>2025 ICPC XXX Regional</h1>
<div>Start: 2025-06-07 08:00:00 End: 2025-06-07 13:00:00</div>
<ul>
  <li><a href="/contest/2564/problem/A">A</a></li>
  <li><a href="/contest/2564/problem/B">B</a></li>
  <li><a href="/contest/2564/problem/C">C</a></li>
</ul>
</body></html>
"""

# Standings 页 mock — 用真实 QOJ 的 JS 数据格式 (score + standings arrays).
# Tarjen 在 A 一次过 (AC 12:34), B 一次 WA, C 两次 WA (第二次也失败).
STANDINGS_HTML = """
<html><body>
<script>
standings_version=2;
standings=[[100,754,["tarjen",1500,2,"tarjen","rgb(0,0,0)",1,""],1,100.0]];
fullscore=300;
score={"tarjen":{"0":[100,754,10001,0,100,0,[]],"1":[0,0,10002,1,100,0,[0]],"2":[0,0,10003,2,100,0,[0]]}};
problems=[100,200,300];
my_name="tarjen";
</script>
</body></html>
"""

# 赛中提交 (周六 2025-06-07): A AC, B WA, C WA, D WA
IN_CONTEST_SUBS = """
<html><body><table>
<tr>
  <td><a href="/submission/10001">10001</a></td>
  <td><a href="/contest/2564/problem/A">A</a></td>
  <td><a href="/user/profile/tarjen">tarjen</a></td>
  <td>AC</td>
  <td>0:12:34</td>
  <td>1024 KB</td>
  <td>GNU C++17</td>
  <td>1240</td>
</tr>
<tr>
  <td><a href="/submission/10002">10002</a></td>
  <td><a href="/contest/2564/problem/B">B</a></td>
  <td><a href="/user/profile/tarjen">tarjen</a></td>
  <td>WA</td>
  <td>0:30:00</td>
  <td>1024 KB</td>
  <td>GNU C++17</td>
  <td>1300</td>
</tr>
<tr>
  <td><a href="/submission/10003">10003</a></td>
  <td><a href="/contest/2564/problem/C">C</a></td>
  <td><a href="/user/profile/tarjen">tarjen</a></td>
  <td>WA</td>
  <td>1:30:00</td>
  <td>1024 KB</td>
  <td>GNU C++17</td>
  <td>1500</td>
</tr>
<tr>
  <td><a href="/submission/10004">10004</a></td>
  <td><a href="/contest/2564/problem/D">D</a></td>
  <td><a href="/user/profile/tarjen">tarjen</a></td>
  <td>WA</td>
  <td>2:00:00</td>
  <td>1024 KB</td>
  <td>GNU C++17</td>
  <td>1700</td>
</tr>
</table></body></html>
"""

# 赛后提交 (周一开始): C AC (补过), D WA (继续尝试)
POST_CONTEST_SUBS = """
<html><body><table>
<tr>
  <td><a href="/submission/20001">20001</a></td>
  <td><a href="/contest/2564/problem/C">C</a></td>
  <td><a href="/user/profile/tarjen">tarjen</a></td>
  <td>AC</td>
  <td>2025-06-09 22:14:00</td>
  <td>1024 KB</td>
  <td>GNU C++17</td>
  <td>1500</td>
</tr>
<tr>
  <td><a href="/submission/20002">20002</a></td>
  <td><a href="/contest/2564/problem/D">D</a></td>
  <td><a href="/user/profile/tarjen">tarjen</a></td>
  <td>WA</td>
  <td>2025-06-10 15:00:00</td>
  <td>1024 KB</td>
  <td>GNU C++17</td>
  <td>1700</td>
</tr>
</table></body></html>
"""


def setup_test_env() -> dict:
    """建临时 git repo + cookie + bare remote."""
    tmp = tempfile.mkdtemp()
    tmp_path = Path(tmp)
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    remote.mkdir()

    subprocess.run(["git", "init", "--bare", str(remote)], check=True,
                   capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"],
                   check=True, capture_output=True)

    (repo / "contests.csv").write_text(
        "slug,name,date,solved,total,problems,link,tags\n", encoding="utf-8",
    )
    (repo / "docs").mkdir()
    (repo / "docs" / "contests").mkdir()
    (repo / "tools").mkdir()

    subprocess.run(["git", "-C", str(repo), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "push", "-u", "origin", "main"],
                   check=True, capture_output=True)

    cfg = tmp_path / "cfg"
    (cfg / "cookies").mkdir(parents=True)
    (cfg / "cookies" / "qoj.txt").write_text(
        ".qoj.ac\tTRUE\t/\tFALSE\t0\tuoj_remember_token\tT\n"
        ".qoj.ac\tTRUE\t/\tFALSE\t0\tuoj_remember_token_checksum\tC\n"
        ".qoj.ac\tTRUE\t/\tFALSE\t0\tUOJSESSID\tS\n",
        encoding="utf-8",
    )

    return {"tmp_root": Path(tmp), "repo": repo, "cfg": cfg, "remote": remote}


def make_mock_factory():
    """返回 (mock_make_client, set_subs_html)."""
    from platforms.qoj import QojClient

    def mock_make_client(platform, config_dir):
        cookies = {"uoj_remember_token": "T", "uoj_remember_token_checksum": "C",
                   "UOJSESSID": "S"}
        client = QojClient(cookies=cookies, request_interval=0)

        def fetch_fn(url, cookie):
            if "/standings" in url:
                return STANDINGS_HTML
            if "/submissions" in url:
                return mock_make_client.current_subs_html[0]
            if "/submission/" in url:
                sid = url.rstrip("/").split("/")[-1]
                return f'<pre class="code">// code {sid}</pre><div>Language: GNU C++17</div>'
            if "/contest/" in url:
                return CONTEST_HTML
            raise Exception(f"unexpected URL: {url}")
        client._fetch_fn = fetch_fn
        return client

    mock_make_client.current_subs_html = [IN_CONTEST_SUBS]
    return mock_make_client


class IntegrationBase(unittest.TestCase):
    """所有 store 一次性 init, 子测试共享 state."""

    @classmethod
    def setUpClass(cls):
        cls.env = setup_test_env()
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from csv_store import CsvStore
        from md_store import MdStore
        from git_ops import GitOps
        import import_logic

        # 保存原始, tearDown 恢复
        cls._orig_make_client = import_logic.make_client

        # 注入 mock
        mock_make_client = make_mock_factory()
        import_logic.make_client = mock_make_client
        cls._mock_make_client = mock_make_client

        cls.csv = CsvStore(cls.env["repo"] / "contests.csv")
        cls.csv.load()
        cls.md = MdStore(cls.env["repo"] / "docs" / "contests")
        cls.git = GitOps(cls.env["repo"])

    @classmethod
    def tearDownClass(cls):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        import import_logic
        import_logic.make_client = cls._orig_make_client
        shutil.rmtree(cls.env["tmp_root"], ignore_errors=True)


class TestDailyWorkflow(IntegrationBase):
    """完整 daily workflow: 比赛日 import + 几天后 upsolve. 直接调 import_logic."""

    def test_01_empty_state(self):
        self.assertEqual(len(self.csv), 0)
        self.assertTrue(self.git.status().clean)

    def test_02_update_preview(self):
        """比赛日: 调 build_update_preview."""
        from import_logic import build_update_preview
        preview = build_update_preview(
            platform="qoj", contest_id="2564", user="tarjen",
            csv_store=self.csv, config_dir=self.env["cfg"],
        )
        self.assertEqual(preview.record_state, "create_new")
        self.assertEqual(preview.slug, "2025-icpc-xxx-regional")
        self.assertEqual(preview.contest["title"], "2025 ICPC XXX Regional")
        self.assertEqual(len(preview.problems), 3)
        self.assertEqual(preview.problems[0]["status"], "O")  # A AC
        self.assertEqual(preview.problems[1]["status"], "!")  # B WA
        self.assertEqual(preview.problems[2]["status"], "!")  # C WA
        self.assertEqual(preview.summary, {"O": 1, "!": 2, "Ø": 0, ".": 0})

    def test_03_update_apply(self):
        """比赛日: apply -> CSV + md + commit + push."""
        from import_logic import build_update_preview, apply_update
        preview = build_update_preview(
            platform="qoj", contest_id="2564", user="tarjen",
            csv_store=self.csv, config_dir=self.env["cfg"],
        )
        result = apply_update(
            preview=preview, csv_store=self.csv, md_store=self.md,
            git_ops=self.git, create_body=True, run_sync=False, push=True,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.record_state, "create_new")
        self.assertEqual(result.slug, "2025-icpc-xxx-regional")
        self.assertTrue(result.csv_written)
        self.assertIsNotNone(result.body_written)
        self.assertTrue(result.committed)
        self.assertTrue(result.pushed)

        # 验证 CSV
        csv_text = (self.env["repo"] / "contests.csv").read_text(encoding="utf-8")
        self.assertIn("2025-icpc-xxx-regional", csv_text)
        self.assertIn("O;!;!", csv_text)

        # 验证 md 详情页
        md_path = (self.env["repo"] / "docs" / "contests"
                   / "2025-icpc-xxx-regional.md")
        self.assertTrue(md_path.exists())
        self.assertIn("2025 ICPC XXX Regional",
                      md_path.read_text(encoding="utf-8"))

        # 验证 git log
        log = subprocess.run(
            ["git", "-C", str(self.env["repo"]), "log", "--oneline"],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("add(2025-icpc-xxx-regional)", log.stdout)

        # 验证 remote 收到
        remote_log = subprocess.run(
            ["git", "-C", str(self.env["remote"]), "log", "--oneline"],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("add(2025-icpc-xxx-regional)", remote_log.stdout)

    def test_04_show_after_update(self):
        c = self.csv.get("2025-icpc-xxx-regional")
        self.assertIsNotNone(c)
        self.assertEqual(c.solved, 1)
        self.assertEqual(c.in_contest_solved, 1)
        self.assertEqual(c.upsolved, 0)
        self.assertEqual(c.problems, ["O", "!", "!"])
        self.assertTrue(self.md.exists("2025-icpc-xxx-regional"))

    def test_05_upsolve_preview(self):
        """几天后: 切换 mock 到赛后数据, 跑 upsolve-preview."""
        self._mock_make_client.current_subs_html[0] = POST_CONTEST_SUBS
        from import_logic import build_upsolve_preview
        preview = build_upsolve_preview(
            platform="qoj", contest_id="2564", slug=None, user="tarjen",
            csv_store=self.csv, config_dir=self.env["cfg"],
        )
        self.assertEqual(preview.slug, "2025-icpc-xxx-regional")
        self.assertEqual(preview.current_problems, ["O", "!", "!"])
        self.assertEqual(len(preview.changes), 1)
        ch = preview.changes[0]
        self.assertEqual(ch["letter"], "C")
        self.assertEqual(ch["before"], "!")
        self.assertEqual(ch["after"], "Ø")
        self.assertEqual(preview.summary["upsolved"], 0)
        self.assertEqual(preview.summary["upsolved_from_bang"], 1)

    def test_06_upsolve_apply(self):
        self._mock_make_client.current_subs_html[0] = POST_CONTEST_SUBS
        from import_logic import build_upsolve_preview, apply_upsolve
        preview = build_upsolve_preview(
            platform="qoj", contest_id="2564", slug=None, user="tarjen",
            csv_store=self.csv, config_dir=self.env["cfg"],
        )
        result = apply_upsolve(
            preview=preview, csv_store=self.csv, md_store=self.md,
            git_ops=self.git, push=True,
        )
        self.assertEqual(result.slug, "2025-icpc-xxx-regional")
        self.assertEqual(result.problems_before, ["O", "!", "!"])
        self.assertEqual(result.problems_after, ["O", "!", "Ø"])
        self.assertTrue(result.committed)

        csv_text = (self.env["repo"] / "contests.csv").read_text(encoding="utf-8")
        self.assertIn("O;!;Ø", csv_text)

    def test_07_final_state(self):
        c = self.csv.get("2025-icpc-xxx-regional")
        self.assertEqual(c.problems, ["O", "!", "Ø"])
        self.assertEqual(c.solved, 2)
        self.assertEqual(c.in_contest_solved, 1)
        self.assertEqual(c.upsolved, 1)
        self.assertTrue(self.git.status().clean)


class TestFetchCodesE2E(IntegrationBase):
    """端到端 fetch_codes: 用真实 QOJ fixture 跑完整抓代码流程.

    fixtures 来自 tests/fixtures/qoj_real/ (300iq Contest 2 / contest 1357).
    走 fetch_codes 全流程, 验证:
      - 题目列表 (get_problem_letters) 走 fixture 拿到
      - 自己 + watchlist + samples 三池合并, watchlist 优先
      - 代码写到 CodesStore (新结构: <platform>/<cid>/<problem>/<user>.<ext>)
      - source 标记正确 (mine / watchlist / sample)
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixtures = REPO_ROOT / "tests" / "fixtures" / "qoj_real"
        cls.contest_html = (cls.fixtures / "contest_1357.html").read_text(encoding="utf-8")
        cls.standings_html = (cls.fixtures / "standings_1357.html").read_text(encoding="utf-8")
        cls.submission_html = (cls.fixtures / "submission_1336269.html").read_text(encoding="utf-8")

    def _make_factory(self):
        """返回 fetch_fn 走 fixture 的 client 工厂."""
        from platforms.qoj import QojClient

        def fetch_fn(url, cookie):
            if url.endswith("/contest/1357"):
                return self.contest_html
            if url.endswith("/contest/1357/standings"):
                return self.standings_html
            if url.startswith("/submission/"):
                return self.submission_html
            return "<html></html>"

        def factory(platform):
            client = QojClient(
                cookies={"uoj_remember_token": "T",
                         "uoj_remember_token_checksum": "C",
                         "UOJSESSID": "S"},
                request_interval=0,
            )
            client._fetch_fn = fetch_fn
            return client
        return factory

    def _setup_codes_store(self):
        """建独立 codes 目录 (避免污染)."""
        from codes_store import CodesStore, ensure_gitignore
        codes_root = Path(tempfile.mkdtemp()) / "codes"
        ensure_gitignore(codes_root)
        return CodesStore(codes_root)

    def _setup_watchlist(self, *users):
        from watchlist import Watchlist
        wl = Watchlist(Path(tempfile.mkdtemp()) / "watchlist.txt")
        wl.add(list(users))
        return wl

    def test_full_flow_default(self):
        """wiki codes 1357  (默认: 自己全 + watchlist + 5 samples/题)."""
        from codes_logic import FetchRequest, fetch_codes
        codes = self._setup_codes_store()
        wl = self._setup_watchlist("cyp063")  # fixture 里有这个用户的提交
        result = fetch_codes(
            FetchRequest(platform="qoj", cid="1357", username="tarjen",
                        request_interval=0),
            self._make_factory(), codes, wl,
        )
        # 走通 + 至少有一些 fetched
        self.assertEqual(result.errors, 0)
        self.assertGreater(result.fetched, 0)
        # source 标记三类都有
        by_src = {f["source"] for f in result.files}
        self.assertIn("mine", by_src)
        self.assertIn("sample", by_src)
        # 文件实际落盘 (新结构: qoj/1357/<prob>/<user>.<ext>)
        files = codes.list_files("qoj", "1357")
        self.assertEqual(len(files), result.fetched)
        for f in files:
            p = Path(codes.root) / "qoj" / "1357" / f.problem / f"{f.user}.cpp"
            self.assertTrue(p.exists(), f"missing {p}")
            self.assertGreater(p.stat().st_size, 50)  # 不是空

    def test_single_problem(self):
        """wiki codes 1357 --problem B  (单 problem fetch)."""
        from codes_logic import FetchRequest, fetch_codes
        codes = self._setup_codes_store()
        wl = self._setup_watchlist("cyp063")
        result = fetch_codes(
            FetchRequest(platform="qoj", cid="1357", username="tarjen",
                        problems=["B"], request_interval=0),
            self._make_factory(), codes, wl,
        )
        self.assertEqual(result.errors, 0)
        # 只抓 B 题
        files = codes.list_files("qoj", "1357", problem="B")
        self.assertGreater(len(files), 0)
        all_problems = {f.problem for f in codes.list_files("qoj", "1357")}
        self.assertEqual(all_problems, {"B"})

    def test_samples_cap(self):
        """wiki codes 1357 --samples 2  (cap 生效)."""
        from codes_logic import FetchRequest, fetch_codes
        codes = self._setup_codes_store()
        wl = self._setup_watchlist()
        result = fetch_codes(
            FetchRequest(platform="qoj", cid="1357", username="tarjen",
                        samples_per_problem=2, request_interval=0),
            self._make_factory(), codes, wl,
        )
        self.assertEqual(result.errors, 0)
        # 每题 watchlist+others 池上限 2 — 验证
        files = codes.list_files("qoj", "1357")
        from collections import Counter
        per_problem = Counter(f.problem for f in files if f.source != "mine")
        for prob, n in per_problem.items():
            self.assertLessEqual(n, 2, f"题 {prob} 非 mine 数量 {n} 超过 cap=2")

    def test_url_helpers(self):
        """PlatformClient URL 助手 — QOJ 实例."""
        c = self._make_factory()("qoj")
        self.assertEqual(c.contest_url("1357"), "https://qoj.ac/contest/1357")
        self.assertEqual(c.standings_url("1357"),
                         "https://qoj.ac/contest/1357/standings")
        self.assertEqual(c.problem_url("1357", "A"),
                         "https://qoj.ac/contest/1357/problem/A")
        self.assertEqual(c.submission_url("1336269"),
                         "https://qoj.ac/submission/1336269")
        # get_problem_letters 走 fixture 拿真实字母列表
        letters = c.get_problem_letters("1357")
        self.assertGreater(len(letters), 0)
        self.assertEqual(letters[0], "A")

    def test_legacy_others_n_warning(self):
        """FetchRequest.others_n 仍能工作, 触发 DeprecationWarning + 转发."""
        import warnings
        from codes_logic import FetchRequest
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            req = FetchRequest(platform="qoj", cid="1357", username="tarjen",
                              others_n=3, request_interval=0)
            self.assertTrue(any(
                issubclass(w.category, DeprecationWarning)
                and "others_n" in str(w.message)
                for w in caught
            ))
            self.assertEqual(req.samples_per_problem, 3)


class TestErrorPaths(IntegrationBase):
    """错误路径 (独立测试, 不依赖 TestDailyWorkflow 的状态)."""

    def test_get_nonexistent(self):
        self.assertIsNone(self.csv.get("nonexistent"))

    def test_add_invalid_problems_length(self):
        from csv_store import Contest, CsvValidationError
        c = Contest("x", "X", "2025.1.1", 0, 5,
                   ["O", "."], "", "")
        with self.assertRaises(CsvValidationError):
            self.csv.add(c)

    def test_add_invalid_slug(self):
        from csv_store import Contest, CsvValidationError
        c = Contest("BAD SLUG", "X", "2025.1.1", 0, 1, ["."], "", "")
        with self.assertRaises(CsvValidationError):
            self.csv.add(c)


if __name__ == "__main__":
    unittest.main()