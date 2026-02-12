from __future__ import annotations

import os
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


XHTML_PLACEHOLDER = "__XHTML__"


class ProfileConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileMappingRoute:
    pattern: str
    mapping: str

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        target = parsed.path or url
        return re.match(self.pattern, target) is not None


@dataclass(frozen=True)
class ProfileDefinition:
    name: str
    inherit: str | None
    api_key: str | None
    mapping_mode: str
    strict_mapping: bool
    mapping: str
    templates_dir: str
    mappings_dir: str
    routes: tuple[ProfileMappingRoute, ...]
    settings: dict[str, Any]

    def resolve_mapping(self, url: str) -> str:
        for route in self.routes:
            if route.matches(url):
                return route.mapping
        return self.mapping


@dataclass(frozen=True)
class ProfileConfig:
    profiles: dict[str, ProfileDefinition]

    def get(self, name: str) -> ProfileDefinition:
        if name not in self.profiles:
            raise ProfileConfigError(f"Unknown profile: {name}")
        return self.profiles[name]


ENV_PARSERS: dict[str, Callable[[str], Any]] = {
    "api_url": str,
    "sitemap_url": str,
    "sitemap_url_pattern": str,
    "sheets_url": str,
    "sheets_name": str,
    "sheets_service_account": str,
    "urls": lambda v: [u.strip() for u in re.split(r"[\n,]", v) if u.strip()],
    "overwrite": lambda v: v.strip().lower() in {"1", "true", "yes", "on"},
    "concurrency": lambda v: int(v.strip()),
    "web_page_import_write_strategy": str,
    "web_page_types": lambda v: [s.strip() for s in v.split(",") if s.strip()],
    "embedding_properties": lambda v: [s.strip() for s in v.split(",") if s.strip()],
    "web_page_import_mode": str,
    "web_page_import_render_js": lambda v: v.strip().lower()
    in {"1", "true", "yes", "on"},
    "web_page_import_wait_for": str,
    "web_page_import_country_code": str,
    "web_page_import_premium_proxy": lambda v: v.strip().lower()
    in {"1", "true", "yes", "on"},
    "web_page_import_block_ads": lambda v: v.strip().lower()
    in {"1", "true", "yes", "on"},
    "web_page_import_timeout": lambda v: int(v.strip()),
    "google_search_console": lambda v: v.strip().lower() in {"1", "true", "yes", "on"},
    "service_account_file": str,
}


INTERPOLATION_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _deep_merge(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(parent)
    for key, value in child.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _interpolate(
    value: Any, env: dict[str, str], strict: bool, profile_name: str
) -> Any:
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            env_key = match.group(1)
            env_value = env.get(env_key)
            if env_value is None:
                if strict:
                    raise ProfileConfigError(
                        f"Missing environment variable '{env_key}' for profile '{profile_name}'."
                    )
                return ""
            return env_value

        return INTERPOLATION_PATTERN.sub(repl, value)

    if isinstance(value, list):
        return [_interpolate(v, env, strict, profile_name) for v in value]

    if isinstance(value, dict):
        return {k: _interpolate(v, env, strict, profile_name) for k, v in value.items()}

    return value


def _apply_env_fallbacks(raw: dict[str, Any], env: dict[str, str]) -> None:
    for key, parser in ENV_PARSERS.items():
        if key in raw:
            continue
        env_key = key.upper()
        env_value = env.get(env_key)
        if env_value is None:
            continue
        raw[key] = parser(env_value)

    if "api_url" not in raw:
        raw["api_url"] = env.get("API_URL", "https://api.wordlift.io")


def _normalize_runtime_setting_types(raw: dict[str, Any], profile_name: str) -> None:
    for key, parser in ENV_PARSERS.items():
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, str):
            try:
                raw[key] = parser(value)
            except Exception as exc:
                raise ProfileConfigError(
                    f"Profile '{profile_name}': invalid value for '{key}': {value}"
                ) from exc


