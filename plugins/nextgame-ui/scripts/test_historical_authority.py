#!/usr/bin/env python3
"""Fail-closed tests for the explicit historical-authority revalidation route."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

import revalidate_historical_authority as authority


class HistoricalAuthorityTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get("NEXTGAME_UI_TEST_TMPDIR", tempfile.gettempdir())).resolve()
        self.root = base / ("nextgame-historical-authority-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True, mode=0o755)
        self.addCleanup(shutil.rmtree, self.root)
        self.frozen = self.root / "frozen" / "nextgame-ui"
        self.current = self.root / "current" / "nextgame-ui"
        for root, version in ((self.frozen, "0.1.0+old"), (self.current, "0.1.0+current")):
            self.write(root / authority.MANIFEST, {"name": "nextgame-ui", "version": version})
            self.write(root / authority.ROLE_CARDS, {"roles": []})
            script = root / authority.VALIDATOR
            script.parent.mkdir(parents=True)
            # A tiny fixture intentionally tests orchestration, not the real
            # semantic validator. Real archived R7 is exercised separately.
            script.write_text(
                'import json,sys\nfrom pathlib import Path\n'
                's=json.loads(Path(sys.argv[1]).read_text())\n'
                'strict="--check-findings-files" in sys.argv\n'
                'bad=s.get("failHistorical") if strict else s.get("failCurrent")\n'
                'r={"valid":not bool(bad),"errors":[{"code":"fixture.failure"}] if bad else [],"warnings":[]}\n'
                'print(json.dumps(r))\nsys.exit(1 if bad else 0)\n', encoding="utf-8"
            )
        self.lock = authority.make_lock(self.frozen)
        self.lock_path = self.root / "frozen.lock.json"
        self.write(self.lock_path, self.lock)
        request = self.root / "request"
        self.packet = request / "request-packet.json"
        self.spec = request / "ui-requirement.json"
        self.draft = request / "ui-requirement.draft.json"
        self.write(self.packet, {"sources": []})
        self.write(self.draft, {"pending": True})
        self.write(request / "contexts/base.json", {})
        inputs = []
        for role in sorted(authority.ROLES):
            self.write(request / "findings" / f"{role}.json", {})
            self.write(request / "agent-inputs" / f"{role}.json", {
                "agentRole": role, "authority": self.lock["authority"], "additionalInputs": []
            })
            inputs.append({"agentRole": role, "findingsRef": f"findings/{role}.json",
                           "rolePacketRef": f"agent-inputs/{role}.json"})
        self.requirement = {"normalization": {"baseContextRef": "contexts/base.json", "findingsInputs": inputs}}
        self.write(self.spec, self.requirement)

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def run_gate(self, allowed=None):
        return authority.revalidate(self.spec, self.packet, self.draft, self.lock_path,
                                    allowed or self.frozen, current_root=self.current)

    def test_both_stages_required_and_exact_complete_model(self):
        result = self.run_gate()
        self.assertTrue(result["valid"], result)
        self.assertIn("--check-findings-files", result["historical"]["command"])
        self.assertNotIn("--check-findings-files", result["current"]["command"])
        for stage in ("historical", "current"):
            self.assertIn(str(self.spec), result[stage]["command"])
        self.assertEqual(22, len(result["bindings"]["inputs"]))

    def test_changed_validator_is_rejected_before_execution(self):
        (self.frozen / authority.VALIDATOR).write_text("raise RuntimeError('must not run')", encoding="utf-8")
        result = self.run_gate()
        self.assertFalse(result["valid"])
        self.assertNotIn("historical", result)

    def test_extra_authority_file_is_rejected(self):
        self.write(self.frozen / "new-import.json", {})
        self.assertFalse(self.run_gate()["valid"])

    def test_missing_authority_file_is_rejected(self):
        (self.frozen / authority.ROLE_CARDS).unlink()
        self.assertFalse(self.run_gate()["valid"])

    def test_bytecode_cannot_bypass_file_lock(self):
        cache = self.frozen / authority.ANALYSIS / "scripts/__pycache__/injected.pyc"
        cache.parent.mkdir()
        cache.write_bytes(b"untrusted cached bytecode")
        result = self.run_gate()
        self.assertFalse(result["valid"])
        self.assertNotIn("historical", result)

    def test_lock_cannot_select_another_root(self):
        result = self.run_gate(self.current)
        self.assertFalse(result["valid"])
        self.assertNotIn("historical", result)

    def test_no_broad_or_relative_allowance(self):
        for root in [Path("nextgame-ui"), self.frozen.parent]:
            with self.subTest(root=root), self.assertRaises(authority.AuthorityError):
                authority.make_lock(root)

    def test_lock_content_tamper_rejected(self):
        forged = copy.deepcopy(self.lock)
        forged["authority"]["pluginVersion"] = "0.1.0+new"
        self.write(self.lock_path, forged)
        self.assertFalse(self.run_gate()["valid"])

    def test_mixed_packet_authority_rejected(self):
        path = self.packet.parent / "agent-inputs/visual-structure.json"
        value = authority.load(path)
        value["authority"]["pluginVersion"] = "0.1.0+new"
        self.write(path, value)
        result = self.run_gate()
        self.assertFalse(result["valid"])
        self.assertNotIn("historical", result)

    def test_incomplete_roles_rejected(self):
        self.requirement["normalization"]["findingsInputs"].pop()
        self.write(self.spec, self.requirement)
        self.assertFalse(self.run_gate()["valid"])

    def test_historical_errors_not_filtered(self):
        self.requirement["failHistorical"] = True
        self.write(self.spec, self.requirement)
        result = self.run_gate()
        self.assertFalse(result["valid"])
        self.assertEqual("fixture.failure", result["historical"]["validation"]["errors"][0]["code"])
        self.assertNotIn("current", result)

    def test_current_errors_not_filtered(self):
        self.requirement["failCurrent"] = True
        self.write(self.spec, self.requirement)
        result = self.run_gate()
        self.assertFalse(result["valid"])
        self.assertTrue(result["historical"]["valid"])
        self.assertEqual("fixture.failure", result["current"]["validation"]["errors"][0]["code"])

    def test_scoped_evidence_cannot_escape(self):
        self.requirement["normalization"]["baseContextRef"] = "../outside.json"
        self.write(self.spec, self.requirement)
        self.assertFalse(self.run_gate()["valid"])

    def test_outputs_cannot_mutate_authority_or_existing_files(self):
        with self.assertRaises(authority.AuthorityError):
            authority.write_new(self.frozen / "report.json", {}, [self.frozen])
        with self.assertRaises(FileExistsError):
            authority.write_new(self.lock_path, {}, [])


if __name__ == "__main__":
    unittest.main()
