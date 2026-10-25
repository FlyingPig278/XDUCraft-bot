<div align="center">

# XDUCraft Bot

<a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" alt="Python Version">
</a>
<a href="https://v2.nonebot.dev/">
    <img src="https://img.shields.io/badge/NoneBot-2.0.0+-red?logo=nonebot" alt="NoneBot Version">
</a>
<a href="https://github.com/onebotdev/onebot/blob/master/v11/README.md">
    <img src="https://img.shields.io/badge/OneBot-v11-green?logo=telegram" alt="OneBot Version">
</a>

基于 NoneBot 2（OneBot v11 适配器）的 XDUCraft 社区群管理与 Minecraft 服务器运维机器人宿主。
整仓采用模块化解耦架构，由 12 个独立发行包组装而成，接入声明式配置核心与 Naive UI 网页管理面板。

</div>

---

## 📦 架构概览与子包清单

宿主根目录作为纯净的装配容器（`plugin_dirs = []`），通过 `pyproject.toml` 显式加载并引入各独立子包：

| 目录 (`packages/`) | 发行包名 (`Distribution Name`) | 加载名 (`Plugin Name`) | 版本 | 定位与门禁 | 核心功能简介 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `core` | `nonebot-plugin-xducraft-core` | `xducraft_config` | 0.3.0 | 基础设施 (`managed=False`) | SQLite 单活跃配置存储、双重门禁预处理器、数据路径决策 SDK |
| `features` | `nonebot-plugin-xducraft-features` | `xducraft_features` | 0.1.0 | 基础设施 (`managed=False`) | QQ 端 `/功能` 集中管理命令，动态枚举与切换群功能 |
| `admin` | `nonebot-plugin-xducraft-admin` | `xducraft_admin` | 0.1.0 | 基础设施 (`managed=False`) | Vue 3 + Naive UI 本地回环 WebUI 管理面板，Schema 驱动渲染 |
| `happy-bot` | `nonebot-plugin-xducraft-happy-bot` | `xducraft_happy_bot` | 0.2.0 | 受管业务插件 | 群聊被 `@` 或被回复时自动贴附表情回应（功能名：`表情回应`） |
| `auto-friend` | `nonebot-plugin-xducraft-auto-friend` | `xducraft_auto_friend` | 0.1.0 | 受管业务插件 | 自动核验白名单群成员并同意好友申请（功能名：`自动加好友`） |
| `keyword` | `nonebot-plugin-xducraft-keyword` | `xducraft_keyword` | 0.1.0 | 受管业务插件 | 群级多模式关键词自动回复与入群欢迎消息（功能名：`关键词回复`） |
| `pig-bot` | `nonebot-plugin-xducraft-pig-bot` | `xducraft_pig_bot` | 0.1.0 | 受管业务插件 | PigHub 猪猪图搜索与定时推送（双功能：`猪猪图查询`、`猪猪图推送`） |
| `mc-update` | `nonebot-plugin-xducraft-mc-update` | `xducraft_mc_update` | 0.1.0 | 受管业务插件 | 监控 Minecraft 官方正式版与快照更新并推送（功能名：`MC 更新推送`） |
| `invite` | `nonebot-plugin-xducraft-invite` | `xducraft_invite` | 0.1.0 | 受管业务插件 | 核心群成员资格校验与白名单邀请码私聊发放（功能名：`邀请码自助领取`） |
| `anti-recall` | `nonebot-plugin-xducraft-anti-recall` | `xducraft_anti_recall` | 0.1.0 | 受管业务插件 | 群撤回消息监听、媒体按需固化与私聊转发查询（功能名：`反撤回`） |
| `wordcloud` | `nonebot-plugin-xducraft-wordcloud` | `xducraft_wordcloud` | 0.1.0 | 受管业务插件 | 记录群聊文本、内置思源黑体，每日 00:00 发放词云（功能名：`群聊词云`） |
| `mc-status` | `nonebot-plugin-xducraft-mc-status` | `xducraft_mc_status` | 0.1.0 | 受管业务插件 | Minecraft 服务器状态树查询，内置字体材质渲染卡片（功能名：`MC 服务器状态`） |

---

## 🚀 快速开始

