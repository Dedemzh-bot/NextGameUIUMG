#!/usr/bin/env python3
"""Bundle width capability uses executed SizeBox overrides, never nominal rects."""

from copy import deepcopy
import unittest

from _bundle_capabilities import _content_width_bound, planned_size_proofs, validate_content_height
from test_build_bundle_capabilities import codes, content_fixture


def size_box_fixture():
    bundle, operation, layout, host = content_fixture()
    content = layout["nodes"][1]
    proof = content.pop("contentSizeProof")
    proof["minimumDesiredSize"][0] = 456
    slot = content.pop("slotLayout")
    content["parent"] = "width"
    content["sizeBoxSlot"] = {"padding": [0, 0, 0, 0], "horizontalAlignment": "Fill", "verticalAlignment": "Fill"}
    layout["nodes"].insert(1, {
        "id": "width", "parent": "root", "role": "container.size", "slotLayout": slot,
        "sizeBoxConstraints": {"version": 1, "widthOverride": 456, "heightOverride": None},
        "contentSizeProof": proof, "rect": [0, 0, 0.01, 0.01],
    })
    layout["referenceSize"][0] = 456
    operation["placementContract"]["childSizingCompatibility"].update(fixedWidth=456, sourceLayoutNodeIds=["width"])
    return bundle, operation, layout, host


def width_of(layout):
    by_id = {node["id"]: node for node in layout["nodes"]}
    return _content_width_bound(by_id["width"], by_id, set())


class SizeBoxContentWidthTests(unittest.TestCase):
    def test_fixed_width_natural_height_bundle_uses_declared_setter(self):
        bundle, op, layout, host = size_box_fixture()
        self.assertEqual(width_of(layout), 456)
        self.assertEqual(validate_content_height(bundle, op, "$.op", layout, host), [])
        self.assertNotIn("measuredDesiredSize", planned_size_proofs(layout)[0])
        layout["nodes"][1]["rect"] = [0, 0, 1, 1]
        self.assertEqual(width_of(layout), 456)

    def test_null_width_inherits_real_child_width_not_rect_or_disabled_raw_value(self):
        _, _, layout, _ = size_box_fixture()
        layout["nodes"][1]["sizeBoxConstraints"].update(widthOverride=None, heightOverride=456)
        self.assertEqual(width_of(layout), 368)
        layout["nodes"][1]["properties"] = {"widthOverride": 999, "bOverride_WidthOverride": False}
        self.assertIsNone(width_of(layout))

    def test_wrong_width_does_not_pass_from_nominal_rect(self):
        bundle, op, layout, host = size_box_fixture()
        layout["nodes"][1]["sizeBoxConstraints"]["widthOverride"] = 455
        self.assertEqual(width_of(layout), 455)
        self.assertIn("operation.child_content_proof", codes(validate_content_height(bundle, op, "$.op", layout, host)))

    def test_malformed_or_unexecuted_constraints_cannot_supply_a_bound(self):
        for value in (None, {}, {"version": 1, "widthOverride": 456},
                      {"version": 1, "widthOverride": 456, "heightOverride": None, "bOverride_WidthOverride": False},
                      {"version": 1, "widthOverride": None, "heightOverride": None}):
            _, _, layout, _ = size_box_fixture()
            layout["nodes"][1]["sizeBoxConstraints"] = value
            self.assertIsNone(width_of(layout))
        for value in (0, -1, True, "456", float("inf"), float("nan"), 10**1000):
            _, _, layout, _ = size_box_fixture()
            layout["nodes"][1]["sizeBoxConstraints"]["widthOverride"] = value
            self.assertIsNone(width_of(layout))

    def test_missing_multiple_or_nonfill_children_are_not_proved(self):
        for mutate in (
            lambda layout: layout["nodes"][2].update(parent="root"),
            lambda layout: layout["nodes"].append({**deepcopy(layout["nodes"][2]), "id": "extra"}),
            lambda layout: layout["nodes"][2].pop("sizeBoxSlot"),
            lambda layout: layout["nodes"][2]["sizeBoxSlot"].update(horizontalAlignment="Left"),
            lambda layout: layout["nodes"][2]["sizeBoxSlot"].update(padding=[1, 0, 0, 0]),
        ):
            _, _, layout, _ = size_box_fixture()
            mutate(layout)
            self.assertIsNone(width_of(layout))

    def test_disabled_width_cannot_trust_unknown_or_cyclic_descendant(self):
        _, _, layout, _ = size_box_fixture()
        layout["nodes"][1]["sizeBoxConstraints"].update(widthOverride=None, heightOverride=456)
        layout["nodes"][2]["role"] = "container.canvas"
        self.assertIsNone(width_of(layout))
        by_id = {node["id"]: node for node in layout["nodes"]}
        self.assertIsNone(_content_width_bound(by_id["width"], by_id, {"width"}))


if __name__ == "__main__":
    unittest.main()
