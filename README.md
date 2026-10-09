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
现已接入轻量声明式配置核心与 Naive UI 网页管理面板，支持群级功能细分、动态配置继承、部署期覆盖与安全审计。

</div>

---

> [!NOTE]  
> 本项目采用独立声明式配置核心（`xducraft_bot.shared.configuration`）配合 Naive UI 本地管理面板。所有业务功能与开关支持群级隔离、全局回退与部署期配置区分，QQ 命令管理与网页控制台共用存储服务。

---

## 🚀 快速开始

### 1. 运行环境要求
- **Python**：3.9+（强烈建议使用独立虚拟环境）
- **Node.js**：`^20.19.0 || >=22.12.0`（仅构建网页前端产物时需要，生产运行无需 Node 进程）
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

# 安装机器人 Python 依赖
pip install -r requirements.txt
```

### 3. 构建管理前端产物
```bash
cd webui
npm ci
npm run build
cd ..
```
> 若跳过前端构建，机器人与 API 仍可正常启动，浏览器访问前端路由时将显示 503 并提示执行构建命令。

### 4. 配置与启动机器人
管理面板默认监听回环地址 `127.0.0.1:8765`。面板管理口令拥有机器人所有者权限，**只从进程环境变量读取，严禁写入 `.env` 或版本控制**。

在 PowerShell 中启动示例：
```powershell
$env:WEB_ADMIN_ENABLED = "true"
$env:WEB_ADMIN_PORT = "8765"
$env:WEB_ADMIN_PASSWORD = [System.Net.NetworkCredential]::new("", (Read-Host "请输入管理面板口令（至少 12 字符）" -AsSecureString)).Password
nb run
```
若在 Linux / macOS 或系统服务中部署：
```bash
export WEB_ADMIN_ENABLED="true"
export WEB_ADMIN_PORT="8765"
export WEB_ADMIN_PASSWORD="your-strong-password-here"
nb run
```
- 控制台输出完成启动后，默认 OneBot 监听端口通常为 `8080`（如 `http://127.0.0.1:8080`）。
- 若口令长度不足 12 位、端口冲突或格式错误，面板会自动放弃启动并输出安全警告，**不影响 QQ 机器人正常收发消息**。

### 5. 协议端连接 (NapCat 等)
将 OneBot 协议端配置为 **WebSocket 客户端**，反向连接至 NoneBot 端口：
- **连接地址**：`ws://127.0.0.1:8080/onebot/v11/ws`
- 协议端连接成功后，NoneBot 日志将打印机器人上线事件。

### 6. 访问管理面板
面板仅绑定本地回环接口（`127.0.0.1`）。
- **本机访问**：直接在浏览器打开 `http://127.0.0.1:8765/`。
- **远程服务器访问**：在客户端主机建立 SSH 端口隧道：
  ```bash
  ssh -N -L 8765:127.0.0.1:8765 user@your-server-ip
  ```
  随后在本地浏览器访问 `http://127.0.0.1:8765/` 即可。

---

## 🖥️ 网页管理面板架构与设计规范

管理面板采用 **Vue 3 + Naive UI** 构建，贯彻**群优先（Group-first）**与**统一全局设置（Unified Settings）**的设计理念：

### 1. 群优先交互体系
- **会话与列表**：自动枚举在线连接的机器人及近期交互群聊，侧栏以群头像、群名与灰色群号清晰罗列。
- **群级工作区**：点击目标群即可展开该群专用的插件卡片与开关，直观查看当前生效值（继承自全局还是群独立覆盖）。手输未知群号作为备用收口。
- **群头像代理**：群头像由后端已认证同源接口统一代理，带超时和大小约束，读取失败平滑回退为文字缩写。

