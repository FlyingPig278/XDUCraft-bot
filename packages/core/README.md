# XDUCraft Core (`nonebot-plugin-xducraft-core`)

XDUCraft NoneBot 插件体系的独立配置存储、生命周期门禁与共享 SDK 核心库。

本项目将配置持久化、门禁控制与 SDK 核心逻辑从业务插件及 WebUI 前端中剥离，提供跨适配器的声明式配置系统与运行时门禁。

---

## 定位与架构边界

- **核心包职责**：提供基于 SQLite 的声明式配置管理（原生 Pydantic 模型支持）、NoneBot 消息与事件前置门禁控制（`@run_preprocessor`）、数据目录路径决策（`data_paths`）及公共 SDK。
- **与业务插件/前端的边界**：业务插件（如 `xducraft_mc_status`、`xducraft_wordcloud` 等）与管理后台 WebUI 仍留在上层主项目仓库中，当前尚未作为独立包分发；Core 仅包含纯净的 SDK 核心与生命周期入口。
- **双重门禁与系统服务定位**：受管业务插件的全局总开关与群级开关**默认均为关闭（OFF）**，需显式开启全局与群级双重门禁方可响应运行。Core 配置生命周期插件自身声明为非受管基础设施（`managed=False`），不受业务门禁拦截，不可作为业务插件关闭。
- **基础依赖精简**：基础安装仅依赖 `nonebot2`、`pydantic` 与 `platformdirs`，不包含 OneBot 适配器、FastAPI 或 WebUI 任何源码。针对权限判定（`permissions`）与私聊推送（`onebot`）等辅助工具，需启用可选依赖 `[onebot]`。

---

## 包名与命名空间说明

为避免命名混淆，请明确区分以下三个维度的标识：

| 维度 | 名称 / 标识 | 用途说明 |
| :--- | :--- | :--- |
| **发行包名 (Distribution Name)** | `nonebot-plugin-xducraft-core` | `pip` 安装、虚拟环境包管理及依赖声明时使用的发行包标识。 |
| **插件加载名 (Plugin Name)** | `xducraft_config` | NoneBot 插件生命周期入口。在 `pyproject.toml` 的 `plugins` 配置或业务插件中通过 `require("xducraft_config")` 加载。 |
| **SDK 导入命名空间 (Import Namespace)** | `xducraft_bot.shared.*` | 业务代码中调用 SDK 的 Python 模块路径，如 `from xducraft_bot.shared.configuration import ...`。 |

---

## 安装方式

> [!NOTE]  
> 本软件包目前处于内部开发演进阶段，**尚未发布至公共 PyPI 仓库**。请勿尝试直接执行 `pip install nonebot-plugin-xducraft-core`。

### 1. 源码开发安装（推荐）

在整仓源码开发环境中，根目录 `requirements.txt` 已通过 `-e ./packages/core[onebot]` 声明了本地开发依赖。在主仓库根目录下执行：

```bash
pip install -r requirements.txt
```

若仅需单独将 Core 包作为可编辑模式安装至当前虚拟环境：

```bash
# 基础核心功能（无 OneBot 适配器）
pip install -e ./packages/core

# 包含 OneBot 适配器辅助工具（permissions / onebot 模块）
pip install -e "./packages/core[onebot]"
```

### 2. 本地 Wheel 构建与安装

在仓库根目录下构建并输出至 `dist/` 目录：

```bash
python -m pip install build
python -m build --outdir dist packages/core
```

构建完成后，可在独立宿主环境中直接安装生成的 wheel 产物：

```bash
pip install dist/nonebot_plugin_xducraft_core-0.1.0-py3-none-any.whl

# 若需要 OneBot 适配器扩展支持：
pip install "dist/nonebot_plugin_xducraft_core-0.1.0-py3-none-any.whl[onebot]"
```

---

## 接入与使用规范

### 1. 生命周期加载顺序：先 init 再 require

