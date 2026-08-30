"""簡易 JSON 檔案快取（含 TTL），減少重複打 API。"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import config


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return config.CACHE_DIR / f"{digest}.json"


def get(key: str, ttl_seconds: int) -> Optional[Any]:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - payload.get("_cached_at", 0) > ttl_seconds:
        return None
    return payload.get("data")


def set(key: str, data: Any) -> None:
    path = _cache_path(key)
    try:
        path.write_text(
            json.dumps({"_cached_at": time.time(), "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass  # 快取寫入失敗不應影響主流程


def cached_call(key: str, ttl_seconds: int, fn: Callable[[], Any]) -> Any:
    """先查快取，沒有才呼叫 fn() 並存回快取。fn() 若拋出例外會往外傳。"""
    hit = get(key, ttl_seconds)
    if hit is not None:
        return hit
    result = fn()
    if result is not None:
        set(key, result)
    return result
