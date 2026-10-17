#!/usr/bin/env python3
"""Closed, offline UILayoutSpec 0.3 validation and pure-set planning.

Native values are supplied by the accepted design after the existing build
lowering. This module does not convert fonts, create assets, or contact Unreal.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SKILL_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = SKILL_ROOT.parents[1]
SCHEMA = SKILL_ROOT / "assets/existing-asset-update.schema.json"
CAPABILITY = "existing-asset-property-update/1"
PLAN_KIND = "nextgame-ui-existing-asset-property-update-plan"
NULLABLE_OBJECT_FIELDS = frozenset({"resourceObject", "fontObject", "entryWidgetClass"})
OBJECT_ASSET_PATH = re.compile(r"^/(?:Game|Engine)/[A-Za-z0-9_/]+(?:\.[A-Za-z0-9_]+)?$")
BLUEPRINT_OBJECT_PATH = re.compile(r"^/(?:Game|Engine)/(?:[A-Za-z0-9_]+/)*([A-Za-z0-9_]+)\.\1$")
FLOW_PARENTS = {
    "/Script/UMG.HorizontalBox": ("/Script/UMG.HorizontalBoxSlot", "container.horizontal"),
    "/Script/UMG.VerticalBox": ("/Script/UMG.VerticalBoxSlot", "container.vertical"),
}
ALIGNMENT_INTENTS = {
    "horizontal": {"HAlign_Left": "left", "HAlign_Center": "center", "HAlign_Right": "right", "HAlign_Fill": "stretch"},
    "vertical": {"VAlign_Top": "top", "VAlign_Center": "center", "VAlign_Bottom": "bottom", "VAlign_Fill": "stretch"},
}


@lru_cache(maxsize=None)
def _art_module(name: str):
    path = PLUGIN_ROOT / "skills/refine-nextgame-ui-art/scripts" / (name + ".py")
    key = "_existing_asset_" + name
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise ImportError("Required existing art authority unavailable: " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def exact(left: Any, right: Any) -> bool:
    """Preserve JSON types at the design/baseline boundary."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(exact(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact(a, b) for a, b in zip(left, right))
    return left == right


def asset_path(layout: dict) -> str:
    return layout["asset"]["folder"] + "/" + layout["asset"]["name"]


def _issue(code: str, path: str, message: str) -> dict:
    return {"code": "existing-update." + code, "path": path, "message": message}


def _merge_observed(before: Any, target: Any, path: str) -> Any:
    """A partial struct can replace only already-observed leaves."""
    field = path.rsplit(".", 1)[-1]
    observed_ref = isinstance(before, dict) and set(before) == {"refPath"}
    observed_null = before is None or before == "None"
    if observed_ref or (observed_null and field in NULLABLE_OBJECT_FIELDS):
        if exact(before, target):
            return copy.deepcopy(before)
        if target is None or target == "None":
            return copy.deepcopy(target)
        if (isinstance(target, dict) and set(target) == {"refPath"}
                and isinstance(target["refPath"], str)
                and (target["refPath"] == "None" or OBJECT_ASSET_PATH.fullmatch(target["refPath"]))):
            return copy.deepcopy(target)
        raise ValueError(path + ": expected an observed native ObjectRef or null, not an arbitrary struct")
    if isinstance(target, dict):
        if not isinstance(before, dict) or set(target) - set(before):
            raise ValueError(path + ": target contains unobserved struct fields")
        merged = copy.deepcopy(before)
        for key, value in target.items():
            merged[key] = _merge_observed(before[key], value, path + "." + key)
        return merged
    if isinstance(target, list):
        if not isinstance(before, list) or len(target) != len(before):
            raise ValueError(path + ": array shape differs from the observation")
        return [_merge_observed(a, b, path) for a, b in zip(before, target)]
    numeric = type(target) in (int, float) and type(before) in (int, float)
    if not numeric and type(target) is not type(before):
        raise ValueError(path + ": native leaf type differs from the observation")
    if numeric and (not math.isfinite(target) or not math.isfinite(before)):
        raise ValueError(path + ": native numbers must be finite")
    return copy.deepcopy(target)


