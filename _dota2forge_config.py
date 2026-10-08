"""Native GsCore configuration bridge; available before project runtime packages."""

import json
import math
import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from gsuid_core.utils.plugins_config.gs_config import StringConfig, all_config_list
from gsuid_core.utils.plugins_config.models import (
    GsBoolConfig,
    GsFloatConfig,
    GsIntConfig,
    GsStrConfig,
)


class ConfigBridgeError(Exception):
    code = "invalid_host_config"

    def __init__(self):
        super().__init__(self.code)


_TRACE_GUARD_MARKER = "Dota2UID/config-trace-guard/v1"
_CONFIG_ROUTE = "/api/plugins/dota2uid"


def _config_request(scope):
    if scope.get("type") != "http":
        return False
    path = scope.get("path", "")
    if not isinstance(path, str):
        return False
    path = path.rstrip("/").casefold()
    return (
        path == _CONFIG_ROUTE
        or path == _CONFIG_ROUTE + "/config"
        or path.startswith(_CONFIG_ROUTE + "/config/")
    )


def _sdk_trace_class(candidate):
    return (
        getattr(candidate, "__module__", None) == "gsuid_core.http_trace_middleware"
        and getattr(candidate, "__name__", None) == "HttpTraceMiddleware"
    )


class ConfigTraceGate:
    """Keep native configuration replies out of the SDK's response-body trace."""

    _dota2uid_config_trace_guard = _TRACE_GUARD_MARKER

    def __init__(self, app, *, trace_factory=None, trace_args=(), trace_kwargs=None, trace=None):
        if trace is None:
            trace = trace_factory(app, *trace_args, **(trace_kwargs or {}))
        self.trace = trace
        self.app = trace.app

    async def __call__(self, scope, receive, send):
        # The inner app still contains routing, authentication and exception handlers.
        target = self.app if _config_request(scope) else self.trace
        await target(scope, receive, send)


def protect_config_traces(app):
    """Compose a plugin-only gate around registered and already-built SDK traces.

    The SDK currently has no request-scope exclusion hook. Replacing only its trace
    middleware record/node leaves every other middleware and route unchanged. Both
    registration and the built stack are checked so hot installation is protected.
    A stable class marker makes a later plugin-module reload reuse the existing gate.
    """
    replacements = []
    nodes = []
    try:
        for index, record in enumerate(app.user_middleware):
            if not _sdk_trace_class(record.cls):
                continue
            arguments = getattr(record, "args", ())
            options = getattr(record, "kwargs", getattr(record, "options", {}))
            if type(arguments) is not tuple or type(options) is not dict:
                raise ConfigBridgeError()
            replacement = type(record)(
                ConfigTraceGate,
                trace_factory=record.cls,
                trace_args=arguments,
                trace_kwargs=dict(options),
            )
            replacements.append((index, replacement))

        parent, attribute = app, "middleware_stack"
        node = getattr(parent, attribute, None)
        visited = set()
        while node is not None:
            if id(node) in visited:
                raise ConfigBridgeError()
            visited.add(id(node))
            if _sdk_trace_class(type(node)):
                inner = node.app
                gate = ConfigTraceGate(inner, trace=node)
                nodes.append((parent, attribute, gate))
                parent, attribute, node = gate, "app", inner
            else:
                parent, attribute = node, "app"
                node = getattr(node, attribute, None)
        # Plan first, then install without clearing or rebuilding the live ASGI stack.
        for index, replacement in replacements:
            app.user_middleware[index] = replacement
        for parent, attribute, gate in nodes:
            setattr(parent, attribute, gate)
    except (AttributeError, TypeError, ValueError):
        raise ConfigBridgeError() from None
    return bool(replacements or nodes)


DEFAULTS = {
    "namespace": "dota2uid-local",
    "stratz_token": "",
    "timeout_seconds": 10.0,
    "reply_mode": "image",
    "illustration_path": "",
    "asset_download_mode": "auto",
    "asset_proxy": "",
    "subscriptions_enabled": False,
    "subscription_interval_seconds": 300,
    "daily_report_hour": 9,
    "platforms": {"onebot": "qq", "qq": "qq", "telegram": "telegram"},
}
REQUIRED_LEGACY_KEYS = {"namespace", "stratz_token", "timeout_seconds", "platforms"}
STRINGS = {
    "namespace",
    "stratz_token",
    "reply_mode",
    "illustration_path",
    "asset_download_mode",
    "asset_proxy",
}
INTEGERS = {"subscription_interval_seconds", "daily_report_hour"}
IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,63}")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ConfigBridgeError()
        result[key] = value
    return result


