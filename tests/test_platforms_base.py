"""
tests/test_platforms_base.py

platforms/base.py 单元测试。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from platforms.base import (  # noqa: E402
    CFBlockedError, ContestMeta, CookieExpiredError, NotFoundError,
    ParseError, PlatformClient, PlatformError, Submission, TimeoutError_,
    get_client_class, get_registry, register,
)


class TestDataclasses(unittest.TestCase):
    def test_contest_meta_minimal(self):
        m = ContestMeta(platform="qoj", contest_id="2564", title="X",
                        problem_count=13)
        self.assertEqual(m.platform, "qoj")
        self.assertEqual(m.problem_count, 13)
        self.assertIsNone(m.start_time)
        self.assertIsNone(m.end_time)

    def test_contest_meta_full(self):
        m = ContestMeta(
            platform="qoj", contest_id="2564", title="X", problem_count=13,
            start_time="2025-06-07T08:00:00Z",
            end_time="2025-06-07T13:00:00Z",
            url="https://qoj.ac/contest/2564",
        )
        self.assertEqual(m.start_time, "2025-06-07T08:00:00Z")

    def test_submission_minimal(self):
        s = Submission(
            platform="qoj", submission_id="12345", user="alice",
            problem="A", verdict="AC", submitted_at="2025-06-07T08:12:00Z",
            contest_time_seconds=720,
        )
        self.assertEqual(s.verdict, "AC")
        self.assertEqual(s.contest_time_seconds, 720)


class TestExceptionHierarchy(unittest.TestCase):
    def test_all_inherit_platform_error(self):
        for cls in [CookieExpiredError, CFBlockedError, ParseError,
                   NotFoundError, TimeoutError_]:
            self.assertTrue(issubclass(cls, PlatformError))

    def test_platform_error_is_runtime(self):
        self.assertTrue(issubclass(PlatformError, RuntimeError))


class TestRegistry(unittest.TestCase):
    def setUp(self):
        # 备份, 因为 register 是全局副作用
        from platforms import base as base_mod
        self._orig = dict(base_mod._REGISTRY)
        base_mod._REGISTRY.clear()

    def tearDown(self):
        from platforms import base as base_mod
        base_mod._REGISTRY.clear()
        base_mod._REGISTRY.update(self._orig)

    def test_register_basic(self):
        @register
        class FakeClient(PlatformClient):
            name = "fake_test"

        self.assertIn("fake_test", get_registry())

    def test_register_requires_name(self):
        with self.assertRaises(ValueError):
            @register
            class NoName(PlatformClient):
                name = ""

    def test_register_rejects_duplicate(self):
        @register
        class A(PlatformClient):
            name = "dup_test"

        with self.assertRaises(ValueError):
            @register
            class B(PlatformClient):
                name = "dup_test"

    def test_get_client_class(self):
        @register
        class C(PlatformClient):
            name = "get_test"

        self.assertIs(get_client_class("get_test"), C)

    def test_get_client_class_unknown(self):
        with self.assertRaises(ValueError) as cm:
            get_client_class("nonexistent")
        self.assertIn("不支持的平台", str(cm.exception))


class TestAbstractEnforcement(unittest.TestCase):
    """PlatformClient 是 ABC, 实例化必须实现所有抽象方法."""

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            PlatformClient()


if __name__ == "__main__":
    unittest.main()