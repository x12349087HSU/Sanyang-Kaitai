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


def _fetch_twse_month(stock_id: str, ym: date) -> list[dict]:
    """回傳 JSON 可序列化的原始 dict（不是 PriceBar），因為這個函式的回傳值會
    直接被 cache.cached_call() 存進磁碟快取（json.dumps）——PriceBar 是
    dataclass，不能直接 json.dumps，之前這裡直接回傳 list[PriceBar] 存快取時
    會整個拋出 TypeError（'Object of type PriceBar is not JSON serializable'），
    只是因為 FinMind 平常都先成功，這個備援分支很少真的被執行到，才一直沒被
    抓到。跟 _fetch_finmind() 的做法一致：cached_call 只存/取原始 dict，
    PriceBar 的組裝放在 cached_call 外面。"""
    url = _twse_stock_day_url(stock_id, ym)
    resp = http_client.get(url)
    payload = resp.json()
    if payload.get("stat") != "OK":
        return []
    rows: list[dict] = []
    for row in payload.get("data", []):
        try:
            roc_date = row[0]  # "115/08/03"
            roc_year, month, day = (int(x) for x in roc_date.split("/"))
            trade_date = date(roc_year + 1911, month, day)
            rows.append({
                "trade_date": trade_date.isoformat(),
                "open": float(row[3].replace(",", "")),
                "high": float(row[4].replace(",", "")),
                "low": float(row[5].replace(",", "")),
                "close": float(row[6].replace(",", "")),
                "volume": int(row[1].replace(",", "")),
            })
        except (ValueError, IndexError):
            continue
    return rows


@safe_provider("TWSE OpenData (STOCK_DAY)")
def _fetch_twse_official(stock_id: str, market_type: str, months: int) -> list[PriceBar]:
    if market_type != "上市":
        raise RuntimeError("目前官方備援僅支援上市股票的股價查詢（證交所 STOCK_DAY）")

    today = date.today()
    all_bars: list[PriceBar] = []
    cursor = today.replace(day=1)
    for _ in range(months):
        key = f"price_twse:{stock_id}:{cursor.isoformat()}"
        month_rows = cache.cached_call(
            key, config.CACHE_TTL_PRICE, lambda c=cursor: _fetch_twse_month(stock_id, c)
        )
        for r in month_rows:
            all_bars.append(PriceBar(
                trade_date=date.fromisoformat(r["trade_date"]),
                open=r["open"], high=r["high"], low=r["low"],
                close=r["close"], volume=r["volume"],
            ))
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
