#!/usr/bin/env python3
"""Pixel-font lowering, native property sequencing, and legacy point regressions."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from prepare_build import build_plan
from test_text_component_rules import split_header_spec
from validate_layout_spec import load_json, validate_spec

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


SKILL_ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_json(SKILL_ROOT / "references" / "component-catalog.json")
RULES = load_json(SKILL_ROOT / "references" / "rule-index.json")
SCHEMA = load_json(SKILL_ROOT / "assets" / "ui-layout-spec.schema.json")
SPEC_PATH = Path("font-size-unit-regression.json")
TARGET = "header-title"


def text_fixture() -> dict:
    spec = split_header_spec()
    for node in spec["nodes"]:
        if node["role"] == "text.label":
            node["properties"]["justification"] = "Left"
    return spec


def text_node(spec: dict) -> dict:
    return next(node for node in spec["nodes"] if node["id"] == TARGET)


def step_by_id(plan: dict, step_id: str) -> dict:
    return next(step for step in plan["steps"] if step["stepId"] == step_id)


def font_values(plan: dict) -> dict:
    return step_by_id(plan, f"set-widget-properties-{TARGET}")["arguments"]["values"]


class FontSizeUnitTests(unittest.TestCase):
    def plan(self, spec: dict) -> dict:
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report["errors"])
        return build_plan(SPEC_PATH, spec, CATALOG, RULES)

    def assert_rejected(self, spec: dict, code: str) -> None:
        report = validate_spec(spec, CATALOG)
        self.assertFalse(report["valid"])
        self.assertIn(code, {error["code"] for error in report["errors"]})
        with self.assertRaises(ValueError):
            build_plan(SPEC_PATH, spec, CATALOG, RULES)

    def test_required_pixel_sizes_and_exact_compensation(self) -> None:
        for pixels, points, scale in ((28, 22, 21 / 22), (24, 18, 1), (40, 30, 1), (22, 18, 11 / 12)):
            with self.subTest(pixels=pixels):
                spec = text_fixture()
                node = text_node(spec)
                node["fontSizeUnit"] = "px"
                node["properties"]["font"]["size"] = pixels
                snapshot = deepcopy(spec)
                values = font_values(self.plan(spec))
                self.assertEqual(values["font"]["size"], points)
                self.assertEqual(values["renderTransform"], {"scale": {"x": scale, "y": scale}})
                self.assertAlmostEqual(points * 96 / 72 * scale, pixels)
                self.assertEqual(spec, snapshot)

    def test_odd_fractional_and_small_pixel_sources_lower_to_even_points(self) -> None:
        for pixels in (1, 19, 21, 23.5, 27.25):
            with self.subTest(pixels=pixels):
                spec = text_fixture()
                text_node(spec)["fontSizeUnit"] = "px"
                text_node(spec)["properties"]["font"]["size"] = pixels
                values = font_values(self.plan(spec))
                points = values["font"]["size"]
                scale = values["renderTransform"]["scale"]["x"]
                self.assertGreater(points, 0)
                self.assertIsInstance(points, int)
                self.assertEqual(points % 2, 0)
                self.assertGreater(scale, 0)
                self.assertLessEqual(scale, 1)
                self.assertAlmostEqual(points * 96 / 72 * scale, pixels)

    def test_justification_pivots_keep_growth_boundary_fixed(self) -> None:
        for justification, pivot_x in (("Left", 0), ("Center", 0.5), ("Right", 1)):
            with self.subTest(justification=justification):
                spec = text_fixture()
                node = text_node(spec)
                node["fontSizeUnit"] = "px"
                node["properties"]["font"]["size"] = 28
                node["properties"]["justification"] = justification
                values = font_values(self.plan(spec))
                pivot = values["renderTransformPivot"]
                scale = values["renderTransform"]["scale"]["x"]
                self.assertEqual(pivot, {"x": pivot_x, "y": 0.5})
                # Model short/long content whose Slot holds the chosen edge.
                # Scaling around this pivot preserves the same edge or center.
                for width in (80, 240):
                    stable_boundary = 600
                    left = stable_boundary - pivot_x * width
                    scaled_left = left + pivot["x"] * width * (1 - scale)
                    scaled_right = scaled_left + scale * width
                    actual_boundary = scaled_left * (1 - pivot_x) + scaled_right * pivot_x
                    self.assertAlmostEqual(actual_boundary, stable_boundary)

    def test_other_font_members_and_all_other_plan_operations_are_preserved(self) -> None:
        spec = text_fixture()
        node = text_node(spec)
        node["properties"]["font"] = {
            "size": 28,
            "fontObject": {"refPath": "/Game/UI/Fonts/TestFont.TestFont"},
            "typefaceFontName": "Bold",
            "letterSpacing": 12,
            "outlineSettings": {"outlineSize": 1, "bSeparateFillAlpha": True},
        }
        before = self.plan(spec)
        node["fontSizeUnit"] = "px"
        snapshot = deepcopy(spec)
        after = self.plan(spec)
        values = font_values(after)
        expected_font = deepcopy(node["properties"]["font"])
        expected_font["size"] = 22
        self.assertEqual(values["font"], expected_font)
        self.assertNotIn("fontSizeUnit", values["font"])
        self.assertEqual(set(values["renderTransform"]), {"scale"})
        self.assertEqual(spec, snapshot)
        self.assertEqual(len(before["steps"]), len(after["steps"]))
        values["font"]["size"] = 28
        for name in ("renderTransform", "renderTransformPivot"):
            del values[name]
            step_by_id(after, f"get-widget-properties-{TARGET}")["arguments"]["properties"].remove(name)
        self.assertEqual(after, before)

    def test_default_and_explicit_pt_plans_are_identical_without_transform_writes(self) -> None:
        spec = text_fixture()
        before = self.plan(spec)
        for node in spec["nodes"]:
            if node["role"] == "text.label":
                node["fontSizeUnit"] = "pt"
        after = self.plan(spec)
        self.assertEqual(after, before)
        for step in after["steps"]:
            values = step["arguments"].get("values", {})
            self.assertNotIn("renderTransform", values)
            self.assertNotIn("renderTransformPivot", values)
            self.assertNotIn("fontSizeUnit", values)

    def test_native_scale_and_pivot_are_in_discover_read_set_sequence(self) -> None:
        spec = text_fixture()
        text_node(spec)["fontSizeUnit"] = "px"
        plan = self.plan(spec)
        index = next(i for i, step in enumerate(plan["steps"]) if step["stepId"] == f"list-widget-properties-{TARGET}")
        sequence = plan["steps"][index:index + 3]
        self.assertEqual([step["toolName"] for step in sequence], ["list_properties", "get_properties", "set_properties"])
        for step in sequence:
            self.assertEqual(step["toolsetName"], "editor_toolset.toolsets.object.ObjectTools")
            self.assertEqual(step["arguments"]["instance"], {"refPath": f"${{node.{TARGET}.returnValue.widget.refPath}}"})
        requested = sequence[1]["arguments"]["properties"]
        self.assertEqual(set(requested), set(sequence[2]["arguments"]["values"]))
        self.assertTrue({"font", "renderTransform", "renderTransformPivot"} <= set(requested))
        self.assertNotIn("fontSizeUnit", requested)
        self.assertEqual(sequence[2]["assertion"], "returnValue must be true")

    def test_illegal_units_and_nontext_metadata_are_rejected(self) -> None:
        for unit in ("PX", "pixels", "Pt", "", None, 96, True, [], {}):
            with self.subTest(unit=unit):
                spec = text_fixture()
                text_node(spec)["fontSizeUnit"] = unit
                self.assert_rejected(spec, "text.font_size_unit.value")
        for unit in ("px", "pt"):
            for index in (0, 1, 3):
                with self.subTest(unit=unit, nontext_index=index):
                    spec = text_fixture()
                    spec["nodes"][index]["fontSizeUnit"] = unit
                    self.assert_rejected(spec, "text.font_size_unit.role")

    def test_invalid_pixel_sizes_and_misplaced_unit_are_rejected(self) -> None:
        for size in (0, -2, None, True, "28", [], {}, float("nan"), float("inf"), 10 ** 400):
            with self.subTest(size=size):
                spec = text_fixture()
                node = text_node(spec)
                node["fontSizeUnit"] = "px"
                node["properties"]["font"]["size"] = size
                self.assert_rejected(spec, "text.font_size.pixels")
        spec = text_fixture()
        text_node(spec)["properties"]["font"]["fontSizeUnit"] = "px"
        self.assert_rejected(spec, "text.font_size_unit.location")
        spec = text_fixture()
        text_node(spec)["properties"]["fontSizeUnit"] = "px"
        self.assert_rejected(spec, "node.property.unknown")

    def test_px_requires_justification_but_legacy_pt_omission_still_plans(self) -> None:
        spec = text_fixture()
        del text_node(spec)["properties"]["justification"]
        self.plan(spec)
        text_node(spec)["fontSizeUnit"] = "px"
        self.assert_rejected(spec, "text.justification.required_for_px")

    def test_pt_even_integer_validation_remains_unchanged(self) -> None:
        for unit in (None, "pt"):
            for size in (19, 0, -2, 24.0, 23.5, True):
                with self.subTest(unit=unit, size=size):
                    spec = text_fixture()
                    if unit is not None:
                        text_node(spec)["fontSizeUnit"] = unit
                    text_node(spec)["properties"]["font"]["size"] = size
                    self.assert_rejected(spec, "text.font_size.even")

    @unittest.skipIf(Draft202012Validator is None, "jsonschema unavailable; semantic validation remains covered")
    def test_json_schema_accepts_text_metadata_and_rejects_wrong_unit_or_role(self) -> None:
        validator = Draft202012Validator(SCHEMA)
        for unit in ("px", "pt"):
            spec = text_fixture()
            text_node(spec)["fontSizeUnit"] = unit
            self.assertEqual(list(validator.iter_errors(spec)), [])
            spec["nodes"][0]["fontSizeUnit"] = unit
            self.assertTrue(list(validator.iter_errors(spec)))
        spec = text_fixture()
        text_node(spec)["fontSizeUnit"] = "pixels"
        self.assertTrue(list(validator.iter_errors(spec)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
