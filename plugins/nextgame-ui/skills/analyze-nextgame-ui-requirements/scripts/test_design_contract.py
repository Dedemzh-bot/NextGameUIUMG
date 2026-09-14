#!/usr/bin/env python3
"""Behavioral tests for structured design provenance and shared build gates."""
from __future__ import annotations

import copy
import json
import shutil
import unittest
import uuid
from pathlib import Path

from _contract_common import (ASSETS_ROOT, canonical_sha256, compute_approved_content_sha256,
    compute_request_input_digest, load_json, sha256_file)
from accepted_build_view import AcceptedBuildViewError, build_accepted_build_view, validate_accepted_build_view
from design_contract import (SEMANTIC_POLICIES, DesignContractError, accept_requirement, compatibility_authority_sha256,
    compile_contract, validate_design_contract)
from validate_requirement_spec import validate_requirement_spec
from validate_build_bundle import validate_build_bundle, DEFAULT_SCHEMA as BUNDLE_SCHEMA
from validate_requirement_coverage import validate_requirement_coverage


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture(root: Path) -> dict:
    source = {"sourceKey": "source-user", "kind": "user-text", "locatorKind": "inline",
        "description": "Synthetic authored design test.", "content": "Create a static full-screen panel for the contract test."}
    rule_text = "project-umg-rule: all umg_ assets use FillScreen."
    (root / "rule.txt").write_text(rule_text, encoding="utf-8")
    rule = {"sourceKey": "source-rule", "kind": "project-rule", "locatorKind": "local-file",
        "description": "Fixture project rule.", "path": str(root / "rule.txt"), "contentSha256": sha256_file(root / "rule.txt")}
    target = {"system": "role", "systemFolder": "Role", "mode": "production", "assetKind": "screen",
        "designCanvas": [2560, 1440], "targetAssetPaths": ["/Game/UI/UMG/Role/umg_contract_test"], "productionAuthorized": True}
    packet = {"version": "0.1", "requestId": "design-contract-test", "inputDigest": "0" * 64,
        "userRequest": {"originalText": [source["content"]], "language": "en"},
        "sources": [source, rule], "targetHints": target,
        "projectRuleRefs": [{"path": str(root / "rule.txt"), "required": True}]}
    packet["inputDigest"] = compute_request_input_digest(packet)
    write(root / "request-packet.json", packet)
    evidence = [{"id": "evidence-design", "sourceId": "source-user", "kind": "user-requirement",
        "description": "Authored full-screen rectangle.", "bounds": [0, 0, 1, 1],
        "sourceDimensions": [2560, 1440], "pixelBounds": [0, 0, 2560, 1440], "measurementMethod": "derived"},
        {"id": "evidence-rule", "sourceId": "source-rule", "kind": "project-reference", "description": rule_text}]
    main_ids = ["region-screen", "element-root", "acceptance-layout"]
    claims = [{"id": "claim-design", "type": "element-structure", "statement": "Adopt the authored full-screen panel.",
        "evidenceIds": ["evidence-design"], "confidence": 1, "impact": "high", "status": "accepted", "blocksBuild": False,
        "subjectRefs": main_ids},
        {"id": "claim-asset", "type": "asset-decomposition", "statement": "Apply project-umg-rule: FillScreen.",
        "evidenceIds": ["evidence-rule"], "confidence": 1, "impact": "high", "status": "accepted", "blocksBuild": False,
        "subjectRefs": ["asset-screen"]}]
    content = {"revision": 1, "requestId": packet["requestId"], "inputDigest": packet["inputDigest"],
        "request": {"purpose": "Contract test", "language": "en", "originalText": [source["content"]],
            "scope": ["One static panel"], "exclusions": ["Runtime code"], "completionCriteria": ["Panel fills the canvas"]},
        "sources": [{"id": s["sourceKey"], **s} for s in packet["sources"]], "target": target,
        "evidence": evidence, "claims": claims,
        "analysisPolicy": {**{p: True for p in SEMANTIC_POLICIES}, "noHistoryRolePacketsRequired": False},
        "uiModel": {"regions": [{"id": "region-screen", "nameHint": "PanelRoot", "purpose": "screen",
            "parentRegionId": None, "bounds": [0, 0, 1, 1], "geometryEvidenceId": "evidence-design",
            "inBuildScope": True, "evidenceIds": ["evidence-design"], "claimIds": ["claim-design"]}],
            "componentFamilies": [], "elements": [{"id": "element-root", "kind": "panel", "nameHint": "PanelRoot",
                "regionId": "region-screen", "parentElementId": None, "familyId": None, "runtimeControlled": False,
                "inBuildScope": True, "evidenceIds": ["evidence-design"], "claimIds": ["claim-design"], "properties": {"layout": "full-screen"}}],
            "collections": [], "runtimeFields": [], "responsiveIntent": []},
        "stateModels": [], "assetPlan": [{"id": "asset-screen", "assetPath": target["targetAssetPaths"][0],
            "assetKind": "screen", "referenceSize": [2560, 1440], "layoutSpecPath": "layout.json",
            "dependsOnAssetIds": [], "buildOrder": 0, "inBuildScope": True, "coversRegionIds": ["region-screen"],
            "coversElementIds": ["element-root"], "coversCollectionIds": [], "coversStateModelIds": [],
            "evidenceIds": ["evidence-rule"], "claimIds": ["claim-asset"], "boundaryClassification": "screen-root",
            "boundaryEvidenceIds": ["evidence-rule"], "designSizeModeDecision": {"mode": "FillScreen", "basis": "project-umg-rule",
                "evidenceIds": [], "claimId": "claim-asset", "reason": "Project basename rule."}}],
        "assumptions": [], "questions": [], "acceptanceCriteria": [{"id": "acceptance-layout", "description": "Panel fills screen.",
            "inBuildScope": True, "claimIds": ["claim-design"]}]}
    proof = {"version": "1", "kind": "synthetic-test-evidence", "description": "This test has one native root panel and no external recipe capabilities."}
    write(root / "compatibility.json", proof)
    contract = {"kind": "nextgame-ui-design-contract", "version": "1", "contractId": "contract-test",
        "origin": {"kind": "authored-design"}, "sourceBindings": [
            {"key": "packet", "role": "request-packet", "path": str(root / "request-packet.json"), "sha256": sha256_file(root / "request-packet.json"), "version": "0.1"},
            {"key": "compatibility", "role": "implementation-evidence", "path": str(root / "compatibility.json"), "sha256": sha256_file(root / "compatibility.json"), "version": "1"}],
        "moduleRefs": [], "content": content, "decisions": [{"pointer": "", "status": "locked",
            "valueSha256": canonical_sha256(content), "sourceKeys": ["packet"], "reason": "Authored synthetic test contract."}], "gapDecisions": [],
        "compatibility": {"status": "verified", "evidenceKeys": ["compatibility"], "notes": ["Synthetic fixture only; no live Editor evidence."]}}
    (root / "compatibility-review.txt").write_text("Synthetic test author explicitly reviews this fixture mapping.", encoding="utf-8")
    refresh_compatibility(root, contract)
    return contract


