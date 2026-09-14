"""Regression tests for explicit semantic text groups and exact lowering."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from semantic_text import validate_requirement_semantic_text, validate_semantic_text_coverage

INTEGRATION = argparse.Namespace(requirement=None, view=None, bundle=None)


def fixture():
    group = {"kind": "semantic-pair", "reason": "Independently authored objectives",
             "sourceCombinedText": "探索边境 · 收集余波", "partNames": ["TxtA", "TxtB"], "gapPx": 16,
             "availableWidthPx": 416, "maxChars": [8, 8], "capacitySamples": ["这是五个字这是五"] * 2}
    elements = [{"id": "group", "kind": "panel", "layoutRole": "container.horizontal", "inBuildScope": True,
                 "bounds": [0.8, 0.2, 0.1625, 0.025], "properties": {"semanticTextGroup": group}}]
    nodes = {"Group": {"id": "Group", "role": "container.horizontal", "rect": deepcopy(elements[0]["bounds"])}}
    maps = [{"assetId": "asset", "layoutNodeId": "Group", "requirementRefs": ["group"]}]
    for index, (identifier, copy) in enumerate((("a", "探索边境"), ("b", "收集余波"))):
        slot = {"slotType": "flow", "sizingBasis": "weighted-remaining-space", "size": {"rule": "Fill", "weight": 1},
                "padding": [16 if index else 0, 0, 0, 0], "horizontalAlignment": "Fill", "verticalAlignment": "Top", "reason": "Reviewed"}
        elements.append({"id": identifier, "kind": "text", "nameHint": "Txt" + identifier.upper(), "parentElementId": "group", "inBuildScope": True,
                         "properties": {"text": copy, "wrap": False, "wrapTextAt": 0}, "panelSlotIntent": slot})
        nodes[identifier.upper()] = {"id": identifier.upper(), "parent": "Group", "role": "text.label",
                                     "properties": {"text": copy, "autoWrap": False, "wrapTextAt": 0},
                                     "flowSlot": {k: deepcopy(v) for k, v in slot.items() if k not in {"slotType", "reason", "sizingBasis"}}}
        maps.append({"assetId": "asset", "layoutNodeId": identifier.upper(), "requirementRefs": [identifier, "rt." + identifier]})
    spec = {"uiModel": {"elements": elements, "runtimeFields": [
        {"id": "rt.a", "elementId": "a", "inBuildScope": True}, {"id": "rt.b", "elementId": "b", "inBuildScope": True}]}}
    bundle = {"assets": [{"id": "asset", "referenceSize": [2560, 1440]}], "nodeMappings": maps}
    return spec, bundle, {"asset": nodes}


class SemanticTextTests(unittest.TestCase):
    def setUp(self):
        self.spec, self.bundle, self.nodes = fixture()

    def requirement(self):
        return validate_requirement_semantic_text(self.spec)

    def coverage(self):
        return validate_semantic_text_coverage(self.spec, self.bundle, self.nodes)

    def test_valid_explicit_pair(self):
        self.assertEqual([], self.requirement())
        self.assertEqual([], self.coverage())

    def test_continuous_unmarked_prose_is_not_rejected(self):
        spec = {"uiModel": {"elements": [{"kind": "text", "properties": {"text": "进入区域：完成探索 / 返回基地。"}}]}}
        self.assertEqual([], validate_requirement_semantic_text(spec))
        self.assertEqual([], validate_semantic_text_coverage(spec, {}, {}))

    def test_invalid_text_values_return_errors(self):
        for value in (None, 0, True, [], {}, 10 ** 1000):
            with self.subTest(value_type=type(value).__name__):
                self.spec["uiModel"]["elements"][1]["properties"]["text"] = value
                self.assertTrue(self.requirement())
                self.assertTrue(self.coverage())

    def test_invalid_slot_values_return_errors(self):
        for value in (None, 0, "", [], {}, {"size": None}, {"horizontalAlignment": []}):
            with self.subTest(value_type=type(value).__name__):
                self.spec["uiModel"]["elements"][1]["panelSlotIntent"] = value
                self.assertTrue(self.requirement())

    def test_extreme_width_or_gap_returns_errors(self):
        for field in ("availableWidthPx", "gapPx"):
            for value in (None, True, 10 ** 1000, float("inf"), float("nan"), [], {}, -1, 0):
                with self.subTest(field=field, value_type=type(value).__name__):
                    self.spec, self.bundle, self.nodes = fixture()
                    self.spec["uiModel"]["elements"][0]["properties"]["semanticTextGroup"][field] = value
                    self.assertTrue(self.requirement())

    def test_out_of_scope_historical_group_is_skipped(self):
        for element in self.spec["uiModel"]["elements"]:
            element["inBuildScope"] = False
        self.spec["uiModel"]["elements"][0]["properties"]["semanticTextGroup"] = None
        self.assertEqual([], self.requirement())
        self.assertEqual([], self.coverage())

    def test_excluded_child_of_active_group_rejected(self):
        self.spec["uiModel"]["elements"][1]["inBuildScope"] = False
        self.assertTrue(self.requirement())

    def test_merged_element_nodes_rejected(self):
        self.bundle["nodeMappings"][2]["layoutNodeId"] = "A"
        self.assertTrue(self.coverage())

    def test_two_runtime_fields_on_first_node_rejected(self):
        self.bundle["nodeMappings"][1]["requirementRefs"].append("rt.b")
        self.bundle["nodeMappings"][2]["requirementRefs"].remove("rt.b")
        self.assertIn("text.semantic.runtime_mapping", [e["code"] for e in self.coverage()])

    def test_runtime_field_missing_mapping_rejected(self):
        self.bundle["nodeMappings"][1]["requirementRefs"].remove("rt.a")
        self.assertTrue(self.coverage())

    def test_duplicate_runtime_mapping_rejected(self):
        self.bundle["nodeMappings"].append({"assetId": "asset", "layoutNodeId": "A", "requirementRefs": ["rt.a"]})
        self.assertTrue(self.coverage())

    def test_multiple_runtime_fields_for_same_text_rejected(self):
        self.spec["uiModel"]["runtimeFields"][1]["elementId"] = "a"
        self.assertIn("text.semantic.runtime_unique", [e["code"] for e in self.coverage()])

    def test_every_flow_slot_field_preserved(self):
        for field, value in (("size", {"rule": "Auto"}), ("padding", [0, 0, 0, 0]),
                             ("horizontalAlignment", "Left"), ("verticalAlignment", "Bottom")):
            with self.subTest(field=field):
                self.spec, self.bundle, self.nodes = fixture()
                self.nodes["asset"]["B"]["flowSlot"][field] = value
                self.assertIn("text.semantic.flow_slot", [e["code"] for e in self.coverage()])

    def test_missing_or_null_lowered_slot_rejected(self):
        for value in (None, {}, [], 0):
            with self.subTest(value_type=type(value).__name__):
                self.nodes["asset"]["B"]["flowSlot"] = value
                self.assertTrue(self.coverage())

    def test_changed_parent_rect_rejected(self):
        self.nodes["asset"]["Group"]["rect"][0] += .01
        self.assertIn("text.semantic.geometry", [e["code"] for e in self.coverage()])

    def test_shortened_group_width_rejected(self):
        self.nodes["asset"]["Group"]["rect"][2] = .05
        self.assertIn("text.semantic.available_width", [e["code"] for e in self.coverage()])

    def test_changed_asset_canvas_cannot_shrink_budget(self):
        self.bundle["assets"][0]["referenceSize"][0] = 1000
        self.assertIn("text.semantic.available_width", [e["code"] for e in self.coverage()])

    def test_null_or_extreme_rects_return_errors(self):
        for value in (None, [], [0, 0, 10 ** 1000, 32], [0, 0, None, 32]):
            with self.subTest(value_type=type(value).__name__):
                self.nodes["asset"]["Group"]["rect"] = value
                self.assertTrue(self.coverage())

    def test_positive_requirement_wrap_width_rejected(self):
        self.spec["uiModel"]["elements"][1]["properties"]["wrapTextAt"] = 48
        self.assertTrue(self.requirement())

    def test_old_requirement_absent_wrap_width_compatible(self):
        self.spec["uiModel"]["elements"][1]["properties"].pop("wrapTextAt")
        self.assertEqual([], self.requirement())

    def test_lowered_wrap_width_must_be_explicit_zero(self):
        for value in (None, True, 24, [], 10 ** 1000):
            with self.subTest(value_type=type(value).__name__):
                self.nodes["asset"]["A"]["properties"]["wrapTextAt"] = value
                self.assertTrue(self.coverage())

    def test_capacity_and_layout_whitespace_rejected(self):
        self.spec["uiModel"]["elements"][1]["properties"]["text"] = "探索边境\n收集余波"
        self.assertTrue(self.requirement())

    def test_actual_latest_requirement_and_accepted_view(self):
        if not INTEGRATION.requirement or not INTEGRATION.view:
            self.skipTest("Pass --requirement and --view to read real current artifacts.")
        req_bytes, view_bytes = INTEGRATION.requirement.read_bytes(), INTEGRATION.view.read_bytes()
        req, view = json.loads(req_bytes), json.loads(view_bytes)
        self.assertEqual([], validate_requirement_semantic_text(req))
        self.assertEqual([], validate_requirement_semantic_text(view["requirement"]))
        self.assertEqual(req["revision"], view["revision"])
        self.assertEqual(req_bytes, INTEGRATION.requirement.read_bytes())
        self.assertEqual(view_bytes, INTEGRATION.view.read_bytes())

    def test_actual_latest_bundle_and_layouts(self):
        if not INTEGRATION.requirement or not INTEGRATION.bundle:
            self.skipTest("Pass --requirement and --bundle after the sole planner produces layouts.")
        req = json.loads(INTEGRATION.requirement.read_bytes())
        bundle = json.loads(INTEGRATION.bundle.read_bytes())
        self.assertEqual(req["revision"], bundle["requirement"]["revision"])
        nodes = {}
        for asset in bundle["assets"]:
            path = INTEGRATION.bundle.parent / asset["layoutSpecPath"]
            payload = path.read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), asset["layoutSpecSha256"])
            nodes[asset["id"]] = {n["id"]: n for n in json.loads(payload)["nodes"]}
        self.assertEqual([], validate_semantic_text_coverage(req, bundle, nodes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--requirement", type=Path)
    parser.add_argument("--view", type=Path)
    parser.add_argument("--bundle", type=Path)
    INTEGRATION, remaining = parser.parse_known_args()
    unittest.main(argv=[__file__, *remaining])
