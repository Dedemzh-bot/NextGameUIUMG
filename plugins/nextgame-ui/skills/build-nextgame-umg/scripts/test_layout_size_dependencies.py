#!/usr/bin/env python3
"""Regression checks for real Slot lowering and planned content dependencies."""

from copy import deepcopy
from pathlib import Path
import unittest

from prepare_build import build_plan
from test_designer_size_mode import CATALOG, RULES, SCHEMA, child_spec
from validate_layout_spec import planned_content_size_proof, validate_spec


def dependency_spec():
    spec = child_spec()
    spec["profile"]["adaptive"] = False
    content = spec["nodes"][1]
    content.update(role="container.vertical", name="VerContent")
    content["slotLayout"]["autoSize"] = True
    content["contentSizeProof"] = {
        "kind": "layout-dependency/1", "minimumDesiredSize": [400, 232],
        "sourceNodeIds": ["header-image", "body-image"], "evidenceId": "ev.content.size",
    }
    for part, y, height in (("header", 0, 52), ("body", 52, 180)):
        rect = [0, y / 232, 1, height / 232]
        spec["nodes"].append({
            "id": part, "name": "Over" + part.title(), "role": "container.overlay",
            "parent": "content", "rect": rect, "anchor": "left-top", "properties": {},
            "overlayPurpose": "adaptive-bounds",
            "flowSlot": {"size": {"rule": "Auto"}, "padding": [0, 0, 0, 0],
                         "horizontalAlignment": "Fill", "verticalAlignment": "Top"},
        })
        spec["nodes"].append({
            "id": part + "-image", "name": "Img" + part.title(), "role": "visual.image",
            "parent": part, "rect": rect, "anchor": "left-top",
            "properties": {"brushImageSize": [400, height]},
            "overlaySlot": {"padding": [0, 0, 0, 0], "horizontalAlignment": "Fill", "verticalAlignment": "Fill"},
        })
    return spec


def proof_valid(spec):
    nodes = {node["id"]: node for node in spec["nodes"]}
    return planned_content_size_proof(nodes["content"], nodes)


