"""12306 HTTP 客户端:会话、cookie、隐藏查询路径发现、车站表。"""

import json
import re
import sys
import time

try:
    import requests
except ImportError:  # pragma: no cover
    print("Error: 需要 requests。装一下: pip install requests", file=sys.stderr)
    raise SystemExit(1)

from .constants import (
    API_BASE, BASE_HEADERS, CACHE_DAYS, LEFT_TICKET_INIT, LCQUERY_INIT,
    MISSING_STATIONS, STATION_JS_FALLBACK, STATION_KEYS, WEB_URL,
)
from .utils import (
    cache_path, norm_station, norm_ticket_path, norm_transfer_path, write_cache,
)

# 抠不到路径时的 fallback。必须是当前真实值(实测 2026-10-05):
#   ticket_path   -> /otn/leftTicket/queryG
#   transfer_path -> /lcquery/queryG  ← 没有 /otn/,加了会被 302 到 passport
FALLBACK_PATHS = {
    "ticket_path": "/otn/leftTicket/queryG",
    "transfer_path": "/lcquery/queryG",
}


class Rail12306:
    def __init__(self, verbose=False):
        self.s = requests.Session()
        self.s.headers.update(BASE_HEADERS)
        self.verbose = verbose
        self._bootstrapped = False
        self.paths = {}
        self._stations = None

    def _log(self, *a):
        if self.verbose:
            print("[12306]", *a, file=sys.stderr)

    # ── 启动:拿 cookie + 抠隐藏查询路径 ──

    def bootstrap(self):
        """访问 init 页拿 cookie,并从页面里正则抠出两个隐藏查询路径。

        ⚠️ 必须用 Session 且**先访问两个 init 页**。
        冷启动裸发一次 lcQuery/init 抠不到 `lc_search_url` —— 那个变量只在有活跃
        会话时才渲染。参考项目 Joooook/12306-skill 就是死在这里。
        """
        if self._bootstrapped:
            return
        cached = cache_path("paths.json", CACHE_DAYS * 24)
        paths = json.loads(open(cached, encoding="utf-8").read()) if cached else None

        # cookie 必须每次现拿(短时效)
        for url in (LEFT_TICKET_INIT, LCQUERY_INIT):
            try:
                self.s.get(url, timeout=20)
            except requests.RequestException as e:
                raise RuntimeError(f"网络不通/被拒,访问 12306 失败: {e}")

        if not paths:
            paths = {}
            self._discover(paths, LEFT_TICKET_INIT, r"var CLeftTicketUrl = '(.+?)'",
                           "ticket_path")
            self._discover(paths, LCQUERY_INIT, r"var lc_search_url = '(.+?)'",
                           "transfer_path")
            write_cache("paths.json", json.dumps(paths, ensure_ascii=False))
        # 归一化。两条路径前缀规则不同,必须分别处理,别合并成一个函数。
        paths["ticket_path"] = norm_ticket_path(paths.get("ticket_path"))
        paths["transfer_path"] = norm_transfer_path(paths.get("transfer_path"))
        self.paths = paths
        self._bootstrapped = True
        self._log("paths:", paths)

    def _discover(self, paths, url, pattern, key):
        try:
            html = self.s.get(url, timeout=20).text
            m = re.search(pattern, html)
            paths[key] = m.group(1) if m else None
        except requests.RequestException:
            paths[key] = None
        if not paths.get(key):
            paths[key] = FALLBACK_PATHS[key]

    # ── 请求 ──

    def get(self, url, params=None, tries=3):
        last = None
        for i in range(tries):
            try:
                r = self.s.get(url, params=params, timeout=25)
                r.raise_for_status()
                return r
            except Exception as e:  # noqa: BLE001
                last = e
                self._log(f"请求失败({i + 1}/{tries}):", e)
                time.sleep(1.2 * (i + 1))
        raise RuntimeError(f"请求 {url} 失败: {last}")

    def query_get(self, url, params):
        """查询接口(余票/中转/经停站)。**每次都实时拉,不做缓存。**

        经评估后去掉查询缓存:实测一个会话 40+ 次实时查询,12306 零限流,
        那个 90 秒缓存没解决过任何真实问题,反而引入了「缓存无限累积」的缺陷。

        本方法只保留两样东西:HTTP 重试退避(在 get 里)和错误可读化。
        """
        raw = self.get(url, params)
        if "text/html" in (raw.headers.get("Content-Type") or ""):
            raise RuntimeError(
                "12306 把接口 302 到登录页了(返回的是 HTML 不是 JSON)。"
                "多半是查询路径变了,跑 `refresh-cache` 重试。")
        try:
            return raw.json()
        except ValueError as e:
            raise RuntimeError(f"12306 返回的不是合法 JSON: {e}")

    # ── 车站表 ──

    def stations(self, refresh=False):
        """全国车站表 {telecode: {...}}。缓存 7 天。"""
        if not refresh and self._stations is not None:
            return self._stations
        cached = None if refresh else cache_path("stations.json", CACHE_DAYS * 24)
        if cached:
            self._stations = json.loads(open(cached, encoding="utf-8").read())
            return self._stations

        raw = None
        try:
            r = self.get(STATION_JS_FALLBACK)
            if "station_names" in r.text:
                raw = r.text
        except Exception as e:  # noqa: BLE001
            self._log("直连 station_name.js 失败,改走首页正则:", e)

        if raw is None:
            html = self.get(WEB_URL).text
            m = re.search(r"(/script/core/common/station_name.+?\.js)", html)
            if not m:
                raise RuntimeError("拿不到 station_name.js,12306 前端结构可能变了")
            raw = self.get(API_BASE + m.group(1)).text

        table = _parse_station_js(raw)
        write_cache("stations.json", json.dumps(table, ensure_ascii=False))
        self._stations = table
        return table

    def resolve(self, name_or_code):
        """中文站名 / 城市名 / telecode → telecode。找不到返回 None。"""
        table = self.stations()
        key = (name_or_code or "").strip()
        if not key:
            return None
        if re.fullmatch(r"[A-Z]{2,4}", key) and key in table:
            return key
        norm = norm_station(key)
        for st in table.values():
            if st["station_name"] == norm:
                return st["station_code"]
        # 退一步:精确匹配城市名(优先本城同名站)
        for st in table.values():
            if st.get("city") == norm:
                return st["station_code"]
        return None

    def station_name(self, telecode):
        return self.stations().get(telecode, {}).get("station_name", telecode)

    def name_map(self):
        return {k: v["station_name"] for k, v in self.stations().items()}


def _parse_station_js(raw):
    body = raw.replace("var station_names ='", "").replace("';", "").strip()
    flat = body.split("|")
    table = {}
    for i in range(len(flat) // 10):
        grp = flat[i * 10: i * 10 + 10]
        st = dict(zip(STATION_KEYS, grp))
        if st.get("station_code"):
            table[st["station_code"]] = st
    for st in MISSING_STATIONS:
        table.setdefault(st["station_code"], st)
    return table
