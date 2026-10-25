# XDUCraft Auto Friend (`nonebot-plugin-xducraft-auto-friend`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的好友申请自动通过插件。

## 用途

当收到用户的好友申请时，插件自动核实申请人是否属于受信任白名单群，并在对应群已启用本功能时自动同意申请。
由于 OneBot v11 好友申请事件不含来源群信息，机器人会按白名单顺序查询申请人的群成员信息；若无法确认身份，则继续检查下一个已启用的群。所有群均未匹配时，申请保持未处理，不会自动拒绝。

## 安装

本插件目前处于内部演进阶段，尚未发布至公共 PyPI。

**本地源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/auto-friend
```

**本地 Wheel 构建与安装**（需同时安装 Core 与插件产物）：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/auto-friend
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] dist/nonebot_plugin_xducraft_auto_friend-0.1.0-py3-none-any.whl
```

## 加载

插件内部已声明 `require("xducraft_config")`。在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_auto_friend",
]
```

## 白名单

- 启动期参数 `auto_accept_friend_group_ids`（群号列表），修改后须重启机器人进程生效。
- 兼容旧版 `.env` 配置项 `AUTO_ACCEPT_FRIEND_GROUP_IDS='[123456789]'` 作为启动基线，系统不会将其批量写入数据库。
- 在管理面板或接口修改白名单后，新参数持久化保存在 Core SQLite 的 `deployment_overrides` 中，重启后生效；若移除该覆盖项，下次重启自动恢复为 `.env` 基准值。

## 启用

插件全局总开关与群功能默认均为关闭。自动通过好友申请须同时满足：全局插件开启、目标群功能开启、目标群处于当前生效白名单中。

- **主仓库环境**：先在网页插件页打开全局总开关，再由群管理员发送 `/功能 on 自动加好友` 开启本群功能（该命令由主项目 `xducraft_features` 提供，不包含在本插件安装包中）。
- **独立部署环境**：通过 Core SDK 启用全局总开关并开启目标群功能：
  ```python
  from xducraft_bot.shared.configuration import set_plugin_enabled
  from xducraft_bot.shared.feature_gate import set_enabled

  # 在 NoneBot 初始化并加载本插件后执行
  group_id = 123456789
  # 1. 开启插件全局总开关
  set_plugin_enabled("auto_friend", True)
  # 2. 开启目标群功能（同时自动同步激活该群插件开关）
  set_enabled("auto_accept_friend", group_id, True)
  ```
  亦可配合单独安装的 WebUI 管理面板在群卡片中直接开启。

## 注意事项

- 本插件无独立业务数据库、本地 JSON 配置文件或媒体资产，无需进行历史数据迁移。
- WebUI 能够基于插件声明的元数据自动渲染群号列表表单（`id-list`），WebUI 本身目前仍处于内部演进阶段，尚未单独打包发布。
- 若申请人不在已开启功能的白名单群中，机器人绝不会自动通过好友申请。
