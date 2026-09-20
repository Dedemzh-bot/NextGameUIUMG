#!/usr/bin/env python3
"""Explicit ButtonSlot lowering for every direct Button content class."""

from copy import deepcopy
from pathlib import Path
import unittest

from prepare_build import build_plan
from test_common_widget_rules import composite_state_panel_spec
from validate_layout_spec import load_json, validate_spec


ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_json(ROOT / "references/component-catalog.json")
RULES = load_json(ROOT / "references/rule-index.json")


def content_spec(role="visual.image"):
    spec = composite_state_panel_spec()
    spec["nodes"] = [node for node in spec["nodes"] if node["id"] not in {"tab-selected", "tab-unselected"}]
    content = next(node for node in spec["nodes"] if node["id"] == "tab-button-content")
    content.update(role=role, name={"visual.image": "ImgContent", "text.label": "TxtContent", "container.overlay": "OverContent", "container.canvas": "PanelContent"}[role])
    if role == "text.label":
        content["properties"] = {"text": "Action", "font": {"size": 24}, "color": {"r": 1, "g": 1, "b": 1, "a": 1}}
    return spec, content


class ButtonContentSlotTests(unittest.TestCase):
    def plan(self, spec):
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report["errors"])
        return build_plan(Path("button-content-slot.json"), spec, CATALOG, RULES)

    def rejected(self, spec, code):
        self.assertIn(code, {item["code"] for item in validate_spec(spec, CATALOG)["errors"]})
        with self.assertRaises(ValueError):
            build_plan(Path("button-content-slot.json"), spec, CATALOG, RULES)

    def test_explicit_slots_including_canvas_lower_exact_insets(self):
        for role in ("visual.image", "text.label", "container.overlay", "container.canvas"):
            with self.subTest(role=role):
                spec, content = content_spec(role)
                content["buttonSlot"]["padding"] = [2, 3, 5, 7]
                before = deepcopy(spec)
                plan = self.plan(spec)
                self.assertEqual(spec, before)
                steps = [step for step in plan["steps"] if "button-slot-properties-tab-button-content" in step["stepId"]]
                self.assertEqual([step["toolName"] for step in steps], ["list_properties", "get_properties", "set_properties"])
                self.assertEqual(steps[-1]["arguments"]["values"], {
                    "padding": {"left": 2, "top": 3, "right": 5, "bottom": 7},
                    "horizontalAlignment": "HAlign_Fill", "verticalAlignment": "VAlign_Fill",
                })
                self.assertEqual(steps[-1]["arguments"]["instance"], {"refPath": "${node.tab-button-content.returnValue.slot.refPath}"})
                self.assertEqual(plan, self.plan(spec))

    def test_legacy_omission_does_not_add_slot_writes(self):
        for role in ("visual.image", "text.label", "container.overlay"):
            with self.subTest(role=role):
                spec, content = content_spec(role)
                del content["buttonSlot"]
                self.assertFalse(any("button-slot-properties-tab-button-content" in step["stepId"] for step in self.plan(spec)["steps"]))

    def test_canvas_still_requires_explicit_fill_slot(self):
        spec, content = content_spec("container.canvas")
        self.plan(spec)
        del content["buttonSlot"]
        self.rejected(spec, "button.direct_canvas.slot.missing")

    def test_wrong_parent_and_root_cannot_declare_button_slot(self):
        spec, content = content_spec()
        content["parent"] = "header"
        self.rejected(spec, "button_slot.relationship")
        spec, content = content_spec()
        spec["nodes"][0]["buttonSlot"] = deepcopy(content["buttonSlot"])
        self.rejected(spec, "button_slot.relationship")

    def test_explicit_contract_must_remain_closed_and_finite(self):
        for role in ("visual.image", "container.canvas"):
            for padding in ([0, 0, 0], [0, True, 0, 0], [0, float("inf"), 0, 0], [0, float("nan"), 0, 0]):
                with self.subTest(role=role, padding=padding):
                    spec, content = content_spec(role)
                    content["buttonSlot"]["padding"] = padding
                    self.rejected(spec, "button.direct_canvas.slot.padding" if role == "container.canvas" else "button_slot.padding")
        spec, content = content_spec()
        content["buttonSlot"]["horizontalAlignment"] = "Center"
        self.rejected(spec, "button_slot.alignment")
        spec, content = content_spec()
        content["buttonSlot"]["guessedSize"] = 12
        self.rejected(spec, "button_slot.fields")
        spec, content = content_spec()
        content["buttonSlot"] = None
        self.rejected(spec, "button_slot.type")


if __name__ == "__main__":
    unittest.main()
