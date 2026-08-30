"""命令列介面：
py -m etf_screener.cli                 （預設：0050 成分股快速掃描）
py -m etf_screener.cli --universe top150   （上市市值前 150 大：0050 + 0051 成分股）
"""
from __future__ import annotations

import argparse

from . import config
from .ma_screener import TIER_LABELS, TIER_ORDER, screen_0050, screen_top150
from .pdf_report import render_screen_pdf
from .screen_page import render_screen_html

_UNIVERSES = {
    "0050": ("0050 成分股", screen_0050),
    "top150": ("上市市值前150大", screen_top150),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="均線篩選器")
    parser.add_argument(
        "--universe",
        choices=sorted(_UNIVERSES),
        default="0050",
        help="要篩選的股票池：0050（成分股，約 50 檔，快）或 top150（上市市值前 150 大，約 150 檔，較久）",
    )
    args = parser.parse_args()

    universe_label, screen_fn = _UNIVERSES[args.universe]
    print(f"正在對「{universe_label}」跑均線篩選（逐檔查詢股價，需要一點時間）...")
    result = screen_fn()

    stem = f"{universe_label}均線篩選_{result.generated_at.isoformat()}"
    html_path = config.REPORTS_DIR / f"{stem}.html"
    html_path.write_text(render_screen_html(result, universe_label=universe_label), encoding="utf-8")

    pdf_path = config.REPORTS_DIR / f"{stem}.pdf"
    pdf_path.write_bytes(render_screen_pdf(result, universe_label=universe_label))

    print(f"網頁報告已產出：{html_path}")
    print(f"PDF 報告已產出：{pdf_path}")
    for tier in TIER_ORDER:
        count = len(result.rows_by_tier(tier))
        print(f"  {TIER_LABELS[tier]}：{count} 檔")
    if result.skipped:
        print(f"  查詢失敗（略過）：{len(result.skipped)} 檔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
