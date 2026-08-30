"""Provider 共用慣例：任何 provider 函式都必須回傳 ProviderResult，絕不對外拋出例外。"""
from __future__ import annotations

import functools
import logging
from typing import Callable, TypeVar

from ..models import ProviderResult

logger = logging.getLogger("etf_screener.providers")

T = TypeVar("T")


def safe_provider(source_name: str):
    """裝飾器：包住 provider 函式，把任何例外轉成 ProviderResult.failure，
    確保單一資料來源的錯誤永遠不會讓呼叫端崩潰。"""

    def decorator(fn: Callable[..., T]) -> Callable[..., "ProviderResult[T]"]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> "ProviderResult[T]":
            try:
                data = fn(*args, **kwargs)
                if data is None:
                    return ProviderResult.failure(source_name, "回傳資料為空")
                return ProviderResult.success(data, source_name)
            except Exception as exc:  # noqa: BLE001 - 這裡就是要接住所有例外
                logger.warning("%s 失敗: %s", source_name, exc)
                return ProviderResult.failure(source_name, str(exc))

        return wrapper

    return decorator
