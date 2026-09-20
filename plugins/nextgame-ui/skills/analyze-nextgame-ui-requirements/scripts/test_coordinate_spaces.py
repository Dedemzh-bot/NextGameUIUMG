"""Observable rejection/compatibility tests for trial source/target coordinates."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from _coordinate_spaces import (CAPABILITY, canonical_sha, file_sha, validate_contract, validate_layout_binding, validate_bundle_binding, expected_rect, slot_projection, target_core)
from _contract_common import load_json, validate_schema_instance, compute_approved_content_sha256
from visual_coverage_scan import declared_visuals

class CoordinateSpacesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'source.png'
        self.source.write_bytes(b'bound-original-image')
        self.raw = [600,300,120,60]
        bounds = [600/2400,300/1080,120/2400,60/1080]
        self.req = {'version':'0.1','requestId':'request.test','sources':[{'id':'source.image','kind':'image','dimensions':[2400,1080],'path':str(self.source),'contentSha256':file_sha(self.source)}], 'evidence':[{'id':'evidence.geom','sourceId':'source.image','sourceDimensions':[2400,1080],'pixelBounds':self.raw,'bounds':bounds,'measurementMethod':'image-measurement'}], 'claims':[{'id':'claim.geom','status':'accepted','subjectRefs':['region.test'],'evidenceIds':['evidence.geom']}], 'reviewGate':{'status':'accepted','acceptedClaimIds':['claim.geom']},'uiModel':{'regions':[{'id':'region.test','bounds':bounds,'geometryEvidenceId':'evidence.geom'}],'elements':[]}, 'assetPlan':[{'id':'asset.screen','assetPath':'/Game/UI/UMG/Test/umg_test','assetKind':'screen','referenceSize':[2560,1440]}]}
        self.req['reviewGate']['approvedContentSha256']=compute_approved_content_sha256(self.req)
        observations=self.write('observations.json',self.req)
        self.target={'assetId':'asset.screen','layoutNodeKey':'test','subjectRefs':['region.test'],'coordinateSpace':'screen-design','rectPixels':[480,400,160,80],'slotContract':{'parent':None,'anchor':'left-top'},'mode':'source-transform','sourceRef':'region.test','geometryEvidenceId':'evidence.geom','evidenceIds':['evidence.geom'],'claimIds':['claim.geom']}
        self.req['coordinateContract']={'capability':CAPABILITY,'version':1,'status':'trial','sourceId':'source.image','sourceSha256':file_sha(self.source),'sourceSize':[2400,1080],'sourceObservations':observations,'contentFrame':[240,0,1920,1080],'targetSize':[2560,1440],'uniformScale':4/3,'evidenceIds':['evidence.geom'],'claimIds':['claim.geom'],'targets':[self.target]}
        self.reqpath=self.root/'requirement.json'
        self.layout={'asset':{'folder':'/Game/UI/UMG/Test','name':'umg_test'},'referenceSize':[2560,1440],'profile':{'assetKind':'screen'},'nodes':[{'id':'test','name':'ImgTest','role':'image','rect':[480/2560,400/1440,160/2560,80/1440],'parent':None,'anchor':'left-top','properties':{}}]}
        self.sync()
    def write(self,name,value):
        path=self.root/name
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return {'path':str(path),'sha256':file_sha(path)}
    def sync(self):
        self.req['reviewGate']['approvedContentSha256']=compute_approved_content_sha256(self.req)
        link=self.write('requirement.json',self.req)
        self.layout['coordinateBinding']={'capability':CAPABILITY,'version':1,'contractSha256':canonical_sha(self.req['coordinateContract']),'assetId':'asset.screen','requirement':link}
    def errors(self):
        return validate_contract(self.req,spec_path=self.reqpath)
    def derived(self):
        self.target.update(mode='design-derived',reason='Explicit accepted local design capacity, not raw measurement.')
        self.target.pop('sourceRef');self.target.pop('geometryEvidenceId')
        script=self.write('derive.py',{'deterministic':'fixture'})
        proof={'kind':'coordinate-design-derivation','version':1,'requestId':self.req['requestId'],'boundary':'design-derived-not-source-transform-proof','script':script,'inputs':[self.req['coordinateContract']['sourceObservations']],'records':[target_core(self.target)]}
        self.target['derivationEvidence']=self.write('derivation.json',proof)
        review={'kind':'coordinate-design-review','version':1,'requestId':self.req['requestId'],'status':'passed','reviewer':'independent-coordinator','reviewedAt':'2026-09-18T00:00:00+00:00','derivationSha256':self.target['derivationEvidence']['sha256'],'records':[{'assetId':self.target['assetId'],'layoutNodeKey':self.target['layoutNodeKey'],'recordSha256':canonical_sha(target_core(self.target))}]}
        self.target['reviewEvidence']=self.write('review.json',review)
        self.sync()
    def test_uniform_transform(self):self.assertEqual([],self.errors())
    def test_anisotropic_16_over_15_rejected(self):
        self.req['coordinateContract']['uniformScale']=16/15
        self.assertTrue(self.errors())
    def test_old_raw_normalization_as_target_rejected(self):
        self.target['rectPixels']=[600*2560/2400,300*1440/1080,120*2560/2400,60*1440/1080]
        self.assertTrue(self.errors())
    def test_source_entity_bounds_change_rejected(self):
        self.req['uiModel']['regions'][0]['bounds'][0]=.3
        self.assertTrue(self.errors())
    def test_simultaneous_source_bounds_and_pixels_change_rejected(self):
        self.req['evidence'][0]['pixelBounds']=[700,300,120,60]
        self.req['evidence'][0]['bounds']=[700/2400,300/1080,120/2400,60/1080]
        self.req['uiModel']['regions'][0]['bounds']=self.req['evidence'][0]['bounds']
        self.target['rectPixels'][0]=(700-240)*4/3
        self.assertTrue(self.errors())
    def test_unrelated_business_revision_allowed(self):
        self.req['uiModel']['regions'][0]['purpose']='New accepted business description'
        self.assertEqual([],self.errors())
    def test_new_entity_does_not_rewrite_old_observation(self):
        self.req['uiModel']['elements'].append({'id':'element.new','properties':{'text':'new'}})
        self.assertEqual([],self.errors())
    def test_source_file_tamper_rejected(self):
        self.source.write_bytes(b'tampered')
        self.assertTrue(self.errors())
    def test_observation_snapshot_tamper_rejected(self):
        (self.root/'observations.json').write_text('{}')
        self.assertTrue(self.errors())
    def test_unknown_contract_field_rejected(self):
        self.req['coordinateContract']['skipSourceDrift']=True
        self.assertTrue(self.errors())
    def test_unknown_target_field_rejected(self):
        self.target['expression']='anything'
        self.assertTrue(self.errors())
    def test_wrong_capability_rejected(self):
        self.req['coordinateContract']['capability']='source-target-coordinates/2'
        self.assertTrue(self.errors())
    def test_missing_accepted_claim_rejected(self):
        self.req['reviewGate']['acceptedClaimIds']=[]
        self.assertTrue(self.errors())
    def test_unrelated_claim_rejected(self):
        self.req['claims'][0]['subjectRefs']=[]
        self.assertTrue(self.errors())
    def test_unknown_evidence_rejected(self):
        self.target['evidenceIds']=['evidence.unknown']
        self.assertTrue(self.errors())
    def test_duplicate_target_rejected(self):
        self.req['coordinateContract']['targets'].append(copy.deepcopy(self.target))
        self.assertTrue(self.errors())
    def test_nonfinite_rect_rejected(self):
        self.target['rectPixels'][0]=float('nan')
        self.assertTrue(self.errors())
    def test_outside_content_frame_rejected(self):
        self.req['coordinateContract']['contentFrame'][0]=-1
        self.assertTrue(self.errors())
    def test_design_derived_exact_review_passes(self):
        self.derived();self.assertEqual([],self.errors())
    def test_design_derived_target_drift_rejected(self):
        self.derived();self.target['rectPixels'][0]+=1;self.assertTrue(self.errors())
    def test_design_derived_slot_drift_rejected(self):
        self.derived();self.target['slotContract']['anchor']='center';self.assertTrue(self.errors())
    def test_design_derived_missing_review_rejected(self):
        self.derived();self.target.pop('reviewEvidence');self.assertTrue(self.errors())
    def test_design_derived_false_source_flag_rejected(self):
        self.derived();self.target['sourceRef']='region.test';self.assertTrue(self.errors())
    def test_design_derived_stale_review_rejected(self):
        self.derived();review=json.loads((self.root/'review.json').read_text());review['records'][0]['recordSha256']='0'*64;self.target['reviewEvidence']=self.write('review.json',review);self.assertTrue(self.errors())
    def test_layout_exact_binding_passes(self):self.assertEqual([],validate_layout_binding(self.layout))
    def test_layout_missing_binding_rejected_with_requirement(self):
        self.layout.pop('coordinateBinding');self.assertTrue(validate_layout_binding(self.layout,requirement=self.req))
    def test_layout_target_drift_rejected(self):
        self.layout['nodes'][0]['rect'][0]+=.01;self.assertTrue(validate_layout_binding(self.layout))
    def test_layout_slot_drift_rejected(self):
        self.layout['nodes'][0]['anchor']='center';self.assertTrue(validate_layout_binding(self.layout))
    def test_layout_extra_node_rejected(self):
        self.layout['nodes'].append(dict(self.layout['nodes'][0],id='extra'));self.assertTrue(validate_layout_binding(self.layout))
    def test_layout_wrong_requirement_hash_rejected(self):
        self.layout['coordinateBinding']['requirement']['sha256']='0'*64;self.assertTrue(validate_layout_binding(self.layout))
    def test_layout_wrong_asset_rejected(self):
        self.layout['asset']['name']='umg_other';self.assertTrue(validate_layout_binding(self.layout))
    def test_bundle_missing_binding_rejected(self):self.assertTrue(validate_bundle_binding({},self.req))
    def test_bundle_node_mapping_exact_binding(self):
        bundle={'coordinateBinding':{k:self.layout['coordinateBinding'][k] for k in ('capability','version','contractSha256')},'assets':[{'id':'build.screen','assetPlanId':'asset.screen'}],'nodeMappings':[{'assetId':'build.screen','layoutNodeId':'test','requirementRefs':['region.test']}]}
        self.assertEqual([],validate_bundle_binding(bundle,self.req))
        bundle['nodeMappings'][0]['requirementRefs']=[]
        self.assertTrue(validate_bundle_binding(bundle,self.req))
    def test_preview_expected_uses_target_space(self):
        self.assertEqual(self.layout['nodes'][0]['rect'],expected_rect(self.req,'asset.screen','test','region.test',[.25,.3,.05,.1]))
        self.assertIsNone(expected_rect(self.req,'asset.screen','test','region.other',[.25,.3,.05,.1]))
    def test_source_scan_does_not_reinterpret_target_layout(self):
        self.assertEqual([],declared_visuals(self.req,[(self.root/'layout.json',self.layout)],2400,1080))
        with self.assertRaises(ValueError):declared_visuals(self.req,[],2560,1440)
    def test_legacy_no_optin_unchanged(self):
        self.req.pop('coordinateContract');self.layout.pop('coordinateBinding')
        self.assertEqual([],validate_contract(self.req));self.assertEqual([],validate_layout_binding(self.layout));self.assertEqual([],validate_bundle_binding({},self.req))
        self.assertEqual([.1,.2,.3,.4],expected_rect(self.req,'x','y','z',[.1,.2,.3,.4]))
    def test_schema_closed_slots(self):
        self.target['slotContract']['unknown']=True;self.assertTrue(self.errors())
    def test_local_direct_source_transform_rejected(self):
        self.target['coordinateSpace']='asset-local';self.assertTrue(self.errors())

    def registered(self):
        resource=self.write('resource.png',{'fixture':'full-frame'})
        script=self.write('registration.py',{'fixture':'registration'})
        doc={'kind':'source-whole-frame-registration','version':1,'reference':{'path':str(self.source),'sha256':file_sha(self.source),'size':[2400,1080]},'script':script,'results':[{'id':'frame.one','status':'source-registration-supported-by-low-residual','source':resource,'best':{'sourceScreenshotFramePosition':[600,300],'resizedFrameSize':[120,60]}}]}
        self.target.pop('sourceRef');self.target.pop('geometryEvidenceId')
        self.target['wholeFrameRegistration']={**self.write('registration.json',doc),'recordKey':'frame.one'}
        return doc
    def test_registered_full_frame_uses_observed_source_pixels(self):
        self.registered();self.assertEqual([],self.errors())
    def test_registered_frame_unknown_record_rejected(self):
        self.registered();self.target['wholeFrameRegistration']['recordKey']='missing';self.assertTrue(self.errors())
    def test_registered_frame_ambiguous_record_rejected(self):
        doc=self.registered();doc['results'].append(copy.deepcopy(doc['results'][0]));self.target['wholeFrameRegistration'].update(self.write('registration.json',doc));self.assertTrue(self.errors())
    def test_registered_frame_target_calculation_not_authority(self):
        doc=self.registered();doc['targetCalculation']={'targetRect':[1,2,3,4]};self.target['wholeFrameRegistration'].update(self.write('registration.json',doc));self.assertEqual([],self.errors())
        self.target['rectPixels']=[1,2,3,4];self.assertTrue(self.errors())
    def test_registered_frame_unaccepted_status_rejected(self):
        doc=self.registered();doc['results'][0]['status']='uncertain';self.target['wholeFrameRegistration'].update(self.write('registration.json',doc));self.assertTrue(self.errors())
    def test_registered_frame_resource_tamper_rejected(self):
        self.registered();(self.root/'resource.png').write_bytes(b'changed');self.assertTrue(self.errors())
    def test_registered_frame_wrong_original_source_rejected(self):
        doc=self.registered();doc['reference']['size']=[2560,1440];self.target['wholeFrameRegistration'].update(self.write('registration.json',doc));self.assertTrue(self.errors())
    def test_layout_wrong_approved_content_rejected(self):
        self.req['uiModel']['regions'][0]['purpose']='changed after approval';link=self.write('requirement.json',self.req);self.layout['coordinateBinding']['requirement']=link;self.assertTrue(validate_layout_binding(self.layout))
    def test_boolean_version_is_not_integer_version(self):
        self.req['coordinateContract']['version']=True;self.assertTrue(self.errors())
    def test_projection_keeps_coordinate_refs_and_header(self):
        from _contract_common import ASSETS_ROOT
        from accepted_build_view import build_accepted_build_view
        req=load_json(ASSETS_ROOT/'example-composite-tabs-requirement.json')
        source=req['sources'][0]
        source.update(locatorKind='local-file',path=str(self.source),contentSha256=file_sha(self.source))
        source.pop('content',None)
        req['reviewGate']['approvedContentSha256']=compute_approved_content_sha256(req)
        contract=copy.deepcopy(self.req['coordinateContract'])
        contract.update(sourceId=source['id'],sourceSha256=file_sha(self.source),sourceSize=[2048,1152],contentFrame=[0,0,2048,1152],uniformScale=1.25,sourceObservations=self.write('observations.json',req),evidenceIds=['evidence-project-resolution'],claimIds=['claim-screen-resolution'])
        target=contract['targets'][0]
        target.update(assetId='asset-screen-role',subjectRefs=['region-screen'],sourceRef='region-screen',geometryEvidenceId='evidence-project-resolution',rectPixels=[0,0,2560,1440],evidenceIds=contract['evidenceIds'],claimIds=contract['claimIds'])
        self.req=req;self.target=target;self.req['coordinateContract']=contract
        self.derived()
        view,mode,reason=build_accepted_build_view(json.dumps(self.req).encode('utf-8'))
        self.assertEqual(('projected',None),(mode,reason))
        self.assertEqual(contract,view['requirement']['coordinateContract'])
        self.assertIn(contract['sourceId'],[s['id'] for s in view['requirement']['sources']])

    def planned_fixture(self):
        import sys
        build_scripts=Path(__file__).resolve().parents[2]/'build-nextgame-umg/scripts'
        if str(build_scripts) not in sys.path:sys.path.insert(0,str(build_scripts))
        from test_adaptive_layout_rules import adaptive_screen_spec
        self.layout=adaptive_screen_spec()
        self.req['assetPlan'][0]['assetPath']='/Game/UI/UMG/Adapt/umg_adapt'
        targets=[]
        for node in self.layout['nodes']:
            target=copy.deepcopy(self.target)
            target.update(layoutNodeKey=node['id'],rectPixels=[v*s for v,s in zip(node['rect'],[2560,1440,2560,1440])],slotContract=slot_projection(node),mode='design-derived',reason='Accepted exact fixture design')
            target.pop('sourceRef');target.pop('geometryEvidenceId')
            targets.append(target)
        script=self.write('derive.py',{'fixture':'declared design records'})
        proof={'kind':'coordinate-design-derivation','version':1,'requestId':self.req['requestId'],'boundary':'design-derived-not-source-transform-proof','script':script,'inputs':[self.req['coordinateContract']['sourceObservations']],'records':[target_core(t) for t in targets]}
        proof_binding=self.write('derivation.json',proof)
        review={'kind':'coordinate-design-review','version':1,'requestId':self.req['requestId'],'status':'passed','reviewer':'fixture-reviewer','reviewedAt':'2026-09-18T00:00:00+00:00','derivationSha256':proof_binding['sha256'],'records':[{'assetId':t['assetId'],'layoutNodeKey':t['layoutNodeKey'],'recordSha256':canonical_sha(target_core(t))} for t in targets]}
        review_binding=self.write('review.json',review)
        for target in targets:target.update(derivationEvidence=proof_binding,reviewEvidence=review_binding)
        self.req['coordinateContract']['targets']=targets
        self.sync()
        return build_scripts
    def test_prepare_lowers_exact_bound_target_and_rejects_drift(self):
        build_scripts=self.planned_fixture()
        from prepare_build import build_plan
        plan=build_plan(self.root/'layout.json',self.layout,load_json(build_scripts.parent/'references/component-catalog.json'),load_json(build_scripts.parent/'references/rule-index.json'))
        self.assertTrue(plan['steps'])
        self.layout['nodes'][2]['rect'][0]+=.01
        with self.assertRaises(ValueError):build_plan(self.root/'layout.json',self.layout,load_json(build_scripts.parent/'references/component-catalog.json'),load_json(build_scripts.parent/'references/rule-index.json'))
    def test_router_recognizes_new_contract(self):
        self.planned_fixture()
        from route_rule_cards import build_rule_card_pack
        self.write('layout.json',self.layout)
        pack=build_rule_card_pack(self.root/'layout.json')
        self.assertEqual('routed',pack['routingMode'])
    def test_root_canvas_offsets_cannot_contradict_accepted_rect(self):
        build_scripts=self.planned_fixture()
        from validate_layout_spec import validate_spec
        self.layout['nodes'][2]['slotLayout']['offsets']['left']+=8
        target=self.req['coordinateContract']['targets'][2]
        target['slotContract']=slot_projection(self.layout['nodes'][2])
        # A fresh accepted exact Slot contract still cannot falsify the rect.
        proof=json.loads((self.root/'derivation.json').read_text());proof['records'][2]=target_core(target)
        proof_binding=self.write('derivation.json',proof)
        review=json.loads((self.root/'review.json').read_text());review['derivationSha256']=proof_binding['sha256'];review['records'][2]['recordSha256']=canonical_sha(target_core(target))
        review_binding=self.write('review.json',review)
        for target in self.req['coordinateContract']['targets']:target.update(derivationEvidence=proof_binding,reviewEvidence=review_binding)
        self.sync()
        report=validate_spec(self.layout,load_json(build_scripts.parent/'references/component-catalog.json'))
        self.assertIn('slot_layout.local_coordinates',{e['code'] for e in report['errors']})

    def test_legacy_bundle_cannot_silently_adopt_optin_layout(self):
        self.write('layout.json',self.layout)
        self.req.pop('coordinateContract')
        bundle={'assets':[{'layoutSpecPath':'layout.json'}]}
        self.assertTrue(validate_bundle_binding(bundle,self.req,bundle_path=self.root/'bundle.json'))
    def test_observation_snapshot_acceptance_hash_cannot_be_forged_by_changes(self):
        path=self.root/'observations.json'
        original=json.loads(path.read_text());original['uiModel']['regions'][0]['purpose']='unaccepted revision'
        self.req['coordinateContract']['sourceObservations']=self.write('observations.json',original)
        self.assertTrue(self.errors())

    def test_legacy_opaque_asset_id_keeps_original_fallback(self):
        from _contract_common import ASSETS_ROOT
        from accepted_build_view import build_accepted_build_view
        req=load_json(ASSETS_ROOT/'example-composite-tabs-requirement.json')
        req['uiModel']['elements'][0].setdefault('properties',{})['assetId']=req['assetPlan'][0]['id']
        req['reviewGate']['approvedContentSha256']=compute_approved_content_sha256(req)
        _,mode,reason=build_accepted_build_view(json.dumps(req).encode('utf-8'))
        self.assertEqual(('full-fallback','unknown-reference-shape'),(mode,reason))

if __name__=='__main__':unittest.main()
