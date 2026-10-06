---
name: "train-12306"
description: "查 12306 火车票:余票、车次过滤、中转方案、经停站、车站编码。Python CLI,免 npm。触发:查车票、余票、火车票、高铁票、中转、12306、G/D 车次、有没有票。"
---

# train-12306 · Python 版 12306 查询

Python 重写自 [Joooook/12306-mcp](https://github.com/Joooook/12306-mcp)(TypeScript),
**零 npm 依赖**,只用 `requests`。CLI 优先,输出对齐好的表格,直接看。

## 0. 能力边界（先读这段）

**这个 skill 只做「查询」和「规划」,不碰买票。**

| 能做 | 不能做 / 不做 |
|---|---|
| 查余票、票价、席别、特性标签 | ❌ 代下单 |
| 查中转方案、比选路线、算时间 | ❌ 碰账号密码 / 登录态 / 身份证信息 |
| 查某趟车经停站 | ❌ 代支付、候补提交 |
| 查车站 telecode、换乘衔接 | ❌ 任何写入操作 |
| 给「选哪趟车」的建议 | ❌ 代替用户去官方渠道操作 |

**12306 的购票接口需要登录态和支付环节,这里一个都不涉及。** 查到信息后,
一律让用户自己去 12306 官方渠道(App / 网页 / 窗口)完成下单。

用户问「能不能买到 / 买哪个好」时,我给**信息和建议**;
问「帮我买」时,我**告知这个 skill 买不了**,并给出官方购买路径。
不要承诺、暗示或尝试任何自动购票。

## 1. 入口

```bash
M=~/.openclaw/skills/train-12306/scripts/main.py
python $M <子命令> [参数]        # 解释器就是 python,不是 python3
```

> ⚠️ **解释器用 `python`,不要用 `python3`**。部分环境里 `python` 指向 venv(装了 requests),
> 而 `python3` 指向系统 Python(没装),用错会报 `ModuleNotFoundError: requests`。

## 1.0 代码结构(2026-10-05 拆分)

单文件 1091 行拆成了分层包,CLI 入口是 `main.py`:

```
scripts/
├── main.py              ← CLI 入口(argparse + 分发 + 全局异常处理)
├── train12306.py        ← 21 行兼容 shim,老命令不破,新代码别再往这写
└── rail12306/
    ├── constants.py     常量表(无任何内部依赖,整个包的基座)
    ├── utils.py         时间/缓存/路径归一化
    ├── client.py        Rail12306 类:会话、cookie、路径发现、车站表
    ├── parsing.py       12306 返回 → dict(价格/标签/车次/经停站)
    ├── filters.py       余票分层、车次类型过滤、排序
    ├── formatting.py    文本表格 + Markdown 表格 + 各 fmt_*
    ├── compare.py       跨日期对比
    └── commands.py      各 cmd_* 实现
```

依赖方向单向向下:`constants → utils → client/parsing → filters → formatting → commands → main`.
**新加功能时,把函数放进它职责所属的层,别全塞进 commands.py。**

⚠️ 拆分时踩过的坑:我在 `main.py` 里手写参数列表时**漏了 `--type`**,
导致 `tickets` / `transfer` 全部报 `unrecognized arguments`。现在公共参数统一走
`_add_filter_args()` / `_add_sort_args()`,加子命令时**调用它们,别手写**。

## 1.1 cache 目录结构

`~/.openclaw/skills/train-12306/cache/` 里只两类文件，**都可以随时删**,删了下次自动重建:

| 文件 | 大小 | 内容 | 有效期 | 删了会怎样 |
|---|---|---|---|---|
| `stations.json` | ~731 KB | 全国 3405 个车站表 | 7 天 | 重新拉(1 次网络请求) |
| `paths.json` | ~77 B | 两个隐藏查询路径 | 7 天 | 重新抠 |

**两个都删也不影响功能**,最坏情况是多几次网络请求。

### ⭐ 查询结果不做缓存(2026-10-05 经评估后决定)

原本有个 `q_<md5>.json` 的 90 秒查询缓存,已**彻底去掉**。理由:

- 实测一个会话 40+ 次实时查询,12306 **零限流** —— 它没解决过任何真实问题
- 它引入了「缓存无限累积」的缺陷(只判断过期、从不删除,单条最大 179KB)
- 它让人搞不清 cache 目录里一堆文件是干嘛的(曾专门被质疑过)

所以 `query_get()` 现在**每次都实时拉**,只保留两样东西:
HTTP 重试退避(在 `get()` 里)和错误可读化(HTML 重定向检测 / JSON 解析失败提示)。

`refresh-cache` 仍会调 `_gc_query_cache()` 清理历史上遗留的 `q_*.json`。

## 2. 子命令速查

### today — 今天的日期(上海时区)

```bash
python $S today
```

**查票前先跑这个**。用户说「明天」「下周五」时,靠这个换算成 `yyyy-MM-dd`,
别自己心算(跨月/闰年会错)。

### refresh-cache — 强制重拉缓存

```bash
python $S refresh-cache
```

12306 改版导致报错(如「重定向到登录页」「没查到车次」全都查不出来)时先跑这个。
平时**不用管**,缓存自己会过期。

### stations — 查车站 telecode

```bash
python $S stations --city 北京                    # 城市下所有车站(北京有 65 个)
python $S stations --name "北京南|上海虹桥"       # 具体站名,多个用 | 分隔
python $S stations --code BJP                    # telecode 反查
```

**关键坑**:`--from 北京` 会解析到 `BJP`(北京站),而大部分高铁在**北京南**。
用户说「北京到上海」时,默认应该用 `北京南`。不确定就先 `stations --city 北京`
把所有站列出来给用户挑,或优先试 `北京南`/`上海虹桥` 这种大站。

### tickets — 查余票 ⭐主力

```bash
python $S tickets --date 2026-10-08 --from 北京南 --to 上海虹桥
```

全部可选参数:

| 参数 | 作用 | 示例 |
|---|---|---|
| `--type` | 车次类型过滤 | `G` / `GD` / `GDC` / `GDCZTKO` |
| `--after` | 最早出发小时 | `--after 6` (06:00 起) |
| `--before` | 最晚出发小时(**不含**) | `--before 20` (20:00 前) |
| `--sort` | `startTime` / `arriveTime` / `duration` | `--sort duration` (历时最短) |
| `--desc` | 排序反转 | 最晚 / 最长在前 |
| `--limit` | 结果条数 | `--limit 5` |
| `--summary` | **按 有座/仅无座/无票 分层汇总** | 判断能不能走时用这个 |
| `--format` | `text`(默认) / **`md`** / `csv` / `json` | `md` = Markdown 表格 |

**Web 端查看结果时优先用 `--format md`**(2026-10-05 确认)。
`--summary --format md` 组合 = 先来一个分层统计表,再按层给车次表,最适合回答「买不买得到」。
`md` 格式**不加代码块围栏**——加了 webchat 会当成源码显示、不渲染表格。

**`--summary` 是回答「买不买得到」的首选输出。** 默认 `text` 会把无票的车次也全部列出,
节假日几十趟里只有 2 趟有票时,翻 90 行找那 2 行很痛苦。分层后一眼看到:
```
📊 2026-10-06 长沙南 → 深圳北 共 91 趟
   ✅ 有座 2 ｜ 🟡 仅无座 0 ｜ ❌ 无票 89
```

**过站查询**不用特殊参数——12306 原生支持区间:`--from 杭州东 --to 上海虹桥`
就是「坐杭州东上车、虹桥下车」的中途区间票,和全程票一个接口。

### compare — 跨日期票量对比 ⭐规划行程用

```bash
python $M compare --from 长沙南 --to 深圳北 --start 2026-10-06 --days 5 --type G
python $M compare --from 长沙南 --to 深圳北 --dates 2026-10-08,2026-10-09
```

| 参数 | 说明 |
|---|---|
| `--start` | 起始日期,默认今天 |
| `--days` | 从 start 起算几天,默认 5 |
| `--dates` | 显式指定日期(逗号分隔),会覆盖 `--start/--days` |
| `--type` / `--after` / `--before` | 同 tickets |
| `--format` | `md`(默认) / `text` |

**回答「哪天走最松」的首选。** 以前只能靠临时脚本跑,已固化成子命令:

```
| 日期 | 总车次 | ✅有座 | 🟡仅无座 | ❌无票 | 二等座有票 | 二等座价 |
|---|---|---|---|---|---|---|
| 2026-10-06 | 91 | 10 | 0 | 81 | 1 | 211~646元 |
| 2026-10-09 | 67 | 62 | 0 | 5 | **54** | 211~627元 |

> ✅ 推荐 2026-10-10 —— 二等座有票 59 趟……
```

**它会自动检测发车站不一致**(长沙南/长沙那个坑)并给出警告,不用再手工核对。

### transfer — 查中转方案

```bash
python $S transfer --date 2026-10-08 --from 杭州东 --to 西安北 --limit 5
python $S transfer --date 2026-10-08 --from 杭州东 --to 西安北 --middle 南京南  # 指定中转站
```

支持 `--wz`(包含无座)、`--type`、`--sort`、`--limit`、`--format text|json|md`。
输出会标出 **同车换乘 / 同站换乘 / 换站换乘** 和等待时间——
换站换乘要拖行李出站,优先推同站。

### route — 查某趟车经停站

```bash
python $S route --train G1 --date 2026-10-08
```

用户问「G1 在哪停」「这趟车到南京南几点」时用。
输出是站序表:站名 / 到达 / 出发 / 停留时长。`--format text|json|md`。

## 2.1 全局 flag

| flag | 作用 |
|---|---|
| `--verbose` | 调试日志打到 stderr |
| `--version` | 打印版本 |

## 3. 车次类型对照(`--type`)

| 字母 | 含义 | 字母 | 含义 |
|---|---|---|---|
| `G` | 高铁(含 C 城际) | `K` | 快速 |
| `C` | 城际 | `Z` | 直达特快 |
| `D` | 动车 | `T` | 特快 |
| `F` | 复兴号(按标签匹配) | `S` | 智能动车组(按标签匹配) |
| `O` | **其它类**(非 G/C/D/Z/T/K) | | |

用户说「高铁票」→ `G`;「动车」→ `D`;「高铁和动车」→ `GD`;
「快的」/「最快的」→ `--type GD --sort duration`。
`--type` 留空 = 不过滤(默认)。

⚠️ **`O` 不是车次首字母。** 实测 12306 的车次首字母只有 G/D/C/Z/T/K(和少量
临时车次的数字/1),**根本不存在首字母为 O 的车次**。`O` 的真实语义是「其它类」,
沿用自原 12306-mcp 项目。`match_types()` 里按 `code not in "GCDZTK"` 实现。
之前实现成了字面匹配首字母,导致 `--type O` 永远返回空。

## 4. 输出规范(经反馈修正后定稿)

**余票必须分三层,不能笼统说「有票」**——`has_ticket()` 只回答「这个席别有没有票」,
真正回答「能不能上车」的是 `avail_tier()`:

| 分层 | 判定 | 含义 |
|---|---|---|
| ✅ `seat` | 任一**非无座**席别有票 | 有座票,能坐 |
| 🟡 `wz` | 只有无座有票 | 站票,硬抗 |
| ❌ `none` | 都没票 | 无票 |

把「仅无座」算进「有票」是错的——用户问「有没有票」时,站票通常不算可接受的答案。
节假日大量车次的商务/一等座还有票但二等座全无,不分层就看不出真实情况。

**票价必须始终输出。** 接口 `yp_info_new` 里就有(定长 10 字符串,第 2-6 位是分/10),
不要用 `席别 状态@价格元` 这种挤在一起的写法,拆开成 `二等座 有 421.5元`。
无票车次也要给二等座参考价,方便用户判断「值不值得候补」。

**有票必须写清楚是几等座(经反馈修正)。** 两条规矩:

1. **按席别重要性排序,不按接口返回顺序。** 12306 返回顺序常把商务座排最前,
   但大多数人买的是二等座。`SEAT_RANK` 固定顺序:二等座→一等座→商务座→特等座→
   硬卧→软卧→软座→硬座→无座→其他。
2. **二等座/一等座无票要显式标出来**,格式 `(二等座❌421.5元)`。
   不标的话用户看到「商务座 有」会以为这趟有二等座——这是最坑的误读。

另外 `--summary` 每行列席别时 **limit 至少 6**,别截断到 3-4,
否则 `无座` 这种排在后面的会消失(踩过一次:用户以为无座没票了)。

### 实测输出样例

```
车次  | 余票 | 出发   | 开车  | 到达   | 到达时间 | 历时  | 有票席别 / 票价
------+------+--------+-------+--------+----------+-------+------------------------------------------
G6053 | ✅    | 长沙南 | 06:15 | 深圳北 | 10:01    | 03:46 | 二等座 有 421.5元 / 一等座 4 655.5元 / 商务座 5 1291.5元
G833  | ✅    | 长沙南 | 19:09 | 深圳北 | 22:55    | 03:46 | 商务座 1 1322.5元  (二等座❌413.5元) (一等座❌643.5元)
G9753 | ❌    | 长沙南 | 00:02 | 深圳北 | 10:01    | 03:08 | ❌ 无票 421.5元
```

余票字段读法:`二等座 有` = 12306 没给具体数字只说「有」;`一等座 4` = 剩 4 张;
`(二等座❌413.5元)` = 这趟二等座没了但告诉你原价;`❌ 无票 421.5元` = 无票 + 二等座参考价。

⚠️ **余票是实时变的。** 同一命令隔几分钟跑结果可能完全不同(有人退票/买票)。
发现前后矛盾时以最新一次为准,不要说「刚才还有」。

## 5. 踩过的坑(重要)

### ⭐ 12306 返回的「出发站」可能不是你查的那个站(2026-10-05 实测)

查「长沙南 → 常德」,返回 44 趟里 **43 趟的 from_station_telecode 是 CSQ(长沙),
只有 1 趟是 CWQ(长沙南)**。裸打 12306 复现过,不是代码的锅:

```
from=CWQ(长沙南) 查询 → 返回 {CSQ: 72, CWQ: 1}
```

原因:去常德的动车/高铁本来就从**长沙站**发车(长沙南在沪昆高铁线上,和常德不通),
但 12306 会把同城的配对站结果一起返回。

**所以每次报结果前,必须看一眼实际返回的 `from_code` 分布**,发现和请求的
不一致要在回复里讲清楚,否则会推荐用户去一个他到不了的站上车。

```bash
python $S tickets ... --format json | python -c "
import json,sys; from collections import Counter
print(Counter(r['from_code'] for r in json.load(sys.stdin)))"
```

### ⭐ 12306 会返回 `24:xx` 这种时刻(次日 00:xx 的写法)

`start_time` 可能是 `24:05`,直接 `datetime.replace(hour=24)` 抛
`ValueError: hour must be in 0..23, not 24`,**整趟车被静默丢弃且不报错**。
已用 `mk_datetime()` 处理(`h >= 24` → 日期 +1 天、小时取模)。

`--after/--before` 的时段过滤也要 `% 24`,否则 `24:xx` 的车默认会被 `--before 24` 滤掉。

### ⭐ 12306 会返回占位脏数据

实测遇到 `G2577 24:00 → 24:00,历时 99:59,日期横跨 4 天` 这种垃圾行。
`parse_tickets()` 现在会丢三类:`lishi` 为 `99:59`/`24:00`/`--:--`、
起止时间相同、历时超 48 小时。不加过滤会直接误导用户。

### `lc_search_url` 必须在「热会话」里才抠得到

这是本 skill 能不能活的关键,也是参考项目 `Joooook/12306-skill` 已死的真正原因。

```python
# 冷启动裸发一次 lcQuery/init —— 抠不到
requests.get(".../otn/lcQuery/init").text
re.search(r" var lc_search_url = '(.+?)'", html)   # -> None

# 先访问 leftTicket/init 拿 JSESSIONID,同 session 再取 —— 抠得到
s = requests.Session()
s.get(".../otn/leftTicket/init")                   # 关键:预热
re.search(r" var lc_search_url = '(.+?)'", s.get(".../otn/lcQuery/init").text)
# -> <re.Match ... match=" var lc_search_url = '/lcquery/queryG'">
```

**`bootstrap()` 里必须用 `requests.Session` 且先访问两个 init 页**,不能像参考项目那样
裸调 `requests.get`。参考项目没有 session → 正则永远匹配不上 → `init()` 抛异常 →
**所有子命令全挂**,而且它抛的报错是 `get station name js file failed`(复制粘贴的
误导信息,和车站表毫无关系)。所以那个仓库「好久没更新」不是作者懒——是它一跑就死。

### ⭐ 两个隐藏查询路径前缀不一样,别合并成一个归一化函数

| 用途 | 从哪抠 | 抠出来的原值 | 归一后 |
|---|---|---|---|
| 余票 | `/otn/leftTicket/init` 的 `CLeftTicketUrl` | `leftTicket/queryG` | `/otn/leftTicket/queryG` ← **要补 `/otn/`** |
| 中转 | `/otn/lcQuery/init` 的 `lc_search_url` | `/lcquery/queryG` | `/lcquery/queryG` ← **已在根路径,加了 `/otn/` 就 302 到 `/otn/passport`** |

代码里已分别用 `_norm_ticket_path()` / `_norm_transfer_path()` 处理。改这块时别合并。

### 其他

- **fallback 默认值不能写错**。抠不到路径时回退的默认值必须是当前真实值
  (`/otn/leftTicket/queryG` 和 `/lcquery/queryG`),写错的话故障会以
  `JSONDecodeError` 的形式出现——中转接口 302 到登录页时返回的是 HTML 而不是 JSON。
  现在 `query_get()` 会先检查 `Content-Type`,HTML 直接报可读错误。
- **取 cookie 的请求和查询请求都走 `get()`**。取 cookie 必须每次现拿,
  否则拿到过期 JSESSIONID。**查询结果不缓存**(见 1.1 节)。
- **表格对齐**是手写的东亚字符宽度补齐(`_h()` / `_pad()`),因为本机**没装 tabulate**。
- `成都东` 不在官方 station_name.js 里,代码里手工补了(`MISSING_STATIONS`)。共 3405 个车站。
- 车站表和查询路径都缓存 7 天,在 `cache/`。改版了就 `refresh-cache`。
- **只查不买** —— 详见第 0 节「能力边界」。

## 6. 排查

| 现象 | 处理 |
|---|---|
| `❌ 车站没解析出来` | `stations --name "正确的站名"` 确认真实站名,别臆造 |
| `❌ 12306 把接口 302 到登录页了` | 跑 `refresh-cache` |
| `❌ 12306 返回的不是合法 JSON` | 同上,查询路径多半变了 |
| `❌ 未预期的错误: KeyError/TypeError` | 12306 返回结构变了。跑 `refresh-cache`;还不行看第 5 节的路径表手动修 `_norm_*` |
| `ValueError: hour must be in 0..23` | 碰到 24:xx 车次,检查 `mk_datetime()` 还在不在 |
| `❌ 请求 ... 失败` | 加 `--verbose` 看重试日志;多半是 12306 临时限流,等几十秒再来 |
| `❌ 没查到 ... 的车次` | 去掉 `--type` / 放宽 `--after --before`;也可能是这天真没车 |
| `ModuleNotFoundError: requests` | 你用了 `python3`,换成 `python` |

调试时用 `TRAIN12306_DEBUG=1` 打开完整 traceback(默认只给可读错误)。

## 7. 关联

- 原项目(TS 版 MCP Server):`https://github.com/Joooook/12306-mcp`
- 作者的 Skill 封装版:`https://github.com/Joooook/12306-skill` ——
  **2026-10-05 实测已失效**(作者 2026-03-09 最后提交,跑任何子命令都报
  `get station name js file failed`)。根因见第 5 节:`lc_search_url` 需要热会话才抠得到,
  而它用裸 `requests.get` 没有 session。

本 skill 相比它多了:会话预热、重试退避、fallback 默认路径、24:xx 时刻处理、
脏数据过滤、Markdown 表格输出、三层余票分类、显式票价输出、跨日到达标记。

本 skill 相比它少了一样(刻意的):**查询缓存**。实测 12306 零限流,缓存不解决问题
反制造 bug,已去掉(见 1.1 节)。
