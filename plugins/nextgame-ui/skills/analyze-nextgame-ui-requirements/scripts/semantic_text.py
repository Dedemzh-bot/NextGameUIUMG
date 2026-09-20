"""Validate explicitly reviewed semantic text pairs; punctuation is never a split heuristic."""
from __future__ import annotations
import math


def _error(code, path, message):
    return {"code": "text.semantic." + code, "path": path, "message": message}


def _number(value, *, positive=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and (value > 0 if positive else value >= 0)
    except (OverflowError, ValueError):
        return False


def _positive(value):
    return _number(value, positive=True)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _model(spec):
    return _dict(_dict(spec).get("uiModel"))


def _elements(spec):
    return [item for item in _list(_model(spec).get("elements")) if isinstance(item, dict)]


def groups(spec):
    for element in _elements(spec):
        # Explicitly excluded historical compositions are not executable.
        if element.get("inBuildScope") is False:
            continue
        properties = _dict(element.get("properties"))
        if "semanticTextGroup" in properties:
            yield element, properties["semanticTextGroup"]


def _rect(value):
    return (isinstance(value, list) and len(value) == 4
            and all(_number(item) for item in value)
            and _positive(value[2]) and _positive(value[3]))


def _flow(slot):
    if not isinstance(slot, dict):
        return False
    size, padding = _dict(slot.get("size")), slot.get("padding")
    size_ok = (size == {"rule": "Auto"} or (set(size) == {"rule", "weight"}
               and size.get("rule") == "Fill" and _positive(size.get("weight"))))
    return (slot.get("slotType") == "flow" and size_ok
            and isinstance(padding, list) and len(padding) == 4
            and all(_number(value) for value in padding)
            and isinstance(slot.get("horizontalAlignment"), str)
            and slot["horizontalAlignment"] in {"Left", "Center", "Right", "Fill"}
            and isinstance(slot.get("verticalAlignment"), str)
            and slot["verticalAlignment"] in {"Top", "Center", "Bottom", "Fill"})


def validate_requirement_semantic_text(spec):
    errors = []
    elements = _elements(spec)
    for owner, group in groups(spec):
        path = "$.uiModel.elements[" + str(elements.index(owner)) + "].properties.semanticTextGroup"
        keys = {"kind", "reason", "sourceCombinedText", "partNames", "gapPx", "availableWidthPx", "maxChars", "capacitySamples"}
        if not isinstance(group, dict) or set(group) != keys or group.get("kind") != "semantic-pair":
            errors.append(_error("shape", path, "Expected the closed semantic-pair contract.")); continue
        names = group["partNames"]
        if (not isinstance(names, list) or len(names) != 2
                or any(not isinstance(n, str) or not n for n in names) or len(set(names)) != 2):
            errors.append(_error("parts", path, "Two distinct reviewed text component names are required.")); continue
        if not isinstance(group["reason"], str) or not group["reason"].strip() or not isinstance(group["sourceCombinedText"], str) or not group["sourceCombinedText"].strip():
            errors.append(_error("evidence", path, "Record semantic reasoning and original combined copy."))
        if (owner.get("kind") != "panel" or owner.get("layoutRole") != "container.horizontal"
                or not isinstance(owner.get("id"), str) or not owner.get("id")):
            errors.append(_error("owner", path, "A semantic pair needs one identified horizontal flow panel.")); continue
        if not _positive(group["availableWidthPx"]) or not _positive(group["gapPx"]) or group["gapPx"] >= group["availableWidthPx"]:
            errors.append(_error("width", path, "Finite positive available width must exceed the flow gap."))
        capacities, samples = group["maxChars"], group["capacitySamples"]
        if not isinstance(capacities, list) or len(capacities) != 2 or any(not isinstance(n, int) or isinstance(n, bool) or n <= 0 for n in capacities):
            errors.append(_error("capacity", path, "Two positive integer character capacities are required.")); continue
        if not isinstance(samples, list) or len(samples) != 2 or any(not isinstance(s, str) or len(s) != n for s, n in zip(samples, capacities)):
            errors.append(_error("samples", path, "Capacity samples must contain exactly the declared character count."))
        children = [e for e in elements if e.get("parentElementId") == owner["id"] and e.get("inBuildScope") is not False]
        if (len(children) != 2 or any(not isinstance(e.get("nameHint"), str) for e in children)
                or {e.get("nameHint") for e in children} != set(names) or any(e.get("kind") != "text" for e in children)):
            errors.append(_error("children", path, "Exactly two direct Text elements are required.")); continue
        for i, name in enumerate(names):
            child = next(e for e in children if e["nameHint"] == name)
            props, slot = _dict(child.get("properties")), child.get("panelSlotIntent")
            text = props.get("text")
            if not isinstance(text, str):
                errors.append(_error("text", path, "A semantic fragment needs string text, not null or another type."))
            elif any(c in text for c in "\t\r\n") or props.get("wrap") is not False:
                errors.append(_error("wrapping", path, "A single-row pair must not wrap or encode layout whitespace."))
            elif len(text) > capacities[i]:
                errors.append(_error("sample_over_capacity", path, "Sample exceeds capacity; revise the reviewed capacity/layout."))
            if "wrapTextAt" in props and (not _number(props["wrapTextAt"]) or props["wrapTextAt"] != 0):
                errors.append(_error("wrap_width", path, "A reviewed no-wrap semantic field cannot retain a positive or invalid wrapTextAt."))
            if not _flow(slot):
                errors.append(_error("slot", path, "Each child needs finite flow Size, Padding and both Alignments.")); continue
            if slot["padding"] != [0 if i == 0 else group["gapPx"], 0, 0, 0]:
                errors.append(_error("gap", path, "Use declared inter-field padding instead of textual spacers."))
    return errors


def validate_semantic_text_coverage(spec, bundle, nodes_by_asset):
    """Require unique field/runtime realizations and exact reviewed flow geometry."""
    errors = validate_requirement_semantic_text(spec)
    if errors:
        return errors
    elements = _elements(spec)
    mappings = [m for m in _list(_dict(bundle).get("nodeMappings")) if isinstance(m, dict)]
    assets = [a for a in _list(_dict(bundle).get("assets")) if isinstance(a, dict)]
    runtimes = [r for r in _list(_model(spec).get("runtimeFields")) if isinstance(r, dict) and r.get("inBuildScope") is not False]
    nodes_by_asset = _dict(nodes_by_asset)

    def mappings_for(identifier):
        return [m for m in mappings if isinstance(identifier, str) and identifier in _list(m.get("requirementRefs"))]

    def key(mapping):
        return mapping.get("assetId"), mapping.get("layoutNodeId")

    for owner, group in groups(spec):
        children = [next(e for e in elements if e.get("parentElementId") == owner["id"]
                         and e.get("nameHint") == name and e.get("inBuildScope") is not False)
                    for name in group["partNames"]]
        paths = []
        for entity in [owner] + children:
            found = mappings_for(entity.get("id"))
            if len(found) != 1:
                errors.append(_error("mapping", owner["id"], "Each semantic owner and field needs exactly one realization.")); break
            mapping = found[0]
            asset_id, node_id = key(mapping)
            if not isinstance(asset_id, str) or not isinstance(node_id, str):
                errors.append(_error("mapping_node", owner["id"], "Mapping needs string asset/node identities.")); break
            node = _dict(nodes_by_asset.get(asset_id)).get(node_id)
            if not isinstance(node, dict) or node.get("id") != node_id:
                errors.append(_error("mapping_node", owner["id"], "Semantic realization is absent from linked layout.")); break
            paths.append((mapping, node, entity))
        if len(paths) != 3:
            continue
        parent_mapping, parent, _ = paths[0]
        asset = parent_mapping["assetId"]
        if parent.get("role") != "container.horizontal" or len({key(m) for m, n, e in paths}) != 3:
            errors.append(_error("distinct", owner["id"], "Fields must be distinct TextBlocks below one horizontal group."))
        ordered = [n.get("id") for n in _dict(nodes_by_asset.get(asset)).values()
                   if isinstance(n, dict) and n.get("parent") == parent["id"]]
        if ordered != [paths[1][1]["id"], paths[2][1]["id"]]:
            errors.append(_error("order", owner["id"], "Direct-child order must match the reviewed pair."))
        rect, bounds = parent.get("rect"), owner.get("bounds")
        asset_matches = [a for a in assets if a.get("id") == asset]
        matches = rect == bounds
        if "coordinateContract" in spec:
            from _coordinate_spaces import close, expected_rect
            plan_id = asset_matches[0].get("assetPlanId", asset) if len(asset_matches) == 1 else None
            bounds = expected_rect(spec, plan_id, parent["id"], owner["id"], None)
            matches = _rect(bounds) and close(rect, bounds, 1e-9)
        if not _rect(rect) or not _rect(bounds) or not matches:
            errors.append(_error("geometry", owner["id"], "Owner rect must preserve its accepted target geometry (legacy requests use source normalized bounds)."))
        size = asset_matches[0].get("referenceSize") if len(asset_matches) == 1 else None
        if (not _rect(rect) or not isinstance(size, list) or len(size) != 2
                or not all(_positive(v) for v in size)
                or not _positive(rect[2] * size[0])
                or rect[2] * size[0] + 1e-6 < group["availableWidthPx"]):
            errors.append(_error("available_width", owner["id"], "Authored group width cannot shrink below reviewed availableWidthPx."))
        runtime_targets = set()
        for mapping, node, entity in paths[1:]:
            props = _dict(node.get("properties"))
            if (mapping.get("assetId") != asset or node.get("parent") != parent["id"]
                    or node.get("role") != "text.label"
                    or props.get("text") != _dict(entity.get("properties")).get("text")
                    or props.get("autoWrap") is not False
                    or not _number(props.get("wrapTextAt")) or props.get("wrapTextAt") != 0):
                errors.append(_error("lowering", entity["id"], "Preserve copy, no-wrap, asset and direct flow owner."))
            expected_slot = {k: v for k, v in entity["panelSlotIntent"].items()
                             if k not in {"reason", "slotType", "sizingBasis"}}
            if node.get("flowSlot") != expected_slot:
                errors.append(_error("flow_slot", entity["id"], "Preserve complete accepted Size, weight, Padding and Alignment."))
            fields = [r for r in runtimes if r.get("elementId") == entity.get("id")]
            if len(fields) > 1:
                errors.append(_error("runtime_unique", entity["id"], "Distinct runtime text fields cannot share one Text element."))
            for field in fields:
                found = mappings_for(field.get("id"))
                if len(found) != 1 or key(found[0]) != key(mapping) or key(mapping) in runtime_targets:
                    errors.append(_error("runtime_mapping", str(field.get("id")), "Each runtime field must map once to its own Text element's unique node."))
                runtime_targets.add(key(mapping))
    return errors
