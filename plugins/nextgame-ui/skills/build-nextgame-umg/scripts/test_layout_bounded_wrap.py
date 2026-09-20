"""Fixed bounded wrap remains distinct from auto-sized natural text growth."""
from copy import deepcopy
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from test_adaptive_layout_rules import adaptive_screen_spec
from test_designer_size_mode import CATALOG, RULES, SCHEMA
from prepare_build import build_plan
from validate_layout_spec import bounded_wrap_capacity, validate_spec


def bounded_spec():
    spec = adaptive_screen_spec()
    node = spec["nodes"][-1]
    node["anchor"] = "left-top"
    size = [0.14 * 2560, 0.08 * 1440]
    node["slotLayout"] = {"anchors": {"minimum": [0, 0], "maximum": [0, 0]},
        "offsets": {"left": (0.05 - 0.04) * 2560, "top": (0.12 - 0.1) * 1440, "right": size[0], "bottom": size[1]},
        "alignment": [0, 0], "autoSize": False}
    node["properties"].update(autoWrap=True, wrapTextAt=size[0])
    node["textCapacity"] = {"kind": "bounded-wrap/1", "capacitySize": size, "maxLines": 2, "evidenceId": "ev.bounded.text"}
    return spec


class BoundedWrapTests(unittest.TestCase):
    def test_explicit_bounded_two_line_capacity_preserves_auto_size_false(self):
        spec = bounded_spec()
        self.assertTrue(Draft202012Validator(SCHEMA).is_valid(spec))
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report["errors"])
        plan = build_plan(Path("bounded.json"), spec, CATALOG, RULES)
        slot = next(s for s in plan["steps"] if s["stepId"] == "set-slot-properties-label")
        self.assertFalse(slot["arguments"]["values"]["bAutoSize"])
        self.assertNotIn("textCapacity", str(plan["steps"]))

    def test_no_opt_in_keeps_old_failure_and_auto_sizing_remains_valid(self):
        spec = bounded_spec()
        spec["nodes"][-1].pop("textCapacity")
        self.assertIn("text.adaptive_slot.auto_size", {e["code"] for e in validate_spec(spec, CATALOG)["errors"]})
        spec["nodes"][-1]["slotLayout"]["autoSize"] = True
        self.assertTrue(validate_spec(spec, CATALOG)["valid"])

    def test_stable_center_and_right_placement_are_supported(self):
        for anchor, align in ((0.5, 0.5), (1, 1)):
            spec = bounded_spec()
            node, parent = spec["nodes"][-1], spec["nodes"][-2]
            slot = node["slotLayout"]
            slot["anchors"] = {"minimum": [anchor, 0], "maximum": [anchor, 0]}
            slot["alignment"] = [align, 0]
            slot["offsets"]["left"] -= anchor * parent["rect"][2] * 2560 - align * node["textCapacity"]["capacitySize"][0]
            self.assertTrue(bounded_wrap_capacity(node, parent, spec["referenceSize"]))

    def test_bad_capacity_or_wrong_scope_never_bypasses_legacy_guard(self):
        changes = [
            lambda n: n["textCapacity"].update(extra=True),
            lambda n: n["textCapacity"].update(kind="bounded-wrap/2"),
            lambda n: n["textCapacity"].update(maxLines=0),
            lambda n: n["textCapacity"].update(maxLines=2.5),
            lambda n: n["textCapacity"].update(maxLines=True),
            lambda n: n["textCapacity"].update(evidenceId="fake evidence"),
            lambda n: n["textCapacity"].update(capacitySize=[0, 10]),
            lambda n: n["textCapacity"].update(capacitySize=[999, 10]),
            lambda n: n["slotLayout"].update(autoSize=True),
            lambda n: n["slotLayout"]["offsets"].update(right=999),
            lambda n: n["slotLayout"]["offsets"].update(left=999),
            lambda n: n["slotLayout"]["anchors"].update(maximum=[1, 0]),
            lambda n: n["slotLayout"]["anchors"].update(minimum=[0.3, 0], maximum=[0.3, 0]),
            lambda n: n["properties"].update(wrapTextAt=0),
            lambda n: n["properties"].update(wrapTextAt=999),
            lambda n: n.update(role="visual.image"),
            lambda n: n.update(parent="button"),
            lambda n: n.update(rect=[0.05, 0.12, 0.13, 0.08]),
        ]
        for mutate in changes:
            spec = bounded_spec()
            mutate(spec["nodes"][-1])
            self.assertIn("text.capacity.invalid", {e["code"] for e in validate_spec(spec, CATALOG)["errors"]})

    def test_unknown_fields_rejected_by_closed_schema(self):
        spec = bounded_spec()
        spec["nodes"][-1]["textCapacity"]["verified"] = True
        self.assertFalse(Draft202012Validator(SCHEMA).is_valid(spec))


if __name__ == "__main__":
    unittest.main()
