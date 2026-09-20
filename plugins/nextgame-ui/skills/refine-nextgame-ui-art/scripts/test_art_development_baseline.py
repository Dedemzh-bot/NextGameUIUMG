"""Production-shaped SYNTHETIC TEST ONLY vectors; never Editor evidence."""
import copy
import sys
import unittest
from pathlib import Path

from art_common import ArtError, binding, digest, load_json, sha256, validate, validate_authority
from art_baseline import validate_baseline_closure, validate_development_baseline
from art_pipeline import create_plan, initialize_request
from test_art_stage_integration import LinkedArtFixture, SYNTHETIC
from validate_unreal_widget_readback import validate_unreal_widget_readback
from _document_contract_common import READBACK_SCHEMA


class DevelopmentFixture(LinkedArtFixture):
    def __init__(self):
        super().__init__()
        self.baseline = load_json(self.baseline_bundle_path)
        self.baseline['execution'] = {'status': 'running',
            'buildOrderAssetIds': self.baseline['execution']['buildOrderAssetIds'],
            'startedAt': '2026-09-14T09:56:00+08:00'}
        self.baseline['verification']['status'] = 'pending'
        evidence = []
        for asset in self.baseline['assets']:
            asset['status'] = 'built'
            for kind, minute in [('compile', 57), ('save', 58)]:
                path = asset['assetPath']
                toolset, tool, arguments = (
                    ('UMGToolSet.UMGToolSet', 'CompileWidgetBlueprint',
                     {'widgetBlueprint': {'refPath': path + '.' + path.rsplit('/', 1)[-1]}})
                    if kind == 'compile' else
                    ('editor_toolset.toolsets.asset.AssetTools', 'save_assets', {'asset_paths': [path]}))
                plan_path = self.art_dir / (asset['id'] + '-' + kind + '.plan.json')
                cp_path = self.art_dir / (asset['id'] + '-' + kind + '.checkpoint.json')
                plan = {'assetPath': path, 'steps': [{'stepId': kind, 'operation': 'call_tool',
                    'toolsetName': toolset, 'toolName': tool, 'arguments': arguments}]}
                self.save(plan_path, plan)
                cp = {'formatVersion': 2, 'planSha256': digest(plan), 'completedPrefix': 1,
                    'status': 'completed', 'updatedAt': f'2026-09-14T09:{minute}:00+08:00',
                    'events': [{'status': 'completed', 'index': 1, 'stepId': kind,
                        'tool': toolset + '.' + tool, 'result': {'returnValue': True}}]}
                self.save(cp_path, cp)
                check_id = 'synthetic-' + kind + '-' + asset['id']
                self.baseline['verification']['checks'].append({'id': check_id, 'type': kind,
                    'status': 'passed', 'assetId': asset['id'], 'details': SYNTHETIC,
                    'requirementRefs': [], 'claimIds': [], 'artifactPath': cp_path.relative_to(self.root).as_posix()})
                evidence.append({'checkId': check_id, 'stepId': kind, 'plan': binding(plan_path), 'checkpoint': binding(cp_path)})
        screen = next(a for a in self.baseline['assets'] if a['assetKind'] == 'screen')
        self.pending = {'id': 'synthetic-hidden-render-pending', 'type': 'preview', 'status': 'pending',
            'assetId': screen['id'], 'details': SYNTHETIC, 'requirementRefs': [], 'claimIds': []}
        self.baseline['verification']['checks'].append(copy.deepcopy(self.pending))
        self.request['goal'] = 'formal-art'
        self.request['capabilities'] = ['development-baseline/1']
        self.request['developmentBaseline'] = {'version': 1,
            'structureCompletedAt': '2026-09-14T09:59:00+08:00',
            'pendingCheckIds': [self.pending['id']], 'buildEvidence': evidence}
        self.bind_baseline()
        self.rebuild()

    def bind_baseline(self):
        self.save(self.baseline_bundle_path, self.baseline)
        readback = load_json(self.baseline_readback_path)
        readback['bundleBinding']['sha256'] = sha256(self.baseline_bundle_path)
        readback['capturedAt'] = '2026-09-14T10:00:00+08:00'
        self.save(self.baseline_readback_path, readback)
        for key, path in [('bundle', self.baseline_bundle_path), ('readback', self.baseline_readback_path)]:
            self.request['baseline'][key] = binding(path)
        self.save(self.request_path, self.request)

    def rebuild(self):
        self.save(self.request_path, self.request)
        self.decisions['requestSha256'] = sha256(self.request_path)
        self.save(self.decisions_path, self.decisions)
        self.plan = create_plan(self.request_path, self.decisions_path)
        self.save(self.plan_path, self.plan)
        self.execution['planSha256'] = sha256(self.plan_path)
        self.save(self.execution_path, self.execution)
        existing = {c['id'] for c in self.sources.bundle['verification']['checks']}
        self.sources.bundle['verification']['checks'].extend(copy.deepcopy(c)
            for c in self.baseline['verification']['checks'] if c['id'] not in existing)
        self.flush()

    def validate_baseline(self):
        return validate_authority(self.request, self.request_path)

    def final_checks(self):
        checks = copy.deepcopy(self.baseline['verification']['checks'])
        for check in checks:
            check['status'] = 'passed'
        return {'verification': {'checks': checks}}


