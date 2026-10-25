# XDUCraft Invite (`nonebot-plugin-xducraft-invite`) 0.1.0

XDUCraft Minecraft 白名单邀请码自助领取与私聊管理插件。

---

## 功能说明

- **核心群资格核验**：仅服务于单个绑定的核心交流群。群成员在绑定群内申请时，核查成员资格后通过**私聊**发放邀请码，防止群内泄露。
- **防止重复领取**：按用户限制领取频次与记录历史租约状态。
- **管理端私聊运维**：超级用户可通过私聊执行初始化、查询发放记录与手动为特定成员补发。
- **双重门禁与前置初始化要求**：
  1. 必须先由超级用户私聊执行 `/invite init` 初始化核心群成员快照（未初始化前禁止开启自助开关）；
  2. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `invite`；
  3. 开启群自助领取功能（在绑定群内发送 `/功能 on 邀请码自助领取` 或 `/功能 on invite_self_service`，系统会自动同步本群插件总开关）。

---

## 启动期部署参数

本插件包含全局独占的启动期参数，修改后**必须重启 NoneBot 进程**方可生效：

- `invite_group_id`：绑定的核心交流群号（字符串，初始化后锁定）；
- `invite_api_url`：邀请码后端生成接口（必须为 HTTPS 地址）；
- `invite_api_secret`：后端接口鉴权密钥（密文字段，仅写入）。

兼容 `.env` 中的 `INVITE_GROUP_ID`、`INVITE_API_URL` 与 `INVITE_API_SECRET` 作为启动基线。在 WebUI 或 API 中显式保存的修改会记录至 Core SQLite 的 `deployment_overrides`，移除覆盖（unset）后下一次重启将自动恢复为 `.env` 基准值。

---

## 初始化与指令说明

### 1. 核心前置：执行初始化
首次使用前，**超级用户必须私聊机器人执行初始化**：
```text
/invite init
```
机器人拉取当前绑定群的成员列表并生成持久化资格快照。

### 2. 常用指令
| 指令 | 范围与权限 | 说明 |
| :--- | :--- | :--- |
| `@机器人 邀请码` / `/邀请码` | 绑定群内（成员均可） | 申请白名单邀请码（核验资格后私聊下发） |
| `/invite status` | 私聊（超管） | 查看当前部署状态、绑定群与初始化时间 |
| `/invite list [页码]` | 私聊（超管） | 分页查看已发放的邀请码记录 |
| `/invite grant <QQ号>` | 私聊（超管） | 手动为指定成员发放邀请码 |

---

## 安装与加载

本插件处于内部演进阶段，尚未发布至公共 PyPI 仓库。

**源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/invite
```

**Wheel 构建与联合安装**：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/invite
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_invite-0.1.0-py3-none-any.whl
```

**宿主加载（`pyproject.toml`）**：
```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_invite",
]
```

---

## 数据存储边界

群成员快照、发放记录与租约状态保存在独立业务数据文件中（外部数据根下路径为 `<ROOT>/plugins/invite/`；旧源码布局为 `xducraft_bot/plugins/xducraft_invite/data/`），不混入 Core 配置数据库。
