# import time
# from collections import defaultdict

from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent#, Bot
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="xducraft_happy_bot",
    description="被@回复“喵~”",
    usage="被@时自动回复“喵~”",
)

from nonebot.rule import to_me

from xducraft_bot.plugins.xducraft_happy_bot.data_manager import get_at_me_status, set_at_me_status


at_me_reply = on_message(
    rule=to_me(),
    priority=10,
    block=True
)


@at_me_reply.handle()
async def handle_at_me(event: GroupMessageEvent):

    group_id = event.group_id
    is_enabled = get_at_me_status(group_id)

    if is_enabled:
    # if True:
        await at_me_reply.finish("喵~")
#
#
# # --- 1. 复读机配置与状态存储 ---
#
# # 配置参数
# REPEAT_COUNT = 5  # 复读触发次数：同一消息重复 3 次后触发
# REPEAT_TIME_LIMIT = 120  # 5分钟 = 300秒：消息记录的有效时间窗口
#
# # 消息记录存储：
# # {group_id: [{"message": str, "time": float, "user_id": int}, ...]}
# # 注意：我们存储的是消息的纯文本内容 (str) 和时间戳 (float)
# message_records = defaultdict(list)
#
# # 临时存储群聊开关状态 (实际项目中推荐使用 nonebot-plugin-datastore 或 JSON 文件存储)
# # group_repeat_switch = {123456: True, 654321: False} # 示例: 123456群开启
#
# # --- 2. 复读匹配器 ---
#
# # 复读匹配器实例：捕获所有群聊消息
# repeater = on_message(
#     priority=90,  # 较低优先级，低于 @喵回复和具体命令
#     block=False  # **关键：不阻塞，允许消息继续传递给其他插件**
# )
#
#
# @repeater.handle()
# async def handle_repeater(bot: Bot, event: GroupMessageEvent):
#     group_id = event.group_id
#     current_time = time.time()
#
#     # --- 群聊开关逻辑（你可以基于之前的 JSON 存储实现） ---
#     is_enabled = get_at_me_status(group_id)
#     if not is_enabled:
#         return
#
#     # 提取消息内容：使用纯文本作为复读判断依据，忽略图片等非文本内容
#     message_content = event.message
#     print(message_content)
#
#     # 忽略空消息或 Bot 自己的消息
#     if not message_content or event.self_id == event.user_id:
#         return
#
#     # --- 消息记录处理 ---
#
#     # 1. 清理过期消息 (移除早于时间限制的消息)
#     records = message_records[group_id]
#     message_records[group_id] = [
#         r for r in records if current_time - r["time"] <= REPEAT_TIME_LIMIT
#     ]
#
#     # 2. 记录当前消息
#     message_records[group_id].append({
#         "message": message_content,
#         "time": current_time,
#     })
#     print('现在的message:')
#     print(message_records[group_id])
#
#     # 3. 统计复读次数
#     repeat_count = 0
#     for record in message_records[group_id]:
#         if record["message"] == message_content:
#             repeat_count += 1
#
#     # 4. 判断是否触发复读
#     if repeat_count >= REPEAT_COUNT:
#         print("已经复读啦")
#         # 触发复读，发送消息
#         await bot.send(event=event, message=event.message)
#
#         # 5. 清空该消息的记录
#         # 清空所有匹配该内容的记录，防止 Bot 和群友无限复读
#         message_records[group_id] = [
#             r for r in message_records[group_id] if r["message"] != message_content
#         ]