def _observed_class_matches(raw_class: Any, actual_class: Any) -> bool:
    if exact(raw_class, actual_class):
        return True
    # GetWidgets can identify a Blueprint asset while get_class reports its generated class.
    return (isinstance(raw_class, str) and BLUEPRINT_OBJECT_PATH.fullmatch(raw_class) is not None
            and actual_class == raw_class + "_C")


def _baseline(layout: dict, spec_path: Path):
    common, editor = _art_module("art_common"), _art_module("art_editor")
    snapshot = common.read_bound(layout["baseline"]["snapshot"], spec_path)
    assets, widgets = common.index_snapshot(snapshot)
    if common.state_hash(snapshot) != layout["baseline"]["stateSha256"]:
        raise ValueError("Baseline stateSha256 differs from the bound snapshot")
    path = asset_path(layout)
    if path not in assets:
        raise ValueError("Current asset path is absent from the bound snapshot")
    raw = common.read_bound(layout["baseline"]["rawTree"], spec_path)
    # Bind the actual GetWidgets payload, not a hand-authored topology summary.
    if not isinstance(raw, dict) or not isinstance(raw.get("info"), dict) or not isinstance(raw.get("widgets"), list):
        raise ValueError("rawTree must be the complete GetWidgets info/widgets payload")
    observed = {name: widget for (owner, name), widget in widgets.items() if owner == path}
    raw_by_name, raw_by_ref = {}, {}
    object_path = path + "." + path.rsplit("/", 1)[-1]
    for item in raw["widgets"]:
        name = item["widgetName"]
        ref = editor._ref(item.get("widget"))
        if name in raw_by_name or ref in raw_by_ref or ref != object_path + ":WidgetTree." + name:
            raise ValueError("Raw tree has duplicate, foreign, or non-native widget identity")
        raw_by_name[name], raw_by_ref[ref] = item, name
    if set(raw_by_name) != set(observed):
        raise ValueError("Snapshot and raw tree do not cover exactly the same topology")
    if editor._ref(raw["info"].get("parentClass")) != assets[path]["parentClassPath"]:
        raise ValueError("Raw tree and snapshot disagree on the Blueprint parent class")
    for name, widget in observed.items():
        item = raw_by_name[name]
        parent_ref = editor._ref(item.get("parent"))
        host_ref = editor._ref(item.get("namedSlotHost"))
        if any(ref is not None and ref not in raw_by_ref for ref in (parent_ref, host_ref)):
            raise ValueError("Raw tree has an unresolved native parent or named Slot host")
        parent = raw_by_ref.get(parent_ref) or raw_by_ref.get(host_ref)
        slot_ref = editor._ref(item.get("slot"))
        if slot_ref is not None and not slot_ref.startswith(object_path + ":WidgetTree."):
            raise ValueError("Raw tree Slot belongs to a different asset")
        if (not _observed_class_matches(editor._ref(item.get("widgetClassPath")), widget["classPath"])
                or not exact(item.get("bIsVariable"), widget["isVariable"])
                or parent != widget["parentWidgetName"]
                or (slot_ref is None) != (widget["slot"]["classPath"] is None)):
            raise ValueError("Raw tree and snapshot disagree on native identity/topology")
    return snapshot, assets[path], observed


def _operations(layout: dict, observed: dict) -> list[dict]:
    editor = _art_module("art_editor")
    writable = editor.WRITE_PROPERTIES - {"visibility", "text"}
    operations = []
    for node in sorted(layout["nodes"], key=lambda n: n["id"]):
        current = observed[node["name"]]
        groups = [
            ("set-property", "nativeProperties", current["properties"], editor.VISUAL_PROPERTIES, writable),
            ("set-slot", "nativeSlot", current["slot"]["properties"], editor.SLOT_PROPERTIES, editor.SLOT_PROPERTIES),
        ]
        for kind, field, before, readable, allowed in groups:
            targets = node[field]
            if set(targets) - readable or set(targets) - set(before):
                raise ValueError(node["id"] + "." + field + ": outside observed ArtEditor fields")
            for prop in sorted(targets):
                after = _merge_observed(before[prop], targets[prop], node["id"] + "." + field + "." + prop)
                if exact(before[prop], after):
                    continue
                if prop not in allowed:
                    raise ValueError(node["id"] + "." + prop + ": protected input, state, content, binding or EntryClass write")
                if kind == "set-slot" and current["slot"]["classPath"] is None:
                    raise ValueError(node["id"] + ": no observed native parent Slot")
                if prop == "font" and "size" in targets[prop]:
                    size = after["size"]
                    if type(size) is not int or size <= 0 or size % 2:
                        raise ValueError("Native font size must already be a positive even integer; use prepare_build lowering")
                operations.append({
                    "id": kind + "-" + node["id"] + "-" + prop,
                    "kind": kind, "assetPath": asset_path(layout), "widgetName": node["name"],
                    "property": prop, "before": copy.deepcopy(before[prop]), "after": after,
                })
    return operations


