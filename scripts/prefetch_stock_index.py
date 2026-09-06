"""排程用腳本：抓一份完整的上市櫃公司代號/名稱/別名索引，寫成
data/stock_index.json，供「直接篩選個股」功能（api.py 的
GET /screen/stock/{query}）在 Render 上做代號/名稱比對用，不用即時打
FinMind——Render 只在「查到是哪一檔股票」之後，才即時查該檔的股價
（見 DEVELOPMENT_LOG.md 相關章節：股價有證交所官方備援、單一檔請求量低，
预期能透過備援成功；但股票清單本身沒有必要每次查詢都重新問 FinMind）。

這份清單一次抓全部上市櫃公司（FinMind TaiwanStockInfo 資料集），不是
逐檔查詢，成本遠低於 prefetch_fundamentals.py 那種批次查詢，不會佔用
額度。

本機手動執行：py scripts/prefetch_stock_index.py
排程執行：見專案根目錄的 run_prefetch.bat（Windows Task Scheduler 呼叫這支）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_FUNDAMENTALS_PROJECT_ROOT = _PROJECT_ROOT.parent / "公司基本面分析"
if str(_FUNDAMENTALS_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_FUNDAMENTALS_PROJECT_ROOT))

from etf_screener import config
from tw_stock_report import aliases_seed
from tw_stock_report.finmind_client import FinMindError, fetch_dataset

from _git_publish import publish_to_git

_MARKET_TYPE_MAP = {"twse": "上市", "tpex": "上櫃", "otc": "上櫃"}


def main() -> int:
    try:
        rows = fetch_dataset("TaiwanStockInfo")
    except FinMindError as exc:
        print(f"抓取股票清單失敗：{exc}")
        return 1

    index: dict[str, dict] = {}
    for row in rows:
        stock_id = row.get("stock_id", "")
        if not stock_id:
            continue
        # 同一代號可能因上市/上櫃切換出現多筆，後面的資料通常較新，直接覆蓋。
        index[stock_id] = {
            "stock_id": stock_id,
            "company_name": row.get("stock_name", ""),
            "aliases": aliases_seed.get_aliases(stock_id),
            "industry_name": row.get("industry_category", "") or "未知產業",
            "market_type": _MARKET_TYPE_MAP.get((row.get("type") or "").lower(), "未知"),
        }

    entries = list(index.values())
    print(f"共 {len(entries)} 檔上市櫃公司。")

    json_path = config.DATA_DIR / "stock_index.json"
    json_path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    print(f"已寫入 {json_path}")

    try:
        pushed = publish_to_git(
            ["data/stock_index.json"],
            f"排程更新股票代號/名稱索引（{len(entries)} 檔）",
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
