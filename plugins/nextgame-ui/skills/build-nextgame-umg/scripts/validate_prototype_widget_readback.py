#!/usr/bin/env python3
"""Strict actual readback for all-prototype Bundle 0.1; never DOCX authority.

The closed schema is pinned to this plugin, not caller supplied. Raw capture
sidecars bind every actual field; layouts supply expected values only. The
Bundle integration calls the payload checker after its ordinary linked gates.
The CLI additionally invokes the complete Bundle and requirement validators.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = SKILL_ROOT.parent.parent
ANALYSIS_SCRIPTS = SKILL_ROOT.parent / "analyze-nextgame-ui-requirements" / "scripts"
DOCUMENT_SCRIPTS = SKILL_ROOT.parent / "document-nextgame-umg" / "scripts"
for script_root in (ANALYSIS_SCRIPTS, DOCUMENT_SCRIPTS):
    if str(script_root) not in sys.path:
        sys.path.append(str(script_root))
from _contract_common import issue, load_json, result, sha256_file, validate_schema_instance
from _document_contract_common import (
    accepted_claim_ids, is_accepted_in_scope, layout_entry_class,
    parse_aware_iso8601, readback_indexes, resolve_request_path,
    runtime_collections, runtime_field_node_mappings, runtime_fields,
)
from prepare_build import build_plan, effective_design_size_mode

DEFAULT_SCHEMA = SKILL_ROOT / "assets" / "prototype-widget-readback.schema.json"
CATALOG_PATH = SKILL_ROOT / "references" / "component-catalog.json"
RULES_PATH = SKILL_ROOT / "references" / "rule-index.json"
ARTIFACT_TYPE = "nextgame-prototype-widget-readback"
PROTOTYPE_PATH = re.compile(r"^/Game/UI/AIPrototype/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*$")
ACTUAL_KEYS = ("assetPath", "assetObjectPath", "assetClass", "generatedClassPath",
               "parentClassPath", "cdoObjectPath", "designSizeMode", "widgets")
SLOT_CLASSES = {
    "/Script/UMG.CanvasPanel": "/Script/UMG.CanvasPanelSlot",
    "/Script/UMG.HorizontalBox": "/Script/UMG.HorizontalBoxSlot",
    "/Script/UMG.VerticalBox": "/Script/UMG.VerticalBoxSlot",
    "/Script/UMG.Overlay": "/Script/UMG.OverlaySlot",
    "/Script/UMG.Button": "/Script/UMG.ButtonSlot",
    "/Script/UIFramework.GameScrollBox": "/Script/UMG.ScrollBoxSlot",
}


def _strict_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        try:
            return math.isfinite(actual) and math.isfinite(expected) and actual == expected
        except (OverflowError, TypeError):
            return False
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_strict_equal(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_strict_equal(a, e) for a, e in zip(actual, expected))
    return actual == expected


def _compare_expected(actual: Any, expected: Any, path: str, errors: list) -> None:
    """Subset comparison matches partial reflected struct setters, not defaults."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            errors.append(issue("actual.property_type", path, "Expected an observed property object."))
            return
        for key, value in expected.items():
            if key not in actual:
                errors.append(issue("actual.property_missing", f"{path}.{key}", "Expected property is absent from actual readback; no planned backfill is allowed."))
            else:
                _compare_expected(actual[key], value, f"{path}.{key}", errors)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            valid = isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-4)
        except (OverflowError, TypeError, ValueError):
            valid = False
        if not valid:
            errors.append(issue("actual.property_mismatch", path, f"Actual {actual!r} differs from expected {expected!r}."))
    elif not _strict_equal(actual, expected):
        errors.append(issue("actual.property_mismatch", path, f"Actual {actual!r} differs from expected {expected!r}."))