def _native_number(value: Any, path: str) -> int | float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(path + ": expected a finite observed native number")
    return value


def _validate_slot_metadata(node: dict, parent: dict | None, current: dict) -> None:
    if "adaptiveLayout" not in node and "flowSlot" not in node:
        return
    path = node["id"]
    slot = _merge_observed(current["slot"]["properties"], node["nativeSlot"], path + ".nativeSlot")
    parent_class = parent["classPath"] if parent else None
    slot_class = current["slot"]["classPath"]
    flow_parent = FLOW_PARENTS.get(parent_class)
    is_flow = flow_parent is not None and slot_class == flow_parent[0]
    if "flowSlot" in node:
        if not is_flow or parent["role"] != flow_parent[1]:
            raise ValueError(path + ".flowSlot: requires its observed direct Box parent, matching native Slot class and semantic role")
        declared = node["flowSlot"]
        size = slot.get("size", {})
        expected_rule = "Automatic" if declared["size"]["rule"] == "Auto" else "Fill"
        if not isinstance(size, dict) or size.get("sizeRule") != expected_rule:
            raise ValueError(path + ".flowSlot.size: allocation differs from the merged native sizeRule")
        value = _native_number(size.get("value"), path + ".nativeSlot.size.value")
        # Automatic ignores the stored native value; metadata must not reset it to a canonical default.
        if expected_rule == "Fill" and value != declared["size"]["weight"]:
            raise ValueError(path + ".flowSlot.size.weight: differs from the merged native Fill allocation")
        padding = slot.get("padding", {})
        if not isinstance(padding, dict) or any(
            _native_number(padding.get(edge), path + ".nativeSlot.padding." + edge) != expected
            for edge, expected in zip(("left", "top", "right", "bottom"), declared["padding"])
        ):
            raise ValueError(path + ".flowSlot.padding: differs from the merged native padding")
        for axis, prefix in (("horizontal", "HAlign_"), ("vertical", "VAlign_")):
            field = axis + "Alignment"
            if slot.get(field) != prefix + declared[field]:
                raise ValueError(path + ".flowSlot." + field + ": differs from the merged native alignment")
    if "adaptiveLayout" not in node:
        return
    adaptive = node["adaptiveLayout"]
    if not adaptive["reason"].strip():
        raise ValueError(path + ".adaptiveLayout.reason: must not be blank")
    if parent_class == "/Script/UMG.CanvasPanel" and slot_class == "/Script/UMG.CanvasPanelSlot":
        geometry = slot.get("layoutData")
        if not isinstance(geometry, dict) or not isinstance(geometry.get("anchors"), dict):
            raise ValueError(path + ".adaptiveLayout: requires observed native layoutData.anchors and alignment")
        anchors, alignment = geometry["anchors"], geometry.get("alignment")
        minimum_vector, maximum_vector = anchors.get("minimum"), anchors.get("maximum")
        if not all(isinstance(value, dict) for value in (minimum_vector, maximum_vector, alignment)):
            raise ValueError(path + ".adaptiveLayout: requires observed native anchor/alignment vectors")
        for field in ("anchors", "alignment"):
            if field in slot and not exact(slot[field], geometry.get(field)):
                raise ValueError(path + ".adaptiveLayout: conflicting native layoutData and " + field)
        for axis, coordinate, choices in (
            ("horizontal", "x", {0: "left", 0.5: "center", 1: "right"}),
            ("vertical", "y", {0: "top", 0.5: "center", 1: "bottom"}),
        ):
            minimum = _native_number(minimum_vector.get(coordinate), path + ".anchors.minimum." + coordinate)
            maximum = _native_number(maximum_vector.get(coordinate), path + ".anchors.maximum." + coordinate)
            pivot = _native_number(alignment.get(coordinate), path + ".alignment." + coordinate)
            if not (0 <= minimum <= maximum <= 1 and 0 <= pivot <= 1):
                raise ValueError(path + ".adaptiveLayout." + axis + ": native anchors/alignment are out of range or reversed")
            if minimum < maximum:
                actual = "stretch"
            elif minimum in choices and pivot == minimum:
                actual = choices[minimum]
            else:
                raise ValueError(path + ".adaptiveLayout." + axis + ": point anchor/alignment must match exactly at 0, 0.5 or 1")
            if adaptive[axis] != actual:
                raise ValueError(path + ".adaptiveLayout." + axis + ": differs from the merged native Canvas Slot")
    elif is_flow:
        for axis, intents in ALIGNMENT_INTENTS.items():
            actual = intents.get(slot.get(axis + "Alignment"))
            if actual is None or adaptive[axis] != actual:
                raise ValueError(path + ".adaptiveLayout." + axis + ": differs from the merged native Box Slot alignment")
    else:
        raise ValueError(path + ".adaptiveLayout: requires an observed Canvas or Box Slot; unsupported parents are not inferred")


