"""Opt-in shared state/initial state and content-height host regressions."""
import copy
import unittest
from pathlib import Path

from _contract_common import ASSETS_ROOT, load_json, validate_schema_instance
from _bundle_capabilities import CONTENT_HEIGHT, CONTENT_HEIGHT_V2, SHARED_STATES, content_proof_capability_errors, initial_refs, planned_size_proofs, validate_content_height, validate_shared_states
import test_build_bundle_quality_contracts as legacy_fixture
try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


def codes(errors):
    return {error["code"] for error in errors}


def fixture():
    states = ["state.popup.shown", "state.popup.hidden"]
    changes = ["SelfHitTestInvisible", "Collapsed"]
    model = {
        "id": "model.popup",
        "axes": [{"id": "axis.visibility", "exclusive": True,
                  "states": [{"id": sid, "inBuildScope": True, "composition": {"mode": "node-overrides", "elementIds": ["element.host"]}} for sid in states]}],
        "implementation": {"strategy": "shared-tree-properties", "sharedRootElementId": "element.host",
                           "stateOverrides": [{"stateId": sid, "changes": [{"elementId": "element.host", "property": "visibility", "value": value}]} for sid, value in zip(states, changes)]},
        "stateAssignments": [{"elementId": "element.host", "axisStateIds": [states[1]]}],
    }
    requirement = {"uiModel": {"elements": [{"id": "element.host"}]}, "stateModels": [model],
                   "assetPlan": [{"id": "plan.screen", "coversStateModelIds": [model["id"]], "coversElementIds": ["element.host"]}]}
    assets = {"screen": {"assetKind": "screen", "assetPlanId": "plan.screen"}, "child": {"assetKind": "child-widget"}}
    mapping = {"id": "mapping.host", "assetId": "screen", "layoutNodeId": "host", "mappingKind": "composite-state", "requirementRefs": ["element.host"], "stateRefs": states, "initialStateRefs": [states[1]]}
    handling = {"strategy": "owning-screen-shared-properties", "stateRefs": states, "initialStateRefs": [states[1]],
                "propertyBindings": [{"stateRef": sid, "elementId": "element.host", "property": "Visibility", "value": value} for sid, value in zip(states, changes)]}
    operation = {"type": "child-widget-integration", "sourceAssetId": "child", "targetAssetId": "screen", "targetLayoutNodeId": "host", "stateHandling": handling}
    bundle = {"capabilities": [SHARED_STATES], "nodeMappings": [mapping], "crossAssetOperations": [operation]}
    nodes = {"screen": {"host": {"isVariable": True, "properties": {"visibility": "Collapsed"}}}}
    return bundle, requirement, assets, nodes


