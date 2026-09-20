"""Compatibility and adversarial tests for explicit static /2 sizing proofs."""
from copy import deepcopy
import math
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from prepare_build import build_plan
from test_layout_size_dependencies import dependency_spec, proof_valid
from test_designer_size_mode import CATALOG, RULES, SCHEMA
from validate_layout_spec import validate_spec


def dependency_v2_spec(width=457.3333333333333):
    spec = dependency_spec()
    spec["referenceSize"] = [math.ceil(width), 232]
    spec["profile"]["hasText"] = True
    for node in spec["nodes"][1:]:
        node["rect"][0] *= width / math.ceil(width)
        node["rect"][2] *= width / math.ceil(width)
        if "brushImageSize" in node["properties"]:
            node["properties"]["brushImageSize"][0] = width
    content = spec["nodes"][1]
    content.update(role="container.size", name="SizeContent")
    content["sizeBoxConstraints"] = {"version": 1, "widthOverride": width, "heightOverride": None}
    content["slotLayout"]["offsets"]["right"] = width
    content["contentSizeProof"].update(kind="layout-dependency/2", minimumDesiredSize=[width, 232])
    for node in spec["nodes"][2:]:
        if node["parent"] == "content":
            node["parent"] = "flow"
    spec["nodes"].append({"id": "flow", "name": "VerFlow", "role": "container.vertical", "parent": "content",
                          "rect": deepcopy(content["rect"]), "anchor": "left-top", "properties": {},
                          "sizeBoxSlot": {"padding": [0, 0, 0, 0], "horizontalAlignment": "Fill", "verticalAlignment": "Fill"}})
    rect = deepcopy(spec["nodes"][2]["rect"])
    spec["nodes"].extend([
        {"id": "row", "name": "HorTitle", "role": "container.horizontal", "parent": "header", "rect": rect,
         "anchor": "left-top", "properties": {}, "overlaySlot": {"horizontalAlignment": "Fill", "verticalAlignment": "Fill", "padding": [0, 0, 0, 0]}},
        {"id": "title", "name": "TxtTitle", "role": "text.label", "parent": "row", "rect": rect,
         "anchor": "left-top", "properties": {"text": "Title", "font": {"size": 24}, "justification": "Left", "autoWrap": True, "wrapTextAt": width - 20, "color": {"r": 1, "g": 1, "b": 1, "a": 1}},
         "flowSlot": {"size": {"rule": "Fill", "weight": 1}, "padding": [0, 0, 0, 0], "horizontalAlignment": "Fill", "verticalAlignment": "Center"}},
        {"id": "arrow", "name": "ImgArrow", "role": "visual.image", "parent": "row", "rect": rect,
         "anchor": "left-top", "properties": {"brushImageSize": [20, 20]},
         "flowSlot": {"size": {"rule": "Auto"}, "padding": [0, 0, 0, 0], "horizontalAlignment": "Right", "verticalAlignment": "Center"}},
    ])
    return spec


class DependencyV2Tests(unittest.TestCase):
    def test_fractional_width_and_fill_text_have_real_static_authority(self):
        spec = dependency_v2_spec()
        self.assertTrue(proof_valid(spec))
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report["errors"])
        self.assertTrue(Draft202012Validator(SCHEMA).is_valid(spec))
        plan = build_plan(Path("v2.json"), spec, CATALOG, RULES)
        self.assertTrue(plan["steps"])
        self.assertNotIn("measuredDesiredSize", str(spec))

    def test_legacy_kind_still_rejects_horizontal_fill(self):
        spec = dependency_v2_spec()
        spec["nodes"][1]["contentSizeProof"]["kind"] = "layout-dependency/1"
        self.assertFalse(proof_valid(spec))
        self.assertTrue(proof_valid(dependency_spec()))

    def test_width_is_exact_not_arbitrarily_toleranced(self):
        spec = dependency_v2_spec()
        spec["nodes"][1]["contentSizeProof"]["minimumDesiredSize"][0] += 1e-9
        self.assertFalse(proof_valid(spec))

    def test_invalid_authority_sources_and_fill_are_rejected(self):
        changes = [
            ("no-width", lambda n: n["content"]["sizeBoxConstraints"].update(widthOverride=None)),
            ("fixed-height", lambda n: n["content"]["sizeBoxConstraints"].update(heightOverride=232)),
            ("broken-slot-authority", lambda n: n["row"]["overlaySlot"].update(horizontalAlignment="Left")),
            ("vertical-fill", lambda n: n["header"]["flowSlot"].update(size={"rule": "Fill", "weight": 1})),
            ("image-fill", lambda n: n["arrow"]["flowSlot"].update(size={"rule": "Fill", "weight": 1})),
            ("zero-weight", lambda n: n["title"]["flowSlot"]["size"].update(weight=0)),
            ("negative-weight", lambda n: n["title"]["flowSlot"]["size"].update(weight=-1)),
            ("negative-padding", lambda n: n["row"]["overlaySlot"].update(padding=[-1, 0, 0, 0])),
            ("infinite-padding", lambda n: n["row"]["overlaySlot"].update(padding=[math.inf, 0, 0, 0])),
            ("hidden-source", lambda n: n["header-image"]["properties"].update(visibility="Hidden")),
            ("collapsed-source", lambda n: n["header-image"]["properties"].update(visibility="Collapsed")),
            ("hidden-source-ancestor", lambda n: n["header"]["properties"].update(visibility="Hidden")),
            ("unknown-source", lambda n: n["content"]["contentSizeProof"].update(sourceNodeIds=["missing"])),
            ("unreachable-source", lambda n: n["header-image"].update(parent="absent")),
            ("cycle", lambda n: n["header"].update(parent="header-image")),
            ("source-duplicate", lambda n: n["content"]["contentSizeProof"].update(sourceNodeIds=["header-image", "header-image"])),
            ("fake-measured", lambda n: n["content"]["contentSizeProof"].update(measuredDesiredSize=[400, 232])),
            ("fake-verified", lambda n: n["content"]["contentSizeProof"].update(verified=True)),
            ("oversized-auto", lambda n: n["arrow"]["properties"].update(brushImageSize=[999, 20])),
            ("no-natural-height", lambda n: n["body-image"]["properties"].update(brushImageSize=[400, 0])),
            ("shifted-origin", lambda n: n["content"]["slotLayout"]["offsets"].update(left=1)),
        ]
        for label, mutate in changes:
            with self.subTest(label=label):
                spec = dependency_v2_spec()
                mutate({n["id"]: n for n in spec["nodes"]})
                self.assertFalse(proof_valid(spec))

    def test_unrelated_root_content_and_nonleaf_text_rejected(self):
        for parent in ("root", "title"):
            spec = dependency_v2_spec()
            sibling = deepcopy(spec["nodes"][-1])
            sibling.update(id="unrelated", parent=parent)
            spec["nodes"].append(sibling)
            self.assertFalse(proof_valid(spec))


if __name__ == "__main__":
    unittest.main()
