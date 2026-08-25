"""邀请码插件的用户可见文本。

运营文案统一放在这里；业务模块只引用常量或渲染函数，方便集中审阅和修改。
日志文本、代码注释和数据库字段名不属于对外文案，不放在这里。
"""

from __future__ import annotations

from typing import Optional

PLUGIN_DESCRIPTION = "新群友自助领取 XDUCraft 邀请码，管理员可在私聊中人工发放"
PLUGIN_USAGE = "群内 @机器人 邀请码 或 /邀请码；私聊 /invite（别名 /邀请码）管理发码"

INVITE_COMMAND_NAME = "邀请码"
SELF_REMARK_PREFIX = "[自助]"
ADMIN_REMARK_PREFIX = "[管理员发放]"
SELF_PRECHECK_MESSAGE = "正在生成您的邀请码，请稍等。"

SELF_NOT_INITIALIZED = "邀请码自助功能尚未开放。"
SELF_DISABLED = "邀请码自助功能当前已暂停，请联系管理员。"
SELF_MEMBER_UNKNOWN = "暂时无法确认您的群成员信息，请稍后重试。"
SELF_LEGACY_MEMBER = "您在自助发码功能上线前已经加入本群，请联系管理员人工处理。"
SELF_JOIN_TIME_UNKNOWN = "暂时无法确认您的入群时间，请联系管理员。"
SELF_JOINED_TOO_EARLY = "您的入群时间早于自助功能上线时间，请联系管理员人工处理。"
SELF_ALREADY_CLAIMED = "您已经申请过邀请码，不能重复自助领取。"
SELF_IN_PROGRESS = "您的邀请码正在生成，请勿重复申请。"
SELF_BUSY = "暂时无法受理申请，请稍后重试。"
SELF_PRIVATE_UNAVAILABLE = "无法向您发送私聊消息，请先添加机器人好友或开启临时会话后重试。"
SELF_GENERATE_FAILED = "邀请码生成失败，请稍后重新申请。"
SELF_PERSIST_FAILED_RETRY = "邀请码状态保存失败，本次不会发送邀请码，请稍后重新申请。"
SELF_DELIVERY_FAILED_LOCKED = "邀请码发送结果异常。为避免重复发码，您已不能再次自助申请，请联系管理员处理。"
SELF_SUCCESS_GROUP = "邀请码已发放，请查收私聊。"
GROUP_ARGUMENTS_REJECTED = "获取邀请码请直接发送 “ /邀请码 ”；管理员命令请私聊机器人发送。"

ADMIN_USAGE = (
    "用法：\n"
    "/invite <QQ> — 为当前大群成员发码\n"
    "/invite force <QQ> — 强制重复发码\n"
    "/invite status — 查看状态\n"
    "/invite on|off — 开关成员自助\n"
    "/invite init — 快照旧成员并首次开放（仅 SUPERUSER）"
)
ADMIN_PRIVATE_ONLY = "邀请码管理命令只能在机器人私聊中使用。"
ADMIN_PERMISSION_DENIED = "只有群主、管理员或 SUPERUSER 可以使用该命令。"
ADMIN_INIT_SUPERUSER_ONLY = "初始化邀请码功能需要 SUPERUSER 权限。"
ADMIN_ALREADY_INITIALIZED = "邀请码功能已经初始化，不能重复快照旧成员。"
ADMIN_MEMBER_LIST_FAILED = "无法读取群成员列表，初始化未生效。"
ADMIN_MEMBER_LIST_EMPTY = "群成员列表为空，初始化未生效。"
ADMIN_LEASE_BUSY = "暂时无法占用发码任务，请稍后再试。"
ADMIN_GENERATE_INTERNAL_ERROR = "邀请码生成失败：未预期的内部错误。"
ADMIN_PERSIST_FAILED = "邀请码已经生成，但领取记录落库失败；邀请码未返回，请检查数据库后重试。"
ADMIN_NOT_INITIALIZED = "邀请码功能尚未初始化，请先由 SUPERUSER 执行 /invite init。"
USAGE_INIT = "用法：/invite init"
USAGE_STATUS = "用法：/invite status"
USAGE_FORCE = "用法：/invite force <QQ>"

