#!/usr/bin/env python3
"""Accepted Button visual ownership survives concrete layout lowering."""

import unittest

import test_build_bundle_image_composition as image_composition_tests
from test_build_bundle_image_composition import error_codes, find_by_id
from validate_build_bundle import _validate_button_visual_ownership


def fixture():
    def element(identity, kind, parent):
        return {"id": identity, "kind": kind, "parentElementId": parent, "inBuildScope": True, "claimIds": ["accepted"]}

    requirement = {"reviewGate": {"status": "accepted"}, "uiModel": {"elements": [
        element("region", "panel", None),
        element("action", "button", "region"),
        element("content", "panel", "action"),
        element("art", "image", "content"),
        element("label", "text", "content"),
        element("heading", "text", "region"),
        element("help", "button", "region"),
        element("help-art", "image", "help"),
    ]}}
    nodes = {
        "region": {"role": "container.canvas", "parent": None},
        "action": {"role": "input.button", "parent": "region", "name": "ArbitraryAction"},
        "content": {"role": "container.canvas", "parent": "action"},
        "art": {"role": "visual.image", "parent": "content", "name": "NotNamedForOwner"},
        "label": {"role": "text.label", "parent": "content"},
        "heading": {"role": "text.label", "parent": "region", "zOrder": 50},
        "help": {"role": "input.button", "parent": "region", "name": "IndependentInput"},
        "help-art": {"role": "visual.image", "parent": "help"},
    }
    bundle = {"nodeMappings": [
        {"assetId": "screen", "layoutNodeId": identity, "requirementRefs": [identity]}
        for identity in nodes
    ], "crossAssetOperations": [], "reuseRelations": []}
    return requirement, bundle, {"screen": nodes}


