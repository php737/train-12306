"""输出格式化:对齐文本表格 / Markdown 表格 / 各查询结果的呈现。"""

import re

from .constants import SEAT_RANK
from .filters import avail_tier, has_ticket


# ── 宽度对齐(本机没装 tabulate,自己算东亚字符宽度)──


def _h(s):
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def _pad(s, w):
    s = str(s)
    return s + " " * max(0, w - _h(s))


def _table(headers, rows):
    widths = [max(_h(headers[i]), max((_h(r[i]) for r in rows), default=0))
              for i, _h_ in enumerate(headers)]
    out = [" | ".join(_pad(h, widths[i]) for i, h in enumerate(headers)),
           "-+-".join("-" * widths[i] for i in range(len(headers)))]
    for r in rows:
        out.append(" | ".join(_pad(c, widths[i]) for i, c in enumerate(r)))
    return "\n".join(out)


def md_table(headers, rows):
    """标准 Markdown 表格。**不加代码块围栏** —— 按需求方反馈改为表格输出,
    加了围栏 webchat 会当源码显示、不渲染表格。"""
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


# ── 席别 ──


def fmt_num(raw):
    if raw in (None, ""):
        return "—"
    if re.fullmatch(r"\d+", str(raw)):
        n = int(raw)
        return "无票" if n == 0 else str(n)
    if raw in ("有", "充足"):
        return "有"
    if raw in ("无", "--", "候补"):
        return "无"
    return str(raw)


def price_of(p):
    v = p.get("price")
    return f"{v:g}元" if isinstance(v, (int, float)) else "—"


def fmt_seats(row, only_available=True, limit=6):
    """席别 + 余票 + 票价。

    两条讲究(经反馈修正):
    1. 按「席别重要性」排序,不按接口返回顺序。12306 返回顺序常把商务座排最前,
       但大多数人买的是二等座。默认 二等座→一等座→商务座→…→无座。
    2. 二等座/一等座即使无票也要显式标出来(如「(二等座❌421.5元)」),
       否则用户看到「商务座 有」会误以为这趟有二等座。
    limit 至少 6,否则排在后面的「无座」会被截掉。
    """
    ps = sorted(row.get("prices", []),
                key=lambda p: (SEAT_RANK.get(p["short"], 99), p.get("price", 1e9)))
    ze = next((p for p in ps if p["short"] == "ze"), None)
    if not only_available:
        return " / ".join(f"{p['seat']} {fmt_num(p['num'])} {price_of(p)}"
                          for p in ps[:limit])
    shown = [p for p in ps if has_ticket(p)][:limit]
    if not shown:
        return "❌ 无票 (二等座参考价 " + price_of(ze) + ")"
    txt = " / ".join(f"{p['seat']} {fmt_num(p['num'])} {price_of(p)}" for p in shown)
    missing = [p for p in ps if p["short"] in ("ze", "zy") and not has_ticket(p)]
    if missing:
        txt += "  " + " ".join(f"({p['seat']}❌{price_of(p)})" for p in missing)
    return txt


# ── 余票 ──

MD_HEADERS = ["车次", "余票", "出发", "开车", "到达", "到达时间", "历时", "有票席别 / 票价"]
_BADGE = {"seat": "✅", "wz": "🟡", "none": "❌"}


def _seat_cell(row):
    tier = avail_tier(row)
    if tier == "none":
        ze = next((p for p in row.get("prices", []) if p["short"] == "ze"), {})
        return "❌ 无票 " + price_of(ze)
    return fmt_seats(row, only_available=True, limit=6)


def _md_ticket_row(r):
    arrived = r["arrive_time"] + ("⁺¹" if r["arrive_date"] != r["start_date"] else "")
    return [r["code"], _BADGE[avail_tier(r)], r["from"], r["start_time"], r["to"],
            arrived, r["lishi"], _seat_cell(r)]


