# XDUCraft Core (`nonebot-plugin-xducraft-core`) 0.3.0

XDUCraft NoneBot 插件体系的独立配置存储、生命周期门禁与共享 SDK 核心库。

本项目将配置持久化、门禁控制与 SDK 核心逻辑从具体业务插件中剥离，提供跨适配器的声明式配置系统、单一活跃 SQLite 配置基础设施与运行时门禁。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 定位与架构边界

- **核心包职责**：提供基于 SQLite 的单一活跃配置源（原生 Pydantic 模型支持与文档存储）、NoneBot 消息与事件前置门禁控制（`@run_preprocessor`）、数据目录路径决策（`data_paths`）、启动期声明式历史迁移框架（`migrate_legacy`）及公共 SDK。
- **与业务插件/前端的边界**：体系内全部 11 个业务插件与系统组件（`happy-bot`、`auto-friend`、`keyword`、`pig-bot`、`mc-update`、`invite`、`anti-recall`、`wordcloud`、`mc-status`、`features` 与 `admin`）均已解耦为独立代码仓库与分发包。所有业务插件均显式依赖 Core（`nonebot-plugin-xducraft-core[onebot]>=0.3.0,<0.4.0`）；WebUI 管理面板亦独立为 `nonebot-plugin-xducraft-admin`。Core 仅包含纯净的 SDK 核心与生命周期入口，不耦合具体业务模型或前端构建逻辑。
- **双重门禁与系统服务定位**：受管业务插件的全局总开关与群级开关**默认均为关闭（OFF）**，全局关闭优先阻断所有事件与主动推送。Core 配置生命周期插件自身声明为非受管基础设施（`managed=False`），不受业务门禁拦截，不可作为业务插件关闭。
- **基础依赖精简**：基础安装仅依赖 `nonebot2`、`pydantic` 与 `platformdirs`，不包含 OneBot 适配器、FastAPI 或 WebUI 任何源码。针对权限判定（`permissions`）与私聊推送（`onebot`）等辅助工具，需启用可选依赖 `[onebot]`。
- **POSIX 文件权限安全**：在 POSIX 系统上，Core 自动将 SQLite 配置数据库主文件及其 WAL、SHM 侧车文件权限严格约束为 `0600`（仅当前进程属主用户可读写），防止同宿主机非特权越权访问。

---

## 包名与命名空间说明

为避免命名混淆，请明确区分以下三个维度的标识：

| 维度 | 名称 / 标识 | 用途说明 |
| :--- | :--- | :--- |
| **发行包名 (Distribution Name)** | `nonebot-plugin-xducraft-core` | `pip` 安装、虚拟环境包管理及依赖声明时使用的发行包标识。 |
| **插件加载名 (Plugin Name)** | `xducraft_config` | NoneBot 插件生命周期入口。在 `pyproject.toml` 的 `plugins` 配置或业务插件中通过 `require("xducraft_config")` 加载。 |
| **SDK 导入命名空间 (Import Namespace)** | `xducraft_bot.shared.*` | 业务代码中调用 SDK 的 Python 模块路径，如 `from xducraft_bot.shared.configuration import ...`。 |

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，通过 Git Tag 安装：

```bash
# 包含 OneBot 适配器扩展（推荐）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 仅核心 SDK（无 OneBot 适配器）
pip install "nonebot-plugin-xducraft-core @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"
```

### 2. 宿主加载配置

NoneBot 启动初始化时，生命周期绑定必须在 `nonebot.init()` 之后完成。在宿主项目的 `pyproject.toml` 中显式加载 `xducraft_config`：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    # 依需加载其他业务插件，如 "xducraft_features", "xducraft_admin" ...
]
plugin_dirs = []
```

---

## 本地开发与测试（贡献者）

克隆本仓库到本地后，在仓库根目录执行：

```bash
# 安装开发与 OneBot 测试依赖
pip install -e ".[onebot,dev]"

# 运行自动化测试
pytest

# 本地构建 wheel 发行包
python -m build
```

本地构建产物将输出至 `dist/` 目录，安装方式：
```bash
pip install "dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot]"
```

---

## 插件接入配置核心最小示例

业务插件通过继承 `ConfigModel` 并调用 `register_config` 注册原生 Pydantic 配置模型，或通过 `declare_config` 与 `PluginConfiguration` 声明插件配置与启动期单次迁移回调 `migrate_legacy`。

> [!IMPORTANT]  
> - **先 require 后导入 SDK**：确保生命周期门禁与存储上下文已就绪。
> - **独立存储不污染 NoneBot 配置缓存**：Core 使用 SQLite 存储独立管理各群与全局生效快照，**不会修改或污染 NoneBot 的 `get_plugin_config` 全局配置缓存**。读取与更新请统一使用 Core 提供的 `get_config` 与 `update_config`。
> - **写入模式规范**：群级原生资源写入模式为全量替换（`write_mode="replace"`），更新必须传入该群的完整配置快照字典；全局原生资源写入模式为局部补丁（`write_mode="patch"`），支持使用 `{"set": {...}, "unset": [...]}` 协议。
> - **历史迁移与启动中断策略**：若历史 JSON 文件损坏或不可读，Core 将立即抛出异常并中断 NoneBot 启动，绝不静默使用默认值覆盖历史配置。

```python
from typing import Optional
from nonebot.plugin import PluginMetadata, require
from pydantic import Field

# 1. 业务插件必须在导入使用 SDK 声明前先 require 核心生命周期
require("xducraft_config")

from xducraft_bot.shared.configuration import (
    PROTOCOL_KEY,
    ConfigModel,
    register_config,
    get_config,
    update_config,
    is_plugin_enabled,
)

