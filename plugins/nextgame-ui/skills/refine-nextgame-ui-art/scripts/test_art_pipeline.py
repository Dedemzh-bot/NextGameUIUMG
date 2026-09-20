"""Synthetic executor regressions. No Unreal connection or production asset writes."""
import copy
import json
import shutil
import struct
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import art_common as common
import art_pipeline as pipeline


ASSET = '/Game/UI/UMG/Test/uw_test_icon'


def snapshot():
    return {'kind':'nextgame-ui-art-snapshot','version':1,'capturedAt':common.utc_now(),
        'acquisition':{'method':'fixture'},'assets':[{'assetPath':ASSET,'parentClassPath':'/Script/UMG.UserWidget',
        'designSizeMode':'Desired','referencesDigest':'a'*64,'referencesComplete':True,'protectedReferences':['TxtValue'],
        'widgets':[
            {'widgetName':'PanelRoot','classPath':'/Script/UMG.CanvasPanel','parentWidgetName':None,'isVariable':False,
             'properties':{'visibility':'SelfHitTestInvisible'},'slot':{'classPath':None,'properties':{}}},
            {'widgetName':'ImgIcon','classPath':'/Script/UIFramework.GameImage','parentWidgetName':'PanelRoot','isVariable':False,
             'properties':{'visibility':'SelfHitTestInvisible','renderOpacity':1.0},'slot':{'classPath':'/Script/UMG.CanvasPanelSlot',
                'properties':{'zOrder':0,'layoutData':{'offsets':{'left':0,'top':0,'right':32,'bottom':32}}}}},
            {'widgetName':'TxtValue','classPath':'/Script/UMG.TextBlock','parentWidgetName':'PanelRoot','isVariable':True,
             'properties':{'visibility':'SelfHitTestInvisible','font':{'size':20}},'slot':{'classPath':'/Script/UMG.CanvasPanelSlot','properties':{}}}]}]}


class FakeEditor:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.calls = []
        self.saves = 0
        self.crash_after_apply = False
    def snapshot(self, paths):
        result = copy.deepcopy(self.value)
        result['capturedAt'] = common.utc_now()
        return result
    def execute(self, operation):
        self.value = common.advance_snapshot(self.value, operation)
        self.calls.append(operation['id'])
        if self.crash_after_apply:
            self.crash_after_apply = False
            raise RuntimeError('simulated lost response after mutation')
    def compile_save(self, paths):
        self.saves += 1


class BatchFakeEditor(FakeEditor):
    """Synthetic transport evidence, explicitly unrelated to production receipts."""
    def __init__(self, value):
        super().__init__(value)
        self.snapshots = 0
        self.batches = []
        self.lose_after = None
        self.fail_at = None
        self.false_changes = False
        self.concurrent = False
        self.save_changes = False
    def snapshot(self, paths):
        self.snapshots += 1
        return super().snapshot(paths)
    def execute_batch(self, operations):
        self.batches.append([o['id'] for o in operations])
        tree = {'widgets': [{'widgetName': w['widgetName'],
            'widget': {'refPath': 'fixture:' + w['widgetName']},
            'slot': {'refPath': 'fixture:slot:' + w['widgetName']}} for w in self.value['assets'][0]['widgets']]}
        result = {'kind': 'nextgame-ui-art-set-batch-result', 'version': 1, 'status': 'completed',
            'results': [], 'referenceTrees': [{'assetPath': ASSET, 'tree': tree}]}
        for index, op in enumerate(operations):
            if self.lose_after == index:
                self.lose_after = None
                raise RuntimeError('lost transport reply')
            node = next(w for w in self.value['assets'][0]['widgets'] if w['widgetName'] == op['widgetName'])
            props = node['slot']['properties'] if op['kind'] == 'set-slot' else node['properties']
            row = {'operationId': op['id'], 'assetPath': op['assetPath'], 'widgetName': op['widgetName'],
                'property': op['property'], 'instance': {'refPath': ('fixture:slot:' if op['kind'] == 'set-slot' else 'fixture:') + op['widgetName']},
                'propertySchema': {'type': 'number'}, 'before': {op['property']: copy.deepcopy(props[op['property']])},
                'after': None, 'setResult': True, 'status': 'passed', 'stage': 'complete', 'error': None}
            failed = self.fail_at == index
            if not failed or self.false_changes:
                self.value = common.advance_snapshot(self.value, op)
                self.calls.append(op['id'])
            node = next(w for w in self.value['assets'][0]['widgets'] if w['widgetName'] == op['widgetName'])
            props = node['slot']['properties'] if op['kind'] == 'set-slot' else node['properties']
            row['after'] = {op['property']: copy.deepcopy(props[op['property']])}
            result['results'].append(row)
            if failed:
                row.update(setResult=False, status='failed', stage='after', error='synthetic setter false')
                result['status'] = 'failed'; self.fail_at = None
                return result
        if self.concurrent:
            self.value['assets'][0]['widgets'][0]['properties']['visibility'] = 'Collapsed'
        if self.lose_after == len(operations):
            self.lose_after = None
            raise RuntimeError('lost transport reply')
        return result
    def compile_save(self, paths):
        super().compile_save(paths)
        if self.save_changes:
            self.value['assets'][0]['widgets'][0]['properties']['visibility'] = 'Collapsed'


