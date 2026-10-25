# MC Status Backend (FastAPI)

独立部署的 Minecraft Java 版状态查询轻量后端，供机器人通过 HTTP 拉取服务器在线状态与 MOTD 信息。
典型应用场景：机器人部署于公网，而 Minecraft 目标服务器仅在校园内网或私有内网可直连访问。

---

## 接口说明

- `GET /health`：健康检查接口，返回 `{"status": "ok"}`
- `GET /status?query=<server_address>`：查询目标服务器状态

响应字段：
- `online`（布尔值）、`hostname`、`port`、`original_query`、`ip`
- 在线时返回：`ping`、`version`、`protocol`、`players`、`description`、`description_raw`、`favicon`
- 查询失败时返回：`error`

---

## 依赖与安装

后端支持完全脱离机器人整仓独立运行。

### 1. 基础依赖安装

在独立的 Python 虚拟环境中安装基础运行依赖：

```bash
pip install "fastapi>=0.93,<1" "uvicorn~=0.38.0" "mcstatus>=11,<12"
```

### 2. 可选 Core 协议增强

后端代码在导入时会检测是否存在 Core 核心包：
- **未安装 Core（轻量模式）**：自动回退至原生 `mcstatus` 实现，支持直接将 `app.py` 复制到任何机器单文件部署；
- **安装了 Core（协议增强）**：若环境中安装了 `nonebot-plugin-xducraft-core`，将复用 Core 的 `xducraft_bot.shared.mc_protocol` 原生协议实现，获取更完整的原始 MOTD 与玩家样本信息。

---

## 环境变量与服务启动

> [!WARNING]  
> FastAPI 与 Uvicorn **默认不会自动读取当前目录的 `.env` 文件**。切勿在仅有 `.env` 的情况下直接启动，否则配置将不会生效。

支持的环境变量：
- `MC_STATUS_BACKEND_TIMEOUT`：单次状态查询超时时间（秒，浮点数，默认 `3.0`）。

### 启动方式 A：直接操作系统环境变量（推荐）

在当前终端注入环境变量并启动服务：

```bash
# Linux / macOS
export MC_STATUS_BACKEND_TIMEOUT=5.0
uvicorn app:app --host 0.0.0.0 --port 8099

# Windows PowerShell
$env:MC_STATUS_BACKEND_TIMEOUT="5.0"
uvicorn app:app --host 0.0.0.0 --port 8099
```

### 启动方式 B：通过 `.env` 文件启动

若希望通过 `.env` 管理环境，必须额外安装 `python-dotenv`，并通过 `--env-file` 参数显式加载：

```bash
pip install python-dotenv
cp .env.example .env
uvicorn app:app --env-file .env --host 0.0.0.0 --port 8099
```

---

## 机器人对接配置

在部署完后端并确保网络互通后，可在机器人所属群内配置接入：

1. **设置查询源为自建后端**：
   ```text
   /mcs source custom
   ```
2. **设置本群查询 API 地址**：
   ```text
   /mcs api set http://<后端IP或域名>:8099/status
   ```
3. 亦可在 WebUI 管理面板的群卡片中直接配置查询源与 API 接口。
