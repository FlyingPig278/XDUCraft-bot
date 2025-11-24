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

### ❓ 常见问题 (FAQ)

- **`nb: command not found`**：
  - 原因：通常是因为没有在激活的虚拟环境中安装依赖。
  - 解决：请回到第 2 步，确保虚拟环境已激活（命令行有`(venv)`），然后重新执行第 3 步 `pip install -r requirements.txt`。这个命令会自动安装`nb-cli`。
- **端口被占用**：可通过 `nb run --port 新端口号`（如 `8090`）指定新端口。

---