class SharedStateTests(unittest.TestCase):
    def setUp(self):
        self.bundle, self.requirement, self.assets, self.nodes = fixture()

    def check(self):
        return validate_shared_states(self.bundle, self.requirement, self.assets, self.nodes)

    def test_one_shared_host_supports_both_states_with_one_initial_state(self):
        self.assertEqual(self.check(), [])
        self.assertEqual(initial_refs(self.bundle, self.bundle["nodeMappings"][0]), ["state.popup.hidden"])

    def test_canonical_visibility_spelling_lowers_to_actual_property(self):
        for override in self.requirement["stateModels"][0]["implementation"]["stateOverrides"]:
            override["changes"][0]["property"] = "Visibility"
        self.assertEqual(self.check(), [])

    def test_other_model_composition_does_not_invent_a_direct_initial_assignment(self):
        self.bundle["crossAssetOperations"] = []
        model = {"id": "model.parent", "axes": [{"id": "axis.parent", "exclusive": True,
            "states": [{"id": "state.parent", "inBuildScope": True,
                        "composition": {"elementIds": ["element.parent", "element.host"]}}]}],
            "implementation": {"strategy": "shared-tree-properties"},
            "stateAssignments": [{"elementId": "element.parent", "axisStateIds": ["state.parent"]}]}
        self.requirement["stateModels"].append(model)
        self.requirement["uiModel"]["elements"].append({"id": "element.parent"})
        plan = self.requirement["assetPlan"][0]
        plan["coversStateModelIds"].append("model.parent")
        plan["coversElementIds"].append("element.parent")
        self.bundle["nodeMappings"][0]["stateRefs"].append("state.parent")
        self.bundle["nodeMappings"].append({"assetId": "screen", "layoutNodeId": "parent",
            "mappingKind": "composite-state", "requirementRefs": ["element.parent"],
            "stateRefs": ["state.parent"], "initialStateRefs": ["state.parent"]})
        self.assertEqual(self.check(), [])
        self.bundle["nodeMappings"][0]["initialStateRefs"].append("state.parent")
        self.assertIn("state.initial_assignment", codes(self.check()))

    def test_visibility_alias_is_not_arbitrary_case_folding(self):
        self.requirement["stateModels"][0]["implementation"]["stateOverrides"][0]["changes"][0]["property"] = "VISIBILITY"
        self.assertIn("state.shared_property", codes(self.check()))

    def test_capability_is_required(self):
        self.bundle.pop("capabilities")
        self.assertIn("capability.required", codes(self.check()))

    def test_initial_assignment_is_not_supported_state_union(self):
        self.bundle["nodeMappings"][0]["initialStateRefs"].append("state.popup.shown")
        self.assertTrue({"state.initial_assignment", "state.initial_exclusive"}.issubset(codes(self.check())))

    def test_initial_must_be_supported(self):
        self.bundle["nodeMappings"][0]["stateRefs"] = ["state.popup.shown"]
        self.assertIn("state.initial_subset", codes(self.check()))

    def test_initial_unknown_is_rejected(self):
        self.bundle["nodeMappings"][0]["initialStateRefs"] = ["state.missing"]
        self.assertIn("state.initial_unknown", codes(self.check()))

    def test_each_supported_axis_requires_initial_assignment(self):
        model = self.requirement["stateModels"][0]
        model["axes"].append({"id": "axis.enabled", "exclusive": True, "states": [{"id": "state.enabled", "inBuildScope": True, "composition": {"elementIds": ["element.host"]}}]})
        self.bundle["nodeMappings"][0]["stateRefs"].append("state.enabled")
        self.assertIn("state.initial_axes", codes(self.check()))

    def test_initial_missing_and_assignment_duplicate_are_rejected(self):
        self.bundle["nodeMappings"][0].pop("initialStateRefs")
        self.assertIn("state.initial_assignment", codes(self.check()))
        self.requirement["stateModels"][0]["stateAssignments"] *= 2
        self.assertIn("state.initial_assignment", codes(self.check()))

    def test_repeated_nodes_cannot_fake_shared_coverage(self):
        duplicate = copy.deepcopy(self.bundle["nodeMappings"][0])
        duplicate["layoutNodeId"] = "second-host"
        self.bundle["nodeMappings"].append(duplicate)
        self.assertIn("state.composition_unique", codes(self.check()))

    def test_every_composition_element_must_be_mapped(self):
        self.requirement["stateModels"][0]["axes"][0]["states"][0]["composition"]["elementIds"].append("element.missing")
        self.assertIn("state.composition_unique", codes(self.check()))

    def test_foreign_element_and_owner_are_rejected(self):
        self.requirement["uiModel"]["elements"].append({"id": "element.foreign"})
        self.bundle["nodeMappings"][0]["requirementRefs"].append("element.foreign")
        self.assertTrue({"state.supported_composition", "state.supported_owner"}.issubset(codes(self.check())))

    def test_wrong_asset_owner_rejected(self):
        self.requirement["assetPlan"][0]["coversStateModelIds"] = []
        self.assertIn("state.supported_owner", codes(self.check()))

    def test_host_property_must_be_real_accepted_override(self):
        self.bundle["crossAssetOperations"][0]["stateHandling"]["propertyBindings"][0]["value"] = "Collapsed"
        self.assertIn("state.shared_bindings", codes(self.check()))

    def test_missing_binding_and_non_variable_host_rejected(self):
        self.bundle["crossAssetOperations"][0]["stateHandling"]["propertyBindings"].pop()
        self.nodes["screen"]["host"]["isVariable"] = False
        self.assertTrue({"state.shared_bindings", "state.shared_variable"}.issubset(codes(self.check())))

    def test_host_initial_property_must_match_layout(self):
        self.nodes["screen"]["host"]["properties"]["visibility"] = "SelfHitTestInvisible"
        self.assertIn("state.shared_initial_property", codes(self.check()))

    def test_exclusive_branches_cannot_use_shared_strategy(self):
        self.requirement["stateModels"][0]["implementation"]["strategy"] = "exclusive-panel-branches"
        self.assertIn("state.shared_contract", codes(self.check()))

    def test_instance_parameter_cannot_be_invented(self):
        self.requirement["stateModels"][0]["implementation"]["stateOverrides"][0]["changes"][0]["property"] = "inventedStateParameter"
        self.assertIn("state.shared_property", codes(self.check()))

    def test_source_child_cannot_claim_host_state(self):
        other = copy.deepcopy(self.bundle["nodeMappings"][0]); other["assetId"] = "child"
        self.bundle["nodeMappings"].append(other)
        self.assertIn("state.shared_source_tree", codes(self.check()))


