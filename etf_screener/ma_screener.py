"""0050 成分股均線篩選：判斷各成分股最近一日收盤價是否站上 5/10/20/60 日均線，
依站上的均線數量分成四個等級。

分級是「巢狀」判定，不是各自獨立判斷：
- 四海遊龍：收盤價同時站上 5MA、10MA、20MA、60MA 四條均線
- 三陽開泰：站上 5MA、10MA、20MA（不論站上或跌破 60MA——若也站上 60MA，
  會被歸類到更高一級的「四海遊龍」，所以這裡看到的必定是跌破或無法判定 60MA 的情況）
- 短線翻多訊號：站上 5MA、10MA（同理，不含也站上 20MA 的情況）
- 準備短線翻多：只站上 5MA（不含也站上 10MA 的情況）

每檔股票只會落在其中一級，或落在「0」（連 5MA 都沒站上，不列入四個等級）。
單一成分股查價失敗只會被記錄到 skipped，不會讓整批篩選中止，跟其他 provider
的容錯原則一致（見 providers/base.py）。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date

from .etf0050_constituents import ETF_0050_CONSTITUENTS
from .models import StockIdentity
from .moving_average import simple_moving_average
from .providers.price import get_price_history

_MA_WINDOWS = (5, 10, 20, 60)
_PRICE_FETCH_MONTHS = 6  # 約可涵蓋 100+ 交易日，60MA 計算所需的暖身資料足夠

TIER_LABELS: dict[int, str] = {
    4: "四海遊龍",
    3: "三陽開泰",
    2: "短線翻多訊號",
    1: "準備短線翻多",
}
TIER_DESCRIPTIONS: dict[int, str] = {
    4: "最近一日收盤價同時站上 5MA、10MA、20MA、60MA 四條均線",
    3: "最近一日收盤價站上 5MA、10MA、20MA 三條均線",
    2: "最近一日收盤價站上 5MA、10MA 兩條均線",
    1: "最近一日收盤價站上 5MA 一條均線",
}


@dataclass
class MaScreenRow:
    stock_id: str
    company_name: str
    trade_date: date
    close: float
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma60: float | None
    tier: int  # 4/3/2/1，或 0 表示未站上任何均線（不列入四個等級）


@dataclass
class MaScreenResult:
    generated_at: date
    rows: list[MaScreenRow] = field(default_factory=list)
    skipped: list[tuple[str, str, str]] = field(default_factory=list)  # (stock_id, name, reason)

    def rows_by_tier(self, tier: int) -> list[MaScreenRow]:
        return sorted(
            (r for r in self.rows if r.tier == tier),
            key=lambda r: r.company_name,
        )

    @property
    def as_of_date(self) -> date | None:
        dates = [r.trade_date for r in self.rows]
        return max(dates) if dates else None


def _classify_tier(
    close: float,
    ma5: float | None,
    ma10: float | None,
    ma20: float | None,
    ma60: float | None,
) -> int:
    above_5 = ma5 is not None and close > ma5
    above_10 = ma10 is not None and close > ma10
    above_20 = ma20 is not None and close > ma20
    above_60 = ma60 is not None and close > ma60
    if above_5 and above_10 and above_20 and above_60:
        return 4
    if above_5 and above_10 and above_20:
        return 3
    if above_5 and above_10:
        return 2
    if above_5:
        return 1
    return 0


def _screen_one(stock_id: str, company_name: str) -> MaScreenRow:
    identity = StockIdentity(
        stock_id=stock_id,
        company_name=company_name,
        market_type="上市",  # 0050 成分股皆為市值前段的上市公司，非上櫃
    )
    result = get_price_history(identity, months=_PRICE_FETCH_MONTHS)
    if not result.ok or not result.data:
        raise RuntimeError(result.error or "查無股價資料")

    bars = sorted(result.data, key=lambda b: b.trade_date)
    closes = [b.close for b in bars]
    if len(closes) < 5:
        raise RuntimeError("股價資料筆數過少，無法計算均線")

    ma_series = {window: simple_moving_average(closes, window) for window in _MA_WINDOWS}
    last_bar = bars[-1]
    ma5 = ma_series[5][-1]
    ma10 = ma_series[10][-1]
    ma20 = ma_series[20][-1]
    ma60 = ma_series[60][-1]
    tier = _classify_tier(last_bar.close, ma5, ma10, ma20, ma60)

    return MaScreenRow(
        stock_id=stock_id,
        company_name=company_name,
        trade_date=last_bar.trade_date,
        close=last_bar.close,
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        ma60=ma60,
        tier=tier,
    )


def screen_0050(max_workers: int = 6) -> MaScreenResult:
    """對 0050 全部成分股跑一次均線篩選。"""
    result = MaScreenResult(generated_at=date.today())
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_screen_one, stock_id, name): (stock_id, name)
            for stock_id, name in ETF_0050_CONSTITUENTS
        }
        for future in as_completed(futures):
            stock_id, name = futures[future]
            try:
                result.rows.append(future.result())
            except Exception as exc:  # noqa: BLE001 - 單檔失敗不可中止整個篩選
                result.skipped.append((stock_id, name, str(exc)))
    return result
