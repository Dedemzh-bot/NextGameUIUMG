#!/usr/bin/env python3
"""The review policy must reach each stage without weakening routing or stale-pack guards."""
import shutil
import tempfile
import unittest
from pathlib import Path
from route_rule_cards import (
    DEFAULT_REFERENCES, DEFAULT_ROUTING, RequiredInputError,
    _build_rule_card_pack_for_test, _validate_rule_card_pack_for_test,
    build_rule_card_pack, write_json,
)
from select_rules import load_json

LAYOUT = Path(__file__).resolve().parents[1] / 'assets/example-layout-spec.json'
POLICY = 'production-fidelity-checks.md'
STAGES = ('build-planning', 'build-execution', 'build-verification')

class ProductionFidelityRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='nextgame-fidelity-')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def references(self):
        path = self.root / 'references'
        shutil.copytree(DEFAULT_REFERENCES, path)
        return path

    def test_each_stage_receives_its_review_duty(self):
        expected = {
            'build-planning': ('workflow.build-planning-ownership', '## Accepted property coverage'),
            'build-execution': ('workflow.editor-sequence', '## Accepted property coverage'),
            'build-verification': ('workflow.actual-readback', '## Independent verification and unchanged replay'),
        }
        for stage, (guard, heading) in expected.items():
            with self.subTest(stage=stage):
                pack = build_rule_card_pack(LAYOUT, stages=[stage])
                self.assertEqual('routed', pack['routingMode'], pack['fallbackReasons'])
                matching = [s for s in pack['detailSections'] if s['file']==POLICY and s['heading']==heading]
                self.assertEqual(1,len(matching))
                self.assertIn(guard,matching[0]['workflowGuardIds'])
                self.assertTrue(pack['machineValidation']['machineValidatorsEnabled'])

    def test_text_capacity_is_routed_by_planning_guard(self):
        pack = build_rule_card_pack(LAYOUT, stages=['build-planning'])
        sections = [s for s in pack['detailSections'] if s['file']==POLICY and s['heading']=='## Text capacity and stable placement']
        self.assertEqual(1,len(sections))
        self.assertIn('workflow.build-planning-ownership', sections[0]['workflowGuardIds'])

    def test_missing_routing_still_delivers_complete_policy_at_all_stages(self):
        for stage in STAGES:
            pack = _build_rule_card_pack_for_test(LAYOUT, stages=[stage], routing_path=self.root/'missing.json')
            self.assertEqual('fallback-full',pack['routingMode'])
            self.assertIn(POLICY, [s['file'] for s in pack['fullDocuments']])

    def test_dropped_coverage_duty_cannot_silently_route(self):
        routing = load_json(DEFAULT_ROUTING)
        guard = next(g for g in routing['workflowGuards'] if g['id']=='workflow.build-planning-ownership')
        guard['detailRefs']=[r for r in guard['detailRefs'] if r['file']!=POLICY]
        path=self.root/'routing.json'
        write_json(path,routing)
        pack=_build_rule_card_pack_for_test(LAYOUT,stages=['build-planning'],routing_path=path)
        self.assertEqual('fallback-full',pack['routingMode'])
        self.assertIn(POLICY,[s['file'] for s in pack['fullDocuments']])

    def test_policy_change_invalidates_already_bound_pack(self):
        refs=self.references()
        pack=_build_rule_card_pack_for_test(LAYOUT,references_dir=refs,stages=['build-verification'])
        path=self.root/'pack.json'
        write_json(path,pack)
        policy=refs/POLICY
        policy.write_bytes(policy.read_bytes()+b'\nChanged policy binding.\n')
        report=_validate_rule_card_pack_for_test(path,LAYOUT,references_dir=refs,stages=['build-verification'])
        self.assertFalse(report['valid'])
        self.assertIn('pack.stale-or-tampered',{e['code'] for e in report['errors']})

    def test_missing_policy_fails_instead_of_omitting_duties(self):
        refs=self.references()
        (refs/POLICY).unlink()
        with self.assertRaises(RequiredInputError):
            _build_rule_card_pack_for_test(LAYOUT,references_dir=refs,stages=['build-planning'])

if __name__=='__main__':
    unittest.main()
