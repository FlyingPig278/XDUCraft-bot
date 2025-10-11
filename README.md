### 【中文版 / Chinese Version】

这是一个专门为XDUCraft编写的Minecraft服务器状态查询插件。

# [XDUCraft_bot] NoneBot 插件

## 环境要求

-   Python 3.9+ 
-   一个基于 OneBot v11 协议的机器人框架（如：Go-CQHTTP, NapCat等）

## 快速开始

请严格按照以下步骤操作，这可以避免环境冲突。

1.  **克隆项目**
    ```bash
    git clone https://github.com/FlyingPig278/XDUCraft-bot.git
    cd XDUCraft-bot
    ```

2.  **（重要）准备Python环境**
    **强烈建议**为本项目创建独立的虚拟环境。

    -   **如果使用PyCharm**：它通常会自动检测到项目并提示你创建虚拟环境，直接同意即可。
    -   **手动创建虚拟环境**（通用方法）：
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
    在虚拟环境激活的状态下，安装运行所需的所有包。
    ```bash
    pip install -r requirements.txt
    ```

4.  **运行项目**
    在虚拟环境激活的状态下，执行：
    ```bash
    nb run
    ```
    程序启动后，**请留意控制台输出的最后几行日志**，找到类似下面的信息，并记下端口号（如 `8080`）：
    `Application startup complete. Uvicorn running on http://127.0.0.1:8080`

5.  **连接机器人框架**
    启动你的机器人框架（如NapCat），将其配置为 **WebSocket客户端**，连接到上一步的地址。
    -   **地址示例**：`ws://127.0.0.1:8080/onebot/v11/ws`
    -   将 `8080` 替换为你实际看到的端口号。
    -   连接成功后，NoneBot控制台会显示日志，即可使用插件。

## 常见问题

-   **`nb: command not found`**：
    -   原因：通常是因为没有在激活的虚拟环境中安装依赖。
    -   解决：请回到第2步，确保虚拟环境已激活（命令行有`(venv)`），然后重新执行第3步 `pip install -r requirements.txt`。这个命令会自动安装`nb-cli`。
-   **端口被占用**：可通过 `nb run --port 新端口号`（如 `8090`）指定新端口。
---

### 【English Version / 英文版】

# [XDUCraft_bot] NoneBot Plugin

This is a Minecraft server status query plugin specifically written for XDUCraft.

## Prerequisites

-   Python 3.9+
-   A OneBot v11 compatible bot framework (e.g., Go-CQHTTP, NapCat, etc.)

## Quick Start

Please follow these steps carefully to avoid environment conflicts.

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/FlyingPig278/XDUCraft-bot.git
    cd XDUCraft-bot
    ```

2.  **(Important) Prepare Python Environment**
    It is **highly recommended** to create a virtual environment for this project.

    -   **If using PyCharm**: It will usually detect the project and prompt you to create a virtual environment. Just accept it.
    -   **Manual setup (Universal method)**:
        ```bash
        # Create the virtual environment
        python -m venv venv

        # Activate the virtual environment
        # On Windows:
        venv\Scripts\activate
        # On macOS or Linux:
        source venv/bin/activate
        ```
        You will see `(venv)` at the start of your command prompt when activated.

3.  **Install Dependencies**
    With the virtual environment activated, install all required packages.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the Project**
    With the virtual environment still activated, run:
    ```bash
    nb run
    ```
    After startup, **check the console output** for a line like the following and note the port number (e.g., `8080`):
    `Application startup complete. Uvicorn running on http://127.0.0.1:8080`

5.  **Connect Your Bot Framework**
    Start your bot framework (e.g., NapCat) and configure it as a **WebSocket Client** to connect to the address from the previous step.
    -   **Example Address**: `ws://127.0.0.1:8080/onebot/v11/ws`
    -   Replace `8080` with your actual port.
    -   Upon successful connection, the NoneBot console will show a log, and the plugin is ready to use.

## FAQ

-   **`nb: command not found`**:
    -   Cause: Usually, the dependencies were not installed within the activated virtual environment.
    -   Solution: Go back to Step 2, ensure the virtual environment is activated (with `(venv)`), and rerun Step 3: `pip install -r requirements.txt`. This command will install `nb-cli` automatically.
-   **Port already in use**: You can specify a new port with `nb run --port new_port` (e.g., `8090`).