class DevelopmentBaselineTests(unittest.TestCase):
    def setUp(self):
        self.fx = DevelopmentFixture()
        self.addCleanup(self.fx.close)

    def rejected(self, code=None):
        with self.assertRaises(ArtError) as caught:
            self.fx.validate_baseline()
        if code:
            self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_explicit_baseline_starts_actual_art_plan_and_preserves_pending(self):
        self.assertEqual(self.fx.validate_baseline()['bundle'], self.fx.baseline_bundle_path)
        self.assertEqual(self.fx.baseline['verification']['checks'][-1]['status'], 'pending')
        self.assertEqual(create_plan(self.fx.request_path, self.fx.decisions_path)['issues'], [])

    def test_existing_init_expands_explicit_job_and_hashes_original_receipts(self):
        keys = ('goal', 'originalText', 'scope', 'references', 'resourceDir', 'developmentBaseline')
        job = {key: copy.deepcopy(self.fx.request[key]) for key in keys}
        job['baseline'] = {key: record['path'] for key, record in self.fx.request['baseline'].items()}
        job['authorizedAssetPaths'] = [a['assetPath'] for a in self.fx.baseline['assets']]
        for ref in job['references']: ref['image'] = ref['image']['path']
        for item in job['developmentBaseline']['buildEvidence']:
            for key in ('plan', 'checkpoint'): item[key] = item[key]['path']
        job_path, output = self.fx.art_dir / 'init-job.json', self.fx.art_dir / 'initialized-request.json'
        self.fx.save(job_path, job)
        initialize_request(job_path, output)
        request = load_json(output)
        self.assertEqual(request['capabilities'], ['presentation-review/1', 'development-baseline/1'])
        self.assertEqual(request['developmentBaseline'], self.fx.request['developmentBaseline'])

    def test_legacy_request_keeps_final_baseline_gate(self):
        del self.fx.request['capabilities']; del self.fx.request['developmentBaseline']
        self.rejected('authority.invalid')

    def test_closed_versioned_capability_schema(self):
        for key, value in [('version', 2), ('extra', True)]:
            request = copy.deepcopy(self.fx.request)
            request['developmentBaseline'][key] = value
            with self.assertRaises(ArtError): validate(request, 'request')
        for mutate in (lambda r: r.update(goal='upgrade-art'),
                       lambda r: r.pop('developmentBaseline'),
                       lambda r: r.update(capabilities=['unknown/1'])):
            request = copy.deepcopy(self.fx.request); mutate(request)
            with self.assertRaises(ArtError): validate(request, 'request')

    def test_pending_ids_are_exact(self):
        self.fx.request['developmentBaseline']['pendingCheckIds'].append('unknown')
        self.rejected('baseline.pending_coverage')

    def test_nonvisual_pending_and_failure_are_rejected(self):
        check = self.fx.baseline['verification']['checks'][0]
        check['status'] = 'pending'
        self.fx.request['developmentBaseline']['pendingCheckIds'].append(check['id'])
        self.fx.bind_baseline(); self.rejected('baseline.check_status')
        check['status'] = 'failed'
        self.fx.request['developmentBaseline']['pendingCheckIds'].remove(check['id'])
        self.fx.bind_baseline(); self.rejected('baseline.check_status')

    def test_missing_structural_check_is_rejected(self):
        self.fx.baseline['verification']['checks'] = [c for c in self.fx.baseline['verification']['checks'] if c['type'] != 'save']
        self.fx.bind_baseline(); self.rejected('baseline.structural_coverage')

    def test_checkpoint_false_or_stale_or_wrong_target_is_rejected(self):
        record = self.fx.request['developmentBaseline']['buildEvidence'][0]
        cp_path = Path(record['checkpoint']['path']); cp = load_json(cp_path)
        cp['events'][0]['result']['returnValue'] = False
        self.fx.save(cp_path, cp); record['checkpoint'] = binding(cp_path)
        self.rejected('baseline.build_result')
        cp['events'][0]['result']['returnValue'] = True
        cp['planSha256'] = '0' * 64
        self.fx.save(cp_path, cp); record['checkpoint'] = binding(cp_path)
        self.rejected('baseline.build_checkpoint')

    def test_real_executor_digest_is_distinct_from_pretty_file_hash(self):
        record = self.fx.request['developmentBaseline']['buildEvidence'][0]
        cp_path = Path(record['checkpoint']['path']); cp = load_json(cp_path)
        self.assertNotEqual(cp['planSha256'], record['plan']['sha256'])
        self.fx.validate_baseline()
        cp['planSha256'] = record['plan']['sha256']
        self.fx.save(cp_path, cp); record['checkpoint'] = binding(cp_path)
        self.rejected('baseline.build_checkpoint')

    def test_resolved_tool_target_and_checkpoint_artifact_are_exact(self):
        record = self.fx.request['developmentBaseline']['buildEvidence'][0]
        plan_path = Path(record['plan']['path']); plan = load_json(plan_path)
        cp_path = Path(record['checkpoint']['path']); cp = load_json(cp_path)
        plan['steps'][0]['arguments']['widgetBlueprint']['refPath'] += 'Wrong'
        self.fx.save(plan_path, plan); record['plan'] = binding(plan_path)
        cp['planSha256'] = digest(plan)
        self.fx.save(cp_path, cp); record['checkpoint'] = binding(cp_path)
        self.rejected('baseline.build_result')

    def test_request_identity_and_duplicate_evidence_rejected(self):
        self.fx.request['requestId'] += '-wrong'
        self.rejected('baseline.request_identity')
        self.fx.request['requestId'] = self.fx.sources.requirement['requestId']
        self.fx.request['developmentBaseline']['buildEvidence'].append(
            copy.deepcopy(self.fx.request['developmentBaseline']['buildEvidence'][0]))
        self.rejected('baseline.build_evidence_coverage')

    def test_incomplete_checkpoint_and_changed_event_are_rejected(self):
        record = self.fx.request['developmentBaseline']['buildEvidence'][0]
        cp_path = Path(record['checkpoint']['path']); cp = load_json(cp_path)
        cp['completedPrefix'] = 0
        self.fx.save(cp_path, cp); record['checkpoint'] = binding(cp_path)
        self.rejected('baseline.build_checkpoint')
        cp['completedPrefix'] = 1; cp['events'][0]['tool'] = 'fake.compile'
        self.fx.save(cp_path, cp); record['checkpoint'] = binding(cp_path)
        self.rejected('baseline.build_events')

    def test_structural_time_and_old_readback_fail(self):
        self.fx.request['developmentBaseline']['structureCompletedAt'] = '2026-09-14T09:57:30+08:00'
        self.rejected('baseline.build_time')
        self.fx.request['developmentBaseline']['structureCompletedAt'] = '2026-09-14T10:01:00+08:00'
        self.rejected('baseline.readback')

    def test_actual_widget_identity_remains_strict(self):
        readback = load_json(self.fx.baseline_readback_path)
        readback['assets'][0]['nodeMappings'][0]['widgetName'] = 'WrongWidget'
        self.fx.save(self.fx.baseline_readback_path, readback)
        self.fx.request['baseline']['readback'] = binding(self.fx.baseline_readback_path)
        self.rejected('baseline.readback')

    def test_snapshot_fixture_or_identity_mismatch_is_rejected(self):
        snap = load_json(self.fx.baseline_snapshot_path)
        snap['acquisition'] = {'method': 'fixture'}
        self.fx.save(self.fx.baseline_snapshot_path, snap)
        self.fx.request['baseline']['snapshot'] = binding(self.fx.baseline_snapshot_path)
        self.rejected('baseline.snapshot')

    def test_formal_readback_and_acceptance_still_reject_development(self):
        report = validate_unreal_widget_readback(load_json(self.fx.baseline_readback_path), load_json(READBACK_SCHEMA),
            readback_path=self.fx.baseline_readback_path, requirement=self.fx.sources.requirement,
            requirement_path=self.fx.sources.requirement_path, bundle=self.fx.baseline,
            bundle_path=self.fx.baseline_bundle_path)
        self.assertFalse(report['valid'])
        self.assertTrue({'bundle.execution', 'bundle.verification', 'bundle.check_status'} <= {i['code'] for i in report['errors']})
        self.assertFalse(self.fx.bundle_report()['valid'])
        self.assertFalse(self.fx.sources.validate_acceptance()['valid'])

    def test_final_closure_passes_only_complete_original_obligations(self):
        final = self.fx.final_checks()
        validate_baseline_closure(self.fx.request, self.fx.request_path, final)
        for mutation in ('remove', 'pending', 'refs', 'rename'):
            value = copy.deepcopy(final); check = value['verification']['checks'][-1]
            if mutation == 'remove': value['verification']['checks'].pop()
            elif mutation == 'pending': check['status'] = 'pending'
            elif mutation == 'refs': check['requirementRefs'] = ['changed']
            else: check['id'] += '-renamed'
            with self.assertRaises(ArtError): validate_baseline_closure(self.fx.request, self.fx.request_path, value)

    def test_final_bundle_cannot_delete_original_pending_check(self):
        self.fx.sources.bundle['verification']['checks'] = [c for c in self.fx.sources.bundle['verification']['checks'] if c['id'] != self.fx.pending['id']]
        self.fx.flush()
        self.assertIn('baseline.closure_pending', {i['code'] for i in self.fx.bundle_report()['errors']})

    def test_completed_original_preview_passes_final_bundle_readback_acceptance(self):
        check = next(c for c in self.fx.sources.bundle['verification']['checks'] if c['id'] == self.fx.pending['id'])
        asset = next(a for a in self.fx.sources.bundle['assets'] if a['id'] == check['assetId'])
        layout = load_json(self.fx.root / asset['layoutSpecPath'])
        nodes = {n['id']: n for n in layout['nodes']}
        regions = {r['id']: r for r in self.fx.sources.requirement['uiModel']['regions']}
        geometry = []
        for mapping in self.fx.sources.bundle['nodeMappings']:
            if mapping['assetId'] != asset['id']: continue
            for ref in mapping['requirementRefs']:
                if ref in regions:
                    geometry.append({'requirementRef': ref, 'layoutNodeId': mapping['layoutNodeId'],
                        'expectedNormalizedRect': regions[ref]['bounds'],
                        'actualNormalizedRect': nodes[mapping['layoutNodeId']]['rect'], 'maxDelta': 0.001, 'status': 'passed'})
        image = Path(next(c['image']['path'] for c in self.fx.captures if c['assetPath'] == asset['assetPath']))
        check.update({'status': 'passed', 'artifactPath': image.relative_to(self.fx.root).as_posix(),
            'previewAudit': {'targetAssetId': asset['id'], 'targetWindow': SYNTHETIC,
                'viewport': [2560, 1440], 'canvas': {'pixelSize': [2560, 1440], 'aspectRatio': 2560 / 1440},
                'modalOrMultipleWindowContamination': False, 'geometryComparisons': geometry,
                'unauthorizedOverlaps': [], 'artifactSha256': sha256(image)}})
        self.fx.flush()
        for report in (self.fx.bundle_report(), self.fx.sources.validate_readback(), self.fx.sources.validate_acceptance()):
            self.assertTrue(report['valid'], report)


if __name__ == '__main__':
    unittest.main()
