"""跨日期对比:一次看多个日期的票量,帮用户挑「哪天走最松」。

以前这个只能靠临时脚本跑,2026-10-05 固化成子命令。
"""

import sys

from .client import Rail12306
from .constants import API_BASE
from .filters import avail_tier, count_ze_available, filter_and_sort
from .formatting import _table, md_table
from .parsing import parse_tickets
from .utils import add_days, today_cst

CMP_HEADERS = ["日期", "总车次", "✅有座", "🟡仅无座", "❌无票", "二等座有票", "二等座价"]


def _fetch(client, date, fr, to, types, after, before):
    data = client.query_get(f"{API_BASE}{client.paths['ticket_path']}", {
        "leftTicketDTO.train_date": date,
        "leftTicketDTO.from_station": fr,
        "leftTicketDTO.to_station": to,
        "purpose_codes": "ADULT",
    })
    if not data.get("status"):
        raise RuntimeError(data.get("messages") or "12306 返回异常")
    rows = parse_tickets((data.get("data") or {}).get("result"), client.name_map())
    return filter_and_sort(rows, types, after, before)


def _summarize(date, rows):
    seat = wz = none = 0
    for r in rows:
        t = avail_tier(r)
        if t == "seat":
            seat += 1
        elif t == "wz":
            wz += 1
        else:
            none += 1
    ze = [p["price"] for r in rows for p in r["prices"] if p["short"] == "ze"]
    return {
        "date": date, "total": len(rows), "seat": seat, "wz": wz, "none": none,
        "ze_ok": sum(count_ze_available(r) for r in rows),
        "ze_range": f"{min(ze):g}~{max(ze):g}" if ze else "—",
        "from_codes": sorted({r["from_code"] for r in rows}),
    }


def _advise(stats):
    """给出「哪天走」的建议 —— 这是这个子命令存在的意义。"""
    with_ze = [s for s in stats if s["ze_ok"] > 0]
    if not with_ze:
        return ("❌ 所列日期**二等座全部无票**。可以改买一等座/商务座,或换个出发站/中转方案。")
    best = max(with_ze, key=lambda s: (s["ze_ok"], s["seat"]))
    return (f"✅ **推荐 {best['date']}** —— 二等座有票 {best['ze_ok']} 趟,"
            f"有座车次共 {best['seat']} 趟。"
            f"二等座参考价 {best['ze_range']}元。")


def compare_dates(frm, to, dates, types="", after=0, before=24, verbose=False):
    """核心:逐日查余票并汇总。返回 stats 列表。"""
    c = Rail12306(verbose=verbose)
    c.bootstrap()
    fr, t = c.resolve(frm), c.resolve(to)
    if not fr or not t:
        raise RuntimeError(f"车站没解析出来: {frm}→{fr} / {to}→{t}")
    stats, errors = [], []
    for d in dates:
        if d < today_cst():
            errors.append(f"{d}: 日期早于今天,跳过")
            continue
        try:
            rows = _fetch(c, d, fr, t, types, after, before)
            stats.append(_summarize(d, rows))
        except RuntimeError as e:
            errors.append(f"{d}: {e}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{d}: {type(e).__name__}: {e}")
    return stats, errors, (frm if c.resolve(frm) else ""), fr


def render(stats, errors, frm, to, requested_code, fmt="md"):
    if not stats:
        return "❌ 所有日期都没查到数据:\n" + "\n".join(f"  - {e}" for e in errors)

    rows = [[s["date"], s["total"], s["seat"], s["wz"], s["none"],
             s["ze_ok"], s["ze_range"] + "元" if s["ze_range"] != "—" else "—"]
            for s in stats]

    # 发车站和请求的不一致时必须讲清楚(同城配对站错位,实测踩过)
    warn = ""
    codes = {c for s in stats for c in s["from_codes"]}
    if len(codes) > 1:
        warn = (f"\n> ⚠️ 这些车次的实际发车站不止一个: {', '.join(sorted(codes))}。"
                f"你查的是 `{frm}`({requested_code}),部分车次实际从别的站发车,"
                f"报结果前请核对。\n")

    body = (md_table(CMP_HEADERS, rows) if fmt == "md"
            else _table(CMP_HEADERS, rows))
    title = (f"### 📊 {frm} → {to} 跨日期票量对比" if fmt == "md"
             else f"📊 {frm} → {to} 跨日期票量对比")
    out = [title, "", body, "", _advise(stats)]
    if warn:
        out.insert(3, warn)
    if errors:
        out += ["", "> ⚠️ 部分日期失败: " + "; ".join(errors)]
    return "\n".join(out)


def cmd_compare(args):
    if args.dates:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    else:
        start = args.start or today_cst()
        dates = [add_days(start, i) for i in range(max(1, args.days))]
    if not dates:
        print("❌ 至少要一个日期(--dates 或 --start + --days)", file=sys.stderr)
        sys.exit(1)
    stats, errors, frm, code = compare_dates(
        args.frm, args.to, dates, args.type, args.after, args.before, args.verbose)
    print(render(stats, errors, args.frm, args.to, code, args.format))