def content_fixture():
    nodes = [
        {"id": "root", "role": "screen.root"},
        {"id": "content", "parent": "root", "role": "container.vertical", "slotLayout": {"autoSize": True, "anchors": {"minimum": [0, 0], "maximum": [0, 0]}},
         "contentSizeProof": {"kind": "layout-dependency/1", "minimumDesiredSize": [368, 416], "sourceNodeIds": ["header", "body"], "evidenceId": "ev.content-size"}},
    ]
    for name, height in (("header", 58), ("body", 358)):
        nodes.append({"id": name, "parent": "content", "role": "visual.image", "properties": {"brushImageSize": [368, height]}, "flowSlot": {"size": {"rule": "Auto"}, "padding": [0, 0, 0, 0]}})
    layout = {"referenceSize": [368, 416], "nodes": nodes}
    host = {"slotLayout": {"autoSize": True, "anchors": {"minimum": [0.5, 0.5], "maximum": [0.5, 0.5]}}}
    op = {"placementContract": {"hostSize": [367, 517], "sizingStrategy": "content-driven", "slot": {"containerType": "CanvasPanel"},
                                "childSizingCompatibility": {"mode": "fixed-width-content-height", "axes": ["horizontal", "vertical"], "sourceLayoutNodeIds": ["content"], "fixedWidth": 368}}}
    return {"capabilities": [CONTENT_HEIGHT]}, op, layout, host


class ContentHeightTests(unittest.TestCase):
    def setUp(self):
        self.bundle, self.op, self.layout, self.host = content_fixture()

    def check(self):
        return validate_content_height(self.bundle, self.op, "$.op", self.layout, self.host)

    def test_content_height_is_not_vertical_stretch_or_nominal_host_rect(self):
        self.assertEqual(self.check(), [])
        self.assertNotIn("measuredDesiredSize", planned_size_proofs(self.layout)[0])

    def test_no_opt_in_rejected(self):
        self.bundle.clear()
        self.assertIn("capability.required", codes(self.check()))

    def test_host_fixed_size_and_stretch_rejected(self):
        self.host["slotLayout"]["autoSize"] = False
        self.assertIn("operation.child_content_host", codes(self.check()))
        self.host["slotLayout"]["autoSize"] = True
        self.host["slotLayout"]["anchors"]["maximum"] = [1, 1]
        self.assertIn("operation.child_content_host", codes(self.check()))

    def test_wrong_width_or_fake_proof_rejected(self):
        self.op["placementContract"]["childSizingCompatibility"]["fixedWidth"] = 400
        self.assertIn("operation.child_content_proof", codes(self.check()))
        self.op["placementContract"]["childSizingCompatibility"]["fixedWidth"] = 368
        self.layout["nodes"][2]["properties"]["brushImageSize"] = [368, 20]
        self.assertIn("operation.child_content_proof", codes(self.check()))

    def test_unrelated_source_node_rejected(self):
        self.op["placementContract"]["childSizingCompatibility"]["sourceLayoutNodeIds"] = ["body"]
        self.assertIn("operation.child_content_proof", codes(self.check()))

    def test_minimum_width_does_not_prove_fixed_width(self):
        self.layout["nodes"].append({"id": "text", "parent": "content", "role": "text.label", "properties": {"text": "dynamic", "wrapTextAt": 500}, "flowSlot": {"size": {"rule": "Auto"}, "padding": [0, 0, 0, 0]}})
        self.assertIn("operation.child_content_width", codes(self.check()))
        self.layout["nodes"][-1]["properties"]["wrapTextAt"] = 368
        self.assertEqual(self.check(), [])
        self.layout["nodes"][-1]["properties"].pop("wrapTextAt")
        self.assertIn("operation.child_content_width", codes(self.check()))

    def test_uncited_root_sibling_cannot_enlarge_desired_width(self):
        self.layout["nodes"].append({"id": "foreign", "parent": "root", "role": "visual.image", "properties": {"brushImageSize": [900, 100]}, "slotLayout": {"autoSize": True, "anchors": {"minimum": [0, 0], "maximum": [0, 0]}}})
        self.assertIn("operation.child_content_root", codes(self.check()))

    def test_root_offset_or_alignment_cannot_change_desired_size(self):
        slot = self.layout["nodes"][1]["slotLayout"]
        slot["offsets"] = {"left": 30, "top": 0}
        self.assertIn("operation.child_content_root", codes(self.check()))
        slot["offsets"]["left"] = 0
        slot["alignment"] = [0.5, 0]
        self.assertIn("operation.child_content_root", codes(self.check()))


class CapabilitySchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = load_json(ASSETS_ROOT / "ui-build-bundle.schema.json")
        self.bundle = load_json(ASSETS_ROOT / "example-composite-tabs-build-bundle.json")

    def test_unknown_duplicate_flags_rejected(self):
        self.bundle["capabilities"] = ["unknown/1"]
        self.assertTrue(validate_schema_instance(self.bundle, self.schema))
        self.bundle["capabilities"] = [SHARED_STATES, SHARED_STATES]
        self.assertTrue(validate_schema_instance(self.bundle, self.schema))

    def test_new_mapping_field_requires_opt_in_at_schema_level(self):
        if Draft202012Validator is None:
            self.skipTest("Full JSON Schema conditional check; semantic capability gates are tested without dependencies.")
        self.bundle["nodeMappings"][0]["initialStateRefs"] = ["state-tab-selected"]
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.bundle))
        self.bundle["capabilities"] = [SHARED_STATES]
        self.assertTrue(Draft202012Validator(self.schema).is_valid(self.bundle))

    def test_new_sizing_and_strategy_require_opt_in_at_schema_level(self):
        if Draft202012Validator is None:
            self.skipTest("Full JSON Schema conditional check; semantic capability gates are tested without dependencies.")
        op = self.bundle["crossAssetOperations"][0]
        op["stateHandling"] = fixture()[0]["crossAssetOperations"][0]["stateHandling"]
        op["placementContract"]["childSizingCompatibility"] = content_fixture()[1]["placementContract"]["childSizingCompatibility"]
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.bundle))
        self.bundle["capabilities"] = [SHARED_STATES, CONTENT_HEIGHT]
        self.assertTrue(Draft202012Validator(self.schema).is_valid(self.bundle))

    def test_legacy_bundle_remains_valid_with_flags_but_without_new_fields(self):
        test = legacy_fixture.BuildBundleQualityContractsTests(); test.setUp()
        test.bundle["capabilities"] = [SHARED_STATES, CONTENT_HEIGHT]
        result = test.validate_bundle(test.bundle)
        self.assertTrue(result["valid"], result["errors"])

    def test_v2_flag_valid_but_mixed_versions_rejected(self):
        self.bundle["capabilities"] = [CONTENT_HEIGHT_V2]
        self.assertTrue(Draft202012Validator(self.schema).is_valid(self.bundle))
        self.bundle["capabilities"].append(CONTENT_HEIGHT)
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.bundle))
        test = legacy_fixture.BuildBundleQualityContractsTests(); test.setUp()
        test.bundle["capabilities"] = [CONTENT_HEIGHT, CONTENT_HEIGHT_V2]
        self.assertIn("capability.conflict", codes(test.validate_bundle(test.bundle)["errors"]))


