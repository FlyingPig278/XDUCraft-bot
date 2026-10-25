# XDUCraft MC Status (`nonebot-plugin-xducraft-mc-status`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的 Minecraft 服务器状态查询与像素风格状态图渲染插件。

---

## 功能说明

- **多级服务器树查询**：支持在群内配置任意深度的服务器树（子服/代理服/跨服网络），自动排版展示父子服关系、备注、标签与延迟。
- **像素图精美渲染**：按原版风格解析 Minecraft 颜色代码（`§`）与 MOTD 描述，支持自定义背景材质或单次查询临时指定材质。
- **多查询源容灾**：支持 Java 原生 Socket 协议直连查询、高校公共 API 源（交大、吉大等）及自建后端源，支持自动故障转移。
- **内置字体与材质随包分发**：Wheel 包中已完整打包专有像素字体、界面图标与全部原版方块材质，生产部署无需外部素材依赖。
- **双重门禁要求**：全局总开关（`mc_status`）与群插件开关默认均为关闭。正常生效必须满足：
  1. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `mc_status`；
  2. 开启本群插件开关及功能（发送 `/功能 on MC 服务器状态` 或 `/功能 on mc_status`，系统会自动同步本群插件总开关）。

---

## 常用指令

| 指令 | 别名 | 说明 |
| :--- | :--- | :--- |
| `/mcs` | `/mcstatus`、`/服务器`、`/状态` | 查询本群配置的服务器状态总览图 |
| `/mcs all` | - | 强制显示全部服务器（包含离线与忽略节点） |
| `/mcs <地址>` | - | 临时查询指定地址（如 `/mcs play.example.com`） |
| `/mcs texture=<方块>` | - | 临时更换渲染背景（如 `/mcs texture=dirt`、`random`） |
| `/mcs auth` | - | 查看或设置本群默认登录认证模式 |
| `/mcs source` / `/mcs api` | - | 查看或配置本群查询源类型及后端 API 地址 |

---

## 配置项与作用域

- **群级独立配置 (`group_only`)**：
  - **服务器树 (`servers`)**：支持每群独立维护多层服务器树，支持配置 IP、备注、自定义短标签与颜色、隐藏真实地址、显示别名、认证模式以及排序权重；
  - **查询源设置**：本群查询方式（`status_api_source`）与专用 API 地址；
  - **外观与展示**：`footer`（页脚说明文案）、`show_offline_by_default`（默认是否展示离线服务器）。
- **启动期部署参数 (`global_only`，需重启生效)**：
  - `MCS_BRAND`：顶栏品牌标识（支持 `§` 颜色码）；
  - `MCS_TITLE`：状态图主标题；
  - `MCS_CREDIT`：状态图底部版权署名；
  - `MCS_TEXTURE`：默认材质（支持 `random`、`none` 或方块英文名）；
  - `MCS_CANVAS_WIDTH` / `MCS_MIN_HEIGHT`：出图画布基准宽度与最小高度。

---

## 安装与加载

本插件处于内部演进阶段，尚未发布至公共 PyPI 仓库。

**源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/mc-status
```

**Wheel 构建与联合安装**：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/mc-status
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_mc_status-0.1.0-py3-none-any.whl
```

**宿主加载（`pyproject.toml`）**：
```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_mc_status",
]
```

---

## 数据存储边界

1. **配置数据迁移**：历史 `server_data.json` 仅作为启动期单次导入源。首次启动由 Core 一次性导入至 Core SQLite（`mc_status` 命名空间），确立记录后旧文件不再写入；若历史配置损坏直接中断启动。
2. **纯净缓存设计**：运行时拉取的状态临时缓存由 `plugin_cache_dir("mc_status")` 统一管理，不写入配置数据库，亦不污染持久化目录。
