"""各子命令的实现。每个 cmd_* 接收 argparse 的 Namespace。"""

import json
import os
import sys

from .client import Rail12306
from .compare import cmd_compare
from .constants import API_BASE, CACHE_DIR, SEARCH_API_BASE, TRAIN_ROUTE_PATH
from .filters import avail_tier, filter_and_sort
from .formatting import (
    fmt_num, fmt_route, fmt_route_md, fmt_tickets, fmt_tickets_md,
    fmt_tickets_summary, fmt_tickets_summary_md, fmt_transfer, fmt_transfer_md,
    fmt_seats, price_of, _table,
)
from .parsing import parse_route_stations, parse_tickets, parse_transfer
from .utils import (
    drop_cache, gc_query_cache, norm_station, today_cst,
)


def cmd_today(args):
    print(today_cst())


def cmd_refresh_cache(args):
    """强制重拉车站表和查询路径。12306 改版报「重定向到登录页」时用。"""
    c = Rail12306(verbose=args.verbose)
    n = len(c.stations(refresh=True))
    drop_cache("paths.json")
    c.bootstrap()
    cleaned = gc_query_cache()
    print(f"♻️ 缓存已刷新:车站表 {n} 个,查询路径 {c.paths}"
          + (f",清理遗留查询缓存 {cleaned} 个" if cleaned else ""))


def cmd_stations(args):
    c = Rail12306(verbose=args.verbose)
    table = c.stations(refresh=args.refresh)

    if args.code:
        st = table.get(args.code.upper())
        print(json.dumps(st, ensure_ascii=False, indent=2) if st
              else f"❌ 没找到 telecode={args.code}")
        return

    if args.city:
        city = norm_station(args.city.strip())
        hit = [s for s in table.values()
               if s.get("city") == city or s["station_name"] == city]
        if not hit:
            print(f"❌ 没找到城市/车站: {args.city}")
            return
        rows = [[s["station_name"], s["station_code"], s.get("station_pinyin", "")]
                for s in sorted(hit, key=lambda x: x["station_code"])]
        print(_table(["车站", "telecode", "拼音"], rows))
        print(f"\n共 {len(rows)} 个车站(用具体站名查询余票更准)")
        return

    if args.name:
        for nm in args.name.split("|"):
            code = c.resolve(nm)
            print(f"{norm_station(nm)} → {code or '❌ 未找到'}")
        return

    print("用法: --city 北京 | --name 北京南|上海虹桥 | --code BJP", file=sys.stderr)


def _resolve_pair(args, c, middle=False):
    fr, to = c.resolve(args.frm), c.resolve(args.to)
    mid = c.resolve(args.middle) if (middle and args.middle) else ""
    if not fr or not to or (middle and args.middle and not mid):
        raise RuntimeError(f"车站没解析出来: {args.frm}→{fr} / {args.to}→{to}"
                           + (f" / {args.middle}→{mid}" if middle else ""))
    return fr, to, mid


def cmd_tickets(args):
    if args.date < today_cst():
        raise RuntimeError(f"查询日期 {args.date} 早于今天")
    c = Rail12306(verbose=args.verbose)
    c.bootstrap()
    fr, to, _ = _resolve_pair(args, c)

    data = c.query_get(f"{API_BASE}{c.paths['ticket_path']}", {
        "leftTicketDTO.train_date": args.date,
        "leftTicketDTO.from_station": fr,
        "leftTicketDTO.to_station": to,
        "purpose_codes": "ADULT",
    })
    if not data.get("status"):
        raise RuntimeError(f"12306 返回异常: {data.get('messages')}")

    rows = parse_tickets((data.get("data") or {}).get("result"), c.name_map())
    rows = filter_and_sort(rows, args.type, args.after, args.before,
                           args.sort, args.desc, args.limit)

    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.format == "md":
        print((fmt_tickets_summary_md if args.summary else fmt_tickets_md)(
            rows, args.date, args.frm, args.to))
    elif args.format == "csv":
        print("车次,余票,出发站,到达站,出发时间,到达时间,历时,"
              "二等座余票,二等座价,一等座余票,一等座价,无座余票,无座价")
        for x in rows:
            p = {q["short"]: q for q in x["prices"]}
            g = lambda k: p.get(k, {}).get("num", "")   # noqa: E731
            v = lambda k: price_of(p.get(k, {}))        # noqa: E731
            tier = {"seat": "有座", "wz": "仅无座", "none": "无票"}[avail_tier(x)]
            print(f"{x['code']},{tier},{x['from']},{x['to']},{x['start_time']},"
                  f"{x['arrive_time']},{x['lishi']},{g('ze')},{v('ze')},"
                  f"{g('zy')},{v('zy')},{g('wz')},{v('wz')}")
    elif args.summary:
        print(fmt_tickets_summary(rows, args.date, args.frm, args.to))
    else:
        print(fmt_tickets(rows, args.date, args.frm, args.to))


def cmd_transfer(args):
    if args.date < today_cst():
        raise RuntimeError(f"查询日期 {args.date} 早于今天")
    c = Rail12306(verbose=args.verbose)
    c.bootstrap()
    fr, to, mid = _resolve_pair(args, c, middle=True)

    params = {
        "train_date": args.date, "from_station_telecode": fr, "to_station_telecode": to,
        "middle_station": mid or "", "result_index": "0", "can_query": "Y",
        "isShowWZ": "Y" if args.wz else "N", "purpose_codes": "00", "channel": "E",
    }
    plans, guard = [], 0
    while len(plans) < args.limit and guard < 10:
        guard += 1
        resp = c.query_get(f"{API_BASE}{c.paths['transfer_path']}", params)
        d = resp.get("data")
        if isinstance(d, str):
            print(f"❌ 未查到相关中转余票({resp.get('errorMsg', '')})")
            return
        plans += d.get("middleList", [])
        if d.get("can_query") == "N":
            break
        params["result_index"] = str(d.get("result_index", 0))

    rows = filter_and_sort(parse_transfer(plans, args.date), args.type,
                           args.after, args.before, args.sort, args.desc, args.limit)
    print(json.dumps(rows, ensure_ascii=False, indent=2) if args.format == "json"
          else (fmt_transfer_md if args.format == "md" else fmt_transfer)(
              rows, args.date, args.frm, args.to))


def cmd_route(args):
    if args.date < today_cst():
        raise RuntimeError(f"查询日期 {args.date} 早于今天")
    c = Rail12306(verbose=args.verbose)
    c.bootstrap()
    s = c.query_get(f"{SEARCH_API_BASE}/search/v1/train/search", {
        "keyword": args.train, "date": args.date.replace("-", "")})
    if not s.get("data"):
        print(f"❌ 没查到车次 {args.train}(确认日期 {args.date} 有没有这趟车)")
        return
    r = c.query_get(f"{API_BASE}{TRAIN_ROUTE_PATH}", {
        "leftTicketDTO.train_no": s["data"][0]["train_no"],
        "leftTicketDTO.train_date": args.date, "rand_code": ""})
    stations = parse_route_stations((r.get("data") or {}).get("data"))
    if args.format == "json":
        print(json.dumps(stations, ensure_ascii=False, indent=2))
    elif args.format == "md":
        print(fmt_route_md(stations, args.train))
    else:
        print(fmt_route(stations, args.train))


__all__ = ["cmd_today", "cmd_refresh_cache", "cmd_stations", "cmd_tickets",
           "cmd_transfer", "cmd_route", "cmd_compare"]
