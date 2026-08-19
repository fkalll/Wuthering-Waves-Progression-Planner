"""角色十级档位、技能 1～10 与合计逻辑测试。"""

from __future__ import annotations

import copy
import unittest

from calculator import (
    calculate_level_details,
    calculate_materials,
    calculate_skill_materials,
    material_rows,
    merge_materials,
    suggest_exp_potions,
)
from data_loader import load_all_data


class CalculatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_all_data()
        cls.materials = cls.data["materials"]
        cls.curve = cls.data["level_curve"]

    def level(self, current: int, target: int) -> dict[str, object]:
        return calculate_level_details(
            self.materials, self.curve, "jinhsi", current, target
        )

    def skills(
        self, current: int, target: int, include_tree: bool = False
    ) -> dict[str, int]:
        return calculate_skill_materials(
            self.materials,
            "jinhsi",
            current,
            target,
            include_skill_tree=include_tree,
        )

    def test_merge_materials(self) -> None:
        self.assertEqual(
            merge_materials({"2": 10, "a": 2}, {"2": 5, "b": 3}),
            {"2": 15, "a": 2, "b": 3},
        )

    def test_character_level_1_to_10_and_10_to_20_have_no_ascension(self) -> None:
        first = self.level(1, 10)
        second = self.level(10, 20)
        self.assertEqual(first["required_exp"], 7_000)
        self.assertEqual(first["leveling_credits"], 2_450)
        self.assertEqual(first["crossed_ascensions"], [])
        self.assertEqual(second["required_exp"], 26_300)
        self.assertEqual(second["crossed_ascensions"], [])

    def test_character_level_20_to_30_adds_first_ascension(self) -> None:
        detail = self.level(20, 30)
        self.assertEqual(detail["required_exp"], 61_200)
        self.assertEqual(detail["crossed_ascensions"], [20])
        self.assertEqual(detail["materials"]["41100021"], 4)
        self.assertEqual(detail["materials"]["2"], 26_420)

    def test_character_level_crosses_multiple_nodes(self) -> None:
        self.assertEqual(self.level(20, 50)["crossed_ascensions"], [20, 40])
        self.assertEqual(self.level(80, 90)["crossed_ascensions"], [80])

    def test_character_level_1_to_90_complete_totals(self) -> None:
        detail = self.level(1, 90)
        self.assertEqual(detail["required_exp"], 2_438_000)
        self.assertEqual(detail["leveling_credits"], 853_300)
        self.assertEqual(detail["materials"]["2"], 1_023_300)
        self.assertEqual(detail["materials"]["41400034"], 46)
        self.assertEqual(detail["materials"]["42310210"], 60)
        self.assertEqual(detail["crossed_ascensions"], [20, 40, 50, 60, 70, 80])

    def test_character_level_rejects_non_ten_level_choices(self) -> None:
        invalid = [(1, 5), (5, 10), (10, 10), (20, 10), (0, 10), (80, 100), (True, 10)]
        for current, target in invalid:
            with self.subTest(current=current, target=target), self.assertRaises(ValueError):
                self.level(current, target)

    def test_skill_1_to_2_aggregates_all_five_skills(self) -> None:
        totals = self.skills(1, 2)
        self.assertEqual(totals, {"43020041": 10, "41100021": 10, "2": 7_500})

    def test_skill_1_to_5_and_5_to_10_partition_full_levels(self) -> None:
        first = self.skills(1, 5)
        second = self.skills(5, 10)
        full = self.skills(1, 10)
        self.assertEqual(first["2"], 70_000)
        self.assertEqual(second["2"], 1_330_000)
        self.assertEqual(full, merge_materials(first, second))
        self.assertEqual(full["2"], 1_400_000)
        self.assertEqual(full["41400144"], 20)

    def test_skill_tree_is_independent(self) -> None:
        without_tree = self.skills(1, 10, False)
        with_tree = self.skills(1, 10, True)
        self.assertEqual(with_tree["2"], 2_030_000)
        self.assertEqual(with_tree["41400144"], 26)
        self.assertEqual(with_tree["43020044"], 67)
        self.assertNotEqual(without_tree, with_tree)

    def test_skill_invalid_ranges_are_rejected(self) -> None:
        for current, target in [(1, 1), (5, 4), (0, 2), (9, 11), (True, 5), (1, 5.5)]:
            with self.subTest(current=current, target=target), self.assertRaises(ValueError):
                self.skills(current, target)  # type: ignore[arg-type]

    def test_total_is_level_plus_selected_skill_scope_for_all_characters(self) -> None:
        for character in self.data["characters"]:
            with self.subTest(character=character["name"]):
                key = character["materials_key"]
                level = calculate_materials(
                    self.materials,
                    key,
                    "level",
                    level_curve=self.curve,
                    current_level=20,
                    target_level=50,
                )
                skills = calculate_materials(
                    self.materials,
                    key,
                    "skills",
                    current_skill_level=5,
                    target_skill_level=10,
                    include_skill_tree=False,
                )
                total = calculate_materials(
                    self.materials,
                    key,
                    "total",
                    level_curve=self.curve,
                    current_level=20,
                    target_level=50,
                    current_skill_level=5,
                    target_skill_level=10,
                    include_skill_tree=False,
                )
                self.assertEqual(total, merge_materials(level, skills))

    def test_potion_suggestion_minimizes_overflow_then_count(self) -> None:
        suggestion, overflow = suggest_exp_potions(
            1_900, self.curve["potion_values"]
        )
        self.assertEqual(suggestion, {"43010001": 2})
        self.assertEqual(overflow, 100)

    def test_calculation_does_not_mutate_source(self) -> None:
        before = copy.deepcopy(self.materials)
        calculate_materials(
            self.materials,
            "jinhsi",
            "total",
            level_curve=self.curve,
        )
        self.assertEqual(self.materials, before)

    def test_material_rows_include_chinese_metadata_and_asset(self) -> None:
        totals = self.skills(1, 2)
        rows = material_rows(self.materials, totals)
        self.assertTrue(
            all(
                {"id", "name", "category", "asset_key", "quantity"} <= set(row)
                for row in rows
            )
        )
        self.assertEqual(rows[0]["name"], "贝币")

    def test_unknown_character_and_mode_are_rejected(self) -> None:
        with self.assertRaises(KeyError):
            calculate_materials(self.materials, "not-found", "skills")
        with self.assertRaises(ValueError):
            calculate_materials(self.materials, "jinhsi", "partial")


if __name__ == "__main__":
    unittest.main()
