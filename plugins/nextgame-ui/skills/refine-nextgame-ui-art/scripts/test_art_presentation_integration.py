"""Synthetic presentation/Bundle/Readback integration; no real UI acceptance."""
import copy
import unittest
from unittest.mock import patch

import art_common as common
import art_pipeline as pipeline
from art_presentation import IMAGE_CLASSES, TEXT_CLASSES, validate_presentation
from test_art_presentation import native_text, text_review
from test_art_stage_integration import LinkedArtFixture, SYNTHETIC


class PresentationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fx = LinkedArtFixture()
        self.addCleanup(self.fx.close)

    def enable(self):
        fx = self.fx
        fx.request['capabilities'] = ['presentation-review/1']
        review = {'version': 1, 'images': [], 'texts': [], 'families': []}
        fx.decisions['presentationReview'] = review
        for asset in fx.snapshot['assets']:
            references = [r for r in fx.request['references'] if r['assetPath'] == asset['assetPath']]
            for ref in references:
                ref['regions'][0]['widgetNames'] = [w['widgetName'] for w in asset['widgets']]
            ref = references[0]
            evidence = {'referenceId': ref['id'], 'regionId': ref['regions'][0]['id'], 'bounds': ref['regions'][0]['bounds']}
            for node in asset['widgets']:
                if node['classPath'] in IMAGE_CLASSES:
                    node['properties']['brush'] = {'drawAs': 'RoundedBox', 'resourceObject': 'None',
                        'imageSize': {'x': 16, 'y': 16}}
                    review['images'].append({'assetPath': asset['assetPath'], 'widgetName': node['widgetName'],
                        'reference': copy.deepcopy(evidence), 'reason': SYNTHETIC, 'resolution': 'unambiguous',
                        'source': {'kind': 'procedural', 'reason': SYNTHETIC}, 'aspectMode': 'stretch', 'familyId': None})
                elif node['classPath'] in TEXT_CLASSES:
                    node['properties'].update(native_text())
                    review['texts'].append(text_review(asset['assetPath'], node['widgetName'], copy.deepcopy(evidence)))
        self.assertTrue(review['images'] or review['texts'], 'Integration fixture must exercise presentation coverage')
        self.rebind()

    def rebind(self):
        fx = self.fx
        fx.save(fx.snapshot_path, fx.snapshot)
        baseline = copy.deepcopy(fx.snapshot)
        baseline['capturedAt'] = '2026-09-14T10:00:00+08:00'
        fx.save(fx.baseline_snapshot_path, baseline)
        fx.request['baseline']['snapshot'] = common.binding(fx.baseline_snapshot_path)
        fx.save(fx.request_path, fx.request)
        fx.decisions['requestSha256'] = common.sha256(fx.request_path)
        fx.save(fx.decisions_path, fx.decisions)
        fx.plan = pipeline.create_plan(fx.request_path, fx.decisions_path, validate_sources=False)
        fx.save(fx.plan_path, fx.plan)
        fx.execution.update(planSha256=common.sha256(fx.plan_path), expectedStateSha256=fx.plan['expectedStateSha256'],
            readback=common.binding(fx.snapshot_path))
        fx.save(fx.execution_path, fx.execution)
        fx.review['snapshotSha256'] = common.sha256(fx.snapshot_path)
        for capture in fx.captures:
            capture['snapshotSha256'] = common.sha256(fx.snapshot_path)
        result = validate_presentation(fx.request, fx.decisions, fx.snapshot, fx.request_path, fx.decisions_path, phase='actual')
        fx.verification['checks'] = result['checks'] + [
            {'id': ('capture:' if 'capabilities' in fx.request else '') + r['id'],
             'status': 'passed', 'details': SYNTHETIC} for r in fx.request['references']]
        fx.flush()

    def assertGatesReject(self, code):
        errors = self.fx.helper()
        self.assertIn(code, {e['code'] for e in errors}, errors)
        self.assertFalse(self.fx.bundle_report()['valid'])
        self.assertFalse(self.fx.sources.validate_readback()['valid'])

    def test_optin_native_only_judgments_pass_existing_linked_gates(self):
        self.enable()
        self.assertEqual([], self.fx.helper())
        self.assertTrue(self.fx.bundle_report()['valid'])
        self.assertTrue(self.fx.sources.validate_readback()['valid'])

    def test_completion_gate_recomputes_presentation_checks(self):
        self.enable()
        self.fx.verification['checks'] = [{'id': 'claimed-all-good', 'status': 'passed', 'details': SYNTHETIC}]
        self.fx.flush()
        self.assertGatesReject('art.presentation_checks')

    def rename_reference_with_presentation_prefix(self):
        fx = self.fx
        old = fx.request['references'][0]['id']; new = 'presentation.legacy-reference'
        fx.request['references'][0]['id'] = new
        fx.comparisons[0]['referenceId'] = new
        fx.review['inspectedRegions'] = [value.replace(old + ':', new + ':', 1) for value in fx.review['inspectedRegions']]

    def test_legacy_reference_id_may_start_with_presentation(self):
        self.rename_reference_with_presentation_prefix()
        self.rebind()
        self.assertEqual([], self.fx.helper())
        self.assertTrue(self.fx.bundle_report()['valid'])

    def test_optin_reference_id_may_start_with_presentation(self):
        self.rename_reference_with_presentation_prefix()
        self.enable()
        self.assertEqual([], self.fx.helper())
        self.assertTrue(self.fx.bundle_report()['valid'])

    def test_extra_injected_passed_check_does_not_bypass_closed_check_identity(self):
        self.enable()
        self.fx.verification['checks'].append({'id': 'presentation.invented', 'status': 'passed', 'details': SYNTHETIC})
        self.fx.flush()
        self.assertGatesReject('art.presentation_checks')

    def test_rebound_decisions_cannot_omit_unchanged_text(self):
        self.enable()
        fx = self.fx
        review = fx.decisions['presentationReview']
        if review['texts']:
            review['texts'].pop()
        else:
            review['images'].pop()
        fx.save(fx.decisions_path, fx.decisions)
        fx.plan['decisions'] = common.binding(fx.decisions_path)
        fx.save(fx.plan_path, fx.plan)
        fx.execution['planSha256'] = common.sha256(fx.plan_path)
        fx.save(fx.execution_path, fx.execution)
        fx.flush()
        self.assertGatesReject('presentation.coverage')

    def test_unknown_geometry_cannot_be_promoted_by_forged_passed_receipt(self):
        self.enable()
        fx = self.fx
        self.assertTrue(fx.decisions['presentationReview']['images'])
        item = fx.decisions['presentationReview']['images'][0]
        node = next(w for a in fx.snapshot['assets'] if a['assetPath'] == item['assetPath']
                    for w in a['widgets'] if w['widgetName'] == item['widgetName'])
        source = fx.resource_dir/'test-icon.png'
        resource = {'refPath': '/Game/UI/Textures/Synthetic/T_Test.T_Test'}
        catalog = {'resources': [{'id': 'synthetic', 'sourcePath': str(source), 'sourceSha256': common.sha256(source),
            'dimensions': [8, 8], 'brushResourceObject': resource}]}
        catalog_path = fx.art_dir/'synthetic-catalog.json'; fx.save(catalog_path, catalog)
        fx.request['resourceCatalog'] = common.binding(catalog_path)
        from PIL import Image
        from art_images import _bounds
        with Image.open(source) as image:
            alpha = _bounds(image.convert('RGBA'))
        item['source'] = {'kind': 'resource', 'catalogResourceId': 'synthetic', 'image': common.binding(source),
            'frameSize': [8, 8], 'alphaBounds': alpha}
        item['aspectMode'] = 'preserve'
        node['properties']['brush'].update(resourceObject=resource, drawAs='Image', tiling='NoTile')
        with patch('art_resources.validate_catalog', return_value=catalog):
            self.rebind()
            self.assertTrue(any(c['status'] == 'pending' for c in fx.verification['checks']))
            self.assertGatesReject('art.presentation_pending')
            for check in fx.verification['checks']:
                check['status'] = 'passed'
            fx.flush()
            self.assertGatesReject('art.presentation_checks')


if __name__ == '__main__':
    unittest.main()
