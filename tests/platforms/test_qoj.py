"""
tests/platforms/test_qoj.py

qoj.py 单元测试 (用录制的 HTML fixture).

QOJ 没公开 API, 解析靠正则, 极易因改版失效。
fixtures 在 tests/fixtures/qoj/ 下, 跑测试前由人手维护。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from platforms.qoj import (  # noqa: E402
    QojClient,
    cookie_header,
    html_unescape,
    parse_contest_time,
    parse_netscape_cookies,
    strip_tags,
)
from platforms.base import (  # noqa: E402
    CFBlockedError, CookieExpiredError, NotFoundError, ParseError,
)


FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "qoj"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# === Cookie 解析 ===

class TestParseNetscapeCookies(unittest.TestCase):
    def test_basic(self):
        text = (
            "# Netscape HTTP Cookie File\n"
            ".qoj.ac\tTRUE\t/\tFALSE\t1924958400\tuoj_remember_token\tabc123\n"
            ".qoj.ac\tTRUE\t/\tFALSE\t1924958400\tUOJSESSID\txyz789\n"
        )
        cookies = parse_netscape_cookies(text)
        self.assertEqual(cookies["uoj_remember_token"], "abc123")
        self.assertEqual(cookies["UOJSESSID"], "xyz789")

    def test_ignore_other_domains(self):
        text = (
            ".other.com\tTRUE\t/\tFALSE\t0\tfoo\tbar\n"
            ".qoj.ac\tTRUE\t/\tFALSE\t0\ttoken\ttoken_value\n"
        )
        cookies = parse_netscape_cookies(text)
        self.assertIn("token", cookies)
        self.assertNotIn("foo", cookies)

    def test_skip_comments(self):
        text = "# this is a comment\n\n.qoj.ac\tTRUE\t/\tFALSE\t0\ttoken\tval\n"
        cookies = parse_netscape_cookies(text)
        self.assertEqual(len(cookies), 1)

    def test_empty(self):
        self.assertEqual(parse_netscape_cookies(""), {})


class TestCookieHeader(unittest.TestCase):
    def test_basic(self):
        h = cookie_header({"a": "1", "b": "2"})
        self.assertIn("a=1", h)
        self.assertIn("b=2", h)


class TestHtmlUnescape(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(html_unescape("&lt;a&gt;"), "<a>")

    def test_quotes(self):
        self.assertEqual(html_unescape("&quot;hi&quot;"), '"hi"')

    def test_amp(self):
        self.assertEqual(html_unescape("a &amp; b"), "a & b")


class TestStripTags(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(strip_tags("<b>hi</b>"), "hi")
        self.assertEqual(strip_tags("a<br>b"), "ab")


class TestParseContestTime(unittest.TestCase):
    def test_hms(self):
        self.assertEqual(parse_contest_time("1:23:45"), 3600 + 23*60 + 45)

    def test_ms(self):
        self.assertEqual(parse_contest_time("23:45"), 23*60 + 45)

    def test_seconds(self):
        self.assertEqual(parse_contest_time("90"), 90)

    def test_invalid(self):
        self.assertIsNone(parse_contest_time("abc"))


# === QojClient ===

def make_client(html_responses: dict[str, str]) -> QojClient:
    """构造一个用 mock fetch_fn 的 client.

    html_responses: {path_or_url: html_body}
    """
    def fetch_fn(url: str, cookie_str: str) -> str:
        for key, body in html_responses.items():
            if key in url:
                return body
        raise NotFoundError(f"no mock for {url}")
    return QojClient(
        cookies={
            "uoj_remember_token": "t",
            "uoj_remember_token_checksum": "c",
            "UOJSESSID": "s",
        },
        request_interval=0,  # 测试不要 sleep
        fetch_fn=fetch_fn,
    )


class TestQojClientCookiesValid(unittest.TestCase):
    def test_valid(self):
        c = QojClient(cookies={
            "uoj_remember_token": "t",
            "uoj_remember_token_checksum": "c",
            "UOJSESSID": "s",
        })
        self.assertTrue(c.cookies_valid())

    def test_missing_token(self):
        c = QojClient(cookies={"UOJSESSID": "s"})
        self.assertFalse(c.cookies_valid())

    def test_missing_checksum(self):
        c = QojClient(cookies={"uoj_remember_token": "t", "UOJSESSID": "s"})
        self.assertFalse(c.cookies_valid())

    def test_missing_session(self):
        c = QojClient(cookies={
            "uoj_remember_token": "t", "uoj_remember_token_checksum": "c",
        })
        self.assertFalse(c.cookies_valid())

    def test_empty(self):
        c = QojClient(cookies={})
        self.assertFalse(c.cookies_valid())


class TestFetchLoginDetection(unittest.TestCase):
    def test_login_page_detected(self):
        body = '<html><body>请先登录<a href="/login">login</a></body></html>'
        self.assertTrue(QojClient._is_login_page(body))

    def test_normal_page(self):
        body = '<html><body><h1>Contest Title</h1>...</body></html>'
        self.assertFalse(QojClient._is_login_page(body))

    def test_cf_challenge_detected(self):
        body = '<html><head><title>Just a moment...</title></head></html>'
        self.assertTrue(QojClient._is_cf_challenge(body))


class TestParseContestMeta(unittest.TestCase):
    """解析比赛页 HTML. 用 fixture (或手写 HTML)."""

    HTML = """
    <html>
    <head><title>Contest 2564</title></head>
    <body>
    <h1>2025 ICPC XXX Regional</h1>
    <div>Start: 2025-06-07 08:00:00 End: 2025-06-07 13:00:00</div>
    <ul>
      <li><a href="/contest/2564/problem/A">A</a></li>
      <li><a href="/contest/2564/problem/B">B</a></li>
      <li><a href="/contest/2564/problem/C">C</a></li>
    </ul>
    </body>
    </html>
    """

    def test_basic(self):
        c = make_client({"/contest/2564": self.HTML})
        meta = c.get_contest_meta("2564")
        self.assertEqual(meta.platform, "qoj")
        self.assertEqual(meta.contest_id, "2564")
        self.assertEqual(meta.title, "2025 ICPC XXX Regional")
        self.assertEqual(meta.problem_count, 3)
        self.assertIn("2025-06-07 08:00:00", meta.start_time)
        self.assertIn("2025-06-07 13:00:00", meta.end_time)

    def test_missing_title_raises(self):
        c = make_client({"/contest/2564": "<html><body>no title</body></html>"})
        with self.assertRaises(ParseError):
            c.get_contest_meta("2564")

    def test_missing_problems_raises(self):
        html = "<html><body><h1>Title</h1></body></html>"
        c = make_client({"/contest/2564": html})
        with self.assertRaises(ParseError):
            c.get_contest_meta("2564")


class TestParseSubmissions(unittest.TestCase):
    """解析提交列表 HTML."""

    HTML = """
    <html><body><table>
    <tr>
      <th>ID</th><th>Problem</th><th>User</th><th>Verdict</th>
      <th>Time</th><th>Memory</th><th>Language</th><th>Length</th>
    </tr>
    <tr>
      <td><a href="/submission/12345">12345</a></td>
      <td><a href="/contest/2564/problem/A">A</a></td>
      <td><a href="/user/profile/tarjen">tarjen</a></td>
      <td>AC</td>
      <td>0:12:34</td>
      <td>1024 KB</td>
      <td>GNU C++17</td>
      <td>1240</td>
    </tr>
    <tr>
      <td><a href="/submission/12346">12346</a></td>
      <td><a href="/contest/2564/problem/B">B</a></td>
      <td><a href="/user/profile/tarjen">tarjen</a></td>
      <td>WA</td>
      <td>0:30:00</td>
      <td>1024 KB</td>
      <td>GNU C++17</td>
      <td>1300</td>
    </tr>
    </table></body></html>
    """

    def test_basic(self):
        c = make_client({"/contest/2564/submissions": self.HTML})
        subs = c.get_user_submissions("2564", "tarjen")
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0].submission_id, "12345")
        self.assertEqual(subs[0].problem, "A")
        self.assertEqual(subs[0].user, "tarjen")
        self.assertEqual(subs[0].verdict, "AC")
        self.assertEqual(subs[0].contest_time_seconds, 12*60 + 34)
        self.assertEqual(subs[0].language, "GNU C++17")
        self.assertEqual(subs[0].code_length, 1240)

    def test_empty_page(self):
        c = make_client({"/contest/2564/submissions": "<html><body>empty</body></html>"})
        subs = c.get_user_submissions("2564", "tarjen")
        self.assertEqual(subs, [])

    def test_pagination_terminates(self):
        # 单页 < 50 条就停, 不再请求第二页
        c = make_client({"/contest/2564/submissions": self.HTML})
        subs = c.get_user_submissions("2564", "tarjen")
        self.assertEqual(len(subs), 2)  # 没有 page=2 请求


class TestParseCode(unittest.TestCase):
    HTML = """
    <html><body>
    <div>Language: GNU C++17</div>
    <pre class="code">#include &lt;iostream&gt;
