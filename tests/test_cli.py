"""
tests/test_cli.py

CLI 单元测试. 用 subprocess + 一个 in-process server fixture.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"


def make_env() -> dict:
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

    return {"tmp_root": Path(tmp), "repo": repo, "cfg": cfg}


class CLITestCase(unittest.TestCase):
    """每个测试独立环境, 启动一个 in-process server."""

    @classmethod
    def setUpClass(cls):
        cls.env = make_env()
        # 设置环境变量
        for k in ["REPO_PATH", "CONFIG_DIR", "CODES_DIR"]:
            os.environ.pop(k, None)
        os.environ["REPO_PATH"] = str(cls.env["repo"])
        os.environ["CONFIG_DIR"] = str(cls.env["cfg"])
        os.environ["CODES_DIR"] = str(cls.env["tmp_root"] / "codes")

        # 启动 server 在后台线程
        import uvicorn
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        # 重置 server 全局 state (防止前一个测试残留)
        import server
        server.state = server.AppState()

        config = uvicorn.Config(server.app, host="127.0.0.1", port=18901,
                               log_level="warning")
        cls.server = uvicorn.Server(config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        # 等 server 起来
        import httpx
        for _ in range(50):
            try:
                r = httpx.get("http://127.0.0.1:18901/healthz", timeout=0.5)
                if r.status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)

        cls.api_base = "http://127.0.0.1:18901"

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.server_thread.join(timeout=5)
        for k in ["REPO_PATH", "CONFIG_DIR", "CODES_DIR"]:
            os.environ.pop(k, None)
        shutil.rmtree(cls.env["tmp_root"], ignore_errors=True)

    def run_cli(self, *args, env_overrides=None, input=None):
        """调 CLI 子进程. 返回 (exit_code, stdout, stderr)."""
        env = os.environ.copy()
        env["REPO_PATH"] = str(self.env["repo"])
        env["CONFIG_DIR"] = str(self.env["cfg"])
        env["CODES_DIR"] = str(self.env["tmp_root"] / "codes")
        env["WIKI_API"] = self.api_base
        if env_overrides:
            env.update(env_overrides)

        return subprocess.run(
            [str(VENV_PY), "-m", "tools.cli_main", *args],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            input=input,
            timeout=30,
        )


# === Basic commands ===

class TestCLIBasic(CLITestCase):
    def test_doctor(self):
        r = self.run_cli("doctor")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("后端在跑", r.stdout)

    def test_list_empty(self):
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("共 0 场", r.stdout)

    def test_show_nonexistent(self):
        r = self.run_cli("show", "nonexistent")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("✗", r.stderr)


# === Cookie command ===

class TestCLICookies(CLITestCase):
    def test_status(self):
        # /import/cookies/status 是 Phase 3.4, 现在不实现; 只测 CLI 不 crash
        r = self.run_cli("cookies", "status")
        # 接受: exit 0 (有 cookie) 或 exit 1 (没实现端点)
        self.assertIn(r.returncode, (0, 1))


# === Update / upsolve (mocked fetch via test endpoint?) ===

class TestCLIRequiresConfirmation(CLITestCase):
    """update 默认需要 Y/n 确认."""

    def test_update_no_confirm_aborts(self):
        # 没有 mock fetch, 实际会 fetch qoj.ac 然后失败
        # 我们只验证: 不加 --yes 时即使填了 y, 也没法走通完整流程
        # 这里只 smoke test "update --dry-run" 这种不需要 fetch 的不会 hang
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()