NoneBot 启动初始化时，生命周期绑定必须在 `nonebot.init()` 之后完成。在业务插件注册配置或拦截事件之前，必须先通过 `require("xducraft_config")` 确保核心生命周期插件已加载：

- **配置文件加载**（项目根目录 `pyproject.toml`）：
  ```toml
  [tool.nonebot]
  plugins = ["xducraft_config"]
  plugin_dirs = ["xducraft_bot/plugins"]
  ```
- **代码中显式声明依赖**：在所有依赖 Core 门禁与配置存储的业务插件入口顶部，优先调用 `require("xducraft_config")`。

### 2. 插件接入配置核心最小示例

业务插件通过继承 `ConfigModel` 并调用 `register_config` 注册原生 Pydantic 配置模型。

> [!IMPORTANT]  
> - **先 require 后导入 SDK**：确保生命周期门禁与存储上下文已就绪。
> - **独立存储不污染 NoneBot 配置缓存**：Core 使用 SQLite 存储独立管理各群与全局生效快照，**不会修改或污染 NoneBot 的 `get_plugin_config` 全局配置缓存**。读取与更新请统一使用 Core 提供的 `get_config` 与 `update_config`，不要混用 `get_plugin_config`。
> - **写入模式规范**：群级原生资源写入模式为全量替换（`write_mode="replace"`），更新必须传入该群的完整配置快照字典，省略字段将以模型声明的默认值补齐；全局原生资源写入模式为局部补丁（`write_mode="patch"`），支持使用 `{"set": {...}, "unset": [...]}` 协议。

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

# 6. 业务中更新配置示例
async def set_welcome_message(group_id: int, new_text: str) -> None:
    # 群级原生资源写入模式为全量替换（write_mode="replace"），省略字段会按模型默认值补齐；
    # 此处传入本群完整配置快照字典
    await update_config(
        "my_notice",
        {"welcome_text": new_text},
        scope="group",
        scope_id=group_id,
    )

async def set_daily_quota(new_quota: int) -> None:
    # 全局原生资源写入模式为局部补丁（write_mode="patch"），支持通过 {"set": {...}} 协议更新
    await update_config(
        "my_notice",
        {"set": {"max_daily_notices": new_quota}},
        scope="global",
    )
```

---

## 数据路径与存储规范

### 1. 运行时数据根目录决策

Core 通过 `xducraft_bot.shared.data_paths` 统一确定运行时数据根目录：

1. **显式指定优先**：启动前若设置了 `XDUCRAFT_DATA_DIR` 环境变量（必须为绝对路径，且不能与已安装的代码包重叠），系统严格使用该外部根目录。
2. **自动旧宿主识别**：
   - 若未显式设置 `XDUCRAFT_DATA_DIR`，且检测到唯一存在的旧版 `xducraft_bot/shared/data` 目录；
   - 或检测到源码宿主标记（非 SDK 自身命名空间根目录下包含 `plugins/` 目录且父目录存在 `pyproject.toml`，即使旧数据目录尚未创建），系统保留预期的旧版源码内数据路径。
   - 若存在多个相互冲突的旧候选路径，将抛出 `DataPathError` 并拒绝猜测。
3. **全新独立安装**：在无旧布局源码标记且未设置环境变量的全新独立运行环境中，自动使用操作系统标准用户数据目录（通过 `platformdirs.user_data_path("xducraft", appauthor=False)`），绝不向 site-packages 等安装代码目录写入运行时数据。

### 2. 数据库选择优先级与数据隔离

- **配置数据库优先级**：显式构造参数 `database(path)` > 环境变量 `XDUCRAFT_CONFIG_DB` > 所选数据根目录下的默认配置库（`<ROOT>/core/configuration.sqlite3`，旧布局为 `xducraft_bot/shared/data/configuration.sqlite3`）。
- **外置配置数据库不自动搬迁数据**：指定外置配置数据库仅接管配置存储本身，系统绝不会自动搬迁、重定向或覆盖其他业务持久化数据（如聊天记录、反撤回媒体、MC 状态游标等）。