def validate_existing_asset_update(layout: Any, *, spec_path: Path | None = None) -> dict:
    errors = []
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        for error in Draft202012Validator(schema).iter_errors(layout):
            errors.append(_issue("schema", "$" + "".join("[" + str(x) + "]" for x in error.path), error.message))
        # Also rejects nonfinite values inside native structs, whose shape is observed at runtime.
        json.dumps(layout, allow_nan=False)
    except (OSError, ValueError, TypeError) as error:
        errors.append(_issue("schema", "$", str(error)))
    if errors:
        return {"valid": False, "errors": errors, "warnings": []}
    if spec_path is None:
        return {"valid": False, "errors": [_issue("baseline.path", "$.baseline", "A physical Layout path is required to resolve current baseline evidence.")], "warnings": []}
    try:
        _, asset, observed = _baseline(layout, Path(spec_path))
        path = asset_path(layout)
        expected_root = "/Game/UI/AIPrototype/" if layout["mode"] == "prototype" else "/Game/UI/UMG/"
        if not path.startswith(expected_root):
            raise ValueError("Layout mode does not match the current asset path")
        profile = layout["profile"]
        if not exact(profile["designSizeMode"], asset["designSizeMode"]):
            raise ValueError("Existing-only update must preserve the observed Designer mode")
        if profile["assetKind"] == "screen" and layout["referenceSize"] != [2560, 1440]:
            raise ValueError("Screen referenceSize must remain [2560, 1440]")
        if profile["assetKind"] == "screen" and profile["listRole"] != "none":
            raise ValueError("A screen cannot be a list Entry")
        nodes = layout["nodes"]
        by_id = {n["id"]: n for n in nodes}
        names = {n["name"] for n in nodes}
        if len(by_id) != len(nodes) or len(names) != len(nodes):
            raise ValueError("Layout native names and node IDs must be unique")
        if names != set(observed):
            raise ValueError("Layout must cover the complete observed topology: no missing or new nodes")
        if sum(n["parent"] is None for n in nodes) != 1:
            raise ValueError("Existing WidgetTree must have exactly one native root")
        for node in nodes:
            old = observed[node["name"]]
            parent = by_id.get(node["parent"]) if node["parent"] is not None else None
            if node["parent"] is not None and parent is None:
                raise ValueError(node["id"] + ": parent ID is not an observed topology node")
            if (node["classPath"] != old["classPath"] or not exact(node["isVariable"], old["isVariable"])
                    or (parent["name"] if parent else None) != old["parentWidgetName"]
                    or node["slotClassPath"] != old["slot"]["classPath"]):
                raise ValueError(node["id"] + ": native name/class/parent/variable/Slot identity must be preserved")
            if node["rect"][2] <= 0 or node["rect"][3] <= 0:
                raise ValueError(node["id"] + ": semantic rect must have positive dimensions")
            _validate_slot_metadata(node, parent, old)
        operations = _operations(layout, observed)
    except (OSError, ValueError, TypeError, KeyError, ImportError, OverflowError) as error:
        errors.append(_issue("baseline_target", "$", str(error)))
        operations = []
    return {"valid": not errors, "errors": errors, "warnings": [],
            "summary": {"nodes": len(layout["nodes"]), "operations": len(operations)}}


