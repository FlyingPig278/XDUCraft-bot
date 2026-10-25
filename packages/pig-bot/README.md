# XDUCraft Pig Bot (`nonebot-plugin-xducraft-pig-bot`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的 PigHub 猪猪图查询与定时群推送插件。

支持从 PigHub 检索匹配的表情图片，并支持通过 APScheduler 定时任务每 6 小时向开启推送的群发送随机精选猪猪图。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能特性与门禁联动

- **关键词图片检索**：从 PigHub 检索匹配的表情图片；匹配多张时使用合并转发，防止刷屏。
- **定时群推送**：定时向订阅群发送随机精选猪猪图，后台任务受双重门禁严格约束，全局关闭或群关闭时绝不外发。
- **双独立功能门禁**：注册了两个独立的群功能：
  - `pig_query`（显示名：`猪猪图查询`，手动 `/pig` 查询）；
  - `pig_auto_push`（显示名：`猪猪图推送`，定时推送）。
- **多功能插件开关联动规则**：
  - 本插件包含多项独立功能，**不属于单功能插件**。
  - 在群内发送 `/功能 on 猪猪图查询` 仅会改变该功能的启用状态，**不会自动开启本群的插件总开关**。
  - 要在群内正常使用，必须同时确保：
    1. 全局总开关 `pig_bot` 处于开启状态（在 WebUI 插件页或通过 Core SDK 开启）；
    2. 本群插件总开关处于开启状态（在 WebUI 群卡片或通过 Core SDK 开启）；
    3. 目标具体功能（查询或推送）处于开启状态。

---

## 标识与命名空间说明

| 维度 | 标识 | 说明 |
| :--- | :--- | :--- |
| **发行包名** | `nonebot-plugin-xducraft-pig-bot` | `pip` 安装与依赖声明标识（版本 `0.1.0`）。 |
| **插件加载名** | `xducraft_pig_bot` | NoneBot 插件加载标识，用于 `pyproject.toml` 中的 `plugins` 配置。 |
| **依赖 Core 插件** | `xducraft_config` | Core 核心配置与生命周期插件，入口处通过 `require("xducraft_config")` 预加载。 |
| **配置项键** | `pig_bot` | Core 声明式配置体系中的配置命名空间。 |
| **功能门禁键** | `pig_query`、`pig_auto_push` | 统一功能管理中注册的特性键名（分别对应手动查询与自动推送）。 |

---

## 指令列表与权限控制

| 指令 | 权限要求 | 说明 |
| :--- | :--- | :--- |
| `/pig [关键词]` | 群成员均可 | 查询猪猪图；未带关键词则随机抽取 |
| `/pig query on\|off` | 群管理 / 群主 / 超管 | 开启或关闭本群手动查询功能 |
| `/pig auto on\|off` | 群管理 / 群主 / 超管 | 开启或关闭本群定时自动推送功能 |
| `/pig status` | 群管理 / 群主 / 超管 | 查看本群猪猪图各开关状态与参数 |

> [!TIP]
> 亦可通过统一命令开关对应特性：`/功能 on 猪猪图查询` 或 `/功能 on 猪猪图推送`。请注意先确认全局总开关与本群插件总开关已开启。

---

## 配置参数

- **群级独立参数 (`group_only`)**：
  - `max_forward_results`：本群合并转发上限（默认 5），查询命中多张图片时最多随机抽取的张数。

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Pig Bot 插件
pip install "nonebot-plugin-xducraft-pig-bot @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-pig-bot.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_pig_bot",
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

1. **单一活跃配置源**：本插件采用 Core 的声明式配置文档系统。活跃配置统一持久化保存在 Core SQLite 数据库中的 `pig_bot` 命名空间。
2. **启动期单次历史导入**：若存在历史配置文件 `pig_bot_config.json`，Core 将在启动阶段执行单次导入并确立活跃文档，导入后旧文件不再写入。若历史 JSON 损坏，系统将抛出异常中断启动，绝不静默覆盖。
3. **无本地媒体库与业务库**：表情图片实时请求外部 PigHub 接口，本地不保存图片，不引入额外业务数据库。
4. **数据目录环境变量**：若需要自定义外部数据目录，必须在启动前通过操作系统环境变量配置 `XDUCRAFT_DATA_DIR`（绝对路径），切勿仅写在 live `.env` 中。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

第三方 API 接口与图片资源版权属于原作者或图库托管方。
