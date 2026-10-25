# XDUCraft Keyword (`nonebot-plugin-xducraft-keyword`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的群关键词自动回复与入群欢迎消息插件。

---

## 功能说明

- **多模式关键词匹配**：支持包含（`contains`）、完全匹配（`exact`）、开头匹配（`prefix`）及正则表达式（`regex`）。
- **复合消息段回复**：单条规则支持顺序发送 1–8 条消息，涵盖纯文本、本地图片、QQ 表情与 `@` 成员组合。
- **入群欢迎消息**：新成员入群时自动触发欢迎消息链，首条回复自动 `@` 新成员。
- **群级独立规则**：每群独立维护规则列表与冷却时间。升级时历史全局规则一次性固化到各已知群，群规则完全独立，不再动态拼接全局规则。
- **双重门禁要求**：全局总开关（`keyword`）与群插件开关默认均为关闭。正常生效必须满足：
  1. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `keyword`；
  2. 开启本群插件开关及功能（可在群内发送 `/功能 on 关键词回复` 或 `/功能 on keyword_reply`，系统会自动同步本群插件总开关）。

---

## 指令列表与交互

群级规则默认通过**私聊**完成配置，避免管理操作刷屏：

| 指令 | 范围与权限 | 说明 |
| :--- | :--- | :--- |
| `/关键词 <群号>` | 私聊（群管理 / 超管） | 查看指定群的规则总览与操作菜单 |
| `/关键词` | 群内（群管理 / 超管） | 机器人向发送者私聊推送本群管理菜单 |
| `/关键词 <群号> on\|off` | 私聊（群管理 / 超管） | 开关该群的关键词自动回复 |
| `/关键词 <群号> add <词> [回复]` | 私聊（群管理 / 超管） | 添加关键词规则（支持后续录制多条回复） |
| `/关键词 <群号> del\|show <词>` | 私聊（群管理 / 超管） | 删除或查看指定关键词规则详情 |
| `/关键词 <群号> mode <词> <模式>` | 私聊（群管理 / 超管） | 切换匹配模式（包含 / 完全 / 开头 / 正则） |
| `/关键词 <群号> cooldown <秒>` | 私聊（群管理 / 超管） | 设置本群默认回复冷却时间（0–3600 秒） |
| `/关键词 <群号> join set\|show\|clear` | 私聊（群管理 / 超管） | 配置、查看或清空本群新成员欢迎消息 |

---

## 安装与加载

本插件处于内部演进阶段，尚未发布至公共 PyPI 仓库。

**源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/keyword
```

**Wheel 构建与联合安装**：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/keyword
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_keyword-0.1.0-py3-none-any.whl
```

**宿主加载（`pyproject.toml`）**：
```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_keyword",
]
```

---

## 数据存储边界

1. **配置数据迁移**：历史 `keyword_config.json` 仅作为启动期单次导入源。首次启动由 Core 一次性导入至 Core SQLite（`keyword` 命名空间），确立记录后旧文件不再写入；若历史配置损坏直接中断启动。
2. **媒体文件独立存储**：上传的回复图片保存在 `media/` 目录下（外部数据根下路径为 `<ROOT>/plugins/keyword/media/`；旧源码布局为 `xducraft_bot/plugins/xducraft_keyword/data/media/`）。图片受 10 MiB 大小限制与格式校验保护，属于独立文件系统持久化，不混入 Core 配置数据库。
