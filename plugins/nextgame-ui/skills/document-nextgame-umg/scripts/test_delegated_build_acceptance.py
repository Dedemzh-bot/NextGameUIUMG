#!/usr/bin/env python3
"""Synthetic, real-shaped fixtures for the opt-in delegated acceptance contract.

All artifacts live in the existing isolated test workspace. These are not a grant,
review, consumption or acceptance for any production request.
"""

from __future__ import annotations

import copy
import hashlib
import unittest

from _document_contract_common import BUILD_ACCEPTANCE_SCHEMA, load_json, sha256_file, validate_schema_instance, write_json
from prepare_program_document_contract import build_document_content_contract
from test_document_contracts import FinalizedSources, error_codes, make_png
from validate_build_acceptance import (
    DELEGATED_REVIEWER, GRANT_STATEMENTS, delegated_consumption_path,
    delegated_result_fingerprint, validate_acceptance_handoff_binding, validate_build_acceptance,
)


class DelegatedAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.sources = FinalizedSources()
        self.root = self.sources.root
        self.grant_path = self.root / "acceptance-authority/grant.json"
        self.grant_path.parent.mkdir(parents=True, exist_ok=True)
        self.review_path = self.root / "acceptance-authority/result-review.json"
        self.packet_path = self.root / "request-packet.json"
        self.original_path = self.root / "original-authorization.json"
        quotes = GRANT_STATEMENTS["zh-one-test-automation/1"]
        self.message = "Synthetic direct-user fixture. " + " ".join(quotes)
        self.packet = {
            "version": "0.1", "requestId": self.sources.requirement["requestId"],
            "userRequest": {"originalText": [self.message]},
            "sources": [{"sourceKey": "source-user-1", "kind": "user-text", "locatorKind": "inline", "content": self.message}],
        }
        self.original = {
            "kind": "request-scoped-user-authorization", "sourceMessage": self.message,
            "freshEvidenceRequired": True, "mayContinueWithoutRepeatedQuestions": True,
            "mayFabricatePostResultUserMessage": False, "mayReuseOldAssetsOrCachedPlans": False,
        }
        write_json(self.packet_path, self.packet)
        write_json(self.original_path, self.original)
        self.acceptance = copy.deepcopy(self.sources.acceptance)
        self.acceptance.update({"version": "0.2", "authorizationMode": "delegated-user-authorization", "reviewer": DELEGATED_REVIEWER.copy()})
        self.grant = {
            "kind": "request-scoped-user-authorization", "version": 1,
            "grantId": "grant:one-test", "status": "active", "recordedAt": "2026-08-10T10:00:00+08:00",
            "requestId": self.packet["requestId"], "authorizedBy": {"actorType": "user", "source": "direct-user-message"},
            "capability": "final-result-review-and-document-handoff", "useLimit": 1,
            "systemAssetRoot": "/".join(self.acceptance["reviewedAssetPaths"][0].split("/")[:5]),
            "assetPaths": self.acceptance["reviewedAssetPaths"].copy(),
            "statementFormat": "zh-one-test-automation/1", "explicitGrantQuote": quotes[0],
            "resultReviewQuote": quotes[1], "documentationQuote": quotes[2],
            "sourcePacket": self.binding(self.packet_path), "sourceKey": "source-user-1",
            "messagePointer": "/sources/0/content", "messageSha256": hashlib.sha256(self.message.encode("utf-8")).hexdigest(),
            "authorizationFile": self.binding(self.original_path),
        }
        self.presentation_path = self.root / "presentation.md"
        self.presentation_path.write_text("Synthetic final-result presentation fixture; no actual user review is claimed.\n", encoding="utf-8")
        self.review = {
            "kind": "delegated-result-review", "version": 1, "grantId": self.grant["grantId"],
            "requestId": self.packet["requestId"], "acceptanceId": self.acceptance["acceptanceId"],
            "reviewer": DELEGATED_REVIEWER.copy(), "reviewedAt": self.acceptance["reviewedAt"],
            "status": "passed", "userHasReviewedResult": False, "unresolvedIssues": [],
            **{k: copy.deepcopy(self.acceptance[k]) for k in ("requirementBinding", "bundleBinding", "readbackBinding")},
            "sourceFiles": {n: self.binding(getattr(self.sources, n + "_path")) for n in ("requirement", "bundle", "readback")},
            "presentation": {**self.binding(self.presentation_path), "presentedAt": "2026-08-10T10:11:15+08:00"},
            "conversationAuthorityCheck": {"checkedAt": self.acceptance["reviewedAt"], "source": "current-direct-user-conversation", "delegationRevokedOrNarrowed": False},
            "assetReviews": [], "checkReviews": [],
        }
        self.image_paths = []
        for index, asset in enumerate(self.sources.bundle["assets"]):
            image = self.root / f"render-{index}.png"
            image.write_bytes(make_png())
            self.image_paths.append(image)
            geometry = self.root / f"geometry-{index}.json"
            states = self.root / f"states-{index}.json"
            write_json(geometry, {"fixture": True, "assetId": asset["id"], "status": "passed"})
            write_json(states, {"fixture": True, "assetId": asset["id"], "status": "passed"})
            self.review["assetReviews"].append({
                "assetId": asset["id"], "assetPath": asset["assetPath"], "renderImages": [self.evidence(image)],
                "geometryEvidence": self.evidence(geometry), "stateMatrixEvidence": self.evidence(states),
                "observations": "Synthetic coordinator review of the declared image, geometry and state evidence.",
            })
        for check in self.sources.bundle["verification"]["checks"]:
            path = self.root / check["artifactPath"] if check.get("artifactPath") else self.image_paths[0]
            self.review["checkReviews"].append({"checkId": check["id"], "result": "passed", "observations": "Synthetic review of the original check.", "evidence": [self.evidence(path)]})
        self.refresh()

    def tearDown(self):
        self.sources.close()

    def binding(self, path):
        return {"path": path.relative_to(self.root).as_posix(), "sha256": sha256_file(path)}

    def evidence(self, path):
        return {**self.binding(path), "capturedAt": self.sources.readback["capturedAt"]}

    def refresh(self, *, consume=True):
        write_json(self.grant_path, self.grant)
        write_json(self.review_path, self.review)
        self.acceptance["authorizationBinding"] = self.binding(self.grant_path)
        self.acceptance["resultReviewBinding"] = self.binding(self.review_path)
        self.consumption_path = self.root / delegated_consumption_path(self.grant["grantId"])
        self.consumption_path.parent.mkdir(parents=True, exist_ok=True)
        if consume:
            self.consumption = {
                "kind": "request-authorization-consumption", "version": 1, "grantId": self.grant["grantId"],
                "grantSha256": self.acceptance["authorizationBinding"]["sha256"], "requestId": self.grant["requestId"],
                "acceptanceId": self.acceptance["acceptanceId"], "resultFingerprint": delegated_result_fingerprint(self.acceptance),
                "consumedAt": "2026-08-10T10:11:31+08:00", "useNumber": 1,
            }
            write_json(self.consumption_path, self.consumption)
        self.acceptance["consumptionBinding"] = self.binding(self.consumption_path)
        write_json(self.sources.acceptance_path, self.acceptance)

    def report(self):
        return self.sources.validate_acceptance(self.acceptance)

    def assert_code(self, code):
        self.assertIn(code, error_codes(self.report()))

    def test_valid_delegated_result_through_both_gates_and_handoff(self):
        self.assertTrue(self.report()["valid"], self.report()["errors"])
        handoff = self.sources.build_handoff(acceptance=self.acceptance)
        report = validate_acceptance_handoff_binding(self.acceptance, self.sources.acceptance_path, handoff)
        self.assertTrue(report["valid"], report["errors"])
        # Rechecking the same frozen consumption is permitted and never writes it.
        before = self.consumption_path.read_bytes()
        self.assertTrue(self.report()["valid"])
        self.assertEqual(before, self.consumption_path.read_bytes())

    def test_existing_document_content_04_chain_accepts_valid_delegation(self):
        handoff = self.sources.build_handoff(acceptance=self.acceptance)
        handoff_path = self.root / "ui-program-handoff.json"
        write_json(handoff_path, handoff)
        contract = build_document_content_contract(
            handoff, handoff_path, self.acceptance, self.sources.acceptance_path,
            self.sources.requirement, self.sources.requirement_path,
            self.sources.bundle, self.sources.bundle_path,
            self.sources.readback, self.sources.readback_path,
        )
        self.assertEqual("0.4", contract["version"])

    def test_sidecar_numeric_types_and_single_capability_are_closed(self):
        original = copy.deepcopy(self.grant)
        for key, value in (("version", True), ("version", 2), ("useLimit", "1"), ("useLimit", True),
                           ("useLimit", 2), ("capability", "all-future-projects"), ("statementFormat", "guess-intent")):
            with self.subTest(key=key, value=value):
                self.grant = copy.deepcopy(original)
                self.grant[key] = value
                self.refresh()
                self.assertFalse(self.report()["valid"])

    def test_nested_unknown_fields_and_missing_evidence_categories_rejected(self):
        original = copy.deepcopy(self.review)
        for key in ("geometryEvidence", "stateMatrixEvidence", "renderImages"):
            with self.subTest(key=key):
                self.review = copy.deepcopy(original)
                del self.review["assetReviews"][0][key]
                self.refresh()
                self.assertFalse(self.report()["valid"])
        self.review = copy.deepcopy(original)
        self.review["assetReviews"][0]["renderImages"][0]["pretendSeen"] = True
        self.refresh()
        self.assertFalse(self.report()["valid"])

    def test_custom_schema_cannot_enable_delegation_bypass(self):
        self.acceptance["authorizationMode"] = "skip"
        report = validate_build_acceptance(
            self.acceptance, {}, acceptance_path=self.sources.acceptance_path,
            requirement=self.sources.requirement, requirement_path=self.sources.requirement_path,
            bundle=self.sources.bundle, bundle_path=self.sources.bundle_path,
            readback=self.sources.readback, readback_path=self.sources.readback_path,
        )
        self.assertFalse(report["valid"])

    def test_legacy_direct_user_unchanged_and_agent_rejected(self):
        old = self.sources.acceptance
        self.assertTrue(self.sources.validate_acceptance(old)["valid"])
        wrong = copy.deepcopy(old)
        wrong["reviewer"] = DELEGATED_REVIEWER.copy()
        self.assertIn("acceptance.not_direct_user", error_codes(self.sources.validate_acceptance(wrong)))
        wrong = copy.deepcopy(old)
        wrong["authorizationBinding"] = self.acceptance["authorizationBinding"]
        self.assertTrue(validate_schema_instance(wrong, load_json(BUILD_ACCEPTANCE_SCHEMA)))

    def test_closed_acceptance_and_sidecar_shapes(self):
        for name in ("acceptance", "grant", "review", "consumption"):
            document = getattr(self, name)
            with self.subTest(keys=list(document)):
                document["skipFinalChecks"] = True
                if name == "consumption":
                    write_json(self.consumption_path, document)
                    self.acceptance["consumptionBinding"] = self.binding(self.consumption_path)
                elif name != "acceptance":
                    self.refresh()
                self.assertFalse(self.report()["valid"])
                del document["skipFinalChecks"]
                self.refresh()

    def test_ordinary_full_workflow_is_not_grant(self):
        message = "Use the full workflow through result review and documentation."
        self.packet["sources"][0]["content"] = message
        self.packet["userRequest"]["originalText"] = [message]
        self.original["sourceMessage"] = message
        write_json(self.packet_path, self.packet)
        write_json(self.original_path, self.original)
        self.grant.update({"sourcePacket": self.binding(self.packet_path), "authorizationFile": self.binding(self.original_path), "messageSha256": hashlib.sha256(message.encode()).hexdigest()})
        self.refresh()
        self.assert_code("delegation.explicit_grant")

    def test_explicit_english_statement_format_is_not_guessed(self):
        quotes = GRANT_STATEMENTS["en-one-request-result-review/1"]
        message = "Synthetic direct-user fixture. " + quotes[0]
        self.packet["sources"][0]["content"] = message
        self.packet["userRequest"]["originalText"] = [message]
        self.original["sourceMessage"] = message
        write_json(self.packet_path, self.packet)
        write_json(self.original_path, self.original)
        self.grant.update({
            "statementFormat": "en-one-request-result-review/1", "explicitGrantQuote": quotes[0],
            "resultReviewQuote": quotes[1], "documentationQuote": quotes[2],
            "sourcePacket": self.binding(self.packet_path), "authorizationFile": self.binding(self.original_path),
            "messageSha256": hashlib.sha256(message.encode()).hexdigest(),
        })
        self.refresh()
        self.assertTrue(self.report()["valid"], self.report()["errors"])

    def test_wrong_or_missing_message_provenance(self):
        original = copy.deepcopy(self.grant)
        for key, value in (("sourceKey", "old-design-answer"), ("messagePointer", "/sources/9/content"), ("messageSha256", "0" * 64)):
            with self.subTest(key=key):
                self.grant = copy.deepcopy(original)
                self.grant[key] = value
                self.refresh()
                self.assert_code("delegation.message")

    def test_explicit_delegated_review_chinese_format_and_boundaries(self):
        quotes = GRANT_STATEMENTS["zh-one-test-delegated-review/1"]
        for message, valid in (
            ("SYNTHETIC: " + " ".join(quotes), True),
            ("SYNTHETIC: 执行 制作结果确认 程序说明文档", False),
            ("SYNTHETIC: " + quotes[0] + " 程序说明文档", False),
            ("SYNTHETIC: " + quotes[0] + " 制作结果确认", False),
        ):
            with self.subTest(message=message):
                self.packet["sources"][0]["content"] = message
                self.packet["userRequest"]["originalText"] = [message]
                self.original["sourceMessage"] = message
                write_json(self.packet_path, self.packet)
                write_json(self.original_path, self.original)
                self.grant.update({
                    "statementFormat": "zh-one-test-delegated-review/1",
                    "explicitGrantQuote": quotes[0], "resultReviewQuote": quotes[1],
                    "documentationQuote": quotes[2], "sourcePacket": self.binding(self.packet_path),
                    "authorizationFile": self.binding(self.original_path),
                    "messageSha256": hashlib.sha256(message.encode()).hexdigest(),
                })
                self.refresh()
                self.assertEqual(valid, self.report()["valid"], self.report()["errors"])

    def test_packet_cannot_claim_another_request(self):
        self.packet["requestId"] = "other-request"
        write_json(self.packet_path, self.packet)
        self.grant["sourcePacket"] = self.binding(self.packet_path)
        self.refresh()
        self.assert_code("delegation.message")

    def test_authorization_file_must_retain_same_message_and_boundaries(self):
        self.original["mayFabricatePostResultUserMessage"] = True
        write_json(self.original_path, self.original)
        self.grant["authorizationFile"] = self.binding(self.original_path)
        self.refresh()
        self.assert_code("delegation.original_authorization")

    def test_source_file_sha_mutation_rejected(self):
        self.packet_path.write_text(self.packet_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assert_code("delegation.file")

    def test_grant_revoked_or_cross_request_rejected(self):
        self.grant["status"] = "revoked"
        self.refresh()
        self.assert_code("delegation.grant_scope")
        self.grant["status"] = "active"
        self.grant["requestId"] = "other-request"
        self.refresh()
        self.assert_code("delegation.grant_scope")

    def test_exact_asset_scope_and_system_root(self):
        original = copy.deepcopy(self.grant)
        for key, value in (("assetPaths", self.grant["assetPaths"][:-1]), ("systemAssetRoot", "/Game/UI/UMG/Other")):
            with self.subTest(key=key):
                self.grant = copy.deepcopy(original)
                self.grant[key] = value
                self.refresh()
                self.assert_code("delegation.asset_scope")

    def test_relative_paths_cannot_escape_request(self):
        for path in ("../grant.json", "C:/grant.json", "C:grant.json", "//server/share/grant.json", "..\\grant.json"):
            with self.subTest(path=path):
                self.acceptance["authorizationBinding"]["path"] = path
                self.assert_code("delegation.file")
                self.refresh()

    def test_missing_review_or_consumption_rejected(self):
        for key in ("authorizationBinding", "resultReviewBinding", "consumptionBinding"):
            with self.subTest(key=key):
                saved = self.acceptance.pop(key)
                self.assertFalse(self.report()["valid"])
                self.acceptance[key] = saved

    def test_review_is_actual_coordinator_not_fake_user(self):
        self.review["reviewer"]["actorType"] = "user"
        self.refresh()
        self.assertFalse(self.report()["valid"])
        self.review["reviewer"] = DELEGATED_REVIEWER.copy()
        self.review["userHasReviewedResult"] = True
        self.refresh()
        self.assertFalse(self.report()["valid"])

    def test_review_before_readback_and_future_review_rejected(self):
        for time in ("2026-08-10T10:09:00+08:00", "2999-08-10T10:11:30+08:00"):
            with self.subTest(time=time):
                self.acceptance["reviewedAt"] = time
                self.review["reviewedAt"] = time
                self.review["conversationAuthorityCheck"]["checkedAt"] = time
                self.refresh()
                self.assert_code("delegation.review_time")

    def test_unknown_timezone_and_early_presentation_rejected(self):
        self.review["presentation"]["presentedAt"] = "2026-08-10T10:10:00+08:00"
        self.refresh()
        self.assert_code("delegation.presentation_time")
        self.review["presentation"]["presentedAt"] = "2026-08-10T10:11:15"
        self.refresh()
        self.assert_code("time.timezone")

    def test_missing_asset_and_check_reviews_rejected(self):
        row = self.review["assetReviews"].pop()
        self.refresh()
        self.assert_code("delegation.review_coverage")
        self.review["assetReviews"].append(row)
        self.review["checkReviews"].pop()
        self.refresh()
        self.assert_code("delegation.check_coverage")

    def test_original_check_artifact_cannot_be_substituted(self):
        ids = {c["id"] for c in self.sources.bundle["verification"]["checks"] if c.get("artifactPath")}
        row = next(x for x in self.review["checkReviews"] if x["checkId"] in ids)
        row["evidence"] = [self.evidence(self.image_paths[0])]
        self.refresh()
        self.assert_code("delegation.check_artifact")

    def test_missing_image_or_state_matrix_rejected(self):
        path = self.root / self.review["assetReviews"][0]["stateMatrixEvidence"]["path"]
        path.unlink()
        self.assert_code("delegation.file")

    def test_json_renamed_to_png_is_not_render_evidence(self):
        image = self.image_paths[0]
        image.write_text('{"passed":true}', encoding="utf-8")
        self.review["assetReviews"][0]["renderImages"] = [self.evidence(image)]
        self.refresh()
        self.assert_code("delegation.render_image")

    def test_pending_visual_review_and_unresolved_issues_rejected(self):
        self.review["status"] = "pending"
        self.refresh()
        self.assertFalse(self.report()["valid"])
        self.review["status"] = "passed"
        self.review["unresolvedIssues"] = ["unreviewed hidden state"]
        self.refresh()
        self.assertFalse(self.report()["valid"])

    def test_evidence_after_review_is_rejected(self):
        self.review["assetReviews"][0]["renderImages"][0]["capturedAt"] = "2026-08-10T10:12:00+08:00"
        self.refresh()
        self.assert_code("delegation.evidence_after_review")

    def test_consumption_cannot_transfer_to_second_acceptance(self):
        self.acceptance["acceptanceId"] = "acceptance:second-result"
        self.review["acceptanceId"] = self.acceptance["acceptanceId"]
        self.refresh(consume=False)
        self.assert_code("delegation.consumption")

    def test_changed_review_cannot_reuse_consumption(self):
        self.review["assetReviews"][0]["observations"] += " Changed after consumption."
        self.refresh(consume=False)
        self.assert_code("delegation.consumption")

    def test_consumption_has_one_deterministic_path(self):
        copy_path = self.root / "another-consumption.json"
        write_json(copy_path, self.consumption)
        self.acceptance["consumptionBinding"] = self.binding(copy_path)
        self.assert_code("delegation.consumption")

    def test_consumption_before_review_is_rejected(self):
        self.consumption["consumedAt"] = "2026-08-10T10:00:00+08:00"
        write_json(self.consumption_path, self.consumption)
        self.acceptance["consumptionBinding"] = self.binding(self.consumption_path)
        self.assert_code("delegation.consumption_time")

    def test_later_revocation_or_narrowing_attestation_rejected(self):
        self.review["conversationAuthorityCheck"]["delegationRevokedOrNarrowed"] = True
        self.refresh()
        self.assertFalse(self.report()["valid"])

    def test_handoff_only_entry_rechecks_current_layout_source_gate(self):
        handoff = self.sources.build_handoff(acceptance=self.acceptance)
        layout = self.root / self.sources.bundle["assets"][0]["layoutSpecPath"]
        layout.write_text(layout.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        report = validate_acceptance_handoff_binding(self.acceptance, self.sources.acceptance_path, handoff)
        self.assertIn("sources.invalid", error_codes(report))

    def test_stale_final_file_rejected_by_both_gates(self):
        handoff = self.sources.build_handoff(acceptance=self.acceptance)
        self.sources.readback_path.write_text(self.sources.readback_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertFalse(self.report()["valid"])
        report = validate_acceptance_handoff_binding(self.acceptance, self.sources.acceptance_path, handoff)
        self.assertFalse(report["valid"])

    def test_original_bundle_final_gate_stays_strict(self):
        self.sources.bundle["verification"]["checks"][0]["status"] = "pending"
        self.assert_code("sources.invalid")

    def test_formal_art_gate_cannot_be_avoided(self):
        self.sources.bundle["version"] = "0.4"
        self.sources.bundle.pop("artStage", None)
        self.assert_code("sources.invalid")


if __name__ == "__main__":
    unittest.main()
