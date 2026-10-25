# XDUCraft Wordcloud (`nonebot-plugin-xducraft-wordcloud`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的群聊天词云图生成与定时推送插件。

支持按群记录发言、内置中文停用词过滤、每日 00:00 自动定时出图推送，以及管理员手动按需生成指定日期词云图。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能特性

- **按群记录与过滤**：仅在启用的群中记录聊天文本；内置停用词库，自动过滤低频无意义词汇与系统格式。
- **定时与按需生成**：每日 `00:00` 自动生成并发放前一天的群词云图；亦支持管理员发送指令即时生成今日、昨日或指定日期的词云图。
- **内置字体资产**：Wheel 安装包内置思源黑体历史版本（`resources/fonts/SourceHanSansCN-Medium.otf`），无需依赖外部系统字体。
- **双重门禁与推送约束**：全局总开关（`wordcloud`）与群插件开关默认均为关闭（`OFF`）。定时任务与消息响应严格遵循双重门禁：
  1. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `wordcloud`；
  2. 开启本群插件开关及群功能（在群内发送 `/功能 on 群聊词云`，系统会自动同步本群插件总开关）。

---

## 指令列表与权限控制

| 指令 | 权限要求 | 说明 |
| :--- | :--- | :--- |
| `/wc on\|off` | 群管理 / 群主 / 超管 | 开启或关闭本群聊天记录与每日词云推送（同步群插件总开关） |
| `/wc status` | 群管理 / 群主 / 超管 | 查看本群词云参数、聊天记录数与启用状态 |
| `/wc gen [today\|yesterday\|日期]` | 群管理 / 群主 / 超管 | 手动生成并发送指定日期的词云图（默认昨天） |
| `/wc ban add\|del\|list [QQ号\|@用户]` | 群管理 / 群主 / 超管 | 管理本群额外封禁成员（排除其发言） |
| `/wc clear [QQ号\|@用户]` | 群管理 / 群主 / 超管 | 清理指定用户在本群的历史聊天记录 |

---

## 配置项与作用域

- **全局独占参数 (`global_only`)**：
  - `retention_days`：聊天日志最大保留天数（默认 1095 天，每日 00:00 任务执行清理）；
  - `ban_user_ids`：全局封禁 QQ 列表（所有群统一排除其发言，群级设置无法解除全局封禁）。
- **群级独立参数 (`group_only`)**：
  - `ban_user_ids`：本群额外封禁 QQ 列表（与全局封禁合并生效）；
  - `min_word_length`：分词最短词长（默认 2 个字符）；
  - `max_words`：词云图最多展示词数（默认 200）；
  - `additional_stopwords`：本群额外停用词；
  - `footer_subtitle`：页脚副标题；
  - `footer_branding_enabled` 与 `footer_branding_text`：页脚署名开关与展示文本。

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Wordcloud 插件
pip install "nonebot-plugin-xducraft-wordcloud @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-wordcloud.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_wordcloud",
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

## 数据存储与历史迁移

1. **配置数据迁移**：历史 `wordcloud_config.json` 仅作为启动期单次导入源。首次启动由 Core 一次性导入至 Core SQLite（`wordcloud` 命名空间），确立记录后旧文件不再写入；若历史配置损坏直接中断启动。
2. **业务数据库隔离**：聊天文本日志保存在独立的业务数据库 `<DATA_DIR>/plugins/wordcloud/chat_logs.db` 中，不混入 Core 配置数据库。
3. **数据目录环境变量**：若需要自定义外部数据目录，必须在启动前通过操作系统环境变量配置 `XDUCRAFT_DATA_DIR`（绝对路径），切勿仅写在 live `.env` 中。

---

## 许可证与资产说明

- 本项目自身源码采用 [MIT License](LICENSE) 授权开源。
- 内置历史版本思源黑体字体文件 `resources/fonts/SourceHanSansCN-Medium.otf` 版权归 Adobe Systems Incorporated 所有，其内嵌声明遵循 **Apache License 2.0**，许可文本参见 [LICENSES/SourceHanSansCN-Apache-2.0.txt](LICENSES/SourceHanSansCN-Apache-2.0.txt)。详细第三方资源说明请参阅仓库根目录下的 [NOTICE](NOTICE) 文件。该历史二进制资产未重新标记为后续新版所采用的 OFL 许可。
- 本项目不主张该字体文件的 MIT 授权，字体资产授权遵循其 Apache 2.0 协议独立保留。
