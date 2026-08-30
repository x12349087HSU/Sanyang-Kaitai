"""FinMind REST API 的最小封裝（直接呼叫 requests，不依賴 finmind 套件）。"""
from __future__ import annotations

import requests

from . import config

_session = requests.Session()
_session.headers.update({"User-Agent": config.HTTP_USER_AGENT})


class FinMindError(Exception):
    pass


def fetch_dataset(
    dataset: str,
    *,
    data_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """呼叫 FinMind v4 data API，回傳 data 陣列。任何失敗都拋出 FinMindError，
    由呼叫端的 provider 接住並轉成 ProviderResult（絕不讓例外往上傳）。
    """
    params: dict[str, str] = {"dataset": dataset}
    if data_id:
        params["data_id"] = data_id
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if config.FINMIND_TOKEN:
        params["token"] = config.FINMIND_TOKEN

    try:
        resp = _session.get(config.FINMIND_BASE_URL, params=params, timeout=config.HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise FinMindError(f"FinMind HTTP 錯誤: {exc}") from exc
    except ValueError as exc:
        raise FinMindError(f"FinMind 回應非 JSON: {exc}") from exc

    if payload.get("status") not in (200, "200", None) and "data" not in payload:
        raise FinMindError(f"FinMind 回應錯誤: {payload.get('msg', payload)}")

    data = payload.get("data")
    if data is None:
        raise FinMindError("FinMind 回應缺少 data 欄位")
    return data
