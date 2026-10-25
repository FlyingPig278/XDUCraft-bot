# XDUCraft Features (`nonebot-plugin-xducraft-features`) 0.1.0

XDUCraft NoneBot 机器人 QQ 端统一功能开关管理插件。

通过统一的 `/功能` 交互命令，群管理员与超级用户可以在群内或通过私聊集中查阅与开关各个业务插件声明的特性。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能说明与开关联动

- **集中开关查阅**：提供统一的 `/功能` 命令，在群内直接查看所有已注册业务特性的启停状态，无需逐个插件排查。
- **动态特性发现**：对接 Core 的 `feature_gate` 注册表，业务插件声明的新功能会自动列出并支持开关。
- **单功能插件开关联动**：对于仅声明单一功能的业务插件（如表情回应、群聊词云、反撤回等），执行 `/功能 on/off` 时系统会自动同步维护该群对应的插件总开关。
- **多功能插件开关联动规则**：对于包含多项功能的插件（如包含“猪猪图查询”与“猪猪图推送”的猪猪图插件），开启单项功能**不会自动联动群插件总开关**，仍需在 WebUI 或通过 SDK 开启该群的插件总开关。
- **双重门禁前置提醒**：通过 `/功能 on` 开启群内功能仅代表本群配置处于开启状态。若该插件的全局总开关为关闭状态，消息和事件仍会被全局门禁拦截。全局关闭具有最高优先级。
- **非受管基础设施定位**：作为非受管系统组件（`managed=False`），不受业务全局门禁拦截，不能在群聊中被关闭。

---

## 常用指令

| 指令 | 范围与权限 | 说明 |
| :--- | :--- | :--- |
| `/功能` | 群内（群成员均可） | 查看本群所有业务功能的启停状态 |
| `/功能 on <功能名>` | 群内（群管理 / 超管） | 开启本群指定的业务功能 |
| `/功能 off <功能名>` | 群内（群管理 / 超管） | 关闭本群指定的业务功能 |
| `/功能 <群号>` | 私聊（群管理 / 超管） | 验证身份后查看指定群的功能状态 |
| `/功能 <群号> on\|off <功能名>` | 私聊（群管理 / 超管） | 验证身份后远程设置指定群的功能状态 |

`<功能名>` 支持中文名称（如 `群聊词云`、`表情回应`、`反撤回`、`猪猪图查询`）或英文键名（如 `wordcloud`、`emoji_reaction`、`anti_recall`、`pig_query`），支持前缀模糊匹配。

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Features 插件
pip install "nonebot-plugin-xducraft-features @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-features.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式加载：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_features",
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

## 数据存储边界

本插件无独立的数据库或 JSON 配置文件，所有状态直接读取并操作 Core 的 `feature_gate` 与配置存储。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

第三方依赖项遵循各自独立的授权许可。
