"""Synchronous resource transactions stay on the bot event loop."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
from typing import Any, Callable, Dict, Mapping, Optional
from pydantic import ValidationError

from . import models
from .adapters import PluginAdapter


class AdminError(Exception):
    def __init__(self, status: int, code: str, message: str = "操作失败", fields: Optional[dict] = None):
        self.status, self.code, self.message, self.fields = status, code, message, fields or {}
        super().__init__(code)


SCHEMAS = {
    ("mc_status", True): models.MCGroup, ("mc_status", False): models.MCGlobal,
    ("keyword", True): models.KeywordGroup, ("keyword", False): models.KeywordGlobal,
    ("happy_bot", True): models.Happy, ("pig_bot", False): models.Pig,
    ("wordcloud", False): models.Wordcloud, ("anti_recall", False): models.AntiRecall,
}


def validate(schema, data):
    try:
        return schema.model_validate(data).model_dump(exclude_none=False)
    except ValidationError as exc:
        fields = {".".join(map(str, item["loc"])): "字段值或类型不合法" for item in exc.errors(include_input=False, include_url=False)}
        raise AdminError(422, "invalid_config", "请修正标记的字段", fields) from None


class AdminService:
    def __init__(self, adapters: Dict[str, PluginAdapter], feature_gate, deployment,
                 bots: Callable[[], Mapping[str, Any]], *, invite_store=None, invite_settings=None):
        self.adapters, self.feature_gate, self.deployment, self.bots = adapters, feature_gate, deployment, bots
        self.invite_store, self.invite_settings = invite_store, invite_settings
        self.deployment_context = None
        self._revision_key = secrets.token_bytes(32)
        self._group_cache: Dict[str, list] = {}

    def revision(self, identity, data):
        raw = json.dumps([identity, data], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        return hmac.new(self._revision_key, raw, hashlib.sha256).hexdigest()

    def resource(self, identity, config, meta=None, raw=None):
        return {"config": config, "meta": meta or {}, "revision": self.revision(identity, config if raw is None else raw)}

    @staticmethod
    def check_revision(current, expected):
        if expected is None:
            raise AdminError(428, "revision_required", "请先读取当前配置")
        if not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise AdminError(400, "invalid_revision", "版本标识不合法")
        if not hmac.compare_digest(current["revision"], expected):
            raise AdminError(409, "stale_config", "配置已被 QQ 或其他页面修改，请重新加载后再保存")

    def adapter(self, name):
        adapter = self.adapters.get(name)
        if adapter is None:
            raise AdminError(404, "unknown_plugin", "不存在的插件")
        if not adapter.loaded:
            raise AdminError(503, "plugin_unavailable", "插件未加载")
        return adapter

    def feature(self, key):
        owner = next((a for a in self.adapters.values() if key in a.feature_keys), None)
        if owner is None:
            raise AdminError(404, "unknown_feature", "不存在的功能")
        if not owner.loaded:
            raise AdminError(503, "plugin_unavailable", "插件未加载")
        feature = self.feature_gate.get_feature(key)
        if feature is None:
            raise AdminError(503, "feature_unavailable", "功能尚未注册")
        return feature

    def get_feature(self, key, gid=None):
        feature = self.feature(key)
        shared = feature.uses_shared_store
        if gid is None:
            if not shared:
                raise AdminError(409, "feature_scope", "该功能由插件自己的群设置管理")
            enabled, source = self.feature_gate.get_default(key), "default"
        else:
            enabled, source = self.feature_gate.resolve(key, gid)
        return self.resource(["feature", key, gid], {"enabled": enabled},
                             {"source": source, "resettable": shared and gid is not None,
                              "superuser_only": feature.superuser_only, "passive": feature.passive},
                             {"enabled": enabled, "source": source})

    def put_feature(self, key, gid, data, expected, *, reset=False):
        current = self.get_feature(key, gid)
        self.check_revision(current, expected)
        if reset:
            if not current["meta"]["resettable"]:
                raise AdminError(409, "feature_scope", "该功能不支持恢复默认")
            self.feature_gate.clear_override(key, gid)
        else:
            target = validate(models.Switch, data)["enabled"]
            if gid is None:
                self.feature_gate.set_default(key, target)
            else:
                self.feature_gate.set_enabled(key, gid, target)
        result = self.get_feature(key, gid)
        if (reset and result["meta"]["source"] != "default") or (not reset and result["config"]["enabled"] != target):
            raise AdminError(500, "storage_failed", "配置未能保存")
        return result

    def get_config(self, name, gid=None):
        if (name, gid is not None) not in SCHEMAS:
            raise AdminError(404, "unknown_resource", "此作用域没有该配置")
        adapter = self.adapter(name)
        getter = adapter.get_global if gid is None else adapter.get_group
        if getter is None:
            raise AdminError(404, "unknown_resource", "此作用域没有该配置")
        raw = getter() if gid is None else getter(gid)
        config, meta = dict(raw), {}
        if name == "happy_bot":
            meta["effective_emoji_id"] = config.pop("effective_emoji_id", config["emoji_id"])
        elif name in ("wordcloud", "anti_recall"):
            keys = SCHEMAS[(name, False)].model_fields
            config = {key: raw[key] for key in keys}
            id_key = "ban_user_ids" if name == "wordcloud" else "exempt_user_ids"
            config[id_key] = [str(value) for value in config[id_key]]
        elif name == "keyword":
            from xducraft_bot.plugins.xducraft_keyword.reply_codec import replies_to_segments
            meta["rule_created_at"] = {rule["id"]: rule.get("created_at") for rule in raw["rules"]}
            config["rules"] = [{key: value for key, value in rule.items() if key != "created_at"} for rule in raw["rules"]]
            for rule in config["rules"]:
                rule["replies"] = replies_to_segments(rule["replies"])
            if gid is not None:
                config["join_replies"] = replies_to_segments(raw["join_replies"])
                global_raw = adapter.get_global()
                meta["effective_default_cooldown"] = raw["default_cooldown"] if raw["default_cooldown"] is not None else global_raw["default_cooldown"]
            else:
                meta["effective_default_cooldown"] = raw["default_cooldown"]
        return self.resource(["config", name, gid], config, meta, raw)

    def put_config(self, name, gid, data, expected):
        current = self.get_config(name, gid)
        self.check_revision(current, expected)
        clean = validate(SCHEMAS[(name, gid is not None)], data)
        adapter = self.adapter(name)
        if name == "happy_bot":
            if clean["emoji_id"] is not None and not re.fullmatch(r"[0-9]+", clean["emoji_id"]):
                raise AdminError(422, "invalid_config", "表情 ID 必须为数字", {"emoji_id": "请输入数字 ID"})
        elif name == "mc_status":
            from xducraft_bot.plugins.xducraft_mc_status.utils import is_valid_api_url, is_valid_server_address
            if clean["status_api_url"] and not is_valid_api_url(clean["status_api_url"]):
                raise AdminError(422, "invalid_config", "API URL 不合法", {"status_api_url": "请输入 HTTP(S) 地址"})
            seen = set()
            def tree(nodes, depth=0):
                if depth > 12 and nodes:
                    raise ValueError("tree_depth")
                for node in nodes:
                    node["ip"] = node["ip"].strip()
                    if not is_valid_server_address(node["ip"]) or node["ip"] in seen:
                        raise ValueError("server_address")
                    seen.add(node["ip"])
                    if node["tag_color"] and not re.fullmatch(r"[a-fA-F0-9]{6}", node["tag_color"]):
                        raise ValueError("tag_color")
                    node["tag_color"] = node["tag_color"].upper()
                    if node["priority"] is None:
                        del node["priority"]
                    tree(node["children"], depth + 1)
            try:
                if gid is not None:
                    tree(clean["servers"])
            except ValueError:
                raise AdminError(422, "invalid_config", "服务器地址、颜色或层级不合法", {"servers": "地址须唯一，树最多 13 层，颜色须为 6 位十六进制"}) from None
        elif name in ("wordcloud", "anti_recall"):
            key = "ban_user_ids" if name == "wordcloud" else "exempt_user_ids"
            try:
                clean[key] = list(dict.fromkeys(models.positive_id(value) for value in clean[key]))
            except ValueError:
                raise AdminError(422, "invalid_config", "名单需为正整数 QQ 号", {key: "非法 QQ 号"}) from None
            if name == "wordcloud":
                clean["additional_stopwords"] = list(dict.fromkeys(value.strip().lower() for value in clean["additional_stopwords"] if value.strip()))
        elif name == "keyword":
            from xducraft_bot.plugins.xducraft_keyword.reply_codec import segments_to_replies
            raw = adapter.get_global() if gid is None else adapter.get_group(gid)
            old = {rule["id"]: rule for rule in raw["rules"]}
            ids = set()
            try:
                for rule in clean["rules"]:
                    identity = rule["id"]
                    if identity is not None:
                        if identity not in old or identity in ids:
                            raise ValueError("invalid_rule_id")
                        ids.add(identity)
                    rule["replies"] = segments_to_replies(rule["replies"], old[identity]["replies"] if identity else [])
                if gid is not None:
                    clean["join_replies"] = segments_to_replies(clean["join_replies"], raw["join_replies"])
            except ValueError:
                raise AdminError(422, "invalid_config", "消息段或规则引用不合法", {"rules": "请检查消息内容和引用"}) from None
        writer = adapter.put_global if gid is None else adapter.put_group
        if writer is None:
            raise AdminError(404, "unknown_resource")
        try:
            writer(clean) if gid is None else writer(gid, clean)
        except ValueError:
            raise AdminError(422, "invalid_config", "配置内容不合法", {"rules" if name == "keyword" else "config": "请检查字段约束"}) from None
        return self.get_config(name, gid)

    def get_invite(self, gid):
        self.adapter("invite")
        if self.invite_store is None or self.invite_settings is None:
            raise AdminError(503, "plugin_unavailable", "邀请码插件未加载")
        if gid != self.invite_settings.group_id:
            raise AdminError(409, "invite_group_not_bound", "邀请码仅适用于当前绑定群")
        state = self.invite_store.get_state()
        meta = {"initialized": state.initialized_at is not None, "initialized_at": state.initialized_at,
                "configuration_complete": not bool(self.invite_settings.configuration_error())}
        return self.resource(["invite", gid], {"enabled": state.self_service_enabled}, meta,
                             {"enabled": state.self_service_enabled, **meta})

    def put_invite(self, gid, data, expected):
        current = self.get_invite(gid)
        self.check_revision(current, expected)
        target = validate(models.Switch, data)["enabled"]
        if not current["meta"]["initialized"]:
            raise AdminError(409, "invite_not_initialized", "请先在 QQ 使用 /invite init 初始化")
        if target and not current["meta"]["configuration_complete"]:
            raise AdminError(409, "invite_configuration_missing", "请先配置邀请码部署参数并重启")
        self.invite_store.set_self_service_enabled(target)
        result = self.get_invite(gid)
        if result["config"]["enabled"] != target:
            raise AdminError(500, "storage_failed", "配置未能保存")
        return result

    @staticmethod
    def public_deployment(values):
        public = dict(values)
        secret = public.pop("invite_api_secret", None)
        public["invite_api_secret_configured"] = None if secret is None else bool(secret)
        if public.get("invite_group_id") is not None:
            public["invite_group_id"] = str(public["invite_group_id"])
        if public.get("auto_accept_friend_group_ids") is not None:
            public["auto_accept_friend_group_ids"] = [str(gid) for gid in public["auto_accept_friend_group_ids"]]
        return public

    def deployment_values(self):
        if self.deployment_context is None:
            raise AdminError(503, "deployment_unavailable", "部署上下文不可用")
        try:
            overrides = self.deployment.read_overrides()
            active = self.deployment_context.values(pending=False)
            pending = self.deployment_context.values(pending=True)
        except self.deployment.DeploymentConfigError:
            raise AdminError(503, "deployment_config_invalid", "部署覆盖文件损坏，请修复后重启；其它配置仍可使用") from None
        return overrides, active, pending

    def get_deployment(self):
        overrides, active, pending = self.deployment_values()
        changed = sorted(key for key in active if active[key] != pending[key])
        locked = self.invite_store is not None and self.invite_store.get_state().initialized_at is not None
        return self.resource("deployment", {"pending": self.public_deployment(pending)},
                             {"active": self.public_deployment(active), "overridden": sorted(overrides),
                              "restart_required": bool(changed), "changed_keys": changed,
                              "textures": self.deployment_context.textures(),
                              "unavailable": self.deployment_context.unavailable, "invite_group_locked": locked}, overrides)

    def put_deployment(self, data, expected):
        current = self.get_deployment()
        self.check_revision(current, expected)
        clean = validate(models.Deployment, data)
        values, unset = clean["set"], clean["unset"]
        try:
            if "invite_group_id" in values:
                values["invite_group_id"] = models.positive_id(values["invite_group_id"], allow_zero=True)
            if "auto_accept_friend_group_ids" in values:
                if not isinstance(values["auto_accept_friend_group_ids"], list):
                    raise ValueError("invalid_ids")
                values["auto_accept_friend_group_ids"] = list(dict.fromkeys(models.positive_id(x) for x in values["auto_accept_friend_group_ids"]))
        except ValueError:
            raise AdminError(422, "invalid_config", "群号必须为数字字符串") from None
        if "invite_group_id" in values or "invite_group_id" in unset:
            if self.invite_store is None:
                raise AdminError(503, "invite_unavailable", "无法确认邀请码资格绑定状态")
            target = values.get("invite_group_id")
            if "invite_group_id" in unset:
                module = self.deployment_context.modules.get("invite")
                base = self.deployment.get_startup_base(module.Config) if module else None
                target = base.invite_group_id if base else None
            if self.invite_store.get_state().initialized_at is not None and target != self.invite_settings.group_id:
                raise AdminError(409, "invite_group_locked", "初始化后的邀请码资格不能迁移到其它群")
        if "mcs_texture" in values:
            texture = values["mcs_texture"]
            if "mc_status" in self.deployment_context.unavailable:
                raise AdminError(503, "texture_unavailable", "MC 插件未加载，无法确认材质")
            if texture not in ("", "random", "none") and texture not in self.deployment_context.textures():
                raise AdminError(422, "invalid_config", "材质不存在", {"mcs_texture": "请选择已有材质"})
        try:
            self.deployment.update_overrides(values, unset)
        except self.deployment.DeploymentConfigError as exc:
            if exc.code == self.deployment.DEPLOYMENT_CONFIG_WRITE_FAILED:
                raise AdminError(500, "storage_failed", "部署配置未能保存") from None
            raise AdminError(422, "invalid_config", "部署参数不合法") from None
        except (ValueError, ValidationError, TypeError):
            raise AdminError(422, "invalid_config", "部署参数不合法") from None
        return self.get_deployment()

    def overview(self):
        try:
            restart = self.get_deployment()["meta"]["restart_required"]
            warning = None
        except AdminError as exc:
            restart, warning = False, exc.code
        features = []
        for adapter in self.adapters.values():
            if not adapter.loaded:
                continue
            for key in adapter.feature_keys:
                feature = self.feature_gate.get_feature(key)
                if feature is not None and feature.uses_shared_store:
                    features.append({"key": key, "name": feature.name, "passive": feature.passive,
                                     "enabled": self.feature_gate.get_default(key)})
        return {"bots": [{"bot_id": str(key), "connected": True} for key in sorted(self.bots())],
                "plugins": [{"id": a.id, "name": a.name, "loaded": a.loaded,
                             "reason": None if a.loaded else "插件未加载"} for a in self.adapters.values()],
                "restart_required": restart, "deployment_warning": warning, "features": features}

    async def groups(self):
        bots = dict(self.bots())
        warnings = []
        successful = set()
        async def fetch(bot_id, bot):
            try:
                rows = await asyncio.wait_for(bot.get_group_list(), 5)
                cleaned = [{"group_id": models.positive_id(str(row["group_id"])),
                            "group_name": str(row.get("group_name", ""))} for row in rows]
                self._group_cache[str(bot_id)] = cleaned
                successful.add(str(bot_id))
            except Exception:
                warnings.append("机器人 " + str(bot_id) + " 的群列表暂不可用，保留最近成功结果")
        await asyncio.gather(*(fetch(key, bots[key]) for key in sorted(bots)))
        known = set()
        try:
            known.update(self.feature_gate.list_configured_groups())
        except Exception:
            warnings.append("共享开关的已配置群列表不可用")
        for name, adapter in self.adapters.items():
            if adapter.loaded and adapter.list_groups:
                try:
                    known.update(adapter.list_groups())
                except Exception:
                    warnings.append(adapter.name + " 的已配置群列表不可用")
        try:
            _, active, pending = self.deployment_values()
            for values in (active, pending):
                known.update(values.get("auto_accept_friend_group_ids") or [])
                if values.get("invite_group_id"):
                    known.add(values["invite_group_id"])
        except AdminError:
            warnings.append("部署配置中的群列表不可用")
        entries = {}
        for bot_id in sorted(self._group_cache, key=lambda key: (key not in successful, key)):
            for row in self._group_cache[bot_id]:
                gid = row["group_id"]
                current = bot_id in successful
                entry = entries.setdefault(gid, {"group_id": str(gid), "name": row["group_name"] or "群 " + str(gid),
                                                "bot_ids": [], "connected": False, "stale": not current})
                entry["bot_ids"].append(bot_id)
                entry["connected"] |= current
                if current:
                    entry["stale"] = False
        for value in known:
            try:
                gid = int(value)
                if gid > 0:
                    entries.setdefault(gid, {"group_id": str(gid), "name": "群 " + str(gid), "bot_ids": [], "connected": False, "stale": False})
            except (ValueError, TypeError):
                continue
        return {"groups": [entries[gid] for gid in sorted(entries)], "warnings": sorted(warnings)}

    def plugins(self, gid):
        cards = []
        active_whitelist = []
        try:
            _, active, _ = self.deployment_values()
            active_whitelist = active.get("auto_accept_friend_group_ids") or []
        except AdminError:
            if self.deployment_context:
                active_whitelist = self.deployment_context.values(pending=False).get("auto_accept_friend_group_ids") or []
        for name, adapter in self.adapters.items():
            card = {"id": adapter.id, "short_name": name, "name": adapter.name, "loaded": adapter.loaded,
                    "unavailable_reason": None if adapter.loaded else "插件未加载", "features": [],
                    "group_config": adapter.get_group is not None, "global_config": adapter.get_global is not None}
            if adapter.loaded:
                for key in adapter.feature_keys:
                    try:
                        resource = self.get_feature(key, gid)
                        feature = self.feature(key)
                        item = {"key": key, "name": feature.name, **resource["config"], **resource["meta"]}
                        item["effective"] = item["enabled"]
                        if name == "auto_friend":
                            item["active_whitelist_match"] = gid in active_whitelist
                            item["effective"] = item["enabled"] and gid in active_whitelist
                        card["features"].append(item)
                    except AdminError:
                        card["unavailable_reason"] = "功能尚未注册"
            if name == "invite":
                card["invite"] = {"applicable": self.invite_settings is not None and gid == self.invite_settings.group_id,
                                  "bound_group_id": str(self.invite_settings.group_id) if self.invite_settings else None}
                if card["invite"]["applicable"] and self.invite_store is not None:
                    resource = self.get_invite(gid)
                    card["invite"].update(resource["meta"])
                    card["invite"].update(resource["config"])
            cards.append(card)
        cards.append({"id": "xducraft_admin", "short_name": "admin", "name": "网页管理", "loaded": True,
                      "features": [], "group_config": False, "global_config": False})
        return {"plugins": cards}