def _json_pointer(value: Any, pointer: str) -> Any:
    def decode(item):
        if isinstance(item, str):
            try:
                return json.loads(item)
            except json.JSONDecodeError:
                return item
        return item
    value = decode(value)
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("sourceBinding requires an RFC 6901 JSON pointer.")
    for raw in pointer[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        value = decode(value)
        if isinstance(value, list):
            if not key.isdigit():
                raise ValueError("Array source pointer requires a nonnegative index.")
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise ValueError("Source pointer traverses a scalar.")
    return decode(value)


def _load_prototype_layouts(bundle: dict, bundle_path: Path, errors: list) -> dict:
    layouts = {}
    if bundle.get("version") != "0.1" or "reuseRelations" in bundle:
        errors.append(issue("prototype.bundle_version", "$.version", "Prototype readback 0.1 supports Bundle 0.1 only; reuse and mixed/advanced modes require a separate reviewed contract."))
        return layouts
    for i, asset in enumerate(bundle.get("assets", [])):
        path = f"$.assets[{i}]"
        if not isinstance(asset, dict):
            errors.append(issue("prototype.asset", path, "Expected a Bundle asset object."))
            continue
        if not PROTOTYPE_PATH.fullmatch(str(asset.get("assetPath", ""))):
            errors.append(issue("prototype.asset_scope", path, "Every actual Bundle asset must be strictly below /Game/UI/AIPrototype/."))
        if asset.get("representationKind", "layout-spec") != "layout-spec":
            errors.append(issue("prototype.representation", path, "Reuse-only representations are not supported."))
        try:
            layout_path = resolve_request_path(bundle_path, asset.get("layoutSpecPath"))
            layout = load_json(layout_path)
            if asset.get("layoutSpecSha256") != sha256_file(layout_path):
                errors.append(issue("prototype.layout_hash", path, "Linked Layout hash differs from Bundle."))
            if not isinstance(layout, dict) or layout.get("mode") != "prototype":
                errors.append(issue("prototype.layout_mode", path, "Every bound Layout must explicitly use mode prototype."))
                continue
            identity = layout.get("asset", {})
            if f"{identity.get('folder')}/{identity.get('name')}" != asset.get("assetPath"):
                errors.append(issue("prototype.layout_identity", path, "Layout prototype asset identity must exactly match the Bundle; targetAsset is future metadata only."))
            layouts[asset.get("id")] = (layout_path, layout)
        except (OSError, ValueError, TypeError) as exc:
            errors.append(issue("prototype.layout_read", path, str(exc)))
    return layouts


def expected_properties(layout_path: Path, layout: dict) -> dict:
    """Lower expected properties with the same trusted planner, without execution."""
    catalog = load_json(CATALOG_PATH)
    plan = build_plan(layout_path, layout, catalog, load_json(RULES_PATH))
    expected = {n["id"]: {"widget": {}, "slot": {}} for n in layout["nodes"]}
    for step in plan["steps"]:
        if step.get("toolName") != "set_properties":
            continue
        args = step["arguments"]
        ref = args.get("instance", {}).get("refPath", "")
        match = re.fullmatch(r"\$\{node\.(.+)\.returnValue\.(widget|slot)\.refPath\}", ref)
        if match:
            expected[match[1]][match[2]].update(args["values"])
    return expected


def _validate_prototype_payload(readback: Any, *, readback_path: Path,
                                requirement: dict, requirement_path: Path,
                                bundle: dict, bundle_path: Path) -> dict:
    """Internal gate; caller must also run full upstream Bundle validation."""
    errors = validate_schema_instance(readback, load_json(DEFAULT_SCHEMA))
    if errors:
        return result(errors, [])
    if not isinstance(requirement, dict) or not isinstance(bundle, dict):
        return result([issue("prototype.upstream_type", "$", "Requirement and Bundle must be objects.")], [])
    layouts = _load_prototype_layouts(bundle, bundle_path, errors)
    if errors:
        return result(errors, [])
    try:
        if not _strict_equal(load_json(requirement_path), requirement) or not _strict_equal(load_json(bundle_path), bundle):
            errors.append(issue("binding.input_snapshot", "$", "Supplied authority objects must equal the bound physical Requirement and Bundle files."))
        expected_requirement = {"requestId": requirement.get("requestId"), "revision": requirement.get("revision"),
                                "approvedContentSha256": requirement.get("reviewGate", {}).get("approvedContentSha256"), "sha256": sha256_file(requirement_path)}
        if readback["requirementBinding"] != expected_requirement:
            errors.append(issue("binding.requirement", "$.requirementBinding", "Readback does not bind the exact current accepted Requirement."))
        if readback["bundleBinding"] != {"bundleId": bundle.get("bundleId"), "sha256": sha256_file(bundle_path)}:
            errors.append(issue("binding.bundle", "$.bundleBinding", "Readback does not bind the exact finalized Bundle file."))
    except (OSError, ValueError) as exc:
        errors.append(issue("binding.authority_read", "$", str(exc)))
    execution = bundle.get("execution", {})
    if execution.get("status") != "completed":
        errors.append(issue("prototype.execution", "$.execution", "Readback requires a completed build execution, not planned assets."))
    started = parse_aware_iso8601(execution.get("startedAt"), "$.execution.startedAt", errors)
    completed = parse_aware_iso8601(execution.get("completedAt"), "$.execution.completedAt", errors)
    captured = parse_aware_iso8601(readback["capturedAt"], "$.capturedAt", errors)
    if started and completed and started > completed:
        errors.append(issue("time.execution_order", "$.execution", "Execution starts after its completion."))
    if completed and captured and captured < completed:
        errors.append(issue("time.readback_before_bundle", "$.capturedAt", "Capture must follow the final saved build completion."))
    evidence_by_id = {}
    evidence_times = {}
    for i, evidence in enumerate(readback["evidence"]):
        path = f"$.evidence[{i}]"
        eid = evidence["id"]
        if eid in evidence_by_id:
            errors.append(issue("evidence.duplicate", path, "Evidence IDs must be unique."))
        when = parse_aware_iso8601(evidence["capturedAt"], path + ".capturedAt", errors)
        evidence_times[eid] = when
        if when and completed and when < completed:
            errors.append(issue("evidence.stale", path, "Raw capture predates completedAt; an old receipt cannot be relabeled as fresh."))
        if when and captured and when > captured:
            errors.append(issue("evidence.future", path, "Readback timestamp precedes its supporting capture."))
        try:
            file = resolve_request_path(readback_path, evidence["path"])
            raw = load_json(file)
            if evidence["sha256"] != sha256_file(file):
                errors.append(issue("evidence.hash", path, "Raw capture hash mismatch."))
            if not isinstance(raw, dict) or raw.get("capturedAt") != evidence["capturedAt"]:
                errors.append(issue("evidence.timestamp_binding", path, "Evidence timestamp must exactly match the stored capture envelope."))
            evidence_by_id[eid] = raw
        except (OSError, ValueError, TypeError) as exc:
            errors.append(issue("evidence.read", path, str(exc)))
    indexes = readback_indexes(readback, errors)
    bundle_assets = {a["id"]: a for a in bundle.get("assets", []) if isinstance(a, dict) and isinstance(a.get("id"), str)}
    if set(indexes["assets"]) != set(bundle_assets):
        errors.append(issue("coverage.assets", "$.assets", "Readback assets must exactly cover all Bundle assets."))
    catalog = {c["role"]: c for c in load_json(CATALOG_PATH)["components"]}
    used_evidence = set()
    for ai, actual in enumerate(readback["assets"]):
        aid, ap = actual["assetId"], f"$.assets[{ai}]"
        ba = bundle_assets.get(aid)
        if ba is None or aid not in layouts:
            continue
        source = actual["sourceBinding"]
        used_evidence.add(source["evidenceId"])
        try:
            raw_asset = _json_pointer(evidence_by_id[source["evidenceId"]], source["jsonPointer"])
            observed = {k: actual[k] for k in ACTUAL_KEYS}
            if not isinstance(raw_asset, dict) or not _strict_equal({k: raw_asset[k] for k in ACTUAL_KEYS}, observed):
                errors.append(issue("evidence.actual_binding", ap, "Normalized actual fields differ from the bound raw capture; planned backfill is forbidden."))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            errors.append(issue("evidence.actual_source", ap, f"Actual source fields are missing or invalid: {exc}"))
        lp, layout = layouts[aid]
        package = ba["assetPath"]
        basename = package.rsplit("/", 1)[-1]
        object_path = f"{package}.{basename}"
        identities = {"assetPath": package, "assetObjectPath": object_path, "generatedClassPath": object_path + "_C",
                      "cdoObjectPath": f"{package}.Default__{basename}_C", "parentClassPath": layout.get("profile", {}).get("parentClass", "/Script/UMG.UserWidget")}
        for key, value in identities.items():
            if actual[key] != value:
                errors.append(issue("identity." + key, ap + "." + key, f"Actual identity must equal {value}."))
        if ba.get("status") not in {"built", "verified"}:
            errors.append(issue("prototype.asset_status", ap, "Readback cannot verify a planned or failed Bundle asset."))
        if actual["designSizeMode"] != effective_design_size_mode(layout):
            errors.append(issue("design_size_mode.mismatch", ap + ".designSizeMode", "Generated CDO DesignSizeMode differs from the bound layout/basename contract."))
        try:
            expected = expected_properties(lp, layout)
        except (KeyError, ValueError, TypeError) as exc:
            errors.append(issue("prototype.layout_invalid", ap, str(exc)))
            continue
        by_name = {n["name"]: n for n in layout["nodes"]}
        by_id = {n["id"]: n for n in layout["nodes"]}
        if {w["widgetName"] for w in actual["widgets"]} != set(by_name):
            errors.append(issue("coverage.widgets", ap + ".widgets", "Actual WidgetTree must exactly cover Layout nodes; missing and extra nodes both fail."))
        actual_order = {w["widgetName"]: i for i, w in enumerate(actual["widgets"])}
        sibling_orders = {}
        for node in layout["nodes"]:
            sibling_orders.setdefault(node.get("parent"), []).append(node["name"])
        for children in sibling_orders.values():
            if all(n in actual_order for n in children) and children != sorted(children, key=actual_order.get):
                errors.append(issue("identity.sibling_order", ap + ".widgets", "Actual sibling order differs from the bound layout."))
        for wi, widget in enumerate(actual["widgets"]):
            wp = ap + f".widgets[{wi}]"
            node = by_name.get(widget["widgetName"])
            if not node:
                continue
            component = catalog[node["role"]]
            parent = by_id.get(node.get("parent"))
            expected_parent = parent["name"] if parent else None
            checks = {"objectPath": object_path + ":WidgetTree." + node["name"], "classPath": component["classPath"],
                      "parentWidgetName": expected_parent, "isVariable": bool(node.get("isVariable", False))}
            for key, value in checks.items():
                if not _strict_equal(widget[key], value):
                    errors.append(issue("identity.widget_" + key, wp + "." + key, f"Actual value differs from {value!r}."))
            if widget["visibility"] != widget["properties"].get("visibility"):
                errors.append(issue("actual.visibility_binding", wp, "Visibility must be the actual reflected property, not independently assigned metadata."))
            expected_widget = expected[node["id"]]["widget"]
            _compare_expected(widget["properties"], expected_widget, wp + ".properties", errors)
            if node["role"].startswith("collection."):
                actual_entry = widget["properties"].get("entryWidgetClass")
                if isinstance(actual_entry, dict):
                    actual_entry = actual_entry.get("refPath")
                if not isinstance(widget["entryWidgetClass"], str) or widget["entryWidgetClass"] != actual_entry:
                    errors.append(issue("collection.entry_binding", wp, "EntryClass must equal the actual reflected generated class."))
                expected_entry = layout_entry_class(node)
                if expected_entry != widget["entryWidgetClass"]:
                    errors.append(issue("collection.entry_class", wp, "Actual EntryClass differs from the layout."))
            elif widget["entryWidgetClass"] is not None:
                errors.append(issue("collection.unexpected_entry", wp, "Non-collection Widget must have null EntryClass."))
            if parent is None:
                if widget["slot"] is not None:
                    errors.append(issue("identity.root_slot", wp, "Root must not carry a parent Slot."))
            else:
                parent_class = catalog[parent["role"]]["classPath"]
                expected_slot_class = SLOT_CLASSES.get(parent_class)
                slot = widget["slot"]
                if expected_slot_class is None or not isinstance(slot, dict):
                    errors.append(issue("prototype.slot_unsupported", wp, "Parent Slot is missing or not supported by this prototype contract."))
                    continue
                if slot["classPath"] != expected_slot_class:
                    errors.append(issue("identity.slot_class", wp + ".slot", "Actual Slot class differs from the parent type."))
                if not slot["objectPath"].startswith(object_path + ":WidgetTree." + parent["name"] + "."):
                    errors.append(issue("identity.slot_owner", wp + ".slot", "Actual Slot must belong to the observed parent Widget object."))
                if not expected[node["id"]]["slot"]:
                    errors.append(issue("prototype.slot_contract_missing", wp, "No trusted explicit Slot lowering exists; this mode needs a reviewed extension."))
                _compare_expected(slot["properties"], expected[node["id"]]["slot"], wp + ".slot.properties", errors)
    if used_evidence != set(evidence_by_id):
        errors.append(issue("evidence.coverage", "$.evidence", "Evidence must exactly support asset sources, without missing or unused receipts."))
    _validate_mappings_and_states(readback, requirement, bundle, layouts, indexes, errors)
    _validate_acquisition(readback, errors)
    _validate_check_links(readback_path, bundle, bundle_path, errors)
    output = result(errors, [])
    output["scope"] = {"mode": "prototype", "assetCount": len(readback["assets"]), "widgetCount": sum(len(a["widgets"]) for a in readback["assets"]), "productionDocumentAuthority": False, "visualPreviewVerified": False}
    return output


def _validate_mappings_and_states(readback, requirement, bundle, layouts, indexes, errors):
    mappings = {m["id"]: m for m in bundle.get("nodeMappings", []) if isinstance(m, dict) and isinstance(m.get("id"), str)}
    if set(indexes["mappings"]) != set(mappings):
        errors.append(issue("coverage.node_mappings", "$.assets[*].nodeMappings", "Every Bundle mapping must be covered exactly once, with no extras."))
    for mid, mapping in mappings.items():
        record = indexes["mappings"].get(mid)
        if not record:
            continue
        aid, actual_mapping = record
        nodes = {n["id"]: n for n in layouts.get(aid, (None, {}))[1].get("nodes", [])}
        expected_node = nodes.get(mapping.get("layoutNodeId"), {})
        if (aid != mapping.get("assetId") or actual_mapping["layoutNodeId"] != mapping.get("layoutNodeId")
                or actual_mapping["widgetName"] != expected_node.get("name")):
            errors.append(issue("identity.mapping", "$.assets[*].nodeMappings", f"Mapping {mid} does not resolve to its exact actual Widget."))
    accepted = accepted_claim_ids(requirement)
    all_mappings = list(mappings.values())
    def mapped_widget(mapping):
        actual = indexes["mappings"].get(mapping.get("id"))
        return indexes["widgets"].get((actual[0], actual[1]["widgetName"])) if actual else None
    for field in runtime_fields(requirement, accepted):
        candidates = runtime_field_node_mappings(field, all_mappings, requirement, accepted)
        if not candidates:
            errors.append(issue("runtime.mapping", "$.assets[*].nodeMappings", f"Runtime field {field.get('id')} lacks exact accepted node mappings."))
        for mapping in candidates:
            widget = mapped_widget(mapping)
            if not widget or widget["isVariable"] is not True:
                errors.append(issue("runtime.actual_variable", "$.assets[*].widgets", f"Runtime field {field.get('id')} must map to an actual variable Widget."))
    for collection in runtime_collections(requirement, accepted):
        refs = {collection.get("id"), collection.get("containerElementId")}
        candidates = [m for m in all_mappings if refs.intersection(m.get("requirementRefs", []))]
        if len(candidates) != 1:
            errors.append(issue("collection.mapping", "$.assets[*].nodeMappings", "Each collection needs exactly one actual mapping."))
        elif (widget := mapped_widget(candidates[0])) is None or not widget["isVariable"] or widget["classPath"] not in {"/Script/UIFramework.LuaListView", "/Script/UIFramework.LuaTileView"}:
            errors.append(issue("collection.actual", "$.assets[*].widgets", "Collection must be an actual variable LuaListView/LuaTileView."))
    for model in requirement.get("stateModels", []):
        if not isinstance(model, dict) or not is_accepted_in_scope(model, accepted, require_scope=False):
            continue
        for branch in model.get("implementation", {}).get("branches", []):
            candidates = [m for m in all_mappings if branch.get("panelElementId") in m.get("requirementRefs", []) and branch.get("stateId") in m.get("stateRefs", [])]
            if len(candidates) != 1:
                errors.append(issue("state.branch_mapping", "$.assets[*].nodeMappings", "Each accepted state branch needs one mapping."))
                continue
            widget = mapped_widget(candidates[0])
            if not widget or not widget["isVariable"] or widget["visibility"] != branch.get("visibility"):
                errors.append(issue("state.branch_actual", "$.assets[*].widgets", "Accepted branch must be variable and retain its exact initial Visibility."))


def _validate_acquisition(readback, errors):
    acquisition = readback["acquisition"]
    method = acquisition["method"]
    evidence_methods = {e["method"] for e in readback["evidence"]}
    if method != "mixed" and evidence_methods != {method}:
        errors.append(issue("acquisition.evidence_method", "$.acquisition", "Capture methods disagree with acquisition metadata."))
    fallbacks = acquisition.get("fieldFallbacks", [])
    paths = [f["jsonPath"] for f in fallbacks]
    if len(paths) != len(set(paths)):
        errors.append(issue("acquisition.duplicate_fallback", "$.acquisition", "Fallback paths must be unique."))
    for path in paths:
        match = re.fullmatch(r"\$\.assets\[(\d+)\]\.(designSizeMode|assetClass)", path)
        if not match or int(match[1]) >= len(readback["assets"]):
            errors.append(issue("acquisition.fallback_scope", "$.acquisition", "Prototype 0.1 mixed field fallbacks support only exact generated-CDO DesignSizeMode or WidgetBlueprint assetClass paths."))
    if method == "nxue-agent":
        required = {f"$.assets[{i}].designSizeMode" for i in range(len(readback["assets"]))}
        if not required.issubset(paths):
            errors.append(issue("acquisition.design_size_fallback", "$.acquisition", "Full NxUE capture must explicitly bind every generated-CDO DesignSizeMode."))


def _validate_check_links(readback_path, bundle, bundle_path, errors):
    covered = set()
    for i, check in enumerate(bundle.get("verification", {}).get("checks", [])):
        if check.get("type") not in {"widget-tree", "key-properties"}:
            continue
        path = f"$.verification.checks[{i}]"
        covered.add((check.get("assetId"), check["type"]))
        if check.get("status") != "passed":
            errors.append(issue("verification.check_status", path, "Structural checks must be passed to claim a verified readback."))
        try:
            if resolve_request_path(bundle_path, check.get("artifactPath")) != readback_path.resolve():
                errors.append(issue("verification.artifact_path", path, "Every structural check must point to this exact readback artifact."))
        except (ValueError, TypeError) as exc:
            errors.append(issue("verification.artifact_path", path, str(exc)))
    required = {(a.get("id"), kind) for a in bundle.get("assets", []) for kind in ("widget-tree", "key-properties")}
    if not required.issubset(covered):
        errors.append(issue("verification.check_coverage", "$.verification.checks", "Every built asset requires both structural check types."))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readback", type=Path)
    parser.add_argument("--requirement", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--accepted-build-view", type=Path)
    args = parser.parse_args()
    try:
        from validate_build_bundle import DEFAULT_SCHEMA as BUNDLE_SCHEMA, validate_build_bundle
        requirement, bundle = load_json(args.requirement), load_json(args.bundle)
        upstream = validate_build_bundle(bundle, load_json(BUNDLE_SCHEMA), bundle_path=args.bundle.resolve(), requirement_spec=requirement,
                                         requirement_path=args.requirement.resolve(), check_linked_files=True,
                                         accepted_build_view_path=args.accepted_build_view.resolve() if args.accepted_build_view else None)
        report = _validate_prototype_payload(load_json(args.readback), readback_path=args.readback.resolve(), requirement=requirement,
                                              requirement_path=args.requirement.resolve(), bundle=bundle, bundle_path=args.bundle.resolve())
        report["errors"] = [issue("upstream." + e["code"], e["path"], e["message"]) for e in upstream["errors"]] + report["errors"]
        report["valid"] = not report["errors"]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report = result([issue("prototype.read", "$", str(exc))], [])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
