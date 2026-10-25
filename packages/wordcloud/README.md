# XDUCraft Wordcloud (`nonebot-plugin-xducraft-wordcloud`) 0.1.0

基于 NoneBot 2 与 OneBot v11 的群聊天词云图生成与定时推送插件。

---

## 功能说明

- **按群记录与过滤**：仅在启用的群中记录聊天文本；内置停用词库，自动过滤低频无意义词汇与系统格式。
- **定时与按需生成**：每日 `00:00` 自动生成并发放前一天的群词云图；亦支持管理员发送指令即时生成今日、昨日或指定日期的词云图。
- **内置字体资产**：插件内置开源思源黑体（`resources/fonts/SourceHanSansCN-Medium.otf`），无需依赖任何外部插件的字体文件。
- **双重门禁要求**：全局总开关（`wordcloud`）与群插件开关默认均为关闭。本功能生效必须同时满足：
  1. 在 WebUI 插件页或通过 Core SDK 开启全局总开关 `wordcloud`；
  2. 开启本群插件开关及群功能（在群内发送 `/功能 on 群聊词云` 或 `/功能 on wordcloud`，系统会自动同步本群插件开关）。

---

## 常用指令

| 指令 | 权限要求 | 说明 |
| :--- | :--- | :--- |
| `/wc on\|off` | 群管理 / 群主 / 超管 | 开启或关闭本群聊天记录与每日词云推送 |
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

本插件处于内部演进阶段，尚未发布至公共 PyPI 仓库。

**源码安装**：
```bash
pip install -e ./packages/core[onebot] -e ./packages/wordcloud
```

**Wheel 构建与联合安装**（字体已打包在 wheel 内）：
```bash
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/wordcloud
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_wordcloud-0.1.0-py3-none-any.whl
```

**宿主加载（`pyproject.toml`）**：
```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_wordcloud",
]
```

---

## 数据存储边界

1. **配置数据迁移**：历史 `wordcloud_config.json` 仅作为启动期单次导入源。首次启动由 Core 一次性导入至 Core SQLite（`wordcloud` 命名空间），确立记录后旧文件不再写入；若历史配置损坏直接中断启动。
2. **业务数据库隔离**：聊天文本日志保存在独立的业务数据库 `DATA_DIR/chat_logs.db`（由 `plugin_data_dir("wordcloud", legacy_relative_path="xducraft_bot/plugins/xducraft_wordcloud/data")` 定位），不混入 Core 配置数据库。
