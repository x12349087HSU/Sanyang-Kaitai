"""簡單移動平均線（SMA）計算。"""
from __future__ import annotations


def simple_moving_average(values: list[float], window: int) -> list[float | None]:
    """回傳與 values 等長的串列；索引 i 對應「以 values[i] 結尾、往前數 window 筆」
    的移動平均，資料筆數不足 window 時該位置為 None。"""
    out: list[float | None] = []
    running_sum = 0.0
    for i, v in enumerate(values):
        running_sum += v
        if i >= window:
            running_sum -= values[i - window]
        out.append(running_sum / window if i >= window - 1 else None)
    return out