### 1. 运行环境要求
- **Python**：3.9+（建议在独立虚拟环境中运行）
- **Node.js**：`^20.19.0 || >=22.12.0`（**仅源码编译 WebUI 静态产物时需要**；使用构建好的 Wheel 运行时无需 Node 环境）
- **OneBot 协议端**：支持 OneBot v11 的框架（推荐 [NapCat](https://github.com/NapNeko/NapCatQQ)）

### 2. 代码获取与依赖安装
```bash
git clone https://github.com/FlyingPig278/XDUCraft-bot.git
cd XDUCraft-bot

# 创建并激活虚拟环境
python -m venv venv
# Windows: venv\Scripts\activate  |  Linux/macOS: source venv/bin/activate

# 安装整仓依赖（通过可编辑模式一次性引入 packages/* 全部 12 个本地包）
pip install -r requirements.txt
```

### 3. 构建管理前端产物 (WebUI)
管理面板前端源码位于 `packages/admin/webui`：
```bash
cd packages/admin/webui
npm ci
npm run build
cd ../../..
```
> [!NOTE]
> 若在源码开发模式下未构建前端产物，机器人和后端 API 仍可启动，浏览器访问前端页面将返回 503 提示。

### 4. 环境变量与启动
管理口令拥有机器人控制权限，**仅从环境变量读取，严禁写入配置文件或版本控制**：
```bash
# Linux / macOS 示例：
export WEB_ADMIN_ENABLED="true"
export WEB_ADMIN_PORT="8765"
export WEB_ADMIN_PASSWORD="your-strong-password-here"  # 强约束至少 12 字符
nb run
```
```powershell
# Windows PowerShell 示例：
$env:WEB_ADMIN_ENABLED = "true"
$env:WEB_ADMIN_PORT = "8765"
$env:WEB_ADMIN_PASSWORD = "your-strong-password-here"  # 强约束至少 12 字符
nb run
```

### 5. 协议端连接与面板访问
- **反向 WebSocket 连接**：将协议端配置为反向 WebSocket 客户端，连接至 `ws://127.0.0.1:8080/onebot/v11/ws`。
- **管理面板访问**：面板仅监听本地回环地址（`127.0.0.1:8765`）。
  - **本机运行**：浏览器直接打开 `http://127.0.0.1:8765/`。
  - **远程服务器部署**：在本地客户端建立 SSH 隧道，严禁直接暴露在公网：
    ```bash
    ssh -N -L 8765:127.0.0.1:8765 user@your-server-ip
    ```
    在本地浏览器打开 `http://127.0.0.1:8765/` 即可安全登录。

---

## ⚙️ 核心架构与门禁机制

### 1. 双重门禁与开关联动规则
- 所有受管业务插件的全局总开关与群级开关**默认均为关闭（OFF）**。
- **全局总停用具有最高支配权**：全局停用时，拦截 Matcher 响应、私聊指令与后台定时任务；群级已开启状态保持独立保存，面板中展示“待全局开启”。
- **单功能与多功能插件开关联动差异**：
  - **单功能插件**（如群聊词云、表情回应、反撤回等）：通过 `/功能 on <名称>` 开启时，Core 会自动同步开启该群的插件总开关（前提仍需全局总开关已开启）。
  - **多功能插件**（如猪猪图插件，同时包含 `pig_query` 与 `pig_auto_push`）：开启单项功能**不会自动联动开启群插件总开关**，必须在 WebUI 或通过 SDK 单独开启该群的插件总开关。
- 基础设施插件（Core、Features、Admin）声明为 `managed=False`，不受业务门禁拦截。

### 2. 配置持久化与单次导入
- **活跃配置存储**：由 Core 的 SQLite 数据库（`core/configuration.sqlite3`，POSIX 权限 `0600`）持久化接管。
- **单次导入机制**：历史插件 JSON 文件仅作为启动期单次导入输入。首次导入成功确立 SQLite 记录后，旧 JSON 文件不再作为写入者，亦不会被删除；若历史文件损坏则直接中断启动（Abort on Error），杜绝静默丢失配置。
- **启动覆盖与 `.env` 基线**：部署期启动参数覆盖保存在 Core SQLite 的 `deployment_overrides` 中，`.env` 作为基线引导不被全量复制。清除覆盖项后下一次重启自动回退为 `.env` 基准值。

### 3. 业务数据与配置严格隔离
业务持久化数据保留在独立存储中，不混入 Core 配置数据库：
- **聊天记录**：词云持久化于独立数据库 `chat_logs.db`；
- **反撤回媒体与记录**：持久化于 `anti_recall.db` 与 `media/`；
- **MC更新订阅例外**：`subscription.json` 混合存储群订阅列表与版本检查游标，属于活跃业务状态，**未被迁移至 Core 配置数据库**；
- **关键词媒体**：外部数据根下路径为 `<ROOT>/plugins/keyword/media/`（旧源码布局为 `xducraft_bot/plugins/xducraft_keyword/data/media/`）。

---

## 🗄️ 运行时数据目录与离线迁移

### 1. 数据目录路径决策 (`XDUCRAFT_DATA_DIR`)
- **显式环境变量优先**：启动前若设置了 `XDUCRAFT_DATA_DIR`（绝对路径且不与代码包目录重叠），以此为外部数据根（`<ROOT>/core/`、`<ROOT>/plugins/<key>/` 等）。
- **未设置时的回退**：若检测到源码宿主或旧数据目录，通过 `legacy_relative_path` 兼容定位历史文件；全新独立安装环境则回退至操作系统标准用户数据目录（`platformdirs.user_data_path('xducraft')`）。

### 2. 离线快照迁移与操作规范 (`scripts/migrate_runtime_data.py`)
> [!WARNING]
> **生产部署提示**：生产基准版本为 `dc47f8e763fbf0cb34701992a345a405d787b79a`。本地环境数据非生产真实数据，切勿盲目直接覆盖生产部署环境；进行生产变更前必须停机并制作验证快照。

- **停机要求**：迁移或恢复前**必须彻底停止 NoneBot 机器人及所有写进程**。
- **目标路径要求**：执行命令前，**目标目录的父目录必须已存在，目标目录本身必须不存在**；工具拒绝软链接与重解析点。
- **核实活动配置库**：若源实例已有 Core 配置库，须用 `--config-db "真实库路径"` 显式指定；设置过 `XDUCRAFT_CONFIG_DB` 时尤其不能省略。若从 `dc47f8e` 首次升级，确认尚无 Core 配置库且未设置此变量，则省略该参数，由首次启动导入旧 JSON，**不要创建空库冒充历史配置**。
- **冷备份与运行副本分离**：制作快照后请妥善保留该冷备份，**切勿直接将验证快照作为活动运行根**。应从快照制作活动工作副本，再设置环境变量：
  ```powershell
  # 1. 从旧源码布局制作冷备份；此例为尚无 Core SQLite 的首次升级
  python scripts/migrate_runtime_data.py migrate --source "C:\bot\XDUCraft-bot" --destination "C:\bot\snapshots\v1"

  # 2. 从快照导出独立活动运行副本
  python scripts/migrate_runtime_data.py migrate --source-layout runtime --source "C:\bot\snapshots\v1" --destination "C:\bot\runtime_data"

  # 3. 设置外部数据根
  $env:XDUCRAFT_DATA_DIR = "C:\bot\runtime_data"
  ```
- 已有配置库时，步骤 1 加 `--config-db "源实例真实库路径"`，步骤 2 加 `--config-db "C:\bot\snapshots\v1\core\configuration.sqlite3"`；第二步不能再指向源实例的活动库。
- **外置库审阅**：若原环境配置了 `XDUCRAFT_CONFIG_DB`，设置 `XDUCRAFT_DATA_DIR` **不会覆盖该变量**。启用新 Root 时必须同步决定是指向工作副本内的 `core/configuration.sqlite3` 还是继续使用独立外置库。
- **回退方案**：生产回退**绝不能仅靠 `git revert`**；若运行中产生了新写入，必须先对最新运行目录完整快照，再安全恢复或切回。

---

## ❓ 常见问题排查 (FAQ)

- **Q: 浏览器访问管理面板出现 503？**
  **A**: 尚未构建前端产物。进入 `packages/admin/webui` 执行 `npm ci && npm run build` 即可。
- **Q: 群卡片显示“待全局开启”？**
  **A**: 说明该插件在本群保存为开启，但全局总开关处于关闭状态。进入群配置详情页点击“前往全局开关”或在插件页开启总开关即可生效。
- **Q: 修改了启动期设置后为何没有变化？**
  **A**: 启动期参数涉及插件单例与底层初始化，保存后需**重启 NoneBot 进程**方可生效。
- **Q: 保存配置时提示 409 Conflict？**
  **A**: 遇到并发修改冲突。系统已保留当前表单草稿，请核对后刷新页面获取最新配置再次提交。
