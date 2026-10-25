# XDUCraft Pig Bot (`nonebot-plugin-xducraft-pig-bot`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的 PigHub 猪猪图查询与定时群推送插件。

---

## 功能说明

- **关键词图片检索**：从 PigHub 检索匹配的表情图片；匹配多张时使用合并转发发送，防止刷屏。
- **定时群推送**：通过 APScheduler 定时任务每 6 小时向开启推送的群发送随机精选猪猪图。
- **双独立功能门禁**：注册了两个独立的群功能：
  - `pig_query`（显示名：`猪猪图查询`，手动 `/pig` 查询）；
  - `pig_auto_push`（显示名：`猪猪图推送`，定时推送）。
- **多功能插件开关联动注意事项**：
  - 本插件包含多项功能，**不属于单功能插件**。
  - 在群内发送 `/功能 on 猪猪图查询` 或使用 `/pig query on` 仅会改变该功能的启用状态，**不会自动开启本群的插件总开关**。
  - 要在群内正常使用，必须同时确保：
    1. 全局总开关 `pig_bot` 处于开启状态（在 WebUI 插件页或通过 Core SDK 开启）；
    2. 本群插件总开关处于开启状态（在 WebUI 群卡片或通过 Core SDK 开启）；
    3. 目标功能（查询或推送）处于开启状态。

---

## 常用指令

| 指令 | 权限要求 | 说明 |
| :--- | :--- | :--- |
| `/pig [关键词]` | 群成员均可 | 查询猪猪图；未带关键词则随机抽取 |
| `/pig query on\|off` | 群管理 / 群主 / 超管 | 开启或关闭本群手动查询功能 |
| `/pig auto on\|off` | 群管理 / 群主 / 超管 | 开启或关闭本群定时自动推送功能 |
| `/pig status` | 群管理 / 群主 / 超管 | 查看本群猪猪图各开关状态与参数 |

> [!TIP]
> 亦可通过统一命令开关对应特性：`/功能 on 猪猪图查询` 或 `/功能 on 猪猪图推送`（别名 `pig_query`、`pig_auto_push`）。注意先确认全局与本群插件总开关已开启。

---

## 配置参数

- **群级独立参数 (`group_only`)**：
  - `max_forward_results`：本群合并转发上限（默认 5），查询命中多张图片时最多随机抽取的张数。

---

## 安装与加载

本插件处于内部演进阶段，尚未发布至公共 PyPI 仓库。

**源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/pig-bot
```

**Wheel 构建与联合安装**：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/pig-bot
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_pig_bot-0.1.0-py3-none-any.whl
```

**宿主加载（`pyproject.toml`）**：
```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_pig_bot",
]
```

---

## 数据存储边界

1. **配置数据迁移**：历史 `pig_bot_config.json` 仅作为一次性导入源，启动时由 Core 一次性导入至 Core SQLite（`pig_bot` 命名空间），旧文件不再写入；若历史配置损坏直接中断启动。
2. **纯网络服务**：表情图片实时请求外部 PigHub 接口，本地不保存图片文件，无业务数据库。
