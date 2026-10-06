"""常量与配置表。**本模块不依赖任何其他模块**,是整个包的基座。"""

import os
from datetime import timedelta, timezone

VERSION = "1.1.0"

# ── 12306 接口地址 ──
API_BASE = "https://kyfw.12306.cn"
WEB_URL = "https://www.12306.cn/index/"
SEARCH_API_BASE = "https://search.12306.cn"
LEFT_TICKET_INIT = f"{API_BASE}/otn/leftTicket/init"
LCQUERY_INIT = f"{API_BASE}/otn/lcQuery/init"
STATION_JS_FALLBACK = f"{API_BASE}/otn/resources/js/framework/station_name.js"
TRAIN_ROUTE_PATH = "/otn/queryTrainInfo/query"

# 本文件在 scripts/rail12306/ 下,cache 在 skill 根目录
CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "cache"))

# 车站表/查询路径的缓存天数
CACHE_DAYS = 7

SHANGHAI = timezone(timedelta(hours=8))

# ── HTTP ──
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,zh-TW;q=0.8,en-US;q=0.6",
    "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
    "X-Requested-With": "XMLHttpRequest",
}

# ── 车站表字段(station_name.js 每条 10 个,顺序固定)──
STATION_KEYS = [
    "station_id", "station_name", "station_code", "station_pinyin",
    "station_short", "station_index", "code", "city", "r1", "r2",
]

# ── 余票接口 result 数组字段顺序(位置敏感,别改)──
TICKET_KEYS = [
    "secret_Sstr", "button_text_info", "train_no", "station_train_code",
    "start_station_telecode", "end_station_telecode", "from_station_telecode",
    "to_station_telecode", "start_time", "arrive_time", "lishi", "canWebBuy",
    "yp_info", "start_train_date", "train_seat_feature", "location_code",
    "from_station_no", "to_station_no", "is_support_card",
    "controlled_train_flag", "gg_num", "gr_num", "qt_num", "rw_num",
    "rz_num", "tz_num", "wz_num", "yb_num", "yw_num", "yz_num", "ze_num",
    "zy_num", "swz_num", "srrb_num", "yp_ex", "seat_types",
    "exchange_train_flag", "houbu_train_flag", "houbu_seat_limit",
    "yp_info_new", "40", "41", "42", "43", "44", "45", "dw_flag", "47",
    "stopcheckTime", "country_flag", "local_arrive_time", "local_start_time",
    "52", "bed_level_info", "seat_discount_info", "sale_time", "56",
]

# yp_info_new 定长字段长度
PRICE_CHUNK_LEN = 10
DISCOUNT_CHUNK_LEN = 5

# ── 席别类型码 → (中文名, 短码)──
SEAT_TYPES = {
    "9": ("商务座", "swz"), "P": ("特等座", "tz"), "M": ("一等座", "zy"),
    "D": ("优选一等座", "zy"), "O": ("二等座", "ze"), "S": ("二等包座", "ze"),
    "6": ("高级软卧", "gr"), "A": ("高级动卧", "gr"), "4": ("软卧", "rw"),
    "I": ("一等卧", "rw"), "F": ("动卧", "rw"), "3": ("硬卧", "yw"),
    "J": ("二等卧", "yw"), "2": ("软座", "rz"), "1": ("硬座", "yz"),
    "W": ("无座", "wz"), "WZ": ("无座", "wz"), "H": ("其他", "qt"),
}

# 席别展示顺序(经反馈修正:按「席别重要性」而非接口返回顺序)
SEAT_RANK = {
    "ze": 0, "zy": 1, "swz": 2, "tz": 3, "yw": 4, "rw": 5,
    "gr": 5, "srrb": 5, "rz": 6, "yz": 7, "wz": 8, "qt": 9,
}

# ── dw_flag 特色标签 ──
DW_FLAGS = ["智能动车组", "复兴号", "静音车厢", "温馨动卧",
            "动车号", "支持选铺", "老年优惠"]

# ── 车次类型过滤 ──
PRIMARY_PREFIXES = "GCDZTK"   # G高铁/C城际/D动车/Z直达/T特快/K快速
FLAG_TYPES = {"F": "复兴号", "S": "智能动车组"}

# station_name.js 里历史上缺失的车站,手工补
MISSING_STATIONS = [
    {"station_id": "@cdd", "station_name": "成都东", "station_code": "WEI",
     "station_pinyin": "chengdudong", "station_short": "cdd",
     "station_index": "", "code": "1707", "city": "成都", "r1": "", "r2": ""},
]

# 12306 会返回的占位脏数据(历时字段)
JUNK_LISHI = ("99:59", "24:00", "--:--")
MAX_DURATION_MIN = 48 * 60
