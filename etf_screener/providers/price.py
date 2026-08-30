"""股價 provider：FinMind 主要 + 證交所 STOCK_DAY 官方備援（僅上市；上櫃無可靠官方備援時會降級記錄原因）。"""
from __future__ import annotations

from datetime import date, timedelta

from .. import cache, config, http_client
from ..finmind_client import FinMindError, fetch_dataset
from ..models import PriceBar, ProviderResult, StockIdentity
from .base import safe_provider


def _parse_finmind_price(rows: list[dict]) -> list[PriceBar]:
    bars: list[PriceBar] = []
    for row in rows:
        try:
            bar = PriceBar(
                trade_date=date.fromisoformat(row["date"]),
                open=float(row["open"]),
                high=float(row["max"]),
                low=float(row["min"]),
                close=float(row["close"]),
                volume=int(row.get("Trading_Volume", 0) or 0),
            )
        except (KeyError, ValueError, TypeError):
            continue
        # FinMind 偶爾會回傳單日 close=0（或負值）的異常資料，這種資料點在均線
        # 計算上會嚴重扭曲結果，明顯是資料錯誤而非真實股價，直接跳過該筆。
        if bar.close <= 0 or bar.open <= 0 or bar.high <= 0 or bar.low <= 0:
            continue
        bars.append(bar)
    bars.sort(key=lambda b: b.trade_date)
    return bars


@safe_provider("FinMind")
def _fetch_finmind(stock_id: str, start_date: str, end_date: str) -> list[PriceBar]:
    def _fetch() -> list[dict]:
        return fetch_dataset(
            "TaiwanStockPrice", data_id=stock_id, start_date=start_date, end_date=end_date
        )

    key = f"price:{stock_id}:{start_date}:{end_date}"
    rows = cache.cached_call(key, config.CACHE_TTL_PRICE, _fetch)
    bars = _parse_finmind_price(rows)
    if not bars:
        raise FinMindError("FinMind 回傳股價資料為空")
    return bars


def _twse_stock_day_url(stock_id: str, ym: date) -> str:
    return (
        "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
        f"?response=json&date={ym.strftime('%Y%m01')}&stockNo={stock_id}"
    )


def _fetch_twse_month(stock_id: str, ym: date) -> list[PriceBar]:
    url = _twse_stock_day_url(stock_id, ym)
    resp = http_client.get(url)
    payload = resp.json()
    if payload.get("stat") != "OK":
        return []
    bars: list[PriceBar] = []
    for row in payload.get("data", []):
        try:
            roc_date = row[0]  # "115/08/03"
            roc_year, month, day = (int(x) for x in roc_date.split("/"))
            trade_date = date(roc_year + 1911, month, day)
            volume = int(row[1].replace(",", ""))
            open_ = float(row[3].replace(",", ""))
            high = float(row[4].replace(",", ""))
            low = float(row[5].replace(",", ""))
            close = float(row[6].replace(",", ""))
            bars.append(PriceBar(trade_date, open_, high, low, close, volume))
        except (ValueError, IndexError):
            continue
    return bars


@safe_provider("TWSE OpenData (STOCK_DAY)")
def _fetch_twse_official(stock_id: str, market_type: str, months: int) -> list[PriceBar]:
    if market_type != "上市":
        raise RuntimeError("目前官方備援僅支援上市股票的股價查詢（證交所 STOCK_DAY）")

    today = date.today()
    all_bars: list[PriceBar] = []
    cursor = today.replace(day=1)
    for _ in range(months):
        key = f"price_twse:{stock_id}:{cursor.isoformat()}"
        month_bars = cache.cached_call(
            key, config.CACHE_TTL_PRICE, lambda c=cursor: _fetch_twse_month(stock_id, c)
        )
        all_bars.extend(month_bars)
        # 回推一個月
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    all_bars.sort(key=lambda b: b.trade_date)
    if not all_bars:
        raise RuntimeError("證交所 STOCK_DAY 查無資料")
    return all_bars


def get_price_history(identity: StockIdentity, months: int = 12) -> ProviderResult[list[PriceBar]]:
    today = date.today()
    start = (today - timedelta(days=months * 31 + 10)).isoformat()
    end = today.isoformat()

    result = _fetch_finmind(identity.stock_id, start, end)
    if result.ok:
        return result

    fallback = _fetch_twse_official(identity.stock_id, identity.market_type, months + 1)
    if fallback.ok:
        return fallback

    return ProviderResult.failure(
        "FinMind + 官方備援",
        f"FinMind: {result.error}；官方備援: {fallback.error}",
    )
