# MC Status Backend (FastAPI)

独立部署的 Minecraft Java 版状态查询后端，用于机器人通过 HTTP 拉取状态。

## 接口

- `GET /health`
- `GET /status?query=<server_address>`

响应字段尽量对齐机器人当前消费结构：

- `online`, `hostname`, `port`, `original_query`, `ip`
- 在线时包含 `ping`, `version`, `protocol`, `players`, `description`, `description_raw`, `favicon`
- 失败时包含 `error`

## 启动

1. 安装依赖（项目根目录）：
   - `pip install -r requirements.txt`
2. 复制环境变量：
   - 将 `.env.example` 复制为 `.env`（可选）
3. 启动服务：
   - `uvicorn scripts.mc_status_backend.app:app --host 0.0.0.0 --port 8099`

也可以只复制 `app.py` 到目标机器后使用 `uvicorn app:app ...` 进行单文件轻量启动；此时若环境未安装 Core，会自动回退使用 `mcstatus` 兼容实现（单文件方式仍完整支持）。
共享协议实现（`xducraft_bot.shared.mc_protocol`）现来自已安装的 Core 包，不再仅因完整仓库位于 `sys.path` 就直接找到。只有在当前环境中安装了 Core 才会复用共享原始状态协议实现，以保留更完整的 MOTD 与玩家样本信息；在完整仓库按 `pip install -r requirements.txt` 安装自然满足该条件。

## 机器人配置建议

1. 机器人群内设置：`/mcs source custom`
2. 配置 API（群级）：`/mcs api set http://<你的后端域名或IP>:8099/status`
3. 或配置全局默认：`/mcs api global set http://<你的后端域名或IP>:8099/status`
