"""專案共用設定值。"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
CACHE_DIR = PROJECT_ROOT / "cache"

REPORTS_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

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

DISCLAIMER_TEXT = (
    "所有投資相關內容僅供參考，不構成任何投資建議，使用者應自行評估風險。"
)
