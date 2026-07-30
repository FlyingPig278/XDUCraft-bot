<div align="center">

# XDUCraft Bot - NoneBot Plugin

<a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white" alt="Python Version">
</a>
<a href="https://v2.nonebot.dev/">
    <img src="https://img.shields.io/badge/NoneBot-2.0.0+-red?logo=nonebot" alt="NoneBot Version">
</a>
<a href="https://github.com/onebotdev/onebot/blob/master/v11/README.md">
    <img src="https://img.shields.io/badge/OneBot-v11-green?logo=telegram" alt="OneBot Version">
</a>

A Minecraft server status query plugin for NoneBot, specially designed for XDUCraft.

[**English**](#english-version--英文版) | [**中文**](#中文版--chinese-version)

</div>

---

> [!WARNING]  
> 此项目还在完善中，请谨慎本地部署。
> 彻底可用后将重构 README 文件。

这是一个专门为 XDUCraft 编写的 Minecraft 服务器状态查询插件。

### 🚀 快速开始

1.  **克隆项目**

    ```bash
    git clone https://github.com/FlyingPig278/XDUCraft-bot.git
    cd XDUCraft-bot
    ```

2.  **（重要）准备 Python 环境**
    **强烈建议**为本项目创建独立的虚拟环境。

    - **如果使用 PyCharm**：它通常会自动检测到项目并提示你创建虚拟环境，直接同意即可。
    - **手动创建虚拟环境**（通用方法）：

      ```bash
      # 创建虚拟环境
      python -m venv venv

      # 激活虚拟环境
      # Windows:
      venv\Scripts\activate
      # macOS/Linux:
      source venv/bin/activate
      ```

      激活后，命令行提示符前会出现 `(venv)` 字样。

3.  **安装项目依赖**
    确保你已处在激活的虚拟环境中，然后运行：

    ```bash
    pip install -r requirements.txt
    ```

4.  **运行项目**
    在虚拟环境中，执行以下命令启动机器人后端：

    ```bash
    nb run
    ```

    程序启动后，**请留意控制台输出的最后几行日志**，找到类似下面的信息，并记下端口号（如 `8080`）：
    `Application startup complete. Uvicorn running on http://127.0.0.1:8080`

5.  **连接机器人框架**
    启动你的机器人框架（如 NapCat），将其配置为 **WebSocket 客户端**，连接到上一步的地址。
    - **地址示例**：`ws://127.0.0.1:8080/onebot/v11/ws`
    - 将 `8080` 替换为你实际看到的端口号。
    - 连接成功后，NoneBot 控制台会显示日志，即可使用插件。

### 📝 环境要求

- Python 3.9+
- 一个基于 OneBot v11 协议的机器人框架（推荐 Napcat）

### 🐷 猪猪图插件（xducraft_pig_bot）

- 自动推送：可按群开关，每 6 小时随机推送 1 张猪猪图。
- 手动查询：`/pig [关键词]`；不带关键词时随机返回 1 张，匹配多张时以合并转发返回。
- 管理命令（群管理/群主/SUPERUSER）：
  - `/pig auto on|off`：开关自动推送
  - `/pig query on|off`：开关手动查询
  - `/pig status`：查看本群开关状态

配置文件位于 `xducraft_bot/plugins/xducraft_pig_bot/data/pig_config.json`。

### ☁️ 词云插件（xducraft_wordcloud）

- 对配置中启用的群持续记录群聊文本（仅纯文本内容）。
- 每天 `00:00` 自动统计前一天聊天并发送词云图。
- 自动过滤停用词（使用 `stopwordsiso` 词库），并按 `retention_days` 轮换删除旧数据。
- 管理命令（仅群管理/群主/SUPERUSER）：
  - `/wc on`：开启本群词云记录与自动推送
  - `/wc off`：关闭本群词云记录与自动推送
  - `/wc status`：查看本群状态
  - `/wc gen [today|yesterday|YYYY-MM-DD|YYYY-MM|all]`：手动生成并发送词云（默认 today）

词云插件支持 `retention_days` 配置项（默认 1095 天），可按需长期保留聊天记录。

配置示例：`xducraft_bot/plugins/xducraft_wordcloud/data/wordcloud_config.json.example`。

### 🎛️ 统一功能开关（xducraft_features）

- `/功能`：查看本群所有插件的启用状态。
- `/功能 on <功能名>`、`/功能 off <功能名>`：群管理员统一开关功能。
- `/功能 reset <功能名>`：清除使用共享存储的群级覆盖，回到默认值。
- 私聊机器人发送 `/功能 <群号>` 查看指定群，或发送
  `/功能 <群号> on|off|reset <功能名>` 进行管理；机器人会重新校验群主或管理员身份。
- 被动响应或主动推送类功能默认关闭；MC 更新推送仍仅允许 SUPERUSER 修改。

猪猪图查询/推送、词云、MC 更新、MC 状态、表情回应、关键词回复和反撤回均已接入此面板。

### 🧩 关键词回复（xducraft_keyword）

- 默认关闭，管理员使用 `/关键词 on` 或 `/功能 on 关键词回复` 开启。
- `/关键词 add <关键词> <回复>`：添加本群规则，回复支持文字、图片和表情。
- `/关键词 del|show <关键词>`：删除或查看规则。
- `/关键词 mode <关键词> <包含|完全|开头|正则>`：调整匹配方式。
- `/关键词 cooldown <秒>`：设置本群默认冷却时间，避免重复触发刷屏。
- `/关键词 global ...`：SUPERUSER 管理所有已启用群共享的全局规则。

### 🕵️ 反撤回（xducraft_anti_recall）

- 默认关闭，只缓存明确开启的群；群内不会公开播报撤回内容。
- 群管理员使用 `/反撤回 on|off|status|clear` 管理本群。
- 群成员私聊机器人发送 `/撤回 [群号|条数]` 查询；机器人会再次校验查询者的群成员身份。
- 支持文字、图片/表情和合并转发，撤回媒体会在链接失效前保存到本地。

### ⛏️ MC 服务器状态（xducraft_mc_status）

- `/mcs`、`/mcs all`、`/mcs <地址>`：查询本群服务器或指定服务器。
- `/mcs auth`：查看并显式配置正版、MUA、XDU、第三方外置、离线或混合登录方式；自动探测默认关闭。
- `/mcs source`、`/mcs api`：按群或全局选择本地协议、公共 API 或自建后端。
- `/mcs edit`：私聊获取网页编辑链接；编辑会话 30 分钟过期且只允许导入一次。
- `/mcs diag`：查看配置、缓存和各状态源连通性。

自建查询后端见 `scripts/mc_status_backend/README.md`。

#### 状态图外观

状态图的设计语言参考了 [`koishi-plugin-mcsm-portal`](https://github.com/KrLite/koishi-plugin-mcsm-portal)：
854×480 的原版窗口画布、方块材质、Minecraft 像素字体和直角硬边框；仅白字保留原版投影，黑字与彩色字不加投影。
每张材质会按自身亮度动态压暗。顶部概览是带像素点的纯文字：对应计数大于零时为绿点，
等于零时为红点。服务器卡片保持 80px：64px 图标无内边框，正文给 MOTD 两行；空 MOTD
或默认的 `A Minecraft Server` 会改用配置备注。Tag 作为卡片左上方的外置页签，底边贴
住卡片顶边；相邻卡片的间距从上一行底边量到下一项可见的 Tag / 卡片顶边。地址行保留，
验证方式使用彩色下划线文字。在线人数最高且至少 5 人的服务器会在人数计数器左侧显示
与文字等大的火焰，并列最高时全部显示。延迟信号条缩小到不超过文字高度；底部公告保持
不透明，版本号保持半透明，离线 barrier 图标完全不透明，验证方式边条用实线 / 虚线区分。

外观参数写在 `.env`（见 `.env.prod.example`，改完重启生效）：

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `MCS_BRAND` | `XDUCRAFT` | 顶栏品牌行，留空则不画 |
| `MCS_TITLE` | `Minecraft 服务器状态` | 主标题，留空则不画 |
| `MCS_CREDIT` | `Powered by …` | 底部渐变压角里的署名，留空则不画 |
| `MCS_SHOW_GENERATED_AT` | `true` | 压角右侧是否显示生成时间 |
| `MCS_TEXTURE` | 留空 | 背景材质：留空按群号固定、`random`、`none` 或具体文件名；亮度会自动归一化 |
| `MCS_WIDTH` | `854` | 画布逻辑宽度（640–1600） |
| `MCS_SCALE` | `2` | 输出倍率，只接受 2 或 4 |
| `MCS_MIN_HEIGHT` | `480` | 最小逻辑高度，`0` 表示收缩到内容 |

`MCS_BRAND`、`MCS_TITLE`、`MCS_CREDIT` 都支持 `§` 颜色码。

调外观不用启动机器人：

```bash
python scripts/preview_mc_status.py            # 用假数据出全部场景到 preview/
python scripts/preview_mc_status.py --list     # 看有哪些场景
python scripts/preview_mc_status.py velocity   # 只出 Velocity 群组服那张
python scripts/preview_mc_status.py --min-height 0 --texture none
```

预览脚本和线上出图走的是同一个渲染函数，所以看到的就是真实效果。场景覆盖
Velocity 群组服层级、超长 MOTD、彩虹名字（逐字色码 / 双色渐变 / 多色渐变）、
六种验证方式、五档延迟和空态。

### ❓ 常见问题 (FAQ)

- **`nb: command not found`**：
  - 原因：通常是因为没有在激活的虚拟环境中安装依赖。
  - 解决：请回到第 2 步，确保虚拟环境已激活（命令行有`(venv)`），然后重新执行第 3 步 `pip install -r requirements.txt`。这个命令会自动安装`nb-cli`。
- **端口被占用**：可通过 `nb run --port 新端口号`（如 `8090`）指定新端口。

---
