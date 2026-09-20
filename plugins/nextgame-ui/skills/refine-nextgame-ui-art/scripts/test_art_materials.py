"""Synthetic official-shaped material evidence; never real UE or approval."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import art_common as common
import art_materials as mat
import test_art_presentation as presentation
import test_art_presentation_integration as integration

PACKAGE='/Game/UI/UMG/Synthetic/Materials/M_Static'
REF={'refPath':PACKAGE+'.M_Static'}

def fixture(root, version=1):
    root=Path(root);project=root/'Synthetic.uproject';project.write_text('{"FileVersion":3,"Description":"SYNTHETIC TEST ONLY"}')
    saved=root/'Content/UI/UMG/Synthetic/Materials/M_Static.uasset';saved.parent.mkdir(parents=True,exist_ok=True)
    saved.write_bytes(b'SYNTHETIC TEST BYTES; NOT AN UNREAL ASSET')
    calls=[]
    def call(ts,tool,args,value):
        n=len(calls);calls.append({'toolset':ts,'tool':tool,'arguments':args,'result':value,
            'startedAt':f'2026-09-01T00:00:{n:02d}+00:00','completedAt':f'2026-09-01T00:00:{n:02d}.500000+00:00'})
    ret=lambda v:{'returnValue':v}
    refs={k:{'refPath':REF['refPath']+':'+k} for k in ('UV','Opacity','Color')}
    props={'UV':{'coordinateIndex':0,'uTiling':1,'vTiling':1,'unMirrorU':False,'unMirrorV':False},
        'Opacity':{'code':'// SYNTHETIC TEST ONLY\nreturn saturate(UV.x);','outputType':'CMOT_Float1',
            'inputs':[{'inputName':'UV','input':{'expression':refs['UV'],'outputIndex':0,'inputName':'None','mask':0,'maskR':0,'maskG':0,'maskB':0,'maskA':0}}],
            'additionalOutputs':[],'additionalDefines':[],'includeFilePaths':[]},
        'Color':{'constant':{'r':.1,'g':.8,'b':1.,'a':1.}}}
    if version == 2:
        props['Color'] = copy.deepcopy(props['Opacity'])
        props['Color'].update(code='// SYNTHETIC TEST ONLY\nreturn float3(UV.x, UV.y, 0.5);', outputType='CMOT_Float3')
    call(mat.MATERIAL,'recompile',{'material_or_function':REF},ret(None))
    call(mat.ASSET,'save_assets',{'asset_paths':[PACKAGE]},ret(True))
    call(mat.ASSET,'load_asset',{'asset_path':PACKAGE},ret(REF))
    call(mat.OBJECT,'get_class',{'instance':REF},ret({'refPath':'/Script/Engine.Material'}))
    call(mat.OBJECT,'get_properties',{'instance':REF,'properties':list(mat.MATERIAL_PROPERTIES)},ret(json.dumps(
        {'materialDomain':'MD_UI','blendMode':'BLEND_Translucent','twoSided':True,'numCustomizedUVs':0})))
    call(mat.MATERIAL,'get_expressions',{'material_or_function':REF},ret(list(refs.values())))
    for key,cls in [('UV',mat.UV),('Opacity',mat.CUSTOM),('Color',mat.CUSTOM if version == 2 else mat.COLOR)]:
        call(mat.OBJECT,'get_class',{'instance':refs[key]},ret({'refPath':cls}))
        call(mat.OBJECT,'get_properties',{'instance':refs[key],'properties':list(mat.EXPRESSION_PROPERTIES[cls])},ret(json.dumps(props[key])))
        call(mat.MATERIAL,'get_expression_inputs',{'material_or_function':REF,'expression':refs[key]},ret(
            [{'output_name':'','expression':refs['UV'],'input_name':'UV'}] if cls == mat.CUSTOM else []))
        call(mat.MATERIAL,'get_expression_output_names',{'expression':refs[key]},ret([''] if cls != mat.COLOR else ['','R','G','B']))
    for name,key in [('MP_Opacity','Opacity'),('MP_EmissiveColor','Color')]:
        call(mat.MATERIAL,'get_property_input',{'material':REF,'material_property':name},ret({'output_name':'','expression':refs[key],'input_name':''}))
    call(mat.ASSET,'is_dirty',{'asset_path':PACKAGE},ret(False))
    receipt={'kind':'task-native-material-execution','version':1,'status':'completed','currentOperation':None,
        'savedFile':str(saved.resolve()),'savedFileSha256':common.sha256(saved),'records':[]}
    for i,c in enumerate(calls[:2]):
        row=copy.deepcopy(c);row['beganAt']=row.pop('startedAt');row['id']=str(i);receipt['records'].append(row)
    receipt_path=root/'SYNTHETIC-execution.json';common.write_json(receipt_path,receipt)
    evidence={'kind':'nextgame-ui-procedural-material-readback','version':version,'acquisition':'official-unreal-mcp',
        'materialPath':PACKAGE,'projectFile':common.binding(project),'savedFile':common.binding(saved),
        'executionReceipt':common.binding(receipt_path),'capturedAt':'2026-09-01T00:01:00+00:00','calls':calls}
    path=root/'SYNTHETIC-material-readback.json';common.write_json(path,evidence)
    return {'kind':'material','materialPath':PACKAGE,'evaluationSize':[96,96],'evidence':common.binding(path)},evidence,path,saved

class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.fx=presentation.PresentationTests(methodName='runTest');self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.root=self.fx.root;self.source,self.e,self.path,self.saved=fixture(self.root)
        self.fx.request['capabilities'].append(mat.CAPABILITY);self.fx.request.pop('resourceCatalog');self.fx.image['source']=self.source
        self.brush=self.fx.icon['properties']['brush'];self.brush.update(resourceObject=copy.deepcopy(REF),imageSize={'x':96,'y':96},mirroring='NoMirror',uVRegion={'bIsValid':False})
        self.fx.icon['slot']['properties']['layoutData']['offsets'].update(right=96,bottom=96);self.sync()
    def sync(self):
        common.write_json(self.path,self.e,replace=True);self.source['evidence']=common.binding(self.path);self.fx.sync()
    def check(self,phase='planned'):return self.fx.check(phase)
    def fail(self,code):
        with self.assertRaises(common.ArtError) as caught:self.check()
        self.assertEqual(code,caught.exception.code,str(caught.exception))
    def row(self,name,suffix=None):
        return next(c for c in self.e['calls'] if c['tool']==name and (suffix is None or c['arguments'].get('instance',{}).get('refPath','').endswith(suffix)))
    def prop(self,suffix,key,value):
        row=self.row('get_properties',suffix);p=json.loads(row['result']['returnValue']);p[key]=value;row['result']['returnValue']=json.dumps(p);self.sync()
    def test_positive_native_material_without_texture_catalog(self):
        with patch('art_resources.validate_catalog',side_effect=AssertionError('No texture catalog')):result=self.check()
        self.assertTrue(all(c['status']=='passed' for c in result['checks']))
        proof=mat.validate_material_source(self.source,self.root/'decisions.json',PACKAGE)
        self.assertEqual([96,96],proof['evaluationSize']);self.assertEqual(64,len(proof['graphSha256']));self.assertNotIn('frameSize',proof)
    def test_actual_geometry_pending(self):
        self.assertTrue(any(c['status']=='pending' and c['id'].endswith(':geometry') for c in self.check('actual')['checks']))
    def test_no_capability(self):self.fx.request['capabilities'].remove(mat.CAPABILITY);self.fail('presentation.capability')
    def test_capability_needs_presentation(self):self.fx.request['capabilities']=[mat.CAPABILITY];self.fail('schema.request')
    def test_unknown_version(self):self.fx.request['capabilities'][-1]='procedural-ui-material/3';self.fail('schema.request')
    def test_closed_source(self):
        for k,v in [('frameSize',[96,96]),('alphaBounds',[0,0,96,96]),('catalogResourceId','fake'),('image',self.source['evidence'])]:
            with self.subTest(k=k):self.source[k]=v;self.fail('schema.decisions');del self.source[k]
    def test_closed_modes(self):
        for mode in ('stretch','nine-slice','no-draw'):
            with self.subTest(mode=mode):self.fx.image['aspectMode']=mode;self.fail('schema.decisions')
    def test_no_procedural_relabel(self):self.fx.image.update(source={'kind':'procedural','reason':'SYNTHETIC'},aspectMode='stretch');self.fail('presentation.procedural')
    def test_resource_identity(self):self.brush['resourceObject']={'refPath':'/Game/Other.Other'};self.fail('material.resource')
    def test_sidecar_identity(self):self.e['materialPath']='/Game/Other';self.sync();self.fail('material.identity')
    def test_stale_sidecar(self):self.path.write_text('{}');self.fail('binding.stale')
    def test_saved_bytes_rechecked(self):self.saved.write_bytes(b'CHANGED');self.fail('binding.stale')
    def test_empty_saved_file(self):self.saved.write_bytes(b'');self.e['savedFile']=common.binding(self.saved);self.sync();self.fail('material.saved_file')
    def test_foreign_saved_file(self):
        p=self.root/'foreign.uasset';p.write_bytes(self.saved.read_bytes());self.e['savedFile']=common.binding(p);self.sync();self.fail('material.saved_file')
    def test_project_file_required(self):
        p=self.root/'not-project.json';p.write_text('{}');self.e['projectFile']=common.binding(p);self.sync();self.fail('material.project')
    def test_closed_evidence(self):self.e['claimedVerified']=True;self.sync();self.fail('schema.proceduralMaterialReadback')
    def test_fixture_provider_rejected(self):self.e['acquisition']='fixture';self.sync();self.fail('schema.proceduralMaterialReadback')
    def test_failed_save(self):self.row('save_assets')['result']['returnValue']=False;self.sync();self.fail('schema.proceduralMaterialReadback')
    def test_compile_error(self):self.row('recompile')['result']={'isError':True};self.sync();self.fail('schema.proceduralMaterialReadback')
    def test_dirty(self):self.row('is_dirty')['result']['returnValue']=True;self.sync();self.fail('schema.proceduralMaterialReadback')
    def test_original_compile_receipt_binding(self):self.row('recompile')['completedAt']='2026-09-01T00:00:00.600000+00:00';self.sync();self.fail('material.execution_receipt')
    def test_missing_call(self):self.e['calls'].pop(9);self.sync();self.fail('schema.proceduralMaterialReadback')
    def test_duplicate_call(self):
        a=self.e['calls'][9];b=self.e['calls'][13];b.update({k:copy.deepcopy(a[k]) for k in ('toolset','tool','arguments','result')});self.sync();self.fail('material.call')
    def test_save_all_rejected(self):self.row('save_assets')['arguments']['asset_paths']=[];self.sync();self.fail('schema.proceduralMaterialReadback')
    def test_time_timezone(self):self.e['calls'][2]['startedAt']='2026-09-01T00:00:00';self.sync();self.fail('material.time')
    def test_capture_order(self):self.e['capturedAt']='2026-09-01T00:00:05+00:00';self.sync();self.fail('material.time')
    def test_instance_class_rejected(self):self.row('get_class','.M_Static')['result']['returnValue']={'refPath':'/Script/Engine.MaterialInstanceConstant'};self.sync();self.fail('material.class')
    def test_domain(self):self.prop('.M_Static','materialDomain','MD_Surface');self.fail('material.domain')
    def test_blend(self):self.prop('.M_Static','blendMode','BLEND_Opaque');self.fail('material.domain')
    def test_custom_uv(self):self.prop('.M_Static','numCustomizedUVs',1);self.fail('material.domain')
    def test_wrong_expression_class(self):self.row('get_class',':Color')['result']['returnValue']={'refPath':'/Script/Engine.MaterialExpressionVectorParameter'};self.sync();self.fail('material.class')
    def test_foreign_expression(self):self.row('get_expressions')['result']['returnValue'][0]={'refPath':'/Game/Other.Other:UV'};self.sync();self.fail('material.graph')
    def test_extra_expression(self):self.row('get_expressions')['result']['returnValue'].append({'refPath':REF['refPath']+':Time'});self.sync();self.fail('schema.proceduralMaterialReadback')
    def test_missing_property(self):self.prop(':UV','extra',1);self.fail('material.properties')
    def test_nonfinite_property(self):self.row('get_properties',':Color')['result']['returnValue']='{"constant":{"r":NaN,"g":1,"b":1,"a":1}}';self.sync();self.fail('material.properties')
    def test_unbound_code_include(self):self.prop(':Opacity','includeFilePaths',['/Unbound.ush']);self.fail('material.custom')
    def test_unbound_custom_input(self):self.prop(':Opacity','inputs',[{'inputName':'UV'},{'inputName':'Time'}]);self.fail('material.custom')
    def test_native_input_masks_cannot_disagree_with_graph(self):
        row=self.row('get_properties',':Opacity');props=json.loads(row['result']['returnValue']);props['inputs'][0]['input']['maskR']=1
        row['result']['returnValue']=json.dumps(props);self.sync();self.fail('material.wiring')
    def test_missing_native_input_cannot_claim_complete_properties(self):
        self.prop(':Opacity','inputs',[{'inputName':'UV'}]);self.fail('material.wiring')
    def test_malformed_uv_override_fails_closed(self):
        self.brush['uVRegion']=None;self.fail('presentation.material_uv')
    def test_original_execution_bytes_are_rechecked(self):
        Path(self.e['executionReceipt']['path']).write_text('{}');self.fail('binding.stale')
    def test_nonzero_uv_channel(self):self.prop(':UV','coordinateIndex',1);self.fail('material.uv')
    def test_wiring(self):self.row('get_property_input')['result']['returnValue']['expression']={'refPath':REF['refPath']+':Color'};self.sync();self.fail('material.wiring')
    def test_aspect(self):self.brush['imageSize']['y']=80;self.fail('presentation.aspect')
    def test_allocation_aspect(self):self.fx.icon['slot']['properties']['layoutData']['offsets']['bottom']=80;self.fail('presentation.aspect')
    def test_unknown_allocation_pending(self):self.fx.icon['slot']['properties']['bAutoSize']=True;self.assertTrue(any(c['status']=='pending' for c in self.check()['checks']))
    def test_uniform_evaluation_scaling(self):
        self.brush['imageSize']={'x':192,'y':192};self.fx.icon['slot']['properties']['layoutData']['offsets'].update(right=192,bottom=192)
        self.assertTrue(all(c['status']=='passed' for c in self.check()['checks']))
    def test_uv_crop(self):self.brush['uVRegion']['bIsValid']=True;self.fail('presentation.material_uv')
    def test_brush_mirror(self):self.brush['mirroring']='Horizontal';self.fail('presentation.material_uv')
    def test_noop_apply_and_rerun(self):
        self.assertEqual('ready',self.fx.plan()['status']);editor=presentation.FakeEditor(self.fx.snapshot)
        self.fx.fx.apply(editor);second=self.fx.fx.apply(editor);self.assertFalse(second['changed'])
    def test_canonical_capture_not_geometry(self):self.fx.test_verify_emits_pending_geometry_even_with_canonical_capture()

class FormalMaterialTests(unittest.TestCase):
    def test_final_bundle_readback_recompute_and_reject_pending_or_forged_pass(self):
        t=integration.PresentationIntegrationTests(methodName='runTest');t.setUp();self.addCleanup(t.doCleanups);t.enable();fx=t.fx
        item=fx.decisions['presentationReview']['images'][0];source,_,_,_=fixture(fx.art_dir)
        fx.request['capabilities'].append(mat.CAPABILITY);item.update(source=source,aspectMode='preserve')
        node=next(w for a in fx.snapshot['assets'] if a['assetPath']==item['assetPath'] for w in a['widgets'] if w['widgetName']==item['widgetName'])
        node['properties']['brush'].update(resourceObject=REF,drawAs='Image',tiling='NoTile',mirroring='NoMirror',imageSize={'x':96,'y':96},margin={'left':0,'top':0,'right':0,'bottom':0},uVRegion={'bIsValid':False})
        t.rebind();t.assertGatesReject('art.presentation_pending')
        for c in fx.verification['checks']:c['status']='passed'
        fx.flush();t.assertGatesReject('art.presentation_checks')

if __name__=='__main__':unittest.main()
