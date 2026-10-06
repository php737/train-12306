"""12306 返回数据 → 结构化 dict。纯函数,不碰网络。"""

import re
from datetime import timedelta

from .constants import (
    DISCOUNT_CHUNK_LEN, DW_FLAGS, JUNK_LISHI, MAX_DURATION_MIN, PRICE_CHUNK_LEN,
    SEAT_TYPES, TICKET_KEYS,
)
from .utils import mk_datetime


def extract_prices(yp_info, seat_discount_info, rec):
    """解 yp_info_new → [{seat, short, num, price, discount}, ...]

    字段是定长字符串,每 PRICE_CHUNK_LEN(10) 一段:
      [0]      席别类型码
      [1:6]    票价 × 10(所以要 /10)
      [6:10]   该席位总数,>=3000 是 12306 前端逆向出来的魔数 → 视作无座
    """
    discounts = {}
    d = seat_discount_info or ""
    for i in range(len(d) // DISCOUNT_CHUNK_LEN):
        chunk = d[i * DISCOUNT_CHUNK_LEN:(i + 1) * DISCOUNT_CHUNK_LEN]
        try:
            discounts[chunk[0]] = int(chunk[1:])
        except ValueError:
            pass

    prices = []
    y = yp_info or ""
    for i in range(len(y) // PRICE_CHUNK_LEN):
        chunk = y[i * PRICE_CHUNK_LEN:(i + 1) * PRICE_CHUNK_LEN]
        try:
            total = int(chunk[6:10])
        except ValueError:
            continue
        if total >= 3000:
            code = "W"                      # 魔数:>=3000 视作无座
        elif chunk[0] not in SEAT_TYPES:
            code = "H"                      # 未知席别
        else:
            code = chunk[0]
        name, short = SEAT_TYPES.get(code, ("其他", "qt"))
        try:
            price = int(chunk[1:6]) / 10
        except ValueError:
            continue
        prices.append({
            "seat": name, "short": short,
            "num": rec.get(f"{short}_num", ""),
            "price": price,
            "discount": discounts.get(code),
        })
    return prices


def extract_dw_flags(raw):
    """解 dw_flag → 特色标签列表。"""
    parts = (raw or "").split("#")
    out = []
    if len(parts) > 0 and parts[0] == "5":
        out.append(DW_FLAGS[0])
    if len(parts) > 1 and parts[1] == "1":
        out.append(DW_FLAGS[1])
    if len(parts) > 2:
        if parts[2].startswith("Q"):
            out.append(DW_FLAGS[2])
        elif parts[2].startswith("R"):
            out.append(DW_FLAGS[3])
    if len(parts) > 5 and parts[5] == "D":
        out.append(DW_FLAGS[4])
    if len(parts) > 6 and parts[6] != "z":
        out.append(DW_FLAGS[5])
    if len(parts) > 7 and parts[7] != "z":
        out.append(DW_FLAGS[6])
    return out


def extract_lishi(all_lishi):
    """中转接口的历时形如「H小时M分钟」/「M分钟」,转成 hh:mm。"""
    m = re.search(r"(?:(\d+)小时)?(\d+?)分钟", all_lishi or "")
    if not m:
        return "00:00"
    return f"{(m.group(1) or '0').zfill(2)}:{m.group(2)}"


def parse_tickets(result_list, name_map):
    """余票接口的 result 数组 → 车次 dict 列表。

    做了脏数据过滤(实测 12306 会返回 `24:00→24:00 历时99:59 日期跨4天` 这种占位行)。
    """
    out = []
    for item in result_list or []:
        vals = item.split("|")
        if len(vals) < 48:
            continue
        rec = dict(zip(TICKET_KEYS, vals))
        if rec.get("lishi", "") in JUNK_LISHI:
            continue
        if rec.get("start_time") == rec.get("arrive_time"):
            continue
        try:
            base = mk_datetime(rec["start_train_date"], rec["start_time"])
            dh, dm = (int(x) for x in rec["lishi"].split(":"))
            arrive = base + timedelta(hours=dh, minutes=dm)
        except (ValueError, KeyError, TypeError):
            continue
        if dh * 60 + dm > MAX_DURATION_MIN:
            continue
        out.append({
            "train_no": rec["train_no"],
            "code": rec["station_train_code"],
            "from": name_map.get(rec["from_station_telecode"],
                                 rec["from_station_telecode"]),
            "to": name_map.get(rec["to_station_telecode"], rec["to_station_telecode"]),
            "from_code": rec["from_station_telecode"],
            "to_code": rec["to_station_telecode"],
            "start_date": base.strftime("%Y-%m-%d"),
            "start_time": rec["start_time"],
            "arrive_date": arrive.strftime("%Y-%m-%d"),
            "arrive_time": rec["arrive_time"],
            "lishi": rec["lishi"],
            "prices": extract_prices(rec.get("yp_info_new"),
                                     rec.get("seat_discount_info"), rec),
            "flags": extract_dw_flags(rec.get("dw_flag")),
        })
    return out


def parse_transfer(plans, default_date=""):
    """中转接口的 middleList → 方案 dict 列表,每个方案带 legs 分段。"""
    rows = []
    for p in plans or []:
        legs = []
        for leg in p.get("fullList", []):
            try:
                base = mk_datetime(leg["start_train_date"], leg["start_time"])
                dh, dm = (int(x) for x in leg["lishi"].split(":"))
                arr = base + timedelta(hours=dh, minutes=dm)
                arr_s = arr.strftime("%Y-%m-%d")
            except (ValueError, KeyError, TypeError):
                arr_s = p.get("arrive_date", "")
            legs.append({
                "code": leg.get("station_train_code", ""),
                "from": leg.get("from_station_name", ""),
                "to": leg.get("to_station_name", ""),
                "start_time": leg.get("start_time", ""),
                "arrive_time": leg.get("arrive_time", ""),
                "arrive_date": arr_s,
                "lishi": leg.get("lishi", ""),
                "prices": extract_prices(leg.get("yp_info"),
                                         leg.get("seat_discount_info"), leg),
                "flags": extract_dw_flags(leg.get("dw_flag")),
            })
        if not legs:
            continue
        rows.append({
            "start_date": p.get("train_date", default_date),
            "start_time": p.get("start_time", ""),
            "arrive_date": p.get("arrive_date", ""),
            "arrive_time": p.get("arrive_time", ""),
            "lishi": extract_lishi(p.get("all_lishi", "")),
            "from_station_name": p.get("from_station_name", ""),
            "middle_station_name": p.get("middle_station_name", ""),
            "end_station_name": p.get("end_station_name", ""),
            "same_train": p.get("same_train") == "Y",
            "same_station": p.get("same_station") == "0",
            "wait_time": p.get("wait_time", ""),
            "legs": legs,
        })
    return rows


def parse_route_stations(raw):
    """经停站接口的 data 数组 → 精简的站序 dict 列表。"""
    keep = ("station_name", "station_train_code", "arrive_time", "start_time",
            "running_time", "arrive_day_str", "train_class_name", "service_type",
            "end_station_name", "is_start", "station_no")
    return [{k: v for k, v in x.items() if k in keep} for x in (raw or [])]
