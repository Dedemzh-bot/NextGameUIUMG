"""Synthetic offline regressions. No production receipts or Editor connection."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from existing_asset_update import (CAPABILITY, PLAN_KIND, PLUGIN_ROOT, _art_module, asset_path,
    _merge_observed, _observed_class_matches, build_update_plan, source_entries, validate_bundle_layout,
    validate_existing_asset_update)
from prepare_build import build_plan
from validate_layout_spec import validate_spec

ANALYSIS = PLUGIN_ROOT / "skills/analyze-nextgame-ui-requirements"
ART = PLUGIN_ROOT / "skills/refine-nextgame-ui-art"
sys.path.append(str(ANALYSIS / "scripts"))
sys.path.append(str(ART / "scripts"))
from _contract_common import compute_approved_content_sha256, load_json
from accepted_build_view import build_accepted_build_view
from validate_build_bundle import DEFAULT_SCHEMA as BUNDLE_SCHEMA, validate_build_bundle
from validate_requirement_spec import DEFAULT_SCHEMA as REQUIREMENT_SCHEMA, validate_requirement_spec
from execute_plan import execute
from execute_plan_programmatic import require_official_operations


PATH = "/Game/UI/UMG/Test/Widgets/uw_legacy_entry"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def bind(path):
    return {"path": str(path), "sha256": sha(path)}


def codes(report):
    return {e["code"] for e in report["errors"]}


def fixture(root: Path, *, panels=2):
    """Unconventional legacy names and native classes intentionally stay unchanged."""
    widgets = [
        {"widgetName": "CanvasPanel_17", "classPath": "/Script/UMG.CanvasPanel", "parentWidgetName": None,
         "isVariable": False, "properties": {"visibility": "SelfHitTestInvisible"},
         "slot": {"classPath": None, "properties": {}}},
    ]
    for index in range(panels):
        widgets.append({"widgetName": "Overlay_" + str(index), "classPath": "/Script/UMG.Overlay",
            "parentWidgetName": "CanvasPanel_17", "isVariable": True,
            "properties": {"visibility": "Collapsed" if index else "SelfHitTestInvisible"},
            "slot": {"classPath": "/Script/UMG.CanvasPanelSlot", "properties": {"zOrder": index}}})
    widgets.extend([
        {"widgetName": "TextBlock_03", "classPath": "/Script/UMG.TextBlock", "parentWidgetName": "CanvasPanel_17",
         "isVariable": True, "properties": {"visibility": "SelfHitTestInvisible", "text": "Unchanged content",
             "font": {"size": 20, "typefaceFontName": "Regular"}, "renderOpacity": 1.0},
         "slot": {"classPath": "/Script/UMG.CanvasPanelSlot", "properties": {"zOrder": 0}}},
        {"widgetName": "Image_42", "classPath": "/Script/UMG.Image", "parentWidgetName": "CanvasPanel_17",
         "isVariable": False, "properties": {"visibility": "Hidden", "brush": {"imageSize": {"x": 32, "y": 32}}},
         "slot": {"classPath": "/Script/UMG.CanvasPanelSlot", "properties": {"zOrder": 2}}},
        {"widgetName": "List_09", "classPath": "/Script/Legacy.UnsupportedList", "parentWidgetName": "CanvasPanel_17",
         "isVariable": True, "properties": {"visibility": "SelfHitTestInvisible",
             "entryWidgetClass": {"refPath": "/Game/UI/UMG/Test/Widgets/uw_old.uw_old_C"}},
         "slot": {"classPath": "/Script/UMG.CanvasPanelSlot", "properties": {"zOrder": 3}}},
    ])
    snapshot = {"kind": "nextgame-ui-art-snapshot", "version": 1,
        "capturedAt": "2026-10-14T00:00:00Z", "acquisition": {"method": "fixture"},
        "assets": [{"assetPath": PATH, "parentClassPath": "/Script/Legacy.NativeEntry",
            "designSizeMode": "Desired", "protectedReferences": ["TextBlock_03", "List_09"],
            "referencesDigest": "a" * 64, "referencesComplete": False, "widgets": widgets}]}
    object_path = PATH + "." + PATH.rsplit("/", 1)[-1]

    def ref(name):
        return {"refPath": object_path + ":WidgetTree." + name} if name else "None"

    raw = {"info": {"parentClass": {"refPath": "/Script/Legacy.NativeEntry"}}, "widgets": [
        {"widgetName": w["widgetName"], "widget": ref(w["widgetName"]), "parent": ref(w["parentWidgetName"]),
         "namedSlotHost": "None", "widgetClassPath": {"refPath": w["classPath"]},
         "bIsVariable": w["isVariable"], "bInherited": False,
         "slot": ref(w["widgetName"] + "_slot") if w["slot"]["classPath"] else "None"} for w in widgets]}
    snapshot_path, raw_path = write(root / "snapshot.json", snapshot), write(root / "raw-tree.json", raw)
    ids = {w["widgetName"]: "node-" + str(i) for i, w in enumerate(widgets)}
    nodes = [{"id": ids[w["widgetName"]], "name": w["widgetName"], "classPath": w["classPath"],
        "parent": ids.get(w["parentWidgetName"]), "isVariable": w["isVariable"],
        "role": "screen.root" if w["parentWidgetName"] is None else
                "text.label" if w["classPath"].endswith(".TextBlock") else
                "visual.image" if w["classPath"].endswith(".Image") else
                "container.overlay" if w["classPath"].endswith(".Overlay") else "legacy.retained",
        "rect": [0, 0, 1, 1], "properties": {}, "slotClassPath": w["slot"]["classPath"],
        "nativeProperties": {}, "nativeSlot": {}} for w in widgets]
    text = next(n for n in nodes if n["name"] == "TextBlock_03")
    text["nativeProperties"] = {"font": {"size": 22}}
    text["nativeSlot"] = {"zOrder": 5}
    layout = {"version": "0.3", "capability": CAPABILITY, "mode": "production",
        "asset": {"folder": PATH.rsplit("/", 1)[0], "name": PATH.rsplit("/", 1)[-1]},
        "referenceSize": [100, 40], "profile": {"assetKind": "child-widget", "listRole": "entry", "designSizeMode": "Desired"},
        "baseline": {"snapshot": bind(snapshot_path), "rawTree": bind(raw_path),
                     "stateSha256": _art_module("art_common").state_hash(snapshot)},
        "nodes": nodes}
    return layout, snapshot, raw


def requirement_fixture(layout):
    """A fresh synthetic accepted Requirement; original example provenance is not evidence."""
    r = load_json(ANALYSIS / "assets/example-composite-tabs-requirement.json")
    r["request"]["purpose"] = "SYNTHETIC TEST: preserve legacy native tree and change supported properties."
    r["normalization"]["aliases"] = [dict(r["normalization"]["aliases"][0],
        canonicalId="evidence-selected-tab")]
    r["claims"] = [dict(r["claims"][0], id="claim-legacy-update", type="explicit-requirement",
        statement="SYNTHETIC TEST accepted native targets and preserved identities.", subjectRefs=[])]
    claim, evidence = ["claim-legacy-update"], ["evidence-selected-tab"]
    region = dict(r["uiModel"]["regions"][0], id="region-legacy", parentRegionId=None, bounds=[0, 0, 1, 1],
                  evidenceIds=evidence, claimIds=claim)
    elements = [{
        "id": "element-" + n["id"], "kind": "text" if n["role"] == "text.label" else
            "image" if n["role"] == "visual.image" else "panel" if n["role"].startswith(("screen.", "container.")) else "other",
        "nameHint": n["name"], "regionId": region["id"],
        "parentElementId": "element-" + n["parent"] if n["parent"] else None,
        "familyId": None, "runtimeControlled": n["isVariable"], "inBuildScope": True,
        "evidenceIds": evidence, "claimIds": claim,
        "properties": {"nativeProperties": copy.deepcopy(n["nativeProperties"]), "nativeSlot": copy.deepcopy(n["nativeSlot"]),
            "targetClassPath": n["classPath"], "observedIsVariable": n["isVariable"],
            "observedParentWidgetName": next((p["name"] for p in layout["nodes"] if p["id"] == n["parent"]), None)}
    } for n in layout["nodes"]]
    r["uiModel"] = {"regions": [region], "componentFamilies": [], "elements": elements,
        "collections": [], "runtimeFields": [], "responsiveIntent": []}
    r["stateModels"], r["assumptions"], r["questions"] = [], [], []
    r.pop("reviewResolutions", None)
    r["acceptanceCriteria"] = [{"id": "criterion-legacy", "description": "Synthetic native update", "inBuildScope": True, "claimIds": claim}]
    r["assetPlan"] = [{
        "id": "asset-legacy", "assetPath": asset_path(layout), "assetKind": "list-entry",
        "referenceSize": layout["referenceSize"], "layoutSpecPath": "layout.json",
        "dependsOnAssetIds": [], "buildOrder": 0, "inBuildScope": True,
        "coversRegionIds": [region["id"]], "coversElementIds": [e["id"] for e in elements],
        "coversCollectionIds": [], "coversStateModelIds": [], "evidenceIds": evidence, "claimIds": claim,
    }]
    r["target"].update(assetKind="child-widget", designCanvas=layout["referenceSize"], targetAssetPaths=[asset_path(layout)])
    r["claims"][0]["subjectRefs"] = [region["id"], "asset-legacy", "criterion-legacy"] + [e["id"] for e in elements]
    r["reviewGate"].update(reviewedBy="synthetic-fixture", notes=["SYNTHETIC TEST ONLY"], acceptedClaimIds=claim, rejectedClaimIds=[])
    r["reviewGate"]["approvedContentSha256"] = compute_approved_content_sha256(r)
    return r


class ExistingAssetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nextgame-existing-update-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.layout, self.snapshot, self.raw = fixture(self.root)
        self.path = write(self.root / "layout.json", self.layout)

    def validate(self, layout=None):
        return validate_spec(self.layout if layout is None else layout, {}, spec_path=self.path)

    def text(self):
        return next(n for n in self.layout["nodes"] if n["name"] == "TextBlock_03")

    def refresh_evidence(self):
        self.layout["baseline"]["snapshot"] = bind(write(self.root / "snapshot.json", self.snapshot))
        self.layout["baseline"]["rawTree"] = bind(write(self.root / "raw-tree.json", self.raw))
        self.layout["baseline"]["stateSha256"] = _art_module("art_common").state_hash(self.snapshot)
        write(self.path, self.layout)

    def canvas_slot(self, name="TextBlock_03", minimum=(0, 0), maximum=None, alignment=None):
        maximum = minimum if maximum is None else maximum
        alignment = minimum if alignment is None else alignment
        widget = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == name)
        widget["slot"]["properties"] = {"zOrder": 0, "layoutData": {
            "anchors": {"minimum": dict(zip(("x", "y"), minimum)), "maximum": dict(zip(("x", "y"), maximum))},
            "alignment": dict(zip(("x", "y"), alignment)),
            "offsets": {"left": 1, "top": 2, "right": 32, "bottom": 40},
        }}
        self.refresh_evidence()
        return next(n for n in self.layout["nodes"] if n["name"] == name)

    def flow_slot(self, box="HorizontalBox", rule="Automatic", value=1):
        parent = next(n for n in self.layout["nodes"] if n["name"] == "Overlay_0")
        parent["classPath"] = "/Script/UMG." + box
        parent["role"] = "container.horizontal" if box == "HorizontalBox" else "container.vertical"
        parent_widget = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == parent["name"])
        parent_widget["classPath"] = parent["classPath"]
        raw_parent = next(w for w in self.raw["widgets"] if w["widgetName"] == parent["name"])
        raw_parent["widgetClassPath"] = {"refPath": parent["classPath"]}
        node = self.text()
        node["parent"], node["slotClassPath"], node["nativeSlot"] = parent["id"], "/Script/UMG." + box + "Slot", {}
        widget = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == node["name"])
        widget["parentWidgetName"] = parent["name"]
        widget["slot"] = {"classPath": node["slotClassPath"], "properties": {
            "size": {"sizeRule": rule, "value": value},
            "padding": {"left": 0, "top": 0, "right": 10, "bottom": 0},
            "horizontalAlignment": "HAlign_Fill", "verticalAlignment": "VAlign_Center",
        }}
        next(w for w in self.raw["widgets"] if w["widgetName"] == node["name"])["parent"] = copy.deepcopy(raw_parent["widget"])
        self.refresh_evidence()
        return node

    @staticmethod
    def auto_flow():
        return {"size": {"rule": "Auto"}, "padding": [0, 0, 10, 0],
                "horizontalAlignment": "Fill", "verticalAlignment": "Center"}

    def test_metadata_schema_definitions_exactly_match_02(self):
        old = load_json(PLUGIN_ROOT / "skills/build-nextgame-umg/assets/ui-layout-spec.schema.json")
        new = load_json(PLUGIN_ROOT / "skills/build-nextgame-umg/assets/existing-asset-update.schema.json")
        for field in ("adaptiveLayout", "flowSlot"):
            self.assertEqual(old["properties"]["nodes"]["items"]["properties"][field], new["$defs"][field])

    def test_adaptive_standard_points_are_metadata_only(self):
        for horizontal, x in (("left", 0), ("center", 0.5), ("right", 1)):
            for vertical, y in (("top", 0), ("center", 0.5), ("bottom", 1)):
                with self.subTest(horizontal=horizontal, vertical=vertical):
                    node = self.canvas_slot(minimum=(x, y))
                    node.pop("adaptiveLayout", None)
                    write(self.path, self.layout)
                    before = build_update_plan(self.path, self.layout)
                    node["adaptiveLayout"] = {"horizontal": horizontal, "vertical": vertical, "reason": "Observed standard point."}
                    write(self.path, self.layout)
                    after = build_update_plan(self.path, self.layout)
                    self.assertEqual(before["operations"], after["operations"])
                    self.assertEqual(before["batches"], after["batches"])

    def test_adaptive_stretch_preserves_observed_center_alignment(self):
        for minimum, maximum, horizontal, vertical in (
            ((0, 0), (1, 1), "stretch", "stretch"),
            ((0, 0.5), (1, 0.5), "stretch", "center"),
            ((0.5, 0), (0.5, 1), "center", "stretch"),
        ):
            with self.subTest(horizontal=horizontal, vertical=vertical):
                node = self.canvas_slot(minimum=minimum, maximum=maximum, alignment=(0.5, 0.5))
                node["adaptiveLayout"] = {"horizontal": horizontal, "vertical": vertical, "reason": "Preserve legacy stretch."}
                write(self.path, self.layout)
                plan = build_update_plan(self.path, self.layout)
                self.assertFalse(any(o["property"] == "layoutData" for o in plan["operations"]))
                self.assertEqual({"x": 0.5, "y": 0.5}, self.snapshot["assets"][0]["widgets"][-3]["slot"]["properties"]["layoutData"]["alignment"])

    def test_adaptive_checks_merged_partial_native_slot_target(self):
        node = self.canvas_slot()
        node["nativeSlot"]["layoutData"] = {
            "anchors": {"minimum": {"x": 0.5}, "maximum": {"x": 0.5}}, "alignment": {"x": 0.5},
        }
        node["adaptiveLayout"] = {"horizontal": "center", "vertical": "top", "reason": "Accepted center target."}
        write(self.path, self.layout)
        plan = build_update_plan(self.path, self.layout)
        operation = next(o for o in plan["operations"] if o["property"] == "layoutData")
        self.assertEqual({"x": 0, "y": 0}, operation["before"]["alignment"])
        self.assertEqual({"x": 0.5, "y": 0}, operation["after"]["alignment"])
        self.assertEqual(operation["before"]["offsets"], operation["after"]["offsets"])
        for field in ("anchors", "alignment"):
            bad = copy.deepcopy(self.layout)
            next(n for n in bad["nodes"] if n["id"] == node["id"])["nativeSlot"]["layoutData"].pop(field)
            self.assertFalse(self.validate(bad)["valid"])

    def test_adaptive_wrong_axes_and_nonstandard_point_alignment_fail(self):
        node = self.canvas_slot(minimum=(0.5, 0.5))
        node["adaptiveLayout"] = {"horizontal": "center", "vertical": "center", "reason": "Exact center."}
        changes = (
            lambda n: n["adaptiveLayout"].update(horizontal="left"),
            lambda n: n["adaptiveLayout"].update(vertical="stretch"),
            lambda n: n["nativeSlot"].update(layoutData={"alignment": {"x": 0}}),
            lambda n: n["nativeSlot"].update(layoutData={"alignment": {"y": 0.25}}),
            lambda n: n["nativeSlot"].update(layoutData={"anchors": {"minimum": {"x": 0.25}, "maximum": {"x": 0.25}}}),
            lambda n: n["nativeSlot"].update(layoutData={"anchors": {"minimum": {"x": 0.50000001}, "maximum": {"x": 0.50000001}},
                                                                      "alignment": {"x": 0.50000001}}),
            lambda n: n["nativeSlot"].update(layoutData={"anchors": {"minimum": {"x": 1}, "maximum": {"x": 0}}}),
            lambda n: n["nativeSlot"].update(layoutData={"alignment": {"x": 2}}),
            lambda n: n["nativeSlot"].update(layoutData={"alignment": {"x": True}}),
        )
        for change in changes:
            with self.subTest(change=change):
                bad = copy.deepcopy(self.layout)
                change(next(n for n in bad["nodes"] if n["id"] == node["id"]))
                self.assertFalse(self.validate(bad)["valid"])

    def test_adaptive_requires_observed_supported_slot_and_vectors(self):
        declaration = {"horizontal": "left", "vertical": "top", "reason": "Observed only."}
        self.layout["nodes"][0]["adaptiveLayout"] = declaration
        self.assertFalse(self.validate()["valid"])
        self.layout["nodes"][0].pop("adaptiveLayout")
        self.text()["adaptiveLayout"] = declaration
        self.assertFalse(self.validate()["valid"])
        self.canvas_slot()
        widget = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == "TextBlock_03")
        original = copy.deepcopy(widget["slot"]["properties"]["layoutData"])
        for malformed in (None, {"anchors": None}, {"anchors": {"minimum": None, "maximum": {"x": 0, "y": 0}}, "alignment": {"x": 0, "y": 0}}):
            with self.subTest(malformed=malformed):
                widget["slot"]["properties"]["layoutData"] = malformed
                self.refresh_evidence()
                self.assertFalse(self.validate()["valid"])
        widget["slot"]["properties"]["layoutData"] = original
        widget["slot"]["properties"]["anchors"] = copy.deepcopy(original["anchors"])
        self.refresh_evidence()
        self.text()["nativeSlot"]["anchors"] = {"maximum": {"x": 1}}
        self.assertFalse(self.validate()["valid"])

    def test_flow_auto_and_weighted_fill_are_metadata_only_for_both_boxes(self):
        for box in ("HorizontalBox", "VerticalBox"):
            for rule in ("Automatic", "Fill"):
                with self.subTest(box=box, rule=rule):
                    node = self.flow_slot(box, rule, 2.5)
                    node.pop("flowSlot", None)
                    node.pop("adaptiveLayout", None)
                    write(self.path, self.layout)
                    before = build_update_plan(self.path, self.layout)
                    node["flowSlot"] = self.auto_flow()
                    if rule == "Fill":
                        node["flowSlot"]["size"] = {"rule": "Fill", "weight": 2.5}
                    node["adaptiveLayout"] = {"horizontal": "stretch", "vertical": "center", "reason": "Occupancy, not allocation."}
                    write(self.path, self.layout)
                    after = build_update_plan(self.path, self.layout)
                    self.assertEqual(before["operations"], after["operations"])
                    self.assertEqual(before["batches"], after["batches"])
                    self.assertFalse(any(o["kind"] == "set-slot" for o in after["operations"]))

    def test_flow_checks_merged_native_size_padding_and_alignments(self):
        node = self.flow_slot()
        node["nativeSlot"] = {"size": {"sizeRule": "Fill", "value": 3.5}, "padding": {"right": 12},
                              "horizontalAlignment": "HAlign_Right", "verticalAlignment": "VAlign_Bottom"}
        node["flowSlot"] = {"size": {"rule": "Fill", "weight": 3.5}, "padding": [0, 0, 12, 0],
                            "horizontalAlignment": "Right", "verticalAlignment": "Bottom"}
        node["adaptiveLayout"] = {"horizontal": "right", "vertical": "bottom", "reason": "Native target alignment."}
        write(self.path, self.layout)
        plan = build_update_plan(self.path, self.layout)
        padding = next(o for o in plan["operations"] if o["property"] == "padding")
        self.assertEqual({"left": 0, "top": 0, "right": 12, "bottom": 0}, padding["after"])
        self.assertEqual(4, sum(o["kind"] == "set-slot" for o in plan["operations"]))
        node["flowSlot"]["size"]["weight"] = 4
        self.assertFalse(self.validate()["valid"])

    def test_flow_wrong_allocation_padding_alignment_and_adaptive_fail(self):
        node = self.flow_slot()
        node["flowSlot"] = self.auto_flow()
        node["adaptiveLayout"] = {"horizontal": "stretch", "vertical": "center", "reason": "Actual Slot."}
        for change in (
            lambda n: n["flowSlot"].update(size={"rule": "Fill", "weight": 1}),
            lambda n: n["flowSlot"].update(padding=[0, 0, 0, 0]),
            lambda n: n["flowSlot"].update(horizontalAlignment="Center"),
            lambda n: n["flowSlot"].update(verticalAlignment="Top"),
            lambda n: n["adaptiveLayout"].update(horizontal="center"),
            lambda n: n["adaptiveLayout"].update(vertical="stretch"),
        ):
            with self.subTest(change=change):
                bad = copy.deepcopy(self.layout)
                change(next(n for n in bad["nodes"] if n["id"] == node["id"]))
                self.assertFalse(self.validate(bad)["valid"])

    def test_flow_requires_actual_direct_box_parent_slot_class_and_role(self):
        self.text()["flowSlot"] = self.auto_flow()
        self.assertFalse(self.validate()["valid"])
        node = self.flow_slot()
        node["flowSlot"] = self.auto_flow()
        parent = next(n for n in self.layout["nodes"] if n["id"] == node["parent"])
        parent["role"] = "container.vertical"
        self.assertFalse(self.validate()["valid"])
        parent["role"] = "container.horizontal"
        widget = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == node["name"])
        widget["slot"]["classPath"] = node["slotClassPath"] = "/Script/UMG.OverlaySlot"
        self.refresh_evidence()
        self.assertFalse(self.validate()["valid"])

    def test_closed_metadata_rejects_unknown_fields_invalid_enums_and_fill_weights(self):
        node = self.flow_slot()
        node["flowSlot"] = self.auto_flow()
        for field, value in (
            ("flowSlot", dict(self.auto_flow(), arbitrary="code")),
            ("flowSlot", dict(self.auto_flow(), size={"rule": "Auto", "weight": 1})),
            ("flowSlot", dict(self.auto_flow(), size={"rule": "Fill"})),
            ("flowSlot", dict(self.auto_flow(), size={"rule": "Fill", "weight": 0})),
            ("flowSlot", dict(self.auto_flow(), size={"rule": "Fill", "weight": True})),
            ("flowSlot", dict(self.auto_flow(), size={"rule": "Fill", "weight": float("inf")})),
            ("flowSlot", dict(self.auto_flow(), padding=[0, 0, 0])),
            ("flowSlot", dict(self.auto_flow(), horizontalAlignment="Stretch")),
            ("adaptiveLayout", {"horizontal": "stretch", "vertical": "center"}),
            ("adaptiveLayout", {"horizontal": "nearest", "vertical": "center", "reason": "No guesses."}),
            ("adaptiveLayout", {"horizontal": "stretch", "vertical": "center", "reason": " "}),
            ("adaptiveLayout", {"horizontal": "stretch", "vertical": "center", "reason": "Actual.", "code": "anything"}),
        ):
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(self.layout)
                next(n for n in bad["nodes"] if n["id"] == node["id"])[field] = value
                self.assertFalse(self.validate(bad)["valid"])

    def test_metadata_only_noop_plan_and_art_source_do_not_lower_semantics(self):
        node = self.canvas_slot()
        for item in self.layout["nodes"]:
            item["nativeProperties"], item["nativeSlot"] = {}, {}
        node["adaptiveLayout"] = {"horizontal": "left", "vertical": "top", "reason": "Preserved point."}
        requirement, _, _, bundle = self.linked()
        plan = build_update_plan(self.path, self.layout)
        self.assertEqual([], plan["operations"])
        entries = source_entries(self.layout, spec_path=self.path, asset=bundle["assets"][0], mappings=bundle["nodeMappings"])
        self.assertEqual({}, entries[(PATH, node["name"])]["slot"])
        self.assertEqual({}, entries[(PATH, node["name"])]["properties"])

    def test_preserved_multi_root_direct_panel_entry_and_zero_panel_entry(self):
        for count in (2, 0):
            with self.subTest(panels=count):
                layout, _, _ = fixture(self.root, panels=count)
                report = self.validate(layout)
                self.assertTrue(report["valid"], report)
                self.assertEqual(2, report["summary"]["operations"])

    def test_distinct_dispatch_does_not_apply_new_create_naming_or_panel_rules(self):
        self.assertTrue(self.validate()["valid"])
        old = copy.deepcopy(self.layout)
        old["version"] = "0.2"
        self.assertFalse(validate_spec(old, {"components": []}, spec_path=self.path)["valid"])
        self.assertFalse(validate_existing_asset_update(self.layout)["valid"])

    def test_pure_set_plan_is_deterministic_top_level_and_generic_executor_rejects(self):
        first = build_plan(self.path, self.layout, {}, {})
        self.assertEqual(first, build_update_plan(self.path, copy.deepcopy(self.layout)))
        self.assertEqual(sha(self.path), first["sourceSpecSha256"])
        self.assertEqual(PLAN_KIND, first["kind"])
        self.assertEqual({"set-property", "set-slot"}, {o["kind"] for o in first["operations"]})
        self.assertEqual({"font", "zOrder"}, {o["property"] for o in first["operations"]})
        font = next(o for o in first["operations"] if o["property"] == "font")
        self.assertEqual({"size": 20, "typefaceFontName": "Regular"}, font["before"])
        self.assertEqual({"size": 22, "typefaceFontName": "Regular"}, font["after"])
        self.assertNotIn("toolName", first["steps"][0])
        client = Mock()
        with self.assertRaisesRegex(RuntimeError, "unsupported operation"):
            execute(first, client, None)
        with self.assertRaisesRegex(RuntimeError, "unsupported operation"):
            require_official_operations(first["steps"])
        client.assert_not_called()
        self.assertEqual([], client.mock_calls)
        for node in self.layout["nodes"]:
            node["nativeProperties"], node["nativeSlot"] = {}, {}
        write(self.path, self.layout)
        plan = build_update_plan(self.path, self.layout)
        self.assertEqual([], plan["operations"])
        with self.assertRaises(RuntimeError):
            execute(plan, client, None)
        with self.assertRaises(RuntimeError):
            require_official_operations(plan["steps"])

    def test_stale_snapshot_raw_and_state_hash_are_rejected(self):
        for field in ("snapshot", "rawTree", "stateSha256"):
            with self.subTest(field=field):
                layout = copy.deepcopy(self.layout)
                if field == "stateSha256":
                    layout["baseline"][field] = "0" * 64
                else:
                    layout["baseline"][field]["sha256"] = "0" * 64
                self.assertFalse(self.validate(layout)["valid"])

    def test_complete_topology_no_missing_new_or_reparented_nodes(self):
        changes = [
            lambda d: d["nodes"].pop(),
            lambda d: d["nodes"].append(dict(d["nodes"][-1], id="new-node", name="NewWidget")),
            lambda d: d["nodes"][2].update(parent=d["nodes"][1]["id"]),
            lambda d: d["nodes"][1].update(parent="missing-parent"),
        ]
        for change in changes:
            with self.subTest(change=change):
                layout = copy.deepcopy(self.layout)
                change(layout)
                self.assertFalse(self.validate(layout)["valid"])

    def test_raw_snapshot_mismatch_cannot_be_rehashed_into_permission(self):
        for field, value in (("bIsVariable", False), ("parent", "None"),
                             ("widgetClassPath", {"refPath": "/Script/UMG.Button"})):
            with self.subTest(field=field):
                raw = copy.deepcopy(self.raw)
                raw["widgets"][1][field] = value
                write(self.root / "raw-tree.json", raw)
                layout = copy.deepcopy(self.layout)
                layout["baseline"]["rawTree"] = bind(self.root / "raw-tree.json")
                self.assertFalse(self.validate(layout)["valid"])

    def test_observed_blueprint_asset_generated_class_pair_is_narrow(self):
        for path in ("/Game/UI/UMG/Widgets/uw_common_currency.uw_common_currency",
                     "/Engine/Widgets/Example.Example"):
            self.assertTrue(_observed_class_matches(path, path + "_C"))
            self.assertTrue(_observed_class_matches(path + "_C", path + "_C"))
        for raw, actual in (
            ("/Script/UMG.Image", "/Script/UMG.Image_C"),
            ("/Script/UMG.Image", "/Script/UMG.Button"),
            ("/Game/UI/uw_a.uw_a", "/Game/Other/uw_a.uw_a_C"),
            ("/Game/UI/uw_a.uw_a", "/Game/UI/uw_b.uw_b_C"),
            ("/Game/UI/uw_a.uw_other", "/Game/UI/uw_a.uw_other_C"),
            ("/Game/UI/uw_a", "/Game/UI/uw_a_C"),
            ("/Game/UI/uw_a.uw_a_C", "/Game/UI/uw_a.uw_a"),
            ("/Game/UI/uw_a.uw_a", "/Game/UI/uw_a.uw_a_C_C"),
        ):
            with self.subTest(raw=raw, actual=actual):
                self.assertFalse(_observed_class_matches(raw, actual))

    def test_blueprint_child_raw_asset_preserves_actual_generated_class_target(self):
        asset_class = "/Game/UI/UMG/Widgets/uw_common_currency.uw_common_currency"
        widget = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == "List_09")
        node = next(n for n in self.layout["nodes"] if n["name"] == "List_09")
        raw_widget = next(w for w in self.raw["widgets"] if w["widgetName"] == "List_09")
        widget["classPath"], node["classPath"] = asset_class + "_C", asset_class + "_C"
        raw_widget["widgetClassPath"] = {"refPath": asset_class}
        self.layout["baseline"]["snapshot"] = bind(write(self.root / "snapshot.json", self.snapshot))
        self.layout["baseline"]["rawTree"] = bind(write(self.root / "raw-tree.json", self.raw))
        self.layout["baseline"]["stateSha256"] = _art_module("art_common").state_hash(self.snapshot)
        write(self.path, self.layout)
        self.assertTrue(self.validate()["valid"])
        self.assertEqual(asset_class + "_C", node["classPath"])
        self.assertEqual(2, len(build_update_plan(self.path, self.layout)["operations"]))
        node["classPath"] = asset_class
        self.assertFalse(self.validate()["valid"])

    def test_rehashed_foreign_blueprint_raw_asset_is_rejected(self):
        widget = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == "List_09")
        node = next(n for n in self.layout["nodes"] if n["name"] == "List_09")
        raw_widget = next(w for w in self.raw["widgets"] if w["widgetName"] == "List_09")
        widget["classPath"], node["classPath"] = ("/Game/UI/UMG/Widgets/uw_a.uw_a_C",) * 2
        self.layout["baseline"]["snapshot"] = bind(write(self.root / "snapshot.json", self.snapshot))
        self.layout["baseline"]["stateSha256"] = _art_module("art_common").state_hash(self.snapshot)
        for raw_class in ("/Game/UI/UMG/Other/uw_a.uw_a", "/Game/UI/UMG/Widgets/uw_b.uw_b",
                          "/Game/UI/UMG/Widgets/uw_a.uw_other", "/Script/UMG.Image"):
            with self.subTest(raw_class=raw_class):
                raw_widget["widgetClassPath"] = {"refPath": raw_class}
                self.layout["baseline"]["rawTree"] = bind(write(self.root / "raw-tree.json", self.raw))
                self.assertFalse(self.validate()["valid"])

    def test_native_name_class_variable_slot_and_mode_cannot_change(self):
        for field, value in (("name", "Renamed"), ("classPath", "/Script/UMG.Button"),
                             ("isVariable", False), ("slotClassPath", "/Script/UMG.OverlaySlot")):
            with self.subTest(field=field):
                layout = copy.deepcopy(self.layout)
                next(n for n in layout["nodes"] if n["name"] == "TextBlock_03")[field] = value
                self.assertFalse(self.validate(layout)["valid"])
        self.layout["profile"]["designSizeMode"] = "FillScreen"
        self.assertFalse(self.validate()["valid"])

    def test_arbitrary_native_fields_nested_fields_code_and_canonical_writes_rejected(self):
        changes = [
            lambda d: d.update(ueCode="import unreal"),
            lambda d: d["nodes"][0].update(isNew=True),
            lambda d: d["nodes"][0]["nativeProperties"].update(OnClicked="code"),
            lambda d: d["nodes"][-3]["nativeProperties"].update(font={"inventedField": 22}),
            lambda d: d["nodes"][-3]["nativeSlot"].update(classPath="/Script/UMG.ButtonSlot"),
            lambda d: d["nodes"][0]["properties"].update(visibility="Hidden"),
            lambda d: d["nodes"][-3]["nativeProperties"].update(renderOpacity=float("nan")),
        ]
        for change in changes:
            with self.subTest(change=change):
                layout = copy.deepcopy(self.layout)
                change(layout)
                self.assertFalse(self.validate(layout)["valid"])

    def test_visibility_text_entry_class_bindings_and_input_writes_rejected(self):
        for name, field, after in (
            ("TextBlock_03", "visibility", "Collapsed"), ("TextBlock_03", "text", "Changed"),
            ("List_09", "entryWidgetClass", {"refPath": "/Game/UI/UMG/Test/uw_new.uw_new_C"}),
            ("List_09", "navigation", {}), ("TextBlock_03", "brushDelegate", "binding"),
        ):
            with self.subTest(field=field):
                layout = copy.deepcopy(self.layout)
                next(n for n in layout["nodes"] if n["name"] == name)["nativeProperties"][field] = after
                self.assertFalse(self.validate(layout)["valid"])
        for node in self.layout["nodes"]:
            old = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == node["name"])
            node["nativeProperties"]["visibility"] = old["properties"]["visibility"]
        self.assertTrue(self.validate()["valid"])

    def test_wrong_asset_and_unobserved_native_property_rejected(self):
        self.layout["asset"]["name"] = "uw_other"
        self.assertFalse(self.validate()["valid"])
        self.layout["asset"]["name"] = PATH.rsplit("/", 1)[-1]
        self.text()["nativeProperties"]["shadowOffset"] = {"x": 1, "y": 2}
        self.assertFalse(self.validate()["valid"])

    def test_no_second_font_conversion_and_bad_native_font_rejected(self):
        self.text()["nativeProperties"] = {"font": {"size": 21}}
        self.assertFalse(self.validate()["valid"])
        self.text()["nativeProperties"] = {"font": {"size": 22.0}}
        self.assertFalse(self.validate()["valid"])
        self.text()["nativeProperties"] = {"font": {"size": 22}}
        self.assertEqual(22, build_update_plan(self.path, self.layout)["operations"][0]["after"]["size"])

    def test_current_art_editor_write_allowlist_is_authoritative(self):
        editor = _art_module("art_editor")
        with patch.object(editor, "WRITE_PROPERTIES", editor.WRITE_PROPERTIES - {"font"}):
            self.assertFalse(self.validate()["valid"])

    def test_native_objectref_null_to_imported_resource_is_a_narrow_union(self):
        resource = {"refPath": "/Game/UI/Textures/Test/pic_imported.pic_imported"}
        for before in (None, "None", {"refPath": "None"},
                       {"refPath": "/Game/UI/Textures/Test/pic_old.pic_old"}):
            with self.subTest(before=before):
                self.assertEqual(resource, _merge_observed(before, resource, "node.nativeProperties.brush.resourceObject"))
                self.assertIsNone(_merge_observed(before, None, "node.nativeProperties.brush.resourceObject"))
                self.assertEqual(resource, _merge_observed(before, resource, "node.nativeProperties.font.fontObject"))
                for target in ({"refPath": resource["refPath"], "code": "import unreal"},
                               {"refPath": "import unreal"}, {"unexpected": 1}):
                    with self.assertRaises(ValueError):
                        _merge_observed(before, target, "node.nativeProperties.brush.resourceObject")
        for before in (None, "None"):
            with self.assertRaises(ValueError):
                _merge_observed(before, resource, "node.nativeProperties.shadowOffset")

    def test_null_brush_resource_plan_preserves_other_observed_fields(self):
        image = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == "Image_42")
        image["properties"]["brush"]["resourceObject"] = "None"
        snapshot_path = write(self.root / "snapshot.json", self.snapshot)
        self.layout["baseline"]["snapshot"] = bind(snapshot_path)
        self.layout["baseline"]["stateSha256"] = _art_module("art_common").state_hash(self.snapshot)
        node = next(n for n in self.layout["nodes"] if n["name"] == "Image_42")
        node["nativeProperties"] = {"brush": {"resourceObject": {"refPath": "/Game/UI/Textures/Test/pic_new.pic_new"}}}
        write(self.path, self.layout)
        report = self.validate()
        self.assertTrue(report["valid"], report)
        operation = next(o for o in build_update_plan(self.path, self.layout)["operations"] if o["property"] == "brush")
        self.assertEqual("None", operation["before"]["resourceObject"])
        self.assertEqual({"x": 32, "y": 32}, operation["after"]["imageSize"])

    def test_unchanged_state_text_and_entry_class_are_preserved_without_operations(self):
        for node in self.layout["nodes"]:
            old = next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == node["name"])
            node["nativeProperties"] = {k: copy.deepcopy(v) for k, v in old["properties"].items()
                                        if k in {"visibility", "text", "entryWidgetClass"}}
            node["nativeSlot"] = {}
        write(self.path, self.layout)
        self.assertTrue(self.validate()["valid"])
        self.assertEqual([], build_update_plan(self.path, self.layout)["operations"])

    def test_plan_rejects_unbound_in_memory_source(self):
        self.text()["nativeProperties"]["font"]["size"] = 24
        with self.assertRaisesRegex(ValueError, "physical sourceSpec"):
            build_update_plan(self.path, self.layout)

    def linked(self):
        requirement = requirement_fixture(self.layout)
        report = validate_requirement_spec(requirement, load_json(REQUIREMENT_SCHEMA))
        self.assertTrue(report["valid"], report)
        req_path = write(self.root / "requirement.json", requirement)
        write(self.path, self.layout)
        view, mode, _ = build_accepted_build_view(req_path)
        self.assertEqual("projected", mode)
        asset = {"id": "build-legacy", "assetPlanId": "asset-legacy", "assetPath": PATH,
            "assetKind": "list-entry", "referenceSize": self.layout["referenceSize"], "layoutSpecPath": "layout.json",
            "layoutSpecSha256": sha(self.path), "dependsOnAssetIds": [], "buildOrder": 0, "status": "planned"}
        mappings = [{"id": "mapping-" + n["id"], "assetId": asset["id"], "layoutNodeId": n["id"], "mappingKind": "direct",
            "requirementRefs": ["element-" + n["id"]] + (["region-legacy"] if n["parent"] is None else []),
            "claimIds": ["claim-legacy-update"], "stateRefs": []} for n in self.layout["nodes"]]
        bundle = {"version": "0.1", "bundleId": "bundle-legacy", "capabilities": [CAPABILITY],
            "requirement": {"path": str(req_path), "sha256": sha(req_path), "requestId": requirement["requestId"],
                "revision": requirement["revision"], "reviewStatus": "accepted",
                "approvedContentSha256": requirement["reviewGate"]["approvedContentSha256"]},
            "assets": [asset], "nodeMappings": mappings, "crossAssetOperations": [],
            "execution": {"status": "pending", "buildOrderAssetIds": [asset["id"]]},
            "verification": {"status": "pending", "checks": [{"id": "check-legacy", "type": "key-properties",
                "assetId": asset["id"], "status": "pending", "details": "Synthetic test, not executed.",
                "requirementRefs": ["criterion-legacy"], "claimIds": ["claim-legacy-update"]}], "deviations": []}}
        return requirement, req_path, view, bundle

    def bundle_report(self, requirement, req_path, view, bundle, **kwargs):
        return validate_build_bundle(bundle, load_json(BUNDLE_SCHEMA), bundle_path=self.root / "bundle.json",
            requirement_spec=requirement, requirement_path=req_path, accepted_build_view=view, **kwargs)

    @staticmethod
    def reapprove(requirement, req_path, bundle):
        requirement["reviewGate"]["approvedContentSha256"] = compute_approved_content_sha256(requirement)
        write(req_path, requirement)
        bundle["requirement"].update(sha256=sha(req_path), approvedContentSha256=requirement["reviewGate"]["approvedContentSha256"])
        view, mode, _ = build_accepted_build_view(req_path)
        if mode != "projected":
            raise AssertionError(view)
        return view

    def semantic_linked(self):
        text = self.flow_slot()
        text["flowSlot"] = self.auto_flow()
        image = self.canvas_slot("Image_42", minimum=(0, 0), maximum=(1, 1), alignment=(0.5, 0.5))
        image["classPath"] = "/Script/UIFramework.GameImage"
        next(w for w in self.snapshot["assets"][0]["widgets"] if w["widgetName"] == image["name"])["classPath"] = image["classPath"]
        next(w for w in self.raw["widgets"] if w["widgetName"] == image["name"])["widgetClassPath"] = {"refPath": image["classPath"]}
        image["adaptiveLayout"] = {"horizontal": "stretch", "vertical": "stretch", "reason": "Observed legacy image Slot."}
        self.refresh_evidence()
        requirement, req_path, _, bundle = self.linked()
        requirement["analysisPolicy"] = {
            "geometryEvidenceRequired": False, "listPriorityRequired": False,
            "imageCompositionRequired": True, "explicitPanelSlotsRequired": True,
        }
        elements = {e["id"]: e for e in requirement["uiModel"]["elements"]}
        image_id, text_id = "element-" + image["id"], "element-" + text["id"]
        elements[image_id]["imageComposition"] = {"groupKey": "graphic.legacy-image", "role": "complete", "adaptation": "independent"}
        elements[text_id]["panelSlotIntent"] = {
            "slotType": "flow", "sizingBasis": "content-driven", **copy.deepcopy(text["flowSlot"]),
            "reason": "Preserve current Auto allocation and exact native alignment.",
        }
        elements["element-" + text["parent"]]["layoutRole"] = "container.horizontal"
        intent_id = "responsive-existing-image"
        requirement["uiModel"]["responsiveIntent"] = [{
            "id": intent_id, "elementId": image_id, "horizontal": "stretch", "vertical": "stretch",
            "reason": image["adaptiveLayout"]["reason"], "inBuildScope": True,
            "evidenceIds": ["evidence-selected-tab"], "claimIds": ["claim-legacy-update"],
        }]
        requirement["claims"][0]["subjectRefs"].append(intent_id)
        next(m for m in bundle["nodeMappings"] if m["layoutNodeId"] == image["id"])["requirementRefs"].append(intent_id)
        view = self.reapprove(requirement, req_path, bundle)
        return requirement, req_path, view, bundle

    def test_normal_bundle_semantic_guards_accept_native_bound_metadata(self):
        report = self.bundle_report(*self.semantic_linked())
        self.assertTrue(report["valid"], report)

    def test_normal_bundle_semantic_guards_still_require_reviewed_declarations(self):
        requirement, req_path, view, bundle = self.semantic_linked()
        original = copy.deepcopy(self.layout)
        for name, field, expected_code in (
            ("Image_42", "adaptiveLayout", "mapping.element_responsive_adaptive"),
            ("TextBlock_03", "flowSlot", "mapping.panel_slot_count"),
        ):
            with self.subTest(field=field):
                self.layout = copy.deepcopy(original)
                next(n for n in self.layout["nodes"] if n["name"] == name).pop(field)
                write(self.path, self.layout)
                bundle["assets"][0]["layoutSpecSha256"] = sha(self.path)
                self.assertTrue(self.validate()["valid"])
                self.assertIn(expected_code, codes(self.bundle_report(requirement, req_path, view, bundle)))

    def test_normal_bundle_semantic_guards_reject_freshly_accepted_source_mismatch(self):
        requirement, req_path, _, bundle = self.semantic_linked()
        original = copy.deepcopy(requirement)
        for field, expected_code in (("adaptiveLayout", "mapping.element_responsive_adaptive"),
                                     ("flowSlot", "mapping.panel_slot_values")):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                if field == "adaptiveLayout":
                    changed["uiModel"]["responsiveIntent"][0]["horizontal"] = "left"
                else:
                    next(e for e in changed["uiModel"]["elements"] if e["nameHint"] == "TextBlock_03")["panelSlotIntent"]["padding"][2] = 20
                view = self.reapprove(changed, req_path, bundle)
                self.assertIn(expected_code, codes(self.bundle_report(changed, req_path, view, bundle)))

    def test_full_requirement_view_bundle_layout_chain_passes(self):
        data = self.linked()
        report = self.bundle_report(*data)
        self.assertTrue(report["valid"], report)

    def test_linked_chain_rejects_missing_capability_view_and_skip(self):
        requirement, req_path, view, bundle = self.linked()
        bad = copy.deepcopy(bundle)
        bad.pop("capabilities")
        self.assertIn("existing-update.capability_required", codes(self.bundle_report(requirement, req_path, view, bad)))
        self.assertIn("existing-update.accepted_view_required", codes(self.bundle_report(requirement, req_path, None, bundle)))
        self.assertIn("existing-update.linked_files_required", codes(self.bundle_report(requirement, req_path, view, bundle, check_linked_files=False)))
        bad_view = copy.deepcopy(view)
        bad_view["buildAllowed"] = False
        self.assertIn("accepted-build-view.invalid", codes(self.bundle_report(requirement, req_path, bad_view, bundle)))

    def test_linked_chain_rejects_stale_layout_requirement_and_wrong_asset(self):
        requirement, req_path, view, bundle = self.linked()
        bad = copy.deepcopy(bundle)
        bad["assets"][0]["layoutSpecSha256"] = "0" * 64
        self.assertIn("layout.sha256", codes(self.bundle_report(requirement, req_path, view, bad)))
        bad = copy.deepcopy(bundle)
        bad["requirement"]["sha256"] = "0" * 64
        self.assertIn("requirement.sha256", codes(self.bundle_report(requirement, req_path, view, bad)))
        bad = copy.deepcopy(bundle)
        bad["assets"][0]["assetPath"] = "/Game/UI/UMG/Test/Widgets/uw_wrong"
        self.assertIn("existing-update.asset", codes(self.bundle_report(requirement, req_path, view, bad)))

    def test_cross_asset_state_entry_or_structural_operations_are_not_update_authority(self):
        requirement, _, _, bundle = self.linked()
        bundle["crossAssetOperations"] = [{"sourceAssetId": "external-asset", "targetAssetId": "build-legacy",
                                           "type": "entry-widget-class"}]
        errors = validate_bundle_layout(self.layout, bundle["assets"][0], bundle, requirement,
            spec_path=self.path, accepted_claim_ids={"claim-legacy-update"})
        self.assertIn("existing-update.cross_asset_write", {e["code"] for e in errors})

    def test_helper_checks_every_element_exact_native_targets_and_own_asset(self):
        requirement, _, _, bundle = self.linked()
        asset = bundle["assets"][0]
        def helper(r=requirement, b=bundle):
            return validate_bundle_layout(self.layout, asset, b, r, spec_path=self.path, accepted_claim_ids={"claim-legacy-update"})
        self.assertEqual([], helper())
        for index in range(len(requirement["uiModel"]["elements"])):
            for field in ("nativeProperties", "nativeSlot"):
                with self.subTest(index=index, field=field):
                    bad = copy.deepcopy(requirement)
                    bad["uiModel"]["elements"][index]["properties"][field] = {"arbitrary": 1}
                    self.assertIn("existing-update.source_target", {e["code"] for e in helper(bad)})
        bad = copy.deepcopy(requirement)
        bad["assetPlan"][0]["coversElementIds"].pop()
        self.assertIn("existing-update.element_asset", {e["code"] for e in helper(bad)})
        own_paths = copy.deepcopy(requirement)
        for element in own_paths["uiModel"]["elements"]:
            element["properties"]["owningAssetPath"] = PATH
        self.assertEqual([], helper(own_paths))
        own_paths["uiModel"]["elements"][0]["properties"]["owningAssetPath"] = PATH + "_foreign"
        self.assertIn("existing-update.element_asset", {e["code"] for e in helper(own_paths)})
        bad = copy.deepcopy(bundle)
        bad["nodeMappings"].pop()
        self.assertIn("existing-update.coverage", {e["code"] for e in helper(requirement, bad)})
        bad = copy.deepcopy(bundle)
        bad["nodeMappings"][0]["assetId"] = "different-asset"
        self.assertIn("existing-update.coverage", {e["code"] for e in helper(requirement, bad)})
        bad = copy.deepcopy(requirement)
        text = next(e for e in bad["uiModel"]["elements"] if e["nameHint"] == "TextBlock_03")
        text["properties"]["nativeSlot"]["zOrder"] = 5.0
        self.assertIn("existing-update.source_target", {e["code"] for e in helper(bad)})

    def test_accepted_element_identity_fields_are_mandatory_and_exact(self):
        requirement, _, _, bundle = self.linked()
        for index in range(len(requirement["uiModel"]["elements"])):
            for field, value in (("targetClassPath", "/Script/UMG.Button"),
                                 ("observedIsVariable", 1), ("observedParentWidgetName", "ForeignParent"),
                                 ("observedWidgetName", "WrongName")):
                with self.subTest(index=index, field=field):
                    bad = copy.deepcopy(requirement)
                    bad["uiModel"]["elements"][index]["properties"][field] = value
                    errors = validate_bundle_layout(self.layout, bundle["assets"][0], bundle, bad,
                        spec_path=self.path, accepted_claim_ids={"claim-legacy-update"})
                    self.assertIn("existing-update.element_identity", {e["code"] for e in errors})
            for field in ("targetClassPath", "observedIsVariable", "observedParentWidgetName"):
                with self.subTest(index=index, missing=field):
                    bad = copy.deepcopy(requirement)
                    bad["uiModel"]["elements"][index]["properties"].pop(field)
                    errors = validate_bundle_layout(self.layout, bundle["assets"][0], bundle, bad,
                        spec_path=self.path, accepted_claim_ids={"claim-legacy-update"})
                    self.assertIn("existing-update.element_identity", {e["code"] for e in errors})

    def test_malformed_linked_layout_fails_closed_without_exception(self):
        requirement, req_path, view, bundle = self.linked()
        for nodes in (None, [{"id": "bad-node", "role": {}}]):
            with self.subTest(nodes=nodes):
                malformed = dict(self.layout, nodes=nodes)
                write(self.path, malformed)
                bundle["assets"][0]["layoutSpecSha256"] = sha(self.path)
                self.assertIn("existing-update.schema", codes(self.bundle_report(requirement, req_path, view, bundle)))

    def test_source_native_mismatch_is_caught_after_fresh_approval_and_view(self):
        requirement, req_path, _, bundle = self.linked()
        text = next(e for e in requirement["uiModel"]["elements"] if e["nameHint"] == "TextBlock_03")
        text["properties"]["nativeProperties"]["font"]["size"] = 24
        requirement["reviewGate"]["approvedContentSha256"] = compute_approved_content_sha256(requirement)
        write(req_path, requirement)
        bundle["requirement"].update(sha256=sha(req_path), approvedContentSha256=requirement["reviewGate"]["approvedContentSha256"])
        view, _, _ = build_accepted_build_view(req_path)
        self.assertIn("existing-update.source_target", codes(self.bundle_report(requirement, req_path, view, bundle)))

    def test_art_source_entries_preserve_native_classes_and_partial_targets(self):
        requirement, req_path, _, bundle = self.linked()
        entries = source_entries(self.layout, spec_path=self.path, asset=bundle["assets"][0], mappings=bundle["nodeMappings"])
        self.assertEqual("/Script/UMG.Image", entries[(PATH, "Image_42")]["classPath"])
        self.assertEqual({"font": {"size": 22}}, entries[(PATH, "TextBlock_03")]["properties"])
        import art_pipeline
        bundle_path = write(self.root / "bundle.json", bundle)
        request = {"requestId": requirement["requestId"], "baseline": {"requirement": bind(req_path), "bundle": bind(bundle_path)}}
        self.assertEqual(entries, art_pipeline._source_nodes(request, self.root / "request.json"))
        requirement["uiModel"]["elements"][0]["properties"]["nativeProperties"] = {"renderOpacity": 0.5}
        write(req_path, requirement)
        request["baseline"]["requirement"] = bind(req_path)
        with self.assertRaisesRegex(ValueError, "source_target"):
            art_pipeline._source_nodes(request, self.root / "request.json")

    def test_existing_art_cas_primitive_consumes_plan_shape_synthetically(self):
        from test_art_editor import FakeTransport, ArtEditor, PATH as fake_path
        transport = FakeTransport()
        editor = ArtEditor(transport)
        snapshot = editor.snapshot([fake_path])
        old = next(w for w in snapshot["assets"][0]["widgets"] if w["widgetName"] == "ImgIcon")
        operation = {"id": "fixture-opacity", "kind": "set-property", "assetPath": fake_path,
            "widgetName": old["widgetName"], "property": "renderOpacity",
            "before": old["properties"]["renderOpacity"], "after": 0.5}
        receipt = editor.execute_batch([operation])
        self.assertEqual("completed", receipt["status"])
        self.assertEqual("passed", receipt["results"][0]["status"])
        stale = copy.deepcopy(operation)
        stale["id"], stale["after"] = "fixture-stale", 0.75
        self.assertEqual("failed", editor.execute_batch([stale])["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
