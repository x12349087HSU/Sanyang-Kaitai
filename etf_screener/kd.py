"""KD 隨機指標（Stochastic Oscillator）計算，台股慣用的 9 日 RSV + 2/3、1/3 平滑法。"""
from __future__ import annotations


def compute_kd(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    window: int = 9,
) -> tuple[list[float | None], list[float | None]]:
    """回傳 (K 序列, D 序列)，長度與輸入等長，索引一一對應。

    前 window-1 筆資料不足以算出 RSV（未成年比較區間），K/D 為 None；第一筆
    算得出 RSV 的位置，K/D 起始值用慣例的 50 當種子往後平滑（K 用前一日
    K 的 2/3 + 本日 RSV 的 1/3，D 用前一日 D 的 2/3 + 本日 K 的 1/3）。
    """
    n = len(closes)
    k_values: list[float | None] = [None] * n
    d_values: list[float | None] = [None] * n
    prev_k = 50.0
    prev_d = 50.0
    for i in range(n):
        if i < window - 1:
            continue
        window_high = max(highs[i - window + 1 : i + 1])
        window_low = min(lows[i - window + 1 : i + 1])
        if window_high == window_low:
            rsv = 50.0
        else:
            rsv = (closes[i] - window_low) / (window_high - window_low) * 100
        k = prev_k * 2 / 3 + rsv * 1 / 3
        d = prev_d * 2 / 3 + k * 1 / 3
        k_values[i] = k
        d_values[i] = d
        prev_k = k
        prev_d = d
    return k_values, d_values
