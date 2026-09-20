#!/usr/bin/env python3
"""SizeBox setter/slot lowering and conservative natural-height proof."""

from copy import deepcopy
from pathlib import Path
import json
import os
import tempfile
import unittest

from jsonschema import Draft202012Validator

from prepare_build import build_plan
from test_layout_size_dependencies import CATALOG, RULES, SCHEMA, dependency_spec
from validate_layout_spec import planned_content_size_proof, validate_spec


def popup_spec():
    """RootCanvas -> fixed width SizeDescriptionWidth -> natural-height flow."""
    spec = dependency_spec()
    spec["referenceSize"] = [456, 232]
    content = spec["nodes"][1]
    slot = content.pop("slotLayout")
    proof = content.pop("contentSizeProof")
    proof["minimumDesiredSize"] = [456, 232]
    content.update(name="VerDescriptionRoot", parent="description-width")
    content["sizeBoxSlot"] = {"padding": [0, 0, 0, 0], "horizontalAlignment": "Fill", "verticalAlignment": "Fill"}
    spec["nodes"].insert(1, {
        "id": "description-width", "name": "SizeDescriptionWidth", "role": "container.size",
        "parent": "root", "rect": [0, 0, 1, 1], "anchor": "left-top", "properties": {},
        "slotLayout": slot, "contentSizeProof": proof,
        "sizeBoxConstraints": {"version": 1, "widthOverride": 456, "heightOverride": None},
    })
    return spec


def proof_valid(spec):
    nodes = {node["id"]: node for node in spec["nodes"]}
    return planned_content_size_proof(nodes["description-width"], nodes)


