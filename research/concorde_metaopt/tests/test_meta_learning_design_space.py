"""P4 元学习设计空间契约测试（设计 §2.3 / §12-1、2、16）。

覆盖：12D 显式空间解码唯一路径（from_unit_interval -> expand 15 名）、
传 15 名向量必须抛 DesignSpaceError、固定值不可覆盖、越界与交叉约束违规必拒、
无参 load_design_space() 仍为 15D 默认（M-08 回归）。
"""
import unittest
from pathlib import Path

from research.concorde_metaopt.aircraft.design_space import DesignSpaceError, load_design_space
from research.concorde_metaopt.meta_learning import offline_runner

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
CONFIG_15D = CONFIG_DIR / "design_space_15d.yaml"
CONFIG_12D = CONFIG_DIR / "design_space_12d_lifting_surfaces.yaml"
FIXED_NAMES = ("fuselage_length", "fuselage_fineness", "fuselage_height_width_ratio")


class TwelveDimensionalDecodeTests(unittest.TestCase):
    def setUp(self):
        self.space = load_design_space(CONFIG_12D)

    def test_01_explicit_config_is_12d(self):
        self.assertEqual(self.space.design_dim, 12)
        self.assertEqual(self.space.design_set, "12d_lifting_surfaces")
        self.assertEqual(tuple(self.space.fixed_names), FIXED_NAMES)
        self.assertEqual(len(self.space.names), 12)

    def test_02_decode_single_path(self):
        fractions = tuple(0.5 for _ in range(12))
        physical = self.space.from_unit_interval(fractions)
        self.assertEqual(set(physical), set(self.space.names))
        expanded = self.space.expand(physical)
        self.assertEqual(set(expanded), set(self.space.names) | set(FIXED_NAMES))
        for name in FIXED_NAMES:
            self.assertAlmostEqual(float(expanded[name]), float(self.space.fixed_dict[name]), places=12)
        self.assertEqual(self.space.check_bounds(physical), [])
        self.assertEqual(self.space.check_cross_constraints(physical), [])

    def test_03_expand_rejects_fifteen_names(self):
        physical = self.space.from_unit_interval(tuple(0.5 for _ in range(12)))
        expanded = self.space.expand(physical)
        with self.assertRaises(DesignSpaceError):
            self.space.expand(expanded)
        with self.assertRaises(DesignSpaceError):
            self.space.expand({**expanded, "wing_area": 350.0})

    def test_04_fixed_values_not_overridable(self):
        physical = self.space.from_unit_interval(tuple(0.5 for _ in range(12)))
        explicit_fixed = self.space.expand(physical)
        # 固定量只能由 expand 从 config 注入：调用方不能从 12 维入口写入
        self.assertEqual(
            [name for name in physical if name in FIXED_NAMES],
            [],
        )
        self.assertAlmostEqual(
            float(explicit_fixed["fuselage_length"]), float(self.space.fixed_dict["fuselage_length"])
        )

    def test_05_wrong_unit_length_rejected(self):
        with self.assertRaises(DesignSpaceError):
            self.space.from_unit_interval(tuple(0.5 for _ in range(13)))
        # 越界单位值在 from_unit_interval 仅线性解码，越界由 check_bounds 判 INVALID
        out_of_bounds = self.space.from_unit_interval(tuple(1.5 for _ in range(12)))
        self.assertTrue(self.space.check_bounds(out_of_bounds))

    def test_06_bounds_violation_rejected(self):
        physical = dict(self.space.baseline_dict())
        physical["wing_area"] = 9999.0
        self.assertTrue(self.space.check_bounds(physical))
        self.assertTrue(self.space.check_physical(physical))

    def test_07_cross_constraints_rejected(self):
        physical = dict(self.space.baseline_dict())
        physical["span_location_2"] = physical["span_location_3"] + 0.01
        self.assertTrue(self.space.check_cross_constraints(physical))
        self.assertTrue(self.space.check_physical(physical))
        chord = dict(self.space.baseline_dict())
        chord["chord_ratio_3"] = chord["chord_ratio_2"] + 0.01
        self.assertTrue(self.space.check_cross_constraints(chord))

    def test_08_runner_loads_same_12d_space(self):
        runner_space = offline_runner.load_design_space_12d()
        self.assertEqual(runner_space.design_dim, 12)
        self.assertEqual(runner_space.design_set, "12d_lifting_surfaces")
        self.assertEqual(tuple(runner_space.names), tuple(self.space.names))


class DefaultFifteenDimensionalRegressionTests(unittest.TestCase):
    """§12-16：构造参数不得改变无参默认（P1-P3/历史脚本行为不变）。"""

    def test_01_no_argument_default_is_15d(self):
        load_design_space(CONFIG_12D)  # 先显式构造 12D，确认不污染无参默认
        space = load_design_space()
        self.assertEqual(space.design_dim, 15)
        self.assertEqual(len(space.names), 15)
        self.assertEqual(tuple(space.fixed_names), ())
        # 实现层默认 design_set 为 "15d"（M-03 裁决默认值）；无参默认不得变为 12D
        self.assertEqual(space.design_set, "15d")
        self.assertEqual(Path(space.config_path).name, CONFIG_15D.name)

    def test_02_no_argument_stable_across_calls(self):
        first = load_design_space()
        second = load_design_space(None)
        self.assertEqual(tuple(first.names), tuple(second.names))
        self.assertEqual(first.design_set, second.design_set)
        self.assertEqual(first.design_dim, second.design_dim)

    def test_03_explicit_12d_does_not_alias_default(self):
        explicit = load_design_space(CONFIG_12D)
        default = load_design_space()
        self.assertNotEqual(explicit.design_set, default.design_set)
        self.assertEqual(explicit.design_dim, 12)
        self.assertEqual(default.design_dim, 15)


if __name__ == "__main__":
    unittest.main()
