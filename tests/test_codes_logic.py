"""
tests/test_codes_logic.py

codes_logic.py 单元测试. 用 mock fetch_fn 跑完整流程.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from codes_logic import (  # noqa: E402
    FetchRequest, fetch_codes,
)
from codes_store import CodesStore  # noqa: E402
from platforms.qoj import QojClient, Submission  # noqa: E402
from watchlist import Watchlist  # noqa: E402


# === Mock 数据 ===

MOCK_SUBMISSIONS = [
    Submission(
        platform="qoj", submission_id="10001", user="tarjen",
        problem="A", verdict="AC", submitted_at="",
        contest_time_seconds=12*60, language="GNU C++17", code_length=1240,
    ),
    Submission(
        platform="qoj", submission_id="10002", user="tarjen",
        problem="D", verdict="WA", submitted_at="",
        contest_time_seconds=90*60, language="GNU C++17", code_length=1300,
    ),
    Submission(
        platform="qoj", submission_id="10003", user="alice",
        problem="A", verdict="AC", submitted_at="",
        contest_time_seconds=18*60, language="GNU C++17", code_length=1100,
    ),
    Submission(
        platform="qoj", submission_id="10004", user="alice",
        problem="B", verdict="AC", submitted_at="",
        contest_time_seconds=25*60, language="Python 3", code_length=892,
    ),
    Submission(
        platform="qoj", submission_id="10005", user="bob",
        problem="A", verdict="AC", submitted_at="",
        contest_time_seconds=24*60, language="GNU C++17", code_length=1300,
    ),
    Submission(
        platform="qoj", submission_id="10006", user="bob",
        problem="B", verdict="WA", submitted_at="",   # 非 AC, 跳过
        contest_time_seconds=99*60, language="GNU C++17", code_length=1300,
    ),
    Submission(
        platform="qoj", submission_id="10007", user="carol",
        problem="A", verdict="AC", submitted_at="",
        contest_time_seconds=10*60, language="GNU C++17", code_length=1503,
    ),
]


CODE_BODY = "// fake code for {user}/{problem}"


def make_factory():
    """构造返回 mock QojClient 的 factory."""
    def factory(platform):
        cookies = {"uoj_remember_token": "t", "uoj_remember_token_checksum": "c",
                   "UOJSESSID": "s"}
        client = QojClient(cookies=cookies, request_interval=0)

        def fetch_fn(url, cookie):
            if "/submissions" in url:
                return ""  # 不解析 HTML, 直接通过 get_user_submissions override
            if "/submission/" in url:
                # 提取 sid
                sid = url.rstrip("/").split("/")[-1]
                # 找对应 submission
                for s in MOCK_SUBMISSIONS:
                    if s.submission_id == sid:
                        return f'<pre class="code">{CODE_BODY.format(user=s.user, problem=s.problem)}</pre><div>Language: {s.language or "GNU C++17"}</div>'
                raise Exception(f"unknown sid {sid}")
            return "<html></html>"
        client._fetch_fn = fetch_fn
        # 直接覆盖 get_user_submissions 避免解析 HTML
        client.get_user_submissions = lambda cid, user: list(MOCK_SUBMISSIONS)
        return client
    return factory


def make_env():
    tmp = tempfile.TemporaryDirectory()
    return tmp, Path(tmp.name)


# === Tests ===

class TestFetchBasic(unittest.TestCase):
    def setUp(self):
        self.tmp_ctx, self.tmp = make_env()
        self.codes = CodesStore(self.tmp)
        self.watchlist = Watchlist(self.tmp / "watchlist.txt")
        self.watchlist.add(["alice", "bob"])

    def tearDown(self):
        self.tmp_ctx.cleanup()

    def test_basic(self):
        req = FetchRequest(
            platform="qoj", cid="2564", username="tarjen",
            request_interval=0,
        )
        result = fetch_codes(req, make_factory(), self.codes, self.watchlist)
        # tarjen A + D (WA), alice (watchlist) A + B, bob (watchlist) A, carol (sample) A
        # 总共 6 份
        self.assertEqual(result.fetched, 6)
        self.assertEqual(result.errors, 0)

        # 文件存在
        self.assertTrue(self.codes.exists("2564", "tarjen", "A"))
        self.assertTrue(self.codes.exists("2564", "tarjen", "D"))  # 自己 WA 也存
        self.assertTrue(self.codes.exists("2564", "alice", "A"))
        self.assertTrue(self.codes.exists("2564", "alice", "B"))
        self.assertTrue(self.codes.exists("2564", "bob", "A"))
        self.assertTrue(self.codes.exists("2564", "carol", "A"))

        # 自己的源码标记
        files = self.codes.list_files("2564")
        by_user = {f.user: f for f in files}
        self.assertEqual(by_user["tarjen"].source, "mine")
        self.assertEqual(by_user["alice"].source, "watchlist")
        self.assertEqual(by_user["bob"].source, "watchlist")
        self.assertEqual(by_user["carol"].source, "sample")

    def test_skip_existing(self):
        # 第一次抓
        req = FetchRequest(platform="qoj", cid="2564", username="tarjen",
                          request_interval=0)
        fetch_codes(req, make_factory(), self.codes, self.watchlist)

        # 第二次抓, 应该全跳过
        result = fetch_codes(req, make_factory(), self.codes, self.watchlist)
        self.assertEqual(result.fetched, 0)
        self.assertEqual(result.skipped_existing, 6)

    def test_no_skip_when_disabled(self):
        req = FetchRequest(platform="qoj", cid="2564", username="tarjen",
                          skip_existing=False, request_interval=0)
        fetch_codes(req, make_factory(), self.codes, self.watchlist)
        result = fetch_codes(req, make_factory(), self.codes, self.watchlist)
        # 第二次也全部重新抓 (覆盖)
        self.assertEqual(result.fetched, 6)

    def test_no_watchlist(self):
        req = FetchRequest(platform="qoj", cid="2564", username="tarjen",
                          fetch_watchlist=False, request_interval=0)
        result = fetch_codes(req, make_factory(), self.codes, self.watchlist)
        # 自己 (A, D) + others (alice A, alice B, bob A, carol A 进 others)
        # others_n=1 默认, A 取最早 (carol 10min), B 取 1 个 (alice) = 2
        # 总共 2 + 2 = 4
        self.assertEqual(result.fetched, 4)
        # alice A 不在 (因为 carol 更快), alice B 在 (B 题只有 alice)
        self.assertFalse(self.codes.exists("2564", "alice", "A"))
        self.assertTrue(self.codes.exists("2564", "alice", "B"))

    def test_no_others(self):
        req = FetchRequest(platform="qoj", cid="2564", username="tarjen",
                          fetch_others="none", request_interval=0)
        result = fetch_codes(req, make_factory(), self.codes, self.watchlist)
        # 自己 + watchlist = 5 (tarjen A+D, alice A+B, bob A)
        self.assertEqual(result.fetched, 5)
        self.assertFalse(self.codes.exists("2564", "carol", "A"))

    def test_others_n(self):
        req = FetchRequest(platform="qoj", cid="2564", username="tarjen",
                          fetch_others="top_n_fastest", others_n=2,
                          request_interval=0)
        result = fetch_codes(req, make_factory(), self.codes, self.watchlist)
        # mine (2) + watchlist AC (3) + others top_n=2 from carol (1, 因为 carol 只有 A 一份)
        # = 2 + 3 + 1 = 6
        self.assertEqual(result.fetched, 6)
        # carol 在 others 里只有 A
        self.assertTrue(self.codes.exists("2564", "carol", "A"))

    def test_filter_by_problems(self):
        req = FetchRequest(platform="qoj", cid="2564", username="tarjen",
                          problems=["A"], request_interval=0)
        result = fetch_codes(req, make_factory(), self.codes, self.watchlist)
        # 只抓 A 题: tarjen A, alice A, bob A, carol A = 4
        self.assertEqual(result.fetched, 4)
        self.assertFalse(self.codes.exists("2564", "tarjen", "D"))
        self.assertFalse(self.codes.exists("2564", "alice", "B"))


class TestTaskManagement(unittest.TestCase):
    def test_create_and_get(self):
        from codes_logic import create_task, get_task, list_tasks
        t = create_task("2564")
        self.assertEqual(t.cid, "2564")
        self.assertEqual(t.status, "started")
        self.assertIsNotNone(get_task(t.task_id))
        self.assertIn(t, list_tasks())

    def test_get_missing(self):
        from codes_logic import get_task
        self.assertIsNone(get_task("nonexistent"))


if __name__ == "__main__":
    unittest.main()