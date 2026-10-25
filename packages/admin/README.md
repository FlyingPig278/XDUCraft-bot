# XDUCraft Admin (`nonebot-plugin-xducraft-admin`) 0.1.0

基于 Vue 3 + Naive UI 的 XDUCraft NoneBot 机器人本地回环 WebUI 管理面板。

---

## 功能说明

- **声明驱动渲染**：前端由 Core 后端输出的 JSON Schema 与元数据动态驱动，自动支持多级树、标签列表、QQ 列表及本地图片上传等表单组件。
- **群优先交互体系 (Group-first)**：
  - **群聊 (`/groups`)**：枚举在线与历史群聊，卡片化展示本群业务插件与群独立配置；
  - **插件 (`/plugins`)**：集中管控各受管插件的全局总开关与全局独占配置；
  - **系统 (`/system`)**：展示已连接 Bot 账号在线状态、OneBot 协议端元数据与基础诊断信息。
- **安全与鉴权防护**：服务限定绑定回环接口，同源 `Origin` 校验、`X-CSRF-Token` 写防护、Cookie 标记 `HttpOnly` + `SameSite=Strict`（12 小时有效期）。
- **并发编辑保护**：基于 HMAC-SHA256 的版本摘要与 `If-Match` 机制，遇到并发编辑时返回 `409 Conflict` 并保留本地草稿。
- **非受管基础设施定位**：声明为 `managed=False`，自身不受业务门禁拦截。

---

## 环境变量配置

管理口令拥有机器人的最高控制权，**仅从环境变量读取，严禁写入配置文件或版本控制**：

| 环境变量 | 默认值 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `WEB_ADMIN_ENABLED` | `false` | 是 | 是否启动 WebUI 服务（设为 `true` 开启） |
| `WEB_ADMIN_PORT` | `8765` | 否 | WebUI 服务本地监听端口 |
| `WEB_ADMIN_PASSWORD` | 无 | 是 | 管理口令（**强约束至少 12 个字符**，不足则拒绝启动） |

---

## 构建与安装方式

前端源码集中在 `packages/admin/webui`。构建产物直接打包进 Python wheel，**生产宿主机运行无需安装 Node.js**。

### 1. 本地源码开发安装

在开发环境中，需先构建前端静态资产，再以可编辑模式联合安装：

```bash
# 1. 编译前端产物（输出至 packages/admin/src/xducraft_admin/static）
cd packages/admin/webui
npm ci
npm run build
cd ../../..

# 2. 联合安装 Core 与 Admin
pip install -e ./packages/core[onebot] -e ./packages/admin
```

> [!NOTE]
> 在可编辑模式（editable）下，若未构建前端产物，后端 API 仍可启动，浏览器访问前端路由将返回 503 提示。

### 2. 构建独立 Wheel 包与联合安装

打包钩子（`build_support.BuildPy`）强制保障：非 editable 模式下必须存在 `static/index.html` 产物方可打包。由于 Core 尚未发布至公共 PyPI，安装 Admin wheel 时必须**联合安装本地 Core wheel**：

```bash
# 构建前确保已完成前端编译
cd packages/admin/webui && npm ci && npm run build && cd ../../..

# 构建 Core 与 Admin Wheel
python -m pip install build
python -m build --outdir dist packages/core
python -m build --outdir dist packages/admin

# 联合安装生成的 Wheel 产物
pip install dist/nonebot_plugin_xducraft_core-0.3.0-py3-none-any.whl[onebot] \
            dist/nonebot_plugin_xducraft_admin-0.1.0-py3-none-any.whl
```

---

## 宿主加载配置

在 NoneBot 宿主项目的 `pyproject.toml` 中显式加载：

```toml
[tool.nonebot]
plugins = [
    "xducraft_config",
    "xducraft_admin",
]
```

---

## 启动与安全访问

服务启动后默认监听本地回环接口 `127.0.0.1:8765`，**严禁直接暴露在公网**。

- **本机访问**：直接在浏览器打开 `http://127.0.0.1:8765/`。
- **远程服务器访问**：在本地客户端建立安全 SSH 隧道：
  ```bash
  ssh -N -L 8765:127.0.0.1:8765 user@your-server-ip
  ```
  然后在本地浏览器打开 `http://127.0.0.1:8765/` 即可安全登录。
