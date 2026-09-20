#!/usr/bin/env python3
"""Opt-in art completion routing without weakening existing Bundle authority."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from _contract_common import ASSETS_ROOT, load_json, validate_schema_instance
import validate_build_bundle as validator


class ArtBundleIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.bundle_path = ASSETS_ROOT / "example-composite-tabs-build-bundle.json"
        self.requirement_path = ASSETS_ROOT / "example-composite-tabs-requirement.json"
        self.legacy = load_json(self.bundle_path)
        self.requirement = load_json(self.requirement_path)
        self.schema = load_json(validator.DEFAULT_SCHEMA)
        self.bundle = copy.deepcopy(self.legacy)
        self.bundle.update({"version": "0.4", "reuseRelations": [], "artStage": {
            "goal": "formal-art",
            **{key: {"path": f"art/{key}.json", "sha256": "a" * 64}
               for key in ("request", "plan", "verification")},
        }})
        for asset in self.bundle["assets"]:
            asset["representationKind"] = "layout-spec"

    def validate(self, bundle, *, check_linked_files=True):
        return validator.validate_build_bundle(
            bundle, self.schema, bundle_path=self.bundle_path,
            requirement_spec=self.requirement, requirement_path=self.requirement_path,
            check_linked_files=check_linked_files,
        )

    def finalize(self):
        self.bundle["execution"].update({"status": "completed",
            "startedAt": "2026-09-14T10:00:00+08:00", "completedAt": "2026-09-14T10:01:00+08:00"})
        self.bundle["verification"]["status"] = "passed"
        for asset in self.bundle["assets"]:
            asset["status"] = "verified"
        for check in self.bundle["verification"]["checks"]:
            check["status"] = "passed"

    def test_developer_only_validation_never_loads_art_stage(self):
        with patch.object(validator, "validate_bundle_art_stage") as art:
            report = self.validate(self.legacy)
        self.assertTrue(report["valid"], report["errors"])
        art.assert_not_called()

    def test_pending_art_bundle_allows_empty_reuse_and_unwritten_outputs(self):
        with patch.object(validator, "validate_bundle_art_stage") as art:
            report = self.validate(self.bundle)
        self.assertTrue(report["valid"], report["errors"])
        art.assert_not_called()

    def test_completion_calls_art_guard_even_when_linked_files_skipped(self):
        self.finalize()
        rejection = {"code": "art.pending", "path": "$.artStage.verification", "message": "Art verification is pending."}
        with patch.object(validator, "validate_bundle_art_stage", return_value=[rejection]) as art:
            report = self.validate(self.bundle, check_linked_files=False)
        self.assertIn(rejection, report["errors"])
        art.assert_called_once_with(self.bundle, bundle_path=self.bundle_path,
            requirement=self.requirement, requirement_path=self.requirement_path)

    def test_completed_execution_alone_cannot_bypass_art_guard(self):
        self.finalize()
        self.bundle["verification"]["status"] = "pending"
        with patch.object(validator, "validate_bundle_art_stage", return_value=[]) as art:
            self.validate(self.bundle)
        art.assert_called_once()

    def test_completed_art_preserves_ordinary_layout_validation(self):
        self.finalize()
        with patch.object(validator, "validate_bundle_art_stage", return_value=[]):
            valid = self.validate(self.bundle)
            self.assertTrue(valid["valid"], valid["errors"])
            self.bundle["assets"][0]["layoutSpecSha256"] = "0" * 64
            report = self.validate(self.bundle)
        self.assertFalse(report["valid"])
        self.assertIn("layout.sha256", {item["code"] for item in report["errors"]})

    def test_art_shape_is_closed_and_requires_relative_complete_bindings(self):
        self.assertEqual([], validate_schema_instance(self.bundle, self.schema))
        cases = []
        for key in ("request", "plan", "verification"):
            value = copy.deepcopy(self.bundle)
            value["artStage"].pop(key)
            cases.append(value)
        for invalid_path in ("C:/temp/plan.json", "/tmp/plan.json", "https://example.test/plan.json", "\\\\host\\plan.json"):
            value = copy.deepcopy(self.bundle)
            value["artStage"]["plan"]["path"] = invalid_path
            cases.append(value)
        value = copy.deepcopy(self.bundle)
        value["artStage"]["skipVerification"] = True
        cases.append(value)
        for value in cases:
            with self.subTest(value=value["artStage"]):
                self.assertTrue(validate_schema_instance(value, self.schema))

    def test_legacy_shapes_reject_art_stage_and_keep_nonempty_reuse(self):
        legacy_with_art = copy.deepcopy(self.legacy)
        legacy_with_art["artStage"] = self.bundle["artStage"]
        self.assertTrue(validate_schema_instance(legacy_with_art, self.schema))
        for version in ("0.2", "0.3"):
            value = copy.deepcopy(self.bundle)
            value["version"] = version
            value.pop("artStage")
            self.assertTrue(validate_schema_instance(value, self.schema))

    def test_missing_helper_fails_closed_only_for_art(self):
        with patch.object(validator.importlib.util, "spec_from_file_location", return_value=None):
            errors = validator.validate_bundle_art_stage(self.bundle, bundle_path=self.bundle_path,
                requirement=self.requirement, requirement_path=self.requirement_path)
        self.assertEqual("art.validation_failed", errors[0]["code"])
        self.assertEqual([], validator.validate_bundle_art_stage(self.legacy, bundle_path=self.bundle_path,
            requirement=None, requirement_path=None))


if __name__ == "__main__":
    unittest.main()