class ArtPipelineTests(unittest.TestCase):
    def setUp(self):
        self.root = common.PLUGIN_ROOT.parent / 'test-runs' / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.initial = snapshot()
        self.write('snapshot.json', self.initial)
        self.write('requirement.json', {'requestId':'test-art','reviewGate':{'status':'accepted'}})
        self.write('bundle.json', {'assets':[{'assetPath':ASSET,'assetKind':'child-widget'}]})
        self.write('readback.json', {})
        Image.new('RGBA',(32,32),(255,0,0,255)).save(self.root/'reference.png')
        self.request = {'kind':'nextgame-ui-art-request','version':1,'requestId':'test-art','goal':'upgrade-art',
            'originalText':'SYNTHETIC TEST: refine one icon', 'scope':[{'assetPath':ASSET,'widgetNames':['ImgIcon']}],
            'baseline':{k:common.binding(self.root/(k+'.json')) for k in ('requirement','bundle','readback','snapshot')},
            'references':[{'id':'icon-default','assetPath':ASSET,'image':common.binding(self.root/'reference.png'),
                'context':{'size':[32,32],'dpiScale':1,'locale':'zh-CN','dataId':'fixture','stateId':'default',
                    'fontSetDigest':'b'*64,'background':[0,0,0,0]},
                'regions':[{'id':'icon','bounds':[0,0,32,32],'widgetNames':['ImgIcon']}]}],
            'resourceDir':str(self.root),'productionAuthorized':True,
            'budget':{'maxCorrectionRounds':2,'maxModelCalls':8,'tokenLimits':{}}}
        self.write('request.json', self.request)
        self.op = {'id':'opacity','kind':'set-property','assetPath':ASSET,'widgetName':'ImgIcon',
                   'property':'renderOpacity','before':1.0,'after':0.5,'sourceElementId':'element.icon'}
        self.locked = {(ASSET,'ImgIcon'):{'classPath':'/Script/UIFramework.GameImage','parentWidgetName':'PanelRoot',
             'isVariable':False,'properties':{},'slot':{},'requirementRefs':['element.icon']}}
        self.source_patch = patch.object(pipeline, '_source_nodes', return_value=self.locked)
        self.source_patch.start()
    def tearDown(self):
        self.source_patch.stop()
        resolved = self.root.resolve()
        assert resolved.is_relative_to(common.PLUGIN_ROOT.parent / 'test-runs')
        shutil.rmtree(resolved)
    def write(self, name, value):
        path = self.root/name
        common.write_json(path,value,replace=True)
        return path
    def plan(self, operations=None, resolution='unambiguous'):
        decisions={'kind':'nextgame-ui-art-decisions','version':1,'requestSha256':common.sha256(self.root/'request.json'),
            'decisions':[{'operation':o,'evidence':'synthetic regression evidence','resolution':resolution} for o in (operations if operations is not None else [self.op])]}
        self.write('decisions.json',decisions)
        result=pipeline.create_plan(self.root/'request.json',self.root/'decisions.json',validate_sources=False)
        self.write('plan.json',result)
        return result
    def apply(self, editor):
        return pipeline.apply_plan(self.root/'plan.json',self.root/'checkpoint.json',editor,validate_sources=False)

    def batch_ops(self):
        return [copy.deepcopy(self.op), dict(self.op, id='z', kind='set-slot', property='zOrder', before=0, after=3),
                dict(self.op, id='visibility', property='visibility', before='SelfHitTestInvisible', after='Hidden')]

    def test_batch_success_three_snapshots_and_readonly_replay(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial)
        self.assertEqual('completed', self.apply(editor)['status'])
        self.assertEqual(3, editor.snapshots)
        self.assertEqual([['opacity', 'z', 'visibility']], editor.batches)
        checkpoint = common.load_json(self.root/'checkpoint.json')
        receipt = common.read_bound(checkpoint['batchReceipts'][0], self.root/'checkpoint.json')
        self.assertEqual('official-result', receipt['mode'])
        self.assertEqual(['opacity', 'z', 'visibility'], receipt['completedIds'])
        self.assertFalse(self.apply(editor)['changed'])
        self.assertEqual(1, editor.saves); self.assertEqual(1, len(editor.batches))

    def test_batch_lost_reply_recovers_each_actual_prefix(self):
        for count in range(4):
            with self.subTest(count=count):
                cp = self.root/'checkpoint.json'
                if cp.exists(): cp.unlink()
                self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial); editor.lose_after = count
                with self.assertRaisesRegex(RuntimeError, 'lost transport'): self.apply(editor)
                self.assertEqual('completed', self.apply(editor)['status'])
                self.assertEqual(['opacity', 'z', 'visibility'], editor.calls)
                checkpoint = common.load_json(cp)
                receipt = common.read_bound(checkpoint['batchReceipts'][0], cp)
                self.assertEqual('actual-prefix-recovery', receipt['mode'])
                self.assertNotIn('result', receipt)
                self.assertEqual(count, len(receipt['completedIds']))

    def test_batch_saved_result_survives_checkpoint_update_interruption(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial)
        editor.fail_at = 1; editor.false_changes = True
        original = pipeline.write_json
        def interrupted(path, value, **kwargs):
            if Path(path).name == 'checkpoint.json' and value.get('currentBatch', {}).get('result'):
                raise KeyboardInterrupt('result durable, checkpoint update interrupted')
            return original(path, value, **kwargs)
        with patch.object(pipeline, 'write_json', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): self.apply(editor)
        cp = common.load_json(self.root/'checkpoint.json')
        self.assertNotIn('result', cp['currentBatch'])
        self.assertTrue(Path(cp['currentBatch']['resultPath']).is_file())
        with self.assertRaisesRegex(common.ArtError, 'contradicts real setter'): self.apply(editor)
        self.assertEqual(0, editor.saves)

    def test_legacy_last_operation_recovery_survives_compile_failure(self):
        self.plan(); editor = FakeEditor(self.initial); editor.crash_after_apply = True
        with self.assertRaises(RuntimeError): self.apply(editor)
        with patch.object(editor, 'compile_save', side_effect=RuntimeError('compile fails')):
            with self.assertRaisesRegex(RuntimeError, 'compile fails'): self.apply(editor)
        cp = common.load_json(self.root/'checkpoint.json')
        self.assertEqual(['opacity'], cp['completedIds']); self.assertIsNone(cp['currentOperation'])
        self.assertEqual('completed', self.apply(editor)['status'])
        self.assertEqual(['opacity'], editor.calls)

    def test_batch_stale_baseline_never_dispatches(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial)
        editor.value['assets'][0]['widgets'][1]['properties']['renderOpacity'] = .7
        with self.assertRaisesRegex(common.ArtError, 'Actual Unreal state changed'): self.apply(editor)
        self.assertEqual([], editor.batches)

    def test_batch_unrelated_concurrent_change_is_not_a_prefix(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial); editor.concurrent = True
        with self.assertRaisesRegex(common.ArtError, 'uniquely match'): self.apply(editor)
        self.assertEqual(0, editor.saves)
        with self.assertRaisesRegex(common.ArtError, 'uniquely match'): self.apply(editor)
        self.assertEqual(1, len(editor.batches))

    def test_batch_false_setter_that_changes_value_never_passes_recovery(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial)
        editor.fail_at = 1; editor.false_changes = True
        with self.assertRaisesRegex(common.ArtError, 'contradicts real setter'): self.apply(editor)
        cp = common.load_json(self.root/'checkpoint.json')
        report = common.read_bound(cp['currentBatch']['result'], self.root/'checkpoint.json')
        self.assertIs(False, report['results'][-1]['setResult'])
        with self.assertRaisesRegex(common.ArtError, 'contradicts real setter'): self.apply(editor)
        self.assertEqual(0, editor.saves)

    def test_batch_known_failure_records_only_true_prefix_and_stops(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial); editor.fail_at = 1
        with self.assertRaisesRegex(common.ArtError, 'stopped at a failed'): self.apply(editor)
        cp = common.load_json(self.root/'checkpoint.json')
        self.assertEqual(['opacity'], cp['completedIds']); self.assertIsNone(cp['currentBatch'])
        self.assertEqual(0, editor.saves)
        self.assertEqual('completed', self.apply(editor)['status'])
        self.assertEqual(['opacity', 'z', 'visibility'], editor.calls)

    def test_batch_postsave_full_state_is_still_required(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial); editor.save_changes = True
        with self.assertRaisesRegex(common.ArtError, 'Post-save actual'): self.apply(editor)
        self.assertEqual('failed', common.load_json(self.root/'checkpoint.json')['status'])

    def test_batch_real_receipt_tamper_is_rejected_on_replay(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial); self.apply(editor)
        cp = common.load_json(self.root/'checkpoint.json'); receipt = common.read_bound(cp['batchReceipts'][0], self.root/'checkpoint.json')
        result_path = Path(receipt['result']['path']); result = common.load_json(result_path)
        result['results'][0]['setResult'] = False; common.write_json(result_path, result, replace=True)
        with self.assertRaises(common.ArtError): self.apply(editor)
        self.assertEqual(1, editor.saves)

    def test_batch_legacy_active_operation_recovers_before_batch(self):
        operations = self.batch_ops(); self.plan(operations)
        editor = FakeEditor(self.initial); editor.crash_after_apply = True
        with self.assertRaises(RuntimeError): self.apply(editor)
        batch = BatchFakeEditor(editor.value)
        self.assertEqual('completed', self.apply(batch)['status'])
        self.assertEqual(['z', 'visibility'], batch.calls)
        self.assertEqual([['z', 'visibility']], batch.batches)

    def test_batch_duplicate_property_and_float32_noop_fall_back(self):
        operations = [self.op, dict(self.op, id='opacity2', before=.5, after=.25)]
        self.plan(operations); editor = BatchFakeEditor(self.initial); self.apply(editor)
        self.assertEqual([], editor.batches)
        near = dict(self.op, after=1.0 + 1e-9)
        self.assertEqual([], pipeline._set_batch([near, self.batch_ops()[1]], self.initial))

    def test_batch_ambiguous_intent_is_rejected_even_with_actual_match(self):
        operations = self.batch_ops(); self.plan(operations); editor = BatchFakeEditor(self.initial); editor.lose_after = 0
        with self.assertRaises(RuntimeError): self.apply(editor)
        cp = common.load_json(self.root/'checkpoint.json'); cp['currentBatch']['operationIds'] = ['z', 'opacity']
        self.write('checkpoint.json', cp)
        with self.assertRaisesRegex(common.ArtError, 'exact next plan'): self.apply(editor)

    def test_batch_unknown_intent_fields_remain_closed(self):
        self.plan(self.batch_ops()); editor = BatchFakeEditor(self.initial); editor.lose_after = 0
        with self.assertRaises(RuntimeError): self.apply(editor)
        cp = common.load_json(self.root/'checkpoint.json'); cp['currentBatch']['skipCAS'] = True
        self.write('checkpoint.json', cp)
        with self.assertRaises(common.ArtError): self.apply(editor)

    def test_developer_goal_does_not_require_art_inputs(self):
        self.assertFalse(pipeline.route('developer-only')['artRequired'])
        for goal in common.ART_GOALS:
            result=pipeline.route(goal)
            self.assertFalse(result['complete']); self.assertEqual(2,len(result['missing']))

    def test_unknown_fields_and_nonfinite_values_rejected(self):
        invalid=copy.deepcopy(self.request); invalid['surprise']=True
        with self.assertRaises(common.ArtError): common.validate(invalid,'request')
        invalid=copy.deepcopy(self.request); invalid['budget']['maxModelCalls']=float('nan')
        with self.assertRaises((common.ArtError,ValueError)): common.validate(invalid,'request')

    def test_apply_and_noop_rerun_do_not_duplicate_or_resave(self):
        self.plan(); editor=FakeEditor(self.initial)
        self.assertTrue(self.apply(editor)['changed'])
        self.assertFalse(self.apply(editor)['changed'])
        self.assertEqual(['opacity'],editor.calls); self.assertEqual(1,editor.saves)

    def test_stale_actual_baseline_stops_before_mutation(self):
        self.plan(); editor=FakeEditor(self.initial)
        editor.value['assets'][0]['widgets'][1]['properties']['renderOpacity']=0.7
        with self.assertRaisesRegex(common.ArtError,'Actual Unreal state changed'): self.apply(editor)
        self.assertEqual([],editor.calls)

    def test_interrupted_mutation_recovers_from_actual_after_state(self):
        self.plan(); editor=FakeEditor(self.initial); editor.crash_after_apply=True
        with self.assertRaises(RuntimeError): self.apply(editor)
        result=self.apply(editor)
        self.assertEqual('completed',result['status']); self.assertEqual(['opacity'],editor.calls)

    def test_partial_unexpected_result_requires_recovery(self):
        self.plan(); editor=FakeEditor(self.initial); editor.crash_after_apply=True
        with self.assertRaises(RuntimeError): self.apply(editor)
        editor.value['assets'][0]['widgets'][1]['properties']['renderOpacity']=0.6
        with self.assertRaisesRegex(common.ArtError,'differs from both'): self.apply(editor)

    def test_finalization_crash_does_not_overwrite_immutable_readback(self):
        self.plan(); editor=FakeEditor(self.initial)
        real_write=pipeline.write_json
        failed=[False]
        def fail_completed(path,value,**kwargs):
            if Path(path).name=='checkpoint.json' and value.get('status')=='completed' and not failed[0]:
                failed[0]=True; raise OSError('simulated checkpoint persistence failure')
            return real_write(path,value,**kwargs)
        with patch.object(pipeline,'write_json',side_effect=fail_completed):
            with self.assertRaises(OSError): self.apply(editor)
        self.assertEqual('completed',self.apply(editor)['status'])
        self.assertEqual(['opacity'],editor.calls)

    def test_forged_plan_and_checkpoint_rejected(self):
        plan=self.plan(); plan['operations'][0]['after']=0.1; self.write('plan.json',plan)
        with self.assertRaisesRegex(common.ArtError,'reproduces'): self.apply(FakeEditor(self.initial))
        self.plan(); editor=FakeEditor(self.initial); self.apply(editor)
        checkpoint=common.load_json(self.root/'checkpoint.json'); checkpoint['completedIds']=['wrong']
        self.write('checkpoint.json',checkpoint)
        with self.assertRaisesRegex(common.ArtError,'contiguous'): self.apply(editor)

    def test_local_scope_and_runtime_properties_protected(self):
        op=copy.deepcopy(self.op); op['widgetName']='TxtValue'
        with self.assertRaisesRegex(common.ArtError,'scope'): self.plan([op])
        op=copy.deepcopy(self.op); op['property']='entryWidgetClass'
        with self.assertRaisesRegex(common.ArtError,'declared art'): self.plan([op])

    def test_locked_layout_requires_design_revision(self):
        self.locked[(ASSET,'ImgIcon')]['properties']['renderOpacity']=1.0
        with self.assertRaisesRegex(common.ArtError,'Revise and accept'): self.plan()

    def test_ambiguous_decisions_remain_nonexecutable(self):
        result=self.plan(resolution='unresolved')
        self.assertEqual('needs-review',result['status'])
        with self.assertRaisesRegex(common.ArtError,'Resolve'): self.apply(FakeEditor(self.initial))

    def test_unknown_designer_mode_is_diagnostic_only(self):
        value=copy.deepcopy(self.initial); value['assets'][0]['designSizeMode']=None
        self.write('snapshot.json',value); self.request['baseline']['snapshot']=common.binding(self.root/'snapshot.json')
        self.write('request.json',self.request)
        with self.assertRaisesRegex(common.ArtError,'Designer mode'): self.plan()

    def test_static_add_can_preserve_unknown_references(self):
        value=copy.deepcopy(self.initial); value['assets'][0]['referencesComplete']=False
        node=copy.deepcopy(value['assets'][0]['widgets'][1]); node['widgetName']='ImgExtra'
        op={'id':'add','kind':'add-widget','assetPath':ASSET,'widgetName':'ImgExtra','before':None,'after':node,'sourceElementId':'element.extra'}
        self.assertEqual(4,len(common.advance_snapshot(value,op)['assets'][0]['widgets']))
        op={'id':'remove','kind':'remove-widget','assetPath':ASSET,'widgetName':'ImgIcon',
            'before':value['assets'][0]['widgets'][1],'after':None,'sourceElementId':'element.icon'}
        with self.assertRaisesRegex(common.ArtError,'complete reference'): common.advance_snapshot(value,op)

    def test_protected_widget_cannot_be_removed(self):
        op={'id':'remove','kind':'remove-widget','assetPath':ASSET,'widgetName':'TxtValue',
            'before':self.initial['assets'][0]['widgets'][2],'after':None,'sourceElementId':'element.value'}
        with self.assertRaisesRegex(common.ArtError,'protected'): common.advance_snapshot(self.initial,op)

    def test_new_nodes_cannot_use_native_image_or_variable(self):
        node=copy.deepcopy(self.initial['assets'][0]['widgets'][1]); node['widgetName']='ImgExtra'
        op={'id':'add','kind':'add-widget','assetPath':ASSET,'widgetName':'ImgExtra','before':None,'after':node,'sourceElementId':'element.extra'}
        node['classPath']='/Script/UMG.Image'
        with self.assertRaises(common.ArtError): common.advance_snapshot(self.initial,op)

    def test_font_even_and_wrap_positive(self):
        for prop,value in [('font',{'size':21}),('wrapTextAt',0)]:
            op=copy.deepcopy(self.op); op.update(property=prop,after=value)
            with self.assertRaises(common.ArtError): common.check_operation(op)

    def test_correction_counter_cannot_be_claimed(self):
        self.plan()
        with self.assertRaisesRegex(common.ArtError,'previous verification'):
            pipeline.create_plan(self.root/'request.json',self.root/'decisions.json',round_number=1,validate_sources=False)

    def test_correction_rejects_unplanned_previous_state(self):
        self.plan(); editor=FakeEditor(self.initial); result=self.apply(editor)
        execution=common.load_json(self.root/'checkpoint.json')
        prior_snapshot=common.load_json(result['readback']['path'])
        prior_snapshot['assets'][0]['widgets'][1]['properties']['renderOpacity']=0.8
        wrong=self.write('unexpected-state.json',prior_snapshot)
        execution['readback']=common.binding(wrong); self.write('checkpoint.json',execution)
        placeholder=self.write('placeholder.json',{})
        previous={'kind':'nextgame-ui-art-verification','version':1,'plan':common.binding(self.root/'plan.json'),
            'snapshot':common.binding(wrong),'execution':common.binding(self.root/'checkpoint.json'),
            'visualReview':common.binding(placeholder),'comparisons':[common.binding(placeholder)],'status':'needs-review',
            'checks':[{'id':'pending','status':'pending','details':'synthetic'}],'verifiedAt':common.utc_now()}
        self.write('previous.json',previous)
        self.write('correction-decisions.json',{'kind':'nextgame-ui-art-decisions','version':1,
            'requestSha256':common.sha256(self.root/'request.json'),'decisions':[]})
        with self.assertRaisesRegex(common.ArtError,'exact completed previous plan'):
            pipeline.create_plan(self.root/'request.json',self.root/'correction-decisions.json',
                previous_verification_path=self.root/'previous.json',validate_sources=False)

    def test_original_source_change_invalidates_binding(self):
        self.plan(); self.write('snapshot.json',{'changed':True})
        with self.assertRaisesRegex(common.ArtError,'changed bound file'): self.apply(FakeEditor(self.initial))

    def test_output_refuses_plugin_or_evidence_overwrite(self):
        with self.assertRaises(common.ArtError): common.write_json(common.SKILL_ROOT/'runtime.json',{})
        with self.assertRaises(common.ArtError): common.write_json(self.root/'request.json',{})

    def test_float_state_matches_engine_float32_storage(self):
        before=copy.deepcopy(self.initial); after=copy.deepcopy(before)
        before['assets'][0]['widgets'][1]['properties']['renderOpacity']=0.6
        after['assets'][0]['widgets'][1]['properties']['renderOpacity']=struct.unpack('f',struct.pack('f',0.6))[0]
        self.assertEqual(common.state_hash(before),common.state_hash(after))

    def test_reference_pixel_dimensions_and_asset_coverage_required(self):
        self.request['references'][0]['context']['size']=[64,32]
        self.write('request.json',self.request)
        with self.assertRaisesRegex(common.ArtError,'Reference pixels'): self.plan()
        self.request['references'][0]['context']['size']=[32,32]
        self.request['references'][0]['assetPath']='/Game/UI/UMG/Test/uw_test_other'
        self.write('request.json',self.request)
        with self.assertRaises(common.ArtError): self.plan()

    def test_full_screen_requires_base_wider_and_taller_references(self):
        self.write('bundle.json',{'assets':[{'assetPath':ASSET,'assetKind':'screen'}]})
        self.request['baseline']['bundle']=common.binding(self.root/'bundle.json')
        self.write('request.json',self.request)
        with self.assertRaisesRegex(common.ArtError,'2560'): self.plan()

    def packet(self):
        return self.write('packet.json',{'requestSha256':common.sha256(self.root/'request.json'),
            'images':[common.binding(self.root/'reference.png')]})

    def test_call_reservation_is_idempotent_and_has_hard_call_limit(self):
        self.request['budget']['maxModelCalls']=1; self.write('request.json',self.request)
        packet=self.packet(); journal=self.root/'calls.json'
        first=pipeline.reserve_call(self.root/'request.json',packet,journal,'region-1')
        self.assertTrue(first['dispatchAllowed']); self.assertEqual(0,first['actualModelCallsExecuted'])
        self.assertFalse(pipeline.reserve_call(self.root/'request.json',packet,journal,'region-1')['dispatchAllowed'])
        with self.assertRaisesRegex(common.ArtError,'budget exhausted'):
            pipeline.reserve_call(self.root/'request.json',packet,journal,'region-2')
        self.assertFalse(journal.with_suffix('.json.reserve-lock').exists())

    def test_token_budget_requires_actual_receipts_and_stops_at_limit(self):
        self.request['budget']['tokenLimits']={'inputTokens':10}; self.write('request.json',self.request)
        packet=self.packet(); journal=self.root/'calls.json'
        first=pipeline.reserve_call(self.root/'request.json',packet,journal,'region-1')
        with self.assertRaisesRegex(common.ArtError,'provider usage receipts'):
            pipeline.reserve_call(self.root/'request.json',packet,journal,'region-2')
        sys.path.insert(0,str(common.PLUGIN_ROOT/'scripts'))
        import token_telemetry as telemetry
        ledger=self.root/'tokens.json'
        event=telemetry.make_model_call_event('synthetic','art','judge',provider='fixture',model='fixture',
            agent_role='art-judgment',token_source='provider-receipt',
            measurement_boundary_id=first['measurementBoundaryId'],run_id_digest=first['runIdDigest'],
            call_id_digest=first['callIdDigest'],usage_receipt_sha256='f'*64,
            not_applicable_metrics=['cachedInputTokens','reasoningTokens','visionTokens'],inputTokens=10,outputTokens=1)
        telemetry.append_event(ledger,event)
        with self.assertRaises(common.ArtError):
            pipeline.reserve_call(self.root/'request.json',packet,journal,'region-2',ledger)
        self.assertEqual(1,len(common.load_json(journal)['calls']))

    def test_zero_budget_and_proxy_limit_names_cannot_dispatch(self):
        self.request['budget']['tokenLimits']={'inputTokens':0}; self.write('request.json',self.request)
        with self.assertRaisesRegex(common.ArtError,'zero remaining'):
            pipeline.reserve_call(self.root/'request.json',self.packet(),self.root/'calls.json','region-1')
        self.request['budget']['tokenLimits']={'tokenizerProxyTokens':100}
        with self.assertRaises(common.ArtError): common.validate(self.request,'request')

    def test_packets_reuse_intact_cache_and_repair_corrupt_image(self):
        cuts=self.root/'cuts'; cuts.mkdir(); shutil.copyfile(self.root/'reference.png',cuts/'icon.png')
        self.request['resourceDir']=str(cuts); self.write('request.json',self.request)
        output=self.root/'packets'
        first=pipeline.prepare_packets(self.root/'request.json',output)
        self.assertEqual(1,first['newPackets'])
        self.assertEqual(1,pipeline.prepare_packets(self.root/'request.json',output)['reusedPackets'])
        packet=common.load_json(first['packets'][0]['path'])
        Path(packet['images'][0]['path']).write_bytes(b'corrupt cache')
        repaired=pipeline.prepare_packets(self.root/'request.json',output)
        self.assertEqual(1,repaired['newPackets'])
        self.request['originalText']='SYNTHETIC revised scope'; self.write('request.json',self.request)
        fresh=pipeline.prepare_packets(self.root/'request.json',output)
        self.assertNotEqual(first['packets'],fresh['packets'])
        self.assertEqual(0,fresh['modelCallsExecuted'])


if __name__=='__main__': unittest.main()
