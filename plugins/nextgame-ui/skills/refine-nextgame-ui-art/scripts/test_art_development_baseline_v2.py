"""SYNTHETIC TEST ONLY. No Editor calls and no production review authority."""
import copy
import unittest

from art_common import ArtError, binding, load_json, sha256, validate
from art_baseline import validate_baseline_closure
from art_baseline_v2 import contract_digest, _resource_gaps, _pending_judgments
from art_pipeline import create_plan, initialize_request
from test_art_development_baseline import DevelopmentFixture
from test_art_stage_integration import SYNTHETIC
from _document_contract_common import compute_approved_content_sha256, accepted_claim_ids, READBACK_SCHEMA
from validate_unreal_widget_readback import validate_unreal_widget_readback


class ResourceFixture(DevelopmentFixture):
    def __init__(self):
        super().__init__()
        requirement = self.sources.requirement
        element = next(e for e in requirement['uiModel']['elements'] if e['kind'] == 'image')
        element.setdefault('properties', {})['defaultBrushResourceObject'] = '/Game/UI/Synthetic/T_Art.T_Art'
        element['properties'].update(drawAs='Box', mirrorDesign='MirrorHorizontal')
        text = next(e for e in requirement['uiModel']['elements'] if e['kind'] == 'text')
        text.setdefault('properties', {}).update(textEffectJudgment='unresolved', textEffectReason=SYNTHETIC)
        requirement['reviewGate']['approvedContentSha256'] = compute_approved_content_sha256(requirement)
        self.save(self.sources.requirement_path, requirement)
        self.baseline['requirement'].update(sha256=sha256(self.sources.requirement_path),
            approvedContentSha256=requirement['reviewGate']['approvedContentSha256'])
        self.request['baseline']['requirement'] = binding(self.sources.requirement_path)
        readback = load_json(self.baseline_readback_path)
        readback['requirementBinding'].update(sha256=sha256(self.sources.requirement_path),
            approvedContentSha256=requirement['reviewGate']['approvedContentSha256'])
        mapping = next(m for m in self.baseline['nodeMappings'] if element['id'] in m['requirementRefs'])
        actual_asset = next(a for a in readback['assets'] if a['assetId'] == mapping['assetId'])
        actual_mapping = next(m for m in actual_asset['nodeMappings'] if m['nodeMappingId'] == mapping['id'])
        widget = next(w for w in actual_asset['widgets'] if w['widgetName'] == actual_mapping['widgetName'])
        widget['classPath'] = '/Script/UIFramework.GameImage'
        self.save(self.baseline_readback_path, readback)
        snap = load_json(self.baseline_snapshot_path)
        sa = next(a for a in snap['assets'] if a['assetPath'] == actual_asset['assetPath'])
        sw = next(w for w in sa['widgets'] if w['widgetName'] == widget['widgetName'])
        sw['classPath'] = widget['classPath']
        sw['properties']['brush'] = {'resourceObject': 'None', 'drawAs': 'Image', 'mirroring': 'NoMirror'}
        self.save(self.baseline_snapshot_path, snap)
        self.request['baseline']['snapshot'] = binding(self.baseline_snapshot_path)
        self.deferred = {'id': 'synthetic-confirmed-resource-traceability', 'type': 'key-properties',
            'assetId': actual_asset['assetId'], 'requirementRefs': [element['id']],
            'claimIds': element['claimIds'], 'status': 'pending', 'details': SYNTHETIC}
        self.baseline['verification']['checks'].append(self.deferred)
        basic = [next(c['id'] for c in self.baseline['verification']['checks']
                      if c['type'] == 'key-properties' and c['assetId'] == a['id'] and c['status'] == 'passed')
                 for a in self.baseline['assets']]
        fields = list(_resource_gaps(requirement, self.baseline, readback, snap, accepted_claim_ids(requirement)).values())
        self.request['capabilities'] = ['development-baseline/2']
        contract = self.request['developmentBaseline']
        contract.update(version=2, basicPropertyCheckIds=basic,
            deferredPropertyChecks=[{'check': {k: self.deferred[k] for k in ('id', 'type', 'assetId', 'requirementRefs', 'claimIds')},
                                     'reason': 'art-owned-property-closure', 'fields': fields}],
            pendingArtJudgments=[dict(j, closureCheckIds=[self.pending['id']])
                                 for j in _pending_judgments(requirement, accepted_claim_ids(requirement)).values()])
        contract['pendingCheckIds'].append(self.deferred['id'])
        self.bind_baseline()
        self.review_path_v2 = self.art_dir / 'SYNTHETIC-primary-deferral-review.json'
        self.review_v2 = {'kind': 'development-baseline-art-deferral-review', 'version': 1, 'status': 'approved',
            'reviewedBy': {'role': 'primary-agent', 'id': SYNTHETIC}, 'reviewedAt': '2026-09-14T10:01:00+08:00',
            'reason': 'art-owned-property-closure', 'confirmedNonArtNativeResponsibilitiesVerified': True,
            'notResultAcceptance': True, 'notes': SYNTHETIC}
        self.synthetic_review()

    def synthetic_review(self):
        """TEST ONLY fixture mutator; no production signing helper is provided."""
        for key in ('requirement', 'bundle', 'readback', 'snapshot'):
            self.review_v2[key + 'Sha256'] = self.request['baseline'][key]['sha256']
        self.review_v2['contractSha256'] = contract_digest(self.request['developmentBaseline'])
        self.save(self.review_path_v2, self.review_v2)
        self.request['developmentBaseline']['primaryReview'] = binding(self.review_path_v2)
        self.save(self.request_path, self.request)


