"""Synthetic child-catalog regressions, never production acceptance or UE evidence."""
import copy
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import art_common as common
import art_pipeline as pipeline


SCREEN = '/Game/UI/AIPrototype/umg_ai_catalog_test'
CHILD = '/Game/UI/AIPrototype/uw_catalog_child'
CHILD_CLASS = CHILD + '.uw_catalog_child_C'


class ChildCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = common.load_json(common.PLUGIN_ROOT / 'skills/build-nextgame-umg/references/component-catalog.json')
        self.request = {'requestId': 'synthetic-catalog', 'scope': [{'assetPath': SCREEN}, {'assetPath': CHILD}]}
        self.source = {'id': 'child', 'assetPlanId': 'child', 'assetPath': CHILD, 'assetKind': 'child-widget'}
        self.target = {'id': 'screen', 'assetPlanId': 'screen', 'assetPath': SCREEN, 'assetKind': 'prototype',
                       'dependsOnAssetIds': ['child']}
        self.requirement = {'version': '0.2', 'requestId': 'synthetic-catalog',
                            'reviewGate': {'status': 'accepted', 'acceptedClaimIds': ['claim']},
                            'claims': [{'id': 'claim', 'status': 'accepted'}],
                            'assetPlan': [dict(self.source, inBuildScope=True), dict(self.target, inBuildScope=True)]}
        self.op = {'id': 'integrate', 'type': 'child-widget-integration', 'integrationStrategy': 'create-child-widget',
                   'sourceAssetId': 'child', 'targetAssetId': 'screen', 'targetLayoutNodeId': 'child-node', 'claimIds': ['claim']}
        self.mapping = {'assetId': 'screen', 'layoutNodeId': 'child-node', 'requirementRefs': ['element'], 'claimIds': ['claim']}
        self.bundle = {'assets': [self.source, self.target], 'nodeMappings': [self.mapping], 'crossAssetOperations': [self.op]}
        self.layout = {'version': '0.2', 'mode': 'prototype',
                       'asset': {'folder': '/Game/UI/AIPrototype', 'name': 'umg_ai_catalog_test'},
                       'referenceSize': [2560, 1440],
                       'profile': {'adaptive': True, 'interactive': False, 'hasText': False,
                                   'containsRepeatedElements': False, 'regionGrouping': True, 'assetKind': 'prototype'},
                       'nodes': [
                           {'id': 'root', 'name': 'PanelRoot', 'role': 'screen.root', 'parent': None,
                            'rect': [0, 0, 1, 1], 'anchor': 'left-top', 'properties': {}},
                           {'id': 'child-node', 'name': 'WgtChild', 'role': 'widget.synthetic-child', 'parent': 'root',
                            'rect': [0.1, 0.1, 0.2, 0.2], 'anchor': 'left-top', 'isVariable': True,
                            'regionPurpose': 'child', 'properties': {'visibility': 'SelfHitTestInvisible'}}]}

    def derive(self):
        return pipeline._asset_source_catalog(self.request, self.requirement, self.bundle,
                                              self.target, self.layout, self.catalog)

    def rejected(self, code):
        with self.assertRaises(common.ArtError) as caught:
            self.derive()
        self.assertEqual(code, caught.exception.code)

    def test_exact_child_for_both_requirement_versions_and_no_input_mutation(self):
        originals = copy.deepcopy([self.request, self.requirement, self.bundle, self.layout, self.catalog])
        for version in ('0.1', '0.2'):
            self.requirement['version'] = version
            result = self.derive()
            self.assertEqual(CHILD_CLASS, result['components'][-1]['classPath'])
            self.assertFalse(result['components'][-1]['isPanel'])
            self.assertTrue(result['components'][-1]['canRepresentRegion'])
            self.assertEqual({}, result['components'][-1]['propertyMap'])
        self.requirement['version'] = '0.2'
        self.assertEqual(originals, [self.request, self.requirement, self.bundle, self.layout, self.catalog])

    def test_real_lowering_uses_exact_class_and_common_visibility(self):
        build = common.PLUGIN_ROOT / 'skills/build-nextgame-umg/scripts'
        sys.path.insert(0, str(build))
        from prepare_build import build_plan
        rules = common.load_json(build.parent / 'references/rule-index.json')
        plan = build_plan(Path('synthetic-layout.json'), self.layout, self.derive(), rules)
        steps = {s['stepId']: s for s in plan['steps']}
        self.assertEqual({'refPath': CHILD_CLASS}, steps['add-child-node']['arguments']['widgetClass'])
        self.assertEqual({'visibility': 'SelfHitTestInvisible'}, steps['set-widget-properties-child-node']['arguments']['values'])

    def test_bound_source_nodes_keep_class_lock(self):
        base = common.PLUGIN_ROOT.parent / 'test-runs'
        directory = base / ('catalog-' + uuid.uuid4().hex)
        directory.mkdir(parents=True)
        try:
            layout_path, req_path, bundle_path = [directory / n for n in ('layout.json', 'requirement.json', 'bundle.json')]
            common.write_json(layout_path, self.layout)
            self.target.update(layoutSpecPath='layout.json', layoutSpecSha256=common.sha256(layout_path))
            common.write_json(req_path, self.requirement)
            common.write_json(bundle_path, self.bundle)
            self.request['baseline'] = {'bundle': common.binding(bundle_path), 'requirement': common.binding(req_path)}
            locked = pipeline._source_nodes(self.request, directory / 'request.json')
            child = locked[(SCREEN, 'WgtChild')]
            self.assertEqual(CHILD_CLASS, child['classPath'])
            operation = {'kind': 'add-widget', 'assetPath': SCREEN, 'widgetName': 'WgtChild', 'sourceElementId': 'element',
                         'after': {**child, 'slot': {'properties': child['slot']}}}
            pipeline._check_design(operation, locked, self.request)
            operation['after']['classPath'] = '/Script/UMG.UserWidget'
            with self.assertRaises(common.ArtError) as caught:
                pipeline._check_design(operation, locked, self.request)
            self.assertEqual('design.structure', caught.exception.code)
        finally:
            assert directory.resolve().is_relative_to(base.resolve())
            shutil.rmtree(directory)

    def test_bound_source_nodes_use_child_class_for_container_placeholder(self):
        self.layout['nodes'][1]['role'] = 'container.canvas'
        base = common.PLUGIN_ROOT.parent / 'test-runs'
        directory = base / ('catalog-container-' + uuid.uuid4().hex)
        directory.mkdir(parents=True)
        try:
            layout_path, req_path, bundle_path = [directory / n for n in ('layout.json', 'requirement.json', 'bundle.json')]
            common.write_json(layout_path, self.layout)
            self.target.update(layoutSpecPath='layout.json', layoutSpecSha256=common.sha256(layout_path))
            common.write_json(req_path, self.requirement)
            common.write_json(bundle_path, self.bundle)
            self.request['baseline'] = {'bundle': common.binding(bundle_path), 'requirement': common.binding(req_path)}
            locked = pipeline._source_nodes(self.request, directory / 'request.json')
            self.assertEqual(CHILD_CLASS, locked[(SCREEN, 'WgtChild')]['classPath'])
        finally:
            assert directory.resolve().is_relative_to(base.resolve())
            shutil.rmtree(directory)

    def test_pending_requirement_still_stops_source_nodes(self):
        self.requirement['reviewGate']['status'] = 'pending'
        self.request['baseline'] = {'bundle': {}, 'requirement': {}}
        with patch.object(pipeline, 'bound_path', return_value=Path('synthetic-bundle.json')), \
                patch.object(pipeline, 'load_json', return_value=self.bundle), \
                patch.object(pipeline, 'read_bound', return_value=self.requirement):
            with self.assertRaises(common.ArtError) as caught:
                pipeline._source_nodes(self.request, Path('synthetic-request.json'))
        self.assertEqual('design.not_accepted', caught.exception.code)

    def test_unknown_role_without_integration_rejected(self):
        self.bundle['crossAssetOperations'] = []
        self.rejected('design.child_unauthorized')

    def test_entry_class_is_not_widget_authorization(self):
        self.op.update(type='entry-widget-class', integrationStrategy='set-entry-widget-class')
        self.rejected('design.child_unauthorized')

    def test_mixed_operation_type_and_strategy_rejected(self):
        for key, value in (('type', 'entry-widget-class'), ('integrationStrategy', 'set-entry-widget-class')):
            original = self.op[key]
            self.op[key] = value
            self.rejected('design.child_operation')
            self.op[key] = original

    def test_duplicate_operation_rejected(self):
        self.bundle['crossAssetOperations'].append(copy.deepcopy(self.op))
        self.rejected('design.child_operation')

    def test_missing_or_duplicate_mapping_rejected(self):
        for mappings in ([], [self.mapping, copy.deepcopy(self.mapping)]):
            self.bundle['nodeMappings'] = mappings
            self.rejected('design.child_mapping')

    def test_wrong_mapping_asset_or_node_rejected(self):
        for key in ('assetId', 'layoutNodeId'):
            old = self.mapping[key]
            self.mapping[key] = 'wrong'
            self.rejected('design.child_mapping')
            self.mapping[key] = old

    def test_empty_mapping_references_rejected(self):
        self.mapping['requirementRefs'] = []
        self.rejected('design.child_mapping')

    def test_unreviewed_or_pending_claim_rejected(self):
        self.requirement['reviewGate']['acceptedClaimIds'] = []
        self.rejected('design.child_claims')
        self.requirement['reviewGate']['acceptedClaimIds'] = ['claim']
        self.requirement['claims'][0]['status'] = 'pending'
        self.rejected('design.child_claims')

    def test_mapping_and_operation_claims_each_required(self):
        for item in (self.mapping, self.op):
            item['claimIds'] = []
            self.rejected('design.child_claims')
            item['claimIds'] = ['claim']

    def test_missing_source_or_wrong_kind_or_missing_dependency_rejected(self):
        self.op['sourceAssetId'] = 'absent'
        self.rejected('design.child_source')
        self.op['sourceAssetId'] = 'child'
        self.source['assetKind'] = 'list-entry'
        self.rejected('design.child_source')
        self.source['assetKind'] = 'child-widget'
        self.target['dependsOnAssetIds'] = []
        self.rejected('design.child_source')

    def test_both_assets_must_be_in_art_scope(self):
        for path in (SCREEN, CHILD):
            self.request['scope'] = [{'assetPath': path}]
            self.rejected('design.child_scope')

    def test_source_assetplan_identity_and_scope_locked(self):
        plan = self.requirement['assetPlan'][0]
        for key, value in (('assetPath', '/Game/UI/Other'), ('assetKind', 'list-entry'), ('inBuildScope', False)):
            old = plan[key]
            plan[key] = value
            self.rejected('design.child_scope')
            plan[key] = old

    def test_duplicate_asset_or_plan_identity_rejected(self):
        for records in (self.bundle['assets'], self.requirement['assetPlan']):
            records.append(copy.deepcopy(records[0]))
            self.rejected('design.child_identity')
            records.pop()

    def test_unknown_target_or_duplicate_layout_node_rejected(self):
        self.op['targetLayoutNodeId'] = 'absent'
        self.rejected('design.child_operation')
        self.op['targetLayoutNodeId'] = 'child-node'
        self.layout['nodes'].append(copy.deepcopy(self.layout['nodes'][1]))
        self.rejected('design.child_identity')

    def test_non_leaf_or_root_target_rejected(self):
        self.layout['nodes'].append({'id': 'grandchild', 'role': 'text.label', 'parent': 'child-node'})
        self.rejected('design.child_leaf')
        self.layout['nodes'].pop()
        self.layout['nodes'][1]['parent'] = None
        self.rejected('design.child_leaf')

    def test_known_role_cannot_be_overridden(self):
        self.layout['nodes'][1]['role'] = 'visual.image'
        self.rejected('design.child_class')

    def test_container_placeholder_can_be_replaced_by_child_widget(self):
        self.layout['nodes'][1]['role'] = 'container.canvas'
        result = self.derive()
        child_role = result['nodeRoleOverrides']['child-node']
        component = next(item for item in result['components'] if item['role'] == child_role)
        self.assertEqual(CHILD_CLASS, component['classPath'])
        self.assertFalse(component['isPanel'])
        self.assertTrue(component['canRepresentRegion'])
        self.assertEqual([], component['allowedChildren'])
        self.assertEqual({}, component['propertyMap'])

    def test_known_matching_role_is_preserved(self):
        self.catalog['components'].append({'role': 'widget.synthetic-child', 'classPath': CHILD_CLASS,
                                           'isPanel': False, 'allowedChildren': [], 'propertyMap': {}})
        self.assertEqual(self.catalog, self.derive())

    def test_second_use_of_new_role_requires_its_own_operation(self):
        self.layout['nodes'].append(dict(self.layout['nodes'][1], id='second'))
        self.rejected('design.child_unauthorized')

    def test_conflicting_classes_for_same_local_role_rejected(self):
        self.layout['nodes'].append(dict(self.layout['nodes'][1], id='second'))
        other = dict(self.source, id='other', assetPlanId='other', assetPath='/Game/UI/AIPrototype/uw_other')
        self.bundle['assets'].append(other)
        self.requirement['assetPlan'].append(dict(other, inBuildScope=True))
        self.request['scope'].append({'assetPath': other['assetPath']})
        self.target['dependsOnAssetIds'].append('other')
        self.bundle['nodeMappings'].append(dict(self.mapping, layoutNodeId='second'))
        self.bundle['crossAssetOperations'].append(dict(self.op, id='second', sourceAssetId='other', targetLayoutNodeId='second'))
        self.rejected('design.child_class')

    def test_role_does_not_leak_to_another_asset(self):
        self.derive()
        self.target = dict(self.target, id='another-target')
        self.rejected('design.child_unauthorized')

    def test_two_assets_can_bind_same_local_role_to_their_own_exact_sources(self):
        first = self.derive()
        other = dict(self.source, id='other', assetPlanId='other', assetPath='/Game/UI/AIPrototype/uw_other')
        host = dict(self.target, id='other-host', assetPlanId='other-host', assetPath='/Game/UI/AIPrototype/umg_ai_other',
                    dependsOnAssetIds=['other'])
        self.bundle['assets'].extend([other, host])
        self.requirement['assetPlan'].extend([dict(other, inBuildScope=True), dict(host, inBuildScope=True)])
        self.request['scope'].extend([{'assetPath': a['assetPath']} for a in (other, host)])
        self.bundle['nodeMappings'].append(dict(self.mapping, assetId='other-host'))
        self.bundle['crossAssetOperations'].append(dict(self.op, id='other-op', sourceAssetId='other', targetAssetId='other-host'))
        self.target = host
        second = self.derive()
        self.assertEqual(CHILD_CLASS, first['components'][-1]['classPath'])
        self.assertEqual('/Game/UI/AIPrototype/uw_other.uw_other_C', second['components'][-1]['classPath'])

    def test_default_catalog_path_unchanged(self):
        self.layout['nodes'][1].update(role='container.canvas', name='PanelChild')
        self.bundle['crossAssetOperations'] = []
        self.assertEqual(self.catalog, self.derive())


if __name__ == '__main__':
    unittest.main()
