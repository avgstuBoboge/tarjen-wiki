#!/usr/bin/env python3
"""
tools/platforms/qoj.py — QOJ (qoj.ac, UOJ fork) 平台客户端

QOJ 没有公开 API, 只能 HTML 抓取. 关键信息:
  - 比赛页: https://qoj.ac/contest/<cid>
  - 提交列表: https://qoj.ac/contest/<cid>/submissions?verdict=<AC|WA>&user=<name>&page=<n>
  - 单份提交: https://qoj.ac/submission/<sid>

Auth: 3 个 cookie (uoj_remember_token / uoj_remember_token_checksum / UOJSESSID)
  浏览器登录 qoj.ac → F12 → Application → Cookies → 导出

登录态判断:
  - HTTP 401/403 → CookieExpiredError
  - 200 但 body 含登录页 (form action="/login" / "请先登录") → CookieExpiredError
  - 200 但 body 是 CF challenge 页 (Server: cloudflare / "Just a moment...") → CFBlockedError

注意: QOJ 改版时 HTML 选择器可能失效, 需要重新跑 fixtures。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .base import (
    CFBlockedError,
    ContestMeta,
    CookieExpiredError,
    NotFoundError,
    ParseError,
    PlatformClient,
    Submission,
    TimeoutError_,
    register,
)


# QOJ 用的 3 个 cookie key
COOKIE_KEY_TOKEN = "uoj_remember_token"
COOKIE_KEY_CHECKSUM = "uoj_remember_token_checksum"
COOKIE_KEY_SESSID = "UOJSESSID"

# 反爬虫: Cloudflare challenge 页特征
CF_CHALLENGE_MARKERS = [
    "Just a moment...",        # English CF challenge
    "请稍候...",                # CF 中文
    "<title>Just a moment",    # CF 标题
    "cf-challenge",            # CF script 标签
]

# QOJ 登录页特征 (UOJ 风格)
LOGIN_PAGE_MARKERS = [
    'action="/login"',
    "请先登录",
    "Please login first",
    "Please log in first",
    "Login Required",
]

# === HTML 解析用的正则 (脆弱, QOJ 改版时要更新) ===

# 比赛页: 提取 title + 题目数
RE_CONTEST_TITLE = re.compile(r"<h1[^>]*>\s*(.*?)\s*</h1>", re.DOTALL)
RE_PROBLEM_LINKS = re.compile(
    r'href="/contest/\d+/problem/([A-Z])"',
)

# 比赛页: 起止时间 (QOJ 在某个 <span> 里, 格式 "Start: ... End: ...")
RE_CONTEST_TIMES = re.compile(
    r"Start:\s*(\d{4}-\d{2}-\d{2}[^,\n]*?)\s*End:\s*(\d{4}-\d{2}-\d{2}[^,\n]*?)(?:<|$)",
    re.IGNORECASE,
)

# 提交列表页: 一行 (tr) 解析
# 实际 QOJ 表头大致: ID | Problem | User | Verdict | Time | Memory | Language | Length | Submitted
# 行格式近似: <tr><td><a href="/submission/12345">12345</a></td><td><a href="/contest/.../problem/A">A</a></td>...
RE_SUBMISSION_ROW = re.compile(
    r'<tr[^>]*>\s*'
    r'<td[^>]*>\s*<a[^>]*href="/submission/(\d+)"[^>]*>\d+</a>\s*</td>\s*'
    r'<td[^>]*>\s*<a[^>]*href="/contest/\d+/problem/([A-Z])"[^>]*>[A-Z]</a>\s*</td>\s*'
    r'<td[^>]*>\s*<a[^>]*>([^<]+)</a>\s*</td>\s*'                  # user
    r'<td[^>]*>\s*([A-Z]+)\s*</td>\s*'                              # verdict
    r'<td[^>]*>\s*([^<]+)\s*</td>\s*'                              # time (contest time or date)
    r'<td[^>]*>\s*([^<]*)\s*</td>\s*'                              # memory (skip)
    r'<td[^>]*>\s*([^<]*)\s*</td>\s*'                              # language
    r'<td[^>]*>\s*(\d*)\s*</td>\s*'                                # length
    r'</tr>',
    re.DOTALL,
)

# 单份提交页: 提取代码
# QOJ 把代码放在 <pre class="code"> 或 <pre><code>...</code></pre> 里
RE_CODE_BLOCK = re.compile(
    r'<pre[^>]*class="[^"]*code[^"]*"[^>]*>(.*?)</pre>',
    re.DOTALL,
)
RE_CODE_LANG = re.compile(
    r'(?:Language|语言)\s*[:：]?\s*([A-Za-z0-9+#.\s]+?)(?=<|$)',
    re.MULTILINE,
)


# === Cookie 加载 (Netscape 格式) ===

def parse_netscape_cookies(text: str, domain: str = "qoj.ac") -> dict[str, str]:
    """解析 Netscape cookie jar 格式, 返回指定 domain 的 cookies.

    格式:
        .qoj.ac  TRUE  /  FALSE  1924958400  cookie_name  value
    """
    cookies: dict[str, str] = {}
    for line in text.splitlines():
        # 跳过注释和空行
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        # tab 分隔 (Mozilla 格式) 或多空格
        parts = re.split(r"\s+", line, maxsplit=6)
        if len(parts) < 7:
            continue
        cookie_domain, _, _, _, _, name, value = parts[:7]
        # domain 匹配 (含子域)
        if domain in cookie_domain or cookie_domain.lstrip(".") == domain:
            cookies[name] = value
    return cookies


def cookie_header(cookies: dict[str, str]) -> str:
    """拼成 Cookie: header 字符串."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# === 工具 ===

