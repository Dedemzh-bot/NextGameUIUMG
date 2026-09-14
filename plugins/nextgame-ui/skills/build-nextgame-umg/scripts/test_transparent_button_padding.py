#!/usr/bin/env python3
"""Native padding must not inset an explicitly transparent four-state hit area."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from prepare_build import build_plan
from test_button_brushes import button_node, step_by_id
from test_common_widget_rules import composite_state_panel_spec
from validate_layout_spec import load_json, validate_spec


SKILL_ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_json(SKILL_ROOT / "references" / "component-catalog.json")
RULES = load_json(SKILL_ROOT / "references" / "rule-index.json")
STATES = ("Normal", "Hovered", "Pressed", "Disabled")
ZERO_PADDING = {"left": 0, "top": 0, "right": 0, "bottom": 0}
SPEC_PATH = Path("transparent-button-padding-regression.json")


def style_values(plan: dict) -> dict:
    return step_by_id(plan, "set-widget-properties-tab-button")["arguments"]["values"]["widgetStyle"]


class TransparentButtonPaddingTests(unittest.TestCase):
    def plan(self, spec: dict) -> dict:
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report["errors"])
        return build_plan(SPEC_PATH, spec, CATALOG, RULES)

    def test_four_transparent_states_zero_normal_and_pressed_style_padding(self) -> None:
        spec = composite_state_panel_spec()
        button_node(spec)["properties"]["buttonBrushes"] = dict.fromkeys(STATES, "NoDrawType")
        snapshot = deepcopy(spec)
        style = style_values(self.plan(spec))
        expected = {state.lower(): {"drawAs": "NoDrawType"} for state in STATES}
        expected.update(normalPadding=ZERO_PADDING, pressedPadding=ZERO_PADDING)
        self.assertEqual(style, expected)
        self.assertEqual(spec, snapshot)

    def test_each_omitted_state_retains_partial_style_without_padding(self) -> None:
        for omitted in STATES:
            with self.subTest(omitted=omitted):
                spec = composite_state_panel_spec()
                brushes = {state: "NoDrawType" for state in STATES if state != omitted}
                button_node(spec)["properties"]["buttonBrushes"] = brushes
                self.assertEqual(style_values(self.plan(spec)), {state.lower(): {"drawAs": value} for state, value in brushes.items()})

    def test_each_nontransparent_state_preserves_existing_style_lowering(self) -> None:
        for state in STATES:
            for draw_type in ("Box", "Border", "Image", "RoundedBox"):
                with self.subTest(state=state, draw_type=draw_type):
                    spec = composite_state_panel_spec()
                    brushes = dict.fromkeys(STATES, "NoDrawType")
                    brushes[state] = draw_type
                    button_node(spec)["properties"]["buttonBrushes"] = brushes
                    self.assertEqual(style_values(self.plan(spec)), {name.lower(): {"drawAs": value} for name, value in brushes.items()})

    def test_omitted_brushes_do_not_add_style_or_padding(self) -> None:
        plan = self.plan(composite_state_panel_spec())
        for step in plan["steps"]:
            self.assertNotIn("widgetStyle", step["arguments"].get("values", {}))
            self.assertNotIn("widgetStyle", step["arguments"].get("properties", []))

    def test_transparent_padding_uses_existing_style_discover_read_set_steps(self) -> None:
        spec = composite_state_panel_spec()
        button_node(spec)["properties"]["buttonBrushes"] = dict.fromkeys(STATES, "NoDrawType")
        plan = self.plan(spec)
        index = next(i for i, step in enumerate(plan["steps"]) if step["stepId"] == "list-widget-properties-tab-button")
        sequence = plan["steps"][index:index + 3]
        self.assertEqual([step["toolName"] for step in sequence], ["list_properties", "get_properties", "set_properties"])
        for step in sequence:
            self.assertEqual(step["toolsetName"], "editor_toolset.toolsets.object.ObjectTools")
            self.assertEqual(step["arguments"]["instance"], {"refPath": "${node.tab-button.returnValue.widget.refPath}"})
        self.assertEqual(sequence[1]["arguments"]["properties"], ["bIsEnabled", "widgetStyle"])
        self.assertEqual(sequence[2]["assertion"], "returnValue must be true")

    def test_other_plan_operations_and_zero_fill_button_slot_remain_unchanged(self) -> None:
        spec = composite_state_panel_spec()
        brushes = dict.fromkeys(STATES, "NoDrawType")
        brushes["Disabled"] = "Box"
        button_node(spec)["properties"]["buttonBrushes"] = brushes
        before = self.plan(spec)
        brushes["Disabled"] = "NoDrawType"
        after = self.plan(spec)
        self.assertEqual(len(before["steps"]), len(after["steps"]))
        slot = step_by_id(after, "set-button-slot-properties-tab-button-content")["arguments"]["values"]
        self.assertEqual(slot, {"padding": ZERO_PADDING, "horizontalAlignment": "HAlign_Fill", "verticalAlignment": "VAlign_Fill"})
        style = style_values(after)
        del style["normalPadding"]
        del style["pressedPadding"]
        style["disabled"]["drawAs"] = "Box"
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