int main() {
    std::cout &lt;&lt; "hi" &lt;&lt; std::endl;
    return 0;
}</pre>
    </body></html>
    """

    def test_basic(self):
        c = make_client({"/submission/12345": self.HTML})
        code, lang = c.get_submission_code("12345")
        self.assertIn("#include", code)
        self.assertIn("std::cout", code)
        self.assertEqual(lang, "GNU C++17")

    def test_missing_code_raises(self):
        html = "<html><body>no code</body></html>"
        c = make_client({"/submission/12345": html})
        with self.assertRaises(ParseError):
            c.get_submission_code("12345")


class TestFetchErrors(unittest.TestCase):
    def test_401_raises_cookie_expired(self):
        def fetch_fn(url, cookie):
            raise CookieExpiredError("HTTP 401")
        c = QojClient(cookies={"uoj_remember_token": "t",
                              "uoj_remember_token_checksum": "c",
                              "UOJSESSID": "s"},
                     fetch_fn=fetch_fn)
        with self.assertRaises(CookieExpiredError):
            c.get_contest_meta("2564")

    def test_login_page_raises_cookie_expired(self):
        def fetch_fn(url, cookie):
            return '<html>请先登录</html>'
        c = QojClient(cookies={"uoj_remember_token": "t",
                              "uoj_remember_token_checksum": "c",
                              "UOJSESSID": "s"},
                     fetch_fn=fetch_fn)
        with self.assertRaises(CookieExpiredError):
            c.get_contest_meta("2564")

    def test_cf_challenge_raises_blocked(self):
        def fetch_fn(url, cookie):
            return '<html><title>Just a moment...</title></html>'
        c = QojClient(cookies={"uoj_remember_token": "t",
                              "uoj_remember_token_checksum": "c",
                              "UOJSESSID": "s"},
                     fetch_fn=fetch_fn)
        with self.assertRaises(CFBlockedError):
            c.get_contest_meta("2564")


class TestFromCookieFile(unittest.TestCase):
    def test_load_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False) as f:
            f.write(".qoj.ac\tTRUE\t/\tFALSE\t0\tuoj_remember_token\tT\n")
            f.write(".qoj.ac\tTRUE\t/\tFALSE\t0\tuoj_remember_token_checksum\tC\n")
            f.write(".qoj.ac\tTRUE\t/\tFALSE\t0\tUOJSESSID\tS\n")
            path = Path(f.name)
        try:
            c = QojClient.from_cookie_file(path)
            self.assertTrue(c.cookies_valid())
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()