### 2. 独立统一设置页（Unified Settings）
- 全局运行期配置、部署期覆盖（Deployment Overrides）及全局插件开关独立汇聚于专门的“统一设置”页面，摒弃局促的侧边抽屉。
- 群卡片中若遇到全局生效的硬性规则（如词云保留期、反撤回媒体上限），界面会明确展示“此规则由全局统一控制”，并附带跳转至统一设置页的直达链接，且保留返回原群的导航上下文。

### 3. 动态表单声明驱动（Autoform）
- 前端**不为具体业务插件硬编码表单结构**，由通用表单渲染器（`SchemaFormRenderer`）解析后端提供的标准 JSON Schema 与 `x-ui-*` 扩展元数据：
  - `x-ui-group` / `x-ui-order`：表单字段的分组与排列顺序。
  - `x-ui-scope`：标记字段为 `global_only`、`group_only` 或群可覆盖。
  - `x-ui-inherit-value`：旧替换模型的显式继承标记。
  - `x-ui-tree`：通用递归树结构元数据，用于渲染 MC 状态的多级服务器树（支持子节点递归、去空白唯一 IP 校验、同级拖拽/调序计算 `priority`）。
  - `x-ui-widget`：专用交互组件绑定，如标签输入（`tags`）、数字/QQ 列表（`id-list`）、本地图片（`image`）等。

### 4. 可视化消息段编辑与安全媒体
- 关键词规则与入群欢迎提供可视化消息编辑器（`reply_variants` / `message_segments`），支持配置多条按顺序发送的回复消息（1–8 条），以及文字、本地图片上传、QQ 表情、@ 成员的自由混编。
- 历史不可编辑段（如第三方卡片、外部富媒体）作为只读 `opaque` 结构保留原引用位置，仅允许移动或删除，不可伪造或跨规则复制，严格隐藏后端绝对路径与远端原始链接。

### 5. 安全控制与并发防冲突
- **安全边界**：严苛限定 Host 必须为回环、校验同源 `Origin`、写操作强制携带 `X-CSRF-Token`、Cookie 标记 `HttpOnly` 与 `SameSite=Strict`；会话固定 12 小时。
- **并发乐观锁**：每个配置资源包含 64 位 HMAC-SHA256 生成的 `revision`。所有提交携带 `If-Match` 头，遭遇 QQ 指令或多页面并发变更时返回 `409 Conflict`，前端保留草稿并引导重新加载，避免数据相互踩踏。

---

## ⚙️ 声明式配置核心系统

配置核心由独立的 `xducraft_bot.shared.configuration` 与 `config_store` 实现，完全解耦于 WebUI。即便未启动网页面板，纯后台与 QQ 命令也能享有统一的配置管控。

### 1. 数据持久化与平滑迁移
- **配置持久化**：统一存储于 SQLite 数据库 `xducraft_bot/shared/data/configuration.sqlite3`，开启 WAL 模式并配合单进程线程锁与忙等待重试（`PRAGMA busy_timeout=5000`），保障单进程事务安全与读写一致性。
- **表结构划分**：
  - `config_documents` 表：存储既有领域整表/命名空间配置（如 MC 状态、关键词、词云、反撤回、猪猪图等配置文档）。首次启动时从历史 JSON 文件单次迁移导入，原 JSON 保留不作可写源。
  - `config_values` 表：存储通过 `register_config` 接入的 NativeConfiguration 原生模型（记录 `desired`、`applied`、`status`、`error` 与 `revision`）。
- **业务存储完全独立**：业务级数据（聊天日志 SQLite、反撤回媒体与记录、邀请码资格租约与领取状态、MC 版本游标）严格保存在各自的独立存储中，绝不与配置库混同。
- **数据备份**：配置数据库备份推荐使用标准 SQLite 一致性导出，或在服务停止时连带归档 `.sqlite3-wal` 与 `.sqlite3-shm` 文件。

