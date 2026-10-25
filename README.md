# XDUCraft Bot

基于 NoneBot 2（OneBot v11 适配器）的 XDUCraft 社区群管理与 Minecraft 服务器运维机器人部署宿主。

---

## 宿主定位与技术选型

本项目为 XDUCraft Bot 的生产部署宿主工程。经过模块化解耦，机器人的核心配置体系与各项业务功能已完全拆分至 12 个独立的 NoneBot 插件仓库中。

本仓库不包含任何内置插件源码，亦非对 NoneBot 框架的修改或 Fork，专注于提供标准化装配与运维支持：
- 装配与启动配置（`pyproject.toml`、`.env.prod.example`）；
- 离线数据迁移与备份保障（`scripts/migrate_runtime_data.py`）；
- 宿主集成验证套件（`tests/`）。

### 两种使用路径对比

| 场景 | 推荐方案 | 说明 |
| :--- | :--- | :--- |
| **自建通用机器人 / 按需挑选插件** | **官方 NoneBot 脚手架** | 使用 `nb create` 初始化标准 NoneBot 2 项目。先通过 Git 安装 `nonebot-plugin-xducraft-core[onebot]`，即可自由引入任何独立的 `nonebot-plugin-xducraft-*` 业务插件。WebUI 管理端（Admin）为可选组件，所有业务插件均可在无 WebUI 状态下独立运行。 |
| **开箱即用部署 / XDUCraft 完整节点** | **使用本部署宿主仓库** | 直接克隆本工程，通过锁定 Git Commit SHA 的 `requirements.txt` 一键安装全套受管插件，并利用预置的启动配置与迁移脚本进行生产运维。 |

> 本地或历史遗留的被忽略路径（如 `xducraft_bot/**/data`、`mcs-editor/`、`bot.py` 等）不随 Git 分发，亦不是插件源码安装源；各插件均作为独立外部包安装使用。

---

## 拆分子包与独立插件清单
所有功能插件均已解耦为独立 GitHub 仓库，使用 Git 标签安装，未在公共 PyPI 发布。各插件角色、加载模块及对应版本如下：

