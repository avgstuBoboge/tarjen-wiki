#!/usr/bin/env python3
"""
tools/codes_logic.py — 代码抓取的业务逻辑

被 server.py 调用. 不依赖 FastAPI.

策略 (watchlist 优先 + sample):
  - 自己的提交: 全抓 (含 WA/TLE, 用于复盘)
  - watchlist 用户: 所有 AC (放在 sample 池前面)
  - 其他用户: 补到 samples_per_problem/题 (默认 5)
  池: 每题 watchlist AC 按时间排, 然后补 others AC, dedup 按 (user, problem),
      截到 samples_per_problem.
  当 fetch_others="none" 时, 池只剩 watchlist AC, 上限 samples_per_problem/题.

后端 store: ~/.local/share/wiki/codes/<cid>/<user>/<prob>.<ext>
索引: ~/.local/share/wiki/codes/<cid>/index.json
gitignored.

长任务: 通过 task_id 暴露状态, 不阻塞 HTTP.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from csv_store import CsvStore
from codes_store import CodesStore
from platforms import get_client_class
from platforms.base import FastestACEntry, PlatformClient, Submission
from watchlist import Watchlist


Source = Literal["mine", "watchlist", "sample", "other"]


# === Task state (in-memory, single-process) ===

TASKS: dict[str, "FetchTask"] = {}


@dataclass
class FetchTask:
    task_id: str
    cid: str
    status: Literal["started", "running", "done", "error"] = "started"
    progress: dict = field(default_factory=dict)
    started_at: float = 0.0
    finished_at: float | None = None
    result: dict | None = None
    error: str | None = None
    cancel_requested: bool = False


def get_task(task_id: str) -> FetchTask | None:
    return TASKS.get(task_id)


def list_tasks() -> list[FetchTask]:
    return list(TASKS.values())


def create_task(cid: str) -> FetchTask:
    tid = f"fetch_{cid}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    task = FetchTask(task_id=tid, cid=cid, started_at=time.time())
    TASKS[tid] = task
    return task


# === Fetch strategy ===

@dataclass
class FetchRequest:
    platform: str = "qoj"
    cid: str = ""
    username: str = ""
    fetch_self: bool = True
    fetch_watchlist: bool = True
    fetch_others: str = "top_n_fastest"   # "top_n_fastest" | "top_n_shortest" | "random_n" | "none"
    samples_per_problem: int = 5
    problems: list[str] | None = None
    skip_existing: bool = True
    timeout_seconds: int = 600
    request_interval: float = 1.5
    # Deprecated 字段: 转发到 samples_per_problem. 设了会触发 DeprecationWarning.
    others_n: int | None = None

    def __post_init__(self):
        import warnings
        if self.others_n is not None:
            warnings.warn(
                "FetchRequest.others_n 已废弃, 请改用 samples_per_problem",
                DeprecationWarning, stacklevel=2,
            )
            self.samples_per_problem = self.others_n
        if self.samples_per_problem < 0:
            self.samples_per_problem = 0


@dataclass
class FetchResult:
    fetched: int = 0
    skipped_existing: int = 0
    skipped_non_ac: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    files: list[dict] = field(default_factory=list)
    error_details: list[dict] = field(default_factory=list)  # [{sid, user, prob, msg}]

    def to_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "skipped_existing": self.skipped_existing,
            "skipped_non_ac": self.skipped_non_ac,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "files": self.files,
            "error_details": self.error_details,
        }


def fetch_codes(
    req: FetchRequest,
    platform_client_factory,
    codes_store: CodesStore,
    watchlist_obj: Watchlist,
    progress_callback=None,
    cancel_check=None,
) -> FetchResult:
    """执行抓取.

    Args:
        req: 抓取请求
        platform_client_factory: 接受 (platform, cookies) -> PlatformClient. 用于测试时注入.
        codes_store: 存储后端
        watchlist_obj: watchlist 实例
        progress_callback: 可选, FetchTask 设进 progress 字段
        cancel_check: 可选, 返回 True 时中断
    """
    import random
    from datetime import datetime

    start = time.time()
    result = FetchResult()
    wl_users = set(watchlist_obj.users())

    # 1. 拿 client
    client = platform_client_factory(req.platform)
    platform = req.platform

    # 2. 题目列表 — 单一真相源 (从 OJ 拿, 不再硬编码 A-Z).
    try:
        all_letters = client.get_problem_letters(req.cid)
    except Exception as e:
        result.errors += 1
        result.duration_seconds = time.time() - start
        raise
    # 过滤到子集 (CLI --problem)
    if req.problems:
        problems = [L for L in all_letters if L in req.problems]
    else:
        problems = all_letters
    if not problems:
        result.duration_seconds = round(time.time() - start, 2)
        return result

    # 3. 拿 standings (结构化, 免 HTML 分页)
    try:
        # 自己: 拿所有 StandingsEntry (含 WAs)
        my_standings = client.get_user_standings(req.cid, req.username) if req.fetch_self else {}
        # 所有用户的 AC (排除自己), 按时间排
        others_per_problem = client.get_all_user_standings(
            req.cid, exclude_users={req.username}
        ) if req.fetch_others != "none" else {}
    except Exception as e:
        result.errors += 1
        result.duration_seconds = time.time() - start
        raise

    # 4. 自己: 转 submission 列表 (含 WAs, 用于复盘)
    mine_subs = _standings_to_subs(my_standings, req.username, problems)
    # 5. watchlist: AC only
    watchlist_subs = []
    if req.fetch_watchlist:
        for u in wl_users:
            if u == req.username:
                continue  # 已在 mine
            try:
                u_standings = client.get_user_standings(req.cid, u)
            except Exception as e:
                result.errors += 1
                result.error_details.append({
                    "submission_id": "?", "user": u, "problem": "?",
                    "error": f"get_user_standings: {type(e).__name__}: {e}",
                })
                continue
            for entry in u_standings.values():
                if entry.letter not in problems:
                    continue
                if entry.verdict == "AC":  # watchlist 只看 AC
                    watchlist_subs.append(_entry_to_sub(entry, u))

    # 6. 构造 pool_per_problem (watchlist 优先, 不够再补 others, 每题 cap)
    #    排除集合:
    #      - self 永远排除
    #      - watchlist 用户只在 fetch_watchlist=True 时排除 (否则降级到 others)
    others_exclude = {req.username}
    if req.fetch_watchlist:
        others_exclude |= wl_users
    pool_per_problem: dict[str, list[Submission]] = {L: [] for L in problems}
    for L in problems:
        # 6a. watchlist AC (按 time 升序)
        if req.fetch_watchlist:
            wl_for_letter = sorted(
                [s for s in watchlist_subs if s.problem == L],
                key=lambda s: s.contest_time_seconds if s.contest_time_seconds is not None else 10**9,
            )
            pool_per_problem[L].extend(wl_for_letter)
        # 6b. others AC (按 time 升序 — get_all_user_standings 已排好)
        if req.fetch_others != "none":
            others_for_letter = _pick_others_for_problem(
                others_per_problem.get(L, []), req.fetch_others, L,
                exclude_users=others_exclude,
            )
            pool_per_problem[L].extend(others_for_letter)

    # 7. 每题去重 (按 user) + 截到 samples_per_problem
    pool_subs: list[Submission] = []
    for L in problems:
        seen_user: set[str] = set()
        for s in pool_per_problem[L]:
            if s.user in seen_user:
                continue
            seen_user.add(s.user)
            pool_subs.append(s)
            if len(seen_user) >= req.samples_per_problem:
                break

    # 8. final = mine + pool, 再去重一次 (防御性 — 自己可能在 watchlist 里)
    seen: set[tuple[str, str]] = set()
    final: list[Submission] = []
    for s in mine_subs + pool_subs:
        key = (s.user, s.problem)
        if key in seen:
            continue
        seen.add(key)
        final.append(s)

    # 6. 抓代码 (串行)
    for s in final:
        if cancel_check and cancel_check():
            break
        # 检查 skip_existing
        if req.skip_existing and codes_store.exists(platform, req.cid, s.problem, s.user):
            result.skipped_existing += 1
            continue

        try:
            code, lang = client.get_submission_code(s.submission_id)
        except Exception as e:
            result.errors += 1
            result.error_details.append({
                "submission_id": s.submission_id,
                "user": s.user,
                "problem": s.problem,
                "error": f"{type(e).__name__}: {e}",
            })
            continue

        # 决定 source
        if s.user == req.username:
            source = "mine"
        elif s.user in wl_users and req.fetch_watchlist:
            source = "watchlist"
        else:
            source = "sample"

        path = codes_store.save(
            platform, req.cid, s.problem, s.user, code, lang,
            verdict=s.verdict, submission_id=s.submission_id,
            source=source, contest_time=_secs_to_str(s.contest_time_seconds),
        )
        result.fetched += 1
        result.files.append({
            "user": s.user, "problem": s.problem, "verdict": s.verdict,
            "lang": lang, "size": path.stat().st_size,
            "source": source, "submission_id": s.submission_id,
        })

        if progress_callback:
            progress_callback({
                "fetched": result.fetched,
                "total": len(final),
                "current": f"{s.user}/{s.problem}",
            })

        # 速率控制
        time.sleep(req.request_interval)

    result.duration_seconds = round(time.time() - start, 2)
    return result


def _standings_to_subs(standings: dict, user: str,
                      problems: list[str] | None) -> list[Submission]:
    """StandingsEntry dict → Submission 列表 (含 WAs)."""
    subs = []
    for letter, entry in standings.items():
        if problems and letter not in problems:
            continue
        subs.append(_entry_to_sub(entry, user))
    return subs


def _entry_to_sub(entry, user: str) -> Submission:
    """单个 StandingsEntry → Submission (含 fake sub_id)."""
    return Submission(
        platform="qoj",
        submission_id=entry.submission_id or "",
        user=user,
        problem=entry.letter,
        verdict=entry.verdict or "WA",
        submitted_at="",
        contest_time_seconds=entry.contest_time_seconds,
        language=None,
        code_length=None,
    )


def _pick_others_for_problem(
    entries: list[FastestACEntry],
    mode: str,
    letter: str,
    exclude_users: set[str],
) -> list[Submission]:
    """从 standings 拿的单题 others 选 candidates (不截, cap 在 pool 层做).

    entries 已按时间升序 (get_all_user_standings 排好).
    返回的 Submission.problem 填上 letter (callers 不会再覆盖).
    """
    if mode == "none":
        return []
    candidates = [e for e in entries if e.user not in exclude_users and e.submission_id]
    if not candidates:
        return []
    if mode == "top_n_fastest":
        pass  # 已经是按时间排
    elif mode == "top_n_shortest":
        # 不知道 code_length, 用 random 退化
        random.shuffle(candidates)
    elif mode == "random_n":
        random.shuffle(candidates)
    return [Submission(
        platform="qoj",
        submission_id=e.submission_id,
        user=e.user,
        problem=letter,
        verdict="AC",
        submitted_at="",
        contest_time_seconds=e.time_seconds,
        language=None,
        code_length=None,
    ) for e in candidates]


def _secs_to_str(secs: int | None) -> str | None:
    if secs is None:
        return None
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"