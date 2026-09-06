"""排程用腳本：對均線篩選股票池（0050+0051）每一檔算一份「簡化版基本面
摘要」（營收/EPS 趨勢文字、基本面自檢表、目標價評等），寫成
data/fundamentals.json，commit 並 push 到 GitHub，給 etf_screener/api.py
新增的 /fundamentals/{stock_id} 讀取。

基本面計算邏輯完全重用另一個獨立專案「公司基本面分析」
（tw_stock_report.report.generate_summary()），不重複實作任何算法；這裡
只負責「對一整個股票池跑一輪、單檔失敗跳過、彙整成一份檔案」的批次邏輯，
跟 etf_screener/ma_screener.py 的 screen_stocks() 是同一套容錯模式。

已知取捨：150 檔 ×（月營收/EPS/財報/資產負債表/現金流量表 5 個 FinMind
資料集 + 目標價評等 7 組關鍵字的鉅亨網搜尋），實際跑起來會比純股價的
prefetch_and_publish.py 慢不少；且營收/EPS/財報本來就不是每天變動，理論上
不需要真的每天重算。這次先求「架構簡單、只有一個排程時間要記」，跟均線
資料一起每天更新；如果之後實測跑太久，可以改成獨立排程（例如只在週末
跑），只需要調整 run_prefetch.bat 跟 Task Scheduler 設定，不需要動這支
腳本的邏輯本身。

本機手動執行：py scripts/prefetch_fundamentals.py
排程執行：見專案根目錄的 run_prefetch.bat（Windows Task Scheduler 呼叫這支）
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_FUNDAMENTALS_PROJECT_ROOT = _PROJECT_ROOT.parent / "公司基本面分析"
if str(_FUNDAMENTALS_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_FUNDAMENTALS_PROJECT_ROOT))

from etf_screener import config
from etf_screener.ma_screener import TOP150_CONSTITUENTS
from tw_stock_report.identity import IdentityNotFound
from tw_stock_report.report import SummaryResult, generate_summary

from _git_publish import publish_to_git


# 刻意比 ma_screener.screen_stocks() 的 6 低：實測用 6 個併發對 150 檔各打
# 5 個 FinMind 資料集，跑到第二次就從「402 Payment Required」（額度用完）
# 惡化成「403 Forbidden」（疑似觸發反濫用機制），這裡放慢並發數，讓整批
# 對 FinMind 的請求速率更溫和，降低再次觸發的機率。
_MAX_WORKERS = 2


def _summary_to_dict(result: SummaryResult) -> dict:
    return {
        "stock_id": result.identity.stock_id,
        "company_name": result.identity.company_name,
        "industry_name": result.identity.industry_name,
        "generated_at": result.generated_at.isoformat(),
        "revenue_summary_text": result.revenue_summary_text,
        "eps_summary_text": result.eps_summary_text,
        "checklist_items": [
            {
                "tier": item.tier,
                "tier_name": item.tier_name,
                "name": item.name,
                "passed": item.passed,
                "detail": item.detail,
            }
            for item in result.checklist_items
        ],
        "ratings": [
            {
                "institution": r.institution,
                "rating": r.rating,
                "target_price": r.target_price,
                "publish_date": r.publish_date.isoformat() if r.publish_date else None,
                "source_title": r.source_title,
                "source_url": r.source_url,
                "note": r.note,
            }
            for r in result.ratings
        ],
    }


def main() -> int:
    fundamentals: dict[str, dict] = {}
    skipped: list[tuple[str, str, str]] = []

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(generate_summary, stock_id): (stock_id, name)
            for stock_id, name in TOP150_CONSTITUENTS
        }
        for future in as_completed(futures):
            stock_id, name = futures[future]
            try:
                result = future.result()
            except IdentityNotFound as exc:
                skipped.append((stock_id, name, str(exc)))
                continue
            except Exception as exc:  # noqa: BLE001 - 單檔失敗不可中止整批
                skipped.append((stock_id, name, str(exc)))
                continue
            fundamentals[stock_id] = _summary_to_dict(result)

    print(f"基本面摘要：{len(fundamentals)} 檔成功、{len(skipped)} 檔失敗（略過）。")
    for stock_id, name, reason in skipped:
        print(f"  跳過 {stock_id} {name}：{reason}")

    json_path = config.DATA_DIR / "fundamentals.json"
    json_path.write_text(json.dumps(fundamentals, ensure_ascii=False), encoding="utf-8")
    print(f"已寫入 {json_path}")

    try:
        pushed = publish_to_git(
            ["data/fundamentals.json"],
            f"排程更新基本面摘要資料（{len(fundamentals)} 檔）",
        )
    except RuntimeError as exc:
        print(f"推送到 GitHub 失敗：{exc}")
        return 1

    if pushed:
        print("已成功 commit 並 push 到 GitHub。")
    else:
        print("資料跟上次推送的內容一模一樣，跳過 commit/push。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
