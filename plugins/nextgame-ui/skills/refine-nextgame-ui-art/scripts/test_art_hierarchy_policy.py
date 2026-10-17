"""Synthetic ownership guard regressions, never production acceptance evidence."""
import copy
import unittest
from unittest.mock import patch

import art_common as common
import art_pipeline as pipeline
import test_art_pipeline as fixtures


ASSET = fixtures.ASSET


class HierarchyPolicyTests(unittest.TestCase):
    write = fixtures.ArtPipelineTests.write
    plan = fixtures.ArtPipelineTests.plan
    apply = fixtures.ArtPipelineTests.apply
    batch_ops = fixtures.ArtPipelineTests.batch_ops
    tearDown = fixtures.ArtPipelineTests.tearDown

    def setUp(self):
        fixtures.ArtPipelineTests.setUp(self)
        self.request['capabilities'] = ['preserve-hierarchy/1']
        self.write('request.json', self.request)

    def test_geometry_and_visual_changes_keep_existing_gates_and_replay(self):
        plan = self.plan(self.batch_ops())
        self.assertEqual('ready', plan['status'])
        editor = fixtures.FakeEditor(self.initial)
        self.assertEqual('completed', self.apply(editor)['status'])
        self.assertEqual(
            [(w['widgetName'], w['parentWidgetName']) for w in self.initial['assets'][0]['widgets']],
            [(w['widgetName'], w['parentWidgetName']) for w in editor.value['assets'][0]['widgets']])
        self.assertFalse(self.apply(editor)['changed'])
        self.assertEqual(1, editor.saves)

    def test_existing_locked_value_is_not_waived(self):
        self.locked[(ASSET, 'ImgIcon')]['properties']['renderOpacity'] = 1
        with self.assertRaisesRegex(common.ArtError, 'locked value'):
            self.plan()

    def test_no_structural_operation_even_with_target_revision(self):
        request = dict(self.request, target={})
        for kind in ('add-widget', 'remove-widget', 'reparent-widget'):
            with self.subTest(kind=kind):
                with self.assertRaises(common.ArtError) as error:
                    pipeline._check_design(dict(self.op, kind=kind), self.locked, request)
                self.assertEqual('design.hierarchy_preserved', error.exception.code)

    def test_unresolved_reparent_is_rejected_before_simulation(self):
        op = dict(self.op, kind='reparent-widget', property='parentWidgetName',
                  before='PanelRoot', after='TxtValue')
        with self.assertRaises(common.ArtError) as error:
            self.plan([op], resolution='unresolved')
        self.assertEqual('design.hierarchy_preserved', error.exception.code)

    def test_new_class_is_not_a_generic_property_write(self):
        with self.assertRaises(common.ArtError):
            self.plan([dict(self.op, property='classPath',
                            before='/Script/UMG.Image', after='/Script/UIFramework.GameImage')])

    def test_legacy_request_keeps_its_interpretation(self):
        legacy = copy.deepcopy(self.request)
        legacy.pop('capabilities')
        common.validate(legacy, 'request')
        pipeline.check_hierarchy_policy(legacy, dict(self.op, kind='add-widget'))

    def test_unknown_capability_rejected(self):
        request = dict(self.request, capabilities=['preserve-hierarchy/2'])
        with self.assertRaises(common.ArtError):
            common.validate(request, 'request')

    def test_initializer_adoption_is_explicit_and_boolean(self):
        job = {key: copy.deepcopy(self.request[key])
               for key in ('goal', 'originalText', 'scope', 'references', 'resourceDir', 'budget')}
        job['baseline'] = {key: value['path'] for key, value in self.request['baseline'].items()}
        for reference in job['references']:
            reference['image'] = reference['image']['path']
        job['authorizedAssetPaths'] = [ASSET]
        for value in (True, False, 'true', 1, None):
            with self.subTest(value=value):
                job['preserveHierarchy'] = value
                path = self.write('job.json', job)
                output = self.root / ('initialized-' + str(value) + '.json')
                with patch.object(pipeline, 'validate_authority'):
                    if type(value) is bool:
                        pipeline.initialize_request(path, output)
                        result = common.load_json(output)
                        self.assertEqual(value, 'preserve-hierarchy/1' in result['capabilities'])
                    else:
                        with self.assertRaises(common.ArtError) as error:
                            pipeline.initialize_request(path, output)
                        self.assertEqual('job.preserve_hierarchy', error.exception.code)


if __name__ == '__main__':
    unittest.main()
