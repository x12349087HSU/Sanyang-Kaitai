"""命令列介面：py -m etf_screener.cli"""
from __future__ import annotations

from . import config
from .ma_screener import TIER_LABELS, screen_0050
from .screen_page import render_screen_html


def main() -> int:
    print("正在對 0050 成分股跑均線篩選（逐檔查詢股價，需要一點時間）...")
    result = screen_0050()
    html = render_screen_html(result)

    out_path = config.REPORTS_DIR / f"0050均線篩選_{result.generated_at.isoformat()}.html"
    out_path.write_text(html, encoding="utf-8")

    print(f"網頁報告已產出：{out_path}")
    for tier in (4, 3, 2, 1):
        count = len(result.rows_by_tier(tier))
        print(f"  {TIER_LABELS[tier]}：{count} 檔")
    if result.skipped:
        print(f"  查詢失敗（略過）：{len(result.skipped)} 檔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