def html_unescape(s: str) -> str:
    """简单 HTML entity 解码 (避免引入 html 库)."""
    return (s
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&amp;", "&"))


def strip_tags(s: str) -> str:
    """去 HTML 标签."""
    return re.sub(r"<[^>]+>", "", s).strip()


def parse_contest_time(text: str) -> int | None:
    """'1:23:45' 或 '1:23' → 秒. None 表示不可解析."""
    text = text.strip()
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 1:
            return int(parts[0])
    except ValueError:
        return None
    return None


# === Client ===

@register
class QojClient(PlatformClient):
    name = "qoj"

    BASE_URL = "https://qoj.ac"
    DEFAULT_TIMEOUT = 30
    DEFAULT_INTERVAL = 1.5   # 请求间隔 (秒), 防限速

    def __init__(self, cookies: dict[str, str] | None = None,
                 timeout: float = DEFAULT_TIMEOUT,
                 request_interval: float = DEFAULT_INTERVAL,
                 fetch_fn=None):
        """
        Args:
            cookies: 已解析的 cookie dict. None 时 cookies_valid() 返回 False.
            timeout: HTTP 超时秒数.
            request_interval: 请求间隔 (秒).
            fetch_fn: 可选, 注入 HTTP 实现 (测试用). 签名 (url, cookie_header) -> str.
        """
        self.cookies = cookies or {}
        self.timeout = timeout
        self.request_interval = request_interval
        self._last_request_at = 0.0
        self._fetch_fn = fetch_fn   # 默认用 urllib

    # === PlatformClient 接口 ===

    def cookies_valid(self) -> bool:
        """QOJ 需要的 3 个 cookie 是否齐全."""
        return all(k in self.cookies for k in (
            COOKIE_KEY_TOKEN, COOKIE_KEY_CHECKSUM, COOKIE_KEY_SESSID,
        ))

    def get_contest_meta(self, contest_id: str) -> ContestMeta:
        html = self._fetch(f"/contest/{contest_id}")
        return self._parse_contest_meta(html, contest_id)

    def get_user_submissions(self, contest_id: str, user: str) -> list[Submission]:
        """抓所有页 (含赛中 + 赛后), 调用方按时间筛."""
        all_subs = []
        page = 1
        while True:
            url = f"/contest/{contest_id}/submissions?user={user}&page={page}"
            html = self._fetch(url)
            subs = self._parse_submission_list(html, contest_id)
            if not subs:
                break
            all_subs.extend(subs)
            # 如果少于 50 条 (QOJ 默认每页), 说明是最后一页
            if len(subs) < 50:
                break
            page += 1
            if page > 100:  # 安全上限
                break
        return all_subs

    def get_submission_code(self, submission_id: str) -> tuple[str, str]:
        html = self._fetch(f"/submission/{submission_id}")
        return self._parse_code(html)

    # === HTTP ===

    def _fetch(self, path_or_url: str) -> str:
        if self._fetch_fn is not None:
            cookie_str = cookie_header(self.cookies) if self.cookies else ""
            body = self._fetch_fn(path_or_url, cookie_str)
            status = 200
        else:
            # 默认实现: urllib
            import urllib.request
            import urllib.error

            url = path_or_url if path_or_url.startswith("http") else self.BASE_URL + path_or_url
            req = urllib.request.Request(url, headers={
                "Cookie": cookie_header(self.cookies),
                "User-Agent": "Mozilla/5.0 (compatible; Wiki-Backend/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            })

            # 速率限制
            elapsed = time.time() - self._last_request_at
            if elapsed < self.request_interval:
                time.sleep(self.request_interval - elapsed)
            self._last_request_at = time.time()

            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.status
                    body = resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                status = e.code
                body = e.read().decode("utf-8", errors="replace") if e.fp else ""

        # 检查登录态 / CF / 错误状态 (无论 body 来自哪)
        if status in (401, 403) or self._is_login_page(body):
            raise CookieExpiredError(
                f"QOJ cookie 失效 (HTTP {status}, login page detected)"
            )
        if self._is_cf_challenge(body):
            raise CFBlockedError("Cloudflare challenge detected")
        if status == 404:
            raise NotFoundError(f"HTTP 404: {path_or_url}")
        if status >= 400:
            raise ParseError(f"HTTP {status}: {path_or_url}")
        return body

    @staticmethod
    def _is_login_page(body: str) -> bool:
        if not body:
            return False
        for marker in LOGIN_PAGE_MARKERS:
            if marker in body:
                return True
        return False

    @staticmethod
    def _is_cf_challenge(body: str) -> bool:
        if not body:
            return False
        for marker in CF_CHALLENGE_MARKERS:
            if marker in body:
                return True
        return False

    # === 解析 ===

    def _parse_contest_meta(self, html: str, contest_id: str) -> ContestMeta:
        title_match = RE_CONTEST_TITLE.search(html)
        if not title_match:
            raise ParseError(f"找不到 contest title, HTML 长度 {len(html)}")
        title = html_unescape(title_match.group(1)).strip()

        problems = RE_PROBLEM_LINKS.findall(html)
        problem_count = len(problems)
        if problem_count == 0:
            raise ParseError(f"找不到 problem links, HTML 长度 {len(html)}")

        start_time = end_time = None
        times = RE_CONTEST_TIMES.search(html)
        if times:
            start_time = times.group(1).strip()
            end_time = times.group(2).strip()

        return ContestMeta(
            platform="qoj",
            contest_id=contest_id,
            title=title,
            problem_count=problem_count,
            start_time=start_time,
            end_time=end_time,
            url=f"{self.BASE_URL}/contest/{contest_id}",
        )

    def _parse_submission_list(self, html: str, contest_id: str) -> list[Submission]:
        rows = RE_SUBMISSION_ROW.findall(html)
        subs = []
        for sid, problem, user, verdict, time_text, _mem, lang, length in rows:
            contest_secs = parse_contest_time(time_text)
            code_length = int(length) if length else None
            # submitted_at 我们没法从列表页直接拿到 (只有相对时间)
            # 留 None, 调用方用 contest_time 推断
            subs.append(Submission(
                platform="qoj",
                submission_id=sid,
                user=user.strip(),
                problem=problem.strip(),
                verdict=verdict.strip(),
                submitted_at="",  # 列表页不显示绝对时间
                contest_time_seconds=contest_secs,
                language=lang.strip() or None,
                code_length=code_length,
            ))
        return subs

    def _parse_code(self, html: str) -> tuple[str, str]:
        code_match = RE_CODE_BLOCK.search(html)
        if not code_match:
            raise ParseError("找不到 <pre class=code> 块")
        code = html_unescape(code_match.group(1)).strip()

        lang_match = RE_CODE_LANG.search(html)
        language = lang_match.group(1).strip() if lang_match else ""
        return code, language

    # === 静态工具 ===

    @staticmethod
    def from_cookie_file(path: Path) -> "QojClient":
        """从 Netscape cookie jar 文件构造."""
        text = path.read_text(encoding="utf-8")
        cookies = parse_netscape_cookies(text)
        return QojClient(cookies=cookies)