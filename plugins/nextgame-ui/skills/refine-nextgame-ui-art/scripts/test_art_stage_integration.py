"""Synthetic-only on-disk integration evidence; never connects to Unreal.

Production-shaped acquisition claims below are deliberate test vectors, visibly
labelled SYNTHETIC TEST ONLY, created under the existing transient fixture root.
They are not user acceptance, real Unreal readback, or exportable UI evidence.
The tests exercise the genuine art helper and downstream completion gates.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from PIL import Image, ImageDraw

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
DOC_SCRIPTS = PLUGIN_ROOT / "skills/document-nextgame-umg/scripts"
if str(DOC_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DOC_SCRIPTS))

from art_common import binding, digest, load_json, sha256, state_hash, validate_art_stage, write_json
from art_images import compare_images
from art_pipeline import create_plan
from test_document_contracts import FinalizedSources
from _document_contract_common import BUNDLE_SCHEMA, READBACK_SCHEMA, canonical_sha256, validate_schema_instance
from validate_build_bundle import validate_build_bundle


SYNTHETIC = "SYNTHETIC TEST ONLY; no Editor was connected; not production evidence."


class LinkedArtFixture:
    """One immutable baseline plus independently hash-bound final art evidence."""

    def __init__(self):
        self.sources = FinalizedSources()
        self.root = self.sources.root
        (self.root / "SYNTHETIC-TEST-ONLY.txt").write_text(SYNTHETIC, encoding="utf-8")
        self.art_dir = self.root / "art"
        self.art_dir.mkdir()
        self.resource_dir = self.art_dir / "resources"
        self.resource_dir.mkdir()
        self.image(self.resource_dir / "test-icon.png", (8, 8))
        # The historical document fixture deliberately predates strict build
        # Slot proofs. Bring only these transient copies up to current lowering
        # rules, preserving their intended Desired mode and exact geometry.
        for asset in self.sources.bundle["assets"]:
            layout_path = self.root / asset["layoutSpecPath"]
            layout = load_json(layout_path)
            nodes = {n["id"]: n for n in layout["nodes"]}
            if asset["assetKind"] == "screen":
                # This fixture's screen owns only host panels; child assets own
                # the buttons. Its local lowering does not own direct input.
                layout["profile"]["interactive"] = False
            for node in layout["nodes"]:
                parent = nodes.get(node.get("parent"), {})
                if parent.get("role") == "input.button" and node["role"] == "container.canvas":
                    node["buttonSlot"] = {"padding": [0, 0, 0, 0], "horizontalAlignment": "Fill", "verticalAlignment": "Fill"}
                if layout["profile"].get("designSizeMode") == "Desired" and parent.get("parent", True) is None:
                    node["slotLayout"] = {"anchors": {"minimum": [0, 0], "maximum": [0, 0]},
                        "offsets": {"left": 0, "top": 0, "right": layout["referenceSize"][0], "bottom": layout["referenceSize"][1]},
                        "alignment": [0, 0], "autoSize": False}
            self.save(layout_path, layout)
            asset["layoutSpecSha256"] = sha256(layout_path)
            actual = next(a for a in self.sources.readback["assets"] if a["assetPath"] == asset["assetPath"])
            actual["designSizeMode"] = layout["profile"].get("designSizeMode", "FillScreen")

        # Freeze the old graph; the art request must never hash the final Bundle
        # which itself hashes this request and the verification (a hash cycle).
        self.baseline_bundle_path = self.root / "baseline-bundle.json"
        self.baseline_readback_path = self.root / "baseline-readback.json"
        baseline_bundle = copy.deepcopy(self.sources.bundle)
        for check in baseline_bundle["verification"]["checks"]:
            if check.get("type") in ("widget-tree", "key-properties"):
                check["artifactPath"] = self.baseline_readback_path.name
        self.save(self.baseline_bundle_path, baseline_bundle)
        baseline_readback = copy.deepcopy(self.sources.readback)
        baseline_readback["bundleBinding"]["sha256"] = sha256(self.baseline_bundle_path)
        self.save(self.baseline_readback_path, baseline_readback)

        self.baseline_snapshot_path = self.art_dir / "baseline-snapshot.json"
        self.snapshot_path = self.art_dir / "final-snapshot.json"
        self.snapshot = self.make_snapshot()
        baseline_snapshot = copy.deepcopy(self.snapshot)
        baseline_snapshot["capturedAt"] = "2026-09-14T10:00:00+08:00"
        self.save(self.baseline_snapshot_path, baseline_snapshot)
        self.save(self.snapshot_path, self.snapshot)

        self.request_path = self.art_dir / "ui-art-request.json"
        self.decisions_path = self.art_dir / "ui-art-decisions.json"
        self.plan_path = self.art_dir / "ui-art-plan.json"
        self.execution_path = self.art_dir / "ui-art-execution.json"
        self.review_path = self.art_dir / "ui-art-visual-review.json"
        self.verification_path = self.art_dir / "ui-art-verification.json"
        self.request = {"kind": "nextgame-ui-art-request", "version": 1,
            "requestId": self.sources.requirement["requestId"], "goal": "upgrade-art",
            "originalText": SYNTHETIC, "scope": [{"assetPath": a["assetPath"]} for a in self.snapshot["assets"]],
            "baseline": {"requirement": binding(self.sources.requirement_path),
                "bundle": binding(self.baseline_bundle_path), "readback": binding(self.baseline_readback_path),
                "snapshot": binding(self.baseline_snapshot_path)},
            "references": [], "resourceDir": str(self.resource_dir), "productionAuthorized": True,
            "budget": {"maxCorrectionRounds": 2, "maxModelCalls": 0, "tokenLimits": {}}}
        self.capture_paths, self.captures, self.comparison_paths, self.comparisons = [], [], [], []
        for asset in self.sources.bundle["assets"]:
            sizes = ([2560, 1440], [3200, 1440], [2560, 1800]) if asset["assetKind"] == "screen" else (asset["referenceSize"],)
            for index, size in enumerate(sizes):
                ref_id = f"synthetic-{asset['id']}-{index}"
                reference_path = self.art_dir / f"{ref_id}-reference.png"
                actual_path = self.art_dir / f"{ref_id}-actual.png"
                self.image(reference_path, tuple(size))
                actual_path.write_bytes(reference_path.read_bytes())
                context = {"size": list(size), "dpiScale": 1, "locale": "zh-CN",
                    "dataId": "synthetic-test-data", "stateId": "synthetic-default",
                    "fontSetDigest": digest({"fontSet": SYNTHETIC}), "background": [0, 0, 0, 1]}
                widget = next(a for a in self.snapshot["assets"] if a["assetPath"] == asset["assetPath"])["widgets"][0]
                regions = [{"id": "synthetic-region", "bounds": [0, 0, min(32, size[0]), min(32, size[1])],
                    "widgetNames": [widget["widgetName"]]}]
                self.request["references"].append({"id": ref_id, "assetPath": asset["assetPath"],
                    "image": binding(reference_path), "context": context, "regions": regions})
                capture_path = self.art_dir / f"{ref_id}-capture.json"
                capture = {"kind": "nextgame-ui-art-capture", "version": 1, "assetPath": asset["assetPath"],
                    "context": context, "snapshotSha256": sha256(self.snapshot_path), "image": binding(actual_path),
                    "capturedAt": "2026-09-14T10:04:00+08:00",
                    "acquisition": {"method": "nxue-agent", "fallbackReason": SYNTHETIC}, "canonical": True}
                self.save(capture_path, capture)
                # Real image comparison code; no fabricated numeric similarity.
                comparison_dir = self.art_dir / f"{ref_id}-comparison"
                comparison = compare_images(reference_path, actual_path, comparison_dir,
                    [{"id": r["id"], "bounds": r["bounds"]} for r in regions])
                comparison.update({"referenceId": ref_id, "capture": binding(capture_path)})
                comparison_path = comparison_dir / "comparison.json"
                self.save(comparison_path, comparison)
                self.capture_paths.append(capture_path)
                self.captures.append(capture)
                self.comparison_paths.append(comparison_path)
                self.comparisons.append(comparison)
        self.save(self.request_path, self.request)
        self.decisions = {"kind": "nextgame-ui-art-decisions", "version": 1,
            "requestSha256": sha256(self.request_path), "decisions": []}
        self.save(self.decisions_path, self.decisions)
        self.plan = create_plan(self.request_path, self.decisions_path, validate_sources=False)
        self.save(self.plan_path, self.plan)
        self.execution = {"kind": "nextgame-ui-art-execution", "version": 1,
            "planSha256": sha256(self.plan_path), "status": "completed", "completedIds": [],
            "currentOperation": None, "expectedStateSha256": self.plan["expectedStateSha256"],
            "startedAt": "2026-09-14T10:01:00+08:00", "updatedAt": "2026-09-14T10:02:00+08:00",
            "readback": binding(self.snapshot_path)}
        self.save(self.execution_path, self.execution)
        self.review = {"kind": "nextgame-ui-art-visual-review", "version": 1, "status": "passed",
            "snapshotSha256": sha256(self.snapshot_path), "comparisons": [],
            "reviewedAt": "2026-09-14T10:05:00+08:00",
            "reviewer": {"actorType": "agent", "confirmationSource": "visual-inspection"}, "message": SYNTHETIC,
            "inspectedRegions": [r["id"] + ":" + region["id"] for r in self.request["references"] for region in r["regions"]],
            "unresolved": []}
        self.verification = {"kind": "nextgame-ui-art-verification", "version": 1,
            "plan": binding(self.plan_path), "snapshot": binding(self.snapshot_path),
            "execution": binding(self.execution_path), "visualReview": {}, "comparisons": [],
            "status": "passed", "checks": [{"id": "synthetic-noop-actual-state", "status": "passed", "details": SYNTHETIC}],
            "verifiedAt": "2026-09-14T10:06:00+08:00"}
        self.sources.bundle.update({"version": "0.4", "reuseRelations": []})
        for asset in self.sources.bundle["assets"]:
            asset["representationKind"] = "layout-spec"
        self.sources.bundle["execution"]["completedAt"] = "2026-09-14T10:06:00+08:00"
        self.sources.readback.update({"version": "0.4", "reuseRelations": [], "capturedAt": "2026-09-14T10:07:00+08:00"})
        for asset in self.sources.readback["assets"]:
            asset.update({"representationKind": "layout-spec", "generatedClassPath": asset["assetObjectPath"] + "_C"})
        self.flush()

    def save(self, path, value):
        write_json(path, value, replace=True)

    @staticmethod
    def image(path, size):
        image = Image.new("RGBA", size, (22, 35, 47, 255))
        ImageDraw.Draw(image).text((2, 2), "SYNTHETIC TEST ONLY", fill=(255, 210, 80, 255))
        image.save(path)

    def make_snapshot(self):
        assets = []
        for source in self.sources.readback["assets"]:
            widgets = []
            for node in source["widgets"]:
                widgets.append({**{k: node[k] for k in ("widgetName", "classPath", "parentWidgetName", "isVariable")},
                    "properties": {k: node[k] for k in ("visibility", "entryWidgetClass") if k in node},
                    "slot": {"classPath": None, "properties": {}}})
            protected = [w["widgetName"] for w in widgets if w["isVariable"]]
            assets.append({"assetPath": source["assetPath"], "parentClassPath": source["parentClassPath"],
                "designSizeMode": source["designSizeMode"], "protectedReferences": protected,
                "referencesDigest": digest(protected), "referencesComplete": True, "widgets": widgets})
        return {"kind": "nextgame-ui-art-snapshot", "version": 1, "capturedAt": "2026-09-14T10:03:00+08:00",
            "acquisition": {"method": "nxue-agent", "fallbackReason": SYNTHETIC}, "assets": assets}

    def flush(self):
        """Rebind downstream files to distinguish semantic failure from stale hash."""
        for capture_path, capture, comparison_path, comparison in zip(
            self.capture_paths, self.captures, self.comparison_paths, self.comparisons
        ):
            self.save(capture_path, capture)
            comparison["capture"] = binding(capture_path)
            self.save(comparison_path, comparison)
        self.review["comparisons"] = [binding(p) for p in self.comparison_paths]
        self.save(self.review_path, self.review)
        self.verification.update({"comparisons": self.review["comparisons"], "visualReview": binding(self.review_path),
            "plan": binding(self.plan_path), "snapshot": binding(self.snapshot_path), "execution": binding(self.execution_path)})
        self.save(self.verification_path, self.verification)
        self.stage = {"goal": self.request["goal"], "request": self.relative_binding(self.request_path),
            "plan": self.relative_binding(self.plan_path), "verification": self.relative_binding(self.verification_path)}
        self.sources.bundle["artStage"] = self.stage
        self.save(self.sources.bundle_path, self.sources.bundle)
        self.sources.readback["bundleBinding"]["sha256"] = sha256(self.sources.bundle_path)
        self.save(self.sources.readback_path, self.sources.readback)
        self.sources.acceptance = self.sources._make_acceptance()
        self.sources.acceptance["reviewedAt"] = "2026-09-14T10:08:00+08:00"
        self.save(self.sources.acceptance_path, self.sources.acceptance)

    def relative_binding(self, path):
        return {"path": path.relative_to(self.root).as_posix(), "sha256": sha256(path)}

    def helper(self, *, readback=True):
        return validate_art_stage(self.stage, bundle_path=self.sources.bundle_path,
            requirement=self.sources.requirement, requirement_path=self.sources.requirement_path,
            readback=self.sources.readback if readback else None)

    def bundle_report(self):
        return validate_build_bundle(self.sources.bundle, load_json(BUNDLE_SCHEMA),
            bundle_path=self.sources.bundle_path, requirement_spec=self.sources.requirement,
            requirement_path=self.sources.requirement_path, check_linked_files=True)

    def close(self):
        self.sources.close()


class ArtStageLinkedIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fx = LinkedArtFixture()
        self.addCleanup(self.fx.close)

    def assertRejected(self, expected_code=None):
        issues = self.fx.helper()
        self.assertTrue(issues, "Tampered on-disk art evidence was accepted")
        if expected_code:
            self.assertIn(expected_code, {i["code"] for i in issues}, issues)
        bundle = self.fx.bundle_report()
        self.assertFalse(bundle["valid"], bundle)
        readback = self.fx.sources.validate_readback()
        self.assertFalse(readback["valid"], readback)

    def test_comparison_cannot_substitute_another_target_image(self):
        other=self.fx.art_dir/'unrelated-target.png'
        reference=self.fx.request['references'][0]
        Image.new('RGBA',tuple(reference['context']['size']),(255,0,0,255)).save(other)
        self.fx.comparisons[0]['reference'].update(binding(other))
        self.fx.flush()
        self.assertRejected('art.comparison_identity')

    def test_comparison_numeric_metrics_are_recomputed(self):
        self.fx.comparisons[0]['mae']=123
        self.fx.flush()
        self.assertRejected('art.invalid')

    def test_old_normalized_readback_cannot_rebind_to_final_art(self):
        self.fx.sources.readback['capturedAt']='2026-09-14T10:02:00+08:00'
        self.fx.flush()
        self.assertIn('art.readback_time',{i['code'] for i in self.fx.helper()})
        self.assertFalse(self.fx.sources.validate_readback()['valid'])

    def test_parent_class_change_after_art_is_rejected(self):
        self.fx.sources.readback['assets'][0]['parentClassPath']='/Script/UMG.UserWidget'
        self.fx.flush()
        self.assertIn('art.readback_parent',{i['code'] for i in self.fx.helper()})
        self.assertFalse(self.fx.sources.validate_readback()['valid'])

    def test_noop_linked_art_passes_real_helper_bundle_readback_and_acceptance(self):
        self.assertEqual([], self.fx.plan["operations"])
        self.assertEqual(self.fx.plan["baselineStateSha256"], self.fx.plan["expectedStateSha256"])
        self.assertEqual([], self.fx.helper())
        for report in (self.fx.bundle_report(), self.fx.sources.validate_readback(), self.fx.sources.validate_acceptance()):
            self.assertTrue(report["valid"], report["errors"])

    def test_document_cli_loads_art_helper_from_unrelated_working_directory(self):
        completed = subprocess.run([sys.executable, "-B", str(DOC_SCRIPTS / "validate_build_acceptance.py"),
            str(self.fx.sources.acceptance_path), "--requirement", str(self.fx.sources.requirement_path),
            "--bundle", str(self.fx.sources.bundle_path), "--readback", str(self.fx.sources.readback_path)],
            cwd=self.fx.root, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["valid"])

    def test_fixture_acquisition_cannot_be_promoted_to_production(self):
        self.fx.snapshot["acquisition"] = {"method": "fixture"}
        self.fx.save(self.fx.snapshot_path, self.fx.snapshot)
        self.fx.review["snapshotSha256"] = sha256(self.fx.snapshot_path)
        for capture in self.fx.captures:
            capture["snapshotSha256"] = sha256(self.fx.snapshot_path)
        self.fx.execution["readback"] = binding(self.fx.snapshot_path)
        self.fx.save(self.fx.execution_path, self.fx.execution)
        self.fx.flush()
        self.assertRejected("art.fixture")

    def test_missing_verification_is_not_development_completion(self):
        self.fx.verification_path.unlink()
        self.assertRejected("binding.stale")

    def test_stale_plan_sidecar_hash_is_rejected(self):
        self.fx.plan_path.write_text(self.fx.plan_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertRejected("binding.stale")

    def test_rebound_capture_wrong_dpi_context_is_rejected(self):
        self.fx.captures[0]["context"] = copy.deepcopy(self.fx.captures[0]["context"])
        self.fx.captures[0]["context"]["dpiScale"] = 1.25
        self.fx.flush()
        self.assertRejected("art.capture")

    def test_rebound_capture_wrong_snapshot_is_rejected(self):
        self.fx.captures[0]["snapshotSha256"] = "0" * 64
        self.fx.flush()
        self.assertRejected("art.capture")

    def test_rebound_unreviewed_region_is_rejected(self):
        self.fx.review["inspectedRegions"].pop()
        self.fx.flush()
        self.assertRejected("art.region_coverage")

    def test_pending_verification_never_passes_final_bundle(self):
        self.fx.verification["status"] = "needs-review"
        self.fx.flush()
        self.assertRejected("art.incomplete")

    def test_current_normalized_readback_tree_is_checked_not_old_bundle_hash(self):
        self.fx.sources.readback["assets"][0]["widgets"][0]["isVariable"] = not self.fx.sources.readback["assets"][0]["widgets"][0]["isVariable"]
        issues = self.fx.helper()
        self.assertIn("art.readback_tree", {i["code"] for i in issues}, issues)
        report = self.fx.sources.validate_readback()
        self.assertFalse(report["valid"], report)
        self.assertIn("art.readback_tree", {i["code"] for i in report["errors"]})
        self.assertFalse(self.fx.sources.validate_acceptance()["valid"])

    def test_reference_image_change_invalidates_final_art(self):
        image_path = Path(self.fx.request["references"][0]["image"]["path"])
        image_path.write_bytes(image_path.read_bytes() + b"SYNTHETIC-CHANGED")
        self.assertRejected("binding.stale")

    def test_legacy_schema_authorities_are_unchanged(self):
        schema = load_json(BUNDLE_SCHEMA)
        coordinate_shape = {'type': 'object', 'additionalProperties': False,
            'required': ['capability', 'version', 'contractSha256'],
            'properties': {'capability': {'const': 'source-target-coordinates/1'},
                'version': {'const': 1, 'type': 'integer'},
                'contractSha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}}}
        valid_binding = {'capability': 'source-target-coordinates/1', 'version': 1, 'contractSha256': 'a' * 64}
        for name in ('bundleV01', 'bundleV02', 'bundleV03', 'bundleV04'):
            # Versioned coordinate opt-in extends each closed Bundle branch;
            # prove its exact shape before subtracting it from the old authority.
            actual_shape = schema['$defs'][name]['properties'].pop('coordinateBinding')
            self.assertEqual(coordinate_shape, actual_shape)
            self.assertEqual([], validate_schema_instance(valid_binding, actual_shape))
            invalid = [dict(valid_binding, extra=True), dict(valid_binding, version=2),
                dict(valid_binding, version='1'), dict(valid_binding, capability='other/1'),
                dict(valid_binding, contractSha256='not-a-hash')]
            invalid.extend({key: value for key, value in valid_binding.items() if key != missing} for missing in valid_binding)
            for value in invalid:
                self.assertTrue(validate_schema_instance(value, actual_shape), (name, value))
        schema["title"] = "NextGame UIBuildBundle 0.1, 0.2, and 0.3"
        schema["oneOf"].remove({"$ref": "#/$defs/bundleV04"})
        for name in ("bundleV04", "artStage", "artArtifactLink"):
            schema["$defs"].pop(name)
        # Strip only registered opt-in capability additions; retain the exact
        # historical authority digest and all old closed-shape assertions.
        self.assertEqual(len(schema.pop("allOf")), 2)
        for name in ("bundleV01", "bundleV02", "bundleV03"):
            self.assertEqual(schema["$defs"][name]["properties"].pop("capabilities"), {"$ref": "#/$defs/capabilities"})
        for name in ("capabilities", "fixedWidthContentHeightCompatibility", "hostPropertyBinding"):
            schema["$defs"].pop(name)
        self.assertEqual(schema["$defs"]["nodeMapping"]["properties"].pop("initialStateRefs"), {"$ref": "#/$defs/idRefs"})
        schema["$defs"]["childSizingCompatibility"]["oneOf"].remove({"$ref": "#/$defs/fixedWidthContentHeightCompatibility"})
        handling = schema["$defs"]["stateHandling"]["properties"]
        self.assertEqual(handling.pop("initialStateRefs"), {"$ref": "#/$defs/idRefs"})
        self.assertEqual(handling.pop("propertyBindings"), {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"$ref": "#/$defs/hostPropertyBinding"}})
        handling["strategy"]["enum"].remove("owning-screen-shared-properties")
        self.assertEqual("b745531935a338112e7ab5b10ee8165935c51e8b8558a028dd681fe7d6601273", canonical_sha256(schema))
        old_bundle = load_json(self.fx.baseline_bundle_path)
        self.assertEqual([], validate_schema_instance(old_bundle, load_json(BUNDLE_SCHEMA)))
        old_bundle["artStage"] = self.fx.stage
        self.assertTrue(validate_schema_instance(old_bundle, load_json(BUNDLE_SCHEMA)))
        schema = load_json(READBACK_SCHEMA)
        schema["title"] = "NextGame Unreal Widget Readback 0.1, 0.2, and 0.3"
        schema["oneOf"].remove({"$ref": "#/$defs/readbackV04"})
        schema["$defs"].pop("readbackV04")
        self.assertEqual("f41370993da7c6f3380f2dc0da39fb89e3d30a03ca3b617e59a08fdee75d8484", canonical_sha256(schema))


if __name__ == "__main__":
    unittest.main()
