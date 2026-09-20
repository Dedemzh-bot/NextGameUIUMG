#!/usr/bin/env python3
"""Closed, versioned dated system-folder opt-in and unchanged naming contracts."""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from route_rule_cards import build_rule_card_pack, validate_rule_card_pack
from test_widget_blueprint_asset_rules import (
    CATALOG_PATH,
    SCHEMA_PATH,
    base_spec,
    child_spec,
    error_codes,
    production_spec,
    project_common_entry_spec,
)
from validate_layout_spec import load_json, validate_spec


def dated_spec(kind: str = "screen", *, production: bool = True) -> dict:
    spec = base_spec() if kind == "screen" else child_spec()
    if kind == "entry":
        spec = project_common_entry_spec()
        spec["profile"]["assetScope"] = "system"
    profile = spec["profile"]
    profile["system"] = "onlinesea"
    profile["systemFolder"] = "OnlineSea_20260917_01"
    profile["systemFolderInstance"] = {"version": 1, "date": "20260917", "number": 1}
    profile["targetAsset"] = {
        "folder": "/Game/UI/UMG/OnlineSea_20260917_01" + ("" if kind == "screen" else "/Widgets"),
        "name": "umg_onlinesea" if kind == "screen" else "uw_onlinesea_" + ("material_list" if kind == "entry" else "item_list"),
    }
    return production_spec(spec) if production else spec


class SystemFolderInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_json(CATALOG_PATH)
        cls.schema = load_json(SCHEMA_PATH)
        Draft202012Validator.check_schema(cls.schema)
        cls.schema_validator = Draft202012Validator(cls.schema)

    def assert_valid(self, spec: dict) -> None:
        self.assertEqual([], list(self.schema_validator.iter_errors(spec)))
        result = validate_spec(spec, self.catalog)
        self.assertTrue(result["valid"], result["errors"])

    def assert_rejected(self, spec: dict, code: str, *, schema_rejects: bool = True) -> None:
        schema_errors = list(self.schema_validator.iter_errors(spec))
        if schema_rejects:
            self.assertTrue(schema_errors, "Structural/calendar constraint must also fail JSON Schema")
        else:
            # Standard JSON Schema cannot compare fields. Semantic validation
            # owns the relation among logical system, declared suffix and path.
            self.assertEqual([], schema_errors)
        self.assertIn(code, error_codes(validate_spec(spec, self.catalog)))

    def test_ordinary_directories_remain_valid(self) -> None:
        for source in (base_spec(), child_spec(), project_common_entry_spec()):
            for spec in (source, production_spec(source)):
                with self.subTest(profile=spec["profile"], mode=spec["mode"]):
                    self.assert_valid(spec)

    def test_explicit_screen_child_and_entry_destinations(self) -> None:
        for kind in ("screen", "child-widget", "entry"):
            self.assert_valid(dated_spec(kind))
        for kind in ("screen", "child-widget"):
            self.assert_valid(dated_spec(kind, production=False))

    def test_number_boundaries_and_case_only_system_identity(self) -> None:
        for prefix in ("onlinesea", "OnlineSea", "ONLINESEA"):
            for number in (1, 9, 10, 99):
                spec = dated_spec()
                folder = f"{prefix}_20260917_{number:02d}"
                spec["profile"]["systemFolderInstance"]["number"] = number
                spec["profile"]["systemFolder"] = folder
                spec["profile"]["targetAsset"]["folder"] = f"/Game/UI/UMG/{folder}"
                self.assert_valid(production_spec(spec))

    def test_dated_folder_without_opt_in_is_rejected(self) -> None:
        for kind in ("screen", "child-widget", "entry"):
            spec = dated_spec(kind)
            del spec["profile"]["systemFolderInstance"]
            self.assert_rejected(spec, "profile.system_folder.system_mismatch", schema_rejects=False)

    def test_instance_shape_is_closed_and_required(self) -> None:
        for instance in (None, False, "20260917", [], {}, {"version": 1},
                         {"version": 1, "date": "20260917"}, {"date": "20260917", "number": 1},
                         {"version": 1, "number": 1},
                         {"version": 1, "date": "20260917", "number": 1, "canonicalId": "x"},
                         {"version": 1, "date": "20260917", "number": 1, "folder": "Other"}):
            with self.subTest(instance=instance):
                spec = dated_spec()
                spec["profile"]["systemFolderInstance"] = instance
                code = "fields" if isinstance(instance, dict) else "type"
                self.assert_rejected(spec, f"profile.system_folder_instance.{code}")

    def test_version_number_and_date_rejections(self) -> None:
        invalid_values = {
            "version": (0, 2, True, "1", None),
            "number": (0, 100, -1, True, False, "1", "01", None, 1.5),
            "date": ("2026091", "202609170", "2026-09-17", "20260917\n", "20260229",
                     "19000229", "21000229", "20260431", "20261301", "20260001",
                     "20260900", "00000101", "00000229", "２０２６０９１７", 20260917, None),
        }
        for field, values in invalid_values.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    spec = dated_spec()
                    spec["profile"]["systemFolderInstance"][field] = value
                    self.assert_rejected(spec, f"profile.system_folder_instance.{field}")

    def test_schema_calendar_matches_gregorian_boundaries(self) -> None:
        date_schema = self.schema["properties"]["profile"]["properties"]["systemFolderInstance"]["properties"]["date"]
        validator = Draft202012Validator(date_schema)
        for year in (0, 1, 4, 100, 400, 1600, 1700, 1900, 2000, 2024, 2026, 9999):
            for month in range(14):
                for day in range(33):
                    value = f"{year:04d}{month:02d}{day:02d}"
                    try:
                        date(year, month, day)
                        expected = True
                    except ValueError:
                        expected = False
                    self.assertEqual(expected, validator.is_valid(value), value)
        for value in ("00010101", "00040229", "04000229", "20000229", "20240229", "99991231"):
            spec = dated_spec()
            spec["profile"]["systemFolderInstance"]["date"] = value
            spec["profile"]["systemFolder"] = f"OnlineSea_{value}_01"
            spec["profile"]["targetAsset"]["folder"] = f"/Game/UI/UMG/OnlineSea_{value}_01"
            self.assert_valid(production_spec(spec))

    def test_logical_system_date_and_number_must_match(self) -> None:
        for folder, structural in (("Other_20260917_01", False), ("OnlineSea_20260918_01", False),
                                   ("OnlineSea_20260917_02", False), ("OnlineSea_20260917_1", True),
                                   ("OnlineSea_20260917_001", True), ("OnlineSea", True),
                                   ("OnlineSea_extra_20260917_01", True)):
            with self.subTest(folder=folder):
                spec = dated_spec()
                spec["profile"]["systemFolder"] = folder
                spec["profile"]["targetAsset"]["folder"] = f"/Game/UI/UMG/{folder}"
                self.assert_rejected(production_spec(spec), "profile.system_folder.system_mismatch", schema_rejects=structural)

    def test_exact_destination_and_unchanged_basename(self) -> None:
        for kind in ("screen", "child-widget", "entry"):
            for folder in ("/Game/UI/UMG/OnlineSea", "/Game/UI/UMG/onlinesea_20260917_01",
                           "/Game/UI/UMG/OnlineSea_20260917_01/Other"):
                spec = dated_spec(kind)
                spec["profile"]["targetAsset"]["folder"] = folder
                self.assert_rejected(production_spec(spec), "target.folder", schema_rejects=False)
            spec = dated_spec(kind)
            spec["profile"]["targetAsset"]["name"] += "_20260917_01"
            self.assert_rejected(production_spec(spec), "target.name", schema_rejects=False)
        spec = dated_spec()
        spec["asset"]["folder"] += "/Widgets"
        self.assert_rejected(spec, "asset.production_target", schema_rejects=False)

    def test_project_common_and_prototype_kind_cannot_opt_in(self) -> None:
        common = project_common_entry_spec()
        common["profile"]["systemFolderInstance"] = {"version": 1, "date": "20260917", "number": 1}
        for folder in ("Common", "Common_20260917_01"):
            common["profile"]["systemFolder"] = folder
            self.assert_rejected(common, "profile.system_folder_instance.scope")
        spec = dated_spec(production=False)
        spec["profile"]["assetKind"] = "prototype"
        self.assert_rejected(spec, "profile.system_folder_instance.scope")

    def test_routed_card_keeps_opt_in_and_machine_validation(self) -> None:
        temp_root = os.environ.get("NEXTGAME_UI_TEST_TMPDIR")
        if temp_root:
            Path(temp_root).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="system-folder-instance-", dir=temp_root) as temp:
            path = Path(temp) / "layout.json"
            path.write_text(json.dumps(dated_spec()), encoding="utf-8")
            pack = build_rule_card_pack(path, stages=["build-planning"])
            self.assertEqual("routed", pack["routingMode"])
            self.assertTrue(pack["machineValidation"]["layoutValid"])
            self.assertFalse(pack["machineValidation"]["routingMayDisableValidators"])
            self.assertIn("folder.system-widget-blueprints", pack["selectedRuleIds"])
            self.assertIn("systemFolderInstance", json.dumps(pack["detailSections"]))
            self.assertIn("Explicit dated system-folder instance", json.dumps(pack["detailSections"]))
            pack_path = Path(temp) / "rule-card-pack.json"
            pack_path.write_text(json.dumps(pack), encoding="utf-8")
            report = validate_rule_card_pack(pack_path, path, stages=["build-planning"])
            self.assertTrue(report["valid"], report)
            invalid = dated_spec()
            del invalid["profile"]["systemFolderInstance"]
            path.write_text(json.dumps(invalid), encoding="utf-8")
            pack = build_rule_card_pack(path)
            self.assertEqual("fallback-full", pack["routingMode"])
            self.assertFalse(pack["machineValidation"]["layoutValid"])


if __name__ == "__main__":
    unittest.main()
