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

基于 NoneBot 2（OneBot v11 适配器）的 XDUCraft 社区群管理与 Minecraft 服务器状态查询机器人。  
现已接入轻量声明式配置核心与 Naive UI 网页管理面板，支持群级独立快照配置、全局与群级双重门禁及安全审计。

</div>

---

> [!NOTE]
> 已可独立安装：配置核心（`packages/core`）、表情回应（`packages/happy-bot`）、自动好友申请（`packages/auto-friend`）。
> 其余插件和 Naive UI 管理面板仍在主仓库。业务插件的全局与群开关默认关闭，升级时自动导入旧配置。
## 🚀 快速开始

### 1. 运行环境要求
- **Python**：3.9+（建议使用独立虚拟环境，依赖 Pydantic 2）
- **Node.js**：`^20.19.0 || >=22.12.0`（仅构建网页前端产物需要，生产运行无需 Node 进程）
- **OneBot 协议端**：支持 OneBot v11 的框架（推荐 [NapCat](https://github.com/NapNeko/NapCatQQ)）

### 2. 获取代码与依赖安装
```bash
# 克隆仓库
git clone https://github.com/FlyingPig278/XDUCraft-bot.git
cd XDUCraft-bot

# 创建并激活 Python 虚拟环境
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 安装机器人 Python 依赖（通过可编辑模式引入 packages/core[onebot]、packages/happy-bot 与 packages/auto-friend）
pip install -r requirements.txt
```
> 若此前拉取过旧版本源码，请重新执行 `pip install -r requirements.txt`，以确保在虚拟环境中通过可编辑模式安装独立的 `packages/core` 核心包与独立业务包 `packages/happy-bot`、`packages/auto-friend`。主仓库仍保留其余业务插件（尚未全部独立分发）与前端管理面板。

### 3. 构建管理前端产物
```bash
cd webui
npm ci
npm run build
cd ..
```
> 若未构建前端产物，机器人与后端 API 仍可正常启动，浏览器访问前端路由将返回 503 提示。

### 4. 配置与启动机器人
管理面板默认监听本地回环地址 `127.0.0.1:8765`。面板管理口令拥有机器人所有者权限，**仅从环境变量读取，严禁写入配置文件或版本控制**。

在 PowerShell 中启动示例：
```powershell
$env:WEB_ADMIN_ENABLED = "true"
$env:WEB_ADMIN_PORT = "8765"
$env:WEB_ADMIN_PASSWORD = [System.Net.NetworkCredential]::new("", (Read-Host "请输入管理面板口令（至少 12 字符）" -AsSecureString)).Password
nb run
```
在 Linux / macOS 中启动示例：
```bash
export WEB_ADMIN_ENABLED="true"
export WEB_ADMIN_PORT="8765"
export WEB_ADMIN_PASSWORD="your-strong-password-here"
nb run
```
- 控制台输出启动完成后，默认 OneBot 反向 WebSocket 监听端口通常为 `8080`（如 `ws://127.0.0.1:8080/onebot/v11/ws`）。
- 若口令长度不足 12 位或端口冲突，面板将放弃启动并记录警告，**不影响 QQ 机器人正常启动与收发消息**。

### 5. 协议端连接 (NapCat 等)
将 OneBot 协议端配置为 **WebSocket 客户端**，反向连接至 NoneBot 端口：
- **连接地址**：`ws://127.0.0.1:8080/onebot/v11/ws`
- 连接成功后，NoneBot 控制台将打印机器人上线事件。

### 6. 访问管理面板
面板仅绑定本地回环接口（`127.0.0.1`）：
- **本机访问**：直接在浏览器打开 `http://127.0.0.1:8765/`。
- **远程服务器访问**：在本地客户端建立 SSH 隧道：
  ```bash
  ssh -N -L 8765:127.0.0.1:8765 user@your-server-ip
  ```
  在本地浏览器打开 `http://127.0.0.1:8765/` 即可。

---

## 🖥️ 网页管理面板架构与设计规范

管理面板采用 **Vue 3 + Naive UI** 构建，以**群优先（Group-first）**为核心交互模型：

### 1. 顶层导航与群优先三级交互体系
- **顶层导航**：顶部清晰分为 **群聊 (`/groups`)**、**插件 (`/plugins`)** 与 **系统 (`/system`)** 三大模块，默认落地进入 `群聊`。
- **三级交互结构**：
  1. **群聊列表**：实时枚举已连接 OneBot 适配器的在线群聊；同时收录本地配置库与历史记录中的已知群（支持搜索筛选并与浏览器历史同步，移动端抽屉在跳转后自动关闭）。若协议端未连接或群列表暂不可用，历史离线分区以紧凑目录展示而不再逐行重复“离线”状态，保留最近缓存的群名；群头像统一由腾讯公开地址（p.qlogo.cn）按群号安全拉取并展示。
  2. **群业务插件卡片**：进入指定群后平铺展示该群业务插件卡片，清晰呈现插件图标、名称、本群独立保存开关以及“配置”入口（全局列表按声明呈现“设置”入口，统一 Ionicons outline 风格图标）；不自动选中首个插件，避免多表单混乱。
  3. **插件群级配置页**：点击卡片“配置”后进入单插件的独立群配置界面，专注维护本群专属参数。
- **插件卡片筛选与空状态**：
  - 提供 **全部插件** 与 **本群已启用** 两档筛选，默认筛选“全部插件”，按群独立记忆过滤选择。
  - “本群已启用”以**本群已保存开关（`control.config.enabled`）**为判定标准。即使该插件全局总停用，只要本群已保存开启，依然纳入本群已启用列表，并明确标识“待全局开启”；群详情内提供直达全局开关的链接。
  - 若筛选结果为 0，展示包含“查看全部插件”快捷按钮的说明性空状态。
  - 基础设施与系统服务（`managed: false`）不伪装为业务卡片开关。

### 2. 插件页与全局/启动弹窗隔离
- **插件页（`/plugins`）**：集中管理所有受管业务插件的全局总开关。
- **居中模态弹窗（NModal）**：全局共享参数与启动期配置收敛于居中模态弹窗中，未保存草稿徽标显示于弹窗标题，群插件详情页亦可一键唤出。启动参数展示单句重启说明；全局与启动资源加载后“高级信息”诊断面板始终存在且默认折叠（群级表单不展示该入口），表单编辑或恢复原值均不导致其隐现，同一资源保留展开状态；已保存值与草稿值严格脱敏，不冒充未上报的运行时状态，白名单等异常集中为单条警告，保持表单清爽。
- **草稿独立隔离**：全局弹窗内的编辑与保存/取消操作与群级配置草稿严格隔离，弹窗保存/关闭绝不影响群级草稿，也不会联动触发开关门禁。

### 3. 动态表单声明驱动
- 前端通用渲染器（`SchemaFormRenderer`）由后端标准 JSON Schema 及扩展元数据驱动：
  - `x-ui-group` / `x-ui-order`：表单字段的分组与排列顺序。
  - `x-ui-scope`：标记字段作用域（`global_only` 为全局独占共享字段，普通字段群级完全独立）。
  - `x-ui-effect-phase`：标记为 `startup` 的字段属于全局启动期参数，需重启生效。
  - `x-ui-tree`：MC 服务器多级递归树结构渲染。
  - `x-ui-widget`：标签（`tags`）、数字/QQ 列表（`id-list`）、本地图片上传等专用组件。
- **紧凑约束与信息降噪**：布尔开关与标签同行展示，说明文案从属下方并享有独立字段间距；数值区间（如 `480–1600`）在字段标题旁紧凑展示；深浅主题警示文字自动适配；业务表单移除了底层无用的内部继承标记、底层 diff 差异树与冗余标签，保持交互直观整洁。

### 4. 系统页与账号连接
- **系统页面 (`/system`)**：展示已连接 Bot 账号与基础服务状态。Bot 名称优先通过 OneBot `get_login_info` 异步获取真实 QQ 昵称；获取失败时平滑降级保留 QQ 号并提示“昵称暂不可用”。菜单导航、返回与刷新等操作统一采用 Ionicons outline 图标。

### 5. 安全防护与并发防冲突
- **安全边界**：强制限定回环地址、同源 `Origin` 校验、写操作强校验 `X-CSRF-Token`、Cookie 标记 `HttpOnly` 与 `SameSite=Strict`，会话固定有效 12 小时。
- **并发乐观锁**：配置资源携带基于 256 位 HMAC-SHA256（64 字符十六进制摘要）的 `revision`。所有更新请求携带 `If-Match` 头；若遇并发修改返回 `409 Conflict`，前端保留草稿并引导用户刷新获取最新配置。
---

## ⚙️ 声明式配置核心系统

配置核心已独立为 `nonebot-plugin-xducraft-core` 0.3.0（位于 `packages/core`，NoneBot 加载入口为 `xducraft_config`，提供 `xducraft_bot.shared.*` 命名空间），完全解耦于 WebUI 与特定适配器。

### 1. 数据持久化与平滑迁移
- **存储介质**：活跃配置统一持久化于 SQLite 数据库（默认旧布局为 `xducraft_bot/shared/data/configuration.sqlite3`，配置 `XDUCRAFT_DATA_DIR` 时为 `<ROOT>/core/configuration.sqlite3`，亦受 `XDUCRAFT_CONFIG_DB` 覆盖），启用 WAL 模式配合单进程事务锁与忙等待重试（`PRAGMA busy_timeout=5000`）。在 POSIX 系统上，Core 自动将 SQLite 数据库文件及其 WAL、SHM 侧车文件权限严格限制为 `0600`（仅属主用户读写）。
- **表结构与活跃文档存储**：
  - `config_documents` 表：存储各命名空间的完整业务配置文档。当前已接入的文档命名空间包括：功能门禁 `feature_gate`、部署期启动覆盖 `deployment_overrides`，以及各业务插件配置文档 `anti_recall`、`happy_bot`、`keyword`、`mc_status`、`pig_bot`、`wordcloud`。
  - **单次导入与写入边界**：历史插件 JSON 与历史 `deployment_overrides.json` 仅作为一次性导入源（one-time import inputs）。导入成功并确立 SQLite 活跃文档后，旧文件绝不再作为写入者（never a second writer），也不会被删除或重写。
  - `config_values` 表：存储通过 `register_config` 接入的原生模型（记录 `desired`、`applied`、`status`、`error` 与 `revision`）。
- **启动期声明式迁移与中断策略**：
  - NoneBot 启动且所有插件模块加载完成后（`on_startup`），Core 统一驱动各命名空间的历史数据导入迁移。
  - Core 先后执行 `feature_gate` 与 `deployment_overrides` 的历史导入，随后按稳定的插件 key 字母顺序依次调用各插件在 `PluginConfiguration` 中声明的可选 `migrate_legacy` 回调。
  - `migrate_legacy` 回调具备幂等性，仅负责确立该插件自身在 SQLite 中的活跃配置文档。
  - **启动失败策略（Abort on Error）**：若历史 JSON 文件或部署覆盖损坏、语法错误或无法解析，系统将立即抛出异常并中断 NoneBot 启动；**绝对严禁**吞没错误或在历史数据损坏时静默回退至代码默认值或环境变量默认值，防止历史配置静默丢失。
- **业务存储严格独立**：聊天日志、反撤回媒体、MC 状态游标等纯业务持久化数据严格保留在独立存储中，绝不作为配置处理，亦不混入核心配置数据库。

### 2. 双重门禁与群独立快照机制
- **业务全局总关 + 群级开关双重门禁**：
  - 受管业务插件的全局总开关与群级开关均为独立布尔值，**默认均为关闭（OFF）**。
  - **全局总停用具有最高支配权**：全局停用时，拦截该插件的所有 Matcher 消息响应、私聊指令、后台定时任务以及外部主动发送（发送前执行晚期复核）；群级开关仍保持独立保存状态，开启时展示“待全局开启”。
  - 基础设施与系统管理插件默认保持开启，不受业务门禁限制。
- **群配置独立快照（无全局动态继承）**：
  - **历史配置一次性固化（One-time freeze）**：升级时，历史已知群的实际生效值一次性物化为独立的群级完整配置；历史已保存的本群功能开启偏好**不会自动开启新的全局总开关**。
  - **新群采用代码默认值**：新加入的群直接采用插件声明的代码默认值（Code Defaults），不随全局运行时配置的修改而隐式变动。
  - **共享字段全局独占**：全服共享的策略（如词云保留期、反撤回媒体上限、全局黑名单）明确声明为 `x-ui-scope: "global_only"`，群配置中不暴露且不参与群级写入。
- **写入模式规范**：
  - **群级原生配置**：写入模式为 **全量替换（`write_mode="replace"`）**，提交完整的独立群配置快照。
  - **全局原生配置**：写入模式为 **局部补丁（`write_mode="patch"`）**，使用 `{"set": {...}, "unset": [...]}` 协议更新字段。

### 3. 运行期生效 (Runtime) 与 启动期参数 (Startup)
- **原生运行期配置**：即时保存入库，并通过异步回调通知插件实时刷新。
- **启动期配置参数与部署覆盖**：
  - 声明为 `x-ui-effect-phase: startup` 的原生字段（必须为 `global_only`）保存在 `config_values`。
  - 部署期下次启动覆盖项存储于 Core SQLite 的 `deployment_overrides` 命名空间中。历史 `deployment_overrides.json` 现仅作为一次性导入源，不再作为活动存储。
  - **`.env` 基线策略**：`.env` 保持为启动引导与环境变量基线，**绝不全量复制到 SQLite 数据库中**。在管理面板或 API 中移除某个显式覆盖项（unset）时，将在下一次进程重启时自动恢复为 `.env` 或进程环境变量所定义的基准值。
  - 启动期参数修改后即时更新期望值（`desired`），标记为 `restart_required`，**必须重启 NoneBot 机器人进程后生效**（重启后对齐 `desired` 与 `applied`）。
- **部署覆盖错误处理策略**：启动阶段读取或导入部署覆盖时，若底层数据损坏或校验失败，将直接抛出 `DeploymentConfigError` 中断启动，绝不会在历史覆盖不可读时静默回退至环境变量基准值。
### 4. 原生回调容灾与显式恢复
- 原生模型配置变更触发 `on_change(context, old_model, new_model)` 回调（支持同步/异步，超时 30 秒，插件应保证操作幂等）。
- 若回调执行失败或超时：
  - 核心记录状态为 `failed` 并保存异常信息；
  - 数据库保留本次期望值 `desired`，同时保留上一次已生效的 `applied`，**系统绝不伪造成功提示**；
  - 若失败由原生共享字段（`global_only`）变更引发，`meta.apply_scope` 将指向 `global`；群草稿仍可正常保存，但故障应在全局范围进行恢复重试或回滚；
  - 管理员可通过 API 发送 POST `/apply`（以期望值重新尝试）或 POST `/rollback`（以最后生效值回退）进行显式恢复。

### 5. 机密凭据管理
- 敏感配置（如邀请码 API 密钥）声明为 `SecretStr`、`writeOnly` 或 `x-ui-secret`。
- API 响应中脱敏，在 `meta.secret_fields` 中返回布尔标记指示服务端是否已配置，正文中不返回明文字符串。
- 保存表单时未修改的凭据字段不回传，提交空字符串 `""` 表示明确清空。审计日志中严禁记录敏感明文。

---
## 🗄️ 运行时数据布局与离线迁移（阶段 1）

### 1. 运行数据目录决策与环境变量 (`XDUCRAFT_DATA_DIR`)
- **显式运行目录环境变量 (`XDUCRAFT_DATA_DIR`)**：
  - 属于启动前进程级环境变量。若启用外部数据根，**必须在启动前设置为非空绝对路径**，且**严禁与机器人已安装代码包目录发生包含或重叠**（系统启动前执行绝对路径解析与代码重叠安全校验，重叠将直接阻断）。
  - **启动前生效约束**：路径解析直接读取 `os.environ`。**仅在 `.env` 中写入无法确保在插件模块导入前生效**，必须在启动进程前于操作系统或系统服务中显式设置（如 Linux `export` 或 Windows PowerShell `$env:`）。显式指定优先于自动模式。
- **未显式设置时的自动路径决策（数据模式合约）**：
  - **自动旧宿主识别（无歧义才保留）**：
    - 若未设置 `XDUCRAFT_DATA_DIR`，且检测到唯一存在的旧版 `xducraft_bot/shared/data` 目录；
    - 或检测到旧平铺源码宿主标记（非 SDK 自身命名空间根目录下包含 `plugins` 目录且父目录存在 `pyproject.toml`，即使是全新的源码检出且 `shared/data` 从未创建，亦精准保留预期的旧版源码内目录）；
    - 若检测到多个相互冲突的旧宿主候选路径，系统抛出 `DataPathError` 并拒绝猜测，要求管理员显式配置 `XDUCRAFT_DATA_DIR`。
  - **全新独立安装（无旧宿主标记）**：
    - 在通过 pip / wheel 独立安装 Core 且无上述源码宿主标记的纯净环境中，自动回退至操作系统标准用户数据目录（依赖 `platformdirs.user_data_path('xducraft', appauthor=False)`），绝不向 site-packages 等安装代码包目录写入运行时数据。
    - 默认 OS 根目录同样严格解析并校验代码包重叠。
    - **注意**：切勿将“未设置数据根”一律等同于 OS 用户目录/AppData，亦不可将 fresh 源码检出与全新独立安装 Core 混为一谈。
- **配置数据库优先级与数据隔离**：
  - 优先级为：显式构造参数 `database(path)` > 环境变量 `XDUCRAFT_CONFIG_DB` > 选定模式（shared legacy / core external）下的默认库文件。
  - 外置配置库仅接管配置数据库本身，**不会自动搬迁、重定向或覆盖其他业务持久化数据**（聊天记录、反撤回媒体等）。
- **外部数据根布局结构**（当指向外部根时）：
  - `<ROOT>/core/`：核心配置与共享数据（`configuration.sqlite3` 等，历史 `deployment_overrides.json` 仅作为一次性导入源）。
  - `<ROOT>/plugins/<plugin_key>/`：各业务插件持久化数据（如 `anti_recall`、`wordcloud`、`keyword` 等；内部原有子目录保持不变）。
  - `<ROOT>/cache/mc_status/`：运行期状态缓存。
  - *注：字体、静态素材（`resources/`）及 WebUI 前端产物不在此轮外部移动范围。*
- **离线迁移工具约束**：
  - `scripts/migrate_runtime_data.py` 快照与迁移工具保持独立，**系统绝不进行静默或自动迁移**。切换数据根须由管理员在停机状态下显式执行迁移。
### 2. 离线快照迁移与恢复工具 (`scripts/migrate_runtime_data.py`)
- **离线操作约束**：运行迁移或恢复前**必须彻底停止 NoneBot 机器人及所有写进程**。工具不会自动终止运行中服务，亦无法判定是否有后台写入；跨 SQLite 数据库、JSON 配置及多媒体文件的一致性严格依赖停机离线。
- **SQLite 事务备份保障**：工具在离线状态下将主库及 WAL 文件私有复制至临时区，再调用 `sqlite3.backup()` 执行事务备份并校验完整性，自动合并已提交事务；**不要把仅复制主库文件或复制 `.shm` 共享内存文件视为一致性备份方案**。
- **元数据清单与凭据安全**：快照根目录包含清单文件 `.xducraft-runtime-data.json`，仅收录相对路径、文件大小、SHA-256 摘要与版本元数据，不包含配置值与敏感明文；但快照本身可能包含历史文件中的明文凭据，需置于受控目录妥善保管。
- **目标路径要求**：执行命令前，**目标目录的父目录必须已存在，目标目录本身必须不存在**；工具拒绝软链接与重解析点。
- **CLI 命令与操作规范（在项目仓库根目录下执行，PowerShell 示例）**：
  - **从旧源码布局制作新快照**：
    ```powershell
    python scripts/migrate_runtime_data.py migrate --source "C:\bot\XDUCraft-bot" --destination "C:\bot\snapshots\v1"
    ```
    *说明：两种 `--source-layout`（`legacy` 与 `runtime`）均支持 `--config-db`。迁移工具检查的是当前终端自身继承的 `os.environ`，无法主动探测已停止实例的环境。无论哪种模式，若当前终端继承了 `XDUCRAFT_CONFIG_DB`，工具均强制要求显式传入 `--config-db "..."`；即使未继承，操作者也必须核实源实例实际使用的配置库（如 `--config-db "C:\db\configuration.sqlite3"`），绝不能靠默认文件存在来猜测。显式传入的数据库统一归档为快照中的 `core/configuration.sqlite3` 并替换既有核心库与侧车文件（恢复时写入旧布局默认位置，不修改外部环境）。*
  - **幂等验证与防冲突**：对相同源与目标重复执行迁移时，工具在临时区根据源重新构建候选快照，**仅当当前源重新生成的快照与既有目标完全匹配时返回 `already-complete`**；若源发生变动或目标被篡改则报错拒绝。
  - **导出活动运行副本并手动启用**：
    制作快照后请保留该独立冷备份，**切勿直接将唯一的验证快照作为活动运行根**。可从快照目录为活动环境制作独立的工作副本（若需显式指定库，应选择冷备份内的 `"C:\bot\snapshots\v1\core\configuration.sqlite3"`，切勿误指向当前活跃运行库）：
    ```powershell
    python scripts/migrate_runtime_data.py migrate --source-layout runtime --source "C:\bot\snapshots\v1" --destination "C:\bot\runtime_data"
    ```
    后续若计划切换，需经审阅后由管理员手动设置环境变量（**当前阶段尚未切换现有部署**）：
    ```powershell
    $env:XDUCRAFT_DATA_DIR = "C:\bot\runtime_data"
    ```
    *重要提示：若原环境配置了 `XDUCRAFT_CONFIG_DB` 且仍指向旧路径，该外置配置库**不会被新的 `XDUCRAFT_DATA_DIR` 覆盖**。启用新 Root 时必须审阅并同步决定该变量是指向工作副本内的 `core/configuration.sqlite3` 还是继续使用独立外置库，切不可误以为仅设置数据根就已完成全部切换。*
  - **为已产生新写入的运行目录重新快照**：
    ```powershell
    python scripts/migrate_runtime_data.py migrate --source-layout runtime --source "C:\bot\runtime_data" --destination "C:\bot\snapshots\v2"
    ```
    *若活动运行环境使用了外置配置库，重新快照时同样需传入实际活跃的外置库路径（`--config-db "..."`），以确保包含最新配置写入。*
  - **恢复至全新旧布局根**：
    ```powershell
    python scripts/migrate_runtime_data.py restore --source "C:\bot\snapshots\v1" --destination "C:\bot\restored_legacy"
    ```
    *`restore` 仅将数据安全恢复至全新未占用的旧布局根目录，不会覆盖既有旧仓库、不恢复代码/依赖/`.env`，亦不会代为修改外置配置库的环境变量设置。*
- **回退方案**：生产切换后的回退**绝不能仅靠 `git revert` 代码**；若切换后运行目录已产生新写入，必须先通过 `--source-layout runtime` 对最新运行目录完整快照并校验，再根据需要恢复至旧布局或安全切回。

---

## 💻 插件接入指南（Pydantic 协议最小示例）

业务插件通过继承 `ConfigModel` 并调用 `register_config` 注册原生 Pydantic 2 配置模型，即可自动接入统一存储与 WebUI 表单，无需编写前端代码。

> [!IMPORTANT]  
> - **必须先 require 再导入使用 SDK**：业务插件在模块加载时应优先调用 `require("xducraft_config")`，确保门禁预处理器与核心存储生命周期生效。
> - **独立存储不修改 NoneBot 配置缓存**：Core 原生模型配置持久化在 SQLite 中，各群与全局具备独立的生效快照，**绝不修改或污染 NoneBot 的 `get_plugin_config` 全局配置缓存**。业务中读取和更新请统一使用 Core 提供的 `get_config` 与 `update_config`，不要混用 `get_plugin_config`。

```python
from typing import Optional
from nonebot.plugin import PluginMetadata, require
from pydantic import Field

# 1. 业务插件必须在导入使用 SDK 声明前先 require 核心生命周期
require("xducraft_config")

from xducraft_bot.shared.configuration import (
    PROTOCOL_KEY, ConfigModel, register_config, get_config, update_config, is_plugin_enabled,
)

# 2. 继承 ConfigModel 定义配置模型
class NoticeConfig(ConfigModel):
    # 群级独立字段：示范群专属参数，不在全局表单出现；新群默认采用代码声明值
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
    # 全局独占字段：共享策略或服务级开关，群级不可覆盖
    max_daily_notices: int = Field(
        default=50,
        ge=1,
        title="每日推送上限",
        description="全服统一配额限制",
        json_schema_extra={
            "x-ui-group": "配额限制",
            "x-ui-order": 2,
            "x-ui-scope": "global_only",
        },
    )

# 3. 注册原生配置（scopes 支持 ("global", "group")）
# 可选传入 on_change 回调：def callback(context, old_model, new_model)
DECLARATION = register_config(
    "my_notice",
    NoticeConfig,
    name="群通知",
    scopes=("global", "group"),
)

# 4. 将协议声明挂载至 PluginMetadata.extra（供 WebUI 动态发现与生命周期门禁识别）
__plugin_meta__ = PluginMetadata(
    name="群通知",
    description="演示接入声明式配置协议",
    usage="在 WebUI 网页管理面板中按群独立配置",
    config=NoticeConfig,
    extra={PROTOCOL_KEY: DECLARATION},
)
# 5. 业务代码中读取与异步更新配置
def get_welcome_text(group_id: int) -> Optional[str]:
    """读取本群生效配置；仅当插件全局总关与本群开关均开启时才返回业务文本。"""
    # 消息预处理器会自动拦截 Matcher，主动发送或后台任务须显式自检双重门禁
    if not is_plugin_enabled("my_notice", group_id):
        return None
    # 群级读取返回完整独立的 NoticeConfig 实例，共享字段结合全局生效值
    config: NoticeConfig = get_config("my_notice", scope="group", scope_id=group_id)
    return config.welcome_text

async def set_welcome_text(group_id: int, text: str) -> None:
    """编程式全量更新群配置快照示例（update_config 为异步函数）。"""
    await update_config("my_notice", {"welcome_text": text}, scope="group", scope_id=group_id)
```

### SDK 核心 API 签名速查
- **`register_config(plugin_id: str, model: Type[BaseModel], *, scopes=("global", "group"), on_change=None, name: Optional[str] = None, feature_keys: Tuple[str, ...] = ()) -> PluginConfiguration`**  
  注册原生模型配置并绑定到统一数据库。
- **`PluginConfiguration(key: str, name: str, resources: Mapping[str, ConfigResource] = ..., feature_keys: Tuple[str, ...] = ..., list_groups: Optional[...] = None, startup: Optional[...] = None, status: Optional[...] = None, media: Optional[...] = None, managed: bool = True, migrate_legacy: Optional[Callable[[], Any]] = None)`**
  插件配置声明数据结构。Core 0.3.0 新增可选的 `migrate_legacy` 声明式回调，在所有插件加载完成后由 Core 统一驱动执行幂等的单次导入，仅确立自身在 SQLite 中的活跃配置文档。
- **`get_config(plugin_id: str, scope: str = "global", scope_id: Optional[int] = None) -> BaseModel`**  
  读取当前生效配置（`scope="global"` 时无需 `scope_id`；`scope="group"` 时需传入整数群号）。
- **`async update_config(plugin_id: str, values: dict, scope: str = "global", scope_id: Optional[int] = None, *, actor: str = "plugin") -> ConfigSnapshot`**  
  编程式更新配置（全局接受 patch 格式，群级接受 replace 全量字典）。
- **`is_plugin_enabled(plugin_id: str, group_id: Optional[int] = None) -> bool`**  
  检查插件当前在目标群（或全局）是否处于有效运行状态（受全局总关与群开关双重约束）。
- **`set_plugin_enabled(plugin_id: str, enabled: bool, group_id: Optional[int] = None, *, actor: str = "plugin") -> dict`**  
  切换插件的控制标志（即插件级全局总关或本群开关）。注意：已有单功能插件（如反撤回、词云等）的业务功能开关同步通过 `feature_gate.set_enabled` 或 Web 管理接口完成；SDK 的 `set_plugin_enabled` 仅设置插件控制标志本身，不会自动修改底层领域业务偏好。

---

## 📦 各业务插件功能与配置说明

所有业务插件默认全局关闭，群级默认关闭。基础设施命令不受业务全局停用阻断。

### 1. ⛏️ MC 服务器状态（xducraft_mc_status）
- **功能特性**：
  - 查询群内配置的多级服务器或指定地址的状态（MOTD、在线人数、Ping、正版验证模式等）。
  - 支持渲染精美的像素风格状态图，自动识别 Velocity/BungeeCord 子服层级。
- **常用命令**：
  - `/mcs`、`/mcs all`、`/mcs <地址>`：查询本群服务器或指定服务器状态。
  - `/mcs auth`：查看或配置登录认证模式（正版/MUA/XDU/外置/离线/混合）。
  - `/mcs source`、`/mcs api`：切换查询源（本地协议/公共 API/自建后端）。
  - 查询命令后可附加 `texture=<材质>` 临时更换背景（如 `/mcs all texture=dirt`）。
- **配置与作用域**：
  - **群级配置**：服务器树（`servers`，支持父子级联、排序、地址隐藏与备注）、本群查询源（`status_api_source`）、本群 API 地址（`status_api_url`）、认证模式（`default_auth_mode`）与静默回复，各群完全独立配置。
  - **全局配置**：无全局运行期配置资源；外观排版参数收敛于启动期参数中。
  - **启动期参数（重启生效）**：`MCS_BRAND`、`MCS_TITLE`、`MCS_CREDIT`、`MCS_TEXTURE`、`MCS_WIDTH`、`MCS_SCALE`、`MCS_MIN_HEIGHT` 等。

### 2. 🧩 关键词与入群回复（xducraft_keyword）
- **功能特性**：
  - 支持基于关键词（包含、完全匹配、前缀、正则）的自动回复及新成员入群欢迎。
  - 命中规则后，插件按顺序逐条发送所配置的回复消息（1–8 条），支持文字、图片、QQ 表情、@ 成员组合。
- **常用命令**：
  - 私聊发送 `/关键词 <群号>` 进行菜单化管理，或使用 `/关键词 <群号> add|del|show|mode|cooldown` 命令。
  - `/关键词 <群号> join set|show|clear`：配置群欢迎消息（首条欢迎自动 @ 新成员）。
- **配置与作用域**：
  - **群级配置**：本群专用规则列表、入群欢迎消息、本群默认冷却时间。升级时历史全局规则已单次冻结固化至已知群中，群规则完全独立，不再动态拼接全局规则。
  - 上传媒体存于 `xducraft_keyword/data/media/`，受格式校验与 10 MiB 大小限制保护。

### 3. ☁️ 词云统计（xducraft_wordcloud）
- **功能特性**：
  - 仅对启用的群持续记录纯文本聊天内容，每日 `00:00` 自动生成并发放前一日词云图。
  - 基于停用词库过滤高频无意义词汇。
- **常用命令**：
  - `/wc on` / `/wc off` / `/wc status`：开关及查看本群状态。
  - `/wc gen [today|yesterday|YYYY-MM-DD|all]`：手动触发生成词云。
- **配置与作用域**：
  - **全局独占策略（global_only）**：日志保留天数（`retention_days`，默认 1095 天）、全局封禁 QQ 名单（`ban_user_ids`，群设置无法解除全局封禁）。
  - **群级独立参数**：本群最短词长（`min_word_length`）、最多词数（`max_words`）、额外停用词（`additional_stopwords`）、页脚副标题及署名开关。

### 4. 🕵️ 反撤回监控（xducraft_anti_recall）
- **功能特性**：
  - 仅记录明确开启的群聊；支持文字、图片、表情及合并转发消息。
  - 群内触发撤回时保持完全静默，仅限私聊管理员查询。
- **常用命令**：
  - `/反撤回 on|off|status|clear`：群内管理开关。
  - 私聊机器人发送 `/撤回` 或 `/撤回 <群号> [条数]`：查看已撤回内容。
- **配置与作用域**：
  - **全局独占策略（global_only）**：缓存保留小时（默认 48h）、撤回记录保留天数（默认 7d）、媒体保存开关与单文件大小上限（默认 20MB）、全局豁免记录 QQ 列表。
  - **群级独立参数**：单次私聊查询返回的条数上限（`max_query_results`）。

### 5. 🐷 猪猪图（xducraft_pig_bot）
- **功能特性**：
  - 关键词搜索猪猪表情图（多张匹配时合并转发）；每 6 小时自动定时推送。
- **常用命令**：
  - `/pig auto on|off`：开关自动推送。
  - `/pig query on|off`：开关手动查询。
  - `/pig [关键词]`：查询猪猪图。
- **配置与作用域**：
  - **群级配置**：合并转发随机抽取上限（`max_forward_results`，群级独立配置快照，无全局继承回退）。

### 6. 😊 表情回应（xducraft_happy_bot）
- **独立分发说明**：
  - 本插件为首个完成独立包拆分的业务插件（源码位于 `packages/happy-bot`，发行名 `nonebot-plugin-xducraft-happy-bot` 0.2.0，加载名 `xducraft_happy_bot`，依赖 `nonebot-plugin-xducraft-core[onebot]>=0.3.0,<0.4.0`），在根 `pyproject.toml` 的 `plugins` 中显式加载。
- **功能特性**：
  - 群内被 `@` 机器人或收到群成员针对机器人的回复时，调用 OneBot v11 扩展接口 `set_msg_emoji_like` 进行表情回应。
  - 属于被动响应规则（优先级 `99`，`block=False`），不阻断后续其他功能插件的消息接收；协议端若不支持贴表情 API 则记录调试日志，不打断消息链。
- **常用命令与权限**：
  - `/ans`（别名 `/answer`、`/表情回应`）：查看本群当前表情回应启用状态与当前表情 ID（群成员均可使用）。
  - `/ans set <emoji_id>`：设置本群表情回应 ID（`emoji_id` 必须为纯数字，受群管理员权限限制）。
  - `/功能 on 表情回应` / `/功能 off 表情回应`：快捷开关本群表情回应功能（亦可在网页管理面板群卡片中开关）。
- **配置与门禁规范**：
  - **双重门禁**：受管插件全局总开关（`happy_bot`）与群功能开关（`emoji_reaction`）默认均为关闭（OFF），须同时开启方可生效。
  - **每群完全独立配置**：表情 ID（`emoji_id`，默认 `123`）完全在每群独立设置与持久化。管理面板不提供全局表情修改入口，避免单群操作意外污染其他群。
  - **声明式单次迁移与中断策略**：通过 `PluginConfiguration` 声明 `migrate_legacy` 回调，NoneBot 启动时由 Core 按序驱动，将历史 `emoji_like_config.json` 一次性导入至 Core SQLite（`happy_bot` 命名空间）；历史 JSON 仅作为导入输入，旧文件不再写入亦不被删除；若历史文件损坏则直接中断启动，绝不静默使用默认配置覆盖。
### 7. 🤝 自动好友申请（xducraft_auto_friend）
- **独立分发说明**：
  - 本插件已作为第二个独立业务插件拆分解耦（源码位于 `packages/auto-friend`，发行名 `nonebot-plugin-xducraft-auto-friend` 0.1.0，加载名 `xducraft_auto_friend`，依赖 `nonebot-plugin-xducraft-core[onebot]>=0.3.0,<0.4.0`），在根 `pyproject.toml` 的 `plugins` 中显式加载。
- **功能特性**：
  - 针对加好友申请，自动核查申请人是否属于白名单群成员；验证通过后自动同意好友。
  - 由于 OneBot v11 好友请求事件自身不包含来源群号，插件会按白名单顺序实时调用 `get_group_member_info` 校验成员归属；若无法确认成员身份（如网络异常或不在群内）则保持拒绝（Fail-closed），并继续尝试下一个已配置且启用的群。
  - 无独立业务数据库、媒体文件或本地 JSON 资产，不涉及自有 JSON 迁移。
- **门禁机制与前置条件**：
  - 需同时满足多重门禁方可自动通过申请：插件全局总开关（`auto_friend`）开启、群级插件总开关开启、群级被动功能开关（`auto_accept_friend`，功能名“自动加好友”）开启，且群号必须包含在当前生效的白名单中（门禁默认均为关闭）。
- **白名单配置与启动期生效**：
  - **启动期参数（重启生效）**：`auto_accept_friend_group_ids`（群号列表，通过插件声明式 Schema 自动向管理面板提供 `id-list` 渲染）。
  - **旧 .env 兼容与动态覆盖**：既有 `.env` 中的 `AUTO_ACCEPT_FRIEND_GROUP_IDS` JSON 数组保持作为启动基线，无需全量搬迁；管理端提交的显式修改通过 Core SQLite 的 `deployment_overrides` 持久化，重启后生效；若移除覆盖项（unset），重启后自动恢复为 `.env` 基准值。
- **命令与管理入口说明**：
  - QQ 端 `/功能 on|off 自动加好友` 交互命令属于主仓库的 `xducraft_features` 插件，不包含在 `nonebot-plugin-xducraft-auto-friend` 独立 wheel 中。独立部署环境下可通过 Core SDK（如 `feature_gate` 与 `configuration`）或单独部署的 WebUI 进行启停配置。
### 8. 🎫 邀请码自助领取（xducraft_invite）
- **功能特性**：
  - 仅服务于单个绑定的核心交流群。成员在绑定群内 @机器人发送“邀请码”（或群内发送 `/邀请码`），核验群成员资格后通过私聊发放 Minecraft 白名单邀请码；私聊直接发送仅返回使用引导。
- **前置与安全约束**：
  - 必须由 SUPERUSER 私聊机器人执行 `/invite init` 初始化核心群成员资格快照。未初始化前，网页端禁止开启自助开关。
  - **启动期参数（重启生效）**：`invite_group_id`、`invite_api_url`、`invite_api_secret`。

### 9. 📢 MC 版本更新订阅（xducraft_mc_update）
- **功能特性**：
  - 追踪 Minecraft 官方版本更新，并在订阅群内推送更新公告。
- **配置与作用域**：
  - 开关基于订阅列表管理；内部版本游标属于系统领域状态，不开放网页配置编辑。

### 10. 🎛️ 统一功能开关（xducraft_features）
- **功能特性**：
  - 系统内置常驻管理入口，供管理员在 QQ 端快速排查与切换各插件开关。
  - 单功能插件与群插件总开关双向同步。
- **常用命令**：
  - `/功能`：列出本群所有功能及当前启停状态。
  - `/功能 on <功能名>` / `/功能 off <功能名>`：快捷开启或关闭指定功能。
  - 私聊 `/功能 <群号>`：远程核验身份后查看指定群状态。
  - 私聊 `/功能 <群号> on|off <功能名>`：远程切换指定群功能。

> [!NOTE]  
> **关于课表等规划插件**：课表等第三方业务数据源目前不可用，未实现占位或伪造接口。待外部数据源就绪后将以标准声明式协议平滑接入。

---

## ❓ 常见问题排查 (FAQ)

- **Q: 启动提示 `nb: command not found`？**  
  **A**: 说明没有在已激活的 Python 虚拟环境中运行。请先激活虚拟环境（提示符出现 `(venv)`），再次运行 `pip install -r requirements.txt`。

- **Q: 浏览器访问管理面板出现 503 提示？**  
  **A**: 说明尚未编译前端静态资源。请进入 `webui/` 目录执行 `npm ci && npm run build` 生成构建产物，刷新浏览器即可。

- **Q: 群卡片中插件显示“待全局开启”是什么原因？**  
  **A**: 说明该插件在本群保存的状态为“已开启”，但插件的全局总开关目前处于关闭状态。全局关闭具有支配权，此时插件在该群不会响应。进入该群的插件配置详情页，点击提示栏中的“前往全局开关”链接（或直接前往全局设置页）开启该插件的总开关即可生效。

- **Q: 为什么部分群聊显示为“群 <群号>”？**  
  **A**: 当机器人离线或对应群未在当前连接的协议端群列表中时，系统从配置数据库中恢复已知群记录；若此前未缓存过真实群名，则降级显示为“群 <群号>”，群头像与配置读写不受影响。

- **Q: 修改了“启动期设置”为什么没有立即生效？**  
  **A**: 启动期参数（如 MC 绘图外观尺寸、邀请码服务地址、自动加好友白名单）涉及插件初始化单例与网络客户端构建。保存后期望值（desired）已落库并标记 `restart_required`，必须**重启 NoneBot 进程**方可应用。

- **Q: 保存配置时提示 409 版本冲突？**  
  **A**: 说明在此期间配置已被并发修改。为防止数据覆盖，系统已自动保留您当前的表单草稿，请确认无误后刷新页面获取最新配置再行提交。

- **Q: 运行期间 SQLite 出现锁定或权限异常？**  
  **A**: 请确保运行用户对数据目录拥有读写权限；不要把仅复制主库文件或复制 `.sqlite3-shm` 视为一致性备份方案，应在停止写进程后通过 `scripts/migrate_runtime_data.py` 制作离线快照，或使用 SQLite 标准备份 API（`backup()`）安全导出。

- **Q: 全局设置中的“高级信息”面板是做什么的？**  
  **A**: “高级信息”是全局运行期和启动期配置的只读诊断折叠面板（群级表单不提供此项）。它以只读方式对比当前生效值、下次启动值/已保存值与基础默认值，且所有敏感机密字段均已脱敏处理。该面板加载后稳定存在且默认收起，用户对其展开或折叠的操作状态在同一资源编辑期间会持续保持，不会因字段变更或恢复默认而异常闪烁。
