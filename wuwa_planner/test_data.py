"""56 项中文数据、逐级技能、图片资源与搜索测试。"""

from __future__ import annotations

import copy
import re
import unittest
from pathlib import Path

from PIL import Image

from data_loader import (
    BUILD_FIELDS,
    ELEMENTS,
    DataValidationError,
    load_all_data,
    search_characters,
    validate_data,
)

EXPECTED_NAMES = {
    "维里奈", "秋水", "秧秧", "鉴心", "渊武", "卡卡罗", "炽霞", "莫特斐",
    "安可", "白芷", "散华", "凌阳", "忌炎", "吟霖", "桃祈", "丹瑾",
    "漂泊者・衍射", "漂泊者・湮灭", "今汐", "长离", "折枝", "相里要",
    "守岸人", "釉瑚", "椿", "灯灯", "珂莱塔", "洛可可", "菲比", "布兰特",
    "坎特蕾拉", "漂泊者・气动", "赞妮", "夏空", "卡提希娅", "露帕",
    "弗洛洛", "奥古斯塔", "尤诺", "嘉贝莉娜", "仇远", "千咲", "卜灵",
    "琳奈", "莫宁", "爱弥斯", "陆・赫斯", "西格莉卡", "绯雪", "达妮娅",
    "露西", "丽贝卡", "露西拉", "秧秧・玄翎", "穗穗", "漂泊者・导电",
}


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_all_data()
        cls.project_dir = Path(cls.data["project_dir"])

    def _raw_documents(self):
        return (
            {"characters": copy.deepcopy(self.data["characters"])},
            copy.deepcopy(self.data["materials"]),
            copy.deepcopy(self.data["level_curve"]),
            {"characters": copy.deepcopy(self.data["builds"])},
            {"assets": copy.deepcopy(self.data["assets"]),
             "category_sizes": {"character": [160, 160], "material": [64, 64], "echo": [96, 96]}},
            copy.deepcopy(self.data["meta"]),
        )

    def test_fixed_35_roster_has_56_unique_forms(self) -> None:
        characters = self.data["characters"]
        self.assertEqual({character["name"] for character in characters}, EXPECTED_NAMES)
        self.assertEqual(len(characters), 56)
        self.assertEqual(len({character["id"] for character in characters}), 56)
        self.assertEqual(
            len(
                [
                    character
                    for character in characters
                    if character["name"].startswith("漂泊者・")
                ]
            ),
            4,
        )

    def test_all_six_elements_and_cross_file_references(self) -> None:
        self.assertEqual(
            {character["element"] for character in self.data["characters"]},
            ELEMENTS,
        )
        for character in self.data["characters"]:
            self.assertIn(
                character["materials_key"], self.data["materials"]["characters"]
            )
            self.assertIn(character["builds_key"], self.data["builds"])
            self.assertIn(character["asset_key"], self.data["assets"])

    def test_all_material_names_and_build_content_are_chinese(self) -> None:
        latin = re.compile(r"[A-Za-z]")
        for item in self.data["materials"]["items"].values():
            self.assertIsNone(latin.search(item["name"]), item["name"])
            self.assertIsNone(latin.search(item["category"]), item["category"])
        for character in self.data["characters"]:
            self.assertIsNone(latin.search(character["name"]), character["name"])
            for build in self.data["builds"][character["builds_key"]]:
                visible = [
                    build["name"], build["role"], build["echo_set"],
                    build["main_echo"]["name"], build["cost_layout_name"],
                    build["notes"], build["energy_regen_target"],
                    *build["weapons"], *build["substat_priority"],
                    *build["skill_priority"], *build["main_stats"].keys(),
                    *build["main_stats"].values(),
                ]
                for value in visible:
                    self.assertIsNone(latin.search(value), value)

    def test_every_material_template_has_five_continuous_skills(self) -> None:
        items = self.data["materials"]["items"]
        for key, template in self.data["materials"]["characters"].items():
            with self.subTest(character=key):
                self.assertEqual(
                    [stage["unlock_level"] for stage in template["ascensions"]],
                    [20, 40, 50, 60, 70, 80],
                )
                self.assertEqual(
                    set(template["skills"]),
                    {"normal", "skill", "forte", "liberation", "intro"},
                )
                for skill in template["skills"].values():
                    self.assertEqual(
                        set(skill["levels"]), {str(level) for level in range(1, 11)}
                    )
                    for costs in skill["levels"].values():
                        self.assertTrue(set(costs) <= set(items))
                self.assertEqual(len(template["skill_tree_nodes"]), 10)
                for node in template["skill_tree_nodes"]:
                    self.assertTrue(node["costs"])
                    self.assertTrue(set(node["costs"]) <= set(items))

    def test_every_character_has_complete_build_and_echo_asset(self) -> None:
        for character in self.data["characters"]:
            for build in self.data["builds"][character["builds_key"]]:
                self.assertTrue(BUILD_FIELDS <= set(build))
                self.assertEqual(build["game_version"], "3.5")
                self.assertIn(build["main_echo"]["asset_key"], self.data["assets"])
                self.assertEqual(
                    self.data["assets"][build["main_echo"]["asset_key"]]["category"],
                    "echo",
                )

    def test_asset_manifest_counts_files_and_dimensions(self) -> None:
        assets = self.data["assets"]
        counts = {
            category: sum(
                entry["category"] == category for entry in assets.values()
            )
            for category in ("character", "material", "echo")
        }
        self.assertEqual(counts, {"character": 56, "material": 147, "echo": 23})
        expected = {"character": (160, 160), "material": (64, 64), "echo": (96, 96)}
        for key, entry in assets.items():
            with self.subTest(asset=key):
                path = self.project_dir / entry["path"]
                self.assertTrue(path.is_file())
                with Image.open(path) as image:
                    image.load()
                    self.assertEqual(image.format, "PNG")
                    self.assertEqual(image.size, expected[entry["category"]])

    def test_level_curve_uses_ten_level_choices_but_keeps_exact_curve(self) -> None:
        curve = self.data["level_curve"]
        self.assertEqual(
            curve["allowed_character_levels"],
            [1, 10, 20, 30, 40, 50, 60, 70, 80, 90],
        )
        self.assertEqual(
            set(curve["cumulative_exp"]), {str(level) for level in range(1, 91)}
        )
        self.assertEqual(curve["cumulative_exp"]["90"], 2_438_000)

    def test_search_and_element_filter_intersection(self) -> None:
        characters = self.data["characters"]
        self.assertEqual(
            [item["name"] for item in search_characters(characters, "JINHSI")],
            ["今汐"],
        )
        self.assertEqual(
            [item["name"] for item in search_characters(characters, "将军")],
            ["忌炎"],
        )
        electro = search_characters(characters, "", "导电")
        self.assertTrue(electro)
        self.assertTrue(all(item["element"] == "导电" for item in electro))
        pistol_fusion = search_characters(characters, "佩枪", "热熔")
        self.assertTrue(pistol_fusion)
        self.assertTrue(
            all(
                item["weapon_type"] == "佩枪" and item["element"] == "热熔"
                for item in pistol_fusion
            )
        )
        self.assertEqual(search_characters(characters, "今汐", "热熔"), [])
        self.assertEqual(len(search_characters(characters, "", "全部")), 56)

    def test_source_types_are_explicit(self) -> None:
        self.assertEqual(
            {source["type"] for source in self.data["meta"]["sources"]},
            {"official", "community_reference", "open_source_reference"},
        )

    def test_invalid_references_and_localization_are_rejected(self) -> None:
        characters, materials, curve, builds, assets, meta = self._raw_documents()
        characters["characters"][0]["asset_key"] = "missing"
        with self.assertRaises(DataValidationError):
            validate_data(
                characters, materials, curve, builds, assets, meta,
                project_dir=self.project_dir,
            )

        characters, materials, curve, builds, assets, meta = self._raw_documents()
        materials["items"]["2"]["name"] = "Shell Credits"
        with self.assertRaises(DataValidationError):
            validate_data(
                characters, materials, curve, builds, assets, meta,
                project_dir=self.project_dir,
            )

        characters, materials, curve, builds, assets, meta = self._raw_documents()
        characters["characters"][1]["id"] = characters["characters"][0]["id"]
        with self.assertRaises(DataValidationError):
            validate_data(
                characters, materials, curve, builds, assets, meta,
                project_dir=self.project_dir,
            )

        characters, materials, curve, builds, assets, meta = self._raw_documents()
        materials["characters"]["jinhsi"]["skills"]["normal"]["levels"].pop("5")
        with self.assertRaises(DataValidationError):
            validate_data(
                characters, materials, curve, builds, assets, meta,
                project_dir=self.project_dir,
            )

        characters, materials, curve, builds, assets, meta = self._raw_documents()
        curve["allowed_character_levels"].insert(1, 5)
        with self.assertRaises(DataValidationError):
            validate_data(
                characters, materials, curve, builds, assets, meta,
                project_dir=self.project_dir,
            )


if __name__ == "__main__":
    unittest.main()
