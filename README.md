# XDUCraft Bot

本仓库提供安装清单与启动配置，用于运行包含网页管理面板的 QQ 机器人。机器人支持 Minecraft 服务器状态查询、群聊词云、消息反撤回与关键词回复等功能。如只需在现有的 NoneBot 2.4.x 项目中查询 Minecraft 服务器状态，请直接使用独立插件 [nonebot-plugin-xducraft-mc-status](https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-status)。

## 准备工作

运行前需要准备好以下环境：
- Python 3.13
- Git
- NapCat（QQ 协议端，推荐与机器人运行在同一台机器上）

## 安装与配置

### 1. 克隆仓库与安装依赖

Windows PowerShell：
```powershell
git clone https://github.com/FlyingPig278/XDUCraft-bot.git
cd XDUCraft-bot
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux：
```bash
git clone https://github.com/FlyingPig278/XDUCraft-bot.git
cd XDUCraft-bot
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 基础配置文件

在项目根目录下创建 `.env` 文件，填入基础运行配置：

```dotenv
DRIVER=~fastapi
HOST=127.0.0.1
PORT=8080
COMMAND_START=["/"]
SUPERUSERS=["123456789"]
WEB_ADMIN_ENABLED=true
```

请把 `123456789` 替换为你自己的管理员 QQ 号。

### 3. 设置管理面板密码并启动

网页管理面板登录密码必须通过系统环境变量 `WEB_ADMIN_PASSWORD` 设置，长度至少 12 个字符。请将示例中的密码替换为你自己的密码。在新的终端窗口启动机器人时需要重新设置该变量。

Windows PowerShell：
```powershell
$env:WEB_ADMIN_PASSWORD = "替换为至少12个字符的密码"
nb run
```

Linux：
```bash
export WEB_ADMIN_PASSWORD="替换为至少12个字符的密码"
nb run
```

数据默认保存在操作系统的用户数据目录下。如果需要指定数据存储路径，可以在启动前设置环境变量 `XDUCRAFT_DATA_DIR`。

## NapCat 接入与首次使用

### 1. 配置 NapCat 反向 WebSocket

在同一台机器上运行 NapCat 并登录机器人的 QQ 账号。在 NapCat 的网络配置中添加 OneBot v11 反向 WebSocket 地址：

```
ws://127.0.0.1:8080/onebot/v11/ws
```

如果 NapCat 配置了访问密钥（Token），需要在 `.env` 中添加 `ONEBOT_ACCESS_TOKEN=你的Token` 保持两端一致。NapCat 自身的 WebUI 端口与机器人的管理面板端口（默认 8765）互相独立。机器人连接成功后会自动同步群列表，不需要在配置文件中填写机器人自身的 QQ 号。

### 2. 在网页管理面板中启用功能

管理面板默认绑定在本地回环地址 `127.0.0.1:8765`。如果部署在远程服务器上，可通过 SSH 隧道映射到本地（例如 `ssh -N -L 8765:127.0.0.1:8765 user@server`）后再通过本地浏览器打开。

首次配置步骤如下：
1. 打开浏览器访问 `http://127.0.0.1:8765`，输入设置的 `WEB_ADMIN_PASSWORD` 登录。
2. 点击进入“插件”页面。所有业务插件初次加载时默认处于关闭状态。找到“MC 服务器状态”，开启其全局总开关。全局总开关开启后，群级开关才能生效。
3. 点击进入“群聊”页面，在列表中选择目标群聊。若群列表显示“尚未获取群聊，请连接 QQ 后刷新”，请检查 NapCat 的登录状态和反向 WebSocket 连接。
4. 在群聊详情页中开启“MC 服务器状态”群开关，并在该插件的群配置中填入 Minecraft 服务器地址，点击保存。
5. 在对应的 QQ 群内发送 `/mcs`，机器人将探测服务器并发送状态信息卡片。

## 插件列表与仓库结构

日常安装和启动使用以下文件：
- `requirements.txt`：安装 NoneBot 框架，并固定各插件的 Git 提交版本。
- `pyproject.toml`：配置 NoneBot 在启动时自动加载这些插件。

插件代码均在各自仓库中修改。如果修改了插件代码并希望本仓库使用新版本，需要在 `requirements.txt` 中更新对应插件的 Git 提交号。各插件仓库如下：

