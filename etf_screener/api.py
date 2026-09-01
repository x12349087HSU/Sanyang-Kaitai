"""FastAPI 服務層：把均線篩選邏輯包成 HTTP API。

存在的原因：手機 App（Capacitor 殼）沒辦法直接嵌入 Python 執行
`ma_screener.py`，需要一個獨立跑的後端服務，App 用 HTTP 打這裡拿篩選結果
（HTML 內容＋PDF 二進位檔），這一層不依賴 Streamlit，跟 `app_streamlit.py`
是兩個平行的前端，共用同一套底層篩選/報告產生邏輯。

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

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from etf_screener.ma_screener import MaScreenResult, screen_0050, screen_top150
from etf_screener.pdf_report import render_screen_pdf
from etf_screener.screen_page import render_screen_html

_UNIVERSES = {
    "0050": ("0050 成分股", screen_0050),
    "top150": ("上市市值前150大", screen_top150),
}

# 同一個篩選範圍在短時間內重複被打（例如網頁版拿完 HTML，App 馬上又要同一批
# 資料的 PDF），直接沿用同一次篩選結果，不重新掃一次全部成分股：一來避免
# 使用者兩次動作中間股價快取（見 cache.py，TTL 4 小時）剛好過期，導致 HTML
# 跟 PDF 顯示的「資料日期」對不起來；二來省下重新逐檔查價+分類的時間。
_RESULT_CACHE_TTL_SECONDS = 600
_result_cache: dict[str, tuple[float, MaScreenResult]] = {}


def _get_screen_result(universe: str) -> tuple[str, MaScreenResult]:
    universe_label, screen_fn = _UNIVERSES[universe]
    cached = _result_cache.get(universe)
    if cached is not None:
        cached_at, cached_result = cached
        if time.time() - cached_at <= _RESULT_CACHE_TTL_SECONDS:
            return universe_label, cached_result
    result = screen_fn()
    _result_cache[universe] = (time.time(), result)
    return universe_label, result


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
    if universe not in _UNIVERSES:
        raise HTTPException(status_code=404, detail=f"未知的篩選範圍: {universe}")

    universe_label, result = _get_screen_result(universe)
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


@app.get("/screen/{universe}/pdf")
def screen_pdf(universe: str, x_app_password: str | None = Header(default=None)) -> Response:
    _check_password(x_app_password)
    if universe not in _UNIVERSES:
        raise HTTPException(status_code=404, detail=f"未知的篩選範圍: {universe}")

    universe_label, result = _get_screen_result(universe)
    pdf_bytes = render_screen_pdf(result, universe_label=universe_label)
    filename = f"{universe_label}均線篩選_{result.generated_at.isoformat()}.pdf"
    # HTTP header 值只能是 latin-1，檔名含中文字元時必須用 RFC 5987 的
    # filename* 語法（percent-encode 過的 UTF-8），同時保留一個 ASCII 安全的
    # filename 當作舊客戶端看不懂 filename* 時的備援（内容是英文，不會出現
    # 剛才那個 UnicodeEncodeError）。
    ascii_fallback = f"{universe}_ma_screen_{result.generated_at.isoformat()}.pdf"
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
