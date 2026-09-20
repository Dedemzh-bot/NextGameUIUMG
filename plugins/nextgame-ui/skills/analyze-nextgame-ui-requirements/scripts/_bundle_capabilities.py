"""Opt-in Bundle capability semantics; released unopted contracts stay unchanged."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

from _contract_common import issue

SHARED_STATES = "shared-node-states/1"
CONTENT_HEIGHT = "content-driven-child-size/1"
CONTENT_HEIGHT_V2 = "content-driven-child-size/2"


def content_height_capability(bundle):
    present = [cap for cap in (CONTENT_HEIGHT, CONTENT_HEIGHT_V2) if enabled(bundle, cap)]
    return present[0] if len(present) == 1 else None


def content_proof_capability_errors(bundle, layout, path):
    errors = []
    cap = content_height_capability(bundle)
    if enabled(bundle, CONTENT_HEIGHT) and enabled(bundle, CONTENT_HEIGHT_V2):
        errors.append(issue("capability.conflict", path, "Declare exactly one content-driven-child-size version."))
    for node in layout.get("nodes", []):
        if not isinstance(node, dict):
            continue
        proof = node.get("contentSizeProof", {})
        # Preserve legacy /1 readability; only the new /2 shape adds a new gate.
        if isinstance(proof, dict) and proof.get("kind") == "layout-dependency/2" and cap != CONTENT_HEIGHT_V2:
            errors.append(issue("capability.required", path, f"layout-dependency/2 requires only {CONTENT_HEIGHT_V2}."))
    return errors


def enabled(bundle, capability):
    flags = bundle.get("capabilities", [])
    return isinstance(flags, list) and capability in flags


def initial_refs(bundle, mapping):
    value = mapping.get("initialStateRefs", []) if enabled(bundle, SHARED_STATES) and "initialStateRefs" in mapping else mapping.get("stateRefs", [])
    return value if isinstance(value, list) else []


def planned_size_proofs(layout, capability=None):
    """Return calculated plan evidence, never mark it as actual measurement."""
    path = Path(__file__).resolve().parents[2] / "build-nextgame-umg/scripts/validate_layout_spec.py"
    spec = importlib.util.spec_from_file_location("_bundle_layout_size_proof", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    helper = getattr(module, "planned_content_size_proof", None)
    if helper is None:
        return []
    nodes = {n.get("id"): n for n in layout.get("nodes", []) if isinstance(n, dict)}
    roots = {n.get("id") for n in nodes.values() if n.get("parent") is None}
    return [n["contentSizeProof"] for n in nodes.values()
            if n.get("parent") in roots and isinstance(n.get("contentSizeProof"), dict)
            and (capability is None or n["contentSizeProof"].get("kind") == ("layout-dependency/2" if capability == CONTENT_HEIGHT_V2 else "layout-dependency/1"))
            and helper(n, nodes)]


def validate_shared_states(bundle, requirement, assets, nodes_by_asset=None):
    errors = []
    opt_in = enabled(bundle, SHARED_STATES)
    mappings = [m for m in bundle.get("nodeMappings", []) if isinstance(m, dict)]
    operations = [o for o in bundle.get("crossAssetOperations", []) if isinstance(o, dict)]
    if not opt_in:
        for i, mapping in enumerate(mappings):
            if "initialStateRefs" in mapping:
                errors.append(issue("capability.required", f"$.nodeMappings[{i}].initialStateRefs", f"Requires {SHARED_STATES}."))
        for i, operation in enumerate(operations):
            handling = operation.get("stateHandling") if isinstance(operation.get("stateHandling"), dict) else {}
            if "initialStateRefs" in handling or "propertyBindings" in handling or handling.get("strategy") == "owning-screen-shared-properties":
                errors.append(issue("capability.required", f"$.crossAssetOperations[{i}].stateHandling", f"Requires {SHARED_STATES}."))
        return errors

    states, assignments, assignment_models = {}, {}, {}
    plans = {p.get("id"): p for p in requirement.get("assetPlan", [])}
    for model in requirement.get("stateModels", []):
        for axis in model.get("axes", []):
            for state in axis.get("states", []):
                states[state["id"]] = (model, axis, state)
        for assignment in model.get("stateAssignments", []):
            assignments.setdefault(assignment.get("elementId"), []).append(assignment)
            assignment_models.setdefault(assignment.get("elementId"), set()).add(model.get("id"))
    element_ids = {e.get("id") for e in requirement.get("uiModel", {}).get("elements", [])}
    for i, mapping in enumerate(mappings):
        path = f"$.nodeMappings[{i}]"
        supported = set(mapping.get("stateRefs", []))
        initial = set(initial_refs(bundle, mapping)) if "initialStateRefs" in mapping else set()
        refs = set(mapping.get("requirementRefs", []))
        assigned = refs & assignments.keys()
        shared_refs = {s for s in supported if s in states and states[s][0].get("implementation", {}).get("strategy") == "shared-tree-properties"}
        if assigned and (shared_refs or "initialStateRefs" in mapping):
            if len(assigned) != 1 or len(assignments[next(iter(assigned))]) != 1:
                errors.append(issue("state.initial_assignment", path, "One mapping must bind exactly one uniquely assigned element."))
            else:
                expected = set(assignments[next(iter(assigned))][0].get("axisStateIds", []))
                if "initialStateRefs" not in mapping or initial != expected:
                    errors.append(issue("state.initial_assignment", path, "initialStateRefs must exactly preserve the accepted stateAssignment."))
        elif not assigned and "initialStateRefs" in mapping:
            errors.append(issue("state.initial_unassigned", path, "Only a uniquely assigned requirement element may declare initialStateRefs."))
        if not initial.issubset(supported):
            errors.append(issue("state.initial_subset", path, "initialStateRefs must be a subset of supported stateRefs."))
        for state_ref in initial:
            if state_ref not in states:
                errors.append(issue("state.initial_unknown", path, f"Unknown initial state {state_ref}."))
        axes = {}
        for state_ref in initial:
            if state_ref in states:
                model, axis, _ = states[state_ref]
                axes.setdefault((model["id"], axis["id"]), []).append(state_ref)
                if axis.get("exclusive") is True and len(axes[(model["id"], axis["id"])]) > 1:
                    errors.append(issue("state.initial_exclusive", path, "An exclusive state axis permits one initial state."))
        if assigned and (shared_refs or "initialStateRefs" in mapping):
            # Composition membership can be inherited from another model's
            # parent. Only models assigning this element own its initial axes.
            direct_models = {mid for element in assigned for mid in assignment_models[element]}
            required_axes = {(states[s][0]["id"], states[s][1]["id"]) for s in supported
                             if s in states and states[s][0]["id"] in direct_models}
            if set(axes) != required_axes:
                errors.append(issue("state.initial_axes", path, "Assigned shared nodes require an initial state for every supported axis of their directly assigning model."))
        plan = plans.get(assets.get(mapping.get("assetId"), {}).get("assetPlanId"), {})
        for state_ref in supported:
            if state_ref not in states:
                continue  # Base validator reports unknown state references.
            model, _, state = states[state_ref]
            if state_ref not in shared_refs and "initialStateRefs" not in mapping:
                continue
            composition = set(state.get("composition", {}).get("elementIds", []))
            bound = refs & element_ids
            if mapping.get("mappingKind") != "composite-state" or not bound or not bound.issubset(composition):
                errors.append(issue("state.supported_composition", path, f"Every element mapped for {state_ref} must belong to its accepted composition."))
            if model["id"] not in plan.get("coversStateModelIds", []) or not bound.issubset(set(plan.get("coversElementIds", []))):
                errors.append(issue("state.supported_owner", path, f"Asset plan must own the elements and state model for {state_ref}."))
    for state_ref, (model, _, state) in states.items():
        if state.get("inBuildScope") is not True or model.get("implementation", {}).get("strategy") != "shared-tree-properties":
            continue
        for element_id in state.get("composition", {}).get("elementIds", []):
            found = [m for m in mappings if state_ref in m.get("stateRefs", []) and element_id in m.get("requirementRefs", [])]
            if len(found) != 1:
                errors.append(issue("state.composition_unique", "$.nodeMappings", f"{state_ref} composition element {element_id} requires exactly one physical mapping; found {len(found)}."))

    for i, operation in enumerate(operations):
        handling = operation.get("stateHandling") if isinstance(operation.get("stateHandling"), dict) else {}
        mapping = next((m for m in mappings if m.get("assetId") == operation.get("targetAssetId") and m.get("layoutNodeId") == operation.get("targetLayoutNodeId")), {})
        if handling and set(initial_refs(bundle, handling)) != set(initial_refs(bundle, mapping)):
            errors.append(issue("state.handling_initial", f"$.crossAssetOperations[{i}].stateHandling", "Initial handling refs must match the target mapping independently of supported stateRefs."))
        if handling.get("strategy") != "owning-screen-shared-properties":
            if "propertyBindings" in handling:
                errors.append(issue("state.shared_strategy", f"$.crossAssetOperations[{i}].stateHandling", "New host property fields require owning-screen-shared-properties."))
            continue
        path = f"$.crossAssetOperations[{i}].stateHandling"
        bound = set(mapping.get("requirementRefs", [])) & element_ids
        if operation.get("type") != "child-widget-integration" or assets.get(operation.get("targetAssetId"), {}).get("assetKind") != "screen" or assets.get(operation.get("sourceAssetId"), {}).get("assetKind") != "child-widget" or len(bound) != 1:
            errors.append(issue("state.shared_host", path, "Shared host properties require one real child instance integrated into its owning screen."))
        if set(initial_refs(bundle, handling)) != set(initial_refs(bundle, mapping)) or not handling.get("initialStateRefs"):
            errors.append(issue("state.shared_initial", path, "Host handling initial states must match the mapped accepted assignment."))
        expected = []
        for state_ref in mapping.get("stateRefs", []):
            if state_ref not in states:
                continue
            model, _, state = states[state_ref]
            impl = model.get("implementation", {})
            changes = [c for o in impl.get("stateOverrides", []) if o.get("stateId") == state_ref for c in o.get("changes", [])]
            if impl.get("strategy") != "shared-tree-properties" or impl.get("sharedRootElementId") not in bound or set(state.get("composition", {}).get("elementIds", [])) != bound or not changes:
                errors.append(issue("state.shared_contract", path, f"{state_ref} must use the accepted singleton shared-tree-properties composition."))
            for change in changes:
                if change.get("elementId") not in bound or change.get("property") not in {"visibility", "Visibility"}:
                    errors.append(issue("state.shared_property", path, "Capability /1 supports actual host Visibility only; child internals and invented parameters are forbidden."))
                expected.append({"stateRef": state_ref, "elementId": change.get("elementId"), "property": "Visibility", "value": change.get("value")})
        bindings = handling.get("propertyBindings") if isinstance(handling.get("propertyBindings"), list) else []
        bindings = [b for b in bindings if isinstance(b, dict)]
        key = lambda v: (str(v.get("stateRef")), str(v.get("elementId")), str(v.get("property")), str(v.get("value")))
        if sorted(bindings, key=key) != sorted(expected, key=key):
            errors.append(issue("state.shared_bindings", path, "Bindings must exactly lower every accepted singleton override, without duplicates or omissions."))
        if nodes_by_asset is not None:
            node = nodes_by_asset.get(operation.get("targetAssetId"), {}).get(operation.get("targetLayoutNodeId"), {})
            if node.get("isVariable") is not True:
                errors.append(issue("state.shared_variable", path, "Runtime controlled child instance must be Is Variable."))
            for binding in bindings:
                if binding.get("stateRef") in handling.get("initialStateRefs", []) and node.get("properties", {}).get("visibility") != binding.get("value"):
                    errors.append(issue("state.shared_initial_property", path, "Linked host Visibility must match the accepted initial state binding."))
        if any(set(m.get("stateRefs", [])) & set(mapping.get("stateRefs", [])) for m in mappings if m.get("assetId") == operation.get("sourceAssetId")):
            errors.append(issue("state.shared_source_tree", path, "Host visibility belongs to the target screen instance, not the source child tree."))
    return errors


def validate_content_height(bundle, operation, path, source_layout, target_node):
    placement = operation.get("placementContract", {})
    compatibility = placement.get("childSizingCompatibility", {})
    if compatibility.get("mode") != "fixed-width-content-height":
        return []
    capability = content_height_capability(bundle)
    if capability is None:
        return [issue("capability.required", path, f"Requires exactly one of {CONTENT_HEIGHT} or {CONTENT_HEIGHT_V2}.")]
    errors = content_proof_capability_errors(bundle, source_layout, path)
    slot = target_node.get("slotLayout", {})
    anchors = slot.get("anchors", {})
    if placement.get("sizingStrategy") != "content-driven" or placement.get("slot", {}).get("containerType") != "CanvasPanel" or slot.get("autoSize") is not True or not isinstance(anchors.get("minimum"), list) or anchors.get("minimum") != anchors.get("maximum"):
        errors.append(issue("operation.child_content_host", path, "Content height requires a point-anchored, auto-sized Canvas host with content-driven sizing."))
    width = compatibility.get("fixedWidth")
    proofs = planned_size_proofs(source_layout, capability)
    cited_nodes = [n for n in source_layout.get("nodes", []) if n.get("id") in compatibility.get("sourceLayoutNodeIds", [])]
    applicable = [p for n in cited_nodes if (p := n.get("contentSizeProof")) in proofs]
    try:
        valid_width = isinstance(width, (int, float)) and not isinstance(width, bool) and math.isfinite(width) and width > 0
    except (OverflowError, ValueError):
        valid_width = False
    reference = source_layout.get("referenceSize", [None])[0]
    expected_reference = math.ceil(width) if valid_width and capability == CONTENT_HEIGHT_V2 else width
    if not applicable or not valid_width or reference != expected_reference or not all(p.get("minimumDesiredSize", [None])[0] == width for p in applicable):
        errors.append(issue("operation.child_content_proof", path, "Fixed width must exactly match the cited root-direct proof width; /1 reference width equals fixedWidth, /2 integer reference width equals ceil(fixedWidth). Nominal source rect is not measured size."))
    else:
        by_id = {n.get("id"): n for n in source_layout.get("nodes", []) if isinstance(n, dict)}
        roots = [n for n in by_id.values() if n.get("parent") is None]
        root_ids = {n.get("id") for n in roots}
        root_children = [n for n in by_id.values() if n.get("parent") in root_ids and n.get("properties", {}).get("visibility") != "Collapsed"]
        # Capability /1 deliberately supports one origin-aligned content root.
        # Auditing only cited subtrees would miss other Canvas contributions.
        root_child = root_children[0] if len(root_children) == 1 else {}
        child_slot = root_child.get("slotLayout", {})
        child_anchors = child_slot.get("anchors", {})
        child_offsets = child_slot.get("offsets", {})
        if (len(roots) != 1 or roots[0].get("role") not in {"screen.root", "container.canvas"}
                or roots[0].get("properties", {}).get("visibility") == "Collapsed"
                or len(root_children) != 1 or [n.get("id") for n in cited_nodes] != [root_child.get("id")]
                or child_anchors.get("minimum") != [0, 0] or child_anchors.get("maximum") != [0, 0]
                or child_offsets.get("left", 0) != 0 or child_offsets.get("top", 0) != 0
                or child_slot.get("alignment", [0, 0]) != [0, 0]):
            errors.append(issue("operation.child_content_root", path, "Capability /1 requires exactly one visible root-direct content subtree, cited once, at zero point anchors/offsets/alignment; other Canvas contributions cannot be ignored."))
        for node in cited_nodes:
            if capability == CONTENT_HEIGHT_V2:
                proof_module_path = Path(__file__).resolve().parents[2] / "build-nextgame-umg/scripts/layout_dependencies_v2.py"
                proof_spec = importlib.util.spec_from_file_location("_bundle_dependency_v2", proof_module_path)
                proof_module = importlib.util.module_from_spec(proof_spec)
                proof_spec.loader.exec_module(proof_module)
                bounds = proof_module.dependency_bounds_v2(node, by_id)
                maximum = bounds[2] if bounds else None
            else:
                maximum = _content_width_bound(node, by_id, set())
            if maximum is None or (maximum != width if capability == CONTENT_HEIGHT_V2 else abs(maximum - width) > 0.000001):
                errors.append(issue("operation.child_content_width", path, "Every visible child must have a finite width bound (image size, explicit text wrap, and real flow/Overlay padding) equal to fixedWidth; a minimum-size proof alone cannot prove fixed width."))
    return errors


def _content_width_bound(node, by_id, visiting):
    """Conservative width contract for fixed-width content-height capability /1."""
    if node.get("id") in visiting:
        return None
    properties = node.get("properties", {})
    if properties.get("visibility") == "Collapsed":
        return 0.0
    role = node.get("role")
    if role in {"visual.image", "text.label"}:
        size = properties.get("brushImageSize")
        width = (size[0] if isinstance(size, list) and size else None) if role == "visual.image" else properties.get("wrapTextAt")
        return float(width) if isinstance(width, (int, float)) and not isinstance(width, bool) and math.isfinite(width) and width > 0 else None
    if role == "container.size":
        # Reuse the build contract's closed shape and enable/clear semantics.
        # A source rect or a stored-but-disabled WidthOverride is not a bound.
        path = Path(__file__).resolve().parents[2] / "build-nextgame-umg/scripts/validate_layout_spec.py"
        spec = importlib.util.spec_from_file_location("_bundle_size_box_constraints", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        constraints = node.get("sizeBoxConstraints")
        children = [child for child in by_id.values() if child.get("parent") == node.get("id")]
        if set(properties) - {"visibility"} or not module.valid_size_box_constraints(constraints) or len(children) != 1:
            return None
        child = children[0]
        slot = child.get("sizeBoxSlot")
        if not module.valid_size_box_slot(slot, require_fill=True) or any(slot["padding"]):
            return None
        if child.get("id") in visiting | {node.get("id")}:
            return None
        width = constraints["widthOverride"]
        if width is not None:
            return float(width)
        return _content_width_bound(child, by_id, visiting | {node.get("id")})
    if role not in {"container.overlay", "container.vertical", "container.horizontal"}:
        return None
    visiting = visiting | {node.get("id")}
    widths = []
    for child in by_id.values():
        if child.get("parent") != node.get("id") or child.get("properties", {}).get("visibility") == "Collapsed":
            continue
        slot = child.get("overlaySlot" if role == "container.overlay" else "flowSlot", {})
        padding = slot.get("padding", [0, 0, 0, 0])
        if not isinstance(padding, list) or len(padding) != 4 or any(not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or p < 0 for p in padding):
            return None
        if role != "container.overlay" and slot.get("size", {}).get("rule") != "Auto":
            return None
        width = _content_width_bound(child, by_id, visiting)
        if width is None:
            return None
        widths.append(width + padding[0] + padding[2])
    return (sum(widths) if role == "container.horizontal" else max(widths, default=0.0))