class SizeBoxConstraintTests(unittest.TestCase):
    def assert_valid(self, spec):
        self.assertEqual([], list(Draft202012Validator(SCHEMA).iter_errors(spec)))
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report)

    def test_fixed_width_preserves_natural_height_without_measurement(self):
        spec = popup_spec()
        self.assert_valid(spec)
        self.assertTrue(proof_valid(spec))
        self.assertNotIn("contentDrivenSize", spec["nodes"][1])
        self.assertNotIn("verified", spec["nodes"][1]["contentSizeProof"])
        spec["nodes"][1]["contentSizeProof"]["minimumDesiredSize"][1] = 456
        self.assertFalse(proof_valid(spec))

    def test_disabled_width_inherits_child_lower_bound(self):
        spec = popup_spec()
        spec["nodes"][1]["sizeBoxConstraints"].update(widthOverride=None, heightOverride=120)
        spec["nodes"][1]["contentSizeProof"]["minimumDesiredSize"] = [400, 120]
        self.assert_valid(spec)
        self.assertTrue(proof_valid(spec))
        spec = popup_spec()
        spec["nodes"][2]["sizeBoxSlot"]["padding"] = [3, 4, 5, 6]
        spec["nodes"][1]["contentSizeProof"]["minimumDesiredSize"] = [456, 242]
        self.assertFalse(proof_valid(spec))  # Nonzero SizeBox padding is outside this conservative proof.

    def test_native_fallback_is_real_method_metadata_with_enable_bits(self):
        plan = build_plan(Path("description-popup.json"), popup_spec(), CATALOG, RULES)
        fallback = next(step for step in plan["steps"] if step["operation"] == "native_setter_fallback")
        self.assertEqual(fallback["contract"], "size-box-constraints/1")
        self.assertEqual(fallback["adapter"], "NxUEAgent")
        self.assertEqual(fallback["requiredClass"], "/Script/UMG.SizeBox")
        self.assertNotIn("toolsetName", fallback)
        self.assertNotIn("toolName", fallback)
        self.assertEqual(fallback["nativeCalls"][:2], [
            {"method": "set_width_override", "arguments": [456]},
            {"method": "clear_height_override", "arguments": []},
        ])
        self.assertEqual({call["method"] for call in fallback["nativeCalls"][2:]}, {
            "clear_min_desired_width", "clear_min_desired_height", "clear_max_desired_width", "clear_max_desired_height",
            "clear_min_aspect_ratio", "clear_max_aspect_ratio",
        })
        self.assertEqual(fallback["expectedProperties"], {
            "widthOverride": 456, "bOverride_WidthOverride": True, "bOverride_HeightOverride": False,
            "bOverride_MinDesiredWidth": False, "bOverride_MinDesiredHeight": False,
            "bOverride_MaxDesiredWidth": False, "bOverride_MaxDesiredHeight": False,
            "bOverride_MinAspectRatio": False, "bOverride_MaxAspectRatio": False,
        })
        self.assertNotIn("heightOverride", fallback["expectedProperties"])
        names = [step["stepId"] for step in plan["steps"]]
        self.assertLess(names.index(fallback["stepId"]), names.index("compile"))
        readback = next(step for step in plan["steps"] if step["stepId"] == "verify-size-box-native-constraints-description-width")
        self.assertGreater(names.index(readback["stepId"]), names.index("save"))
        self.assertEqual(fallback["expectedProperties"], readback["expectedProperties"])
        self.assertEqual(set(readback["arguments"]["properties"]), set(fallback["expectedProperties"]))

    def test_size_box_slot_is_explicitly_lowered_and_read_after_save(self):
        plan = build_plan(Path("description-popup.json"), popup_spec(), CATALOG, RULES)
        steps = plan["steps"]
        index = next(i for i, step in enumerate(steps) if step["stepId"] == "set-size-box-slot-properties-content")
        self.assertEqual([step.get("toolName") for step in steps[index - 2:index + 1]], ["list_properties", "get_properties", "set_properties"])
        self.assertEqual(steps[index]["arguments"]["values"], {
            "padding": {"left": 0, "top": 0, "right": 0, "bottom": 0},
            "horizontalAlignment": "HAlign_Fill", "verticalAlignment": "VAlign_Fill",
        })
        ids = [step["stepId"] for step in steps]
        self.assertGreater(ids.index("verify-layout-size-box-slot-content"), ids.index("save"))

    def test_official_executors_reject_fallback_before_any_editor_call(self):
        from execute_plan import execute
        from execute_plan_programmatic import build_programmatic_script, run_plan
        plan = build_plan(Path("description-popup.json"), popup_spec(), CATALOG, RULES)
        self.assertTrue(plan["executorContract"]["nativeSetterFallbacks"]["requiresAuthorizedMixedRunner"])
        self.assertFalse(plan["executorContract"]["nativeSetterFallbacks"]["officialExecutorMaySkip"])

        class NoEditorCalls:
            def __getattr__(self, name):
                raise AssertionError("Executor must fail before accessing the Editor: " + name)

        for invoke in (
            lambda: execute(plan, NoEditorCalls(), None),
            lambda: run_plan(plan, NoEditorCalls()),
            lambda: build_programmatic_script(plan, plan["steps"], {}),
        ):
            with self.assertRaisesRegex(RuntimeError, "native_setter_fallback"):
                invoke()

    def test_existing_readback_comparison_checks_enable_bits_and_child_slot(self):
        from validate_prototype_widget_readback import _compare_expected, expected_properties
        expected = expected_properties(Path("description-popup.json"), popup_spec())
        widget = expected["description-width"]["widget"]
        self.assertEqual(widget["widthOverride"], 456)
        self.assertIs(widget["bOverride_WidthOverride"], True)
        self.assertIs(widget["bOverride_HeightOverride"], False)
        observed = deepcopy(widget)
        observed["heightOverride"] = 999  # Inactive stored values are not constraints.
        errors = []
        _compare_expected(observed, widget, "$", errors)
        self.assertEqual(errors, [])
        observed["bOverride_HeightOverride"] = True
        observed["bOverride_WidthOverride"] = False
        _compare_expected(observed, widget, "$", errors)
        self.assertEqual(len(errors), 2)
        self.assertEqual(expected["content"]["slot"]["horizontalAlignment"], "HAlign_Fill")

    def test_existing_rule_routes_complete_constraint_contract(self):
        from route_rule_cards import build_rule_card_pack
        temp_root = os.environ.get("NEXTGAME_UI_TEST_TMPDIR")
        if temp_root:
            Path(temp_root).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="size-box-contract-", dir=temp_root) as temp:
            path = Path(temp) / "popup.json"
            path.write_text(json.dumps(popup_spec()), encoding="utf-8")
            pack = build_rule_card_pack(path, stages=["build-planning"])
            self.assertEqual(pack["routingMode"], "routed", pack["fallbackReasons"])
            self.assertTrue(pack["machineValidation"]["layoutValid"])
            self.assertIn("layout.content-driven-canvas-module", pack["selectedRuleIds"])
            details = json.dumps(pack["detailSections"])
            self.assertIn("Exact-axis SizeBox execution and planned dependency", details)
            self.assertIn("native_setter_fallback", details)
            self.assertIn("zero padding", details)

    def test_schema_and_semantics_reject_malformed_constraints(self):
        variants = [None, {}, {"version": 1, "widthOverride": 456},
                    {"version": 2, "widthOverride": 456, "heightOverride": None},
                    {"version": 1, "widthOverride": None, "heightOverride": None},
                    {"version": 1, "widthOverride": 456, "heightOverride": None, "minDesiredHeight": 10}]
        variants.extend({"version": 1, "widthOverride": value, "heightOverride": None}
                        for value in (0, -1, True, "456"))
        for value in variants:
            with self.subTest(value=value):
                spec = popup_spec()
                spec["nodes"][1]["sizeBoxConstraints"] = value
                self.assertTrue(list(Draft202012Validator(SCHEMA).iter_errors(spec)))
                self.assertFalse(validate_spec(spec, CATALOG)["valid"])
                self.assertFalse(proof_valid(spec))
                with self.assertRaises(ValueError):
                    build_plan(Path("invalid.json"), spec, CATALOG, RULES)
        for value in (float("nan"), float("inf"), 10**1000):
            spec = popup_spec()
            spec["nodes"][1]["sizeBoxConstraints"]["widthOverride"] = value
            self.assertFalse(validate_spec(spec, CATALOG)["valid"])
            self.assertFalse(proof_valid(spec))

    def test_constraints_and_slots_require_real_size_box_relationships(self):
        for mutate in (
            lambda s: s["nodes"][1].update(role="container.vertical", name="VerWrong"),
            lambda s: s["nodes"][2].update(parent="root"),
            lambda s: s["nodes"][2].pop("sizeBoxSlot"),
            lambda s: s["nodes"][2]["sizeBoxSlot"].update(invented=True),
            lambda s: s["nodes"][2]["sizeBoxSlot"].update(padding=[0, -1, 0, 0]),
            lambda s: s["nodes"][2]["sizeBoxSlot"].update(horizontalAlignment="Unknown"),
        ):
            spec = popup_spec()
            mutate(spec)
            self.assertFalse(validate_spec(spec, CATALOG)["valid"])
            self.assertFalse(proof_valid(spec))

    def test_proof_rejects_missing_extra_collapsed_unknown_and_cyclic_children(self):
        mutations = [
            lambda s: s["nodes"][2].update(parent="root"),
            lambda s: s["nodes"].append({**deepcopy(s["nodes"][2]), "id": "extra", "name": "VerExtra"}),
            lambda s: s["nodes"][2]["properties"].update(visibility="Collapsed"),
            lambda s: s["nodes"][2].update(role="container.canvas"),
            lambda s: s["nodes"][1].pop("sizeBoxConstraints"),
            lambda s: s["nodes"][1]["properties"].update(widthOverride=456),
            lambda s: s["nodes"][2]["sizeBoxSlot"].update(horizontalAlignment="Left"),
            lambda s: s["nodes"][1].update(parent="content"),
            lambda s: s["nodes"][1]["contentSizeProof"].update(sourceNodeIds=["content"]),
            lambda s: s["nodes"][1]["contentSizeProof"].update(sourceNodeIds=["missing"]),
        ]
        for mutate in mutations:
            spec = popup_spec()
            mutate(spec)
            self.assertFalse(proof_valid(spec), spec)


if __name__ == "__main__":
    unittest.main()