# 2. 继承 ConfigModel 定义配置模型
class NoticeConfig(ConfigModel):
    # 群级独立参数：各群完全隔离，默认采用代码声明值
    welcome_text: str = Field(
        default="欢迎加入交流群！",
        title="欢迎文本",
        description="本群专用入群欢迎文案",
        json_schema_extra={
            "x-ui-group": "消息设置",
            "x-ui-order": 1,
            "x-ui-scope": "group_only",
        },
    )
    # 全局独占参数：共享策略或服务级限额，群级不可覆盖
    max_daily_notices: int = Field(
        default=50,
        ge=1,
        title="每日推送上限",
        description="全服统一推送限额",
        json_schema_extra={
            "x-ui-group": "配额限制",
            "x-ui-order": 2,
            "x-ui-scope": "global_only",
        },
    )

# 3. 注册原生配置（scopes 支持 ("global", "group")）
DECLARATION = register_config(
    "my_notice",
    NoticeConfig,
    name="群通知",
    scopes=("global", "group"),
)

# 4. 将协议声明挂载至 PluginMetadata.extra 供生命周期与前端动态发现
__plugin_meta__ = PluginMetadata(
    name="群通知",
    description="基于 Core 的声明式配置插件示例",
    usage="支持在控制台或网页管理面板中按群独立配置",
    config=NoticeConfig,
    extra={PROTOCOL_KEY: DECLARATION},
)

# 5. 业务中读取配置示例
def get_welcome_message(group_id: int) -> Optional[str]:
    # 消息预处理器会自动校验双重门禁；主动发送或后台任务可显式核验
    if not is_plugin_enabled("my_notice", group_id):
        return None

    # scope="group" 时必须传入整数群号，返回 NoticeConfig 实例
    group_cfg: NoticeConfig = get_config("my_notice", scope="group", scope_id=group_id)
    return group_cfg.welcome_text

def get_daily_quota() -> int:
    # scope="global" 时无需 scope_id，获取全局共享策略
    global_cfg: NoticeConfig = get_config("my_notice", scope="global")
    return global_cfg.max_daily_notices
```

---

## 数据路径与存储规范

### 1. 运行时配置架构与迁移机制

- **单一活跃配置源（SQLite Active Store）**：
  - 活跃配置统一持久化于 Core 所选的 SQLite 数据库（`configuration.sqlite3`，优先级：显式 `database(path)` > 环境变量 `XDUCRAFT_CONFIG_DB` > 默认数据根下的 `<ROOT>/core/configuration.sqlite3`）。
  - `config_documents` 表持久化各命名空间的完整业务文档；`config_values` 表存储原生模型期望与生效值。
  - **单次导入输入边界**：历史插件 JSON 与历史 `deployment_overrides.json` 仅作为一次性导入源。在首次启动成功导入并在 SQLite 建立活跃文档后，旧文件绝不再作为写入者，也不会被删除或重写。
  - **首次升级与缺失库防护**：旧版生产环境（如早期单仓历史）无 Core SQLite 数据库，首次升级初始化时系统会建立全新干净的 SQLite 库结构，绝不能伪造或复制不存在的历史数据库文件。
- **启动期声明式迁移与中断策略**：
  - 在 NoneBot 启动且所有插件加载完成后（`on_startup`），Core 驱动各命名空间的历史数据单次导入。
  - 系统优先导入 `feature_gate` 与 `deployment_overrides`，随后按插件 key 字母顺序依次调用各插件声明的 `migrate_legacy` 回调。
  - **启动失败策略**：若历史 JSON 文件损坏或不可读，系统立即抛出异常并中断 NoneBot 启动；严禁吞没错误或回退至默认值，防止配置被静默覆盖。
- **部署覆盖与 `.env` 基线策略**：
  - 环境变量与 `.env` 作为启动引导与静态基线（包括适配器连接参数、Admin 运行参数、数据路径以及 `MCS_*`、`INVITE_*`、`AUTO_ACCEPT_FRIEND_GROUP_IDS` 等业务插件启动期参数默认值），**绝不全量复制进 SQLite**。
  - 启动期部署参数通过 Core 的 `deployment_overrides` 命名空间在 SQLite 中持久化存储下一启动期望覆盖值。当在 WebUI 或 API 显式保存修改时，覆盖值记录于 SQLite 并在下次重启生效；当移除覆盖项（unset）时，下次重启将自动恢复为 `.env` 或操作系统环境变量所定义的基准值。
- **业务数据严格隔离**：聊天日志、反撤回媒体、MC 状态游标等纯业务持久化数据严格保留在独立存储中，绝不作为配置处理，亦不混入核心配置数据库。

### 2. 运行时数据根目录决策

Core 通过 `xducraft_bot.shared.data_paths` 统一确定运行时数据根目录：

1. **显式指定优先**：启动前若设置了 `XDUCRAFT_DATA_DIR` 环境变量（必须为操作系统环境变量绝对路径，且不能与已安装的代码包重叠），系统严格使用该外部根目录。请务必在启动进程的 OS 环境中注入，切勿仅写在 live `.env` 中。
2. **全新独立安装**：在全新独立运行环境中，若未设置 `XDUCRAFT_DATA_DIR`，自动使用操作系统标准用户数据目录（通过 `platformdirs.user_data_path("xducraft", appauthor=False)`），绝不向 site-packages 等安装代码目录写入运行时数据。
3. **旧版宿主兼容**：若检测到既有源码宿主数据标记，系统安全保留旧版源码相对路径。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

核心库及其依赖所使用的第三方开源组件、字体或资源文件遵循各自独立的开源许可协议，不属于本项目的单一 MIT 许可范围。
