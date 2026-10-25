# XDUCraft Happy Bot (`nonebot-plugin-xducraft-happy-bot`) 0.2.0

基于 NoneBot 2 与 OneBot v11 适配器的群聊表情回应插件。

当机器人在群聊中被 `@` 或被成员回复消息时，插件会自动调用协议端 API 为该消息贴上预设表情回应。本插件已解耦为独立分发包。

---

## 功能特性

- **被动表情贴附**：在群聊中被 `@` 机器人或被回复时，自动调用 OneBot v11 扩展接口 `set_msg_emoji_like` 进行表情贴附。
- **消息链非阻断**：作为被动响应规则，优先级设为 `99` 且声明 `block=False`。在响应表情贴附的同时，绝不阻断后续其他功能插件（如词云统计、反撤回监控等）接收该条消息。
- **协议端容错降级**：调用 `set_msg_emoji_like` 时若协议端（如特定 OneBot 实现）不支持该接口或调用失败，插件捕获异常并仅在控制台输出调试日志（`debug` 级别），绝不抛出未处理异常打断正常消息处理链。
- **每群独立表情配置**：表情 ID 按群完全隔离存储。管理面板和交互命令仅修改本群独立参数，新群默认使用代码初始值 `123`，不存在向全局动态继承的回退逻辑。
- **双重门禁安全机制**：受管插件全局总开关（`happy_bot`）与群级功能开关（`emoji_reaction`）默认均为关闭（`OFF`），新加入群聊不会默认主动响应，必须经两层门禁显式开启。

---

## 标识与命名空间说明

为避免命名混淆，请明确区分以下三个维度的标识：

| **发行包名 (Distribution Name)** | `nonebot-plugin-xducraft-happy-bot` | `pip` 安装、依赖声明及构建 wheel 时使用的发行包名（版本 `0.2.0`）。 |
| **插件加载名 (Plugin Name)** | `xducraft_happy_bot` | NoneBot 插件生命周期加载标识，用于 `pyproject.toml` 中的 `plugins` 配置。 |
| **依赖的 Core SDK 命名空间** | `xducraft_bot.shared.*` | 引用 Core 提供的功能门禁、配置系统及数据路径等 SDK 接口。 |
| **配置项键 (Config Key)** | `happy_bot` | 插件在 Core 声明式配置体系中注册的配置命名空间。 |
| **功能门禁键 (Feature Key)** | `emoji_reaction` | 统一功能开关（`/功能`）与门禁系统中的被动功能注册键（名称为“表情回应”）。 |

---

## 指令列表与权限控制

| 指令 | 别名 | 权限要求 | 说明 |
| :--- | :--- | :--- | :--- |
| `/ans` | `/answer`、`/表情回应` | 群成员均可 | 查看本群当前表情回应启用状态与当前表情 ID |
| `/ans set <emoji_id>` | - | 仅群管理员 / 群主 | 修改本群表情回应使用的数字表情 ID（`emoji_id` 必须为纯数字） |

> [!TIP]
> - 表情回应的群级启停请使用统一功能管理命令：`/功能 on 表情回应` 或 `/功能 off 表情回应`，亦可在 WebUI 网页管理面板的群卡片中直接开关。
> - 普通群成员可以发送 `/ans` 查看当前群的设置；修改设置时若非群管理人员，机器人将提示权限不足并拒绝修改。

---

## 安装方式

> [!NOTE]
> 本软件包目前处于内部演进阶段，**尚未发布至公共 PyPI 仓库**。请勿尝试直接执行 `pip install nonebot-plugin-xducraft-happy-bot`。
> 安装前必须确保宿主环境已安装 Core 核心包（`nonebot-plugin-xducraft-core[onebot]>=0.3.0,<0.4.0`）。

### 1. 本地源码可编辑模式安装（推荐）
在主仓库开发环境中，根目录 `requirements.txt` 已包含 `-e ./packages/happy-bot`。如需单独安装：

```bash
pip install -e ./packages/happy-bot
```

### 2. 本地 Wheel 构建与安装

在仓库根目录下构建 wheel 产物至 `dist/` 目录：

```bash
python -m pip install build
python -m build --outdir dist packages/happy-bot
```

构建完成后，可在目标宿主虚拟环境中直接安装生成的 wheel 文件：

```bash
pip install dist/nonebot_plugin_xducraft_happy_bot-0.2.0-py3-none-any.whl
```

---

## 宿主配置与接入规范

### 1. 显式生命周期加载

