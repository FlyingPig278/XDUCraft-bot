"""跨插件共享的基础设施。

这里只放**与业务无关**的通用能力，插件之间不应该再互相 import：

- :mod:`.json_store`   —— 带缓存与原子写入的 JSON 配置存储
- :mod:`.permissions`  —— 统一的权限判定
- :mod:`.feature_gate` —— 群级功能开关（功能隔离）
- :mod:`.onebot`       —— OneBot v11 发送辅助（合并转发、私聊回执等）
"""
