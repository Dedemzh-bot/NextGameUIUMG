#!/usr/bin/env python3
"""Regressions for LuaListView direction writes through the public planner."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from prepare_build import build_plan
from test_dynamic_list_rules import tile_container_spec
from test_prototype_screen_collections import screen_collections
from validate_layout_spec import load_json, validate_spec


SKILL_ROOT = Path(__file__).resolve().parent.parent
CATALOG = load_json(SKILL_ROOT / "references" / "component-catalog.json")
RULES = load_json(SKILL_ROOT / "references" / "rule-index.json")
SPEC_PATH = Path("list-orientation-regression.json")
OBJECT_TOOLS = "editor_toolset.toolsets.object.ObjectTools"

# The seven independent lobby endpoints retain their exact direction values.
ENDPOINTS = (
    ("el_navigation_collection", "ListNavigationCollection", "Orient_Horizontal"),
    ("el_currency_collection", "ListCurrencyCollection", "Orient_Horizontal"),
    ("el_metric_collection", "ListMetricCollection", "Orient_Horizontal"),
    ("el_daily_row_collection", "ListDailyRowCollection", "Orient_Vertical"),
    ("el_squad_slot_collection", "ListSquadSlotCollection", "Orient_Horizontal"),
    ("el_chat_line_collection", "ListChatLineCollection", "Orient_Vertical"),
    ("el_shortcut_collection", "ListShortcutCollection", "Orient_Horizontal"),
)


def lobby_collection_fixture() -> dict:
    """Valid, self-contained layout; no dependence on a user's saved project."""
    spec = screen_collections(mode="prototype")
    for node, (node_id, name, direction) in zip(spec["nodes"][1:], ENDPOINTS):
        node.update({"id": node_id, "name": name, "role": "collection.lua-list"})
        node["properties"].pop("entryWidth", None)
        node["properties"].pop("entryHeight", None)
        node["properties"]["orientation"] = direction

    # The currency endpoint remains a direct native Canvas child, with its
    # accepted right anchor, -12 inset, Auto Size, and original item ordering.
    currency = next(n for n in spec["nodes"] if n["id"] == "el_currency_collection")
    currency["rect"] = [0.71875, 0.011111111111111112, 0.16875, 0.03888888888888889]
    currency["parent"] = "reg_module_currency"
    currency["anchor"] = "right-top"
    currency["slotLayout"] = {
        "anchors": {"minimum": [1, 0], "maximum": [1, 0]},
        "offsets": {"left": -12, "top": 0, "right": 432, "bottom": 56},
        "alignment": [1, 0],
        "autoSize": True,
    }
    currency["adaptiveLayout"] = {
        "horizontal": "right", "vertical": "top",
        "reason": "Direct native Canvas Slot retains its right inset and Auto Size.",
    }
    parent = {
        "id": "reg_module_currency", "name": "PanelCurrency",
        "role": "container.canvas", "parent": "root",
        "rect": [0.7140625, 0.011111111111111112, 0.178125, 0.03888888888888889],
        "anchor": "right-top",
        "regionPurpose": currency.pop("regionPurpose"), "properties": {},
    }
    spec["nodes"].insert(1, parent)
    return spec


def legacy_catalog() -> dict:
    """Reproduce the obsolete capability exclusion without editing the catalog."""
    catalog = deepcopy(CATALOG)
    role = next(c for c in catalog["components"] if c["role"] == "collection.lua-list")
    role["writeUnsupportedProperties"] = ["orientation"]
    role["writeUnsupportedGuidance"] = {
        "orientation": "Vertical lists may keep the verified Orient_Vertical default; "
        "non-default directions require another verified setter.",
    }
    return catalog


def step_by_id(plan: dict, step_id: str) -> dict:
    return next(step for step in plan["steps"] if step["stepId"] == step_id)


