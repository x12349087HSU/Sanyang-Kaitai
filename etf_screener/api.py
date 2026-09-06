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
from etf_screener.fundamentals_pdf import render_fundamentals_pdf
from etf_screener.ma_screener import screen_stocks
from etf_screener.screen_page import render_screen_html

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


# data/fundamentals.json 是一整份「所有股票的基本面摘要」（見
# ../scripts/prefetch_fundamentals.py），跟 _payload_cache 分開存，因為這裡
# 快取的 key 是整份檔案本身，不是個別 universe。
_fundamentals_cache: tuple[float, dict] | None = None


def _fetch_fundamentals_index() -> dict:
    global _fundamentals_cache
    if _fundamentals_cache is not None:
        cached_at, cached_index = _fundamentals_cache
        if time.time() - cached_at <= config.DATA_FETCH_TTL_SECONDS:
            return cached_index

    url = f"{config.DATA_RAW_BASE}/fundamentals.json"
    try:
        response = requests.get(url, timeout=config.HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        index = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="基本面資料尚未就緒，請稍後再試（排程結果還沒推送成功，或暫時連不到 GitHub）",
        ) from exc

    _fundamentals_cache = (time.time(), index)
    return index


# data/stock_index.json 是完整上市櫃公司代號/名稱/別名清單（見
# ../scripts/prefetch_stock_index.py），給「直接篩選個股」用來把使用者輸入
# 的代號/名稱解析成確切的 (stock_id, company_name)，這一步本身不呼叫
# FinMind，只在查表；查到之後才即時查該檔股價（見 screen_stock()）。
_stock_index_cache: tuple[float, list[dict]] | None = None


def _fetch_stock_index() -> list[dict]:
    global _stock_index_cache
    if _stock_index_cache is not None:
        cached_at, cached_index = _stock_index_cache
        if time.time() - cached_at <= config.DATA_FETCH_TTL_SECONDS:
            return cached_index

    url = f"{config.DATA_RAW_BASE}/stock_index.json"
    try:
        response = requests.get(url, timeout=config.HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        index = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="股票清單尚未就緒，請稍後再試（排程結果還沒推送成功，或暫時連不到 GitHub）",
        ) from exc

    _stock_index_cache = (time.time(), index)
    return index


def _resolve_stock(query: str, index: list[dict]) -> tuple[str, str] | None:
    """把使用者輸入的代號/名稱解析成 (stock_id, company_name)，比對順序
    跟 ../../公司基本面分析/tw_stock_report/identity.py 的 resolve() 一致：
    代號完全相符 > 名稱完全相符 > 名稱包含 > 別名完全相符 > 別名包含。
    這裡只是在既有清單裡查表（無網路請求），不是重新實作該檔案對 FinMind
    的呼叫。"""
    query = (query or "").strip()
    if not query:
        return None

    if query.isdigit():
        for entry in index:
            if entry["stock_id"] == query:
                return entry["stock_id"], entry["company_name"]
        return None

    for entry in index:
        if entry["company_name"] == query:
            return entry["stock_id"], entry["company_name"]
    for entry in index:
        if query in entry["company_name"]:
            return entry["stock_id"], entry["company_name"]
    for entry in index:
        if query in entry.get("aliases", []):
            return entry["stock_id"], entry["company_name"]
    for entry in index:
        if any(query in alias for alias in entry.get("aliases", [])):
            return entry["stock_id"], entry["company_name"]
    return None


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


@app.get("/fundamentals/{stock_id}")
def fundamentals(stock_id: str, x_app_password: str | None = Header(default=None)) -> dict:
    _check_password(x_app_password)
    index = _fetch_fundamentals_index()
    summary = index.get(stock_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"查無此股票的基本面資料: {stock_id}")
    return summary


@app.get("/fundamentals/{stock_id}/pdf")
def fundamentals_pdf(stock_id: str, x_app_password: str | None = Header(default=None)) -> Response:
    """即時把基本面摘要組成 PDF，不預先產生也不儲存（見
    fundamentals_pdf.py 檔頭說明）——摘要資料本身已經是 GitHub 上的現成
    資料，這裡只是本地排版，不呼叫任何外部資料源。"""
    _check_password(x_app_password)
    index = _fetch_fundamentals_index()
    summary = index.get(stock_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"查無此股票的基本面資料: {stock_id}")

    pdf_bytes = render_fundamentals_pdf(summary)
    company_name = summary["company_name"]
    generated_at = summary["generated_at"]
    filename = f"{company_name}基本面摘要_{generated_at}.pdf"
    ascii_fallback = f"{stock_id}_fundamentals_{generated_at}.pdf"
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


@app.get("/screen/stock/{query}")
def screen_stock(query: str, x_app_password: str | None = Header(default=None)) -> dict:
    """直接篩選個股：代號/名稱不限於 0050+0051 這個排程預抓的股票池，
    所以無法比照 /screen/{universe} 讀現成資料——**這是這個 API 唯一即時
    呼叫 FinMind/證交所的地方**。股價有證交所官方備援、單一檔請求量低，
    預期大部分時候能透過備援成功（見 DEVELOPMENT_LOG 相關章節）；基本面
    摘要沒有這種豁免，只有剛好也在 150 檔池子裡的股票查得到（走既有的
    /fundamentals/{stock_id} 404 優雅降級，不需要在這裡特別處理）。"""
    _check_password(x_app_password)
    index = _fetch_stock_index()
    resolved = _resolve_stock(query, index)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"查無股票「{query}」，請確認代號或名稱是否正確")
    stock_id, company_name = resolved

    result = screen_stocks([(stock_id, company_name)])
    if not result.rows:
        reason = result.skipped[0][2] if result.skipped else "查詢失敗"
        raise HTTPException(
            status_code=503,
            detail=f"「{company_name}（{stock_id}）」目前查不到股價資料，請稍後再試：{reason}",
        )

    html = render_screen_html(result, universe_label=company_name, include_neutral_tier=True)
    return {
        "universe": f"stock:{stock_id}",
        "universe_label": company_name,
        "generated_at": result.generated_at.isoformat(),
        "as_of_date": result.as_of_date.isoformat() if result.as_of_date else None,
        "total_count": len(result.rows) + len(result.skipped),
        "skipped_count": len(result.skipped),
        "html": html,
    }
