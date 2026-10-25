# XDUCraft Happy Bot (`nonebot-plugin-xducraft-happy-bot`) 0.2.0

基于 NoneBot 2 与 OneBot v11 适配器的群聊表情回应插件。

当机器人在群聊中被 `@` 或被成员回复消息时，插件会自动调用协议端 API 为该消息贴上预设表情回应。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能特性

- **被动表情贴附**：在群聊中被 `@` 机器人或被回复时，自动调用 OneBot v11 扩展接口 `set_msg_emoji_like` 进行表情回应。
- **消息链非阻断**：作为被动响应规则，优先级设为 `99` 且声明 `block=False`，绝不阻断后续其他功能插件（如词云统计、反撤回监控等）接收该条消息。
- **协议端容错降级**：若协议端不支持该接口或调用失败，插件捕获异常并仅在控制台输出调试日志，绝不抛出未处理异常打断消息链。
- **每群独立表情配置**：表情 ID 按群完全隔离存储。管理面板和交互命令仅修改本群独立参数，新群默认使用代码初始值 `123`。
- **双重门禁安全机制**：受管插件全局总开关（`happy_bot`）与群级功能开关（`emoji_reaction`）默认均为关闭（`OFF`）。全局关闭具有最高优先级；开启必须经两层门禁显式打开。

---

## 标识与命名空间说明

| 维度 | 标识 | 说明 |
| :--- | :--- | :--- |
| **发行包名** | `nonebot-plugin-xducraft-happy-bot` | `pip` 安装与依赖声明标识（版本 `0.2.0`）。 |
| **插件加载名** | `xducraft_happy_bot` | NoneBot 插件加载标识，用于 `pyproject.toml` 中的 `plugins` 配置。 |
| **依赖 Core 插件** | `xducraft_config` | Core 核心配置与生命周期插件，入口处通过 `require("xducraft_config")` 预加载。 |
| **配置项键** | `happy_bot` | Core 声明式配置体系中的配置命名空间。 |
| **功能门禁键** | `emoji_reaction` | 统一功能开关（`/功能`）中注册的特性键名（显示名：`表情回应`）。 |

---

## 指令列表与权限控制

| 指令 | 别名 | 权限要求 | 说明 |
| :--- | :--- | :--- | :--- |
| `/ans` | `/answer`、`/表情回应` | 群成员均可 | 查看本群当前表情回应启用状态与当前表情 ID |
| `/ans set <emoji_id>` | - | 仅群管理员 / 群主 | 修改本群表情回应使用的数字表情 ID（`emoji_id` 必须为纯数字） |

> [!TIP]
> - 表情回应的群级启停可使用统一功能管理命令：`/功能 on 表情回应` 或 `/功能 off 表情回应`，亦可在 WebUI 网页管理面板的群卡片中直接开关。
> - 普通群成员可以发送 `/ans` 查看当前群的设置；修改设置必须具备群管理人员权限。

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Happy Bot 插件
pip install "nonebot-plugin-xducraft-happy-bot @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-happy-bot.git@v0.2.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_happy_bot",
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

1. **单一活跃配置源**：本插件采用 Core 的声明式配置文档系统。活跃配置统一持久化保存在 Core SQLite 数据库中的 `happy_bot` 命名空间。
2. **启动期单次历史导入**：若存在历史配置文件 `emoji_like_config.json`，Core 将在启动阶段执行单次导入并确立活跃文档，导入后旧文件不再写入。若历史 JSON 损坏，系统将抛出异常中断启动，绝不静默覆盖。
3. **数据目录环境变量**：若需要自定义外部数据目录，必须在启动前通过操作系统环境变量配置 `XDUCRAFT_DATA_DIR`（绝对路径），切勿仅写在 live `.env` 中。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

第三方依赖项与协议端接口规范遵循各自独立的授权许可。
