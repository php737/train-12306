"""train-12306 · 12306 火车票查询(只查不买)。

分层:
  constants  常量表(无依赖)
  utils      时间/缓存/归一化
  client     HTTP 会话 + 车站表
  parsing    12306 返回 → dict
  filters    分类/过滤/排序
  formatting 输出呈现
  compare    跨日期对比
  commands   子命令实现
"""

from .constants import VERSION

__all__ = ["VERSION"]
__version__ = VERSION
