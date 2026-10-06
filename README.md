# train-12306

> 12306 火车票查询 CLI —— 余票、中转、经停站、跨日期对比。
> **只查不卖**:不碰账号密码、不代下单、不代支付。

一个 Python 实现的 12306 查询工具,把余票、票价、席别、中转方案直接输出成对齐好的表格。
灵感来自 [Joooook/12306-mcp](https://github.com/Joooook/12306-mcp)(TypeScript),
用 Python 重写,零 npm 依赖。

## 特点

- **纯查询** —— 不涉及登录态、支付,不碰任何个人凭证
- **三层余票分类** —— 有座 / 仅无座 / 无票,把「有票」说清楚
- **票价始终输出** —— 席别、余票、票价一行看清,无票也给参考价
- **跨日期对比** —— 一条命令看清「哪天走最松」
- **多格式输出** —— 终端表格 / Markdown 表格 / CSV / JSON
- **自动提醒发车站错位** —— 12306 经常返回非请求站的列车,工具会主动告警

## 环境要求

- Python 3.9+
- `requests`

```bash
pip install requests
```

## 快速开始

```bash
M=scripts/main.py

# 查余票
python $M tickets --date 2026-10-08 --from 北京南 --to 上海虹桥

# 只要高铁/动车,按历时排序
python $M tickets --date 2026-10-08 --from 北京南 --to 上海虹桥 --type GDC --sort duration

# Markdown 表格(适合贴进文档/聊天)
python $M tickets --date 2026-10-08 --from 北京南 --to 上海虹桥 --summary --format md

# 跨日期对比:哪天走票最松
python $M compare --from 北京南 --to 上海虹桥 --start 2026-10-06 --days 5 --type GDC

# 中转方案
python $M transfer --date 2026-10-08 --from 杭州东 --to 西安北 --limit 5

# 某趟车经停站
python $M route --train G1 --date 2026-10-08
```

## 子命令

| 命令 | 用途 |
|---|---|
| `tickets` | 查余票(支持过站区间,如 `杭州东→上海虹桥`) |
| `compare` | 跨日期票量对比 ⭐ 规划行程用 |
| `transfer` | 查中转方案 |
| `route` | 查某趟车经停站 |
| `stations` | 查车站 telecode |
| `today` | 今天的日期(Asia/Shanghai) |
| `refresh-cache` | 强制重拉车站表和查询路径 |

### 常用参数

| 参数 | 说明 |
|---|---|
| `--type` | 车次类型:`G` 高铁 / `C` 城际 / `D` 动车 / `Z` 直特快 / `T` 特快 / `K` 快速 / `F` 复兴号 / `S` 智能动车组 / `O` 其它类 |
| `--after` `--before` | 出发时段过滤(小时,0-24) |
| `--sort` | `startTime` / `arriveTime` / `duration` |
| `--limit` | 结果条数上限 |
| `--summary` | 按 有座/仅无座/无票 分层汇总 |
| `--format` | `text`(默认)/ `md` / `csv` / `json` |

## 输出示例

```
$ python $M tickets --date 2026-10-08 --from 北京南 --to 上海虹桥 --type G --sort duration --format md

### 🚄 2026-10-08 北京南 → 上海虹桥 —— 共 3 趟

| 车次 | 余票 | 出发 | 开车 | 到达 | 到达时间 | 历时 | 有票席别 / 票价 |
|---|---|---|---|---|---|---|---|
| G25 | ✅ | 北京南 | 17:00 | 上海虹桥 | 21:18 | 04:18 | 二等座 有 661元 / 一等座 有 1058元 / 商务座 有 2315元 |
| G35 | ✅ | 北京南 | 19:24 | 上海虹桥 | 23:51 | 04:27 | 二等座 有 661元 / 一等座 7 1058元 / 商务座 12 2315元 |
| G13 | ✅ | 北京南 | 16:00 | 上海虹桥 | 20:28 | 04:28 | 二等座 有 661元 / 一等座 有 1058元 / 商务座 有 2315元 |
```

`G833` 这类只有一等座的车会显式标出 `(二等座❌413.5元)`,
避免看到「商务座有」误以为这趟有二等座。

## 架构

```
scripts/
├── main.py              CLI 入口(argparse + 分发)
├── train12306.py        兼容入口(等价于 main.py)
└── rail12306/
    ├── constants.py     常量表(无内部依赖)
    ├── utils.py         时间 / 缓存 / 路径归一化
    ├── client.py        HTTP 会话、cookie、路径发现、车站表
    ├── parsing.py       12306 返回 → 结构化 dict
    ├── filters.py       余票分层、类型过滤、排序
    ├── formatting.py    文本表格 + Markdown 表格
    ├── compare.py       跨日期对比
    └── commands.py      各子命令实现
```

依赖方向单向向下,无循环引用。

## 踩过的坑(维护者必读)

这些是实测踩出来的,改代码前建议先扫一眼:

1. **`lc_search_url` 需要热会话** —— 12306 的查询路径藏在 init 页面里,而且**只在有活跃会话时才渲染**。
   必须用 `requests.Session` 且先访问两个 init 页,裸调 `requests.get` 抠不到。

2. **两条查询路径前缀不同** —— 余票 `leftTicket/queryG` 要补 `/otn/`,
   中转 `/lcquery/queryG` **已经在根路径,加 `/otn/` 会被 302 到登录页**。别合并成一个归一化函数。

3. **时刻可能是 `24:xx`** —— 12306 用 `24:05` 表示次日 00:05,
   `datetime.replace(hour=24)` 会抛 `ValueError` 并静默丢车次。见 `utils.mk_datetime()`。

4. **会返回占位脏数据** —— 见过 `24:00→24:00 历时 99:59 日期跨 4 天` 这种行,已在 `parsing.py` 过滤。

5. **返回的出发站可能不是你查的站** —— 12306 会把同城配对站的结果一并返回。你查的是「某市南站」,
   返回里大部分车次的实际发车站却是同城的另一座站(南站在一条线上,往某方向的动车走的是主站)。
   `compare` 会自动检测并告警,`tickets` 也会在输出里如实标注真实发车站。

## 缓存

`cache/` 下有两个文件,7 天过期,删了会自动重建:

- `stations.json` —— 全国 3405 个车站表
- `paths.json` —— 12306 的两个隐藏查询路径

**查询结果不缓存**,每次实时拉 —— 实测零限流,加缓存反而引入过期问题。

## 免责声明

本工具**只做查询和行程规划**。12306 的购票流程需要登录态和支付环节,
本项目不涉及、也不代办。查到信息后请自行前往 12306 官方渠道(App / 网页 / 窗口)完成下单。

## License

MIT

致谢 [Joooook/12306-mcp](https://github.com/Joooook/12306-mcp)(MIT) —— 本项目为独立的 Python 重写实现。