class ListOrientationPlanTests(unittest.TestCase):
    def plan(self, spec: dict, catalog: dict | None = None) -> dict:
        selected_catalog = CATALOG if catalog is None else catalog
        report = validate_spec(spec, selected_catalog)
        self.assertTrue(report["valid"], report["errors"])
        return build_plan(SPEC_PATH, spec, selected_catalog, RULES)

    def test_all_seven_exact_endpoint_directions_are_written(self) -> None:
        spec = lobby_collection_fixture()
        snapshot = deepcopy(spec)
        plan = self.plan(spec)
        writes = [
            step for step in plan["steps"]
            if step["toolName"] == "set_properties"
            and "orientation" in step["arguments"].get("values", {})
        ]
        expected = {
            f"set-widget-properties-{node_id}": direction
            for node_id, _, direction in ENDPOINTS
        }
        self.assertEqual(len(writes), 7)
        self.assertEqual(
            {step["stepId"]: step["arguments"]["values"]["orientation"] for step in writes},
            expected,
        )
        self.assertEqual(spec, snapshot)
        for node_id, _, _ in ENDPOINTS:
            self.assertFalse(any(f"{node_id}: orientation" in warning for warning in plan["warnings"]))

    def test_each_orientation_write_keeps_discovery_read_and_reference_sequence(self) -> None:
        plan = self.plan(lobby_collection_fixture())
        for node_id, _, direction in ENDPOINTS:
            with self.subTest(endpoint=node_id):
                index = next(i for i, step in enumerate(plan["steps"]) if step["stepId"] == f"list-widget-properties-{node_id}")
                sequence = plan["steps"][index:index + 3]
                self.assertEqual([s["toolName"] for s in sequence], ["list_properties", "get_properties", "set_properties"])
                for step in sequence:
                    self.assertEqual(step["toolsetName"], OBJECT_TOOLS)
                    self.assertEqual(step["arguments"]["instance"], {"refPath": f"${{node.{node_id}.returnValue.widget.refPath}}"})
                self.assertIn("orientation", sequence[1]["arguments"]["properties"])
                self.assertEqual(sequence[2]["arguments"]["values"]["orientation"], direction)
                self.assertEqual(sequence[2]["assertion"], "returnValue must be true")

    def test_both_supported_direction_values_are_preserved_on_every_endpoint(self) -> None:
        for direction in ("Orient_Horizontal", "Orient_Vertical"):
            with self.subTest(direction=direction):
                spec = lobby_collection_fixture()
                for node in spec["nodes"]:
                    if node["role"] == "collection.lua-list":
                        node["properties"]["orientation"] = direction
                plan = self.plan(spec)
                for node_id, _, _ in ENDPOINTS:
                    self.assertEqual(step_by_id(plan, f"set-widget-properties-{node_id}")["arguments"]["values"]["orientation"], direction)

    def test_currency_native_canvas_slot_is_unchanged(self) -> None:
        plan = self.plan(lobby_collection_fixture())
        add = step_by_id(plan, "add-el_currency_collection")
        self.assertEqual(add["arguments"]["parentWidget"], {"refPath": "${node.reg_module_currency.returnValue.widget.refPath}"})
        self.assertEqual(step_by_id(plan, "add-reg_module_currency")["arguments"]["widgetClass"], {"refPath": "/Script/UMG.CanvasPanel"})
        values = step_by_id(plan, "set-slot-properties-el_currency_collection")["arguments"]["values"]
        self.assertEqual(values, {
            "layoutData": {
                "anchors": {"minimum": {"x": 1, "y": 0}, "maximum": {"x": 1, "y": 0}},
                "offsets": {"left": -12, "top": 0, "right": 432, "bottom": 56},
                "alignment": {"x": 1, "y": 0},
            },
            "bAutoSize": True,
            "zOrder": 0,
        })

    def test_plan_shape_and_all_other_operations_remain_identical(self) -> None:
        spec = lobby_collection_fixture()
        old_plan = self.plan(spec, legacy_catalog())
        new_plan = self.plan(spec)
        self.assertEqual(new_plan["version"], "0.2")
        self.assertEqual(new_plan.keys(), old_plan.keys())
        self.assertEqual(len(new_plan["steps"]), len(old_plan["steps"]))
        # Remove only the intended direction delta, then compare whole plans.
        for node_id, _, _ in ENDPOINTS:
            step_by_id(new_plan, f"get-widget-properties-{node_id}")["arguments"]["properties"].remove("orientation")
            del step_by_id(new_plan, f"set-widget-properties-{node_id}")["arguments"]["values"]["orientation"]
        prefixes = tuple(f"{node_id}: orientation is read-only" for node_id, _, _ in ENDPOINTS)
        old_plan["warnings"] = [warning for warning in old_plan["warnings"] if not warning.startswith(prefixes)]
        self.assertEqual(new_plan, old_plan)

    def test_unverified_tile_orientation_limitation_is_preserved(self) -> None:
        for direction in ("Orient_Horizontal", "Orient_Vertical"):
            with self.subTest(direction=direction):
                spec = tile_container_spec()
                spec["nodes"][1]["properties"]["orientation"] = direction
                plan = self.plan(spec)
                values = step_by_id(plan, "set-widget-properties-grid-tile")["arguments"]["values"]
                self.assertNotIn("orientation", values)
                self.assertNotIn("orientation", step_by_id(plan, "get-widget-properties-grid-tile")["arguments"]["properties"])
                self.assertTrue(any("grid-tile: orientation is read-only" in warning for warning in plan["warnings"]))
                self.assertEqual(plan, self.plan(spec, legacy_catalog()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