class ButtonOwnershipTests(unittest.TestCase):
    def validate(self, requirement, bundle, records):
        return _validate_button_visual_ownership(bundle, requirement, {"accepted"}, records)

    def test_independent_region_heading_and_help_remain_valid(self):
        self.assertEqual(self.validate(*fixture()), [])

    def test_image_and_text_outside_explicit_owner_are_rejected(self):
        for identity in ("art", "label"):
            with self.subTest(identity=identity):
                requirement, bundle, records = fixture()
                records["screen"][identity]["parent"] = "region"
                errors = self.validate(requirement, bundle, records)
                self.assertEqual([error["code"] for error in errors], ["mapping.button_visual_owner"])
                self.assertIn(identity, errors[0]["message"])
                self.assertIn("action", errors[0]["message"])

    def test_wrong_help_owner_and_nested_input_cannot_claim_outer_button(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                requirement, bundle, records = fixture()
                records["screen"]["art"]["parent"] = "help"
                if nested:
                    records["screen"]["help"]["parent"] = "content"
                self.assertEqual(len(self.validate(requirement, bundle, records)), 1)

    def test_unaccepted_or_unscoped_parent_chain_does_not_infer_ownership(self):
        for change in ({"claimIds": ["unaccepted"]}, {"inBuildScope": False}, {"parentElementId": None}):
            with self.subTest(change=change):
                requirement, bundle, records = fixture()
                find_by_id(requirement["uiModel"]["elements"], "content").update(change)
                records["screen"]["art"]["parent"] = "region"
                self.assertEqual(self.validate(requirement, bundle, records), [])

    @staticmethod
    def child_fixture():
        requirement, bundle, records = fixture()
        art = records["screen"].pop("art")
        art["parent"] = "child-root"
        records["child"] = {"child-root": {"role": "screen.root", "parent": None}, "art": art}
        next(mapping for mapping in bundle["nodeMappings"] if mapping["layoutNodeId"] == "art")["assetId"] = "child"
        records["screen"]["host"] = {"role": "container.canvas", "parent": "content", "name": "ChildHost"}
        bundle["crossAssetOperations"] = [{"type": "child-widget-integration", "sourceAssetId": "child", "targetAssetId": "screen", "targetLayoutNodeId": "host"}]
        return requirement, bundle, records

    def test_child_widget_and_entry_class_boundaries_preserve_ownership(self):
        for operation_type in ("child-widget-integration", "entry-widget-class"):
            with self.subTest(operation_type=operation_type):
                requirement, bundle, records = self.child_fixture()
                bundle["crossAssetOperations"][0]["type"] = operation_type
                self.assertEqual(self.validate(requirement, bundle, records), [])
                records["screen"]["host"]["parent"] = "help"
                self.assertEqual(len(self.validate(requirement, bundle, records)), 1)

    def test_nested_child_widget_paths_are_checked(self):
        requirement, bundle, records = self.child_fixture()
        records["middle"] = {"host": {"role": "container.canvas", "parent": None}}
        bundle["crossAssetOperations"][0]["targetAssetId"] = "middle"
        bundle["crossAssetOperations"].append({"type": "child-widget-integration", "sourceAssetId": "middle", "targetAssetId": "screen", "targetLayoutNodeId": "host"})
        self.assertEqual(self.validate(requirement, bundle, records), [])
        records["screen"]["host"]["parent"] = "region"
        self.assertEqual(len(self.validate(requirement, bundle, records)), 1)

    def test_shared_instances_accept_each_mapped_owner_but_reject_wrong_host(self):
        requirement, bundle, records = self.child_fixture()
        records["screen"]["another-action"] = {"role": "input.button", "parent": "region"}
        bundle["nodeMappings"].append({"assetId": "screen", "layoutNodeId": "another-action", "requirementRefs": ["action"]})
        bundle["crossAssetOperations"].append({"type": "child-widget-integration", "sourceAssetId": "child", "targetAssetId": "screen", "targetLayoutNodeId": "another-action"})
        self.assertEqual(self.validate(requirement, bundle, records), [])
        bundle["crossAssetOperations"][-1]["targetLayoutNodeId"] = "help"
        self.assertEqual(len(self.validate(requirement, bundle, records)), 1)

    def test_unrelated_shared_consumers_do_not_reassign_this_owner(self):
        requirement, bundle, records = self.child_fixture()
        records["other-screen"] = {"host": {"role": "container.canvas", "parent": None}}
        bundle["crossAssetOperations"].append({"type": "child-widget-integration", "sourceAssetId": "child", "targetAssetId": "other-screen", "targetLayoutNodeId": "host"})
        self.assertEqual(self.validate(requirement, bundle, records), [])

    def test_existing_widget_tree_instance_placement_is_followed(self):
        requirement, bundle, records = self.child_fixture()
        bundle["crossAssetOperations"] = []
        bundle["reuseRelations"] = [{"type": "widget-tree-instance", "sourceAssetId": "child", "targetAssetId": "screen", "targetAssetPath": "/Game/UI/umg_test", "placementContract": {"slot": {
            "parentWidgetName": "ChildHost", "parentTreePath": "/Game/UI/umg_test.umg_test:WidgetTree.ChildHost",
        }}}]
        self.assertEqual(self.validate(requirement, bundle, records), [])
        records["screen"]["host"]["parent"] = "help"
        self.assertEqual(len(self.validate(requirement, bundle, records)), 1)

    def test_inherited_owner_without_concrete_node_defers_to_reuse_validation(self):
        requirement, bundle, records = fixture()
        bundle["nodeMappings"] = [mapping for mapping in bundle["nodeMappings"] if mapping["layoutNodeId"] != "action"]
        bundle["reuseRelations"] = [{"type": "class-settings-parent-class", "sourceAssetId": "prototype", "targetAssetId": "screen", "requirementRefs": ["action"]}]
        self.assertEqual(self.validate(requirement, bundle, records), [])

    def test_relation_does_not_exempt_wrong_concrete_mapping(self):
        requirement, bundle, records = fixture()
        bundle["reuseRelations"] = [{"type": "class-settings-parent-class", "sourceAssetId": "prototype", "targetAssetId": "screen", "requirementRefs": ["action"]}]
        records["screen"]["art"]["parent"] = "help"
        self.assertEqual(len(self.validate(requirement, bundle, records)), 1)

    def test_owner_without_button_mapping_or_explicit_reuse_is_rejected(self):
        requirement, bundle, records = fixture()
        records["screen"]["action"]["role"] = "container.canvas"
        errors = self.validate(requirement, bundle, records)
        self.assertEqual([error["code"] for error in errors], ["mapping.button_owner_missing"] * 2)

    def test_unrelated_reuse_binding_cannot_supply_missing_owner(self):
        requirement, bundle, records = fixture()
        records["screen"]["action"]["role"] = "container.canvas"
        bundle["reuseRelations"] = [{"type": "class-settings-parent-class", "sourceAssetId": "prototype", "targetAssetId": "other-screen", "requirementRefs": ["action"]}]
        self.assertEqual(len(self.validate(requirement, bundle, records)), 2)

    def test_unaccepted_requirement_is_not_interpreted(self):
        requirement, bundle, records = fixture()
        requirement["reviewGate"]["status"] = "pending"
        records["screen"]["art"]["parent"] = "help"
        self.assertEqual(self.validate(requirement, bundle, records), [])


class ButtonOwnershipBundleIntegrationTests(unittest.TestCase):
    def test_real_bundle_gate_runs_without_image_composition_policy(self):
        fixture_test = image_composition_tests.BuildBundleImageCompositionTests()
        fixture_test.setUp()
        report = fixture_test._validate(policy_enabled=False)
        self.assertTrue(report["valid"], report["errors"])

        def move_visual(_requirement, _bundle, child_layout, _screen_layout):
            find_by_id(child_layout["nodes"], "node-tab-selected-background")["parent"] = "node-child-region"

        report = fixture_test._validate(move_visual, policy_enabled=False)
        self.assertIn("mapping.button_visual_owner", error_codes(report))


if __name__ == "__main__":
    unittest.main()