def _json(source):
    try:
        value = json.loads(source, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        # Python's JSON parser accepts unpaired surrogates that the SDK decoder rejects.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except (ValueError, TypeError, RecursionError):
        raise ConfigBridgeError() from None


def _invalid_constant(value):
    raise ConfigBridgeError()


def _typed_value(key, value, *, native=False):
    if key in STRINGS:
        valid = type(value) is str
    elif key in INTEGERS:
        valid = type(value) is int
    elif key == "subscriptions_enabled":
        valid = type(value) is bool
    elif key == "timeout_seconds":
        valid = type(value) in (int, float)
        if valid:
            try:
                converted = float(value)
            except OverflowError:
                raise ConfigBridgeError() from None
            if not math.isfinite(converted):
                raise ConfigBridgeError()
            return converted
    elif key == "platforms":
        if native:
            if type(value) is not str:
                raise ConfigBridgeError()
            value = _json(value)
        valid = type(value) is dict and all(
            type(name) is str and type(platform) is str for name, platform in value.items()
        )
        if valid:
            return dict(value)
    else:
        valid = False
    if not valid:
        raise ConfigBridgeError()
    return value


def _semantic_value(key, value):
    plain = _typed_value(key, value, native=key == "platforms")
    if key == "namespace":
        valid = IDENTIFIER.fullmatch(plain) is not None
    elif key == "stratz_token":
        valid = plain.isascii() and all(33 <= ord(char) <= 126 for char in plain)
    elif key == "timeout_seconds":
        valid = math.isfinite(plain) and 0 < plain <= 60
    elif key == "reply_mode":
        valid = plain in {"image", "text"}
    elif key == "asset_download_mode":
        valid = plain in {"auto", "manual", "off"}
    elif key == "subscription_interval_seconds":
        valid = 60 <= plain <= 86400
    elif key == "daily_report_hour":
        valid = 0 <= plain <= 23
    elif key == "illustration_path":
        valid = len(plain) <= 2048 and all(ord(char) >= 32 for char in plain)
    elif key == "asset_proxy":
        valid = len(plain) <= 2048 and all(ord(char) >= 33 for char in plain)
        if valid and plain:
            try:
                proxy = urlsplit(plain)
                valid = (
                    proxy.scheme in {"http", "https"}
                    and bool(proxy.hostname)
                    and proxy.port is not None
                    and not proxy.query
                    and not proxy.fragment
                    and proxy.path in {"", "/"}
                )
            except ValueError:
                valid = False
    elif key == "platforms":
        valid = bool(plain) and all(
            bool(name) and IDENTIFIER.fullmatch(platform) is not None
            for name, platform in plain.items()
        )
    else:
        valid = True
    if not valid:
        raise ConfigBridgeError()
    return plain if key == "timeout_seconds" else value


def _native_type(key):
    if key in INTEGERS:
        return "GsIntConfig"
    if key == "subscriptions_enabled":
        return "GsBoolConfig"
    if key == "timeout_seconds":
        return "GsFloatConfig"
    return "GsStrConfig"


def _check_native(path):
    raw = _json(path.read_text(encoding="utf-8"))
    if type(raw) is not dict or set(raw) != set(DEFAULTS):
        raise ConfigBridgeError()
    common = {"type", "title", "desc", "data", "secret"}
    for key, field in raw.items():
        if type(field) is not dict or not {"type", "title", "desc", "data"} <= set(field):
            raise ConfigBridgeError()
        allowed = set(common)
        if _native_type(key) == "GsStrConfig":
            allowed |= {"options", "regex", "details"}
        elif _native_type(key) == "GsIntConfig":
            allowed |= {"options", "max_value"}
        elif _native_type(key) == "GsFloatConfig":
            allowed |= {"min_value", "max_value"}
        if (
            set(field) - allowed
            or field["type"] != _native_type(key)
            or type(field["title"]) is not str
            or type(field["desc"]) is not str
            or "secret" in field
            and type(field["secret"]) is not bool
        ):
            raise ConfigBridgeError()
        if "options" in field and (
            type(field["options"]) is not list
            or any(type(item) is not (int if key in INTEGERS else str) for item in field["options"])
        ):
            raise ConfigBridgeError()
        if "regex" in field and field["regex"] is not None and type(field["regex"]) is not str:
            raise ConfigBridgeError()
        if (
            "details" in field
            and field["details"] is not None
            and type(field["details"]) is not dict
        ):
            raise ConfigBridgeError()
        for bound in ("min_value", "max_value"):
            if bound in field and field[bound] is not None:
                accepted = (int,) if key in INTEGERS else (int, float)
                if type(field[bound]) not in accepted:
                    raise ConfigBridgeError()
                if key == "timeout_seconds":
                    _typed_value(key, field[bound])
        _typed_value(key, field["data"], native=True)


def _legacy_values(path):
    if not path.exists():
        return dict(DEFAULTS)
    raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    if not set(raw) >= REQUIRED_LEGACY_KEYS or set(raw) - set(DEFAULTS):
        raise ConfigBridgeError()
    result = dict(DEFAULTS)
    for key, value in raw.items():
        result[key] = _typed_value(key, value)
    return result


def _fields(values):
    apply = "保存后请先停用 Dota2UID，再重载插件或完整重启 GsCore 后生效。"
    return {
        "namespace": GsStrConfig(
            "部署命名空间",
            "用于账号与订阅身份分区，修改后将使用新的分区。" + apply,
            values["namespace"],
            regex=r"^[a-z][a-z0-9_.-]{0,63}$",
        ),
        "stratz_token": GsStrConfig(
            "STRATZ Token",
            "留空时等待配置，请勿在聊天中发送密钥。" + apply,
            values["stratz_token"],
            secret=True,
        ),
        "timeout_seconds": GsFloatConfig(
            "查询超时（秒）",
            "大于 0 且不超过 60 秒。" + apply,
            values["timeout_seconds"],
            min_value=0.01,
            max_value=60.0,
        ),
        "reply_mode": GsStrConfig(
            "回复方式",
            "image 图片卡片；text 纯文本。" + apply,
            values["reply_mode"],
            options=["image", "text"],
        ),
        "illustration_path": GsStrConfig(
            "自定义英雄素材目录",
            "留空使用托管素材；相对路径以 data/Dota2UID 为基准。" + apply,
            values["illustration_path"],
        ),
        "asset_download_mode": GsStrConfig(
            "素材下载方式",
            "auto 自动准备；manual 主人手动下载；off 关闭下载。" + apply,
            values["asset_download_mode"],
            options=["auto", "manual", "off"],
        ),
        "asset_proxy": GsStrConfig(
            "素材下载代理",
            "可留空；格式 http(s)://host:port，仅用于素材。" + apply,
            values["asset_proxy"],
            secret=True,
        ),
        "subscriptions_enabled": GsBoolConfig(
            "启用战绩订阅",
            "开启后按订阅设置检查新比赛。" + apply,
            values["subscriptions_enabled"],
        ),
        "subscription_interval_seconds": GsIntConfig(
            "订阅检查间隔（秒）",
            "范围 60–86400 秒。" + apply,
            values["subscription_interval_seconds"],
            max_value=86400,
        ),
        "daily_report_hour": GsIntConfig(
            "日报发送小时",
            "0–23，按北京时间 UTC+8 计算。" + apply,
            values["daily_report_hour"],
            max_value=23,
        ),
        "platforms": GsStrConfig(
            "平台映射（JSON）",
            'JSON 对象，例如 {"onebot":"qq","telegram":"telegram"}。' + apply,
            json.dumps(values["platforms"], ensure_ascii=False, sort_keys=True),
        ),
    }


class HostConfig:
    def __init__(self, native):
        self.native = native

    def snapshot(self):
        try:
            if not set(DEFAULTS) <= set(self.native.config):
                raise ConfigBridgeError()
            return {
                key: _typed_value(key, self.native.config[key].data, native=True)
                for key in DEFAULTS
            }
        except (OSError, ValueError, TypeError, AttributeError, KeyError, RecursionError):
            raise ConfigBridgeError() from None

    def set_config(self, key, value):
        if key not in DEFAULTS:
            return False
        try:
            value = _semantic_value(key, value)
        except (ConfigBridgeError, ValueError, TypeError, OverflowError, RecursionError):
            return False
        previous = self.native.config[key].data
        try:
            # Call the SDK class method directly; repeated reloads never stack old wrappers.
            result = StringConfig.set_config(self.native, key, value)
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            self.native.config[key].data = previous
            return False
        if not result:
            self.native.config[key].data = previous
        return bool(result)


def register_config(data_root: Path) -> HostConfig:
    previous = all_config_list.get("Dota2UID")
    previous_state = dict(previous.__dict__) if previous is not None else None
    constructing = False
    try:
        path = data_root / "config.json"
        if path.exists():
            _check_native(path)
            values = dict(DEFAULTS)
        else:
            values = _legacy_values(data_root / "config.toml")
        data_root.mkdir(parents=True, exist_ok=True)
        # Keep this construction in the generated plugin file for SDK ownership detection.
        constructing = True
        native = StringConfig("Dota2UID", path, _fields(values))
        bridge = HostConfig(native)
        native.set_config = bridge.set_config
        return bridge
    except (
        ConfigBridgeError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        RecursionError,
    ):
        if constructing:
            if previous is None:
                all_config_list.pop("Dota2UID", None)
            else:
                previous.__dict__.clear()
                previous.__dict__.update(previous_state)
        raise ConfigBridgeError() from None
