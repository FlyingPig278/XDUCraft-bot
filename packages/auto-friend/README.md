# XDUCraft Auto Friend (`nonebot-plugin-xducraft-auto-friend`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的好友申请自动通过插件。

当收到用户的好友申请时，插件自动核实申请人是否属于受信任白名单群，并在该群已启用本功能且全局开关开启时自动同意申请。
由于 OneBot v11 好友申请事件不含来源群信息，机器人会按白名单顺序查询申请人的群成员信息；若无法确认身份，则继续检查下一个已启用的群。所有群均未匹配时，申请保持未处理，绝不自动拒绝。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 标识与作用域说明

| 维度 | 标识 | 说明 |
| :--- | :--- | :--- |
| **发行包名** | `nonebot-plugin-xducraft-auto-friend` | `pip` 安装与依赖声明标识（版本 `0.1.0`）。 |
| **插件加载名** | `xducraft_auto_friend` | NoneBot 插件加载标识，用于 `pyproject.toml` 中的 `plugins` 配置。 |
| **依赖 Core 插件** | `xducraft_config` | Core 核心配置与生命周期插件，入口处通过 `require("xducraft_config")` 预加载。 |
| **功能门禁键** | `auto_accept_friend` | 统一功能开关（`/功能`）中注册的特性键名（显示名：`自动加好友`）。 |
| **启动期部署白名单** | `auto_accept_friend_group_ids` | 整数群号列表，重启生效；修改持久化于 Core 的 `deployment_overrides` 中。 |

---

## 启停与门禁控制

受管业务插件的全局总开关与群功能**默认均为关闭（OFF）**。自动同意好友申请必须同时满足：
1. **全局总开关开启**：在 WebUI 插件页或通过 Core SDK 将 `auto_friend` 设为开启；
2. **群功能开启**：群管理员在目标白名单群发送 `/功能 on 自动加好友`（该命令由 `nonebot-plugin-xducraft-features` 插件提供）；
3. **白名单核验**：目标群已加入生效的白名单列表 `auto_accept_friend_group_ids`。

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Auto Friend 插件
pip install "nonebot-plugin-xducraft-auto-friend @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-auto-friend.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_auto_friend",
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

## 数据存储与配置规范

- **无独立业务数据库**：本插件无独立的业务数据库、历史 JSON 文件或本地媒体资产，无需执行历史数据迁移。
- **白名单配置基线**：兼容 `.env` 中的 `AUTO_ACCEPT_FRIEND_GROUP_IDS='[123456789]'` 作为启动基线，系统不会将其批量写入数据库。在管理面板或 API 修改白名单后，新参数持久化在 Core SQLite 的 `deployment_overrides` 中，重启生效；若移除覆盖项，下次重启自动恢复为 `.env` 基准值。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。
第三方依赖项遵循各自独立的授权许可。
