---
name: "train-12306"
description: "查 12306 火车票:余票、车次过滤、中转方案、经停站、跨日期对比。Python CLI,免 npm。触发:查车票、余票、火车票、高铁票、动车票、中转、12306、G/D 车次、有没有票、哪天走票松。"
---

# train-12306 · 12306 查询 CLI

Python 实现,只用 `requests`。**完整文档见同目录 `README.md`,本文件只写给 agent 看的规则。**

## 0. 能力边界(先读)

**只做查询和规划,不碰买票。**

| 能做 | 不做 |
|---|---|
| 查余票、票价、席别、特性标签 | ❌ 代下单 |
| 查中转、比选路线、算时间 | ❌ 碰账号密码 / 登录态 / 身份证 |
| 查经停站、车站 telecode、换乘衔接 | ❌ 代支付、候补提交 |

12306 购票要登录态和支付,本工具一个都不涉及。**查到信息后一律让用户自己去 12306
官方渠道(App / 网页 / 窗口)下单。**

用户问「能不能买到 / 买哪个好」→ 给**信息和建议**;
问「帮我买」→ **告知买不了**并给官方路径。不要承诺、暗示或尝试自动购票。

## 1. 入口

```bash
M=~/.openclaw/skills/train-12306/scripts/main.py
python $M <子命令> [参数]
```

⚠️ **用 `python`,不要 `python3`** —— 某些环境 `python3` 指向未装 requests 的系统解释器。

## 2. 子命令

| 命令 | 用途 | 关键参数 |
|---|---|---|
| `tickets` | 查余票 ⭐主力 | `--date --from --to` |
| `compare` | 跨日期对比 ⭐规划用 | `--from --to --start --days` |
| `transfer` | 中转方案 | `--date --from --to [--middle]` |
| `route` | 某趟车经停站 | `--train --date` |
| `stations` | 车站 telecode | `--city / --name / --code` |
| `today` | 今天日期(上海时区) | 无 |
| `refresh-cache` | 强制重拉车站表和路径 | 无 |

**公共筛选参数**:`--type`(车次类型)、`--after/--before`(出发小时)、`--sort`
(`startTime`/`arriveTime`/`duration`)、`--desc`、`--limit`、`--format`
(`text`/`md`/`csv`/`json`)、`--summary`(三层汇总)。

### 用法要点

- **`today` 先跑** —— 用户说「明天」「下周五」时用它换算日期,别心算(跨月会错)
- **`--summary --format md`** 是回答「买不买得到」的首选,先给分层统计再给车次表
- **过站查询**无需特殊参数:`--from 杭州东 --to 上海虹桥` 就是中途区间票
- **`stations --city 北京`** —— 用户只说城市名时(没说具体站),先列全部站让他挑。
  直接 `--from 北京` 会解析到北京站,而高铁大多在北京南

### 车次类型(`--type`)

`G` 高铁(含 C 城际) `D` 动车 `Z` 直特快 `T` 特快 `K` 快速
`F` 复兴号(按标签匹配) `S` 智能动车组(按标签匹配) `O` 其它类(非 GDCZTK)

> 「高铁」→ `G`;「动车」→ `D`;「最快的」→ `--type GD --sort duration`。
> `O` **不是车次首字母**(12306 根本没有 O 开头的车次),语义是「其它类」。

## 3. 输出规则(agent 必守)

### 余票必须分三层

`avail_tier()` 的三层,不能笼统说「有票」:

| 分层 | 判定 | 含义 |
|---|---|---|
| ✅ `seat` | 任一**非无座**席别有票 | 有座票 |
| 🟡 `wz` | **只有无座**有票 | 站票,硬抗 |
| ❌ `none` | 都没票 | 无票 |

把「仅无座」算进「有票」是错的。节假日大量车次商务/一等座还有票但二等座全无,
不分层会给出完全错误的结论。

### 票价必须始终输出

`yp_info_new` 里就有(定长 10 字符串,第 2-6 位是分/10)。格式 `二等座 有 421.5元`,
**不要**写成 `席别 状态@价格元` 那种挤在一起的。无票车次也要给二等座参考价。

### 有票必须写清是几等座

1. **按席别重要性排序**(`SEAT_RANK`:二等座→一等座→商务座→特等座→卧铺→无座),
   不按接口返回顺序 —— 12306 常把商务座排最前,但用户买的是二等座
2. **二等座/一等座无票要显式标出** `(二等座❌421.5元)`。
   不标的话用户看到「商务座 有」会误以为这趟有二等座,这是最坑的误读
3. **列席别 limit 至少 6**,否则排在后面的「无座」会被截掉

### Web 端优先 `--format md`

