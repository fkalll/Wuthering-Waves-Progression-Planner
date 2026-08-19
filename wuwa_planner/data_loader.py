"""加载、校验并搜索本地《鸣潮》中文数据和图片资源。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ELEMENTS = {"冷凝", "热熔", "导电", "气动", "衍射", "湮灭"}
ELEMENT_FILTERS = ["全部", "冷凝", "热熔", "导电", "气动", "衍射", "湮灭"]
SOURCE_TYPES = {"official", "community_reference", "open_source_reference"}
SKILL_KEYS = {"normal", "skill", "forte", "liberation", "intro"}
BUILD_FIELDS = {
    "name", "role", "weapons", "echo_set", "cost_layout", "cost_layout_name",
    "main_echo", "main_stats", "substat_priority", "energy_regen_target",
    "skill_priority", "notes", "game_version", "source_ids",
}
EXPECTED_SIZES = {"character": [160, 160], "material": [64, 64], "echo": [96, 96]}


class DataValidationError(ValueError):
    """本地数据、跨文件引用或图片资源无效。"""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise DataValidationError(f"缺少数据文件：{path.name}") from exc
    except json.JSONDecodeError as exc:
        raise DataValidationError(
            f"JSON 格式错误：{path.name}（第 {exc.lineno} 行）"
        ) from exc
    except OSError as exc:
        raise DataValidationError(f"无法读取数据文件：{path.name}") from exc
    if not isinstance(data, dict):
        raise DataValidationError(f"数据文件顶层必须是对象：{path.name}")
    return data


def _require(data: Mapping[str, object], fields: set[str], context: str) -> None:
    missing = fields - set(data)
    if missing:
        raise DataValidationError(f"{context} 缺少字段：{', '.join(sorted(missing))}")


def _quantity(value: object, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DataValidationError(f"{context} 必须是非负整数")


def _chinese_visible(value: object, context: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DataValidationError(f"{context} 必须是非空中文文本")
    if re.search(r"[A-Za-z]", value):
        raise DataValidationError(f"{context} 含未本地化英文：{value}")


def _validate_assets(
    assets_data: Mapping[str, object], project_dir: Path
) -> Mapping[str, object]:
    assets = assets_data.get("assets")
    sizes = assets_data.get("category_sizes")
    if not isinstance(assets, dict) or not assets:
        raise DataValidationError("assets.json 缺少资源字典")
    if sizes != EXPECTED_SIZES:
        raise DataValidationError("资源分类尺寸必须是角色 160、材料 64、声骸 96")
    asset_root = (project_dir / "assets").resolve()
    seen_paths: set[Path] = set()
    for key, entry in assets.items():
        if not isinstance(key, str) or not key or not isinstance(entry, dict):
            raise DataValidationError(f"资源定义无效：{key}")
        _require(
            entry,
            {"category", "path", "source_url", "source", "downloaded_on", "size", "rights"},
            f"资源 {key}",
        )
        category = entry["category"]
        if category not in EXPECTED_SIZES or entry["size"] != EXPECTED_SIZES[category]:
            raise DataValidationError(f"资源 {key} 的类别或尺寸无效")
        path_text = entry["path"]
        if not isinstance(path_text, str):
            raise DataValidationError(f"资源 {key} 的路径无效")
        path = (project_dir / path_text).resolve()
        if asset_root not in path.parents or path.suffix.lower() != ".png":
            raise DataValidationError(f"资源 {key} 的路径越界或不是 PNG")
        if path in seen_paths:
            raise DataValidationError(f"资源路径重复：{path_text}")
        seen_paths.add(path)
        if not path.is_file() or path.stat().st_size == 0:
            raise DataValidationError(f"资源文件缺失：{path_text}")
        if not isinstance(entry["source_url"], str) or not entry["source_url"].startswith("https://"):
            raise DataValidationError(f"资源 {key} 缺少 HTTPS 原始地址")
    return assets


def _asset(
    assets: Mapping[str, object], key: object, category: str, context: str
) -> None:
    if not isinstance(key, str) or key not in assets:
        raise DataValidationError(f"{context} 引用了未知图片：{key}")
    entry = assets[key]
    if not isinstance(entry, Mapping) or entry.get("category") != category:
        raise DataValidationError(f"{context} 的图片类别错误：{key}")


def _material_costs(
    costs: object, items: Mapping[str, object], context: str
) -> None:
    if not isinstance(costs, dict):
        raise DataValidationError(f"{context} 的材料消耗必须是对象")
    for item_id, value in costs.items():
        if item_id not in items:
            raise DataValidationError(f"{context} 引用了未知材料：{item_id}")
        _quantity(value, f"{context} 的材料 {item_id}")


def _validate_curve(curve: Mapping[str, object], items: Mapping[str, object]) -> None:
    _require(
        curve,
        {
            "min_level", "max_level", "credit_per_exp", "cumulative_exp",
            "potion_values", "ascension_levels", "allowed_character_levels", "source_id",
        },
        "level_curve.json",
    )
    if curve["min_level"] != 1 or curve["max_level"] != 90:
        raise DataValidationError("角色等级曲线必须覆盖 1～90")
    if curve["allowed_character_levels"] != [1, 10, 20, 30, 40, 50, 60, 70, 80, 90]:
        raise DataValidationError("角色等级档位必须是 1、10、20……90")
    if curve["ascension_levels"] != [20, 40, 50, 60, 70, 80]:
        raise DataValidationError("角色突破节点无效")
    cumulative = curve["cumulative_exp"]
    if not isinstance(cumulative, dict) or set(cumulative) != {str(i) for i in range(1, 91)}:
        raise DataValidationError("累计经验必须连续包含 1～90 级")
    values = [cumulative[str(level)] for level in range(1, 91)]
    if values[0] != 0:
        raise DataValidationError("1 级累计经验必须为 0")
    for index, value in enumerate(values, 1):
        _quantity(value, f"{index} 级累计经验")
    if not all(left < right for left, right in zip(values, values[1:])):
        raise DataValidationError("累计经验必须严格递增")
    potions = curve["potion_values"]
    if not isinstance(potions, dict) or not potions:
        raise DataValidationError("共鸣促剂数据缺失")
    for item_id, value in potions.items():
        if item_id not in items or type(value) is not int or value <= 0:
            raise DataValidationError(f"共鸣促剂数据无效：{item_id}")


def validate_data(
    characters_data: Mapping[str, object],
    materials_data: Mapping[str, object],
    level_curve: Mapping[str, object],
    builds_data: Mapping[str, object],
    assets_data: Mapping[str, object],
    meta_data: Mapping[str, object],
    *,
    project_dir: Path = BASE_DIR,
) -> None:
    """验证 56 项数据、逐级技能、中文字段和全部本地资源引用。"""
    assets = _validate_assets(assets_data, project_dir)
    characters = characters_data.get("characters")
    items = materials_data.get("items")
    templates = materials_data.get("characters")
    builds = builds_data.get("characters")
    if not isinstance(characters, list) or len(characters) != 56:
        raise DataValidationError("characters.json 必须恰好包含 56 个战斗形态")
    if not isinstance(items, dict) or not items or not isinstance(templates, dict):
        raise DataValidationError("材料字典或角色材料模板缺失")
    if not isinstance(builds, dict):
        raise DataValidationError("角色配装数据缺失")

    for item_id, item in items.items():
        if not isinstance(item_id, str) or not isinstance(item, dict):
            raise DataValidationError(f"材料定义无效：{item_id}")
        _require(item, {"name", "category", "asset_key"}, f"材料 {item_id}")
        _chinese_visible(item["name"], f"材料 {item_id} 名称")
        _chinese_visible(item["category"], f"材料 {item_id} 类别")
        _asset(assets, item["asset_key"], "material", f"材料 {item_id}")
    _validate_curve(level_curve, items)

    ids: set[str] = set()
    names: set[str] = set()
    used_templates: set[str] = set()
    character_fields = {
        "id", "name", "aliases", "rarity", "element", "weapon_type", "role",
        "release_version", "materials_key", "builds_key", "asset_key",
    }
    for index, character in enumerate(characters):
        if not isinstance(character, dict):
            raise DataValidationError(f"第 {index + 1} 个角色格式错误")
        _require(character, character_fields, f"第 {index + 1} 个角色")
        character_id, name = character["id"], character["name"]
        if not isinstance(character_id, str) or not character_id or character_id in ids:
            raise DataValidationError(f"角色 ID 无效或重复：{character_id}")
        _chinese_visible(name, f"角色 {character_id} 名称")
        if name in names:
            raise DataValidationError(f"角色名称重复：{name}")
        ids.add(character_id); names.add(name)
        aliases = character["aliases"]
        if not isinstance(aliases, list) or not all(isinstance(value, str) and value for value in aliases):
            raise DataValidationError(f"角色 {name} 别名格式错误")
        if character["element"] not in ELEMENTS:
            raise DataValidationError(f"角色 {name} 属性无效")
        for field in ("weapon_type", "role"):
            _chinese_visible(character[field], f"角色 {name} 的 {field}")
        material_key, build_key = character["materials_key"], character["builds_key"]
        if material_key not in templates or build_key not in builds:
            raise DataValidationError(f"角色 {name} 的材料或配装引用无效")
        used_templates.add(str(material_key))
        _asset(assets, character["asset_key"], "character", f"角色 {name}")
    if set(builds) != ids or set(templates) != used_templates:
        raise DataValidationError("角色、材料模板和配装引用范围不一致")
    if {character["element"] for character in characters} != ELEMENTS:
        raise DataValidationError("角色名单必须覆盖六种伤害属性")

    for key, template in templates.items():
        if not isinstance(template, dict):
            raise DataValidationError(f"角色材料模板格式错误：{key}")
        _require(template, {"ascensions", "skills", "skill_tree_nodes"}, f"角色 {key} 材料")
        ascensions = template["ascensions"]
        if not isinstance(ascensions, list) or len(ascensions) != 6:
            raise DataValidationError(f"角色 {key} 必须有 6 个突破阶段")
        if [stage.get("unlock_level") for stage in ascensions if isinstance(stage, dict)] != [20, 40, 50, 60, 70, 80]:
            raise DataValidationError(f"角色 {key} 的突破节点无效")
        for stage in ascensions:
            if not isinstance(stage, dict):
                raise DataValidationError(f"角色 {key} 的突破阶段无效")
            _require(stage, {"stage", "unlock_level", "level_cap", "costs"}, f"角色 {key} 突破")
            _material_costs(stage["costs"], items, f"角色 {key} 突破")
        skills = template["skills"]
        if not isinstance(skills, dict) or set(skills) != SKILL_KEYS:
            raise DataValidationError(f"角色 {key} 必须包含五项技能")
        for skill_key, skill in skills.items():
            if not isinstance(skill, dict):
                raise DataValidationError(f"角色 {key} 技能 {skill_key} 无效")
            _require(skill, {"name", "levels"}, f"角色 {key} 技能 {skill_key}")
            _chinese_visible(skill["name"], f"角色 {key} 技能名")
            levels = skill["levels"]
            if not isinstance(levels, dict) or set(levels) != {str(i) for i in range(1, 11)}:
                raise DataValidationError(f"角色 {key} 技能 {skill_key} 必须连续覆盖 1～10")
            for level, costs in levels.items():
                _material_costs(costs, items, f"角色 {key} 技能 {skill_key} {level} 级")
        nodes = template["skill_tree_nodes"]
        if not isinstance(nodes, list) or len(nodes) != 10:
            raise DataValidationError(f"角色 {key} 必须有 10 个独立技能树节点")
        for node in nodes:
            if not isinstance(node, dict):
                raise DataValidationError(f"角色 {key} 技能树节点无效")
            _require(node, {"name", "costs"}, f"角色 {key} 技能树")
            _chinese_visible(node["name"], f"角色 {key} 技能树节点名")
            _material_costs(node["costs"], items, f"角色 {key} 技能树")

    sources = meta_data.get("sources")
    version = meta_data.get("game_version")
    if version != "3.5" or not isinstance(sources, list) or not sources:
        raise DataValidationError("meta.json 必须提供 3.5 版本和来源")
    source_ids: set[str] = set()
    source_types: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise DataValidationError("资料来源格式错误")
        _require(source, {"id", "type", "title", "url", "usage"}, "资料来源")
        source_id = source["id"]
        if source["type"] not in SOURCE_TYPES or not isinstance(source_id, str) or source_id in source_ids:
            raise DataValidationError(f"资料来源类型或 ID 无效：{source_id}")
        source_ids.add(source_id); source_types.add(source["type"])
    if source_types != SOURCE_TYPES or level_curve["source_id"] not in source_ids:
        raise DataValidationError("资料来源类型或等级曲线来源不完整")

    for character_id, character_builds in builds.items():
        if not isinstance(character_builds, list) or not character_builds:
            raise DataValidationError(f"角色 {character_id} 至少需要一套配装")
        for build in character_builds:
            if not isinstance(build, dict):
                raise DataValidationError(f"角色 {character_id} 配装格式错误")
            _require(build, BUILD_FIELDS, f"角色 {character_id} 配装")
            for field in ("name", "role", "echo_set", "cost_layout_name", "notes", "energy_regen_target"):
                _chinese_visible(build[field], f"角色 {character_id} 配装 {field}")
            for field in ("weapons", "substat_priority", "skill_priority"):
                values = build[field]
                if not isinstance(values, list) or not values:
                    raise DataValidationError(f"角色 {character_id} 配装 {field} 为空")
                for value in values:
                    _chinese_visible(value, f"角色 {character_id} 配装 {field}")
            main_stats = build["main_stats"]
            if not isinstance(main_stats, dict) or not main_stats:
                raise DataValidationError(f"角色 {character_id} 主词条为空")
            for label, value in main_stats.items():
                _chinese_visible(label, f"角色 {character_id} 主词条标签")
                _chinese_visible(value, f"角色 {character_id} 主词条")
            main_echo = build["main_echo"]
            if not isinstance(main_echo, dict):
                raise DataValidationError(f"角色 {character_id} 主声骸无效")
            _require(main_echo, {"id", "name", "asset_key"}, f"角色 {character_id} 主声骸")
            _chinese_visible(main_echo["name"], f"角色 {character_id} 主声骸名称")
            _asset(assets, main_echo["asset_key"], "echo", f"角色 {character_id} 主声骸")
            source_refs = build["source_ids"]
            if not isinstance(source_refs, list) or not source_refs:
                raise DataValidationError(f"角色 {character_id} 配装来源为空")
            unknown = set(source_refs) - source_ids
            if unknown:
                raise DataValidationError(f"角色 {character_id} 配装引用未知来源：{', '.join(sorted(unknown))}")


def load_all_data(data_dir: Path | None = None) -> dict[str, Any]:
    """读取全部离线数据，验证后返回 GUI 使用的统一结构。"""
    directory = Path(data_dir) if data_dir is not None else DATA_DIR
    project_dir = directory.parent
    characters = _load_json(directory / "characters.json")
    materials = _load_json(directory / "materials.json")
    curve = _load_json(directory / "level_curve.json")
    builds = _load_json(directory / "builds.json")
    assets = _load_json(directory / "assets.json")
    meta = _load_json(directory / "meta.json")
    validate_data(
        characters, materials, curve, builds, assets, meta, project_dir=project_dir
    )
    return {
        "characters": characters["characters"],
        "materials": materials,
        "level_curve": curve,
        "builds": builds["characters"],
        "assets": assets["assets"],
        "meta": meta,
        "project_dir": project_dir,
    }


def search_characters(
    characters: list[Mapping[str, object]], query: str, element: str = "全部"
) -> list[Mapping[str, object]]:
    """按文字与伤害属性取交集进行本地搜索。"""
    if element not in ELEMENT_FILTERS:
        raise ValueError(f"未知伤害属性：{element}")
    keyword = query.strip().casefold()
    results: list[Mapping[str, object]] = []
    for character in characters:
        if element != "全部" and character.get("element") != element:
            continue
        aliases = character.get("aliases", [])
        fields = [
            character.get("name", ""), character.get("element", ""),
            character.get("weapon_type", ""), character.get("role", ""),
        ]
        if isinstance(aliases, list):
            fields.extend(aliases)
        if not keyword or keyword in " ".join(str(value) for value in fields).casefold():
            results.append(character)
    return results
