# XDUCraft Features (`nonebot-plugin-xducraft-features`) 0.1.0

XDUCraft NoneBot 机器人 QQ 端统一功能开关管理插件。

---

## 功能说明

- **集中开关查阅**：提供统一的 `/功能` 命令，在群内直接查看所有已注册业务特性的启停状态，无需逐个插件排查。
- **动态特性发现**：对接 Core 的 `feature_gate` 注册表，业务插件声明的新功能会自动列出。
- **单功能插件开关联动**：对于仅声明单一功能的业务插件（如表情回应、群聊词云、反撤回等），执行 `/功能 on/off` 时 Core 会自动同步维护该群对应的插件总开关。
- **多功能插件开关联动规则**：对于包含多项功能的插件（如包含“猪猪图查询”与“猪猪图推送”的猪猪图插件），开启单项功能**不会自动联动群插件总开关**，仍需在 WebUI 或通过 SDK 单独开启该群的插件总开关。
- **双重门禁前置提醒**：通过 `/功能 on` 开启群内功能仅代表本群配置处于开启状态。若该插件的全局总开关为关闭状态，消息和事件仍会被全局门禁拦截，须先开启全局总开关。
- **基础设施定位**：作为非受管系统组件（`managed=False`），不受业务全局门禁拦截，不能在群聊中被关闭。

---

## 常用指令

| 指令 | 范围与权限 | 说明 |
| :--- | :--- | :--- |
| `/功能` | 群内（成员均可） | 查看本群所有业务功能的启停状态 |
| `/功能 on <功能名>` | 群内（群管理 / 超管） | 开启本群指定的业务功能 |
| `/功能 off <功能名>` | 群内（群管理 / 超管） | 关闭本群指定的业务功能 |
| `/功能 <群号>` | 私聊（群管理 / 超管） | 验证身份后查看指定群的功能状态 |
| `/功能 <群号> on\|off <功能名>` | 私聊（群管理 / 超管） | 验证身份后远程设置指定群的功能状态 |

`<功能名>` 支持中文名称（如 `群聊词云`、`表情回应`、`反撤回`、`猪猪图查询`）或英文键名（如 `wordcloud`、`emoji_reaction`、`anti_recall`、`pig_query`），支持前缀匹配。

---

## 安装与加载

本插件处于内部演进阶段，尚未发布至公共 PyPI 仓库。

**源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/features
```

**Wheel 构建与联合安装**：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/features
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_features-0.1.0-py3-none-any.whl
```

**宿主加载（`pyproject.toml`）**：
```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_features",
]
```

---

## 数据边界

本插件无独立的数据库或 JSON 配置文件，所有状态直接读取并操作 Core 的 `feature_gate` 与配置存储。