**不加代码块围栏** —— 加了 webchat 会当源码显示、不渲染表格。

⚠️ **余票实时变。** 同一命令隔几分钟结果可能完全不同。前后矛盾时以最新一次为准,
不要说「刚才还有」。

## 4. 技术坑(改代码前必读)

### ⭐ 发车站可能不是你查的那个站

12306 会把**同城配对站**的结果一并返回。实测某次查某市「南站」,返回的大部分车次
实际从该市**主站**发车(南站在另一条高铁线上,不通那个方向):

```
from=CWQ(南站) 查询 → 返回 {CSQ(主站): 72, CWQ(南站): 1}
```

**报结果前必须核对实际 `from_code` 分布**,不一致要在回复里讲清楚,
否则会推荐用户去一个他到不了的站上车。`compare` 会自动检测并告警。

### ⭐ `lc_search_url` 需要热会话

这个变量**只在有活跃会话时才渲染**。必须用 `requests.Session` 且**先访问两个 init 页**:

```python
requests.get(".../otn/lcQuery/init")          # ❌ 抠不到
s = requests.Session()
s.get(".../otn/leftTicket/init")               # ✅ 预热,拿 JSESSIONID
s.get(".../otn/lcQuery/init")                  # ✅ 这时才抠得到
```

### ⭐ 两条查询路径前缀不同,别合并成一个函数

| 用途 | 来源 | 原值 | 归一后 |
|---|---|---|---|
| 余票 | `CLeftTicketUrl` | `leftTicket/queryG` | `/otn/leftTicket/queryG` ← 补 `/otn/` |
| 中转 | `lc_search_url` | `/lcquery/queryG` | `/lcquery/queryG` ← **已在根路径,加 `/otn/` 会 302 到登录页** |

fallback 默认值必须是当前真实值,写错会以 `JSONDecodeError` 形式炸出来。

### ⭐ 时刻可能是 `24:xx`

12306 用 `24:05` 表示次日 00:05。`datetime.replace(hour=24)` 抛 `ValueError`
并**静默丢弃整趟车**。见 `utils.mk_datetime()`。时段过滤也要 `% 24`。

### 占位脏数据

实测有 `24:00→24:00 历时99:59 日期跨4天` 这种行。`parse_tickets()` 过滤三类:
`lishi` 为 `99:59`/`24:00`/`--:--`、起止时间相同、历时超 48 小时。

### 其他

- **取 cookie 的请求必须每次现拿**,不能缓存,否则拿到过期 JSESSIONID
- **查询结果不缓存** —— 实测 12306 零限流,加缓存只引入过期问题和维护负担
- 表格对齐是手写的东亚字符宽度补齐(`_h()`/`_pad()`),本机没装 tabulate
- `成都东` 不在官方 station_name.js 里,代码手工补了(`MISSING_STATIONS`)
- `cache/` 只有 `stations.json`(731KB 车站表)和 `paths.json`(查询路径),7 天过期,都可随时删

## 5. 代码结构

```
scripts/
├── main.py            CLI 入口(argparse + 分发 + 全局异常处理)
├── train12306.py      兼容 shim,新代码别往这写
└── rail12306/
    ├── constants.py   常量(无内部依赖)    ├── formatting.py  输出呈现
    ├── utils.py       时间/缓存/归一化    ├── compare.py     跨日期对比
    ├── client.py      HTTP/cookie/车站表   └── commands.py    子命令实现
    ├── parsing.py     返回 → dict
    └── filters.py     分层/过滤/排序
```

依赖单向向下:`constants → utils → client/parsing → filters → formatting → commands → main`

**新功能放进职责所属的层**,别全塞进 commands.py。
**公共 argparse 参数调 `_add_filter_args()` / `_add_sort_args()`,别手写** ——
手写过一次,漏了 `--type`,导致 tickets/transfer 全部报错。

## 6. 排查

| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: requests` | 用了 `python3`,换 `python` |
| `❌ 车站没解析出来` | `stations --name "真实站名"`,别臆造站名 |
| `❌ 302 到登录页` / `❌ 不是合法 JSON` | 跑 `refresh-cache`,多半是查询路径变了 |
| `❌ 未预期的错误: KeyError/TypeError` | 12306 结构变了。先 `refresh-cache`,还不行看第 4 节路径表 |
| `❌ 没查到车次` | 去掉 `--type` / 放宽时段;也可能是真没车 |
| `❌ 请求失败` | 加 `--verbose`;多半是临时限流,等几十秒 |

调试: `TRAIN12306_DEBUG=1` 开完整 traceback(默认只给可读错误)。

---

致谢 [Joooook/12306-mcp](https://github.com/Joooook/12306-mcp)(MIT) —— 本项目为独立 Python 重写。