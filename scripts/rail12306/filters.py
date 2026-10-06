"""余票分类、车次类型过滤、排序。纯函数。"""

from .constants import FLAG_TYPES, PRIMARY_PREFIXES
from .utils import hmm_to_min


def has_ticket(price):
    """这个席别有没有票。注意「无座」也是一种票,但要单独统计。"""
    n = str(price.get("num", ""))
    if n in ("有", "充足"):
        return True
    return n.isdigit() and int(n) > 0


def avail_tier(row):
    """把一列车归类(经反馈修正:不能笼统说「有票」)。

    seat = 有正式座位(商务/一等/二等/硬卧...)
    wz   = 只有无座(站票)
    none = 完全没票
    """
    prices = row.get("prices") or []
    if any(has_ticket(p) and p["short"] != "wz" for p in prices):
        return "seat"
    if any(has_ticket(p) and p["short"] == "wz" for p in prices):
        return "wz"
    return "none"


def count_ze_available(row):
    """这趟车二等座有没有票。"""
    return sum(1 for p in row.get("prices", []) if p["short"] == "ze" and has_ticket(p))


def _row_code(row):
    """统一取车次字母。transfer 的行没有顶层 code,用第一段行程的车次。"""
    if "code" in row:
        return (row["code"] or "")[:1].upper()
    legs = row.get("legs") or []
    return legs[0].get("code", "")[:1].upper() if legs else ""


def _row_flags(row):
    if "flags" in row:
        return row.get("flags") or []
    flags = []
    for leg in row.get("legs") or []:
        flags += leg.get("flags") or []
    return flags


def match_types(row, wanted):
    """车次类型过滤。O = 其它类(非 G/C/D/Z/T/K),这是原 12306-mcp 的语义
    —— 12306 并不存在首字母为 O 的车次,别做成字面匹配。"""
    if not wanted:
        return True
    code = _row_code(row)
    flags = _row_flags(row)
    if code in wanted:
        return True
    # G 代表「高铁/城际」,同时包含 C
    if code in ("G", "C") and ("G" in wanted or "C" in wanted):
        return True
    for k, flag in FLAG_TYPES.items():
        if k in wanted and flag in flags:
            return True
    if "O" in wanted:
        if code in ("L", "Y", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
            return True
        if code and code not in PRIMARY_PREFIXES:
            return True
    return False


def filter_and_sort(rows, types="", earliest=0, latest=24, sort="", desc=False, limit=0):
    wanted = set(types.upper().replace(" ", "")) if types else set()
    res = [r for r in rows if match_types(r, wanted)]
    # % 24 是为了不把 24:xx 的深夜车次滤掉
    res = [r for r in res
           if earliest <= hmm_to_min(r["start_time"]) // 60 % 24 < latest]

    if sort:
        keys = {
            "startTime": lambda r: (r["start_date"], hmm_to_min(r["start_time"])),
            "arriveTime": lambda r: (r["arrive_date"], hmm_to_min(r["arrive_time"])),
            "duration": lambda r: hmm_to_min(r["lishi"]),
        }
        if sort in keys:
            res = sorted(res, key=keys[sort], reverse=desc)
    if limit and limit > 0:
        res = res[:limit]
    return res