### 2. 作用域流转与继承规则
原生模型（Native Configuration）遵循 **“代码默认值 → 全局配置 → 群级覆盖”** 的自顶向下生效逻辑：
- **缺失即继承**：群级未明确设置的键自动沿用全局值；未设置全局值的键沿用代码默认值。
- **显式值独立**：显式设置的 `null`、`false`、`0` 或空列表均代表明确的业务配置，不会触发隐式继承。
- **顶层整体覆盖**：按顶层模型字段整体覆盖，不对内部嵌套对象进行隐式深合并。
- **Patch 变更协议**：原生写入采用 `{ "set": { ... }, "unset": [ ... ] }` 协议。其中 `unset` 用于明确删除群级覆盖，恢复继承行为。

### 3. 运行期生效 (Runtime) 与 启动期覆盖 (Startup)
系统严格区分配置的生命周期与持久化介质：

| 维度 | 原生运行期配置 (Native Runtime) | 既有部署期配置 (Deployment Overrides) |
| :--- | :--- | :--- |
| **生效方式** | 即时落库，通过回调通知插件刷新 | 保存至本地文件，**需重启机器人进程后生效** |
| **存储介质** | `configuration.sqlite3` (`config_values`) | `xducraft_bot/shared/data/deployment_overrides.json` |
| **优先级** | 群覆盖 > 全局设置 > 代码默认值 | **网页覆盖 > 环境配置 (.env) > 代码默认值** |
| **典型内容** | 原生配置项（如自定义文案、功能开关、数值阈值等） | MC 品牌与画布排版、邀请码服务地址与绑定群、自动加好友群白名单 |
| **状态回显** | `active`（已生效）/ `failed`（应用失败） | `active`（当前生效）、`pending`（待重启生效）、`restart_required` |

> 注：既有业务插件（MC 状态、关键词规则、词云参数、反撤回策略、猪猪图转发等）的运行期配置作为整表/文档存储于 SQLite 的 `config_documents` 表；原生模型中声明为启动期生效的字段（`x-ui-effect-phase: startup`）保存在 `config_values` 表（重启后对齐 desired 与 applied）；而既有部署参数则由 `deployment_overrides.json` 管理。

- **回调容灾与恢复**：运行期配置更新会触发插件的 `on_change` 回调（异步任务超时 30 秒）。若插件应用失败，状态置为 `failed` 并保留上一次生效的配置，**绝不伪造成功提示**；管理员可通过 API 进行重试（`/apply`）或回滚（`/rollback`）。
- **部署覆盖容灾**：若 `deployment_overrides.json` 损坏或内容非法，插件启动时安全降级使用环境配置并记录警告；面板中**仅部署设置资源返回 503** 提示修复，普通插件的运行期配置仍可正常管理，系统绝不会自动清空该损坏文件。

### 4. 插件执行拦截门禁
- 独立配置插件 `xducraft_config` 注册 NoneBot `@run_preprocessor`。在任何 Matcher 响应前，统一核验插件在当前群的启用状态（`is_plugin_enabled`）。
- **全局总停用具有支配权**：全局停用的插件，任何群级开启偏好均无效。插件自身的后台定时任务、主动消息推送等无法被 Matcher 预处理器拦截的逻辑，在执行前须主动调用 `is_plugin_enabled()` 进行自检。

### 5. 机密凭据安全
- 敏感配置（如邀请码 API 密钥）使用 `SecretStr` / `writeOnly` / `x-ui-secret`。
- API 响应在 `meta.secret_fields` 中返回字段点路径的布尔映射（例如 `{"invite_api_secret": true}`），标明该敏感字段是否已在服务端配置；配置响应正文（`config`）中直接剔除敏感明文。
- 提交保存时，若用户未修改机密输入框（前端不提交未变更字段），服务端将保留原密钥；显式提交空字符串 `""` 则表示明确清空密钥。
- 配置审计日志（`config_audit`）仅记录操作人、命名空间、变更字段列表及结果，**严禁记录明文机密值**。

---

## 💻 插件接入指南（Pydantic 协议最小示例）