| 独立仓库 (`Repository`) | 定位与门禁 | 加载模块名 (`Plugin Name`) | 版本 | 核心功能简介 |
| :--- | :--- | :--- | :--- | :--- |
| [nonebot-plugin-xducraft-core](https://github.com/FlyingPig278/nonebot-plugin-xducraft-core) | 基础设施 (`managed=False`) | `xducraft_config` | 0.3.0 | SQLite 集中配置存储、双重门禁切面、SDK 命名空间 `xducraft_bot.shared` |
| [nonebot-plugin-xducraft-features](https://github.com/FlyingPig278/nonebot-plugin-xducraft-features) | 基础设施 (`managed=False`) | `xducraft_features` | 0.1.0 | QQ 端 `/功能` 交互式开关命令与受管功能动态枚举 |
| [nonebot-plugin-xducraft-admin](https://github.com/FlyingPig278/nonebot-plugin-xducraft-admin) | 基础设施·可选 (`managed=False`) | `xducraft_admin` | 0.1.0 | 本地回环 WebUI 管理面板（包含内置前端静态产物，业务运行非必需） |
| [nonebot-plugin-xducraft-happy-bot](https://github.com/FlyingPig278/nonebot-plugin-xducraft-happy-bot) | 受管业务插件 | `xducraft_happy_bot` | 0.2.0 | 群聊被 `@` 或被回复时自动贴附表情回应（功能名：`表情回应`） |
| [nonebot-plugin-xducraft-auto-friend](https://github.com/FlyingPig278/nonebot-plugin-xducraft-auto-friend) | 受管业务插件 | `xducraft_auto_friend` | 0.1.0 | 自动校验指定群成员资格并同意好友请求（功能名：`自动加好友`） |
| [nonebot-plugin-xducraft-keyword](https://github.com/FlyingPig278/nonebot-plugin-xducraft-keyword) | 受管业务插件 | `xducraft_keyword` | 0.1.0 | 群级关键词自动回复与入群欢迎语设定（功能名：`关键词回复`） |
| [nonebot-plugin-xducraft-pig-bot](https://github.com/FlyingPig278/nonebot-plugin-xducraft-pig-bot) | 受管业务插件 | `xducraft_pig_bot` | 0.1.0 | PigHub 猪猪图库查询与定时群推送（功能名：`猪猪图查询`、`猪猪图推送`） |
| [nonebot-plugin-xducraft-mc-update](https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-update) | 受管业务插件 | `xducraft_mc_update` | 0.1.0 | 追踪 Minecraft 正式版与快照更新并推送（功能名：`MC 更新推送`） |
| [nonebot-plugin-xducraft-invite](https://github.com/FlyingPig278/nonebot-plugin-xducraft-invite) | 受管业务插件 | `xducraft_invite` | 0.1.0 | 白名单邀请码生成、验证与私聊分发（功能名：`邀请码自助领取`） |
| [nonebot-plugin-xducraft-anti-recall](https://github.com/FlyingPig278/nonebot-plugin-xducraft-anti-recall) | 受管业务插件 | `xducraft_anti_recall` | 0.1.0 | 群撤回消息监听、图片/语音离线暂存与私聊回查（功能名：`反撤回`） |
| [nonebot-plugin-xducraft-wordcloud](https://github.com/FlyingPig278/nonebot-plugin-xducraft-wordcloud) | 受管业务插件 | `xducraft_wordcloud` | 0.1.0 | 群聊分词统计，每日零点自动渲染发送词云（功能名：`群聊词云`） |
| [nonebot-plugin-xducraft-mc-status](https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-status) | 受管业务插件 | `xducraft_mc_status` | 0.1.0 | Minecraft 服务器状态多节点探测与点阵材质卡片渲染（功能名：`MC 服务器状态`） |

> **Git 安装规范**：以上仓库尚未发布至公共 PyPI。在第三方 NoneBot 实例中安装任一独立业务插件时，必须使用 PEP 508 命名直链显式先安装 Core，再安装目标插件（以 Git Tag 或 Commit SHA 引用）：
> ```bash
> # 必须先安装 Core SDK：
> pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"
> # 随后安装具体业务插件（例如 mc-status）：
> pip install "nonebot-plugin-xducraft-mc-status @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-status.git@v0.1.0"
> ```

---

## 生产部署指南

### 1. 运行环境要求
- Python：`>= 3.9, < 4.0`
- OneBot 协议端：支持 OneBot v11 反向 WebSocket 的实现端（推荐 NapCatQQ 或 LLOneBot）
- 注：生产环境通过 Wheel 或 Git 安装时已自带打包好的 WebUI 静态文件，无需 Node.js/npm 编译环境。

### 2. 克隆宿主并安装锁定依赖
在生产机器上，通过固定插件 Git SHA 的 `requirements.txt` 安装插件与框架。该清单固定了 12 个插件的源码版本，第三方 Python 依赖仍按各包声明的兼容版本范围由 pip 动态解析：
```bash
git clone https://github.com/FlyingPig278/XDUCraft-bot.git
cd XDUCraft-bot

# 创建并激活虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 从固定插件 Git SHA 的清单安装 NoneBot2 及全部 12 个插件
pip install -r requirements.txt
```
### 3. 环境配置与凭据安全
NoneBot 默认在未显式指定 `ENVIRONMENT` 时仅读取根目录下的 `.env` 与 `.env.dev`。生产部署时建议直接将模板复制为 `.env`：
```bash
cp .env.prod.example .env
```
若保留 `.env.prod` 文件名，则必须在 `.env` 中声明 `ENVIRONMENT=prod` 方可生效。

`.env` 中的典型基础配置（真实字段示例）：
```dotenv
DRIVER=~fastapi
COMMAND_START=["/"]

# Web 管理面板基础项（密码严禁写入配置文件！）
WEB_ADMIN_ENABLED=true
WEB_ADMIN_PORT=8765

# 业务插件配置项（按需填写）
INVITE_GROUP_ID=0
INVITE_API_URL=https://www.xducraft.cn/api/invitation-codes/generate
AUTO_ACCEPT_FRIEND_GROUP_IDS=[]
```

#### 关键安全规范：管理密码与访问隔离
- **口令由系统环境变量注入**：`WEB_ADMIN_PASSWORD` 拥有机器人管理最高权限，严禁写在 `.env` 或提交至代码库。必须在启动进程时通过操作系统环境变量直接注入，且长度不得少于 12 位。
- **本地回环与 SSH 隧道**：管理面板默认仅绑定本地回环地址 `127.0.0.1:8765`，严禁直接映射至公网。远程管理请通过 SSH 端口转发访问：
  ```bash
  ssh -N -L 8765:127.0.0.1:8765 user@your-server-ip
  ```
  随后在本地浏览器打开 `http://127.0.0.1:8765/` 登录。

### 4. 启动与协议端接入
```bash
# Linux / macOS 启动示例：
export WEB_ADMIN_PASSWORD="set_your_strong_password_here_12chars"
export XDUCRAFT_DATA_DIR="/var/lib/xducraft/data"  # 外部数据根目录
nb run
```
```powershell
# Windows PowerShell 启动示例：
$env:WEB_ADMIN_PASSWORD = "set_your_strong_password_here_12chars"
$env:XDUCRAFT_DATA_DIR = "C:\bot\xducraft_data"    # 外部数据根目录
nb run
```

- **协议端配置**：在 NapCat 等 OneBot v11 协议端中添加反向 WebSocket 地址：
  ```
  ws://127.0.0.1:8080/onebot/v11/ws
  ```

---

## 门禁机制与存储结构

### 1. 双重门禁与开关联动
- **默认全关**：所有受管业务插件（`managed=True`）的全局总开关与群级开关在初次加载后默认均为关闭（OFF）。
- **全局支配性**：全局总开关处于关闭状态时，会直接拦截该插件的一切 Matcher 事件、私聊交互与后台定时任务。即使群开关已开，也处于“待全局开启”挂起状态。
- **开关控制范围与权限分工**：
  - **全局总开关**：只能在 WebUI 面板（插件详情页）或通过 Core SDK 开启，QQ 群指令无法更改全局总开关。
  - **群级功能开关**：群管理员或超管可通过群内命令 `/功能 on <功能名>` 开启本群功能（私聊可用 `/功能 <群号> on <功能名>` 远程设置）。
  - **单功能与多功能联动**：对于单功能插件（如词云、表情回应、反撤回），群内执行 `/功能 on <名称>` 会同步开启该群的插件总开关；对于多功能插件（如猪猪图），开启单项功能不会联动开启群插件总开关，须在 WebUI 或 SDK 显式打开该群的插件总开关。无论群级状态如何，必须在全局总开关开启后功能才真正生效。
- **基础设施免检**：`core`、`features` 与 `admin` 声明为 `managed=False`，不受门禁过滤。

### 2. 配置与业务数据严格分离
- **动态配置存储**：由 Core 专属 SQLite 数据库（`core/configuration.sqlite3`，POSIX 权限 `0600`）接管。支持重启保留设置与下一次生效参数。
- **业务存储隔离**：各插件的活动业务数据存放在外部数据根（`$XDUCRAFT_DATA_DIR/plugins/<key>/`）下，互不混淆：
  - 词云聊天历史：`plugins/wordcloud/chat_logs.db`；
  - 反撤回媒体与库：`plugins/anti_recall/anti_recall.db` 与 `plugins/anti_recall/media/`；
  - MC 更新订阅状态：`plugins/mc_update/subscription.json`（保留群订阅与版本游标，不迁入配置库）；
  - 关键词自定义媒体：`plugins/keyword/media/`。

---

## 生产升级与离线数据迁移 (针对 dc47f8e 首次迁移)

生产环境基准版本为 `dc47f8e763fbf0cb34701992a345a405d787b79a`。由于早期版本采用扁平目录且不存在 Core SQLite 数据库，升级时必须严格遵循离线备份与迁移流程。

> **升级操作要求**：
> 1. **必须完全停机**：迁移前必须彻底停止 NoneBot 进程及所有写操作。
> 2. **切勿伪造空配置库**：`dc47f8e` 无 Core SQLite，首次迁移绝对不要传入 `--config-db` 或新建空数据库，由首次启动时从旧 JSON 文件幂等导入。
> 3. **冷备份与工作副本分离**：导出的首份快照为只读冷备份，严禁直接用作活动运行根。必须再从冷备份导出独立工作副本使用。
> 4. **必须通过操作系统环境变量注入 `XDUCRAFT_DATA_DIR`**：在启动 Python 进程前注入，切勿仅写在 `.env` 中。

### 操作步骤示范

#### 第一步：制作源环境离线冷备份
```bash
# 确认机器人已停止后执行（首次升级无 Core SQLite，不指定 --config-db）
python scripts/migrate_runtime_data.py migrate \
  --source-layout legacy \
  --source "/opt/legacy-xducraft-bot" \
  --destination "/opt/snapshots/dc47f8e-backup-v1"
```

#### 第二步：从验证快照生成活动工作副本
```bash
# 目标路径必须不存在
python scripts/migrate_runtime_data.py migrate \
  --source-layout runtime \
  --source "/opt/snapshots/dc47f8e-backup-v1" \
  --destination "/opt/xducraft_runtime_data"
```

#### 第三步：注入环境变量并首次启动验证
```bash
# 必须先注入系统环境变量
export XDUCRAFT_DATA_DIR="/opt/xducraft_runtime_data"
export WEB_ADMIN_PASSWORD="your-strong-password-min12chars"

# 启动机器人
nb run
```

#### 首次启动核验检查单
1. **JSON 导入幂等性**：Core 启动时会自动扫描工作副本中的旧 JSON 配置文件并严格校验后写入新生成的 `core/configuration.sqlite3`。后续启动仍可能对其进行一致性校验，但不会重新回写或覆盖已在 SQLite 中生效的最新配置，运行时以 SQLite 为唯一权威存储。
2. **开关状态确认**：导入后，所有业务插件的全局总开关与群开关依门禁规范保持默认关闭（OFF）。
3. **逐项启用**：管理员通过 WebUI 后台先开启全局总开关，再按需开启群内功能开关。
4. **业务数据完好**：检查词云历史 `chat_logs.db` 及反撤回媒体等是否在新目录下正常接续工作。

---

## 贡献与同级目录开发指南 (Contributor Path)

针对希望协同改进插件或宿主集成的开发者，推荐采用同级并列仓库布局（Sibling Repo Layout）：

```
workspace/
├── XDUCraft-bot/                          # 本部署宿主仓库
├── nonebot-plugin-xducraft-core/          # 核心插件源码
├── nonebot-plugin-xducraft-admin/         # 管理面板源码
├── nonebot-plugin-xducraft-features/      # 功能控制源码
└── nonebot-plugin-xducraft-.../           # 其余各业务插件仓库
```

### 1. 搭建开发环境
```bash
cd XDUCraft-bot
python -m venv venv
source venv/bin/activate

# 以可编辑模式（-e）链接各同级插件仓库：
pip install -r requirements-dev.txt
```

### 2. 运行集成验证
在宿主环境下，使用 `requirements-test.txt` 安装测试套件，执行对已装载插件的端到端集成测试与数据迁移校验：
```bash
pip install -r requirements-test.txt
pytest tests/test_host_integration.py tests/test_data_migration.py
```

---

## 开源许可证与资源声明

- 本项目（`XDUCraft-bot` 宿主）及所涉原创插件代码均基于 [MIT License](LICENSE) 授权开源。
- 仓库内及衍生服务中使用的 Minecraft 原版贴图、材质、像素字体及思源黑体等第三方资源，其版权归各自作者或 Mojang Studios 部分所有。历史保留资源依照原状留存，本项目不声明对其拥有排他授权或将其转为 MIT 授权。
- 本仓库各插件使用 Git 标签及 Commit SHA 引用安装，未在公共 PyPI 注册，亦未作出生产级可用性认证承诺。
