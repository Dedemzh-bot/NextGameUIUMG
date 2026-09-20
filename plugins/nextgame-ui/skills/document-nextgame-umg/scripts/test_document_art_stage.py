#!/usr/bin/env python3
"""Final-art gates must receive current actual identity before authorizing docs."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from _document_contract_common import READBACK_SCHEMA, canonical_sha256, load_json, sha256_file, validate_schema_instance, write_json
from test_document_contracts import FinalizedSources, error_codes
import validate_unreal_widget_readback as readback_validator


class ArtDocumentGateTests(unittest.TestCase):
    def setUp(self):
        self.sources = FinalizedSources()
        self.addCleanup(self.sources.close)
        self.sources.bundle.update({"version": "0.4", "reuseRelations": [], "artStage": {
            "goal": "upgrade-art",
            **{key: {"path": f"art/{key}.json", "sha256": "a" * 64}
               for key in ("request", "plan", "verification")},
        }})
        for asset in self.sources.bundle["assets"]:
            asset["representationKind"] = "layout-spec"
        write_json(self.sources.bundle_path, self.sources.bundle)
        self.sources.readback.update({"version": "0.4", "reuseRelations": []})
        self.sources.readback["bundleBinding"]["sha256"] = sha256_file(self.sources.bundle_path)
        for asset in self.sources.readback["assets"]:
            asset.update({"representationKind": "layout-spec", "generatedClassPath": asset["assetObjectPath"] + "_C"})
        write_json(self.sources.readback_path, self.sources.readback)
        self.sources.acceptance = self.sources._make_acceptance()
        write_json(self.sources.acceptance_path, self.sources.acceptance)
        # Separate Bundle completion from the normalized actual-readback callback.
        self.completion_guard = patch("validate_build_bundle.validate_bundle_art_stage", return_value=[])
        self.completion_guard.start()
        self.addCleanup(self.completion_guard.stop)

    def test_current_normalized_readback_is_passed_to_art_validator(self):
        with patch.object(readback_validator, "validate_bundle_art_stage", return_value=[]) as art:
            report = self.sources.validate_acceptance()
        self.assertTrue(report["valid"], report["errors"])
        art.assert_called_once_with(self.sources.bundle,
            bundle_path=self.sources.bundle_path, requirement=self.sources.requirement,
            requirement_path=self.sources.requirement_path, readback=self.sources.readback)

    def test_stale_art_identity_invalidates_acceptance_without_bundle_hash_change(self):
        rejection = {"code": "art.readback_identity", "path": "$.artStage", "message": "Current actual identity differs from verified art snapshot."}
        before = sha256_file(self.sources.bundle_path)
        with patch.object(readback_validator, "validate_bundle_art_stage", return_value=[rejection]):
            report = self.sources.validate_acceptance()
        self.assertFalse(report["valid"])
        self.assertIn("art.readback_identity", error_codes(report))
        self.assertEqual(before, sha256_file(self.sources.bundle_path))

    def test_actual_widget_and_readback_version_guards_remain_active(self):
        with patch.object(readback_validator, "validate_bundle_art_stage", return_value=[]):
            wrong_version = copy.deepcopy(self.sources.readback)
            wrong_version["version"] = "0.3"
            self.assertIn("version.bundle_readback", error_codes(self.sources.validate_readback(wrong_version)))
            wrong_parent = copy.deepcopy(self.sources.readback)
            wrong_parent["assets"][0]["widgets"][0]["parentWidgetName"] = "UnknownParent"
            self.assertFalse(self.sources.validate_readback(wrong_parent)["valid"])

    def test_empty_reuse_readback_is_opt_in_and_old_shape_stays_closed(self):
        schema = load_json(READBACK_SCHEMA)
        self.assertEqual([], validate_schema_instance(self.sources.readback, schema))
        for version in ("0.2", "0.3"):
            older = copy.deepcopy(self.sources.readback)
            older["version"] = version
            self.assertTrue(validate_schema_instance(older, schema))
        extra = copy.deepcopy(self.sources.readback)
        extra["artProperties"] = {}
        self.assertTrue(validate_schema_instance(extra, schema))

    def test_complete_pre_art_readback_schema_semantics_are_unchanged(self):
        legacy = load_json(READBACK_SCHEMA)
        legacy["title"] = "NextGame Unreal Widget Readback 0.1, 0.2, and 0.3"
        legacy["oneOf"].remove({"$ref": "#/$defs/readbackV04"})
        legacy["$defs"].pop("readbackV04")
        self.assertEqual("f41370993da7c6f3380f2dc0da39fb89e3d30a03ca3b617e59a08fdee75d8484", canonical_sha256(legacy))


if __name__ == "__main__":
    unittest.main()