普通插件仅需基于 Pydantic 声明配置模型，并通过配置核心注册，即可自动接入统一存储与 WebUI 表单，无需修改前端代码：

```python
from typing import Optional
from nonebot.plugin import PluginMetadata
from pydantic import Field
from xducraft_bot.shared.configuration import (
    PROTOCOL_KEY, ConfigModel, register_config, get_config, is_plugin_enabled,
)

# 1. 继承 ConfigModel 定义配置模型（禁止多余字段）
class NoticeConfig(ConfigModel):
    welcome_text: str = Field(
        default="欢迎加入交流群！",
        title="欢迎文本",
        description="本群未配置时将自动继承全局欢迎词",
        json_schema_extra={
            "x-ui-group": "消息设置",
            "x-ui-order": 1,
            "x-ui-scope": "group_overridable",
        },
    )

# 2. 注册原生配置（支持 global 与 group 作用域）
DECLARATION = register_config(
    "my_notice",
    NoticeConfig,
    name="群通知",
)

# 3. 将协议声明挂载至 PluginMetadata.extra（WebUI 通过已加载插件元数据发现配置）
__plugin_meta__ = PluginMetadata(
    name="群通知",
    description="演示接入声明式配置协议",
    usage="在 WebUI 网页管理面板中按群或全局配置欢迎词",
    config=NoticeConfig,
    extra={PROTOCOL_KEY: DECLARATION},
)

# 4. 业务代码中读取当前生效配置（SDK 读取函数示例）
def get_welcome_text(group_id: int) -> Optional[str]:
    """获取本群生效欢迎词；若插件或本群未启用则返回 None。"""
    # 消息响应由配置核心预处理器自动拦截；后台主动调用前仍须自检开关
    if not is_plugin_enabled("my_notice", group_id):
        return None
    # 自动处理「群覆盖 -> 全局 -> 默认值」三级继承回退
    config: NoticeConfig = get_config("my_notice", "group", group_id)
    return config.welcome_text
```

- **配置变更回调（可选）**：`register_config(..., on_change=callback)` 支持同步或异步回调函数。其签名固定为 `callback(context: ConfigContext, old_model: Optional[T], new_model: T)`。在插件初次加载或补齐必填项默认值时，`old_model` 可能为 `None`。回调执行应保证幂等性，超时设定为 30 秒；若抛出异常，配置核心将记录该作用域进入 `failed` 状态并保留旧生效配置，支持重试与回滚。
- **自定义领域适配与运行期状态反馈**：对于拥有特殊持久化结构、独立媒体通道或部署期参数的复杂插件，可通过 `PluginConfiguration`、`ConfigResource` 与 `StartupConfig` 提供领域读写钩子，将业务校验与适配完全留在插件内部。此外，插件还可声明 `status(context: ConfigContext)` 钩子，返回当前群的通用提示通知（`notices`）及具体功能实际可用性映射（`feature_effective: {feature_key: bool}`）。在群面板中，管理 API 会将插件声明的实际资格（如运行白名单命中）与用户保存的功能开启偏好及插件全局总开关做交集计算，前端展示返回的实际生效状态；若为 `false`（例如当前运行白名单不包含该群），界面会清晰提示“当前实际未生效”，而不会破坏或静默清除用户已保存的配置；即便插件报告 `true`，也无法绕过全局或群级总停用；全局统一设置页不会在缺省群号的上下文中虚假推断各群运行可用性。

---

## 📦 各业务插件功能与配置说明

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
  - **群级配置**：服务器树（`servers`，支持父子级联、排序、地址隐藏与备注）、群默认查询源、认证模式与静默回复。
  - **全局配置**：全局默认查询源与默认 API 地址。
  - **部署期参数（重启生效）**：`MCS_BRAND`、`MCS_TITLE`、`MCS_CREDIT`、`MCS_TEXTURE`、`MCS_WIDTH`、`MCS_SCALE`、`MCS_MIN_HEIGHT` 等。

