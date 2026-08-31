"""均線篩選：判斷股票最近一日收盤價站上或跌破幾條均線（5/10/20/60 日），
依站上/跌破的均線數量分成八個等級（多頭四級、空頭四級）。

分級是「巢狀」判定，不是各自獨立判斷：
- 四海遊龍：收盤價同時站上 5MA、10MA、20MA、60MA 四條均線
- 三陽開泰：站上 5MA、10MA、20MA（不論站上或跌破 60MA——若也站上 60MA，
  會被歸類到更高一級的「四海遊龍」，所以這裡看到的必定是跌破或無法判定 60MA 的情況）
- 短線翻多訊號：站上 5MA、10MA（同理，不含也站上 20MA 的情況）
- 準備短線翻多：只站上 5MA（不含也站上 10MA 的情況）
- 空頭四級（四面楚歌／三聲無奈／短線翻空／注意停損）是上述的鏡像版本，條件改成
  「跌破」對應數量的均線。

每檔股票只會落在其中一級，或落在「0」（多空訊號不一致，例如站上 5MA 但跌破
10MA，不列入八個等級）。單一股票查價失敗只會被記錄到 skipped，不會讓整批篩選
中止，跟其他 provider 的容錯原則一致（見 providers/base.py）。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date

from .etf0050_constituents import ETF_0050_CONSTITUENTS
from .etf0051_constituents import ETF_0051_CONSTITUENTS
from .kd import compute_kd
from .models import StockIdentity
from .moving_average import simple_moving_average
from .providers.price import get_price_history

_MA_WINDOWS = (5, 10, 20, 60)
_PRICE_FETCH_MONTHS = 6  # 約可涵蓋 100+ 交易日，60MA 計算所需的暖身資料足夠
_KD_WINDOW = 9  # 台股慣用的 KD 計算天數

# 上市市值前 150 大 = 0050（市值前 50 大）+ 0051（市值第 51~150 名），兩者互補不重疊。
TOP150_CONSTITUENTS: list[tuple[str, str]] = ETF_0050_CONSTITUENTS + ETF_0051_CONSTITUENTS

TIER_ORDER: tuple[int, ...] = (4, 3, 2, 1, -1, -2, -3, -4)

TIER_LABELS: dict[int, str] = {
    4: "四海遊龍",
    3: "三陽開泰",
    2: "短線翻多訊號",
    1: "準備短線翻多",
    -1: "注意停損，切勿追高",
    -2: "短線翻空，小心崩盤",
    -3: "三聲無奈，請別凹單",
    -4: "四面楚歌，岌岌可危",
}
TIER_DESCRIPTIONS: dict[int, str] = {
    4: "最近一日收盤價同時站上 5MA、10MA、20MA、60MA 四條均線",
    3: "最近一日收盤價站上 5MA、10MA、20MA 三條均線",
    2: "最近一日收盤價站上 5MA、10MA 兩條均線",
    1: "最近一日收盤價站上 5MA 一條均線",
    -1: "最近一日收盤價跌破 5MA 一條均線",
    -2: "最近一日收盤價跌破 5MA、10MA 兩條均線",
    -3: "最近一日收盤價跌破 5MA、10MA、20MA 三條均線",
    -4: "最近一日收盤價同時跌破 5MA、10MA、20MA、60MA 四條均線",
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
    tier: int  # 4/3/2/1（多頭）、-1/-2/-3/-4（空頭），或 0 表示多空訊號不一致
    # 這段暖身期間（約 6 個月）的完整每日序列，跟上面 ma5~ma60 只留「最近一日」
    # 的數字不同——保留下來是為了給技術分析圖表用（見 screen_page.py），四筆
    # 陣列彼此等長、同一個 index 對應同一個交易日。
    history_dates: list[date] = field(default_factory=list)
    history_close: list[float] = field(default_factory=list)
    # 開高低收（K 棒）需要的另外三個序列；close 沿用上面已經有的 history_close。
    history_open: list[float] = field(default_factory=list)
    history_high: list[float] = field(default_factory=list)
    history_low: list[float] = field(default_factory=list)
    history_ma5: list[float | None] = field(default_factory=list)
    history_ma10: list[float | None] = field(default_factory=list)
    history_ma20: list[float | None] = field(default_factory=list)
    history_ma60: list[float | None] = field(default_factory=list)
    history_k: list[float | None] = field(default_factory=list)
    history_d: list[float | None] = field(default_factory=list)


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

    below_5 = ma5 is not None and close < ma5
    below_10 = ma10 is not None and close < ma10
    below_20 = ma20 is not None and close < ma20
    below_60 = ma60 is not None and close < ma60
    if below_5 and below_10 and below_20 and below_60:
        return -4
    if below_5 and below_10 and below_20:
        return -3
    if below_5 and below_10:
        return -2
    if below_5:
        return -1
    return 0


def _screen_one(stock_id: str, company_name: str) -> MaScreenRow:
    identity = StockIdentity(
        stock_id=stock_id,
        company_name=company_name,
        market_type="上市",
    )
    result = get_price_history(identity, months=_PRICE_FETCH_MONTHS)
    if not result.ok or not result.data:
        raise RuntimeError(result.error or "查無股價資料")

    bars = sorted(result.data, key=lambda b: b.trade_date)
    closes = [b.close for b in bars]
    if len(closes) < 5:
        raise RuntimeError("股價資料筆數過少，無法計算均線")

    ma_series = {window: simple_moving_average(closes, window) for window in _MA_WINDOWS}
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    k_series, d_series = compute_kd(highs, lows, closes, window=_KD_WINDOW)
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
        history_dates=[b.trade_date for b in bars],
        history_close=closes,
        history_open=[b.open for b in bars],
        history_high=highs,
        history_low=lows,
        history_ma5=ma_series[5],
        history_ma10=ma_series[10],
        history_ma20=ma_series[20],
        history_ma60=ma_series[60],
        history_k=k_series,
        history_d=d_series,
    )


def screen_stocks(constituents: list[tuple[str, str]], max_workers: int = 6) -> MaScreenResult:
    """對指定的股票清單跑一次均線篩選。"""
    result = MaScreenResult(generated_at=date.today())
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_screen_one, stock_id, name): (stock_id, name)
            for stock_id, name in constituents
        }
        for future in as_completed(futures):
            stock_id, name = futures[future]
            try:
                result.rows.append(future.result())
            except Exception as exc:  # noqa: BLE001 - 單檔失敗不可中止整個篩選
                result.skipped.append((stock_id, name, str(exc)))
    return result


def screen_0050(max_workers: int = 6) -> MaScreenResult:
    """對 0050（市值前 50 大）成分股跑一次均線篩選，檔數少、可快速完成。"""
    return screen_stocks(ETF_0050_CONSTITUENTS, max_workers=max_workers)


def screen_top150(max_workers: int = 6) -> MaScreenResult:
    """對上市市值前 150 大（0050 + 0051 成分股）跑一次均線篩選。"""
    return screen_stocks(TOP150_CONSTITUENTS, max_workers=max_workers)