def _build_routes(
    raw: dict[str, Any], profile_name: str
) -> tuple[ProfileMappingRoute, ...]:
    routes: list[ProfileMappingRoute] = []
    mappings = raw.get("mappings")

    if mappings is not None:
        if not isinstance(mappings, list):
            raise ProfileConfigError(
                f"Profile '{profile_name}': 'mappings' must be an array of tables."
            )
        for route in mappings:
            if not isinstance(route, dict):
                raise ProfileConfigError(
                    f"Profile '{profile_name}': each mapping route must be a table."
                )
            pattern = route.get("pattern")
            mapping = route.get("mapping")
            if not pattern or not mapping:
                raise ProfileConfigError(
                    f"Profile '{profile_name}': each mapping route requires 'pattern' and 'mapping'."
                )
            routes.append(ProfileMappingRoute(pattern=pattern, mapping=mapping))

    if not routes:
        routes.append(ProfileMappingRoute(pattern=".*", mapping=raw["mapping"]))
    elif not any(r.pattern == ".*" for r in routes):
        routes.append(ProfileMappingRoute(pattern=".*", mapping=raw["mapping"]))

    return tuple(routes)


def _profile_defaults(name: str, raw: dict[str, Any], has_base: bool) -> dict[str, Any]:
    result = deepcopy(raw)

    if name != "_base":
        result.setdefault("inherit", "_base" if has_base else None)
        result.setdefault("mapping", "default.yarrrml")
        result.setdefault("templates_dir", f"profiles/{name}/templates")
        result.setdefault("mappings_dir", f"profiles/{name}/mappings")
    else:
        result.setdefault("mapping", "default.yarrrml")

    result.setdefault("mapping_mode", "xpath")
    result.setdefault("strict_mapping", True)

    return result


def load_profile_config(
    config_path: Path | str, env: dict[str, str] | None = None
) -> ProfileConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "rb") as f:
        doc = tomllib.load(f)

    raw_profiles = doc.get("profiles", {})
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise ProfileConfigError(
            "worai.toml must define a non-empty [profiles] section."
        )

    env_dict = dict(os.environ)
    if env is not None:
        env_dict.update(env)

    has_base = "_base" in raw_profiles
    cache: dict[str, dict[str, Any]] = {}

    def resolve_raw(name: str, stack: list[str]) -> dict[str, Any]:
        if name in cache:
            return deepcopy(cache[name])
        if name not in raw_profiles:
            raise ProfileConfigError(f"Profile '{name}' not found.")
        if name in stack:
            chain = " -> ".join(stack + [name])
            raise ProfileConfigError(f"Profile inheritance cycle detected: {chain}")

        node = raw_profiles[name]
        if not isinstance(node, dict):
            raise ProfileConfigError(f"Profile '{name}' must be a TOML table.")

        prepared = _profile_defaults(name, node, has_base)
        parent_name = prepared.get("inherit")

        if parent_name:
            parent = resolve_raw(parent_name, stack + [name])
            merged = _deep_merge(parent, prepared)
        else:
            merged = prepared

        cache[name] = deepcopy(merged)
        return merged

    resolved_profiles: dict[str, ProfileDefinition] = {}
    for name in raw_profiles:
        merged = resolve_raw(name, [])
        strict = bool(merged.get("strict_mapping", True))
        merged = _interpolate(merged, env_dict, strict, name)
        _apply_env_fallbacks(merged, env_dict)
        _normalize_runtime_setting_types(merged, name)

        mapping_mode = str(merged.get("mapping_mode", "xpath")).strip().lower()
        if mapping_mode != "xpath":
            raise ProfileConfigError(
                f"Profile '{name}': only mapping_mode='xpath' is supported. Got '{mapping_mode}'."
            )

        routes = _build_routes(merged, name)

        settings = {key: merged[key] for key in ENV_PARSERS if key in merged}
        settings["api_url"] = merged.get("api_url", "https://api.wordlift.io")

        resolved_profiles[name] = ProfileDefinition(
            name=name,
            inherit=merged.get("inherit"),
            api_key=merged.get("api_key"),
            mapping_mode="xpath",
            strict_mapping=bool(merged.get("strict_mapping", True)),
            mapping=str(merged.get("mapping", "default.yarrrml")),
            templates_dir=str(
                merged.get("templates_dir", f"profiles/{name}/templates")
            ),
            mappings_dir=str(merged.get("mappings_dir", f"profiles/{name}/mappings")),
            routes=routes,
            settings=settings,
        )

    return ProfileConfig(profiles=resolved_profiles)