### 2. 🧩 关键词与入群回复（xducraft_keyword）
- **功能特性**：
  - 支持基于关键词（包含、完全匹配、前缀、正则）的自动回复及新成员入群欢迎。
  - 命中规则后，插件按顺序逐条发送所配置的全部回复消息（1–8 条），支持文字、图片、QQ 表情、@ 成员自由组合。
- **常用命令**：
  - 私聊发送 `/关键词 <群号>` 进行菜单化管理，或使用 `/关键词 <群号> add|del|show|mode|cooldown` 命令。
  - `/关键词 <群号> join set|show|clear`：配置群欢迎消息（首条欢迎自动 @ 新成员）。
  - `/关键词 global ...`：SUPERUSER 私聊维护全局通用规则。
- **配置与作用域**：
  - **群级配置**：本群专用规则列表、入群欢迎消息、默认冷却时间。
  - **全局配置**：全局共享规则列表、全局默认冷却时间。
  - 本地上传图片存于 `xducraft_keyword/data/media/`，受格式校验与 10 MiB 大小限制保护。

### 3. ☁️ 词云统计（xducraft_wordcloud）
- **功能特性**：
  - 仅对启用的群持续记录纯文本聊天内容，每日 `00:00` 自动生成并发放前一日词云图。
  - 基于停用词库过滤高频无意义词汇。
- **常用命令**：
  - `/wc on` / `/wc off` / `/wc status`：开关及查看本群状态。
  - `/wc gen [today|yesterday|YYYY-MM-DD|all]`：手动触发生成词云。
- **配置与作用域**：
  - **全局统一策略（群不可覆盖）**：日志保留天数（`retention_days`，默认 1095 天）、全局封禁 QQ 名单（`ban_user_ids`，群封禁与全局取并集，群设置无法解除全局封禁）。
  - **群级可覆盖参数**：本群最短词长（`min_word_length`）、最多词数（`max_words`）、额外停用词（`additional_stopwords`）、页脚副标题及署名开关。

### 4. 🕵️ 反撤回监控（xducraft_anti_recall）
- **功能特性**：
  - 仅记录明确开启的群聊；支持文字、图片、表情及合并转发消息。
  - 群内触发撤回时保持完全静默，仅限私聊管理员查询。
- **常用命令**：
  - `/反撤回 on|off|status|clear`：群内管理开关。
  - 私聊机器人发送 `/撤回` 或 `/撤回 <群号> [条数]`：查看已撤回内容。
- **配置与作用域**：
  - **全局策略（隐私与安全）**：缓存保留小时（默认 48h）、撤回记录保留天数（默认 7d）、媒体保存开关与单文件大小上限（默认 20MB）、全局豁免记录 QQ 列表。
  - **群级可覆盖参数**：单次私聊查询返回的条数上限（`max_query_results`）。

### 5. 🐷 猪猪图（xducraft_pig_bot）
- **功能特性**：
  - 手动关键词搜索猪猪表情图（多张匹配时合并转发）；每 6 小时自动定时推送。
- **常用命令**：
  - `/pig auto on|off`：开关自动推送。
  - `/pig query on|off`：开关手动查询。
  - `/pig [关键词]`：查询猪猪图。
- **配置与作用域**：
  - **群级配置**：合并转发随机抽取上限（`max_forward_results`，群级未设时继承全局值）。
  - **全局配置**：全局默认合并转发抽取上限。

### 6. 😊 表情回应（xducraft_happy_bot）
- **功能特性**：
  - 针对特定触发场景发送表情回应。
- **常用命令**：
  - `/ans set <表情ID>`：设置本群回应表情。
  - `/ans on|off|status`：开关与状态查询。
- **配置与作用域**：
  - **每群独立配置**：表情 ID 仅在每群独立设置；恢复默认即清空本群覆盖，回退到持久化存储中的现有根默认值。
  - **无全局修改接口**：管理面板不提供全局表情修改入口，避免单群操作意外污染全局体验。

