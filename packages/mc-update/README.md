# XDUCraft MC Update (`nonebot-plugin-xducraft-mc-update`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的 Minecraft 官方版本更新监控与群推送插件。

通过 APScheduler 定时轮询 Mojang 官方版本清单（`version_manifest.json`），自动检测正式版（`release`）与快照版（`snapshot`）的最新发布，并向所有已订阅的群推送通知。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能特性

- **官方版本追踪**：定期检查 Mojang 官方版本清单，精准区分正式版与快照版。
- **差异化公告推送**：一旦检测到新版本，自动提取发布时间并向所有已订阅的群推送更新通知。
- **双重门禁与后台推送约束**：后台推送任务受双重门禁严格管控。全局总开关（`mc_update`）与群订阅开关默认均为关闭（`OFF`）。正常生效必须满足：
  1. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `mc_update`；
  2. 超管在群内开启订阅（发送 `/MC更新 订阅`，或发送 `/功能 on MC 更新推送`，系统会自动同步本群插件总开关）。

---

## 指令列表与权限控制

| 指令 | 别名 | 权限要求 | 说明 |
| :--- | :--- | :--- | :--- |
| `/MC更新 订阅` | `/mcup on` | 超级用户 (SUPERUSER) | 为当前群开启 Minecraft 版本更新推送 |
| `/MC更新 取消订阅` | `/mcup off` | 超级用户 (SUPERUSER) | 取消当前群的更新推送订阅 |

> [!TIP]
> 亦可使用统一管理命令：`/功能 on MC 更新推送` 或 `/功能 off MC 更新推送`（特性键名 `mc_update`）。

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 MC Update 插件
pip install "nonebot-plugin-xducraft-mc-update @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-mc-update.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_mc_update",
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

- **业务持久化状态边界**：
  - 插件业务数据持久化于 `<DATA_DIR>/plugins/mc_update/subscription.json`。
  - `subscription.json` 混合存储了群订阅列表与版本检查游标（`versions`），属于活跃业务领域状态，**未迁移至 Core 配置数据库**。
  - 本插件不对 Core 注册配置文档导入，版本游标由业务代码自行读写，不开放网页配置编辑。
- **数据目录环境变量**：若需要自定义外部数据目录，必须在启动前通过操作系统环境变量配置 `XDUCRAFT_DATA_DIR`（绝对路径），切勿仅写在 live `.env` 中。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

Mojang 与 Minecraft 商标与版本数据版权归 Mojang AB / Microsoft 所有。
