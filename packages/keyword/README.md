# XDUCraft Keyword (`nonebot-plugin-xducraft-keyword`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的群关键词自动回复与入群欢迎消息插件。

支持按群独立维护关键词规则、多种匹配模式（包含、完全匹配、开头匹配、正则表达式）、复合消息段回复（纯文本、本地图片、表情、`@`）以及新成员入群欢迎。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能特性

- **多模式关键词匹配**：支持包含（`contains`）、完全匹配（`exact`）、开头匹配（`prefix`）及正则表达式（`regex`）。
- **复合消息段回复**：单条规则支持顺序发送 1–8 条消息段，涵盖纯文本、本地图片、QQ 表情与 `@` 成员组合。
- **入群欢迎消息**：新成员入群时自动触发欢迎消息链，首条回复自动 `@` 新成员。
- **群级独立规则**：每群独立维护规则列表与回复冷却时间，群间规则完全隔离。
- **双重门禁安全机制**：受管插件全局总开关（`keyword`）与群级功能开关（`keyword_reply`）默认均为关闭（`OFF`）。全局关闭具有最高优先级。

---

## 标识与命名空间说明

| 维度 | 标识 | 说明 |
| :--- | :--- | :--- |
| **发行包名** | `nonebot-plugin-xducraft-keyword` | `pip` 安装与依赖声明标识（版本 `0.1.0`）。 |
| **插件加载名** | `xducraft_keyword` | NoneBot 插件加载标识，用于 `pyproject.toml` 中的 `plugins` 配置。 |
| **依赖 Core 插件** | `xducraft_config` | Core 核心配置与生命周期插件，入口处通过 `require("xducraft_config")` 预加载。 |
| **配置项键** | `keyword` | Core 声明式配置体系中的配置命名空间。 |
| **功能门禁键** | `keyword_reply` | 统一功能开关（`/功能`）中注册的特性键名（显示名：`关键词回复`）。 |

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

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Keyword 插件
pip install "nonebot-plugin-xducraft-keyword @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-keyword.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_keyword",
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

1. **单一活跃配置源**：本插件采用 Core 的声明式配置文档系统。活跃配置统一持久化保存在 Core SQLite 数据库中的 `keyword` 命名空间。
2. **启动期单次历史导入**：若存在历史配置文件 `keyword_config.json`，Core 将在启动阶段执行单次导入并确立活跃文档，导入后旧文件不再写入。若历史 JSON 损坏，系统将抛出异常中断启动，绝不静默覆盖。
3. **媒体资源文件严格隔离**：上传与保存的回复图片存放于 `<DATA_DIR>/plugins/keyword/media/` 目录下。图片文件系统独立持久化，受 10 MiB 大小限制与格式校验保护，绝不混入 Core 配置数据库。
4. **数据目录环境变量**：若需要自定义外部数据目录，必须在启动前通过操作系统环境变量配置 `XDUCRAFT_DATA_DIR`（绝对路径），切勿仅写在 live `.env` 中。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

第三方依赖项与协议端接口规范遵循各自独立的授权许可。
