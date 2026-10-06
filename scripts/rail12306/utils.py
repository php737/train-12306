"""纯工具函数:时间、缓存、路径归一化。不涉及网络和业务逻辑。"""

import os
import time
from datetime import datetime, timedelta

from .constants import CACHE_DIR, SHANGHAI


# ── 缓存 ──


def cache_path(name, ttl_hours=168):
    """缓存文件在有效期内返回路径,否则返回 None。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    p = os.path.join(CACHE_DIR, name)
    if os.path.exists(p) and (time.time() - os.path.getmtime(p)) < ttl_hours * 3600:
        return p
    return None


def write_cache(name, content):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, name), "w", encoding="utf-8") as f:
        f.write(content)


def gc_query_cache():
    """清理遗留的 q_* 查询缓存。

    2026-10-05:查询缓存已彻底去掉(经评估,实测零限流),但历史写下的 q_*.json 还在 cache/ 里。
    这个函数负责清干净,refresh-cache 会调它。
    """
    if not os.path.isdir(CACHE_DIR):
        return 0
    removed = 0
    try:
        for f in os.listdir(CACHE_DIR):
            if f.startswith("q_") and f.endswith(".json"):
                try:
                    os.remove(os.path.join(CACHE_DIR, f))
                    removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def drop_cache(name):
    p = os.path.join(CACHE_DIR, name)
    try:
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass


# ── 时间 ──


def today_cst():
    return datetime.now(SHANGHAI).strftime("%Y-%m-%d")


def hmm_to_min(t):
    """'24:05' → 1445。12306 对深夜车次会给 24:xx(次日 00:xx 的写法),
    这里不归一,排序/比较都按绝对分钟数算才正确。"""
    try:
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def mk_datetime(date_str, hhmm, tz=SHANGHAI):
    """构造时刻。**必须处理 hour==24** —— 12306 会返回 '24:05' 表示次日 00:05,
    直接 .replace(hour=24) 会抛 ValueError,整趟车被静默丢弃(实测踩过)。"""
    d = datetime.strptime(date_str, "%Y%m%d")
    h, m = (int(x) for x in hhmm.split(":"))
    if h >= 24:            # 24:05 → 次日 00:05
        d = d + timedelta(days=h // 24)
        h = h % 24
    return d.replace(hour=h, minute=m, tzinfo=tz)


def add_days(date_str, n):
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


# ── 归一化 ──


def norm_station(s):
    """去掉末尾的「站」字。"""
    s = (s or "").strip()
    return s[:-1] if s.endswith("站") else s


def norm_ticket_path(p):
    """CLeftTicketUrl 抠出来可能是 'leftTicket/queryG'(无前导斜杠)也可能带 /otn/,
    统一成 /otn/leftTicket/xxx。"""
    if not p:
        return p
    p = p.strip()
    if not p.startswith("/"):
        p = "/" + p
    if not p.startswith("/otn/"):
        p = "/otn" + p
    return p


def norm_transfer_path(p):
    """lc_search_url 抠出来的是根路径(如 /lcquery/queryG),不在 /otn/ 下,
    所以这里只补前导斜杠,千万别加 /otn —— 加了会被 302 到 /otn/passport。"""
    if not p:
        return p
    p = p.strip()
    return p if p.startswith("/") else "/" + p