def content_v2_fixture():
    bundle, op, layout, host = content_fixture()
    width = 457.3333333333333
    bundle["capabilities"] = [CONTENT_HEIGHT_V2]
    layout["referenceSize"][0] = 458
    content = layout["nodes"][1]
    proof = content.pop("contentSizeProof")
    proof.update(kind="layout-dependency/2", minimumDesiredSize=[width, 416])
    slot = content.pop("slotLayout")
    content["parent"] = "width"
    content["sizeBoxSlot"] = {"padding": [0, 0, 0, 0], "horizontalAlignment": "Fill", "verticalAlignment": "Fill"}
    layout["nodes"].insert(1, {"id": "width", "parent": "root", "role": "container.size", "slotLayout": slot,
        "sizeBoxConstraints": {"version": 1, "widthOverride": width, "heightOverride": None}, "contentSizeProof": proof})
    for node in layout["nodes"]:
        if "flowSlot" in node:
            node["flowSlot"].update(horizontalAlignment="Fill", verticalAlignment="Top")
    op["placementContract"]["childSizingCompatibility"].update(fixedWidth=width, sourceLayoutNodeIds=["width"])
    return bundle, op, layout, host


class ContentHeightV2Tests(unittest.TestCase):
    def setUp(self):
        self.bundle, self.op, self.layout, self.host = content_v2_fixture()

    def check(self):
        return validate_content_height(self.bundle, self.op, "$.op", self.layout, self.host)

    def test_exact_runtime_width_differs_from_integer_reference_envelope(self):
        self.assertEqual(self.check(), [])
        proof = planned_size_proofs(self.layout, CONTENT_HEIGHT_V2)[0]
        self.assertEqual(proof["minimumDesiredSize"][0], 457.3333333333333)
        self.assertNotIn("measuredDesiredSize", proof)
        self.assertEqual(planned_size_proofs(self.layout, CONTENT_HEIGHT), [])

    def test_ceil_is_exact_not_an_arbitrary_slack_range(self):
        for reference in (457, 459, 457.3333333333333):
            self.layout["referenceSize"][0] = reference
            self.assertIn("operation.child_content_proof", codes(self.check()))
        self.layout["referenceSize"][0] = 458
        self.op["placementContract"]["childSizingCompatibility"]["fixedWidth"] += 1e-9
        self.assertIn("operation.child_content_proof", codes(self.check()))

    def test_v2_cannot_launder_through_v1_or_missing_capability(self):
        for caps in ([], [CONTENT_HEIGHT], [CONTENT_HEIGHT, CONTENT_HEIGHT_V2]):
            self.bundle["capabilities"] = caps
            self.assertTrue(self.check())
            self.assertTrue(content_proof_capability_errors(self.bundle, self.layout, "$.layout"))

    def test_v2_flag_cannot_reinterpret_v1_proof(self):
        self.layout["nodes"][1]["contentSizeProof"]["kind"] = "layout-dependency/1"
        self.assertIn("operation.child_content_proof", codes(self.check()))

    def test_new_reference_envelope_is_not_silently_granted_to_v1(self):
        self.bundle["capabilities"] = [CONTENT_HEIGHT]
        self.layout["nodes"][1]["contentSizeProof"]["kind"] = "layout-dependency/1"
        self.assertIn("operation.child_content_proof", codes(self.check()))

    def test_real_width_authority_single_origin_and_positive_height_required(self):
        for mutate in (
            lambda n: n["width"]["sizeBoxConstraints"].update(widthOverride=None),
            lambda n: n["width"]["sizeBoxConstraints"].update(heightOverride=416),
            lambda n: n["width"]["slotLayout"].update(alignment=[0.5, 0]),
            lambda n: n["header"]["properties"].update(visibility="Hidden"),
            lambda n: n["width"]["contentSizeProof"].update(verified=True),
            lambda n: n["width"]["contentSizeProof"].update(minimumDesiredSize=[457.3333333333333, 0]),
        ):
            self.setUp()
            mutate({n["id"]: n for n in self.layout["nodes"]})
            self.assertTrue(self.check())

    def test_upper_bound_is_checked_under_fixed_width_authority(self):
        self.layout["nodes"].append({"id": "wide", "parent": "content", "role": "text.label",
            "properties": {"wrapTextAt": 900}, "flowSlot": {"size": {"rule": "Auto"}, "padding": [0, 0, 0, 0],
            "horizontalAlignment": "Fill", "verticalAlignment": "Top"}})
        self.assertTrue(self.check())

    def test_invalid_width_never_becomes_an_envelope(self):
        for value in (0, -1, True, float("nan"), float("inf"), 10**1000):
            self.op["placementContract"]["childSizingCompatibility"]["fixedWidth"] = value
            self.assertIn("operation.child_content_proof", codes(self.check()))


if __name__ == "__main__":
    unittest.main()
