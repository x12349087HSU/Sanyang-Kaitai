"""專案共用設定值。"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
CACHE_DIR = PROJECT_ROOT / "cache"
DATA_DIR = PROJECT_ROOT / "data"

REPORTS_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# 一般公開頁面用的 User-Agent，識別為一般瀏覽器請求，非用於繞過封鎖。
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "TWStockScreenerBot/1.0 (+personal research tool; contact via project owner)"
)
HTTP_TIMEOUT_SECONDS = 10
HTTP_MAX_RETRIES = 2
HTTP_RETRY_BACKOFF_SECONDS = 1.5
# 對同一網站發出連續請求之間的最小間隔秒數（禮貌性延遲）。
HTTP_MIN_DELAY_SECONDS = 1.0

FINMIND_BASE_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "").strip() or None

CACHE_TTL_PRICE = 4 * 3600

# Render 上的 API 不再即時抓 FinMind/證交所（見 DEVELOPMENT_LOG 第 14.2
# 節，雲端主機 IP 被這兩個來源擋），改成讀家裡電腦排程推上 GitHub 的現成
# 結果檔（data/{universe}.json、data/{universe}.pdf）。
DATA_RAW_BASE = "https://raw.githubusercontent.com/x12349087HSU/Sanyang-Kaitai/master/data"
DATA_FETCH_TTL_SECONDS = 900  # 15 分鐘；資料本身一天只變一次，這裡只是避免短時間內重複打 GitHub

DISCLAIMER_TEXT = (
    "所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。"
)
