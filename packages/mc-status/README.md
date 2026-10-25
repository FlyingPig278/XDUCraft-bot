# XDUCraft MC Status (`nonebot-plugin-xducraft-mc-status`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的 Minecraft 服务器状态查询与像素风格状态图渲染插件。

支持多级服务器树结构、原版样式 MOTD 与颜色代码（`§`）解析、自适应材质背景渲染，以及直连与后端多源容灾查询。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能特性

- **多级服务器树查询**：支持在群内配置任意深度的服务器树（子服/代理服/跨服网络），自动排版展示父子服关系、备注、标签与延迟。
- **像素图精美渲染**：按原版风格解析 Minecraft 颜色代码（`§`）与 MOTD 描述，支持自定义背景材质或单次查询临时指定材质。
- **多查询源容灾**：支持 Java 原生 Socket 协议直连查询、高校公共 API 源及自建独立后端源（`scripts/mc_status_backend`），支持单文件 `mcstatus` 兼容模式。
- **内置字体与材质资产**：Wheel 包内完整打包专用像素字体、界面图标与方块材质，生产部署无需外部素材依赖。
- **开发与调试工具集**：仓库内提供离线渲染工具 `scripts/preview_mc_status.py` 与背景材质预览工具 `scripts/preview_mc_texture.py`。
- **双重门禁安全机制**：全局总开关（`mc_status`）与群插件开关默认均为关闭（`OFF`）。正常生效必须满足：
  1. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `mc_status`；
  2. 开启本群插件开关及功能（发送 `/功能 on MC 服务器状态`，系统会自动同步本群插件总开关）。

---

## 常用指令

| 指令 | 别名 | 说明 |
| :--- | :--- | :--- |
| `/mcs` | `/mcstatus`、`/服务器`、`/状态` | 查询本群配置的服务器状态总览图 |
| `/mcs all` | - | 强制显示全部服务器（包含离线与忽略节点） |
| `/mcs <地址>` | - | 临时查询指定地址（如 `/mcs play.example.com`） |
| `/mcs texture=<方块>` | - | 临时更换渲染背景（如 `/mcs texture=dirt`、`random`） |
| `/mcs auth` | - | 查看或设置本群默认登录认证模式 |
| `/mcs source` | `/mcs api` | 查看或配置本群查询源类型及后端 API 地址 |

---

## 配置项与作用域

- **群级独立配置 (`group_only`)**：
  - `servers`：每群独立维护多层服务器树，支持配置 IP、备注、自定义短标签与颜色、隐藏真实地址、显示别名、认证模式以及排序权重；
  - `status_api_source` 与 `status_api_url`：本群查询方式（直连、公开源或自定义后端）与专用 API 地址；
  - `footer` 与 `show_offline_by_default`：页脚说明文案及默认是否展示离线服务器。
- **启动期部署参数 (`global_only`，需重启生效)**：
  - `MCS_BRAND`：顶栏品牌标识（支持 `§` 颜色码）；
  - `MCS_TITLE`：状态图主标题（支持 `§` 颜色码）；
  - `MCS_CREDIT`：状态图底部版权署名（支持 `§` 颜色码）；
  - `MCS_SHOW_GENERATED_AT`：是否在底栏右侧显示生成时间（布尔值，默认 `true`）；
  - `MCS_TEXTURE`：默认材质（留空按群号挑选，或 `random`、`none`、PNG 方块文件名）；
  - `MCS_WIDTH`：逻辑画布宽度（480–1600，默认 640）；
  - `MCS_SCALE`：渲染缩放倍率（仅接受偶数 `2` 或 `4`，默认 `2`）；
  - `MCS_MIN_HEIGHT`：出图最小逻辑高度（`0` 表示收缩到内容，默认 480）。
  启动期部署参数可在 `.env` 中提供基线，修改并保存至 Core SQLite 的 `deployment_overrides` 后将在下次重启生效；移除覆盖项后自动恢复为环境变量基准值。

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 MC Status 插件
pip install "nonebot-plugin-xducraft-mc-status @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-status.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_mc_status",
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

### 调试工具使用

仓库内 `scripts/` 目录提供了免启动机器人的本地离线渲染脚本：

```bash
# 1. 离线状态图渲染预览（使用假数据验证排版）
python scripts/preview_mc_status.py
python scripts/preview_mc_status.py --list

# 2. 材质背景平铺效果预览
python scripts/preview_mc_texture.py dirt
python scripts/preview_mc_texture.py cyan_glazed_terracotta --size 512
```

---

## 数据存储与历史迁移

1. **配置数据迁移**：历史 `server_data.json` 仅作为启动期单次导入源。首次启动由 Core 一次性导入至 Core SQLite（`mc_status` 命名空间），确立记录后旧文件不再写入；若历史配置损坏直接中断启动。
2. **纯净运行时缓存**：拉取的状态临时缓存由 `plugin_cache_dir("mc_status")` 统一管理，不写入配置数据库，亦不污染持久化目录。
3. **数据目录环境变量**：若需要自定义外部数据目录，必须在启动前通过操作系统环境变量配置 `XDUCRAFT_DATA_DIR`（绝对路径），切勿仅写在 live `.env` 中。

---

## 许可证与资产说明

- 本项目自身源码采用 [MIT License](LICENSE) 授权开源。
- 插件内包含的原版 Minecraft 方块材质、图标等美术资产遵循 Mojang 最终用户许可协议；像素字体遵循其原始发布协议。
- 本项目不主张上述第三方游戏与字体资产的 MIT 授权，相关资产授权单独保留。
