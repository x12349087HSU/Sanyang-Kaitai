"""共用 HTTP 存取邏輯：UA、逾時、重試、robots.txt 檢查、禮貌性延遲。"""
from __future__ import annotations

import threading
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from . import config

_last_request_at: dict[str, float] = {}
# 值是成功讀到的 RobotFileParser，或是 _ROBOTS_UNREADABLE 這個 sentinel
# （代表這個 host 的 robots.txt 讀不到，之後一律視為允許，見下方說明）。
_robots_cache: dict[str, "urllib.robotparser.RobotFileParser | object"] = {}
_ROBOTS_UNREADABLE = object()
# ma_screener.screen_stocks() 用 ThreadPoolExecutor 平行處理多檔股票，每個
# worker thread 都可能同時呼叫 is_allowed_by_robots() 查同一個 host（例如
# FinMind 全部失敗、大家一起 fallback 到證交所時）。沒有這把鎖時，多個
# thread 會在 `_robots_cache.get(host)` 都拿到 None 的那個瞬間各自重複發出
# robots.txt 請求——不只是浪費請求，若目標網站對短時間內大量並發連線比較
# 敏感（例如觸發雲端主機常見的流量防護），不同 thread 各自拿到的 fetch
# 結果可能不一致（有的成功、有的被擋），導致「同一批股票裡，有些被判定
# robots 允許、有些被判定不允許」這種看起來像隨機的不一致行為。
_robots_lock = threading.Lock()

_session = requests.Session()
_session.headers.update({"User-Agent": config.HTTP_USER_AGENT})


def _host(url: str) -> str:
    return urlparse(url).netloc


def is_allowed_by_robots(url: str) -> bool:
    """檢查 robots.txt 是否允許存取此 URL。任何解析失敗都視為「允許」，
    避免把邊角案例誤判為封鎖而讓整個來源被跳過。

    用鎖包住「查快取、沒有才抓 robots.txt、寫回快取」這整段：確保同一個
    host 的 robots.txt 在多執行緒情況下只會真的抓一次，其他 thread 等這次
    抓完直接沿用結果，不會各自重複發請求、也不會因為各自獨立抓取的結果
    不一致而讓同一批股票出現不同的允許/不允許判定（見上方模組層級註解）。

    已修正的 bug：robots.txt 讀取失敗時（例如證交所網站的憑證缺少
    Subject Key Identifier 這個擴充欄位，導致 Python 內建 urllib 的 SSL
    驗證失敗，即使 requests/curl 都能正常連得上），原本會把那個「讀取失敗、
    完全空的」RobotFileParser 物件直接存進快取——問題是 RobotFileParser
    自己的 can_fetch() 在從未成功讀取過（last_checked 是 0）的情況下預設
    回傳 False（不允許），跟原本註解假設的「空 parser 預設允許」剛好相反。
    後果是：同一個 host 第一次讀取失敗時這次呼叫本身沒事（有 except 擋著
    直接回傳 True），但快取裡存的這個「讀取失敗」的 parser 物件，會讓同一個
    host 之後每一次呼叫都改成直接呼叫這個壞掉的 parser 的 can_fetch()，
    每次都回傳 False——等於「第一次允許，之後全部不允許」，跟原本想要的
    「讀不到 robots.txt 就永遠視為允許」正好相反。改用一個獨立的 sentinel
    （_ROBOTS_UNREADABLE）明確記錄「這個 host 讀不到 robots.txt」，之後
    每次查到都直接回傳 True，不再去呼叫壞掉的 parser。"""
    host = _host(url)
    with _robots_lock:
        cached = _robots_cache.get(host)
        if cached is None:
            parser = urllib.robotparser.RobotFileParser()
            robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception:
                _robots_cache[host] = _ROBOTS_UNREADABLE
                return True
            _robots_cache[host] = parser
            cached = parser
        if cached is _ROBOTS_UNREADABLE:
            return True
        try:
            return cached.can_fetch(config.HTTP_USER_AGENT, url)
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