def refresh_compatibility(root: Path, contract: dict):
    report = {"kind": "nextgame-ui-design-compatibility-review", "version": "1", "level": "design-contract-compatibility",
        "contentSha256": canonical_sha256(contract["content"]), "moduleBindingsSha256": canonical_sha256(contract["moduleRefs"]),
        "authorityBindingsSha256": compatibility_authority_sha256(contract),
        "checks": [{"target": target, "status": "passed", "details": "Synthetic fixture design mapping reviewed."}
            for target in ["contract", *(m["moduleId"] for m in contract["moduleRefs"])]],
        "review": {"kind": "direct-user-message", "reviewedBy": "synthetic-test-reviewer", "reviewedAt": "2026-09-14T09:00:00Z",
            "messagePath": str(root / "compatibility-review.txt"), "messageSha256": sha256_file(root / "compatibility-review.txt")}}
    write(root / "compatibility.json", report)
    next(s for s in contract["sourceBindings"] if s["key"] == "compatibility")["sha256"] = sha256_file(root / "compatibility.json")


class DesignContractTests(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[3] / "Saved" / "CodexUITestTemp"
        parent.mkdir(parents=True, exist_ok=True)
        self.root = parent / ("design-" + uuid.uuid4().hex[:12])
        self.root.mkdir()
        self.schema = load_json(ASSETS_ROOT / "ui-requirement-spec.schema.json")
        self.contract = fixture(self.root)
        self.path = self.root / "design-contract.json"
        self.save()
        self.message = self.root / "review-message.txt"
        self.message.write_text("Synthetic test reviewer approves this exact fixture design.", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root)

    def save(self):
        write(self.path, self.contract)

    def compile(self):
        self.save()
        output = self.root / "pending.json"
        compile_contract(self.path, output)
        return output

    def accepted(self):
        pending = self.compile()
        accepted = self.root / "accepted.json"
        accept_requirement(pending, accepted, self.message, "synthetic-test-reviewer", "2026-09-14T10:00:00+08:00")
        return accepted

    def test_compile_full_validator_and_accepted_view(self):
        accepted = self.accepted()
        requirement = load_json(accepted)
        self.assertEqual(requirement["version"], "0.2")
        self.assertNotIn("findingsInputs", requirement["normalization"])
        self.assertTrue(validate_requirement_spec(requirement, self.schema, spec_path=accepted)["valid"])
        view, mode, reason = build_accepted_build_view(accepted)
        self.assertEqual((mode, reason), ("projected", None))
        self.assertTrue(validate_accepted_build_view(view, source_requirement=accepted)["valid"])

    def test_new_requirement_passes_bundle_and_coverage_with_linked_view(self):
        path = self.accepted()
        requirement = load_json(path)
        layout = load_json(ASSETS_ROOT / "example-composite-tabs-screen-layout-spec.json")
        layout["asset"]["name"] = "umg_contract_test"
        layout["profile"]["targetAsset"]["name"] = "umg_contract_test"
        layout["profile"].update({"interactive": False, "containsRepeatedElements": False, "explicitPanelSlots": True})
        layout["nodes"] = [layout["nodes"][0]]
        layout["notes"] = ["Synthetic planned layout only; no Editor connection."]
        write(self.root / "layout.json", layout)
        bundle = {"version": "0.1", "bundleId": "bundle-contract-test", "requirement": {
            "path": "accepted.json", "sha256": sha256_file(path), "requestId": requirement["requestId"],
            "revision": 1, "reviewStatus": "accepted", "approvedContentSha256": requirement["reviewGate"]["approvedContentSha256"]},
            "assets": [{"id": "build-screen", "assetPlanId": "asset-screen", "assetPath": requirement["target"]["targetAssetPaths"][0],
                "assetKind": "screen", "referenceSize": [2560, 1440], "layoutSpecPath": "layout.json",
                "layoutSpecSha256": sha256_file(self.root / "layout.json"), "dependsOnAssetIds": [], "buildOrder": 0, "status": "planned"}],
            "nodeMappings": [{"id": "mapping-root", "assetId": "build-screen", "layoutNodeId": "node-screen-root",
                "mappingKind": "direct", "requirementRefs": ["element-root", "region-screen", "asset-screen"],
                "claimIds": ["claim-design", "claim-asset"], "stateRefs": []}],
            "crossAssetOperations": [], "execution": {"status": "pending", "buildOrderAssetIds": ["build-screen"]},
            "verification": {"status": "pending", "checks": [{"id": "check-screen", "type": "schema", "assetId": "build-screen",
                "status": "pending", "details": "Validate authored panel", "requirementRefs": ["acceptance-layout"], "claimIds": ["claim-design"]}], "deviations": []}}
        bundle_path = self.root / "bundle.json"
        write(bundle_path, bundle)
        view, _, _ = build_accepted_build_view(path)
        checked = validate_build_bundle(bundle, load_json(BUNDLE_SCHEMA), bundle_path=bundle_path,
            requirement_spec=requirement, requirement_path=path, requirement_schema=self.schema,
            accepted_build_view=view, check_linked_files=True)
        self.assertTrue(checked["valid"], checked)
        checked = validate_requirement_coverage(bundle, requirement, bundle_path=bundle_path)
        self.assertTrue(checked["valid"], checked)

    def test_locked_field_change_fails_even_after_reapproval(self):
        path = self.accepted()
        requirement = load_json(path)
        requirement["uiModel"]["elements"][0]["nameHint"] = "PanelChanged"
        requirement["reviewGate"]["approvedContentSha256"] = compute_approved_content_sha256(requirement)
        checked = validate_requirement_spec(requirement, self.schema)
        self.assertIn("design.adoption_mismatch", {e["code"] for e in checked["errors"]})

    def test_declared_content_change_without_decision_digest_fails(self):
        self.contract["content"]["request"]["purpose"] = "Tampered purpose"
        self.save()
        self.assertFalse(validate_design_contract(self.contract, contract_path=self.path)["valid"])

    def test_source_file_change_is_rejected_from_accepted_view(self):
        path = self.accepted()
        (self.root / "compatibility.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(AcceptedBuildViewError):
            build_accepted_build_view(path)

    def test_missing_content_field_unknown_version_and_missing_decision(self):
        for edit in [lambda c: c["content"].pop("assetPlan"), lambda c: c.__setitem__("version", "999"), lambda c: c.__setitem__("decisions", [])]:
            changed = copy.deepcopy(self.contract)
            edit(changed)
            self.assertFalse(validate_design_contract(changed)["valid"])

    def test_open_high_gap_pending_decision_and_unverified_compatibility_block_acceptance(self):
        edits = [lambda c: c["gapDecisions"].append({"id": "gap-test", "pointer": "/uiModel", "status": "open", "impact": "high", "blocksBuild": True, "reason": "Missing agreed adaptation"}),
            lambda c: c["decisions"][0].__setitem__("status", "pending"),
            lambda c: c["compatibility"].__setitem__("status", "pending")]
        original = copy.deepcopy(self.contract)
        for i, edit in enumerate(edits):
            self.contract = copy.deepcopy(original)
            edit(self.contract)
            self.save()
            pending = self.root / f"pending-{i}.json"
            compile_contract(self.path, pending)
            with self.assertRaises(DesignContractError):
                accept_requirement(pending, self.root / f"accepted-{i}.json", self.message, "test", "2026-09-14T10:00:00Z")

    def test_pending_review_never_produces_executable_view(self):
        path = self.compile()
        with self.assertRaises(AcceptedBuildViewError):
            build_accepted_build_view(path)

    def test_path_escape_and_symlink_escape_fail(self):
        path = self.accepted()
        requirement = load_json(path)
        requirement["normalization"]["contractRef"] = "../design-contract.json"
        self.assertFalse(validate_requirement_spec(requirement, self.schema)["valid"])

    def test_unknown_schema_falls_back_and_old_schema_cannot_accept_new_requirement(self):
        path = self.accepted()
        changed_schema = copy.deepcopy(self.schema)
        changed_schema["description"] = "Unreviewed schema authority"
        schema_path = self.root / "other-schema.json"
        write(schema_path, changed_schema)
        view, mode, _ = build_accepted_build_view(path, requirement_schema_path=schema_path)
        self.assertEqual(mode, "full-fallback")
        self.assertFalse(view["buildAllowed"])
        old_schema = ASSETS_ROOT / "ui-requirement-spec-0.1.schema.json"
        with self.assertRaises(AcceptedBuildViewError):
            build_accepted_build_view(path, requirement_schema_path=old_schema)

    def test_shared_geometry_policy_cannot_be_disabled_or_rewritten(self):
        self.contract["content"]["analysisPolicy"]["geometryEvidenceRequired"] = False
        self.contract["decisions"][0]["valueSha256"] = canonical_sha256(self.contract["content"])
        self.save()
        self.assertFalse(validate_design_contract(self.contract, contract_path=self.path)["valid"])
        self.contract["content"]["analysisPolicy"]["geometryEvidenceRequired"] = True
        self.contract["content"]["uiModel"]["regions"][0]["bounds"] = [0, 0, 0.5, 1]
        self.contract["decisions"][0]["valueSha256"] = canonical_sha256(self.contract["content"])
        refresh_compatibility(self.root, self.contract)
        self.save()
        errors = validate_design_contract(self.contract, contract_path=self.path)["errors"]
        self.assertIn("geometry.requirement_drift", {e["code"] for e in errors})

    def test_legacy_accepted_requirement_still_requires_nine_real_roles(self):
        legacy = load_json(ASSETS_ROOT / "example-composite-tabs-requirement.json")
        legacy["normalization"]["findingsInputs"] = legacy["normalization"]["findingsInputs"][:-1]
        legacy["reviewGate"]["approvedContentSha256"] = compute_approved_content_sha256(legacy)
        errors = validate_requirement_spec(legacy, self.schema)["errors"]
        self.assertIn("normalization.role_coverage", {e["code"] for e in errors})

    def test_review_evidence_is_required_and_rehashed(self):
        path = self.accepted()
        requirement = load_json(path)
        requirement["reviewGate"].pop("designReview")
        requirement["reviewGate"]["approvedContentSha256"] = compute_approved_content_sha256(requirement)
        self.assertFalse(validate_requirement_spec(requirement, self.schema)["valid"])
        self.message.write_text("changed", encoding="utf-8")
        self.assertFalse(validate_requirement_spec(load_json(path), self.schema)["valid"])

    def test_old_review_receipt_cannot_be_reused_after_rehashing_all_design_fields(self):
        path = self.accepted()
        requirement = load_json(path)
        self.contract["content"]["uiModel"]["elements"][0]["nameHint"] = "PanelReauthored"
        self.contract["decisions"][0]["valueSha256"] = canonical_sha256(self.contract["content"])
        refresh_compatibility(self.root, self.contract)
        self.save()
        requirement["uiModel"] = copy.deepcopy(self.contract["content"]["uiModel"])
        from design_contract import _normalize
        requirement["normalization"] = _normalize(self.contract, self.path)
        requirement["reviewGate"]["approvedContentSha256"] = compute_approved_content_sha256(requirement)
        self.assertFalse(validate_requirement_spec(requirement, self.schema)["valid"])

    def test_full_packet_target_and_language_checks_run_without_explicit_packet_argument(self):
        for field, value in [("productionAuthorized", False), ("system", "bag")]:
            changed = copy.deepcopy(self.contract)
            changed["content"]["target"][field] = value
            changed["decisions"][0]["valueSha256"] = canonical_sha256(changed["content"])
            refresh_compatibility(self.root, changed)
            write(self.path, changed)
            validation = validate_design_contract(changed, contract_path=self.path)
            self.assertIn("packet.target_hint", {e["code"] for e in validation["errors"]})

    def test_arbitrary_packet_file_is_not_compatibility_evidence(self):
        self.contract["compatibility"]["evidenceKeys"] = ["packet"]
        self.save()
        self.assertIn("design.compatibility_role", {e["code"] for e in validate_design_contract(self.contract, contract_path=self.path)["errors"]})

    def add_module(self, status="Approved"):
        spec = {"schema_version": "2.0.0", "id": "SYS.ContractTest", "version": "1.0.0", "status": status,
            "approval": {"by": "synthetic-reviewer", "at": "2026-09-14T10:00:00Z"} if status == "Approved" else None,
            "geometry": {key: "synthetic" for key in ["space", "sizing", "anchor", "alignment", "offset", "size"]},
            "layout": {key: "synthetic" for key in ["kind", "padding", "gap", "horizontal_align", "vertical_align", "growth", "overflow"]}}
        recipe = {"format": "nextgame-design-recipes/1", "version": "1.0.0", "recipes": [
            {"id": "NG.ContractTest@1.0.0", "specRef": "SYS.ContractTest@1.0.0"}]}
        for key, document, role in [("spec", spec, "module-spec"), ("recipe", recipe, "recipe")]:
            source_path = self.root / (key + ".json")
            write(source_path, document)
            self.contract["sourceBindings"].append({"key": key, "role": role, "path": str(source_path),
                "sha256": sha256_file(source_path), "version": "1.0.0"})
        self.contract["moduleRefs"] = [{"moduleId": "test-module", "specRef": "SYS.ContractTest@1.0.0",
            "recipeRef": "NG.ContractTest@1.0.0", "specSourceKey": "spec", "recipeSourceKey": "recipe",
            "recipeRefPointer": "/recipes/0/id", "contentPointers": ["/uiModel"], "mappingStatus": "explicit-content"}]
        self.contract["decisions"][0]["sourceKeys"].extend(["spec", "recipe"])
        refresh_compatibility(self.root, self.contract)
        self.save()

    def test_actual_module_identity_and_recipe_version_are_bound(self):
        self.add_module()
        self.assertTrue(validate_design_contract(self.contract, contract_path=self.path)["buildReady"])
        self.contract["moduleRefs"][0]["specRef"] = "SYS.ContractTest@9.0.0"
        refresh_compatibility(self.root, self.contract)
        self.save()
        self.assertIn("design.module_identity", {e["code"] for e in validate_design_contract(self.contract, contract_path=self.path)["errors"]})

    def test_draft_module_and_unsupported_mapping_cannot_be_accepted(self):
        self.add_module(status="Draft")
        validation = validate_design_contract(self.contract, contract_path=self.path)
        self.assertTrue(validation["valid"], validation)
        self.assertFalse(validation["buildReady"])
        self.contract["moduleRefs"][0]["mappingStatus"] = "unsupported"
        refresh_compatibility(self.root, self.contract)
        self.save()
        self.assertFalse(validate_design_contract(self.contract, contract_path=self.path)["buildReady"])

    def test_module_adoption_requires_source_mapping_for_every_content_leaf(self):
        self.add_module()
        self.contract["decisions"][0]["sourceKeys"] = ["packet"]
        self.save()
        self.assertIn("design.module_decision_source", {e["code"] for e in validate_design_contract(self.contract, contract_path=self.path)["errors"]})


if __name__ == "__main__":
    unittest.main()
