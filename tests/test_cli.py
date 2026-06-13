"""
tests/test_cli.py

CLI 测试 (用 click.testing.CliRunner, 不启动 server).

直接 import cli_main, 用 CliRunner.invoke 调命令.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def setup_env() -> dict:
    """建临时 git repo + config 目录."""
    tmp = tempfile.mkdtemp()
    tmp_path = Path(tmp)
    repo = tmp_path / "repo"
    repo.mkdir()
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
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"],
                   check=True, capture_output=True)

    cfg = tmp_path / "cfg"
    (cfg / "cookies").mkdir(parents=True)
    cfg.joinpath("config.json").write_text(json.dumps({
        "default_user": {"qoj": "tarjen"}
    }))

    return {"tmp_root": Path(tmp), "repo": repo, "cfg": cfg}


class CLITestBase(unittest.TestCase):
    """每次 setUp 建独立环境."""

    def setUp(self):
        self.env = setup_env()
        os.environ["REPO_PATH"] = str(self.env["repo"])
        os.environ["CONFIG_DIR"] = str(self.env["cfg"])
        os.environ["CODES_DIR"] = str(self.env["tmp_root"] / "codes")

        # 让 cli_main 能 import 各模块
        sys.path.insert(0, str(REPO_ROOT / "tools"))

        # 必须在导入 cli_main 之前设环境变量
        from click.testing import CliRunner
        self.runner = CliRunner()

        # import 后初始化 app state
        import cli_main
        cli_main.app.init()

    def tearDown(self):
        for k in ["REPO_PATH", "CONFIG_DIR", "CODES_DIR"]:
            os.environ.pop(k, None)
        shutil.rmtree(self.env["tmp_root"], ignore_errors=True)

    def invoke(self, *args, **kwargs):
        from cli_main import cli
        return self.runner.invoke(cli, list(args), **kwargs)


class TestCLIBasic(CLITestBase):
    def test_help(self):
        r = self.invoke("--help")
        self.assertEqual(r.exit_code, 0)
        self.assertIn("doctor", r.output)
        self.assertIn("list", r.output)
        self.assertIn("update", r.output)

    def test_doctor(self):
        r = self.invoke("doctor")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("数据 store 加载完成", r.output)
        self.assertIn("比赛: 0", r.output)

    def test_list_empty(self):
        r = self.invoke("list")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("共 0 场", r.output)

    def test_show_nonexistent(self):
        r = self.invoke("show", "nonexistent")
        self.assertNotEqual(r.exit_code, 0)
        self.assertIn("slug 不存在", r.output)


class TestCRUD(CLITestBase):
    def test_add_and_show(self):
        r = self.invoke("add",
                       "--slug", "2025-test",
                       "--name", "Test Contest",
                       "--date", "2025.6.12",
                       "--total", "3",
                       "--problems", "O;O;.",
                       "--tags", "#test",
                       "-y")
        self.assertEqual(r.exit_code, 0, r.output)

        r = self.invoke("show", "2025-test")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("2025-test", r.output)
        self.assertIn("O;O;.", r.output)

    def test_set_status(self):
        # 先加
        self.invoke("add",
                    "--slug", "x", "--name", "X", "--date", "2025.1.1",
                    "--total", "3", "--problems", ".;.;.", "-y")
        # 再改
        r = self.invoke("set", "x",
                       "--status", "A=O",
                       "--status", "B=Ø",
                       "-y")
        self.assertEqual(r.exit_code, 0, r.output)

        r = self.invoke("show", "x")
        self.assertIn("O;Ø;.", r.output)

    def test_rm(self):
        self.invoke("add",
                    "--slug", "x", "--name", "X", "--date", "2025.1.1",
                    "--total", "1", "--problems", ".", "-y")
        r = self.invoke("rm", "x", "-y")
        self.assertEqual(r.exit_code, 0, r.output)
        r = self.invoke("show", "x")
        self.assertNotEqual(r.exit_code, 0)


class TestUpdateDryRun(CLITestBase):
    def test_update_no_cookie(self):
        # 没有 QOJ cookie, update 应该报清晰错误
        r = self.invoke("update", "2564", "--dry-run")
        # 没 cookie: exit 1, 错误信息
        self.assertNotEqual(r.exit_code, 0)
        # 错误信息可能来自 QOJ client (连不通), 但不是 cookie 检查
        # 因为我们没 cookie 文件
        # 实际上我们设了 config.json 但没 cookie 文件, 会先报 cookie 错
        self.assertIn("cookie", r.output.lower() if hasattr(r, 'output') else "")


if __name__ == "__main__":
    unittest.main()