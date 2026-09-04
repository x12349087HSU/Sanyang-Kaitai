"""排程用腳本：在家裡電腦（住宅 IP，未被 FinMind/證交所封鎖）跑一次均線
篩選，把結果寫成 data/{universe}.json + data/{universe}.pdf，commit 並 push
到 GitHub，讓 Render 上的 API（etf_screener/api.py）之後改用讀取這份現成
結果，不用自己即時打 FinMind/證交所（見 DEVELOPMENT_LOG.md 第 14.2 節）。

本機手動執行：py scripts/prefetch_and_publish.py
排程執行：見專案根目錄的 run_prefetch.bat（Windows Task Scheduler 呼叫這支）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from etf_screener import config
from etf_screener.ma_screener import MaScreenResult, screen_0050, screen_top150
from etf_screener.pdf_report import render_screen_pdf
from etf_screener.screen_page import render_screen_html

_UNIVERSES = {
    "0050": ("0050 成分股", screen_0050),
    "top150": ("上市市值前150大", screen_top150),
}


def _build_payload(universe: str, universe_label: str, result: MaScreenResult) -> dict:
    """組出跟 etf_screener/api.py `/screen/{universe}` 回傳完全相同的 schema，
    這樣 api.py 直接把這份 JSON 原封不動回傳給 App，不用再轉換一次。"""
    html = render_screen_html(result, universe_label=universe_label)
    return {
        "universe": universe,
        "universe_label": universe_label,
        "generated_at": result.generated_at.isoformat(),
        "as_of_date": result.as_of_date.isoformat() if result.as_of_date else None,
        "total_count": len(result.rows) + len(result.skipped),
        "skipped_count": len(result.skipped),
        "html": html,
    }


def _run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _publish_to_git(generated_at: str) -> bool:
    """git add + commit + push data/。回傳是否真的有新 commit（沒有變化就
    跳過 commit/push，避免產生空 commit）。任何一步失敗會拋出例外，讓
    main() 印出清楚錯誤並回傳非 0 exit code。"""
    add_result = _run_git("add", "data/")
    if add_result.returncode != 0:
        raise RuntimeError(f"git add 失敗：{add_result.stderr}")

    diff_result = _run_git("diff", "--cached", "--quiet")
    if diff_result.returncode == 0:
        print("資料跟上次推送的內容一模一樣，跳過 commit/push。")
        return False

    commit_message = f"排程更新篩選結果資料（{generated_at}）"
    commit_result = _run_git("commit", "-m", commit_message)
    if commit_result.returncode != 0:
        raise RuntimeError(f"git commit 失敗：{commit_result.stderr}")

    push_result = _run_git("push")
    if push_result.returncode != 0:
        raise RuntimeError(f"git push 失敗：{push_result.stderr}")

    return True


def main() -> int:
    generated_at = ""

    for universe, (universe_label, screen_fn) in _UNIVERSES.items():
        print(f"正在對「{universe_label}」跑均線篩選...")
        result = screen_fn()
        generated_at = result.generated_at.isoformat()

        payload = _build_payload(universe, universe_label, result)
        json_path = config.DATA_DIR / f"{universe}.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"  已寫入 {json_path}（{payload['total_count']} 檔，"
              f"{payload['skipped_count']} 檔查詢失敗）")

        pdf_bytes = render_screen_pdf(result, universe_label=universe_label)
        pdf_path = config.DATA_DIR / f"{universe}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        print(f"  已寫入 {pdf_path}")

    try:
        pushed = _publish_to_git(generated_at)
    except RuntimeError as exc:
        print(f"推送到 GitHub 失敗：{exc}")
        return 1

    if pushed:
        print("已成功 commit 並 push 到 GitHub，Render API 最多 "
              f"{config.DATA_FETCH_TTL_SECONDS // 60} 分鐘內會讀到新資料。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
