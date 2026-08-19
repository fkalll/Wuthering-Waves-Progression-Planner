"""角色十级档位、五项技能区间与材料展示的纯计算逻辑。"""

from __future__ import annotations

import math
from collections.abc import Mapping


VALID_MODES = {"level", "skills", "total"}
CATEGORY_ORDER = {
    "货币": 0,
    "角色经验": 1,
    "区域特产": 2,
    "突破首领材料": 3,
    "残象掉落": 4,
    "凝素领域材料": 5,
    "周本材料": 6,
    "材料": 7,
}


def merge_materials(*groups: Mapping[str, int]) -> dict[str, int]:
    """合并若干材料数量，不修改输入对象。"""
    merged: dict[str, int] = {}
    for group in groups:
        for item_id, quantity in group.items():
            merged[item_id] = merged.get(item_id, 0) + quantity
    return merged


def _material_template(
    materials_data: Mapping[str, object], character_key: str
) -> Mapping[str, object]:
    characters = materials_data.get("characters")
    if not isinstance(characters, Mapping) or character_key not in characters:
        raise KeyError(f"找不到角色材料：{character_key}")
    template = characters[character_key]
    if not isinstance(template, Mapping):
        raise TypeError(f"角色材料格式错误：{character_key}")
    return template


def _validate_character_levels(
    level_curve: Mapping[str, object], current_level: int, target_level: int
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    if isinstance(current_level, bool) or not isinstance(current_level, int):
        raise ValueError("当前角色等级必须是整数档位")
    if isinstance(target_level, bool) or not isinstance(target_level, int):
        raise ValueError("目标角色等级必须是整数档位")
    allowed = level_curve.get("allowed_character_levels")
    if not isinstance(allowed, list) or not all(type(value) is int for value in allowed):
        raise ValueError("角色等级档位配置无效")
    if current_level not in allowed or target_level not in allowed:
        choices = "/".join(str(value) for value in allowed)
        raise ValueError(f"角色等级只能选择这些档位：{choices}")
    if current_level >= target_level:
        raise ValueError("当前角色等级必须低于目标角色等级")
    cumulative = level_curve.get("cumulative_exp")
    potions = level_curve.get("potion_values")
    if not isinstance(cumulative, Mapping) or not isinstance(potions, Mapping):
        raise ValueError("角色等级曲线数据不完整")
    return cumulative, potions


def _validate_skill_levels(current_level: int, target_level: int) -> None:
    if isinstance(current_level, bool) or not isinstance(current_level, int):
        raise ValueError("当前技能等级必须是 1～9 的整数")
    if isinstance(target_level, bool) or not isinstance(target_level, int):
        raise ValueError("目标技能等级必须是 2～10 的整数")
    if not 1 <= current_level < target_level <= 10:
        raise ValueError("技能等级必须满足 1 ≤ 当前等级 < 目标等级 ≤ 10")


def suggest_exp_potions(
    required_exp: int, potion_values: Mapping[str, object]
) -> tuple[dict[str, int], int]:
    """依次最小化经验溢出和道具数量。"""
    if required_exp < 0:
        raise ValueError("所需经验不能为负数")
    values: list[tuple[str, int]] = []
    for item_id, raw_value in potion_values.items():
        if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value <= 0:
            raise ValueError(f"促剂 {item_id} 的经验值无效")
        values.append((str(item_id), raw_value))
    if not values or required_exp == 0:
        return {}, 0

    unit = math.gcd(*(value for _, value in values))
    required_units = math.ceil(required_exp / unit)
    coins = [(item_id, value // unit) for item_id, value in values]
    limit = required_units + max(value for _, value in coins)
    best: list[tuple[int, dict[str, int]] | None] = [None] * (limit + 1)
    best[0] = (0, {})
    for total in range(1, limit + 1):
        candidate: tuple[int, dict[str, int]] | None = None
        for item_id, value in coins:
            if total < value or best[total - value] is None:
                continue
            previous_count, previous_items = best[total - value]
            counts = dict(previous_items)
            counts[item_id] = counts.get(item_id, 0) + 1
            option = (previous_count + 1, counts)
            if candidate is None or option[0] < candidate[0]:
                candidate = option
        best[total] = candidate
    for total in range(required_units, limit + 1):
        if best[total] is not None:
            return best[total][1], total * unit - required_exp
    raise ValueError("无法生成共鸣促剂建议")


def calculate_level_details(
    materials_data: Mapping[str, object],
    level_curve: Mapping[str, object],
    character_key: str,
    current_level: int,
    target_level: int,
) -> dict[str, object]:
    """计算角色等级档位区间的经验、贝币、促剂和突破材料。"""
    cumulative, potion_values = _validate_character_levels(
        level_curve, current_level, target_level
    )
    template = _material_template(materials_data, character_key)
    ascensions = template.get("ascensions")
    if not isinstance(ascensions, list):
        raise TypeError(f"角色突破数据格式错误：{character_key}")

    required_exp = int(cumulative[str(target_level)]) - int(
        cumulative[str(current_level)]
    )
    rate = level_curve.get("credit_per_exp")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
        raise ValueError("升级贝币换算比例无效")
    leveling_credits = math.ceil(required_exp * rate)
    totals: dict[str, int] = {"2": leveling_credits}
    potion_counts, overflow = suggest_exp_potions(required_exp, potion_values)
    totals = merge_materials(totals, potion_counts)

    crossed: list[int] = []
    for stage in ascensions:
        if not isinstance(stage, Mapping):
            raise TypeError(f"角色突破阶段格式错误：{character_key}")
        unlock = stage.get("unlock_level")
        costs = stage.get("costs")
        if isinstance(unlock, int) and current_level <= unlock < target_level:
            if not isinstance(costs, Mapping):
                raise TypeError(f"角色突破消耗格式错误：{character_key}")
            totals = merge_materials(totals, costs)
            crossed.append(unlock)

    potion_exp = sum(
        int(potion_values[item_id]) * count
        for item_id, count in potion_counts.items()
    )
    return {
        "materials": totals,
        "required_exp": required_exp,
        "leveling_credits": leveling_credits,
        "potion_exp": potion_exp,
        "overflow_exp": overflow,
        "crossed_ascensions": crossed,
    }


def calculate_skill_materials(
    materials_data: Mapping[str, object],
    character_key: str,
    current_level: int,
    target_level: int,
    *,
    include_skill_tree: bool = True,
) -> dict[str, int]:
    """统一计算五项技能的同一 1～10 级区间，可独立计入技能树。"""
    _validate_skill_levels(current_level, target_level)
    if not isinstance(include_skill_tree, bool):
        raise ValueError("技能树选项必须是布尔值")
    template = _material_template(materials_data, character_key)
    skills = template.get("skills")
    if not isinstance(skills, Mapping) or len(skills) != 5:
        raise TypeError(f"角色五项技能数据格式错误：{character_key}")

    totals: dict[str, int] = {}
    for skill in skills.values():
        if not isinstance(skill, Mapping) or not isinstance(skill.get("levels"), Mapping):
            raise TypeError(f"角色逐级技能数据格式错误：{character_key}")
        levels = skill["levels"]
        assert isinstance(levels, Mapping)
        for level in range(current_level + 1, target_level + 1):
            costs = levels.get(str(level))
            if not isinstance(costs, Mapping):
                raise TypeError(f"角色技能 {level} 级消耗缺失：{character_key}")
            totals = merge_materials(totals, costs)

    if include_skill_tree:
        nodes = template.get("skill_tree_nodes")
        if not isinstance(nodes, list):
            raise TypeError(f"角色技能树数据格式错误：{character_key}")
        for node in nodes:
            if not isinstance(node, Mapping) or not isinstance(node.get("costs"), Mapping):
                raise TypeError(f"角色技能树节点格式错误：{character_key}")
            totals = merge_materials(totals, node["costs"])
    return totals


def calculate_materials(
    materials_data: Mapping[str, object],
    character_key: str,
    mode: str = "total",
    *,
    level_curve: Mapping[str, object] | None = None,
    current_level: int = 1,
    target_level: int = 90,
    current_skill_level: int = 1,
    target_skill_level: int = 10,
    include_skill_tree: bool = True,
) -> dict[str, int]:
    """按角色等级、技能等级或二者合计返回材料。"""
    if mode not in VALID_MODES:
        raise ValueError(f"未知计算模式：{mode}")
    _ = _material_template(materials_data, character_key)

    skills: dict[str, int] | None = None
    level: dict[str, int] | None = None
    if mode in {"skills", "total"}:
        skills = calculate_skill_materials(
            materials_data,
            character_key,
            current_skill_level,
            target_skill_level,
            include_skill_tree=include_skill_tree,
        )
    if mode in {"level", "total"}:
        if level_curve is None:
            raise ValueError("计算角色等级时必须提供等级曲线")
        result = calculate_level_details(
            materials_data, level_curve, character_key, current_level, target_level
        )["materials"]
        if not isinstance(result, Mapping):
            raise TypeError("角色等级材料结果格式错误")
        level = dict(result)
    if mode == "skills":
        return skills or {}
    if mode == "level":
        return level or {}
    return merge_materials(level or {}, skills or {})


def material_rows(
    materials_data: Mapping[str, object], totals: Mapping[str, int]
) -> list[dict[str, object]]:
    """转换为带中文名称、类别与图片键的表格行。"""
    items = materials_data.get("items")
    if not isinstance(items, Mapping):
        raise TypeError("材料字典格式错误")
    rows: list[dict[str, object]] = []
    for item_id, quantity in totals.items():
        item = items[item_id]
        if not isinstance(item, Mapping):
            raise TypeError(f"材料定义格式错误：{item_id}")
        rows.append(
            {
                "id": item_id,
                "name": item["name"],
                "category": item["category"],
                "asset_key": item["asset_key"],
                "quantity": quantity,
            }
        )
    rows.sort(
        key=lambda row: (
            CATEGORY_ORDER.get(str(row["category"]), 99),
            str(row["name"]),
        )
    )
    return rows
