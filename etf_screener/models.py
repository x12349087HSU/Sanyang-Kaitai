"""共用資料結構。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Generic, Optional, TypeVar


@dataclass
class StockIdentity:
    stock_id: str
    company_name: str
    market_type: str  # "上市" / "上櫃" / "未知"


@dataclass
class PriceBar:
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


T = TypeVar("T")


@dataclass
class ProviderResult(Generic[T]):
    """所有 provider 的統一回傳型別：永不對外拋出例外。"""

    ok: bool
    data: Optional[T]
    source_name: str
    error: str = ""

    @staticmethod
    def success(data: T, source_name: str) -> "ProviderResult[T]":
        return ProviderResult(ok=True, data=data, source_name=source_name, error="")

    @staticmethod
    def failure(source_name: str, error: str) -> "ProviderResult[T]":
        return ProviderResult(ok=False, data=None, source_name=source_name, error=error)
