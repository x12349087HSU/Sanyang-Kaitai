"""FastAPI 服務層：把均線篩選結果包成 HTTP API 給手機 App 用。

存在的原因：手機 App（Capacitor 殼）沒辦法直接嵌入 Python 執行
`ma_screener.py`，需要一個獨立跑的後端服務，App 用 HTTP 打這裡拿篩選結果
（HTML 內容＋PDF 二進位檔）。

**這個服務不再自己即時抓 FinMind/證交所股價**（見 DEVELOPMENT_LOG.md 第
14.2 節：Render 這類雲端主機的 IP 會被這兩個來源擋下來，402/428）。改成讀
家裡電腦每天排程（見 `../scripts/prefetch_and_publish.py`）算好、推上
GitHub 的現成結果（`data/{universe}.json`／`data/{universe}.pdf`），只有
家裡電腦的住宅 IP 還會直接打 FinMind/證交所。

本機執行：py -m uvicorn etf_screener.api:app --reload --port 8000
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from etf_screener import config

_UNIVERSE_LABELS = {
    "0050": "0050 成分股",
    "top150": "上市市值前150大",
}

# 資料本身一天只被排程更新一次，這裡的快取單純是避免短時間內同一個 universe
# 被重複請求時，每次都再打一次 GitHub raw content。
_payload_cache: dict[str, tuple[float, dict]] = {}


def _fetch_universe_payload(universe: str) -> dict:
    cached = _payload_cache.get(universe)
    if cached is not None:
        cached_at, cached_payload = cached
        if time.time() - cached_at <= config.DATA_FETCH_TTL_SECONDS:
            return cached_payload

    url = f"{config.DATA_RAW_BASE}/{universe}.json"
    try:
        response = requests.get(url, timeout=config.HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="資料尚未就緒，請稍後再試（排程結果還沒推送成功，或暫時連不到 GitHub）",
        ) from exc

    _payload_cache[universe] = (time.time(), payload)
    return payload


def _fetch_universe_pdf(universe: str) -> bytes:
    url = f"{config.DATA_RAW_BASE}/{universe}.pdf"
    try:
        response = requests.get(url, timeout=config.HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF 尚未就緒，請稍後再試（排程結果還沒推送成功，或暫時連不到 GitHub）",
        ) from exc
    return response.content


def _get_configured_password() -> str | None:
    return os.environ.get("APP_PASSWORD") or None


def _check_password(x_app_password: str | None) -> None:
    """跟 app_streamlit.py 的 APP_PASSWORD 機制對齊：沒設就不擋，設了就要求
    App 端在 header 帶對密碼，兩邊共用同一個環境變數，不需要另外管理一組。"""
    correct = _get_configured_password()
    if not correct:
        return
    if x_app_password != correct:
        raise HTTPException(status_code=401, detail="密碼錯誤或未提供")


app = FastAPI(title="均線篩選器 API")

# Capacitor App 是從 capacitor://localhost（iOS）或 http://localhost（Android）
# 這類非網頁 origin 發出請求，不是瀏覽器分頁，這裡先開放所有 origin：這個 API
# 本身沒有登入態/session cookie，唯一的存取控制是上面的密碼 header，開放 CORS
# 不會因此洩漏額外資訊。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/screen/{universe}")
def screen(universe: str, x_app_password: str | None = Header(default=None)) -> dict:
    _check_password(x_app_password)
    if universe not in _UNIVERSE_LABELS:
        raise HTTPException(status_code=404, detail=f"未知的篩選範圍: {universe}")

    return _fetch_universe_payload(universe)


@app.get("/screen/{universe}/pdf")
def screen_pdf(universe: str, x_app_password: str | None = Header(default=None)) -> Response:
    _check_password(x_app_password)
    if universe not in _UNIVERSE_LABELS:
        raise HTTPException(status_code=404, detail=f"未知的篩選範圍: {universe}")

    payload = _fetch_universe_payload(universe)
    pdf_bytes = _fetch_universe_pdf(universe)
    universe_label = payload["universe_label"]
    generated_at = payload["generated_at"]
    filename = f"{universe_label}均線篩選_{generated_at}.pdf"
    # HTTP header 值只能是 latin-1，檔名含中文字元時必須用 RFC 5987 的
    # filename* 語法（percent-encode 過的 UTF-8），同時保留一個 ASCII 安全的
    # filename 當作舊客戶端看不懂 filename* 時的備援（内容是英文，不會出現
    # 剛才那個 UnicodeEncodeError）。
    ascii_fallback = f"{universe}_ma_screen_{generated_at}.pdf"
    encoded_filename = quote(filename)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{encoded_filename}"
            )
        },
    )
