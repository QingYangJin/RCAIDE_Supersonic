"""Workspace-local tmp_path override for the M0-R task-evaluator tests.

The DSH sandbox on this host denies pytest's default temp root, so every test
gets a unique scratch directory inside the worktree.  The suite is hermetic,
performs no solver starts, and never touches the real F1R2/F2R2 run dirs.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

WORK_ROOT = Path(__file__).resolve().parent / "_test_work"


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)


@pytest.fixture()
def tmp_path(request):
    target = WORK_ROOT / (_safe_name(request.node.name) + "_" + str(os.getpid()))
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    try:
        yield target
    finally:
        shutil.rmtree(target, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_work_root():
    yield
    shutil.rmtree(WORK_ROOT, ignore_errors=True)
