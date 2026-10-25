# XDUCraft Anti-Recall (`nonebot-plugin-xducraft-anti-recall`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的群撤回消息持久化与私聊查询插件。

---

## 功能说明

- **群内完全静默**：检测到撤回事件时不向群内发送任何提示，避免引战与刷屏。
- **按需缓存与延迟固化**：仅对开启本功能的群缓存消息内容；仅在收到撤回通知时固化记录并下载图片媒体，防止无效下载消耗磁盘。
- **私聊鉴权查询**：仅限通过**私聊**向群管理员与超级用户提供撤回记录查询，严格校验提问者在对应群的管理权限。
- **合并转发展开**：在收到消息时展开合并转发节点，确保原消息被撤回后内容仍可完整回放。
- **双重门禁要求**：全局总开关（`anti_recall`）与群插件开关默认均为关闭。正常生效必须满足：
  1. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `anti_recall`；
  2. 开启本群插件开关及功能（群内管理员发送 `/反撤回 on`，或发送 `/功能 on 反撤回` / `/功能 on anti_recall`，系统会自动同步本群插件总开关）。

---

## 常用指令

| 指令 | 范围与权限 | 说明 |
| :--- | :--- | :--- |
| `/反撤回 on\|off` | 群内（群管理 / 超管） | 开启或关闭本群反撤回记录 |
| `/反撤回 status` | 群内（群管理 / 超管） | 查看本群反撤回启用状态与已记录数量 |
| `/反撤回 clear` | 群内（群管理 / 超管） | 清空本群已固化的撤回历史记录 |
| `/撤回` | 私聊（群管理 / 超管） | 查询撤回记录（单群直接展示，多群返回序号选择菜单） |
| `/撤回 <群号> [条数]` | 私聊（群管理 / 超管） | 指定群号和查询条数回放撤回记录 |

---

## 配置项与作用域

- **全局独占参数 (`global_only`)**：
  - `cache_retention_hours`：未撤回消息缓存保留小时（默认 48 小时，次日 04:17 清理）；
  - `recall_retention_days`：已撤回记录保留天数（默认 7 天，次日 04:17 清理）；
  - `save_media`：撤回发生时是否自动下载媒体（默认 `True`）；
  - `max_media_mb`：单媒体文件下载大小上限（默认 20 MB）；
  - `include_self`：是否缓存机器人自身发送的消息（默认 `False`）；
  - `exempt_user_ids`：全局豁免 QQ 列表（这些用户的消息一律不记录）。
- **群级独立参数 (`group_only`)**：
  - `max_query_results`：本群单次私聊查询返回的撤回记录条数上限（默认 30 条）。

---

## 安装与加载

本插件处于内部演进阶段，尚未发布至公共 PyPI 仓库。

**源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/anti-recall
```

**Wheel 构建与联合安装**：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/anti-recall
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_anti_recall-0.1.0-py3-none-any.whl
```

**宿主加载（`pyproject.toml`）**：
```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_anti_recall",
]
```

---

## 数据存储边界

1. **配置数据迁移**：历史 `anti_recall_config.json` 仅作为启动期单次导入源。首次启动由 Core 一次性导入至 Core SQLite（`anti_recall` 命名空间），确立记录后旧文件不再写入；若历史配置损坏直接中断启动。
2. **业务数据库与媒体隔离**：
   - 消息缓存与已撤回记录持久化于独立业务数据库 `DATA_DIR/anti_recall.db`；
   - 固化的媒体文件存于 `DATA_DIR/media/`（外部数据根下路径为 `<ROOT>/plugins/anti_recall/`；旧源码布局为 `xducraft_bot/plugins/xducraft_anti_recall/data/`）；
   - 业务数据和多媒体资产不混入 Core 配置数据库。
