#!/usr/bin/env python3
"""
tools/platforms/__init__.py — 注册所有内置平台 client
"""
from .base import (
    ContestMeta,
    CookieExpiredError,
    CFBlockedError,
    NotFoundError,
    ParseError,
    PlatformClient,
    PlatformError,
    Submission,
    TimeoutError_,
    get_client_class,
    get_registry,
    register,
)

# QOJ 是当前唯一实现. 注册即暴露.
from .qoj import QojClient  # noqa: E402,F401

__all__ = [
    "ContestMeta", "Submission", "PlatformClient", "PlatformError",
    "CookieExpiredError", "CFBlockedError", "NotFoundError", "ParseError",
    "TimeoutError_",
    "get_client_class", "get_registry", "register",
    "QojClient",
]