def fmt_tickets(rows, date, fr, to):
    if not rows:
        return f"❌ 没查到 {date} {fr} → {to} 的车次(试试去掉 --type 过滤,或换个日期)"
    lines = [f"🚄 {date} {fr} → {to} —— 共 {len(rows)} 趟", ""]
    lines.append(_table(
        ["车次", "余票", "出发", "开车", "到达", "到达时间", "历时", "有票席别 / 票价"],
        [_md_ticket_row(r) for r in rows]))
    lines.append("")
    lines.append("图例: ✅ 有座票 ｜ 🟡 仅无座 ｜ ❌ 无票(括号内为二等座参考价)")
    tagged = [r for r in rows if r.get("flags")]
    if tagged:
        lines += ["", "🏷️ 特色: " + "; ".join(
            f"{r['code']}({'/'.join(r['flags'])})" for r in tagged[:8])]
    return "\n".join(lines)


def fmt_tickets_md(rows, date, fr, to):
    if not rows:
        return f"❌ 没查到 {date} {fr} → {to} 的车次"
    return "\n".join([f"### 🚄 {date} {fr} → {to} —— 共 {len(rows)} 趟", "",
                      md_table(MD_HEADERS, [_md_ticket_row(r) for r in rows]),
                      "", "> ✅ 有座票 ｜ 🟡 仅无座 ｜ ❌ 无票(尾价 = 二等座参考价)｜ ⁺¹ = 次日到达"])


def _bucket(rows):
    b = {"seat": [], "wz": [], "none": []}
    for r in rows:
        b[avail_tier(r)].append(r)
    return b


def fmt_tickets_summary(rows, date, fr, to):
    if not rows:
        return f"❌ 没查到 {date} {fr} → {to} 的车次"
    b = _bucket(rows)
    out = [f"📊 {date} {fr} → {to} 共 {len(rows)} 趟",
           f"   ✅ 有座 {len(b['seat'])} ｜ 🟡 仅无座 {len(b['wz'])} "
           f"｜ ❌ 无票 {len(b['none'])}", ""]
    for tier, label, badge in (("seat", "有座票", "✅"), ("wz", "仅无座(站票)", "🟡")):
        group = b[tier]
        if not group:
            continue
        out.append(f"{badge} {label} {len(group)} 趟:")
        for r in sorted(group, key=lambda x: x["start_time"]):
            cross = " (次日)" if r["arrive_date"] != r["start_date"] else ""
            out.append(f"   {r['code']:<7} {r['start_time']} → {r['arrive_time']}{cross}"
                       f"  {r['lishi']}  {r['from']}→{r['to']}  {fmt_seats(r, limit=6)}")
        out.append("")
    if b["none"]:
        out.append(f"❌ 无票 {len(b['none'])} 趟({_ze_price_range(b['none'])})")
    return "\n".join(out)


def fmt_tickets_summary_md(rows, date, fr, to):
    if not rows:
        return f"❌ 没查到 {date} {fr} → {to} 的车次"
    b = _bucket(rows)
    ze_ok = sum(1 for r in rows for p in r["prices"] if p["short"] == "ze" and has_ticket(p))
    out = [f"### 📊 {date} {fr} → {to} —— 共 {len(rows)} 趟", "",
           "| ✅ 有座 | 🟡 仅无座 | ❌ 无票 | 二等座有票 |",
           "|---|---|---|---|",
           f"| **{len(b['seat'])}** | **{len(b['wz'])}** | "
           f"**{len(b['none'])}** | **{ze_ok}** |", ""]
    for tier, title in (("seat", "✅ 有座票"), ("wz", "🟡 仅无座(站票)")):
        group = b[tier]
        if not group:
            continue
        out += [f"**{title} {len(group)} 趟**", "",
                md_table(MD_HEADERS,
                         [_md_ticket_row(r) for r in sorted(group,
                                                            key=lambda x: x["start_time"])]),
                ""]
    if b["none"]:
        out.append(f"❌ 无票 **{len(b['none'])}** 趟({_ze_price_range(b['none'])})")
    return "\n".join(out)


