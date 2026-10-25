# XDUCraft Invite (`nonebot-plugin-xducraft-invite`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的 Minecraft 白名单邀请码自助领取与私聊运维管理插件。

仅服务于单个绑定的核心交流群。群成员在绑定群内申请时，核查成员资格后通过**私聊**下发邀请码，防止群内泄露；管理员与超管可通过私聊进行初始化、记录查询与补发。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能特性

- **核心群资格核验**：严格绑定单一交流群。群成员申请时核验成员身份，并通过私聊下发邀请码。
- **防止重复领取**：按用户限制领取频次与记录历史租约状态。
- **管理端私聊运维**：超级用户可通过私聊执行初始化、查询发放记录与手动为特定成员补发。
- **双重门禁与前置初始化要求**：
  1. 必须先由超级用户私聊执行 `/invite init` 初始化核心群成员快照（未初始化前禁止开启自助开关）；
  2. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `invite`；
  3. 开启群自助领取功能（在绑定群内发送 `/功能 on 邀请码自助领取`，系统会自动同步本群插件总开关）。

---

## 启动期部署参数

本插件包含全局独占的启动期参数，修改后**必须重启 NoneBot 进程**方可生效：

- `invite_group_id`：绑定的核心交流群号（字符串，初始化后锁定）；
- `invite_api_url`：邀请码后端生成接口（必须为 HTTPS 地址）；
- `invite_api_secret`：后端接口鉴权密钥（密文字段，仅写入）。

兼容 `.env` 中的 `INVITE_GROUP_ID`、`INVITE_API_URL` 与 `INVITE_API_SECRET` 作为启动基线。在 WebUI 或 API 中显式保存的修改会记录至 Core SQLite 的 `deployment_overrides`，移除覆盖（unset）后下一次重启将自动恢复为 `.env` 基准值。

---

## 指令列表与交互

### 1. 前置初始化

首次使用前，**超级用户必须私聊机器人执行初始化**：
```text
/invite init
```
机器人拉取当前绑定群的成员列表并建立持久化资格快照。

### 2. 常用指令

| 指令 | 范围与权限 | 说明 |
| :--- | :--- | :--- |
| `@机器人 邀请码` / `/邀请码` | 绑定群内（成员均可） | 申请白名单邀请码（核验资格后私聊下发） |
| `/invite status` | 私聊（超管） | 查看当前部署状态、绑定群与初始化时间 |
| `/invite list [页码]` | 私聊（超管） | 分页查看已发放的邀请码记录 |
| `/invite grant <QQ号>` | 私聊（超管） | 手动为指定成员发放邀请码 |

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Invite 插件
pip install "nonebot-plugin-xducraft-invite @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-invite.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_invite",
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

## 业务数据存储边界

- **业务数据严格隔离**：群成员快照、发放记录与租约状态保存在独立业务数据文件中（位于 `<DATA_DIR>/plugins/invite/`），不混入 Core 配置数据库。
- **数据目录环境变量**：若需要自定义外部数据目录，必须在启动前通过操作系统环境变量配置 `XDUCRAFT_DATA_DIR`（绝对路径），切勿仅写在 live `.env` 中。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

第三方 API 依赖与外部系统接口遵循各自独立的授权许可。
