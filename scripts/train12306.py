#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""train12306 —— 兼容入口。

真正的实现已拆分成 rail12306/ 包,CLI 入口是 main.py。
这个文件保留是为了不破坏已有的调用方式
(`python train12306.py tickets ...` 依然可用)。

推荐直接用:
    python main.py <子命令>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import main  # noqa: E402

if __name__ == "__main__":
    main()