def _ze_price_range(rows):
    ze = [p["price"] for r in rows for p in r["prices"] if p["short"] == "ze"]
    rng = f"{min(ze):g}~{max(ze):g}元" if ze else "—"
    return f"二等座票价区间 {rng},仅供参考"


# ── 中转 ──


def _transfer_kind(r):
    return "同车换乘" if r["same_train"] else ("同站换乘" if r["same_station"] else "换站换乘")


def fmt_transfer(rows, date, fr, to):
    if not rows:
        return f"❌ 没查到 {date} {fr} → {to} 的中转方案"
    out = [f"🔄 {date} {fr} → {to} 中转方案 —— 共 {len(rows)} 种", ""]
    for i, r in enumerate(rows, 1):
        lines = [
            f"{i}. {r['start_date']} {r['start_time']} → {r['arrive_date']} {r['arrive_time']}"
            f" ｜ 总历时 {r['lishi']} ｜ {_transfer_kind(r)} ｜ 等待 {r.get('wait_time', '—')}",
            f"   {r['from_station_name']} → {r['middle_station_name']} → {r['end_station_name']}",
        ]
        for leg in r["legs"]:
            lines.append(f"   · {leg['code']} {leg['from']} {leg['start_time']} → "
                         f"{leg['to']} {leg['arrive_time']} ({leg['lishi']})  "
                         f"{fmt_seats(leg, limit=4)}")
        out += ["\n".join(lines), ""]
    return "\n".join(out)


def fmt_transfer_md(rows, date, fr, to):
    if not rows:
        return f"❌ 没查到 {date} {fr} → {to} 的中转方案"
    return "\n".join([
        f"### 🔄 {date} {fr} → {to} —— 共 {len(rows)} 种中转方案", "",
        md_table(["出发", "到达", "总历时", "路线", "换乘方式", "等待", "分段余票 / 票价"],
                 [[f"{r['start_date']} {r['start_time']}",
                   f"{r['arrive_date']} {r['arrive_time']}",
                   r["lishi"],
                   f"{r['from_station_name']} → {r['middle_station_name']} → {r['end_station_name']}",
                   _transfer_kind(r), r.get("wait_time", "—"),
                   "<br>".join(
                       f"{l['code']} {l['from']} {l['start_time']}→{l['to']} "
                       f"{l['arrive_time']} ({l['lishi']}) {fmt_seats(l, limit=3)}"
                       for l in r["legs"])]
                  for r in rows]),
        "", "> 换站换乘要拖行李出站,优先同站/同车"])


# ── 经停站 ──


def fmt_route(stations, train_code):
    if not stations:
        return "❌ 没查到该车次的经停信息"
    head = stations[0]
    title = f"🚃 {head.get('station_train_code', train_code)}次列车"
    if head.get("train_class_name"):
        title += (f"({head['train_class_name']} · "
                  f"{'有空调' if head.get('service_type') == '1' else '无空调'})")
    rows = [[i, s["station_name"], s.get("arrive_time", "--:--"),
             s.get("start_time", "--:--"), s.get("running_time", "")]
            for i, s in enumerate(stations, 1)]
    return "\n".join([title, "", _table(["#", "车站", "到达", "出发", "停留"], rows)])


def fmt_route_md(stations, train_code):
    if not stations:
        return "❌ 没查到该车次的经停信息"
    head = stations[0]
    title = f"### 🚃 {head.get('station_train_code', train_code)} 次列车经停站"
    if head.get("train_class_name"):
        title += (f"({head['train_class_name']} · "
                  f"{'有空调' if head.get('service_type') == '1' else '无空调'})")
    rows = [[i, s["station_name"], s.get("arrive_time", "--:--"),
             s.get("start_time", "--:--"), s.get("running_time", ""),
             s.get("arrive_day_str", "")]
            for i, s in enumerate(stations, 1)]
    return "\n".join([title, "", md_table(["#", "车站", "到达", "出发", "停留", "日"], rows)])