class LayoutSizeDependencyTests(unittest.TestCase):
    def test_auto_content_is_executable_without_fabricated_measurement(self):
        spec = dependency_spec()
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report)
        self.assertTrue(proof_valid(spec))
        self.assertNotIn("contentDrivenSize", spec["nodes"][1])
        plan = build_plan(Path("dependency.json"), spec, CATALOG, RULES)
        step = next(item for item in plan["steps"] if item["stepId"] == "set-widget-properties-header-image")
        self.assertEqual(step["arguments"]["values"]["brush"], {"imageSize": {"x": 400, "y": 52}})
        self.assertNotIn("resourceObject", step["arguments"]["values"]["brush"])
        ids = [item["stepId"] for item in plan["steps"]]
        self.assertGreater(ids.index("verify-layout-widget-properties-header-image"), ids.index("save"))
        self.assertGreater(ids.index("verify-layout-overlay-padding-header-image"), ids.index("save"))
        index = ids.index("set-widget-properties-header-image")
        self.assertEqual([item["toolName"] for item in plan["steps"][index - 2:index + 1]],
                         ["list_properties", "get_properties", "set_properties"])

    def test_padding_contributes_to_plan_and_size(self):
        spec = dependency_spec()
        spec["nodes"][3]["overlaySlot"]["padding"] = [3, 4, 5, 6]
        spec["nodes"][1]["contentSizeProof"]["minimumDesiredSize"] = [408, 242]
        self.assertTrue(proof_valid(spec))
        plan = build_plan(Path("padding.json"), spec, CATALOG, RULES)
        step = next(item for item in plan["steps"] if item["stepId"] == "set-overlay-slot-properties-header-image")
        self.assertEqual(step["arguments"]["values"]["padding"], {"left": 3, "top": 4, "right": 5, "bottom": 6})

    def test_legacy_overlay_without_padding_is_unchanged(self):
        spec = dependency_spec()
        del spec["nodes"][3]["overlaySlot"]["padding"]
        self.assertTrue(validate_spec(spec, CATALOG)["valid"])
        plan = build_plan(Path("old-overlay.json"), spec, CATALOG, RULES)
        step = next(item for item in plan["steps"] if item["stepId"] == "set-overlay-slot-properties-header-image")
        self.assertNotIn("padding", step["arguments"]["values"])

    def test_malformed_padding_rejected_before_planning(self):
        for value in ([1, 2, 3], [0, 0, True, 0], [0, float("inf"), 0, 0], "padding"):
            with self.subTest(value=value):
                spec = dependency_spec()
                spec["nodes"][3]["overlaySlot"]["padding"] = value
                codes = {item["code"] for item in validate_spec(spec, CATALOG)["errors"]}
                self.assertIn("overlay.slot.padding", codes)
                with self.assertRaises(ValueError):
                    build_plan(Path("bad-padding.json"), spec, CATALOG, RULES)
        spec = dependency_spec()
        spec["nodes"][3]["overlaySlot"]["invented"] = 1
        self.assertIn("overlay.slot.fields", {item["code"] for item in validate_spec(spec, CATALOG)["errors"]})

    def test_brush_size_requires_two_positive_finite_numbers(self):
        for value in ([0, 20], [-2, 20], [True, 20], [float("nan"), 20], [10**1000, 20], [20], {"x": 20, "y": 20}):
            with self.subTest(value=value):
                spec = dependency_spec()
                spec["nodes"][3]["properties"]["brushImageSize"] = value
                self.assertIn("image.brush_image_size", {item["code"] for item in validate_spec(spec, CATALOG)["errors"]})
                self.assertFalse(proof_valid(spec))

    def test_proof_rejects_forged_unreachable_collapsed_or_cyclic_sources(self):
        mutations = [
            lambda s: s["nodes"][1]["contentSizeProof"].update(minimumDesiredSize=[400, 999]),
            lambda s: s["nodes"][1]["contentSizeProof"].update(sourceNodeIds=["missing"]),
            lambda s: s["nodes"][1]["contentSizeProof"].update(sourceNodeIds=["header-image", "header-image"]),
            lambda s: s["nodes"][1]["contentSizeProof"].update(evidenceId="Invalid ID"),
            lambda s: s["nodes"][3]["properties"].update(visibility="Collapsed"),
            lambda s: s["nodes"][3].update(parent="body-image"),
            lambda s: s["nodes"][2].update(role="container.size"),
            lambda s: s["nodes"][2]["flowSlot"]["size"].update(rule="Fill", weight=1),
            lambda s: s["nodes"][1]["slotLayout"]["anchors"].update(maximum=[1, 0]),
            lambda s: s["nodes"][1]["slotLayout"].update(autoSize=False),
            lambda s: s["nodes"][1].update(parent="header"),
        ]
        for mutate in mutations:
            spec = dependency_spec()
            mutate(spec)
            self.assertFalse(proof_valid(spec), spec)

    def test_unknown_fields_and_actual_measurement_shape_remain_separate(self):
        spec = dependency_spec()
        spec["nodes"][1]["contentSizeProof"]["verified"] = True
        self.assertFalse(proof_valid(spec))
        schema = SCHEMA["properties"]["nodes"]["items"]["properties"]
        self.assertFalse(schema["contentSizeProof"]["additionalProperties"])
        self.assertEqual(schema["contentSizeProof"]["properties"]["kind"]["enum"], ["layout-dependency/1", "layout-dependency/2"])
        self.assertNotIn("verified", schema["contentSizeProof"]["properties"])
        self.assertNotIn("minimumDesiredSize", schema["contentDrivenSize"]["properties"])

    def test_scale_cover_maps_explicit_native_enums(self):
        spec = child_spec()
        spec["profile"]["designSizeMode"] = "FillScreen"
        spec["nodes"][1].update(role="container.scale", name="ScaContent")
        spec["nodes"][1]["properties"] = {"stretch": "ScaleToFill", "stretchDirection": "Both"}
        plan = build_plan(Path("cover.json"), spec, CATALOG, RULES)
        step = next(item for item in plan["steps"] if item["stepId"] == "set-widget-properties-content")
        self.assertEqual(step["arguments"]["values"]["stretch"], "ScaleToFill")
        self.assertEqual(step["arguments"]["values"]["stretchDirection"], "Both")
        spec["nodes"][1]["properties"]["stretch"] = "Cover"
        self.assertIn("scale.property", {item["code"] for item in validate_spec(spec, CATALOG)["errors"]})

    def test_existing_readback_comparison_checks_new_nested_native_fields(self):
        from validate_prototype_widget_readback import _compare_expected, expected_properties
        expected = expected_properties(Path("dependency.json"), dependency_spec())["header-image"]
        observed = deepcopy(expected)
        observed["widget"]["brush"]["resourceObject"] = {"refPath": "/Game/Existing.Existing"}
        errors = []
        _compare_expected(observed, expected, "$", errors)
        self.assertEqual(errors, [])
        observed["widget"]["brush"]["imageSize"]["x"] = 0
        observed["slot"]["padding"]["right"] = 99
        _compare_expected(observed, expected, "$", errors)
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(error["code"] == "actual.property_mismatch" for error in errors))


if __name__ == "__main__":
    unittest.main()
