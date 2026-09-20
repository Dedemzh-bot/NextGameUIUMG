"""Equal nominal Overlay bounds may still host one explicitly fixed axis."""
from copy import deepcopy
import unittest

from jsonschema import Draft202012Validator
from test_layout_size_dependencies import CATALOG, SCHEMA, dependency_spec
from validate_layout_spec import validate_spec


def fixture(width=None, height=52, horizontal="Fill", vertical="Top"):
    spec = dependency_spec()
    image = next(n for n in spec["nodes"] if n["id"] == "header-image")
    box = {
        "id": "header-size", "name": "SizeHeaderGraphic", "role": "container.size",
        "parent": "header", "rect": deepcopy(image["rect"]), "anchor": "left-top",
        "properties": {},
        "sizeBoxConstraints": {"version": 1, "widthOverride": width, "heightOverride": height},
        "overlaySlot": {"horizontalAlignment": horizontal, "verticalAlignment": vertical,
                        "padding": [0, 0, 0, 0]},
    }
    image["parent"] = box["id"]
    image["sizeBoxSlot"] = image.pop("overlaySlot")
    spec["nodes"].insert(3, box)
    return spec, box


class SizeBoxOverlayConstraintTests(unittest.TestCase):
    def assert_passes(self, spec):
        self.assertEqual([], list(Draft202012Validator(SCHEMA).iter_errors(spec)))
        report = validate_spec(spec, CATALOG)
        self.assertTrue(report["valid"], report)

    def assert_fill_rejected(self, spec):
        codes = {e["code"] for e in validate_spec(spec, CATALOG)["errors"]}
        self.assertIn("overlay.slot.full_region_fill", codes)

    def test_fixed_height_allows_vertical_independent_alignment(self):
        for alignment in ("Top", "Center", "Bottom"):
            with self.subTest(alignment=alignment):
                spec, box = fixture(vertical=alignment)
                self.assert_passes(spec)

    def test_fixed_width_allows_horizontal_independent_alignment(self):
        for alignment in ("Left", "Center", "Right"):
            with self.subTest(alignment=alignment):
                spec, box = fixture(width=400, height=None, horizontal=alignment, vertical="Fill")
                self.assert_passes(spec)

    def test_both_axes_require_their_own_constraint(self):
        spec, box = fixture(width=400, height=52, horizontal="Center", vertical="Center")
        self.assert_passes(spec)
        for key in ("widthOverride", "heightOverride"):
            broken = deepcopy(spec)
            next(n for n in broken["nodes"] if n["id"] == box["id"])["sizeBoxConstraints"][key] = None
            self.assert_fill_rejected(broken)

    def test_plain_image_cannot_claim_sizebox_exemption(self):
        spec = dependency_spec()
        image = next(n for n in spec["nodes"] if n["id"] == "header-image")
        image["overlaySlot"]["verticalAlignment"] = "Top"
        self.assert_fill_rejected(spec)
        image["sizeBoxConstraints"] = {"version": 1, "widthOverride": None, "heightOverride": 52}
        self.assert_fill_rejected(spec)

    def test_unconstrained_and_malformed_sizeboxes_do_not_bypass_fill(self):
        for constraints in (None, {"version": 1, "widthOverride": None, "heightOverride": None},
                            {"version": 1, "widthOverride": None, "heightOverride": True},
                            {"version": 1, "widthOverride": None, "heightOverride": 0}):
            spec, box = fixture()
            if constraints is None:
                box.pop("sizeBoxConstraints")
            else:
                box["sizeBoxConstraints"] = constraints
            self.assert_fill_rejected(spec)

    def test_full_fill_remains_valid_and_invalid_alignment_stays_invalid(self):
        self.assert_passes(dependency_spec())
        spec, box = fixture(vertical="Unknown")
        self.assert_fill_rejected(spec)
        self.assertIn("overlay.slot.vertical_alignment", {
            e["code"] for e in validate_spec(spec, CATALOG)["errors"]})


if __name__ == "__main__":
    unittest.main()