def build_update_plan(spec_path: Path, layout: dict) -> dict:
    report = validate_existing_asset_update(layout, spec_path=spec_path)
    if not report["valid"]:
        raise ValueError("UILayoutSpec 0.3 validation failed: " + json.dumps(report["errors"]))
    source_bytes = Path(spec_path).read_bytes()
    if not exact(json.loads(source_bytes.decode("utf-8-sig")), layout):
        raise ValueError("Plan Layout must exactly equal the current physical sourceSpec file")
    _, _, observed = _baseline(layout, spec_path)
    operations = _operations(layout, observed)
    return {
        "kind": PLAN_KIND, "version": "0.3", "capability": CAPABILITY,
        "sourceSpec": str(spec_path), "sourceSpecSha256": hashlib.sha256(source_bytes).hexdigest(),
        "assetPath": asset_path(layout), "baseline": copy.deepcopy(layout["baseline"]),
        "executionStatus": "not-executed",
        "executorContract": {
            "adapter": "ArtEditor.execute_batch", "genericCreateExecutorAllowed": False,
            "requiresCurrentBaselineRevalidation": True, "requiresAcceptedRequirementViewBundle": True,
            "baselineRevalidation": ["bound-file-hashes", "current-snapshot-stateSha256",
                                     "current-raw-tree-identity-and-child-order"],
            "requiresPostSaveReadback": True, "maxBatchOperations": 256,
        },
        # Even a no-op plan must be rejected by the generic Create executor before calls.
        "steps": [{"stepId": "existing-asset-update-only", "operation": "existing_asset_property_update",
                   "contract": CAPABILITY}],
        "operations": operations,
        "batches": [operations[i:i + 256] for i in range(0, len(operations), 256)],
    }


def source_entries(layout: dict, *, spec_path: Path, asset: dict, mappings: list[dict]) -> dict:
    """Art source lowering for 0.3 only; no catalog class substitution or conversion."""
    report = validate_existing_asset_update(layout, spec_path=spec_path)
    if not report["valid"] or asset.get("assetPath") != asset_path(layout):
        raise ValueError("Invalid or foreign existing-asset source: " + json.dumps(report["errors"]))
    mapping_by_id = {}
    for mapping in mappings:
        if mapping.get("assetId") != asset["id"]:
            continue
        if mapping["layoutNodeId"] in mapping_by_id:
            raise ValueError("Duplicate existing-asset source mapping")
        mapping_by_id[mapping["layoutNodeId"]] = mapping
    nodes = {n["id"]: n for n in layout["nodes"]}
    if set(mapping_by_id) != set(nodes):
        raise ValueError("Existing-asset source requires complete own-asset node mapping coverage")
    return {(asset_path(layout), node["name"]): {
        "classPath": node["classPath"], "parentWidgetName": nodes[node["parent"]]["name"] if node["parent"] else None,
        "isVariable": node["isVariable"], "properties": copy.deepcopy(node["nativeProperties"]),
        "slot": copy.deepcopy(node["nativeSlot"]), "requirementRefs": mapping_by_id[node["id"]]["requirementRefs"],
    } for node in layout["nodes"]}


