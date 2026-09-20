"""SYNTHETIC delegation tests. No real appearance or user approval evidence."""
import copy, hashlib, unittest
import art_common as c
from art_delegation import FIELDS
from test_art_presentation import PresentationTests
class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.fx=PresentationTests('runTest');self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.root=self.fx.root;self.req=self.fx.request;self.item=self.fx.text_decision
        self.message='SYNTHETIC: 我授权你这一次测试自动进行下去。高保真美术还原。'
        self.packet={'requestId':self.req['requestId'],'inputDigest':'synthetic-input','sources':[{'sourceKey':'user','kind':'user-text','locatorKind':'inline','content':self.message}],'userRequest':{'originalText':[self.message]}}
        self.original={'kind':'request-scoped-user-authorization','sourceMessage':self.message,'freshEvidenceRequired':True,'mayContinueWithoutRepeatedQuestions':True,'mayFabricatePostResultUserMessage':False,'mayReuseOldAssetsOrCachedPlans':False}
        self.requirement={'requestId':self.req['requestId'],'inputDigest':'synthetic-input','request':{'originalText':[self.message]}}
        self.item['resolution']='delegated';self.item['parameterConfidence']='medium'
        self.auth={'kind':'request-scoped-art-choice','version':1,'requestId':self.req['requestId'],'reviewer':'primary-coordinator','scope':'appearance-choices-only','sourcePacket':{},'authorizationFile':{},'sourceKey':'user','messageSha256':hashlib.sha256(self.message.encode()).hexdigest(),'explicitGrantQuote':'我授权你这一次测试自动进行下去','sourceConfidencePreserved':True,'actualVisualAcceptanceRequired':True,'assetPaths':[self.item['assetPath']],'texts':[{k:copy.deepcopy(self.item[k]) for k in FIELDS}]}
        self.req['capabilities'].append('delegated-art-choice/1');self.sync()
    def sync(self):
        w=self.fx.fx.write
        self.auth['sourcePacket']=c.binding(w('packet.json',self.packet));self.auth['authorizationFile']=c.binding(w('authorization.json',self.original))
        self.req['baseline']['requirement']=c.binding(w('requirement.json',self.requirement))
        self.req['delegatedArtChoice']=c.binding(w('authority.json',self.auth));self.fx.sync()
    def rejected(self):
        with self.assertRaises(c.ArtError):self.fx.check()
    def test_ready_configuration_does_not_pass_geometry(self):
        self.assertEqual([],self.fx.check()['issues']);self.assertEqual('ready',self.fx.plan()['status'])
        self.assertTrue(any(x['status']=='pending' and x['id'].endswith(':geometry') for x in self.fx.check('actual')['checks']))
    def test_no_capability_rejected(self):
        self.req['capabilities'].remove('delegated-art-choice/1');self.rejected()
    def test_no_sidecar_cannot_bypass_with_delegated_label(self):
        self.req['capabilities'].remove('delegated-art-choice/1');self.req.pop('delegatedArtChoice');self.rejected()
    def test_generic_method_permission_rejected(self):
        self.packet['sources'][0]['content']='SYNTHETIC automatic recognition';self.sync();self.rejected()
    def _replace_message(self,message,quote):
        self.message=message
        self.packet['sources'][0]['content']=message
        self.packet['userRequest']['originalText']=[message]
        self.original['sourceMessage']=message
        self.requirement['request']['originalText']=[message]
        self.auth['explicitGrantQuote']=quote
        self.auth['messageSha256']=hashlib.sha256(message.encode()).hexdigest()
        self.sync()
    def test_explicit_delegated_review_format_preserves_actual_gate(self):
        quote='我授权本次测试按插件现有支持的委托审核流程自动推进；委托审核不能替代真实验证或伪造通过。'
        self._replace_message('SYNTHETIC: '+quote+' 高保真美术还原',quote)
        self.assertEqual([],self.fx.check()['issues'])
        self.assertTrue(any(x['status']=='pending' and x['id'].endswith(':geometry') for x in self.fx.check('actual')['checks']))
    def test_continuation_and_missing_art_stage_do_not_grant(self):
        quote='我授权本次测试按插件现有支持的委托审核流程自动推进；委托审核不能替代真实验证或伪造通过。'
        self._replace_message('SYNTHETIC: 执行 高保真美术还原','执行');self.rejected()
        self._replace_message('SYNTHETIC: '+quote,quote);self.rejected()
    def test_wrong_request_rejected(self):
        self.auth['requestId']='other';self.sync();self.rejected()
    def test_wrong_requirement_input_rejected(self):
        self.requirement['inputDigest']='other';self.sync();self.rejected()
    def test_stale_authority_hash_rejected(self):
        self.fx.fx.write('authority.json',{**self.auth,'sourceKey':'other'});self.rejected()
    def test_scope_mismatch_rejected(self):
        self.auth['assetPaths'].append('/Game/UI/UMG/Other/umg_other');self.sync();self.rejected()
    def test_confidence_cannot_be_elevated(self):
        self.item['parameterConfidence']='high';self.rejected()
    def test_numeric_choice_cannot_change(self):
        self.item['outline']['size']=3;self.rejected()
    def test_no_fake_user_confirmation(self):
        self.item['confirmations']=[{'source':'direct-user-message','scope':'appearance-parameters','text':'SYNTHETIC fabricated'}];self.rejected()
    def test_unknown_choice_rejected(self):
        self.item['effect']='unknown';self.auth['texts'][0]['effect']='unknown';self.sync();self.rejected()
    def test_duplicate_choice_rejected(self):
        self.auth['texts'].append(copy.deepcopy(self.auth['texts'][0]));self.sync();self.rejected()
    def test_original_boundary_not_bool_integer(self):
        self.original['freshEvidenceRequired']=1;self.sync();self.rejected()
    def test_tampered_visual_gate_claim_rejected(self):
        self.auth['actualVisualAcceptanceRequired']=False;self.sync();self.rejected()
if __name__=='__main__':unittest.main()
