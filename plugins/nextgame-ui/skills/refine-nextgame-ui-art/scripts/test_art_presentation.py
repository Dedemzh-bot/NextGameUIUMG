"""Synthetic opt-in presentation regressions. No Editor or real art approval."""
import copy
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

import art_common as common
import art_pipeline as pipeline
from art_presentation import validate_presentation
import test_art_pipeline as legacy

ASSET = legacy.ASSET
FakeEditor = legacy.FakeEditor


def transform(x=1, y=1):
    return {'translation': {'x': 0, 'y': 0}, 'scale': {'x': x, 'y': y},
            'shear': {'x': 0, 'y': 0}, 'angle': 0}


def native_text():
    return {'font': {'size': 20, 'outlineSettings': {'outlineSize': 0,
            'outlineColor': {'r': .02, 'g': .03, 'b': .06, 'a': 1}}},
            'shadowOffset': {'x': 0, 'y': 0}, 'shadowColorAndOpacity': {'r': 0, 'g': 0, 'b': 0, 'a': 0}}


def text_review(asset, widget, reference):
    return {'assetPath': asset, 'widgetName': widget, 'reference': reference,
            'reason': 'SYNTHETIC local glyph inspection; not real design intent.', 'resolution': 'unambiguous',
            'effect': 'none', 'effectTypeConfidence': 'high', 'parameterConfidence': 'high', 'confirmations': [],
            'outline': {'size': 0, 'color': [.02, .03, .06, 1]}, 'shadow': {'offset': [0, 0], 'color': [0, 0, 0, 0]}}


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.fx = legacy.ArtPipelineTests(methodName='runTest')
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.root = self.fx.root
        self.request = self.fx.request
        self.request['capabilities'] = ['presentation-review/1']
        self.request['scope'] = [{'assetPath': ASSET}]
        self.request['references'][0]['regions'][0]['widgetNames'] = ['ImgIcon', 'TxtValue']
        self.snapshot = self.fx.initial
        self.icon = self.snapshot['assets'][0]['widgets'][1]
        self.text = self.snapshot['assets'][0]['widgets'][2]
        for node in self.snapshot['assets'][0]['widgets']:
            node['properties']['renderTransform'] = transform()
        source = self.root/'source-frame.png'
        image = Image.new('RGBA', (20, 10), (255, 255, 255, 0))
        ImageDraw.Draw(image).rectangle((2, 1, 17, 8), fill=(40, 70, 140, 255))
        image.save(source)
        resource = {'refPath': '/Game/UI/Textures/Test/T_Frame.T_Frame'}
        self.icon['properties']['brush'] = {'resourceObject': resource, 'drawAs': 'Image', 'tiling': 'NoTile',
            'imageSize': {'x': 40, 'y': 20}, 'margin': {'left': 0, 'top': 0, 'right': 0, 'bottom': 0}}
        slot = self.icon['slot']['properties']
        slot['bAutoSize'] = False
        slot['layoutData']['anchors'] = {'minimum': {'x': 0, 'y': 0}, 'maximum': {'x': 0, 'y': 0}}
        slot['layoutData']['offsets'].update(right=40, bottom=20)
        self.text['properties'].update(native_text())
        self.catalog = {'resources': [{'id': 'synthetic-frame', 'sourcePath': str(source),
            'sourceSha256': common.sha256(source), 'dimensions': [20, 10], 'brushResourceObject': resource}]}
        catalog_path = self.fx.write('catalog.json', self.catalog)
        self.request['resourceCatalog'] = common.binding(catalog_path)
        # The existing art_resources test suite covers genuine import provenance.
        # Here a labelled synthetic catalog isolates presentation invariants.
        self.catalog_patch = patch('art_resources.validate_catalog', return_value=self.catalog)
        self.catalog_patch.start()
        self.addCleanup(self.catalog_patch.stop)
        reference = {'referenceId': 'icon-default', 'regionId': 'icon', 'bounds': [0, 0, 32, 32]}
        self.image = {'assetPath': ASSET, 'widgetName': 'ImgIcon', 'reference': reference,
            'reason': 'SYNTHETIC full-frame logo; not real artwork.', 'resolution': 'unambiguous',
            'source': {'kind': 'resource', 'catalogResourceId': 'synthetic-frame', 'image': common.binding(source),
                'frameSize': [20, 10], 'alphaBounds': [2, 1, 16, 8]}, 'aspectMode': 'preserve', 'familyId': None}
        self.text_decision = text_review(ASSET, 'TxtValue', copy.deepcopy(reference))
        self.decisions = {'kind': 'nextgame-ui-art-decisions', 'version': 1, 'requestSha256': 'a'*64,
            'decisions': [], 'presentationReview': {'version': 1, 'images': [self.image],
                'texts': [self.text_decision], 'families': []}}
        self.sync()

    def sync(self):
        self.fx.write('snapshot.json', self.snapshot)
        self.request['baseline']['snapshot'] = common.binding(self.root/'snapshot.json')
        self.fx.write('request.json', self.request)
        self.decisions['requestSha256'] = common.sha256(self.root/'request.json')
        self.fx.write('decisions.json', self.decisions)

    def check(self, phase='planned'):
        return validate_presentation(self.request, self.decisions, self.snapshot,
            self.root/'request.json', self.root/'decisions.json', phase=phase)

    def plan(self, operations=None):
        self.decisions['decisions'] = [{'operation': o, 'evidence': 'SYNTHETIC operation evidence', 'resolution': 'unambiguous'} for o in operations or []]
        self.sync()
        result = pipeline.create_plan(self.root/'request.json', self.root/'decisions.json', validate_sources=False)
        self.fx.write('plan.json', result)
        return result

    def assertCode(self, code, call=None):
        with self.assertRaises(common.ArtError) as caught:
            (call or self.check)()
        self.assertEqual(code, caught.exception.code, str(caught.exception))

    def nine(self, cuts=(2, 0, 4, 0)):
        self.image['aspectMode'] = 'nine-slice'
        self.image['nineSlice'] = {'cutPixels': list(cuts), 'stretchAxes': ['x'], 'basisScale': 2,
            'protectedRegions': [{'id': 'right-border-shadow', 'bounds': [16, 0, 4, 10],
                'purpose': 'Preserve the right border and its entire shadow.', 'preserveAxes': ['x', 'y']}]}
        self.icon['properties']['brush']['drawAs'] = 'Box'
        self.icon['properties']['brush']['margin'] = dict(zip(('left', 'top', 'right', 'bottom'),
            [cuts[0]/20, cuts[1]/10, cuts[2]/20, cuts[3]/10]))
        self.icon['slot']['properties']['layoutData']['offsets']['right'] = 80

    def test_complete_static_proof_is_not_actual_geometry(self):
        self.assertTrue(all(c['status'] == 'passed' for c in self.check()['checks']))
        actual = self.check('actual')
        self.assertTrue(any(c['status'] == 'pending' and c['id'].endswith(':geometry') for c in actual['checks']))
        self.assertEqual('ready', self.plan()['status'])

    def test_new_init_enables_capability_and_legacy_stays_legacy(self):
        job = {k: self.request[k] for k in ('goal', 'originalText', 'scope', 'resourceDir')}
        job.update(baseline={k: v['path'] for k, v in self.request['baseline'].items()},
            references=copy.deepcopy(self.request['references']), authorizedAssetPaths=[ASSET])
        job['references'][0]['image'] = job['references'][0]['image']['path']
        self.fx.write('job.json', job)
        with patch.object(pipeline, 'validate_authority'):
            pipeline.initialize_request(self.root/'job.json', self.root/'new-request.json')
        self.assertEqual(['presentation-review/1'], common.load_json(self.root/'new-request.json')['capabilities'])
        self.request.pop('capabilities'); self.decisions.pop('presentationReview')
        self.assertEqual({'checks': [], 'issues': []}, self.check())
        self.assertEqual('ready', self.plan()['status'])

    def test_capability_requires_closed_matching_review(self):
        original = copy.deepcopy(self.decisions)
        self.decisions.pop('presentationReview')
        self.assertCode('presentation.coverage')
        self.decisions = original; self.request.pop('capabilities')
        self.assertCode('presentation.capability')
        self.request['capabilities'] = ['presentation-review/2']
        self.assertCode('schema.request')

    def test_unknown_review_fields_rejected(self):
        self.image['guessedUV'] = [0, 0, 1, 1]
        self.assertCode('schema.decisions')

    def test_unchanged_collapsed_text_cannot_be_omitted(self):
        self.text['properties']['visibility'] = 'Collapsed'
        self.decisions['presentationReview']['texts'] = []
        self.assertCode('presentation.coverage')

    def test_duplicate_or_wrong_class_review_rejected(self):
        self.decisions['presentationReview']['texts'].append(copy.deepcopy(self.text_decision))
        self.assertCode('presentation.coverage')
        self.decisions['presentationReview']['texts'] = [self.text_decision]
        self.text_decision['widgetName'] = 'ImgIcon'
        self.assertCode('presentation.coverage')

    def test_local_reference_requires_widget_and_region_binding(self):
        self.request['references'][0]['regions'][0]['widgetNames'] = ['ImgIcon']
        self.assertCode('presentation.reference')

    def test_source_frame_is_not_alpha_bounds(self):
        self.image['source']['frameSize'] = [16, 8]
        self.assertCode('presentation.source_frame')

    def test_transparent_white_rgb_does_not_expand_alpha_content(self):
        self.assertEqual([], self.check()['issues'])
        self.image['source']['alphaBounds'] = [0, 0, 20, 10]
        self.assertCode('presentation.source_frame')

    def test_source_hash_resource_path_and_sprite_dimensions_checked(self):
        self.icon['properties']['brush']['resourceObject'] = {'refPath': '/Game/UI/Textures/Other'}
        self.assertCode('presentation.resource_identity')
        self.icon['properties']['brush']['resourceObject'] = self.catalog['resources'][0]['brushResourceObject']
        self.catalog['resources'][0]['atlas'] = {'sourceDimensions': [200, 100]}
        self.assertCode('presentation.source_frame')

    def test_resource_catalog_cannot_be_replaced_with_name_guess(self):
        self.request.pop('resourceCatalog')
        self.assertCode('presentation.resource_catalog')

    def test_native_brush_and_slot_and_ancestor_distortion_rejected(self):
        self.icon['properties']['brush']['imageSize']['x'] = 42
        self.assertCode('presentation.aspect')
        self.icon['properties']['brush']['imageSize']['x'] = 40
        self.icon['slot']['properties']['layoutData']['offsets']['right'] = 42
        self.assertCode('presentation.aspect')
        self.icon['slot']['properties']['layoutData']['offsets']['right'] = 40
        self.snapshot['assets'][0]['widgets'][0]['properties']['renderTransform'] = transform(2, 1)
        self.assertCode('presentation.aspect')

    def test_unknown_layout_evidence_stays_pending(self):
        self.icon['slot']['properties'].pop('bAutoSize')
        self.assertTrue(any(c['status'] == 'pending' for c in self.check()['checks']))

    def test_accepted_mirroring_preserves_dimensions_but_zero_is_degenerate(self):
        self.snapshot['assets'][0]['widgets'][0]['properties']['renderTransform'] = transform(-1, 1)
        self.assertEqual([], self.check()['issues'])
        self.snapshot['assets'][0]['widgets'][0]['properties']['renderTransform'] = transform(-2, 1)
        self.assertCode('presentation.aspect')
        self.snapshot['assets'][0]['widgets'][0]['properties']['renderTransform'] = transform(0, 1)
        self.assertCode('presentation.transform')

    def test_conflicting_native_auto_size_aliases_rejected(self):
        self.icon['slot']['properties']['autoSize'] = True
        self.assertCode('presentation.slot_alias')

    def test_nine_slice_border_shadow_inside_stretch_band_rejected(self):
        self.nine((2, 0, 2, 0))
        self.assertCode('presentation.protected_region')
        self.nine((2, 0, 4, 0))
        self.assertEqual([], self.check()['issues'])

    def test_straight_horizontal_border_can_stretch_x_but_preserves_y(self):
        self.nine((2, 1, 4, 1))
        self.image['nineSlice']['protectedRegions'] = [{'id': 'top-line', 'bounds': [0, 0, 20, 1],
            'purpose': 'The horizontal line can lengthen, but cannot change thickness.', 'preserveAxes': ['y']}]
        self.assertEqual([], self.check()['issues'])
        self.image['nineSlice']['stretchAxes'] = ['x', 'y']
        self.image['nineSlice']['protectedRegions'][0]['bounds'] = [0, 0, 20, 2]
        self.assertCode('presentation.protected_region')

    def test_nine_slice_requires_cuts_native_margin_and_basis_agreement(self):
        self.nine(); self.icon['properties']['brush']['margin']['right'] = .1
        self.assertCode('presentation.native_mismatch')
        self.nine(); self.image['nineSlice']['basisScale'] = 1
        self.assertCode('presentation.native_mismatch')
        self.nine((10, 0, 10, 0)); self.assertCode('presentation.nine_slice')

    def test_nine_slice_disallowed_axis_and_small_target_rejected(self):
        self.nine(); self.icon['slot']['properties']['layoutData']['offsets']['bottom'] = 21
        self.assertCode('presentation.stretch_axis')
        self.icon['slot']['properties']['layoutData']['offsets'].update(right=8, bottom=20)
        self.assertCode('presentation.nine_slice_target')

    def test_none_is_not_unknown_or_default(self):
        self.text_decision['effectTypeConfidence'] = 'unknown'
        self.assertCode('presentation.text_unknown_none')
        self.text_decision['effect'] = 'unknown'
        self.assertTrue(self.check()['issues'])
        self.assertEqual('needs-review', self.plan()['status'])

    def test_explicit_none_confirmation_preserves_automatic_unknown_confidence(self):
        self.text_decision.update(effectTypeConfidence='unknown', resolution='confirmed')
        self.text_decision['confirmations'] = [{'scope': 'effect-type', 'source': 'direct-user-message',
            'text': 'SYNTHETIC explicit choice: this text has no outline or shadow.'}]
        self.assertEqual([], self.check()['issues'])
        self.assertEqual('unknown', self.text_decision['effectTypeConfidence'])

    def test_effect_type_and_parameter_confidence_are_independent(self):
        self.text_decision['parameterConfidence'] = 'low'
        self.assertTrue(self.check()['issues'])
        self.text_decision['confirmations'] = [{'scope': 'effect-type', 'source': 'direct-user-message', 'text': 'SYNTHETIC: none confirmed'}]
        self.assertTrue(self.check()['issues'])
        self.text_decision['confirmations'].append({'scope': 'appearance-parameters', 'source': 'direct-user-message', 'text': 'SYNTHETIC: these explicit parameters confirmed'})
        self.assertEqual([], self.check()['issues'])

    def test_method_approval_cannot_confirm_appearance(self):
        self.text_decision['confirmations'] = [{'scope': 'workflow-method', 'source': 'direct-user-message', 'text': 'Automatic identification accepted'}]
        self.assertCode('schema.decisions')

    def test_outline_shadow_labels_and_native_values_are_both_checked(self):
        self.text_decision['effect'] = 'outline'
        self.assertCode('presentation.text_effect')
        self.text_decision['outline']['size'] = 2
        self.assertCode('presentation.native_mismatch')
        self.text['properties']['font']['outlineSettings']['outlineSize'] = 2
        self.assertEqual([], self.check()['issues'])
        self.text['properties']['shadowColorAndOpacity']['a'] = 1
        self.assertCode('presentation.native_mismatch')

    def test_family_relations_are_explicit_reciprocal_and_checked(self):
        other = copy.deepcopy(self.icon); other['widgetName'] = 'ImgPeer'
        self.snapshot['assets'][0]['widgets'].append(other)
        item = copy.deepcopy(self.image); item['widgetName'] = 'ImgPeer'
        self.image['familyId'] = item['familyId'] = 'level-plates'
        self.decisions['presentationReview']['images'].append(item)
        self.request['references'][0]['regions'][0]['widgetNames'].append('ImgPeer')
        self.assertCode('presentation.family')
        self.decisions['presentationReview']['families'] = [{'id': 'level-plates',
            'members': [{'assetPath': ASSET, 'widgetName': n} for n in ('ImgIcon', 'ImgPeer')],
            'comparisons': ['brush-size', 'source-scale', 'slot-size', 'aspect-mode'], 'reason': 'Explicit synthetic family', 'exceptions': []}]
        self.assertEqual([], self.check()['issues'])
        other['properties']['brush']['imageSize'] = {'x': 44, 'y': 22}
        other['slot']['properties']['layoutData']['offsets'].update(right=44, bottom=22)
        self.assertCode('presentation.family_mismatch')

    def test_family_single_axis_and_exact_member_exceptions(self):
        other = copy.deepcopy(self.icon); other['widgetName'] = 'ImgPeer'
        self.snapshot['assets'][0]['widgets'].append(other)
        item = copy.deepcopy(self.image); item['widgetName'] = 'ImgPeer'
        self.image['familyId'] = item['familyId'] = 'plates'
        item['aspectMode'] = self.image['aspectMode'] = 'stretch'
        self.decisions['presentationReview']['images'].append(item)
        self.request['references'][0]['regions'][0]['widgetNames'].append('ImgPeer')
        other['properties']['brush']['imageSize']['x'] = 60
        family = {'id': 'plates', 'members': [{'assetPath': ASSET, 'widgetName': n} for n in ('ImgIcon', 'ImgPeer')],
            'comparisons': ['brush-height'], 'reason': 'Equal height, intentionally different width', 'exceptions': []}
        self.decisions['presentationReview']['families'] = [family]
        self.assertEqual([], self.check()['issues'])
        family['comparisons'] = ['brush-width']
        self.assertCode('presentation.family_mismatch')
        exception = {'assetPath': ASSET, 'widgetName': 'ImgPeer', 'comparison': 'brush-width',
            'expectedValue': 60, 'reason': 'Explicit longer peer backplate'}
        family['exceptions'] = [exception]
        self.assertEqual([], self.check()['issues'])
        exception['expectedValue'] = 61
        self.assertCode('presentation.family_mismatch')
        exception['expectedValue'] = 40
        self.assertCode('presentation.family_exception')

    def test_family_exceptions_cannot_be_unknown_duplicate_or_blanket(self):
        self.test_family_single_axis_and_exact_member_exceptions()
        family = self.decisions['presentationReview']['families'][0]
        exception = family['exceptions'][0]; exception['expectedValue'] = 60
        exception['widgetName'] = 'Missing'
        self.assertCode('presentation.family_exception')
        exception['widgetName'] = 'ImgPeer'; family['exceptions'].append(copy.deepcopy(exception))
        self.assertCode('presentation.family_exception')
        family['exceptions'].pop(); exception['expectedValue'] = 'any'
        self.assertCode('schema.decisions')

    def test_plan_apply_noop_and_cas_keep_optin_evidence(self):
        self.plan([self.fx.op]); editor = FakeEditor(self.snapshot)
        self.assertTrue(self.fx.apply(editor)['changed'])
        self.assertFalse(self.fx.apply(editor)['changed'])
        self.assertEqual(['opacity'], editor.calls)
        self.assertEqual(1, editor.saves)
        editor.value['assets'][0]['widgets'][1]['properties']['renderOpacity'] = .7
        self.assertCode('execution.stale_baseline', lambda: self.fx.apply(editor))

    def test_interrupted_optin_execution_recovers_without_extra_mutation(self):
        self.plan([self.fx.op]); editor = FakeEditor(self.snapshot); editor.crash_after_apply = True
        with self.assertRaises(RuntimeError): self.fx.apply(editor)
        self.fx.apply(editor)
        self.assertEqual(['opacity'], editor.calls)

    def test_completed_add_rerun_does_not_create_extra_node(self):
        added = copy.deepcopy(self.icon); added['widgetName'] = 'ImgAdded'
        op = {'id': 'add-static', 'kind': 'add-widget', 'assetPath': ASSET, 'widgetName': 'ImgAdded',
            'before': None, 'after': added, 'sourceElementId': 'element.added'}
        self.fx.locked[(ASSET, 'ImgAdded')] = {'classPath': added['classPath'], 'parentWidgetName': 'PanelRoot',
            'isVariable': False, 'properties': {}, 'slot': {}, 'requirementRefs': ['element.added']}
        item = copy.deepcopy(self.image); item['widgetName'] = 'ImgAdded'
        self.decisions['presentationReview']['images'].append(item)
        self.request['references'][0]['regions'][0]['widgetNames'].append('ImgAdded')
        self.plan([op]); editor = FakeEditor(self.snapshot)
        self.fx.apply(editor); self.fx.apply(editor)
        self.assertEqual(4, len(editor.value['assets'][0]['widgets']))
        self.assertEqual(['add-static'], editor.calls)
        self.assertEqual(1, editor.saves)

    def test_explicit_local_removal_excludes_only_the_removed_identity(self):
        self.request['scope'] = [{'assetPath': ASSET, 'widgetNames': ['ImgIcon']}]
        self.request['target'] = {k: self.request['baseline'][k] for k in ('requirement', 'bundle')}
        self.decisions['presentationReview'] = {'version': 1, 'images': [], 'texts': [], 'families': []}
        self.fx.locked.pop((ASSET, 'ImgIcon'))
        op = {'id': 'remove-static', 'kind': 'remove-widget', 'assetPath': ASSET, 'widgetName': 'ImgIcon',
            'before': copy.deepcopy(self.icon), 'after': None, 'sourceElementId': 'element.icon'}
        self.assertEqual('ready', self.plan([op])['status'])
        self.request['scope'][0]['widgetNames'].append('UndeclaredMissing')
        self.assertCode('presentation.scope', lambda: self.plan([op]))

    def test_packets_remind_per_text_review_and_geometry_boundary(self):
        output = (self.root.parent/(self.root.name+'-packets')).resolve()
        self.assertEqual(self.root.resolve().parent, output.parent)
        self.assertEqual(self.root.name+'-packets', output.name)
        import shutil
        self.addCleanup(lambda: shutil.rmtree(output) if output.is_dir() else None)
        result = pipeline.prepare_packets(self.root/'request.json', output)
        packet_path = common.bound_path(result['packets'][0], self.root/'receipt.json')
        packet = common.load_json(packet_path)
        self.assertIn('effect-type confidence', packet['presentationReview']['textChecks'])

    def test_verify_emits_pending_geometry_even_with_canonical_capture(self):
        self.plan(); editor = FakeEditor(self.snapshot); self.fx.apply(editor)
        execution = common.load_json(self.root/'checkpoint.json')
        capture = {'kind': 'nextgame-ui-art-capture', 'version': 1, 'assetPath': ASSET,
            'context': self.request['references'][0]['context'], 'snapshotSha256': execution['readback']['sha256'],
            'image': common.binding(self.root/'reference.png'), 'capturedAt': common.utc_now(),
            'acquisition': {'method': 'nxue-agent', 'fallbackReason': 'SYNTHETIC TEST ONLY; no Editor capture'}, 'canonical': True}
        self.fx.write('capture.json', capture)
        self.fx.write('captures.json', [{'referenceId': 'icon-default', 'capture': common.binding(self.root/'capture.json')}])
        with patch.object(pipeline, 'validate_authority'):
            result = pipeline.verify_plan(self.root/'plan.json', self.root/'checkpoint.json', self.root/'captures.json', self.root/'verification.json')
        self.assertEqual('needs-review', result['status'])
        checks = common.load_json(self.root/'verification.json')['checks']
        self.assertTrue(any(c['status'] == 'pending' and c['id'].endswith(':geometry') for c in checks))


if __name__ == '__main__':
    unittest.main()
