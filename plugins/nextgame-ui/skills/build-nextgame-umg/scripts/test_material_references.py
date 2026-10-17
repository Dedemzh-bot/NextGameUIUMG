"""Source-evidence invariants, not a visual test or material-write capability."""
import json
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[3]
EVIDENCE = PLUGIN / "assets/material-reference-evidence/20260930"


class MaterialReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readback = json.loads((EVIDENCE / "actual-material-readback.json").read_text(encoding="utf-8"))
        cls.graph = json.loads((EVIDENCE / "actual-graph-readback.json").read_text(encoding="utf-8"))

    def material(self, name):
        return next(m for m in self.readback["materials"] if m["asset"]["path"].endswith("." + name))

    def graph_node(self, family, name):
        return self.graph["graphs"][f"/Game/UI/Materials/{family}.{family}:{name}"]["properties"]

    def test_read_only_provenance_and_six_unchanged_assets(self):
        self.assertEqual("nxue-agent", self.readback["acquisition"])
        self.assertTrue(self.readback["fallbackReason"])
        self.assertEqual(6, len(self.readback["sha256Before"]))
        self.assertEqual(self.readback["sha256Before"], self.readback["sha256After"])
        for call in self.graph["calls"]:
            self.assertIn(call["arguments"]["action"], ("list", "get"))
            self.assertTrue(call["result"]["ok"])
            self.assertFalse(call["result"]["data"]["target"]["isDirty"])

    def test_exact_widget_resources_and_parent_identity(self):
        for widget, seed, parent in (
            ("ImgCD", "Circular_Progress_Bar_CD_Inst", "Circular_Progress_Bar_mat"),
            ("GameImageBlack", "HaloMask_Scope1_Inst", "HaloMask_mat"),
        ):
            source = next(w for w in self.readback["widgets"] if w["target"]["widget"]["path"].endswith("." + widget))
            instance_path = self.material(seed)["asset"]["path"]
            self.assertEqual(instance_path, source["target"]["resource"]["path"])
            self.assertEqual(self.material(parent)["asset"]["path"],
                             self.graph["graphs"][instance_path]["properties"]["Parent"]["path"])

    def test_circular_progress_and_range_are_distinct(self):
        params = self.material("Circular_Progress_Bar_CD_Inst")["parameters"]
        self.assertEqual({"CutStartPivot", "Percent", "Clockwise", "CutPercent", "Opacity"},
                         set(params["scalar"]))
        self.assertEqual(0, params["scalar"]["Clockwise"])
        self.assertEqual(1, self.material("Circular_Progress_Bar_mat")["parameters"]["scalar"]["Clockwise"])
        self.assertFalse(params["static_switch"]["DebugAnimation"])
        self.assertEqual(33, len(self.material("Circular_Progress_Bar_mat")["expressions"]))
        product = self.graph_node("Circular_Progress_Bar_mat", "MaterialExpressionMultiply_7")
        self.assertEqual("MaterialExpressionScalarParameter_1", product["A"]["fields"]["Expression"]["name"])
        self.assertEqual("MaterialExpressionScalarParameter_11", product["B"]["fields"]["Expression"]["name"])

    def test_scale_components_follow_current_wiring_not_old_note(self):
        append = self.graph_node("Circular_Progress_Bar_mat", "MaterialExpressionAppendVector_1")
        self.assertEqual(3, append["A"]["fields"]["OutputIndex"])
        self.assertEqual(1, append["A"]["fields"]["MaskB"])
        self.assertEqual(4, append["B"]["fields"]["OutputIndex"])
        self.assertEqual(1, append["B"]["fields"]["MaskA"])

    def test_halo_actual_smoothstep_and_aspect_inputs(self):
        params = self.material("HaloMask_Scope1_Inst")["parameters"]
        self.assertAlmostEqual(0.45, params["scalar"]["Size"])
        self.assertAlmostEqual(0.01, params["scalar"]["SmoothValue"])
        self.assertEqual([2560, 1440, 0, 1], params["vector"]["Param"])
        self.assertEqual({}, params["static_switch"])
        self.assertEqual(17, len(self.material("HaloMask_mat")["expressions"]))
        step = self.graph_node("HaloMask_mat", "MaterialExpressionSmoothStep_0")
        for field, node in (("Min", "MaterialExpressionDistance_0"),
                            ("Max", "MaterialExpressionAdd_1"),
                            ("Value", "MaterialExpressionScalarParameter_1")):
            self.assertEqual(node, step[field]["fields"]["Expression"]["name"])
        aspect = self.graph_node("HaloMask_mat", "MaterialExpressionDivide_0")
        self.assertEqual(1, aspect["A"]["fields"]["MaskR"])
        self.assertEqual(1, aspect["B"]["fields"]["MaskG"])


if __name__ == "__main__":
    unittest.main()
