"""余票分类、车次类型过滤、排序。纯函数。"""

import re

from .constants import (
    FLAG_TYPES, PRIMARY_PREFIXES, PS_LETTERS_POST, PS_LETTERS_PRE,
    REFORM_PS_DATE, TYPE_ALIASES,
)
from .utils import hmm_to_min

# 类别码 → 实际字头集合。
#   PS = 普速旅客列车 / TE = 普速特快 / QU = 普速快速(这四个按查询日期展开)
#   其余就是字头本身;F / S 是特色标签(复兴号 / 智能动车组),不是字头。
ALIAS_CATEGORIES = {
    "PS": "PS", "TE": "TE", "QU": "QU",
    "Z": "Z", "G": "G", "X": "X", "D": "D", "C": "C",
    "F": "F", "S": "S",
}

# 改革过渡日:同一列车在 11-25 当天可能同时出现新旧两种表达,
# 所以过渡日的别名要同时展开成新旧两套字头。
TRANSITION_DAYS = {REFORM_PS_DATE}


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


def _expand_category(cat, date):
    """类别码 → 字头集合。普速三类按查询日期展开(改革前 ZTK / 改革后 ZNV)。"""
    if cat == "PS":
        if date in TRANSITION_DAYS:
            return set(PS_LETTERS_PRE) | set(PS_LETTERS_POST)
        return set(PS_LETTERS_POST if date and date >= REFORM_PS_DATE
                   else PS_LETTERS_PRE)
    if cat == "TE":
        if date in TRANSITION_DAYS:
            return {"T", "N"}
        return {"N"} if date and date >= REFORM_PS_DATE else {"T"}
    if cat == "QU":
        if date in TRANSITION_DAYS:
            return {"K", "V"}
        return {"V"} if date and date >= REFORM_PS_DATE else {"K"}
    return {cat}


def parse_type_spec(types, date=""):
    """把 --type 拆成待匹配的 token 集合。

    支持两种写法,可以混用:
      - **字头字母**: G D C Z T K N V X S F O,多字连写如 "GD"。字面量永远
        按字面意思匹配(12306 返回什么字头就匹配什么字头)。
      - **中文别名**: 普速 特快 快速 直特快 高铁 动车 城际 复兴号 智能动车组。
        别名按**查询日期**展开 —— 普速字头 2026-11-25 起由 Z/T/K 改为 Z/N/V,
        所以「特快」在改革前是 T、改革后是 N,写死字母就会错。

    分隔符:逗号 / 空格 / 顿号 / 竖线。
    """
    tokens = set()
    if not types:
        return tokens
    for tok in re.split(r"[,\s、|]+", types.strip()):
        if not tok:
            continue
        if tok in TYPE_ALIASES:
            for cat in TYPE_ALIASES[tok]:
                tokens |= _expand_category(cat, date)
            continue
        upper = tok.upper()
        if upper in ALIAS_CATEGORIES:
            tokens |= _expand_category(ALIAS_CATEGORIES[upper], date)
            continue
        # 兜底:当成字头字母串(GDCZ / TKO 之类)
        tokens |= set(upper)
    return tokens


def match_types(row, wanted):
    """车次类型过滤。O = 其它类(非 GCDZTKNV),这是原 12306-mcp 的语义
    —— 12306 并不存在首字母为 O 的车次,别做成字面匹配。
    F / S 是特色标签(复兴号 / 智能动车组),按 dw_flag 匹配而不是字头。
    """
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


def filter_and_sort(rows, types="", earliest=0, latest=24, sort="", desc=False,
                    limit=0, date=""):
    wanted = parse_type_spec(types, date)
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
