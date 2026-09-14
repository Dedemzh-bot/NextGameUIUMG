#!/usr/bin/env python3
"""Synthetic contract tests. These fixtures are NOT actual Unreal evidence."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from test_text_component_rules import split_header_spec
from validate_prototype_widget_readback import (
    ACTUAL_KEYS, ARTIFACT_TYPE, CATALOG_PATH, DEFAULT_SCHEMA, SLOT_CLASSES,
    _json_pointer, _strict_equal, _validate_prototype_payload,
    expected_properties, load_json, sha256_file, validate_schema_instance,
)
from _document_contract_common import READBACK_SCHEMA
from validate_build_bundle import _validate_prototype_readback_checks

OPTIONS = argparse.Namespace(request_root=None, output_root=None)
CAPTURED = "2026-09-14T12:10:00+08:00"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SyntheticFixture:
    """Expected-derived UNIT TEST data only; not an acquisition implementation."""
    def __init__(self, root):
        self.root = root
        self.reqpath, self.bundlepath = root / "requirement.json", root / "bundle.json"
        self.rbpath, self.rawpath = root / "prototype-readback.json", root / "synthetic-raw.json"
        self.layout = deepcopy(split_header_spec())
        self.layout["mode"] = "prototype"
        self.layout["asset"] = {"folder": "/Game/UI/AIPrototype/ContractTest", "name": "umg_ai_contracttest"}
        for node in self.layout["nodes"]:
            if node["role"] == "text.label":
                node["properties"]["justification"] = "Left"
                node["fontSizeUnit"] = "pt"
        self.layout["nodes"][2]["properties"].update(autoWrap=False, wrapTextAt=0)
        self.layout["nodes"][2]["isVariable"] = True
        self.layoutpath = root / "layout.json"
        write_json(self.layoutpath, self.layout)
        self.req = {"requestId": "synthetic-contract-only", "revision": 1,
                    "reviewGate": {"status": "accepted", "approvedContentSha256": "a" * 64, "acceptedClaimIds": []},
                    "claims": [], "stateModels": [], "uiModel": {"elements": [], "runtimeFields": []}}
        package = self.layout["asset"]["folder"] + "/" + self.layout["asset"]["name"]
        self.bundle = {"version": "0.1", "bundleId": "synthetic-only", "assets": [
            {"id": "asset", "assetPath": package, "layoutSpecPath": "layout.json", "layoutSpecSha256": sha256_file(self.layoutpath), "status": "built"}],
            "nodeMappings": [{"id": "mapping." + n["id"], "assetId": "asset", "layoutNodeId": n["id"], "requirementRefs": [], "stateRefs": []} for n in self.layout["nodes"]],
            "execution": {"status": "completed", "startedAt": "2026-09-14T12:00:00+08:00", "completedAt": "2026-09-14T12:05:00+08:00"},
            "verification": {"status": "failed", "checks": [
                {"id": "check." + kind, "assetId": "asset", "type": kind, "status": "passed", "artifactPath": self.rbpath.name} for kind in ("widget-tree", "key-properties")], "deviations": []}}
        self.initialize_readback()

    def initialize_readback(self):
        write_json(self.reqpath, self.req)
        write_json(self.bundlepath, self.bundle)
        self.rb = {"artifactType": ARTIFACT_TYPE, "mode": "prototype", "version": "0.1", "readbackId": "synthetic-unit-test-only",
                   "capturedAt": CAPTURED, "capturedFrom": "unreal-editor", "acquisition": {"method": "official-unreal-mcp"}, "status": "verified",
                   "requirementBinding": {"requestId": self.req["requestId"], "revision": self.req["revision"], "approvedContentSha256": self.req["reviewGate"]["approvedContentSha256"], "sha256": sha256_file(self.reqpath)},
                   "bundleBinding": {"bundleId": self.bundle["bundleId"], "sha256": sha256_file(self.bundlepath)}, "assets": [], "evidence": []}
        catalog = {c["role"]: c for c in load_json(CATALOG_PATH)["components"]}
        for ai, ba in enumerate(self.bundle["assets"]):
            lp = self.root / ba["layoutSpecPath"]
            layout = load_json(lp)
            expected = expected_properties(lp, layout)
            package = ba["assetPath"]
            name = package.rsplit("/", 1)[-1]
            obj = package + "." + name
            by_id = {n["id"]: n for n in layout["nodes"]}
            widgets = []
            for ni, node in enumerate(layout["nodes"]):
                props = deepcopy(expected[node["id"]]["widget"])
                props.setdefault("visibility", "Visible")
                parent = by_id.get(node.get("parent"))
                slot = None
                if parent:
                    classpath = SLOT_CLASSES[catalog[parent["role"]]["classPath"]]
                    slot = {"objectPath": obj + ":WidgetTree." + parent["name"] + "." + classpath.rsplit(".", 1)[-1] + "_" + str(ni), "classPath": classpath, "properties": deepcopy(expected[node["id"]]["slot"])}
                entry = props.get("entryWidgetClass")
                if isinstance(entry, dict):
                    entry = entry.get("refPath")
                widgets.append({"widgetName": node["name"], "objectPath": obj + ":WidgetTree." + node["name"], "classPath": catalog[node["role"]]["classPath"],
                                "parentWidgetName": parent["name"] if parent else None, "isVariable": bool(node.get("isVariable", False)),
                                "visibility": props["visibility"], "entryWidgetClass": entry, "properties": props, "slot": slot})
            self.rb["assets"].append({"assetId": ba["id"], "assetPath": package, "assetObjectPath": obj, "assetClass": "/Script/UMGEditor.WidgetBlueprint",
                                      "generatedClassPath": obj + "_C", "parentClassPath": layout.get("profile", {}).get("parentClass", "/Script/UMG.UserWidget"),
                                      "cdoObjectPath": package + ".Default__" + name + "_C", "designSizeMode": layout["profile"]["designSizeMode"],
                                      "widgets": widgets, "status": "verified", "sourceBinding": {"evidenceId": "synthetic.capture", "jsonPointer": f"/assets/{ai}"},
                                      "nodeMappings": [{"nodeMappingId": m["id"], "layoutNodeId": m["layoutNodeId"], "widgetName": by_id[m["layoutNodeId"]]["name"]} for m in self.bundle["nodeMappings"] if m["assetId"] == ba["id"]]})
        self.sync_raw()

    def sync_raw(self):
        write_json(self.rawpath, {"capturedAt": CAPTURED, "syntheticFixtureNotUnrealEvidence": True,
                                  "assets": [{k: deepcopy(a[k]) for k in ACTUAL_KEYS} for a in self.rb["assets"]]})
        self.rb["evidence"] = [{"id": "synthetic.capture", "path": self.rawpath.name, "sha256": sha256_file(self.rawpath), "capturedAt": CAPTURED, "method": "official-unreal-mcp"}]
        write_json(self.rbpath, self.rb)

    def sync_bundle(self):
        write_json(self.bundlepath, self.bundle)
        self.rb["bundleBinding"]["sha256"] = sha256_file(self.bundlepath)

    def report(self):
        return _validate_prototype_payload(self.rb, readback_path=self.rbpath, requirement=self.req, requirement_path=self.reqpath, bundle=self.bundle, bundle_path=self.bundlepath)


class PrototypeReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="prototype-readback-test-", dir=OPTIONS.output_root)
        self.addCleanup(self.temp.cleanup)
        self.fx = SyntheticFixture(Path(self.temp.name))
        self.rb = self.fx.rb

    def codes(self):
        return {e["code"] for e in self.fx.report()["errors"]}

    def test_valid_observed_structure(self):
        report = self.fx.report()
        self.assertTrue(report["valid"], report["errors"])
        self.assertFalse(report["scope"]["productionDocumentAuthority"])
        self.assertFalse(report["scope"]["visualPreviewVerified"])

    def test_discriminator_required(self):
        del self.rb["artifactType"]
        self.assertFalse(self.fx.report()["valid"])

    def test_production_mode_forbidden(self):
        self.rb["mode"] = "production"
        self.assertFalse(self.fx.report()["valid"])

    def test_unknown_top_level_rejected(self):
        self.rb["reuseRelations"] = []
        self.assertFalse(self.fx.report()["valid"])

    def test_schema_override_cannot_be_supplied(self):
        import inspect
        self.assertNotIn("schema", inspect.signature(_validate_prototype_payload).parameters)

    def test_formal_schema_rejects_prototype(self):
        self.assertTrue(validate_schema_instance(self.rb, load_json(READBACK_SCHEMA)))

    def test_path_relabel_does_not_satisfy_formal_schema(self):
        candidate = deepcopy(self.rb)
        candidate["assets"][0]["assetPath"] = "/Game/UI/UMG/ContractTest/umg_contracttest"
        self.assertTrue(validate_schema_instance(candidate, load_json(READBACK_SCHEMA)))

    def test_layout_must_explicitly_be_prototype(self):
        self.fx.layout["mode"] = "production"
        write_json(self.fx.layoutpath, self.fx.layout)
        self.fx.bundle["assets"][0]["layoutSpecSha256"] = sha256_file(self.fx.layoutpath)
        self.fx.sync_bundle()
        self.assertIn("prototype.layout_mode", self.codes())

    def test_layout_hash_stale(self):
        self.fx.bundle["assets"][0]["layoutSpecSha256"] = "0" * 64
        self.fx.sync_bundle()
        self.assertIn("prototype.layout_hash", self.codes())

    def test_bundle_advanced_reuse_rejected(self):
        self.fx.bundle["version"] = "0.3"
        self.fx.sync_bundle()
        self.assertIn("prototype.bundle_version", self.codes())

    def test_bundle_production_path_rejected(self):
        self.fx.bundle["assets"][0]["assetPath"] = "/Game/UI/UMG/ContractTest/umg_contracttest"
        self.fx.sync_bundle()
        self.assertIn("prototype.asset_scope", self.codes())

    def test_traversal_layout_rejected(self):
        self.fx.bundle["assets"][0]["layoutSpecPath"] = "../escape.json"
        self.fx.sync_bundle()
        self.assertIn("prototype.layout_read", self.codes())

    def test_stale_bundle_hash_rejected(self):
        self.rb["bundleBinding"]["sha256"] = "0" * 64
        self.assertIn("binding.bundle", self.codes())

    def test_stale_requirement_hash_rejected(self):
        self.rb["requirementBinding"]["sha256"] = "0" * 64
        self.assertIn("binding.requirement", self.codes())

    def test_in_memory_authority_not_file_rejected(self):
        self.fx.bundle["bundleId"] = "forged"
        self.assertIn("binding.input_snapshot", self.codes())

    def test_planned_execution_rejected(self):
        self.fx.bundle["execution"]["status"] = "planned"
        self.fx.sync_bundle()
        self.assertIn("prototype.execution", self.codes())

    def test_old_capture_cannot_be_relabelled(self):
        self.rb["evidence"][0]["capturedAt"] = "2026-09-13T01:00:00Z"
        self.assertIn("evidence.stale", self.codes())
        self.assertIn("evidence.timestamp_binding", self.codes())

    def test_naive_capture_time_rejected(self):
        self.rb["capturedAt"] = "2026-09-14T12:10:00"
        self.assertIn("time.timezone", self.codes())

    def test_duplicate_evidence_rejected(self):
        self.rb["evidence"].append(deepcopy(self.rb["evidence"][0]))
        self.assertIn("evidence.duplicate", self.codes())

    def test_source_pointer_missing_field_rejected(self):
        self.rb["assets"][0]["sourceBinding"]["jsonPointer"] = "/missing/actual"
        self.assertIn("evidence.actual_source", self.codes())

    def test_raw_hash_mismatch_rejected(self):
        self.rb["evidence"][0]["sha256"] = "0" * 64
        self.assertIn("evidence.hash", self.codes())

    def test_raw_evidence_traversal_rejected(self):
        self.rb["evidence"][0]["path"] = "../forged.json"
        self.assertIn("evidence.read", self.codes())

    def test_actual_filled_from_plan_but_not_raw_rejected(self):
        self.rb["assets"][0]["widgets"][2]["properties"]["text"] = "invented"
        self.assertIn("evidence.actual_binding", self.codes())

    def test_missing_actual_property_not_backfilled(self):
        del self.rb["assets"][0]["widgets"][2]["properties"]["wrapTextAt"]
        self.fx.sync_raw()
        self.assertIn("actual.property_missing", self.codes())

    def test_real_property_difference_rejected(self):
        self.rb["assets"][0]["widgets"][2]["properties"]["wrapTextAt"] = 88
        self.fx.sync_raw()
        self.assertIn("actual.property_mismatch", self.codes())

    def test_bool_is_not_numeric_zero(self):
        self.rb["assets"][0]["widgets"][2]["properties"]["wrapTextAt"] = False
        self.fx.sync_raw()
        self.assertIn("actual.property_mismatch", self.codes())

    def test_wrong_native_image_class_rejected(self):
        self.rb["assets"][0]["widgets"][3]["classPath"] = "/Script/UMG.Image"
        self.fx.sync_raw()
        self.assertIn("identity.widget_classPath", self.codes())

    def test_image_white_tint_is_not_an_automatic_exception(self):
        self.rb["assets"][0]["widgets"][3]["properties"]["colorAndOpacity"] = {"r": 1, "g": 1, "b": 1, "a": 1}
        self.fx.sync_raw()
        self.assertIn("actual.property_mismatch", self.codes())

    def test_wrong_parent_rejected(self):
        self.rb["assets"][0]["widgets"][2]["parentWidgetName"] = "PanelRoot"
        self.fx.sync_raw()
        self.assertIn("identity.widget_parentWidgetName", self.codes())

    def test_wrong_variable_flag_rejected(self):
        self.rb["assets"][0]["widgets"][2]["isVariable"] = False
        self.fx.sync_raw()
        self.assertIn("identity.widget_isVariable", self.codes())

    def test_missing_widget_rejected(self):
        self.rb["assets"][0]["widgets"].pop()
        self.fx.sync_raw()
        self.assertIn("coverage.widgets", self.codes())

    def test_extra_widget_rejected(self):
        extra = deepcopy(self.rb["assets"][0]["widgets"][2])
        extra["widgetName"] = "TxtUnexpected"
        self.rb["assets"][0]["widgets"].append(extra)
        self.fx.sync_raw()
        self.assertIn("coverage.widgets", self.codes())

    def test_duplicate_widget_rejected(self):
        self.rb["assets"][0]["widgets"].append(deepcopy(self.rb["assets"][0]["widgets"][2]))
        self.fx.sync_raw()
        self.assertIn("readback.widget_duplicate", self.codes())

    def test_missing_mapping_rejected(self):
        self.rb["assets"][0]["nodeMappings"].pop()
        self.assertIn("coverage.node_mappings", self.codes())

    def test_wrong_slot_alignment_rejected(self):
        self.rb["assets"][0]["widgets"][2]["slot"]["properties"]["layoutData"]["alignment"]["x"] = 1
        self.fx.sync_raw()
        self.assertIn("actual.property_mismatch", self.codes())

    def test_wrong_cdo_mode_rejected(self):
        self.rb["assets"][0]["designSizeMode"] = "Desired"
        self.fx.sync_raw()
        self.assertIn("design_size_mode.mismatch", self.codes())

    def test_wrong_asset_object_rejected(self):
        self.rb["assets"][0]["assetObjectPath"] += "_Other"
        self.fx.sync_raw()
        self.assertIn("identity.assetObjectPath", self.codes())

    def test_structural_checks_need_exact_report(self):
        self.fx.bundle["verification"]["checks"][0]["artifactPath"] = "other.json"
        self.fx.sync_bundle()
        self.assertIn("verification.artifact_path", self.codes())

    def test_each_asset_needs_both_structural_checks(self):
        self.fx.bundle["verification"]["checks"].pop()
        self.fx.sync_bundle()
        self.assertIn("verification.check_coverage", self.codes())

    def test_mixed_asset_class_fallback_supported(self):
        self.rb["acquisition"] = {"method": "mixed", "fieldFallbacks": [{"jsonPath": "$.assets[0].assetClass", "fallbackReason": "Official get_asset_class returns generated CDO class instead of asset class."}]}
        self.rb["evidence"][0]["method"] = "mixed"
        self.assertTrue(self.fx.report()["valid"], self.fx.report()["errors"])

    def test_unknown_fallback_path_rejected(self):
        self.rb["acquisition"] = {"method": "mixed", "fieldFallbacks": [{"jsonPath": "$.assets[0].widgets", "fallbackReason": "not supported"}]}
        self.assertIn("acquisition.fallback_scope", self.codes())

    def test_nested_mcp_return_value_pointer_supported(self):
        self.assertEqual({"actual": 2}, _json_pointer({"result": {"returnValue": '{"assets":[{"actual":2}]}' }}, "/result/returnValue/assets/0"))

    def test_route_valid_prototype_passes(self):
        errors = []
        _validate_prototype_readback_checks(self.fx.bundle, self.fx.req, self.fx.bundlepath, self.fx.reqpath, errors)
        self.assertEqual([], errors)

    def test_route_forged_prototype_fails(self):
        self.rb["assets"][0]["designSizeMode"] = "Desired"
        write_json(self.fx.rbpath, self.rb)
        errors = []
        _validate_prototype_readback_checks(self.fx.bundle, self.fx.req, self.fx.bundlepath, self.fx.reqpath, errors)
        self.assertTrue(errors)

    def test_route_production_cannot_reuse_prototype_report(self):
        self.fx.bundle["assets"][0]["assetPath"] = "/Game/UI/UMG/ContractTest/umg_contracttest"
        errors = []
        _validate_prototype_readback_checks(self.fx.bundle, self.fx.req, self.fx.bundlepath, self.fx.reqpath, errors)
        self.assertIn("prototype.production_forbidden", {e["code"] for e in errors})

    def test_route_mixed_assets_rejected(self):
        self.fx.bundle["assets"].append({"id": "formal", "assetPath": "/Game/UI/UMG/ContractTest/umg_contracttest"})
        errors = []
        _validate_prototype_readback_checks(self.fx.bundle, self.fx.req, self.fx.bundlepath, self.fx.reqpath, errors)
        self.assertIn("prototype.mixed_bundle", {e["code"] for e in errors})

    def test_route_planned_bundle_without_passes_unchanged(self):
        for check in self.fx.bundle["verification"]["checks"]:
            check["status"] = "pending"
        self.fx.rbpath.unlink()
        errors = []
        _validate_prototype_readback_checks(self.fx.bundle, self.fx.req, self.fx.bundlepath, self.fx.reqpath, errors)
        self.assertEqual([], errors)


class CurrentR8Integration(unittest.TestCase):
    def setUp(self):
        if not OPTIONS.request_root:
            self.skipTest("Pass --request-root for the real R8 authority integration test")
        self.temp = tempfile.TemporaryDirectory(prefix="prototype-r8-test-", dir=OPTIONS.output_root)
        self.addCleanup(self.temp.cleanup)
        self.fx = fx = SyntheticFixture(Path(self.temp.name))
        source = Path(OPTIONS.request_root)
        fx.req = load_json(source / "ui-requirement.json")
        fx.bundle = load_json(source / "ui-build-bundle.executed.json")
        fx.reqpath = fx.root / fx.bundle["requirement"]["path"]
        for asset in fx.bundle["assets"]:
            destination = fx.root / asset["layoutSpecPath"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((source / asset["layoutSpecPath"]).read_bytes())
            asset["layoutSpecSha256"] = sha256_file(destination)
        fx.bundle["execution"]["startedAt"] = "2026-09-14T12:00:00+08:00"
        fx.bundle["execution"]["completedAt"] = "2026-09-14T12:05:00+08:00"
        for check in fx.bundle["verification"]["checks"]:
            if check.get("type") in {"widget-tree", "key-properties"}:
                check.update(status="passed", artifactPath=fx.rbpath.name)
        write_json(fx.reqpath, fx.req)
        fx.bundle["requirement"]["sha256"] = sha256_file(fx.reqpath)
        fx.initialize_readback()

    def codes(self):
        return {e["code"] for e in self.fx.report()["errors"]}

    def test_current_eight_asset_bundle_route(self):
        from validate_build_bundle import DEFAULT_SCHEMA as BUNDLE_SCHEMA, validate_build_bundle
        fx = self.fx
        report = fx.report()
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(8, report["scope"]["assetCount"])
        self.assertEqual(165, report["scope"]["widgetCount"])
        write_json(fx.rbpath, fx.rb)
        report = validate_build_bundle(fx.bundle, load_json(BUNDLE_SCHEMA), bundle_path=fx.bundlepath, requirement_spec=fx.req, requirement_path=fx.reqpath)
        self.assertTrue(report["valid"], report["errors"])

    def test_collection_wrong_entry_class_rejected(self):
        widget = next(w for a in self.fx.rb["assets"] for w in a["widgets"] if w["classPath"].endswith("LuaListView"))
        widget["entryWidgetClass"] = "/Game/UI/AIPrototype/Wrong/Wrong.Wrong_C"
        widget["properties"]["entryWidgetClass"] = {"refPath": widget["entryWidgetClass"]}
        self.fx.sync_raw()
        self.assertIn("collection.entry_class", self.codes())

    def test_collection_entry_metadata_cannot_cover_missing_property(self):
        widget = next(w for a in self.fx.rb["assets"] for w in a["widgets"] if w["classPath"].endswith("LuaListView"))
        del widget["properties"]["entryWidgetClass"]
        self.fx.sync_raw()
        self.assertIn("collection.entry_binding", self.codes())

    def test_entry_parent_class_rejected(self):
        self.fx.rb["assets"][0]["parentClassPath"] = "/Script/UMG.UserWidget"
        self.fx.sync_raw()
        self.assertIn("identity.parentClassPath", self.codes())

    def test_runtime_field_actual_variable_rejected(self):
        widget = next(w for a in self.fx.rb["assets"] for w in a["widgets"] if w["classPath"].endswith("TextBlock") and w["isVariable"])
        widget["isVariable"] = False
        self.fx.sync_raw()
        self.assertIn("runtime.actual_variable", self.codes())

    def test_initial_state_branch_visibility_rejected(self):
        branch = next(b for m in self.fx.req["stateModels"] for b in m.get("implementation", {}).get("branches", []))
        mapping = next(m for m in self.fx.bundle["nodeMappings"] if branch["panelElementId"] in m["requirementRefs"] and branch["stateId"] in m["stateRefs"])
        asset = next(a for a in self.fx.rb["assets"] if a["assetId"] == mapping["assetId"])
        actual_mapping = next(m for m in asset["nodeMappings"] if m["nodeMappingId"] == mapping["id"])
        widget = next(w for w in asset["widgets"] if w["widgetName"] == actual_mapping["widgetName"])
        widget["visibility"] = "Visible" if widget["visibility"] == "Collapsed" else "Collapsed"
        widget["properties"]["visibility"] = widget["visibility"]
        self.fx.sync_raw()
        self.assertIn("state.branch_actual", self.codes())

    def test_collection_wrong_preview_count_rejected(self):
        widget = next(w for a in self.fx.rb["assets"] for w in a["widgets"] if w["classPath"].endswith("LuaListView"))
        widget["properties"]["numDesignerPreviewEntries"] = 999
        self.fx.sync_raw()
        self.assertIn("actual.property_mismatch", self.codes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    OPTIONS, rest = parser.parse_known_args()
    if OPTIONS.output_root:
        OPTIONS.output_root.mkdir(parents=True, exist_ok=True)
    unittest.main(argv=[__file__] + rest)
