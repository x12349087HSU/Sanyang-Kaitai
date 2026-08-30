"""共用 HTTP 存取邏輯：UA、逾時、重試、robots.txt 檢查、禮貌性延遲。"""
from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from . import config

_last_request_at: dict[str, float] = {}
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

_session = requests.Session()
_session.headers.update({"User-Agent": config.HTTP_USER_AGENT})


def _host(url: str) -> str:
    return urlparse(url).netloc


def is_allowed_by_robots(url: str) -> bool:
    """檢查 robots.txt 是否允許存取此 URL。任何解析失敗都視為「允許」，
    避免把邊角案例誤判為封鎖而讓整個來源被跳過。"""
    host = _host(url)
    parser = _robots_cache.get(host)
    if parser is None:
        parser = urllib.robotparser.RobotFileParser()
        robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
        parser.set_url(robots_url)
        try:
            parser.read()
        except Exception:
            _robots_cache[host] = parser  # 空 parser：can_fetch 預設回傳 True
            return True
        _robots_cache[host] = parser
    try:
        return parser.can_fetch(config.HTTP_USER_AGENT, url)
    except Exception:
        return True


def _respect_delay(host: str) -> None:
    last = _last_request_at.get(host, 0.0)
    wait = config.HTTP_MIN_DELAY_SECONDS - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    _last_request_at[host] = time.time()


class FetchBlocked(Exception):
    """robots.txt 不允許存取此 URL。"""


def get(url: str, *, params: dict | None = None, respect_robots: bool = True) -> requests.Response:
    """GET 一個 URL，含 robots 檢查、禮貌延遲與有限重試。
    失敗（含 403、逾時、robots 阻擋）一律拋出例外，由呼叫端的 provider 接住並轉成 ProviderResult。
    """
    if respect_robots and not is_allowed_by_robots(url):
        raise FetchBlocked(f"robots.txt disallows fetching {url}")

    host = _host(url)
    last_exc: Exception | None = None
    for attempt in range(config.HTTP_MAX_RETRIES + 1):
        _respect_delay(host)
        try:
            resp = _session.get(url, params=params, timeout=config.HTTP_TIMEOUT_SECONDS)
            if resp.status_code == 403:
                raise FetchBlocked(f"HTTP 403 for {url}")
            resp.raise_for_status()
            return resp
        except FetchBlocked:
            raise  # 403 不重試，直接視為封鎖並跳過
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < config.HTTP_MAX_RETRIES:
                time.sleep(config.HTTP_RETRY_BACKOFF_SECONDS * (attempt + 1))
    assert last_exc is not None
    raise last_exc
