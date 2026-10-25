# XDUCraft Admin (`nonebot-plugin-xducraft-admin`) 0.1.0

基于 Vue 3 + Naive UI 的 XDUCraft NoneBot 机器人本地回环 WebUI 管理面板。

提供可视化声明驱动表单渲染、按群配置管理、插件全局管控与系统状态监控。

主部署宿主仓库参见：[FlyingPig278/XDUCraft-bot](https://github.com/FlyingPig278/XDUCraft-bot)。

---

## 功能说明

- **声明驱动表单渲染**：前端由 Core 后端输出的 JSON Schema 与元数据动态驱动，自动支持多级树、标签列表、QQ 列表及本地图片上传等复杂组件。
- **群优先交互体系 (Group-first)**：
  - **群聊 (`/groups`)**：枚举在线与历史群聊，卡片化展示本群业务插件与群独立配置；
  - **插件 (`/plugins`)**：集中管控各受管插件的全局总开关与全局独占配置；
  - **系统 (`/system`)**：展示已连接 Bot 账号在线状态、OneBot 协议端元数据与基础诊断信息。
- **安全与鉴权防护**：服务严格限定绑定本地回环接口，同源 `Origin` 校验、`X-CSRF-Token` 写防护、Cookie 标记 `HttpOnly` + `SameSite=Strict`（12 小时有效期）。
- **并发编辑保护**：基于 HMAC-SHA256 的版本摘要与 `If-Match` 机制，遇到并发编辑时返回 `409 Conflict` 并保留本地草稿。
- **非受管基础设施定位**：声明为 `managed=False`，自身不受业务门禁拦截，且业务插件在未启用 WebUI 时完全正常运行。

---

## 环境变量配置

| 环境变量 | 默认值 | 配置来源 | 说明 |
| :--- | :--- | :--- | :--- |
| `WEB_ADMIN_ENABLED` | `false` | `.env` 或 OS 环境变量 | 是否启动 WebUI 服务（设为 `true` 开启，OS 变量优先） |
| `WEB_ADMIN_PORT` | `8765` | `.env` 或 OS 环境变量 | WebUI 服务本地监听端口（OS 变量优先） |
| `WEB_ADMIN_PASSWORD` | 无 | **仅操作系统环境变量** | 管理口令（**强约束至少 12 个字符**，仅当面板启用时必填） |

> [!IMPORTANT]
> - **管理口令安全约束**：`WEB_ADMIN_PASSWORD` 拥有机器人最高控制权，代码中特意未设 NoneBot `.env` 回退，**必须直接设置在进程操作系统的环境变量中**，防止被 NoneBot 的全局配置输出泄露。
> - **面板启动隔离**：当开启了面板但未提供口令或口令不足 12 位时，仅 WebUI 面板自身拒绝启动并输出错误日志，**NoneBot 机器人主进程与其他业务插件将继续正常运行**，绝不会导致整个机器人进程崩溃中断。

---

## 安装与加载

> [!NOTE]  
> 本软件包目前尚未发布至公共 PyPI 仓库。安装请使用预定推送的 GitHub Release Tag 源码链接。  
> 本仓库已在版本控制中跟踪编译好的前端静态资产（`src/xducraft_admin/static/`），无论是通过 pip Git Tag 安装、宿主固定 Git SHA 安装还是 Wheel 包安装，**部署宿主机均无需安装 Node.js 或 npm 环境**。

### 1. 宿主环境安装

在已初始化的 NoneBot 2 部署环境中，先安装 Core 核心包，再安装本插件：

```bash
# 1. 安装 Core 核心包（需包含 [onebot] 适配器扩展）
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"

# 2. 安装 Admin 插件
pip install "nonebot-plugin-xducraft-admin @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-admin.git@v0.1.0"
```

### 2. 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式同时加载 Core 与本插件：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_admin",
]
```

---

## 本地开发与测试（贡献者）

仓库中已跟踪预编译的前端产物。**仅开发后端或运行测试时无需 Node.js**，直接在仓库根目录执行：

```bash
# 安装 Core 依赖与本地开发依赖
pip install "nonebot-plugin-xducraft-core[onebot] @ git+https://github.com/FlyingPig278/nonebot-plugin-xducraft-core.git@v0.3.0"
pip install -e ".[dev]"

# 运行自动化测试
pytest

# 本地构建 wheel 发行包
python -m build
```

### 修改前端与完整 CI 构建

前端源码位于 `webui/` 目录下。当且仅当修改前端界面或执行完整 CI 构建时需要 Node.js 环境：

```bash
# 1. 编译前端产物（产物将输出至 src/xducraft_admin/static）
cd webui
npm ci
npm run build
cd ..

# 2. 修改前端后，须连同重新生成的 src/xducraft_admin/static/ 一并提交版本控制
```

打包构建机制（`build_support.BuildPy`）要求构建发行包时必须存在 `src/xducraft_admin/static/index.html` 静态产物。

---

## 启动与安全访问

服务启动后默认严格监听本地回环地址 `127.0.0.1:8765`，**严禁直接暴露在公网**。

- **本机访问**：直接在浏览器打开 `http://127.0.0.1:8765/`。
- **远程服务器访问（推荐）**：在本地客户端建立安全 SSH 隧道映射：
  ```bash
  ssh -N -L 8765:127.0.0.1:8765 user@your-server-ip
  ```
  随后在本地浏览器访问 `http://127.0.0.1:8765/` 即可安全登录。

---

## 许可证说明

本项目自身源码采用 [MIT License](LICENSE) 授权开源。

前端界面及其引用的第三方 JavaScript/CSS 依赖库（Vue、Naive UI 等）遵循各自独立的开源许可协议。
