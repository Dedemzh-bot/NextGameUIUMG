"""Synthetic evidence only: version selection and closed two-Custom graph guards."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import art_common as common
import art_materials as mat
import test_art_materials as legacy
import test_art_presentation as presentation
import test_art_presentation_integration as integration


class MulticolorMaterialTests(unittest.TestCase):
    sync = legacy.MaterialTests.sync
    check = legacy.MaterialTests.check
    fail = legacy.MaterialTests.fail
    row = legacy.MaterialTests.row
    prop = legacy.MaterialTests.prop

    def setUp(self):
        self.fx = presentation.PresentationTests(methodName='runTest')
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.root
        self.source, self.e, self.path, self.saved = legacy.fixture(self.root, version=2)
        self.fx.request['capabilities'].append(mat.MULTICOLOR_CAPABILITY)
        self.fx.request.pop('resourceCatalog')
        self.fx.image['source'] = self.source
        self.brush = self.fx.icon['properties']['brush']
        self.brush.update(resourceObject=copy.deepcopy(legacy.REF), imageSize={'x':96,'y':96},
                          mirroring='NoMirror', uVRegion={'bIsValid':False})
        self.fx.icon['slot']['properties']['layoutData']['offsets'].update(right=96, bottom=96)
        self.sync()

    def expression_call(self, tool, name):
        return next(c for c in self.e['calls'] if c['tool'] == tool and
                    c['arguments'].get('expression', {}).get('refPath', '').endswith(':' + name))

    def proof(self, **kwargs):
        return mat.validate_material_source(self.source, self.root/'decisions.json', legacy.PACKAGE,
                                            capability=mat.MULTICOLOR_CAPABILITY, **kwargs)

    def test_multicolor_graph_passes_existing_planning_entry(self):
        with patch('art_resources.validate_catalog', side_effect=AssertionError('No texture catalog')):
            result = self.check()
        self.assertTrue(all(c['status'] == 'passed' for c in result['checks']))
        proof = self.proof()
        self.assertEqual([96,96], proof['evaluationSize'])
        self.assertEqual(64, len(proof['graphSha256']))
        self.assertNotIn('frameSize', proof)
        self.assertEqual('ready', self.fx.plan()['status'])

    def test_both_complete_native_code_strings_are_bound_in_graph_hash(self):
        for name in ('Opacity', 'Color'):
            with self.subTest(name=name):
                before = self.proof()['graphSha256']
                row = self.row('get_properties', ':' + name)
                props = json.loads(row['result']['returnValue'])
                self.prop(':' + name, 'code', props['code'] + '\n// changed bound source')
                self.assertNotEqual(before, self.proof()['graphSha256'])

    def test_actual_geometry_stays_pending(self):
        self.assertTrue(any(c['status']=='pending' and c['id'].endswith(':geometry')
                            for c in self.check('actual')['checks']))

    def test_noop_apply_and_rerun(self):
        self.assertEqual('ready', self.fx.plan()['status'])
        editor = presentation.FakeEditor(self.fx.snapshot)
        self.fx.fx.apply(editor)
        self.assertFalse(self.fx.fx.apply(editor)['changed'])

    def test_missing_request_capability(self):
        self.fx.request['capabilities'].remove(mat.MULTICOLOR_CAPABILITY)
        self.fail('presentation.capability')

    def test_requires_presentation_capability(self):
        self.fx.request['capabilities'] = [mat.MULTICOLOR_CAPABILITY]
        self.fail('schema.request')

    def test_legacy_request_rejects_new_evidence(self):
        self.fx.request['capabilities'][-1] = mat.CAPABILITY
        self.fail('schema.proceduralMaterialReadback')

    def test_new_request_rejects_legacy_evidence(self):
        self.e['version'] = 1
        self.sync()
        self.fail('schema.proceduralMaterialReadbackV2')

    def test_both_capability_versions_rejected(self):
        self.fx.request['capabilities'].append(mat.CAPABILITY)
        self.fail('schema.request')

    def test_default_importable_entry_cannot_infer_new_version(self):
        with self.assertRaises(common.ArtError) as caught:
            mat.validate_material_source(self.source, self.root/'decisions.json', legacy.PACKAGE)
        self.assertEqual('schema.proceduralMaterialReadback', caught.exception.code)

    def test_unknown_direct_capability_rejected(self):
        with self.assertRaises(common.ArtError) as caught:
            mat.validate_material_source(self.source, self.root/'decisions.json', legacy.PACKAGE,
                                         capability='procedural-ui-material/3')
        self.assertEqual('material.capability', caught.exception.code)

    def test_closed_evidence(self):
        self.e['claimedVisualPass'] = True
        self.sync()
        self.fail('schema.proceduralMaterialReadbackV2')

    def test_legacy_constant_graph_cannot_be_relabelled(self):
        self.row('get_class', ':Color')['result']['returnValue']['refPath'] = mat.COLOR
        self.sync()
        self.fail('material.class')

    def test_two_scalar_outputs_rejected(self):
        self.prop(':Color', 'outputType', 'CMOT_Float1')
        self.fail('material.custom')

    def test_malformed_native_output_type_fails_closed(self):
        self.prop(':Color', 'outputType', {'unbound':'value'})
        self.fail('material.custom')

    def test_float4_mask_topology_is_not_implicitly_supported(self):
        self.prop(':Color', 'outputType', 'CMOT_Float4')
        self.fail('material.custom')

    def test_component_mask_expression_is_not_supported(self):
        self.row('get_class', ':Color')['result']['returnValue']['refPath'] = '/Script/Engine.MaterialExpressionComponentMask'
        self.sync()
        self.fail('material.class')

    def test_swapped_output_pins_rejected(self):
        for c in self.e['calls']:
            if c['tool'] == 'get_property_input':
                suffix = 'Color' if c['arguments']['material_property']=='MP_Opacity' else 'Opacity'
                c['result']['returnValue']['expression'] = {'refPath':legacy.REF['refPath']+':'+suffix}
        self.sync()
        self.fail('material.wiring')

    def test_each_custom_requires_complete_code(self):
        for name in ('Opacity', 'Color'):
            with self.subTest(name=name):
                original = copy.deepcopy(self.e)
                self.prop(':' + name, 'code', '')
                self.fail('material.custom')
                self.e = original
                self.sync()

    def test_each_custom_rejects_external_dependencies(self):
        cases = [('includeFilePaths', ['/Unbound.ush']), ('additionalDefines', [{'defineName':'OUTSIDE'}]),
                 ('additionalOutputs', [{'outputName':'Outside'}]), ('code', '#include "Unbound.ush"\nreturn 0;'),
                 ('inputs', [{'inputName':'UV'}, {'inputName':'External'}])]
        for name in ('Opacity', 'Color'):
            for key, value in cases:
                with self.subTest(name=name, property=key):
                    original = copy.deepcopy(self.e)
                    self.prop(':' + name, key, value)
                    self.fail('material.custom')
                    self.e = original
                    self.sync()

    def test_each_custom_requires_uv_graph_connection(self):
        for name in ('Opacity', 'Color'):
            with self.subTest(name=name):
                original = copy.deepcopy(self.e)
                self.expression_call('get_expression_inputs', name)['result']['returnValue'] = []
                self.sync()
                self.fail('material.wiring')
                self.e = original
                self.sync()

    def test_native_input_mask_rejected_even_when_graph_claims_uv(self):
        row = self.row('get_properties', ':Color')
        props = json.loads(row['result']['returnValue'])
        props['inputs'][0]['input']['maskR'] = 1
        self.prop(':Color', 'inputs', props['inputs'])
        self.fail('material.wiring')

    def test_unconnected_native_input_rejected(self):
        self.prop(':Color', 'inputs', [{'inputName':'UV'}])
        self.fail('material.wiring')

    def test_nondefault_output_pin_rejected(self):
        self.expression_call('get_expression_inputs', 'Color')['result']['returnValue'][0]['output_name']='R'
        self.sync()
        self.fail('material.wiring')

    def test_wrong_uv_input_name_rejected(self):
        self.expression_call('get_expression_inputs', 'Color')['result']['returnValue'][0]['input_name']='External'
        self.sync()
        self.fail('material.wiring')

    def test_extra_expression_rejected(self):
        self.row('get_expressions')['result']['returnValue'].append({'refPath':legacy.REF['refPath']+':Extra'})
        self.sync()
        self.fail('schema.proceduralMaterialReadbackV2')

    def test_extra_default_outputs_rejected(self):
        self.expression_call('get_expression_output_names', 'Color')['result']['returnValue'].append('A')
        self.sync()
        self.fail('material.wiring')

    def test_foreign_uv_graph_dependency_rejected(self):
        self.expression_call('get_expression_inputs', 'Color')['result']['returnValue'][0]['expression']={'refPath':'/Game/Outside.Outside:UV'}
        self.sync()
        self.fail('material.wiring')

    def test_fake_compile_success_rejected(self):
        self.row('recompile')['result']={'returnValue':True}
        self.sync()
        self.fail('schema.proceduralMaterialReadbackV2')

    def test_compile_projection_must_match_original_receipt(self):
        self.row('recompile')['completedAt']='2026-09-01T00:00:00.600000+00:00'
        self.sync()
        self.fail('material.execution_receipt')

    def test_failed_save_rejected(self):
        self.row('save_assets')['result']['returnValue']=False
        self.sync()
        self.fail('schema.proceduralMaterialReadbackV2')

    def test_stale_saved_bytes_rejected(self):
        self.saved.write_bytes(b'CHANGED')
        self.fail('binding.stale')

    def test_rebound_save_without_original_execution_rejected(self):
        self.saved.write_bytes(b'CHANGED')
        self.e['savedFile']=common.binding(self.saved)
        self.sync()
        self.fail('material.execution_receipt')

    def test_stale_readback_rejected(self):
        self.path.write_text('{}')
        self.fail('binding.stale')

    def test_missing_readback_call_rejected(self):
        self.e['calls'].pop(9)
        self.sync()
        self.fail('schema.proceduralMaterialReadbackV2')

    def test_unbound_code_edit_rejected(self):
        self.e['calls'][11]['result']['returnValue']='changed without source binding'
        common.write_json(self.path, self.e, replace=True)
        self.fail('binding.stale')

    def test_dirty_rejected(self):
        self.row('is_dirty')['result']['returnValue']=True
        self.sync()
        self.fail('schema.proceduralMaterialReadbackV2')

    def test_dirty_must_be_last_read(self):
        self.e['calls'][-1], self.e['calls'][-2]=self.e['calls'][-2], self.e['calls'][-1]
        for n, c in enumerate(self.e['calls']):
            c['startedAt']=f'2026-09-01T00:00:{n:02d}+00:00'
            c['completedAt']=f'2026-09-01T00:00:{n:02d}.500000+00:00'
        self.sync()
        self.fail('material.order')


class MulticolorFinalGateTests(unittest.TestCase):
    def test_final_bundle_readback_recompute_rejects_pending_and_forged_geometry(self):
        t=integration.PresentationIntegrationTests(methodName='runTest')
        t.setUp()
        self.addCleanup(t.doCleanups)
        t.enable()
        fx=t.fx
        item=fx.decisions['presentationReview']['images'][0]
        source,_,_,_=legacy.fixture(fx.art_dir, version=2)
        fx.request['capabilities'].append(mat.MULTICOLOR_CAPABILITY)
        item.update(source=source, aspectMode='preserve')
        node=next(w for a in fx.snapshot['assets'] if a['assetPath']==item['assetPath']
                  for w in a['widgets'] if w['widgetName']==item['widgetName'])
        node['properties']['brush'].update(resourceObject=legacy.REF, drawAs='Image', tiling='NoTile',
            mirroring='NoMirror', imageSize={'x':96,'y':96},
            margin={'left':0,'top':0,'right':0,'bottom':0}, uVRegion={'bIsValid':False})
        t.rebind()
        t.assertGatesReject('art.presentation_pending')
        for c in fx.verification['checks']:
            c['status']='passed'
        fx.flush()
        t.assertGatesReject('art.presentation_checks')


if __name__=='__main__':
    unittest.main()
