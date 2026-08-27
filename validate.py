#!/usr/bin/env python3
"""
站点配置校验脚本

1. JSON Schema 校验：sites/api/ 与 sites/html/ 下所有 JSON 必须符合对应 schema（阻塞）
2. 语义检查：
   - 错误（不通过，exit 1）：重复站点 id
   - 警告（不阻塞；--strict 时视为错误）：
     - 站点 id 非小写 [a-z0-9_-]
     - 文件名与 id 不一致
     - HTML 字段配置中出现未知键（拼写错误检测）
     - 使用未知/废弃的过滤器名

用法：
    uv run python validate.py            # 常规校验
    uv run python validate.py --strict   # 警告也视为失败（CI 用）
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).parent / "sites" / "schema"
SITES_DIR = Path(__file__).parent / "sites"

# 后端实际生效的过滤器（src/app/sites/api_searcher.py _apply_filters）
KNOWN_FILTERS = {"regex", "re_search", "split", "replace", "strip", "appendleft", "querystring"}
# 历史兼容过滤器名（解析器容忍，值原样保留，不报错）
LEGACY_FILTERS = {"trim", "dateparse", "lstrip", "date_en_elapsed_parse"}

# HTML 种子字段配置允许的键（schema 声明 + 后端 html_searcher.py 实际读取的键）
HTML_FIELD_KEYS = {
    "selector", "xpath", "attribute", "text", "type", "value", "case", "inline",
    "contents", "remove", "optional", "default", "default_value", "default_value_format",
    "index", "join", "if_present", "replace", "transform", "template", "filters",
}

# API item_mapping / field_mapping 允许的键
API_FIELD_KEYS = {
    "source", "type", "method", "path", "body", "response_key", "value", "map",
    "transform", "filters", "selector", "attribute", "fields", "domains",
    "separator", "keep_unknown",
}

# 用户信息字段配置允许的键（config_html.py）
USER_INFO_FIELD_KEYS = {"selector", "attribute", "extract", "pattern", "values"}

ID_PATTERN = re.compile(r"^[a-z0-9_-]+$")

errors: list[str] = []
warnings: list[str] = []
legacy_files: set[str] = set()


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_registry() -> Registry:
    """加载本地 schema 并注册到 Registry，避免网络请求"""
    registry = Registry()
    for schema_file in SCHEMA_DIR.glob("*.json"):
        resource = Resource.from_contents(load_json(schema_file))
        registry = resource @ registry
    return registry


def validate_schema(json_path: Path, schema: dict, registry: Registry, filename: str) -> None:
    """JSON Schema 校验（阻塞错误）"""
    try:
        data = load_json(json_path)
    except json.JSONDecodeError as e:
        errors.append(f"{filename}: JSON 解析错误 — {e}")
        return

    validator = Draft202012Validator(schema, registry=registry)
    for err in validator.iter_errors(data):
        path = "/".join(str(p) for p in err.path) or "root"
        errors.append(f"{filename}: [{path}] {err.message}")


def check_duplicate_ids(sites: list[tuple[str, str, str]]) -> None:
    """跨 api/html 重复的站点 id（阻塞错误）"""
    counter = Counter(sid for _, _, sid in sites)
    for sid, count in counter.items():
        if count > 1:
            errors.append(f"站点 id 重复: {sid!r} 出现 {count} 次")


def check_id_and_filename(sites: list[tuple[str, str, str]]) -> None:
    """id 格式与文件名一致性（警告）"""
    for sub, fname, sid in sites:
        if not ID_PATTERN.fullmatch(sid):
            warnings.append(f"{sub}/{fname}.json: id {sid!r} 建议使用小写 [a-z0-9_-]（id 变更会影响已配置站点，谨慎处理）")
        if fname != sid:
            warnings.append(f"{sub}/{fname}.json: 文件名与 id 不一致（id={sid!r}），建议重命名为 {sid}.json")


def iter_field_configs(data: dict):
    """遍历 HTML 种子字段配置（fields / browse_fields / container_fields）"""
    torrents = data.get("html", {}).get("torrents", {})
    if not isinstance(torrents, dict):
        return
    for group in ("fields", "browse_fields", "container_fields"):
        cfg = torrents.get(group)
        if isinstance(cfg, dict):
            for fname, fc in cfg.items():
                if isinstance(fc, dict):
                    yield fname, fc


def check_html_field_keys(data: dict, filename: str) -> None:
    """HTML 种子字段配置未知键检测（捕获 defualt_value 类拼写错误）"""
    for fname, fc in iter_field_configs(data):
        unknown = set(fc) - HTML_FIELD_KEYS
        for key in sorted(unknown):
            warnings.append(f"{filename}: 字段 {fname!r} 未知配置键 {key!r}（拼写检查，参见 HTML_FIELD_KEYS）")


def check_filters(data: dict, filename: str) -> None:
    """过滤器名检查（未知/废弃提示）"""
    seen: Counter = Counter()
    for fname, fc in iter_field_configs(data):
        for f in fc.get("filters", []) or []:
            if isinstance(f, dict):
                seen[f.get("name", "")] += 1
            else:
                seen[f"<string:{f}>"] += 1
    for name, count in sorted(seen.items()):
        if not name:
            warnings.append(f"{filename}: filters 条目缺少 name（出现 {count} 次）")
        elif name.startswith("<string:"):
            warnings.append(f"{filename}: filters 使用了字符串形式 {name}，后端不支持，建议改为 {{'name': ...}} 对象")
        elif name in LEGACY_FILTERS:
            legacy_files.add(filename)
        elif name not in KNOWN_FILTERS:
            warnings.append(f"{filename}: 未知过滤器 {name!r}（{count} 处），可用: {', '.join(sorted(KNOWN_FILTERS))}")


def check_api_field_keys(data: dict, filename: str) -> None:
    """API item_mapping / user_info.field_mapping 未知键检测"""
    endpoints = data.get("api", {}).get("endpoints", {})
    if isinstance(endpoints, dict):
        for epname, ep in endpoints.items():
            if not isinstance(ep, dict):
                continue
            for fname, fc in (ep.get("response", {}).get("item_mapping", {}) or {}).items():
                if isinstance(fc, dict):
                    unknown = set(fc) - API_FIELD_KEYS
                    for key in sorted(unknown):
                        warnings.append(f"{filename}: endpoints.{epname} 字段 {fname!r} 未知配置键 {key!r}")
    user_info = data.get("user_info", {})
    if isinstance(user_info, dict):
        for fname, fc in (user_info.get("fields", {}) or {}).items():
            if isinstance(fc, dict):
                unknown = set(fc) - USER_INFO_FIELD_KEYS
                for key in sorted(unknown):
                    warnings.append(f"{filename}: user_info.fields.{fname} 未知配置键 {key!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexus Media 站点配置校验")
    parser.add_argument("--strict", action="store_true", help="将警告视为失败")
    args = parser.parse_args()

    print("=" * 50)
    print("站点配置 JSON Schema 校验")
    print("=" * 50)

    registry = build_registry()
    try:
        api_schema = load_json(SCHEMA_DIR / "site-api.schema.json")
        html_schema = load_json(SCHEMA_DIR / "site-html.schema.json")
    except Exception as e:
        print(f"加载 schema 失败: {e}")
        return 1

    sites: list[tuple[str, str, str]] = []
    total = 0

    for subdir, schema in (("api", api_schema), ("html", html_schema)):
        target_dir = SITES_DIR / subdir
        if not target_dir.exists():
            continue
        for fpath in sorted(target_dir.glob("*.json")):
            total += 1
            filename = f"{subdir}/{fpath.name}"
            try:
                data = load_json(fpath)
            except json.JSONDecodeError:
                data = {}
            validate_schema(fpath, schema, registry, filename)
            if data:
                sites.append((subdir, fpath.stem, str(data.get("id", ""))))
                if subdir == "html":
                    check_html_field_keys(data, filename)
                else:
                    check_api_field_keys(data, filename)
                check_filters(data, filename)

    check_duplicate_ids(sites)
    check_id_and_filename(sites)

    if legacy_files:
        warnings.append(
            f"{len(legacy_files)} 个文件使用了废弃过滤器（trim/dateparse 等），当前后端不生效，建议随站点改版清理"
        )

    print(f"共校验 {total} 个文件")

    if errors:
        print(f"发现 {len(errors)} 处错误:")
        for err in errors:
            print(f"  ✗ {err}")

    if warnings:
        print(f"发现 {len(warnings)} 处警告" + ("（--strict 时视为失败）" if not args.strict else "（--strict 生效）"))
        for warn in warnings:
            print(f"  ⚠ {warn}")

    if not errors and not warnings:
        print("全部通过 ✓")
        return 0
    if not errors and warnings and not args.strict:
        print("通过（存在警告）")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