class ResourceBaselineTests(unittest.TestCase):
    def setUp(self):
        self.fx = ResourceFixture()
        self.addCleanup(self.fx.close)

    def reject(self, code=None):
        with self.assertRaises(ArtError) as caught:
            self.fx.validate_baseline()
        if code:
            self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_fresh_v2_accepts_actual_gap_and_retains_pending(self):
        self.fx.validate_baseline()
        self.assertEqual(self.fx.deferred['status'], 'pending')
        self.fx.decisions['requestSha256'] = sha256(self.fx.request_path)
        self.fx.save(self.fx.decisions_path, self.fx.decisions)
        self.assertEqual(create_plan(self.fx.request_path, self.fx.decisions_path)['issues'], [])

    def test_v1_cannot_gain_v2_meaning(self):
        self.fx.request['capabilities'] = ['development-baseline/1']
        c = self.fx.request['developmentBaseline']
        c['version'] = 1
        for k in ('deferredPropertyChecks', 'basicPropertyCheckIds', 'pendingArtJudgments', 'primaryReview'):
            del c[k]
        self.reject('baseline.check_status')

    def test_mixed_capabilities_missing_and_extra_fields_rejected(self):
        for mutation in (lambda r: r['capabilities'].append('development-baseline/1'),
                         lambda r: r['developmentBaseline'].pop('primaryReview'),
                         lambda r: r['developmentBaseline'].update(allowPending=True),
                         lambda r: r.update(capabilities=['development-baseline/1'])):
            r = copy.deepcopy(self.fx.request); mutation(r)
            with self.assertRaises(ArtError): validate(r, 'request')

    def test_basic_properties_cannot_be_deferred(self):
        self.fx.request['developmentBaseline']['basicPropertyCheckIds'][0] = self.fx.deferred['id']
        self.reject('baseline.basic_properties')

    def test_every_asset_needs_schema_check(self):
        self.fx.baseline['verification']['checks'] = [c for c in self.fx.baseline['verification']['checks'] if c['type'] != 'schema']
        self.fx.bind_baseline(); self.fx.synthetic_review()
        self.reject()  # Full source coverage may reject the missing schema obligation first.

    def test_failed_deferred_check_is_rejected(self):
        self.fx.deferred['status'] = 'failed'
        self.fx.request['developmentBaseline']['pendingCheckIds'].remove(self.fx.deferred['id'])
        self.fx.bind_baseline(); self.fx.synthetic_review()
        self.reject('baseline.deferral_check')

    def test_deferral_cannot_change_original_identity_or_reason(self):
        c = self.fx.request['developmentBaseline']['deferredPropertyChecks'][0]['check']
        c['requirementRefs'] = []
        self.reject('baseline.deferral_check')

    def test_known_source_value_and_actual_observation_are_both_required(self):
        f = self.fx.request['developmentBaseline']['deferredPropertyChecks'][0]['fields'][0]
        for key, value in [('sourceValue', '/Game/Fake'), ('expectedNativeValue', '/Game/Fake'), ('actualValue', '/Game/Fake'),
                           ('sourcePointer', '/claims/0'), ('actualSnapshotPointer', '/assets/9'),
                           ('widgetName', 'Fake'), ('nodeMappingId', 'fake')]:
            old = f[key]; f[key] = value
            self.reject('baseline.deferral_field')
            f[key] = old

    def test_three_exact_mappings_and_native_mirror_enum(self):
        fields = self.fx.request['developmentBaseline']['deferredPropertyChecks'][0]['fields']
        self.assertEqual({f['nativeProperty'] for f in fields}, {'brush.resourceObject', 'brush.drawAs', 'brush.mirroring'})
        mirror = next(f for f in fields if f['nativeProperty'] == 'brush.mirroring')
        self.assertEqual((mirror['sourceValue'], mirror['expectedNativeValue']), ('MirrorHorizontal', 'Horizontal'))
        self.fx.validate_baseline()

    def test_missing_accepted_draw_as_gap_is_rejected(self):
        fields = self.fx.request['developmentBaseline']['deferredPropertyChecks'][0]['fields']
        fields[:] = [f for f in fields if f['nativeProperty'] != 'brush.drawAs']
        self.reject('baseline.deferral_coverage')

    def test_unknown_brush_enum_not_automatically_lowered(self):
        req = copy.deepcopy(self.fx.sources.requirement)
        element = next(e for e in req['uiModel']['elements'] if e['kind'] == 'image')
        element['properties']['mirrorDesign'] = 'InventedMirror'
        with self.assertRaises(ArtError):
            _resource_gaps(req, self.fx.baseline, load_json(self.fx.baseline_readback_path),
                           load_json(self.fx.baseline_snapshot_path), accepted_claim_ids(req))

    def test_procedural_source_responsibilities_do_not_become_a_material_path(self):
        req = copy.deepcopy(self.fx.sources.requirement)
        element = next(e for e in req['uiModel']['elements'] if e['kind'] == 'image')
        element['properties'].update(staticAppearance={'nativeMaterialParameters': 'unresolved-art-stage'},
            artMaterialCapability='procedural-ui-material/2', artMaterialExecutionStatus='not-created-or-validated')
        records = _pending_judgments(req, accepted_claim_ids(req))
        found = [r for r in records.values() if r['elementId'] == element['id']]
        self.assertEqual(len(found), 3)
        self.assertEqual({r['sourcePointer'].rsplit('/', 1)[-1] for r in found},
                         {'staticAppearance', 'artMaterialCapability', 'artMaterialExecutionStatus'})

    def test_unrelated_native_property_cannot_be_deferred(self):
        self.fx.request['developmentBaseline']['deferredPropertyChecks'][0]['fields'][0]['nativeProperty'] = 'visibility'
        self.reject('schema.request')

    def test_missing_or_matched_actual_resource_is_not_a_gap(self):
        snap = load_json(self.fx.baseline_snapshot_path)
        field = self.fx.request['developmentBaseline']['deferredPropertyChecks'][0]['fields'][0]
        widget = next(w for a in snap['assets'] for w in a['widgets'] if w['widgetName'] == field['widgetName'])
        widget['properties']['brush']['resourceObject'] = field['sourceValue']
        self.fx.save(self.fx.baseline_snapshot_path, snap)
        self.fx.request['baseline']['snapshot'] = binding(self.fx.baseline_snapshot_path)
        self.reject('baseline.deferral_field')

    def test_actual_missing_observation_cannot_be_filled_from_expected(self):
        snap = load_json(self.fx.baseline_snapshot_path)
        for asset in snap['assets']:
            for widget in asset['widgets']: widget['properties'].pop('brush', None)
        self.fx.save(self.fx.baseline_snapshot_path, snap)
        self.fx.request['baseline']['snapshot'] = binding(self.fx.baseline_snapshot_path)
        self.reject('baseline.deferral_actual')

    def test_primary_review_is_bound_and_must_be_explicit(self):
        self.fx.review_v2['bundleSha256'] = '0' * 64
        self.fx.save(self.fx.review_path_v2, self.fx.review_v2)
        self.fx.request['developmentBaseline']['primaryReview'] = binding(self.fx.review_path_v2)
        self.reject('baseline.deferral_review')

    def test_no_native_default_can_close_unresolved_art_judgment(self):
        self.fx.request['developmentBaseline']['pendingArtJudgments'].pop()
        self.reject('baseline.judgment_coverage')

    def test_art_judgment_cannot_substitute_resource_deferral(self):
        self.fx.request['developmentBaseline']['pendingArtJudgments'][0]['closureCheckIds'] = [self.fx.deferred['id']]
        self.reject('baseline.judgment_check')

    def test_final_public_readback_remains_strict(self):
        report = validate_unreal_widget_readback(load_json(self.fx.baseline_readback_path), load_json(READBACK_SCHEMA),
            readback_path=self.fx.baseline_readback_path, requirement=self.fx.sources.requirement,
            requirement_path=self.fx.sources.requirement_path, bundle=self.fx.baseline,
            bundle_path=self.fx.baseline_bundle_path)
        self.assertFalse(report['valid'])
        self.assertIn('verification.check_status', {e['code'] for e in report['errors']})

    def test_final_closure_preserves_every_original_check(self):
        final = self.fx.final_checks()
        validate_baseline_closure(self.fx.request, self.fx.request_path, final)
        for mutate in (lambda c: c.update(status='pending'), lambda c: c.update(type='preview'),
                       lambda c: c.update(claimIds=[]), lambda c: c.update(requirementRefs=[]),
                       lambda c: c.update(assetId='other')):
            altered = copy.deepcopy(final)
            target = next(c for c in altered['verification']['checks'] if c['id'] == self.fx.deferred['id'])
            mutate(target)
            with self.assertRaises(ArtError): validate_baseline_closure(self.fx.request, self.fx.request_path, altered)

    def test_init_requires_explicit_version_and_binds_existing_review(self):
        keys = ('goal', 'originalText', 'scope', 'references', 'resourceDir', 'developmentBaseline')
        job = {k: copy.deepcopy(self.fx.request[k]) for k in keys}
        job['baseline'] = {k: v['path'] for k, v in self.fx.request['baseline'].items()}
        job['authorizedAssetPaths'] = [a['assetPath'] for a in self.fx.baseline['assets']]
        for ref in job['references']: ref['image'] = ref['image']['path']
        for record in job['developmentBaseline']['buildEvidence']:
            for key in ('plan', 'checkpoint'): record[key] = record[key]['path']
        job['developmentBaseline']['primaryReview'] = self.fx.request['developmentBaseline']['primaryReview']['path']
        p, out = self.fx.art_dir / 'synthetic-job.json', self.fx.art_dir / 'synthetic-init-request.json'
        self.fx.save(p, job); initialize_request(p, out)
        result = load_json(out)
        self.assertIn('development-baseline/2', result['capabilities'])
        self.assertNotIn('development-baseline/1', result['capabilities'])
        self.assertEqual(result['developmentBaseline'], self.fx.request['developmentBaseline'])


if __name__ == '__main__':
    unittest.main()
