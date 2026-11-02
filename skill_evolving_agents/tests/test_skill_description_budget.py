from __future__ import annotations

import unittest

import run_pipeline as runner


class DescriptionBudgetTest(unittest.TestCase):
    def test_long_description_is_bounded(self) -> None:
        value = runner.bounded_skill_description(
            "Build native editable multi-ring Excel doughnut charts and verify rendered labels."
        )
        self.assertLessEqual(len(value), 60)
        self.assertTrue(value.endswith("."))

    def test_short_description_is_preserved(self) -> None:
        value = "Build nested Excel charts."
        self.assertEqual(runner.bounded_skill_description(value), value)


if __name__ == "__main__":
    unittest.main()
