"""Synthetic fixtures only: no model calls, Editor access or real performance."""
import copy
import json
from pathlib import Path
import shutil
import unittest
import uuid

from PIL import Image

import art_benchmark as benchmark
import art_common as common


class ArtBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.parent = common.PLUGIN_ROOT.parent / "test-runs"
        self.root = self.parent / ("benchmark-synthetic-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.telemetry = benchmark._telemetry()
        self.start, self.finish = "2026-09-14T11:00:00Z", "2026-09-14T11:01:00Z"
        self.verification = self.make_verification("child", (50, 100, 150, 255))
        self.manifest = {"kind": "nextgame-ui-art-benchmark-manifest", "version": 1, "benchmarkId": "synthetic-only",
            "synthetic": True, "requireHeldOut": True, "samples": [{"id": "child", "assetKind": "child-widget",
                "membership": "held-out", "reference": common.binding(self.root / "child/reference.png")}], "runs": []}
        self.add_run("first", "first-production")
        self.manifest_path = self.root / "manifest.json"

    def tearDown(self):
        resolved = self.root.resolve()
        if resolved.parent != self.parent.resolve() or not resolved.name.startswith("benchmark-synthetic-"):
            raise ValueError("Refusing cleanup outside synthetic fixture directory")
        shutil.rmtree(resolved)

    def write(self, path, value):
        path = self.root / path
        common.write_json(path, value, replace=True)
        return path

    def make_verification(self, name, color):
        folder = self.root / name
        folder.mkdir()
        Image.new("RGBA", (20, 20), color).save(folder / "reference.png")
        snapshot = {"kind": "nextgame-ui-art-snapshot", "version": 1, "capturedAt": "2026-09-14T11:00:30Z",
            "acquisition": {"method": "fixture"}, "assets": [{"assetPath": "/Game/UI/UMG/Test/uw_test_icon",
                "parentClassPath": "/Script/UMG.UserWidget", "designSizeMode": "Desired", "referencesDigest": "1" * 64,
                "referencesComplete": False, "protectedReferences": [], "widgets": [{"widgetName": "Root",
                    "classPath": "/Script/UMG.CanvasPanel", "parentWidgetName": None, "isVariable": False,
                    "properties": {}, "slot": {"classPath": None, "properties": {}}}]}]}
        snapshot_path = self.write(folder / "snapshot.json", snapshot)
        request = self.write(folder / "request.json", {"synthetic": True, "baseline": {}})
        decisions = self.write(folder / "decisions.json", {"synthetic": True})
        state = common.state_hash(snapshot)
        plan = self.write(folder / "plan.json", {"kind": "nextgame-ui-art-plan", "version": 1, "request": common.binding(request),
            "decisions": common.binding(decisions), "baselineStateSha256": state, "expectedStateSha256": state,
            "operations": [], "status": "ready", "issues": [], "round": 0})
        execution = self.write(folder / "execution.json", {"kind": "nextgame-ui-art-execution", "version": 1,
            "planSha256": common.sha256(plan), "status": "completed", "completedIds": [], "currentOperation": None,
            "expectedStateSha256": state, "startedAt": self.start, "updatedAt": "2026-09-14T11:00:35Z",
            "readback": common.binding(snapshot_path)})
        comparison = self.write(folder / "comparison.json", {"version": 1, "referenceId": name, "dimensionAgreement": True,
            "mae": 0.0, "changedPixels": 0, "reference": common.binding(folder / "reference.png"),
            "actual": common.binding(folder / "reference.png"), "overlay": common.binding(folder / "reference.png"),
            "diff": common.binding(folder / "reference.png"), "synthetic": True})
        review = self.write(folder / "review.json", {"kind": "nextgame-ui-art-visual-review", "version": 1,
            "status": "needs-review", "snapshotSha256": common.sha256(snapshot_path), "comparisons": [common.binding(comparison)],
            "reviewedAt": "2026-09-14T11:00:45Z", "reviewer": {"actorType": "agent", "confirmationSource": "visual-inspection"},
            "message": "SYNTHETIC ONLY: no actual visual acceptance", "inspectedRegions": [name + ":icon"],
            "unresolved": [{"code": "synthetic.fixture", "message": "Not actual production evidence"}]})
        return self.write(folder / "verification.json", {"kind": "nextgame-ui-art-verification", "version": 1,
            "plan": common.binding(plan), "snapshot": common.binding(snapshot_path), "execution": common.binding(execution),
            "visualReview": common.binding(review), "comparisons": [common.binding(comparison)], "status": "needs-review",
            "checks": [{"id": "synthetic", "status": "passed", "details": "Synthetic report wiring only"}],
            "verifiedAt": "2026-09-14T11:00:50Z"})

    def add_run(self, identity, scenario, *, sample_id="child", verification=None, model_label="Candidate K3", ledger=True):
        result = {"kind": "nextgame-ui-art-benchmark-result", "version": 1, "runId": identity, "sampleId": sample_id,
            "modelLabel": model_label, "scenario": scenario, "synthetic": True, "timingSource": "measured-run-clock",
            "startedAt": self.start, "finishedAt": self.finish, "humanCorrectionSource": "counted-review-events",
            "humanCorrections": [{"id": "correct-1", "timestamp": "2026-09-14T11:00:40Z"}],
            "verification": common.binding(verification or self.verification)}
        result_path = self.write(identity + "-result.json", result)
        run_digest = common.digest(identity)
        call_digest = common.digest(identity + "-call")
        run = {"id": identity, "sampleId": sample_id, "modelLabel": model_label, "scenario": scenario, "result": common.binding(result_path),
            "ledger": None, "measurementBoundaryId": "art-refinement", "runIdDigest": run_digest,
            "expectedModelCalls": [{"stage": "art", "agentRole": "visual", "callIdDigest": call_digest}]}
        if ledger:
            event = self.telemetry.make_model_call_event("synthetic-only", "art", "choose-resource", provider="test-provider",
                model="synthetic-provider-model", agent_role="visual", token_source="provider-receipt",
                measurement_boundary_id="art-refinement", call_id_digest=call_digest, run_id_digest=run_digest,
                timestamp="2026-09-14T11:00:20Z", usage_receipt_sha256=common.digest(identity + "-synthetic-receipt"),
                inputTokens=100, cachedInputTokens=20, outputTokens=40, reasoningTokens=5, visionTokens=10)
            ledger_path = self.write(identity + "-ledger.json", {"schemaVersion": "1.1", "events": [event]})
            run["ledger"] = common.binding(ledger_path)
        self.manifest["runs"].append(run)
        return run

    def report(self):
        self.write(self.manifest_path, self.manifest)
        return benchmark.build_report(self.manifest_path)

    def change_result(self, run, **values):
        path = Path(run["result"]["path"])
        result = common.load_json(path)
        result.update(values)
        self.write(path, result)
        run["result"] = common.binding(path)

    def change_ledger(self, run, update):
        path = Path(run["ledger"]["path"])
        ledger = common.load_json(path)
        update(ledger)
        self.write(path, ledger)
        run["ledger"] = common.binding(path)

    def test_measured_tokens_time_and_corrections_have_no_invented_total(self):
        report = self.report()
        row = report["rows"][0]
        self.assertEqual(row["modelLabel"], "Candidate K3")
        self.assertEqual(row["tokens"]["providerModels"], ["test-provider/synthetic-provider-model"])
        self.assertEqual(row["elapsedSeconds"], 60)
        self.assertEqual(row["humanCorrections"], 1)
        self.assertEqual(row["tokens"]["metrics"]["inputTokens"], 100)
        self.assertEqual(row["tokens"]["metrics"]["outputTokens"], 40)
        self.assertNotIn("totalTokens", row["tokens"])
        self.assertEqual(row["quality"]["sourceStatus"], "needs-review")
        self.assertFalse(row["quality"]["productionValidated"])
        self.assertEqual(report["qualityAcceptance"], "not-awarded-by-benchmark")
        self.assertFalse(report["heldOutRequirementSatisfied"])

    def test_first_local_rerun_and_held_out_coverage_stay_explicit(self):
        screen_verification = self.make_verification("screen", (200, 30, 40, 255))
        self.manifest["samples"].append({"id": "screen", "assetKind": "full-screen", "membership": "held-out",
            "reference": common.binding(self.root / "screen/reference.png")})
        self.add_run("local", "local-change")
        self.add_run("again", "rerun", sample_id="screen", verification=screen_verification)
        report = self.report()
        self.assertTrue(report["heldOutRequirementSatisfied"])
        self.assertEqual(report["coverage"][0]["missingScenarios"], [])
        self.add_run("other", "first-production", model_label="Other supplied label")
        self.assertFalse(self.report()["heldOutRequirementSatisfied"])

    def test_missing_and_partly_unmeasured_tokens_are_null(self):
        run = self.manifest["runs"][0]
        self.change_ledger(run, lambda ledger: (ledger["events"][0].pop("outputTokens"), ledger["events"][0].update(unmeasuredMetrics=["outputTokens"])))
        row = self.report()["rows"][0]
        self.assertEqual(row["tokens"]["status"], "partially-measured")
        self.assertIsNone(row["tokens"]["metrics"]["outputTokens"])
        self.assertEqual(row["tokens"]["metrics"]["inputTokens"], 100)
        run["ledger"] = None
        row = self.report()["rows"][0]
        self.assertIsNone(row["tokens"]["modelCallCount"])
        self.assertTrue(all(value is None for value in row["tokens"]["metrics"].values()))

    def test_missing_expected_receipt_is_unavailable_and_no_call_run_is_not_zero_tokens(self):
        run = self.manifest["runs"][0]
        self.change_ledger(run, lambda ledger: ledger.update(events=[]))
        self.assertEqual(self.report()["rows"][0]["tokens"]["reason"], "missing-provider-receipts")
        run["expectedModelCalls"] = []
        row = self.report()["rows"][0]
        self.assertEqual(row["tokens"]["modelCallCount"], 0)
        self.assertIsNone(row["tokens"]["metrics"]["inputTokens"])

    def test_estimates_and_tokenizer_proxy_are_rejected(self):
        run = self.manifest["runs"][0]
        self.change_result(run, estimatedElapsedSeconds=10)
        with self.assertRaisesRegex(ValueError, "Additional properties"):
            self.report()
        path = Path(run["result"]["path"])
        result = common.load_json(path)
        result.pop("estimatedElapsedSeconds")
        self.write(path, result)
        run["result"] = common.binding(path)
        event = self.telemetry.make_model_call_event("synthetic-only", "art", "choose-resource", provider="test-provider",
            model="synthetic-provider-model", agent_role="visual", token_source="tokenizer-proxy",
            measurement_boundary_id="art-refinement", call_id_digest=run["expectedModelCalls"][0]["callIdDigest"], run_id_digest=run["runIdDigest"],
            timestamp="2026-09-14T11:00:20Z", tokenizerProxyTokens=50, tokenizer_encoding="test", tokenizer_version="test")
        self.change_ledger(run, lambda ledger: ledger.update(events=[event]))
        with self.assertRaisesRegex(ValueError, "Tokenizer proxies"):
            self.report()

    def test_stale_ledger_and_nested_quality_image_are_rejected(self):
        run = self.manifest["runs"][0]
        Path(run["ledger"]["path"]).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed bound file"):
            self.report()
        run["ledger"] = None
        # Keep the top-level sample binding current: the nested verification
        # binding must still independently detect changed image bytes.
        image = self.root / "child/reference.png"
        Image.new("RGBA", (20, 20), "white").save(image)
        self.manifest["samples"][0]["reference"] = common.binding(image)
        with self.assertRaisesRegex(ValueError, "changed bound file"):
            self.report()

    def test_reference_library_cannot_be_relabelled_held_out(self):
        self.manifest["samples"].append({**self.manifest["samples"][0], "id": "library-copy", "membership": "reference-library"})
        with self.assertRaisesRegex(ValueError, "also be declared held-out"):
            self.report()

    def test_result_identity_time_and_human_events_are_checked(self):
        run = self.manifest["runs"][0]
        self.change_result(run, modelLabel="Different label")
        with self.assertRaisesRegex(ValueError, "modelLabel"):
            self.report()
        self.change_result(run, modelLabel=run["modelLabel"], finishedAt="2026-09-14T10:00:00Z")
        with self.assertRaisesRegex(ValueError, "finish precedes"):
            self.report()
        self.change_result(run, finishedAt=self.finish, humanCorrections=[{"id": "bad", "timestamp": "2026-09-14T12:00:00Z"}])
        with self.assertRaisesRegex(ValueError, "outside the measured run"):
            self.report()

    def test_fixture_cannot_be_declared_production_measurement(self):
        self.manifest["synthetic"] = False
        self.change_result(self.manifest["runs"][0], synthetic=False)
        with self.assertRaisesRegex(ValueError, "Fixture verification"):
            self.report()

    def test_reused_boundary_and_unexpected_calls_are_rejected(self):
        first = self.manifest["runs"][0]
        second = self.add_run("second", "rerun")
        second["runIdDigest"] = first["runIdDigest"]
        with self.assertRaisesRegex(ValueError, "reuse a telemetry run boundary"):
            self.report()
        self.manifest["runs"].pop()
        first["expectedModelCalls"] = []
        with self.assertRaisesRegex(ValueError, "zero-call run contains"):
            self.report()

    def test_reports_are_deterministic_synthetic_and_outside_plugin(self):
        report = self.report()
        output = self.root / "reports"
        receipt = benchmark.write_report(self.manifest_path, output)
        text = Path(receipt["markdown"]["path"]).read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC FIXTURES", text)
        self.assertIn("needs-review (synthetic)", text)
        self.assertEqual(benchmark.write_report(self.manifest_path, output), receipt)
        self.assertEqual(json.loads(Path(receipt["report"]["path"]).read_text(encoding="utf-8")), report)
        with self.assertRaisesRegex(ValueError, "outside the plugin"):
            benchmark.write_report(self.manifest_path, common.PLUGIN_ROOT / "invalid-runtime-output")


if __name__ == "__main__":
    unittest.main()
