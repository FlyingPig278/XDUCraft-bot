"""让插件模块能在测试里被正常导入。

``xducraft_mc_status`` 的包 ``__init__`` 在导入时就会注册命令处理器，而注册需要
NoneBot 已经初始化。所以这里必须在**模块层**初始化——放进 fixture 太晚了，
pytest 收集测试时就已经 import 过测试模块了。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nonebot  # noqa: E402

nonebot.init()