| 功能 | 说明 |
| :--- | :--- |
| [核心配置](https://github.com/FlyingPig278/nonebot-plugin-xducraft-core) | 保存插件设置与全局、群级开关 |
| [群内命令控制](https://github.com/FlyingPig278/nonebot-plugin-xducraft-features) | 支持群内通过 `/功能` 命令管理本群开关 |
| [网页管理面板](https://github.com/FlyingPig278/nonebot-plugin-xducraft-admin) | 浏览器管理界面，内置前端文件，运行无需 Node.js |
| [MC 服务器状态](https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-status) | 服务器状态探测与卡片渲染，群命令 `/mcs` |
| [MC 更新推送](https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-update) | Minecraft 版本更新检测与推送 |
| [猪猪图库与推送](https://github.com/FlyingPig278/nonebot-plugin-xducraft-pig-bot) | PigHub 图库查询与定时推送 |
| [表情回应](https://github.com/FlyingPig278/nonebot-plugin-xducraft-happy-bot) | 被艾特或回复时贴附表情回应 |
| [群聊词云](https://github.com/FlyingPig278/nonebot-plugin-xducraft-wordcloud) | 群聊消息分词与每日词云图片生成 |
| [消息反撤回](https://github.com/FlyingPig278/nonebot-plugin-xducraft-anti-recall) | 群消息撤回监听与私聊回查 |
| [关键词回复与欢迎](https://github.com/FlyingPig278/nonebot-plugin-xducraft-keyword) | 群关键词自动回复与新人入群欢迎语 |
| [邀请码自助领取](https://github.com/FlyingPig278/nonebot-plugin-xducraft-invite) | 服务器白名单邀请码生成与私聊分发 |
| [自动同意好友](https://github.com/FlyingPig278/nonebot-plugin-xducraft-auto-friend) | 校验群成员身份并自动同意好友申请 |

如果选择不运行网页管理面板（设置 `WEB_ADMIN_ENABLED=false`），可以通过 Core 提供的 Python 接口配置开关，调用方式请参考 [nonebot-plugin-xducraft-core 不使用网页时启用插件](https://github.com/FlyingPig278/nonebot-plugin-xducraft-core#不使用网页时启用插件)。

## 可选流程与开发者指南

<details>
<summary>从历史版本 dc47f8e 迁移数据</summary>

本段说明适用于从早期基准版本 `dc47f8e` 升级数据的场景。新部署用户不需要执行此流程。

迁移前请先完全停止机器人进程。

早期 `dc47f8e` 版本不包含 Core SQLite 数据库。运行迁移脚本前，必须确认系统环境变量中没有设置 `XDUCRAFT_CONFIG_DB`。如果设置了该变量，脚本会强制要求指定 `--config-db` 参数。迁移时不要传入 `--config-db`，也不要创建空的数据库文件。

第一步，从旧项目目录创建停机备份并妥善保存（在 Windows PowerShell 中请去掉行尾反斜杠并合并为一行执行）：
```bash
python scripts/migrate_runtime_data.py migrate \
  --source-layout legacy \
  --source "/path/to/legacy-xducraft-bot" \
  --destination "/path/to/backup-v1"
```

第二步，从备份导出独立的工作副本供升级后的机器人运行使用（目标路径必须不存在；在 Windows PowerShell 中同样需合并为单行执行），避免运行过程中直接读写初始备份：
```bash
python scripts/migrate_runtime_data.py migrate \
  --source-layout runtime \
  --source "/path/to/backup-v1" \
  --destination "/path/to/working_data"
```

第三步，设置环境变量并启动新版本机器人：
```bash
export XDUCRAFT_DATA_DIR="/path/to/working_data"
export WEB_ADMIN_PASSWORD="替换为至少12个字符的密码"
nb run
```
在 Windows PowerShell 环境中，使用 `$env:XDUCRAFT_DATA_DIR = "..."` 和 `$env:WEB_ADMIN_PASSWORD = "..."` 设置上述环境变量。

迁移脚本不会复制旧环境的 `.env` 配置文件，需要按前文说明单独配置新环境的 `.env`。

首次启动时，Core 会扫描工作副本中的旧 JSON 配置文件并导入到 `core/configuration.sqlite3` 中。旧 JSON 文件不会被修改，后续在数据库中保存的新设置也不会被旧 JSON 覆盖。新版本的全局总开关默认关闭。请登录管理面板检查各群设置，再按需开启插件。

</details>

<details>
<summary>开发者指南：同级仓库开发与测试</summary>

修改单个插件不需要克隆全部仓库。如果只需要修改某个插件，直接克隆该插件对应的独立仓库，并参考该仓库的说明进行开发即可。

`requirements-dev.txt` 声明了全部 12 个同级插件仓库。如需使用该清单进行多仓库联合开发或集成测试，必须将全部 12 个插件仓库与本仓库克隆到同一父目录下：

```
workspace/
├── XDUCraft-bot/
├── nonebot-plugin-xducraft-core/
├── nonebot-plugin-xducraft-admin/
├── nonebot-plugin-xducraft-features/
└── nonebot-plugin-xducraft-.../
```

在虚拟环境中以可编辑模式安装所有同级插件：
```bash
pip install -r requirements-dev.txt
```

安装测试依赖并执行集成测试与迁移测试：
```bash
pip install -r requirements-test.txt
pytest
```
测试文件位于 `tests/test_data_migration.py` 与 `tests/test_host_integration.py`。

管理面板插件仓库中已包含预构建的前端静态产物。修改 Python 代码或运行测试无需安装 Node.js。只有在修改管理面板前端界面代码时，才需要进入 nonebot-plugin-xducraft-admin 仓库的 webui/ 目录下执行 `npm ci` 与 `npm run build` 重新构建静态文件。

</details>

## 开源许可证与资源声明

本仓库代码基于 [MIT License](LICENSE) 开源。

各插件使用的第三方资源归原作者所有，具体授权条款与署名见对应插件仓库的说明文件：
- MC 状态相关素材：[MC 状态插件 NOTICE](https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-status/blob/main/NOTICE)
- 词云字体文件：[词云插件 NOTICE](https://github.com/FlyingPig278/nonebot-plugin-xducraft-wordcloud/blob/main/NOTICE)
