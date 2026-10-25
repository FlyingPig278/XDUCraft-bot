# XDUCraft Anti-Recall (`nonebot-plugin-xducraft-anti-recall`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的群撤回消息持久化与私聊查询插件。

支持在检测到撤回事件时按需固化消息与下载媒体，仅限通过私聊向群管理与超管提供记录查询，群内完全静默。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能特性

- **群内完全静默**：检测到撤回事件时不向群内发送任何提示，避免引战与刷屏。
- **按需缓存与延迟固化**：仅对开启本功能的群缓存消息内容；仅在收到撤回通知时固化记录并下载图片媒体，防止无效下载消耗磁盘。
- **私聊鉴权查询**：仅限通过**私聊**向群管理员与超级用户提供撤回记录查询，严格校验提问者在对应群的管理权限。
- **合并转发展开**：在收到消息时递归展开合并转发节点，确保原消息被撤回后内容仍可完整回放。
- **双重门禁安全机制**：受管插件全局总开关（`anti_recall`）与群级功能开关（`anti_recall`）默认均为关闭（`OFF`）。全局关闭具有最高优先级。

---

## 标识与命名空间说明

| 维度 | 标识 | 说明 |
| :--- | :--- | :--- |
| **发行包名** | `nonebot-plugin-xducraft-anti-recall` | `pip` 安装与依赖声明标识（版本 `0.1.0`）。 |
| **插件加载名** | `xducraft_anti_recall` | NoneBot 插件加载标识，用于 `pyproject.toml` 中的 `plugins` 配置。 |
| **依赖 Core 插件** | `xducraft_config` | Core 核心配置与生命周期插件，入口处通过 `require("xducraft_config")` 预加载。 |
| **配置项键** | `anti_recall` | Core 声明式配置体系中的配置命名空间。 |
| **功能门禁键** | `anti_recall` | 统一功能管理中注册的特性键名（显示名：`反撤回`）。 |

---

## 指令列表与交互

| 指令 | 范围与权限 | 说明 |
| :--- | :--- | :--- |
| `/反撤回 on\|off` | 群内（群管理 / 超管） | 开启或关闭本群反撤回记录（自动同步本群插件总开关） |
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

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Anti-Recall 插件
pip install "nonebot-plugin-xducraft-anti-recall @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-anti-recall.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_anti_recall",
]
```

---

## 本地开发与测试（贡献者）

克隆本仓库到本地后，在仓库根目录执行：

```bash
# 安装 Core 依赖与本地开发依赖
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"
pip install -e ".[dev]"

# 运行自动化测试
pytest

# 本地构建 wheel 发行包
python -m build
```

本地构建产物将输出至 `dist/` 目录。

---

## 数据存储与历史迁移

1. **配置数据迁移**：历史 `anti_recall_config.json` 仅作为启动期单次导入源。首次启动由 Core 一次性导入至 Core SQLite（`anti_recall` 命名空间），确立记录后旧文件不再写入；若历史配置损坏直接中断启动。
2. **业务数据库与媒体隔离**：
   - 消息缓存与已撤回记录持久化于独立业务数据库 `<DATA_DIR>/plugins/anti_recall/anti_recall.db`；
   - 固化的媒体文件存于 `<DATA_DIR>/plugins/anti_recall/media/`；
   - 业务数据和多媒体资产严格独立，绝不混入 Core 配置数据库。
3. **数据目录环境变量**：若需要自定义外部数据目录，必须在启动前通过操作系统环境变量配置 `XDUCRAFT_DATA_DIR`（绝对路径），切勿仅写在 live `.env` 中。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

第三方依赖项与协议端接口规范遵循各自独立的授权许可。
