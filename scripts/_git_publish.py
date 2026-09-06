"""排程腳本共用的 git add/commit/push 小工具，給
prefetch_and_publish.py（均線篩選資料）跟 prefetch_fundamentals.py
（基本面摘要資料）共用，避免兩份幾乎一樣的 git 邏輯分開維護。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def publish_to_git(paths: list[str], commit_message: str) -> bool:
    """git add + commit + push 指定路徑。回傳是否真的有新 commit（沒有變化
    就跳過 commit/push，避免產生空 commit）。任何一步失敗會拋出
    RuntimeError，呼叫端負責印出清楚錯誤並回傳非 0 exit code。"""
    add_result = run_git("add", *paths)
    if add_result.returncode != 0:
        raise RuntimeError(f"git add 失敗：{add_result.stderr}")

    diff_result = run_git("diff", "--cached", "--quiet", "--", *paths)
    if diff_result.returncode == 0:
        return False

    commit_result = run_git("commit", "-m", commit_message)
    if commit_result.returncode != 0:
        raise RuntimeError(f"git commit 失敗：{commit_result.stderr}")

    push_result = run_git("push")
    if push_result.returncode != 0:
        raise RuntimeError(f"git push 失敗：{push_result.stderr}")

    return True