def validate_bundle_layout(layout: dict, asset: dict, bundle: dict, requirement: dict, *,
                           spec_path: Path, accepted_claim_ids: set[str]) -> list[dict]:
    """Additional native-target gate. Full Requirement/View/Bundle validation stays mandatory."""
    errors = validate_existing_asset_update(layout, spec_path=spec_path)["errors"]
    if errors:
        return errors
    path = asset_path(layout)
    plans = [p for p in requirement.get("assetPlan", []) if p.get("id") == asset.get("assetPlanId")]
    if len(plans) != 1 or plans[0].get("assetPath") != path or asset.get("assetPath") != path:
        return [_issue("asset", "$.assets", "Current native asset identity must match its own accepted assetPlan and Bundle asset.")]
    plan = plans[0]
    expected_kind = "list-entry" if layout["profile"]["listRole"] == "entry" else layout["profile"]["assetKind"]
    if expected_kind != asset.get("assetKind"):
        errors.append(_issue("asset_kind", "$.assets", "Existing Layout profile must match the accepted asset boundary."))
    decision = plan.get("designSizeModeDecision", {})
    if "mode" in decision and decision["mode"] != layout["profile"]["designSizeMode"]:
        errors.append(_issue("designer_mode", "$.assets", "Accepted Designer mode differs from the preserved current mode."))
    nodes = {n["id"]: n for n in layout["nodes"]}
    elements = {e["id"]: e for e in requirement.get("uiModel", {}).get("elements", [])}
    owned = set(plan.get("coversElementIds", []))
    mappings = [m for m in bundle.get("nodeMappings", []) if m.get("assetId") == asset["id"]]
    if len(mappings) != len(nodes) or {m.get("layoutNodeId") for m in mappings} != set(nodes):
        errors.append(_issue("coverage", "$.nodeMappings", "Complete observed topology requires exactly one own-asset mapping per node."))
    for mapping in mappings:
        node = nodes.get(mapping.get("layoutNodeId"))
        if node is None:
            continue
        matched = []
        for ref in mapping.get("requirementRefs", []):
            element = elements.get(ref)
            if element is None:
                continue
            claims = set(element.get("claimIds", [])) & set(mapping.get("claimIds", [])) & accepted_claim_ids
            if element.get("inBuildScope") is not True or not claims:
                errors.append(_issue("element_acceptance", "$.nodeMappings", "Every mapped element must be in scope and backed by its reviewed accepted claim."))
                continue
            if ref not in owned:
                errors.append(_issue("element_asset", "$.nodeMappings", "Mapped accepted element belongs to a different assetPlan: " + ref))
            props = element.get("properties", {})
            if "owningAssetPath" in props and not exact(props["owningAssetPath"], path):
                errors.append(_issue("element_asset", "$.nodeMappings", ref + ".owningAssetPath differs from this node's own native asset."))
            for field in ("nativeProperties", "nativeSlot"):
                if field not in props or not exact(props[field], node[field]):
                    errors.append(_issue("source_target", "$.nodeMappings", ref + "." + field + " must exactly equal this linked Layout native target."))
            if element.get("nameHint") != node["name"]:
                errors.append(_issue("element_identity", "$.nodeMappings", "Accepted element must identify the preserved native name: " + ref))
            identity = {
                "targetClassPath": node["classPath"],
                "observedIsVariable": node["isVariable"],
                "observedParentWidgetName": nodes[node["parent"]]["name"] if node["parent"] else None,
            }
            for field, value in identity.items():
                if field not in props or not exact(props[field], value):
                    errors.append(_issue("element_identity", "$.nodeMappings", ref + "." + field + " must bind this node's preserved native identity."))
            for field in ("targetWidgetName", "observedWidgetName"):
                if field in props and not exact(props[field], node["name"]):
                    errors.append(_issue("element_identity", "$.nodeMappings", ref + "." + field + " differs from the preserved native name."))
            expected_role = {"text": "text.label", "image": "visual.image", "button": "input.button"}.get(element.get("kind"))
            if expected_role is not None and node["role"] != expected_role:
                errors.append(_issue("element_role", "$.nodeMappings", "Accepted element semantic kind differs from the Layout role: " + ref))
            matched.append(ref)
        if (node["nativeProperties"] or node["nativeSlot"]) and not matched:
            errors.append(_issue("target_acceptance", "$.nodeMappings", "Every declared native target needs a mapped accepted own-asset element."))
    for operation in bundle.get("crossAssetOperations", []):
        if asset["id"] in (operation.get("sourceAssetId"), operation.get("targetAssetId")):
            errors.append(_issue("cross_asset_write", "$.crossAssetOperations", "Existing-only native updates cannot authorize structural, EntryClass, input or state cross-asset operations."))
    return errors
