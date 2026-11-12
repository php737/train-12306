"""2026 版《列车车次编排规定》——车次字头改革的跨字头兼容。

2026-11-25 0 时起,普速旅客列车启用新车次:
    原 T 字头(特快)→ N 字头   原 K 字头及无字头数字号段 → V 字头   Z 字头保留
**号段数字也会重排**,不是简单换字母:实测 T290(南宁→北京西)在 11-26 变成 **N6**,
不是 N290。所以「查不到就换个字母再查」这条路走不通 —— V290 是另一趟昆山→成都的车。

可靠的身份键是 `train_no[:6]`(车底号段前缀)+ 起点 + 时刻 + 终点:
    T290  train_no=710000T2900C  南宁 15:38 → 北京西 18:09
    N6    train_no=71000000N600  南宁 15:38 → 北京西 18:09   ← 同一趟车
单独用 train_no[:6] 不唯一(K158 和 T290 同为 710000),必须叠加时刻和起终点。

本模块的用途:查经停站(route)时,用户给的车次号在目标日期可能已改号,
这时跨改革边界把「同一趟车」在新日期下的车次号找出来。
"""

from .constants import API_BASE, REFORM_PS_DATE, SEARCH_API_BASE, TRAIN_ROUTE_PATH
from .utils import add_days, today_cst

SEARCH_API = f"{SEARCH_API_BASE}/search/v1/train/search"

# 预售期 15 天(含当天)→ 可查的最远日期
PRESALE_DAYS = 15


def _search_train(c, code, date):
    """车次号 → search 接口的那条记录。**必须精确匹配字头+号段**,
    否则 'V108' 会命中 'V1080'、'N6' 会命中 'N67'。"""
    data = c.query_get(SEARCH_API, {
        "keyword": code, "date": date.replace("-", "")}) or {}
    rows = data.get("data") or []
    exact = [r for r in rows
             if (r.get("station_train_code") or "").upper() == code.upper()]
    return exact[0] if exact else None


def _route_rows(c, train_no, date):
    """经停站接口 → 站点列表。"""
    r = c.query_get(f"{API_BASE}{TRAIN_ROUTE_PATH}", {
        "leftTicketDTO.train_no": train_no,
        "leftTicketDTO.train_date": date, "rand_code": ""})
    return (r.get("data") or {}).get("data") or []


def _probe_dates(target_date):
    """「另一侧」可用的探测日期 —— 必须同时落在预售期窗口内。

    目标日期在改革后 → 往改革前找同一趟车;目标在改革前 → 往改革后找。
    """
    today = today_cst()
    horizon = add_days(today, PRESALE_DAYS - 1)
    out = []
    if target_date >= REFORM_PS_DATE:
        d = REFORM_PS_DATE
        while d >= today:
            out.append(d)
            d = add_days(d, -1)
        out.reverse()          # 越接近改革日越可能是同一趟车
    else:
        d = REFORM_PS_DATE
        while d <= horizon:
            out.append(d)
            d = add_days(d, 1)
    return [d for d in out if today <= d <= horizon]


def _find_same_train(c, old, target_date):
    """在目标日期上找到「同一趟车」的新记录。

    old: search 记录 + 出发时刻 `_start` / 到达时刻 `_arrive`
    匹配条件:train_no[:6] 相同 + 起点相同 + 终点相同 + 出发时刻相同 + 到达时刻相同。
    """
    fr = c.resolve(old.get("from_station") or "")
    to = c.resolve(old.get("to_station") or "")
    if not fr or not to:
        return None
    data = c.query_get(f"{API_BASE}{c.paths['ticket_path']}", {
        "leftTicketDTO.train_date": target_date,
        "leftTicketDTO.from_station": fr,
        "leftTicketDTO.to_station": to,
        "purpose_codes": "ADULT",
    }) or {}
    fam = (old.get("train_no") or "")[:6]
    for item in (data.get("data") or {}).get("result") or []:
        v = item.split("|")
        if len(v) < 48:
            continue
        code, tno = v[3], v[2]
        if not tno.startswith(fam):
            continue
        if v[6] != fr or v[7] != to:
            continue
        if v[8] != old.get("_start") or v[9] != old.get("_arrive"):
            continue
        return {"station_train_code": code, "train_no": tno,
                "from_station": old.get("from_station"),
                "to_station": old.get("to_station")}
    return None


def resolve_train(c, code, date):
    """route 用:解析 (车次号, 日期) → 真正能查经停站的那条记录。

    返回 dict: {code, train_no, date, note}。note 说明车次号是否被改过。
    查不到返回 None。
    """
    direct = _search_train(c, code, date)
    if direct:
        return {"code": code.upper(), "train_no": direct["train_no"],
                "date": date, "note": ""}

    # 直接查不到 → 跨改革边界找同一趟车
    for probe in _probe_dates(date):
        old = _search_train(c, code, probe)
        if not old:
            continue
        rows = _route_rows(c, old["train_no"], probe)
        if not rows:
            continue
        old = dict(old)
        old["_start"] = rows[0].get("start_time")      # 始发站发车时刻
        old["_arrive"] = rows[-1].get("arrive_time")   # 终到站到达时刻
        hit = _find_same_train(c, old, date)
        if hit:
            return {"code": hit["station_train_code"], "train_no": hit["train_no"],
                    "date": date,
                    "note": (f"该车次号在 {date} 已改号:{code.upper()} → "
                             f"{hit['station_train_code']}。2026-11-25 起普速列车"
                             f"启用新车次字头,号段数字也一并重排,不只是换字母。")}
    return None
