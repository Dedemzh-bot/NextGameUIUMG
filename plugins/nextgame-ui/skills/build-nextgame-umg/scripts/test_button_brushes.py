#!/usr/bin/env python3
"""Validate and plan only explicitly declared native Button brush draw types."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from prepare_build import build_plan
from test_common_widget_rules import composite_state_panel_spec
from validate_layout_spec import load_json, validate_spec


SKILL_ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_json(SKILL_ROOT / "references" / "component-catalog.json")
RULES = load_json(SKILL_ROOT / "references" / "rule-index.json")
SPEC_PATH = Path("button-brushes-regression.json")
DRAW_TYPES = ("NoDrawType", "Box", "Border", "Image", "RoundedBox")
STATE_NAMES = ("Normal", "Hovered", "Pressed", "Disabled")


def button_node(spec: dict) -> dict:
    return next(node for node in spec["nodes"] if node["id"] == "tab-button")


def step_by_id(plan: dict, step_id: str) -> dict:
    return next(step for step in plan["steps"] if step["stepId"] == step_id)


class ButtonBrushesTests(unittest.TestCase):
    def plan(self, spec: dict) -> dict:
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report["errors"])
        return build_plan(SPEC_PATH, spec, CATALOG, RULES)

    def assert_rejected(self, spec: dict, code: str) -> None:
        report = validate_spec(spec, CATALOG)
        self.assertFalse(report["valid"])
        self.assertIn(code, {item["code"] for item in report["errors"]})
        with self.assertRaises(ValueError):
            build_plan(SPEC_PATH, spec, CATALOG, RULES)

    def test_three_accepted_states_lower_to_partial_widget_style(self) -> None:
        spec = composite_state_panel_spec()
        button_node(spec)["properties"]["buttonBrushes"] = {
            "Normal": "NoDrawType", "Hovered": "NoDrawType", "Pressed": "NoDrawType",
        }
        snapshot = deepcopy(spec)
        plan = self.plan(spec)
        self.assertEqual(spec, snapshot)
        self.assertEqual(
            step_by_id(plan, "set-widget-properties-tab-button")["arguments"]["values"],
            {
                "bIsEnabled": True,
                "widgetStyle": {
                    "normal": {"drawAs": "NoDrawType"},
                    "hovered": {"drawAs": "NoDrawType"},
                    "pressed": {"drawAs": "NoDrawType"},
                },
            },
        )

    def test_each_state_and_draw_type_passes_through_without_defaults(self) -> None:
        for state in STATE_NAMES:
            for draw_type in DRAW_TYPES:
                with self.subTest(state=state, draw_type=draw_type):
                    spec = composite_state_panel_spec()
                    button_node(spec)["properties"]["buttonBrushes"] = {state: draw_type}
                    values = step_by_id(self.plan(spec), "set-widget-properties-tab-button")["arguments"]["values"]
                    self.assertEqual(values["widgetStyle"], {state.lower(): {"drawAs": draw_type}})

    def test_state_output_order_is_deterministic(self) -> None:
        first = composite_state_panel_spec()
        second = deepcopy(first)
        button_node(first)["properties"]["buttonBrushes"] = dict(zip(STATE_NAMES, DRAW_TYPES))
        button_node(second)["properties"]["buttonBrushes"] = dict(reversed(list(button_node(first)["properties"]["buttonBrushes"].items())))
        first_plan, second_plan = self.plan(first), self.plan(second)
        self.assertEqual(first_plan, second_plan)
        style = step_by_id(second_plan, "set-widget-properties-tab-button")["arguments"]["values"]["widgetStyle"]
        self.assertEqual(list(style), [state.lower() for state in STATE_NAMES])

    def test_existing_properties_structure_and_step_contracts_are_unchanged(self) -> None:
        spec = composite_state_panel_spec()
        before = self.plan(spec)
        button_node(spec)["properties"]["buttonBrushes"] = {"Normal": "NoDrawType"}
        after = self.plan(spec)
        self.assertEqual(after["version"], "0.2")
        self.assertEqual(after.keys(), before.keys())
        self.assertEqual(len(after["steps"]), len(before["steps"]))
        properties = step_by_id(after, "get-widget-properties-tab-button")["arguments"]["properties"]
        properties.remove("widgetStyle")
        del step_by_id(after, "set-widget-properties-tab-button")["arguments"]["values"]["widgetStyle"]
        self.assertEqual(after, before)

    def test_write_uses_existing_objecttools_discover_read_set_sequence(self) -> None:
        spec = composite_state_panel_spec()
        button_node(spec)["properties"]["buttonBrushes"] = {"Normal": "Box"}
        plan = self.plan(spec)
        index = next(i for i, step in enumerate(plan["steps"]) if step["stepId"] == "list-widget-properties-tab-button")
        sequence = plan["steps"][index:index + 3]
        self.assertEqual([step["toolName"] for step in sequence], ["list_properties", "get_properties", "set_properties"])
        for step in sequence:
            self.assertEqual(step["toolsetName"], "editor_toolset.toolsets.object.ObjectTools")
            self.assertEqual(step["arguments"]["instance"], {"refPath": "${node.tab-button.returnValue.widget.refPath}"})
        self.assertIn("widgetStyle", sequence[1]["arguments"]["properties"])
        self.assertEqual(sequence[2]["assertion"], "returnValue must be true")

    def test_omitted_contract_does_not_add_brush_writes(self) -> None:
        plan = self.plan(composite_state_panel_spec())
        for step in plan["steps"]:
            self.assertNotIn("widgetStyle", step["arguments"].get("values", {}))
            self.assertNotIn("widgetStyle", step["arguments"].get("properties", []))

    def test_rejects_empty_and_nonobject_contracts(self) -> None:
        for value in ({}, None, [], "NoDrawType", True, 1):
            with self.subTest(value=value):
                spec = composite_state_panel_spec()
                button_node(spec)["properties"]["buttonBrushes"] = value
                self.assert_rejected(spec, "button.brushes.type")

    def test_rejects_unknown_or_wrong_case_state_names(self) -> None:
        for state in ("normal", "Hovered ", "Focused", "widgetStyle", "", 1):
            with self.subTest(state=state):
                spec = composite_state_panel_spec()
                button_node(spec)["properties"]["buttonBrushes"] = {state: "Box"}
                self.assert_rejected(spec, "button.brushes.state")

    def test_rejects_invalid_draw_types_and_nested_unreal_structs(self) -> None:
        for value in ("None", "box", "NoDrawType ", "", None, True, 1, [], {"drawAs": "Box"}):
            with self.subTest(value=value):
                spec = composite_state_panel_spec()
                button_node(spec)["properties"]["buttonBrushes"] = {"Normal": value}
                self.assert_rejected(spec, "button.brushes.draw_as")

    def test_rejects_nonbutton_use_and_raw_widget_style_bypass(self) -> None:
        spec = composite_state_panel_spec()
        spec["nodes"][0]["properties"]["buttonBrushes"] = {"Normal": "NoDrawType"}
        self.assert_rejected(spec, "button.brushes.role")
        spec = composite_state_panel_spec()
        button_node(spec)["properties"]["widgetStyle"] = {"normal": {"drawAs": "NoDrawType"}}
        self.assert_rejected(spec, "node.property.unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