### 7. 🤝 自动好友申请（xducraft_auto_friend）
- **功能特性**：
  - 针对加好友申请，自动核实申请人是否属于受信任群成员，确认后自动同意好友。
- **配置与作用域**：
  - **双重前置条件**：该群必须由群管理员在 QQ 执行 `/功能 on 自动加好友`，且该群号必须收录在部署白名单中。
  - **部署期参数（重启生效）**：`auto_accept_friend_group_ids`（群号正整数列表），修改后须重启机器人进程生效。

### 8. 🎫 邀请码自助领取（xducraft_invite）
- **功能特性**：
  - 仅服务于单个绑定的核心交流群，成员私聊自助验证领取 Minecraft 白名单邀请码。
- **前置与安全约束**：
  - 必须由管理员在 QQ 群内通过 `/invite init` 命令初始化资格快照。未初始化前，网页端禁止开启自助开关。
  - **禁止跨群迁移**：绑定群一旦初始化，WebUI 部署配置禁止修改 `invite_group_id`，杜绝旧群资格套用到新群。
  - **部署期参数（重启生效）**：`invite_group_id`、`invite_api_url`、`invite_api_secret`。

### 9. 📢 MC 版本更新订阅（xducraft_mc_update）
- **功能特性**：
  - 追踪 Minecraft 官方版本更新，并在群内推送更新公告。
- **配置与作用域**：
  - 开关基于订阅列表管理；内部版本游标属于系统领域状态，不开放网页配置编辑。

### 10. 🎛️ 统一功能开关（xducraft_features）
- **功能特性**：
  - 系统内置常驻管理入口，供群管理员在 QQ 端快速排查与切换各插件开关。
- **常用命令**：
  - `/功能`：列出本群所有功能及当前启停状态。
  - `/功能 on <功能名>` / `/功能 off <功能名>`：快捷开关指定功能。
  - `/功能 reset <功能名>`：重置群覆盖，恢复默认状态。
  - 私聊 `/功能 <群号>`：远程核验身份后管理指定群。

> [!NOTE]  
> **关于课表等规划插件**：课表等第三方业务数据源尚在调研筹备阶段，目前未内置假数据或占位接口。待外部数据源稳定后将以标准声明式协议平滑接入。

---

## ❓ 常见问题排查 (FAQ)

- **Q: 启动提示 `nb: command not found`？**  
  **A**: 说明没有在已激活的 Python 虚拟环境中运行。请先激活虚拟环境（提示符出现 `(venv)`），再次运行 `pip install -r requirements.txt`。

- **Q: 浏览器访问管理面板出现 503 提示？**  
  **A**: 说明尚未编译前端静态资源。请进入 `webui/` 目录执行 `npm ci && npm run build` 生成构建产物，刷新浏览器即可。

- **Q: 修改了“部署期设置”为什么没有立即生效？**  
  **A**: 部署期参数（如 MC 绘图外观尺寸、邀请码服务地址、自动加好友白名单）涉及插件初始化时的单例与第三方客户端构建。此类参数保存后会显示待重启状态，必须**重启 NoneBot 进程**方可应用。

- **Q: 保存配置时提示 409 版本冲突？**  
  **A**: 说明在您打开页面期间，该项配置已被 QQ 命令或其他管理员页面修改。为防止覆盖他人更改，系统已自动保留您当前的表单草稿，请确认无误后刷新页面重新载入最新配置再行保存。

- **Q: 运行期间 SQLite 出现锁定或权限异常？**  
  **A**: 请确保启动 NoneBot 进程的用户对 `xducraft_bot/shared/data/` 目录拥有读写权限；备份数据库时请连带备份 `.sqlite3-wal` 与 `.sqlite3-shm` 文件，或使用标准 SQLite 导出机制。