插件代码入口处已通过 `require("xducraft_config")` 自行确保 Core 配置生命周期与门禁前置就绪。在 NoneBot 宿主项目的配置文件（`pyproject.toml`）中，`plugins` 列表应**显式同时声明** `xducraft_config` 与 `xducraft_happy_bot`：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_happy_bot",
]
```

### 2. 门禁配置生效条件

机器人响应群内表情回应必须同时满足以下条件：
1. **全局总开关开启**：Core 管理后台或系统级门禁中 `happy_bot` 全局开关处于开启状态。
2. **群级开关开启**：目标群已执行 `/功能 on 表情回应` 或在管理面板群卡片中开启了表情回应功能。
3. **被 @ 或被回复**：群消息确实 `@` 机器人或直接对机器人的发言进行了回复（`event.is_tome()` 或回复对象为机器人自身）。

---

## 运行时数据路径与兼容边界

插件的活跃群表情配置实际托管于 Core 声明式配置系统的 SQLite 数据库中（即 `config_documents` 表中的 `happy_bot` 命名空间），**绝不向文件系统读写实时 JSON 配置文件**：

- **活跃配置存储位置**：活跃配置持久化于 Core 所选的 SQLite 数据库（优先级：显式 `database(path)` > 环境变量 `XDUCRAFT_CONFIG_DB` > 默认 `<ROOT>/core/configuration.sqlite3`），在 POSIX 环境下由 Core 严格受限于 `0600` 文件权限。
- **启动期声明式单次导入机制**：Happy Bot 通过 `bind_configuration()` 注册 `PluginConfiguration`，并显式挂载 `migrate_legacy=manager.migrate_legacy_config` 回调。在 NoneBot 启动且所有插件加载完毕后，Core 按稳定插件 key 顺序统一调用该迁移入口。
- **启动中断故障策略（Abort on Error）**：在迁移导入过程中，若历史 `emoji_like_config.json` 损坏、包含无效 JSON 或不可读，系统将立即抛出异常并中断 NoneBot 启动；**绝对严禁**吞没异常或静默使用代码默认配置（如默认表情 `123` 或空映射）覆盖不可读的历史数据，以杜绝历史配置丢失。
- **无第二写入源（No Second Writer）**：一旦 SQLite 中成功确立 `happy_bot` 命名空间活跃文档，所有读取与写入（如 `/ans set <emoji_id>`）均严格持久化于 SQLite；历史 `emoji_like_config.json` 仅作为一次性导入源，后续外部修改该旧文件绝不会生效，系统亦不会删除或重写旧文件。
- **全新环境无文件开销**：在全新独立环境中，`ConfigDocumentStore` 直接以代码默认文档（`{"schema_version": 2, "groups": {}}`）在 Core 选定的 SQLite 数据库中初始化，**绝不自动创建任何 JSON 目录，也绝不进行任何文件复制或搬迁**。

### 历史配置导入路径查找逻辑
Core 提供的 `plugin_data_dir("happy_bot", ..., legacy_relative_path=LEGACY_DATA_PATH)` 仅用于决策**历史配置文件（`emoji_like_config.json`）的单次导入回退查找位置**：

1. **显式数据根目录（`XDUCRAFT_DATA_DIR`）**：若启动前配置了环境变量 `XDUCRAFT_DATA_DIR`，仅将 `<ROOT>/plugins/happy_bot/` 作为历史 JSON 的查找位置；活跃配置依然存储于 `<ROOT>/core/configuration.sqlite3`（除非通过 `XDUCRAFT_CONFIG_DB` 或显式数据库路径另行指定）。
2. **旧源码宿主兼容**：当独立包安装于包含旧插件数据目录的源码宿主且未设置 `XDUCRAFT_DATA_DIR` 时，通过 Core 0.2.0 为既有 `plugin_data_dir` 新增的 `legacy_relative_path` 参数，精准定位旧源码路径 `xducraft_bot/plugins/xducraft_happy_bot/data/`，确保历史 `emoji_like_config.json` 可被单次导入。
3. **全新独立安装**：在无旧源码宿主标记且未配置外部数据根的全新独立运行环境中，历史文件查找路径回退至操作系统标准用户数据目录（通过 `platformdirs.user_data_path("xducraft", appauthor=False)`）。

> [!IMPORTANT]
> - **纯路径决策原则**：`plugin_data_dir` 仅执行只读路径计算以供历史配置定位，**绝不自动创建目录，也绝不自动搬迁、重定向或复制历史数据**。
> - **存储位置兼容而非代码 Shim**：此处的兼容性是指历史数据文件读取位置的向前兼容，而非 Python 模块导入层面的 shim 兼容。
