# XDUCraft MC Update (`nonebot-plugin-xducraft-mc-update`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的 Minecraft 官方版本更新监控与群推送插件。

---

## 功能说明

- **官方版本追踪**：通过 APScheduler 定时轮询 Mojang 官方版本清单（`version_manifest.json`），自动检测正式版（`release`）与快照版（`snapshot`）的最新发布。
- **差异化公告推送**：一旦检测到新版本，自动提取发布时间并向所有已订阅的群推送通知。
- **双重门禁要求**：全局总开关（`mc_update`）与群订阅开关默认均为关闭。正常生效必须满足：
  1. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `mc_update`；
  2. 开启本群订阅（由超管在群内发送 `/MC更新 订阅`，或发送 `/功能 on MC 更新推送`，系统会自动同步本群插件总开关）。

---

## 指令列表与权限控制

| 指令 | 别名 | 权限要求 | 说明 |
| :--- | :--- | :--- | :--- |
| `/MC更新 订阅` | `/mcup on` | 超级用户 (SUPERUSER) | 为当前群开启 Minecraft 版本更新推送 |
| `/MC更新 取消订阅` | `/mcup off` | 超级用户 (SUPERUSER) | 取消当前群的更新推送订阅 |

> [!TIP]
> 亦可使用统一管理命令：`/功能 on MC 更新推送` 或 `/功能 off MC 更新推送`（别名 `mc_update`）。

---

## 安装与加载

本插件处于内部演进阶段，尚未发布至公共 PyPI 仓库。

**源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/mc-update
```

**Wheel 构建与联合安装**：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/mc-update
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_mc_update-0.1.0-py3-none-any.whl
```

**宿主加载（`pyproject.toml`）**：
```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_mc_update",
]
```

---

## 数据存储边界

> [!IMPORTANT]
> **业务持久化状态边界**：
> - 插件业务数据存储于 `subscription.json`（外部数据根下路径为 `<ROOT>/plugins/mc_update/subscription.json`；旧源码布局为 `xducraft_bot/plugins/xducraft_mc_update/data/subscription.json`）。
> - `subscription.json` 混合存储了群订阅列表与版本检查游标（`versions`），属于活跃业务领域状态，**未被迁移至 Core 配置数据库**。
> - 插件不对 Core 注册业务文档导入，版本游标由业务代码自行读写，不开放网页配置编辑。