CONFIG_GROUP_ID_MISSING = "未配置 INVITE_GROUP_ID"
CONFIG_SECRET_MISSING = "未配置 INVITE_API_SECRET"
CONFIG_HTTPS_REQUIRED = "INVITE_API_URL 必须使用 HTTPS"

API_REMARK_REQUIRED = "邀请码备注不能为空"
API_REMARK_TOO_LONG = "邀请码备注超过 255 个字符"
API_SUCCESS_NOT_JSON = "API 成功响应不是合法 JSON"
API_SUCCESS_NOT_ENVELOPE = "API 成功响应不是信封对象"
API_CIPHERTEXT_EMPTY = "API 响应密文为空"
API_DECRYPT_FAILED = "API 响应解密失败：密钥不一致或内容被篡改"
API_PLAINTEXT_NOT_JSON = "API 解密结果不是合法 JSON"
API_PLAINTEXT_NOT_OBJECT = "API 解密结果不是对象"
API_CODE_INVALID = "API 返回的邀请码格式错误"
API_METADATA_INCOMPLETE = "API 返回的邀请码元数据不完整"
API_CONNECTION_FAILED = "连接邀请码 API 失败"
API_REQUEST_FAILED = "邀请码 API 请求失败"


def self_service_guide(group_id: int) -> str:
    if group_id > 0:
        return (
            f"请到 XDUCraft 大群（群号 {group_id}）发送 /邀请码 以获取邀请码。"
        )
    return "请到 XDUCraft 大群发送 /邀请码。当前机器人尚未配置大群号，请联系管理员。"


def self_invite_message(code: str) -> str:
    return f"您的 XDUCraft 邀请码：\n{code}\n\n请妥善保管并尽快使用。"


def render_status(
    *,
    initialized: bool,
    enabled: bool,
    group_id: int,
    initialized_at: Optional[int],
    legacy_count: int,
    claimed_count: int,
    issuance_count: int,
    secret_configured: bool,
) -> str:
    return (
        "邀请码功能状态：\n"
        f"初始化：{'是' if initialized else '否'}\n"
        f"成员自助：{'开启' if enabled else '关闭'}\n"
        f"大群：{group_id or '未配置'}\n"
        f"上线时间戳：{initialized_at or '未初始化'}\n"
        f"旧成员快照：{legacy_count} 人\n"
        f"已占用自助资格：{claimed_count} 人\n"
        f"成功发码记录：{issuance_count} 条\n"
        f"API 密钥：{'已配置' if secret_configured else '未配置'}"
    )


def init_config_error(error: str) -> str:
    return f"无法初始化：{error}。"


def issue_config_error(error: str) -> str:
    return f"无法发码：{error}。"


def init_success(legacy_count: int, initialized_at: int) -> str:
    return (
        f"初始化完成：已快照 {legacy_count} 名旧成员，成员自助现已开启。\n"
        f"上线时间戳：{initialized_at}"
    )


def target_not_member(user_id: int) -> str:
    return f"无法确认 QQ {user_id} 当前在大群中，未生成邀请码。"


def target_already_claimed(user_id: int) -> str:
    return (
        f"QQ {user_id} 已有成功发码记录。\n"
        f"如确认需要重复发码，请使用 /invite force {user_id}"
    )


def target_in_progress(user_id: int) -> str:
    return f"QQ {user_id} 当前有发码任务正在进行，请稍后再试。"


def api_generate_failed(message: str) -> str:
    return f"邀请码生成失败：{message}"


def admin_issue_success(user_id: int, code: str, *, forced: bool) -> str:
    force_note = "（强制重复发码）" if forced else ""
    return (
        f"已为 QQ {user_id} 生成邀请码{force_note}：\n{code}\n\n"
        f"API 备注：{ADMIN_REMARK_PREFIX}{user_id}"
    )


def usage_toggle(action: str) -> str:
    return f"用法：/invite {action}"


def toggle_success(enabled: bool) -> str:
    return f"已{'开启' if enabled else '关闭'}普通成员自助发码。管理员手动发码不受影响。"


def api_field_missing(field: str) -> str:
    return f"API 响应缺少 {field}"


def api_field_not_base64(field: str) -> str:
    return f"API 响应的 {field} 不是合法 Base64"


def api_field_wrong_size(field: str) -> str:
    return f"API 响应的 {field} 长度错误"


def api_http_error(status_code: int) -> str:
    return f"邀请码 API 返回 HTTP {status_code}"
