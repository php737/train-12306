#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""train-12306 CLI 入口。

用法:
  python main.py <子命令> [参数]
  python main.py --help

子命令:
  today                          今天日期(Asia/Shanghai)
  refresh-cache                  强制重拉车站表和查询路径
  stations  --city/--name/--code  查车站 telecode
  tickets  --from --to           查余票(支持过站区间)
  compare  --from --to           跨日期票量对比 ⭐ 规划行程用
  transfer --from --to           查中转方案
  route    --train --date        查某趟车经停站
"""

import argparse
import os
import sys

# 允许直接从 scripts/ 目录运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rail12306.constants import VERSION          # noqa: E402
from rail12306.commands import (                  # noqa: E402
    cmd_compare, cmd_refresh_cache, cmd_route, cmd_stations, cmd_tickets,
    cmd_today, cmd_transfer,
)


def _add_filter_args(sp):
    """tickets / transfer / compare 共用的筛选参数。**别漏 --type**,
    2026-10-05 拆分时手写参数列表漏了它,导致 tickets/transfer 全部报错。"""
    sp.add_argument("--type", default="", help="车次类型过滤,如 G / GD / GDCZ TKO")
    sp.add_argument("--after", type=int, default=0, help="最早出发小时(0-24)")
    sp.add_argument("--before", type=int, default=24, help="最晚出发小时(0-24,不含)")


def _add_sort_args(sp, default_limit=0):
    """排序与条数。compare 不需要(它有自己的 --days/--start/--dates)。"""
    sp.add_argument("--sort", default="",
                    choices=["", "startTime", "arriveTime", "duration"])
    sp.add_argument("--desc", action="store_true", help="排序反转(最晚/最长在前)")
    sp.add_argument("--limit", type=int, default=default_limit,
                    help=f"结果条数上限,默认 {default_limit}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="train12306",
        description="12306 火车票查询 —— 只查余票/中转/经停站/跨日期对比,不代购票")
    p.add_argument("--verbose", action="store_true", help="打印调试日志到 stderr")
    p.add_argument("--version", action="version", version=f"train-12306 {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("today", help="今天日期(Asia/Shanghai)").set_defaults(fn=cmd_today)
    sub.add_parser("refresh-cache", help="强制重拉车站表和查询路径"
                   ).set_defaults(fn=cmd_refresh_cache)

    s = sub.add_parser("stations", help="查车站 telecode")
    s.add_argument("--city", help="中文城市名,如 北京")
    s.add_argument("--name", help="具体站名,多个用 | 分隔,如 北京南|上海虹桥")
    s.add_argument("--code", help="3-4 位 telecode,如 BJP")
    s.add_argument("--refresh", action="store_true", help="强制刷新车站表缓存")
    s.set_defaults(fn=cmd_stations)

    t = sub.add_parser("tickets", help="查余票(支持过站区间,如 杭州东→上海虹桥)")
    t.add_argument("--date", required=True, help="yyyy-MM-dd")
    t.add_argument("--from", dest="frm", required=True, help="出发站(中文名或 telecode)")
    t.add_argument("--to", required=True, help="到达站(中文名或 telecode)")
    t.add_argument("--summary", action="store_true",
                   help="按 有座/仅无座/无票 分层汇总,判断能不能走时用")
    _add_filter_args(t)
    _add_sort_args(t, 0)
    t.add_argument("--format", default="text", choices=["text", "json", "csv", "md"])
    t.set_defaults(fn=cmd_tickets)

    c = sub.add_parser("compare", help="跨日期票量对比 —— 挑哪天走最松 ⭐")
    c.add_argument("--from", dest="frm", required=True, help="出发站")
    c.add_argument("--to", required=True, help="到达站")
    c.add_argument("--start", help="起始日期 yyyy-MM-dd,默认今天")
    c.add_argument("--days", type=int, default=5, help="从 --start 起算几天,默认 5")
    c.add_argument("--dates", help="显式指定日期,逗号分隔,会覆盖 --start/--days")
    _add_filter_args(c)
    c.add_argument("--format", default="md", choices=["text", "md"])
    c.set_defaults(fn=cmd_compare)

    tr = sub.add_parser("transfer", help="查中转方案")
    tr.add_argument("--date", required=True, help="yyyy-MM-dd")
    tr.add_argument("--from", dest="frm", required=True)
    tr.add_argument("--to", required=True)
    tr.add_argument("--middle", default="", help="指定中转站(可选)")
    tr.add_argument("--wz", action="store_true", help="包含无座")
    _add_filter_args(tr)
    _add_sort_args(tr, 10)
    tr.add_argument("--format", default="text", choices=["text", "json", "md"])
    tr.set_defaults(fn=cmd_transfer)

    r = sub.add_parser("route", help="查某趟车经停站")
    r.add_argument("--train", required=True, help="车次号,如 G1033")
    r.add_argument("--date", required=True, help="yyyy-MM-dd")
    r.add_argument("--format", default="text", choices=["text", "json", "md"])
    r.set_defaults(fn=cmd_route)
    return p


def main():
    args = build_parser().parse_args()
    try:
        args.fn(args)
    except SystemExit:
        raise
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:  # noqa: BLE001
        # 12306 前端改版时很容易出 KeyError/TypeError,给可读信息而不是裸 traceback
        import traceback
        print(f"❌ 未预期的错误: {type(e).__name__}: {e}", file=sys.stderr)
        print("   加 --verbose 看细节;若是 KeyError,多半是 12306 返回结构变了,"
              "跑 refresh-cache 后重试。", file=sys.stderr)
        if os.environ.get("TRAIN12306_DEBUG"):
            traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
