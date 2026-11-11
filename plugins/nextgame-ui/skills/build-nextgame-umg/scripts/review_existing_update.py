#!/usr/bin/env python3
"""Read-only ownership, dependency and conflict review for existing Layout 0.4.

Uses the existing planner and snapshot/2 validators as authority. This report
never grants execution or result acceptance. Independently implemented after
studying Design2UMG's ownership/binding/conflict checks (see accompanying rule).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
SCHEMA_PATH = Path(__file__).resolve().parent.parent / 'assets/existing-update-review.schema.json'
DEFAULT_PLUGIN = Path(__file__).resolve().parents[3]
KIND = 'nextgame-ui-existing-update-review'
REFERENCE_URL = 'https://github.com/DiracSea12/Design2UMG/blob/master/Source/Design2UMGEditor/Private/DesignImportReimportConflict.cpp'


def _read(path):
    """Reject ambiguous JSON, non-finite constants and duplicate keys."""
    raw = Path(path).read_bytes()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Non-finite JSON value: ' + value)
    data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=constant)
    json.dumps(data, allow_nan=False)
    return data, {'path': str(Path(path).resolve(strict=True)), 'sha256': hashlib.sha256(raw).hexdigest()}


def _same_file(binding):
    return hashlib.sha256(Path(binding['path']).read_bytes()).hexdigest() == binding['sha256']


def _load_authority(plugin):
    scripts = plugin / 'skills/build-nextgame-umg/scripts'
    paths = [scripts / 'existing_asset_update_v2.py', scripts / 'existing_asset_snapshot_v2.py',
             scripts / 'existing_asset_update.py',
             plugin / 'skills/build-nextgame-umg/assets/existing-asset-update-v2.schema.json',
             plugin / 'skills/build-nextgame-umg/assets/existing-asset-snapshot-v2.schema.json',
             plugin / 'skills/build-nextgame-umg/assets/existing-asset-update.schema.json',
             plugin / 'skills/refine-nextgame-ui-art/scripts/art_editor.py', Path(__file__).resolve(), SCHEMA_PATH]
    authority = [_read(path)[1] if path.suffix == '.json' else
                 {'path': str(path.resolve(strict=True)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    # Canonical modules resolve their own schema/art siblings from this source.
    # Loading them does not construct an Editor or execute any tool call.
    sys.path.insert(0, str(scripts))
    import existing_asset_update_v2 as update
    import existing_asset_snapshot_v2 as snapshot
    if Path(update.__file__).resolve() != scripts / 'existing_asset_update_v2.py' or Path(snapshot.__file__).resolve() != scripts / 'existing_asset_snapshot_v2.py' or Path(update.legacy.__file__).resolve() != scripts / 'existing_asset_update.py':
        raise ValueError('A different plugin authority is already imported; run this review in a fresh process.')
    art = update.legacy._art_module('art_editor')
    compare = {'math': math, 'json': json}
    exec(art._FLOAT32_PROGRAM, compare)
    return update, snapshot, compare['same_property'], authority


def _validate(value, kind):
    from jsonschema import Draft202012Validator
    schema = _read(SCHEMA_PATH)[0]
    validator = Draft202012Validator({'$schema': schema['$schema'], '$ref': '#/$defs/' + kind, '$defs': schema['$defs']})
    errors = sorted(validator.iter_errors(value), key=lambda error: str(list(error.path)))
    if errors:
        raise ValueError(kind + ' schema ' + str(list(errors[0].path)) + ': ' + errors[0].message)


def _asset(snapshot, path):
    found = [asset for asset in snapshot['assets'] if asset['assetPath'] == path]
    if len(found) != 1:
        raise ValueError('Snapshot must include exactly one target asset: ' + path)
    return found[0]


def _pointer(value, pointer):
    if pointer == '':
        return value
    if not pointer.startswith('/'):
        raise ValueError('Evidence pointer must be an RFC 6901 JSON pointer')
    for encoded in pointer[1:].split('/'):
        if re.search(r'~(?![01])', encoded):
            raise ValueError('Invalid JSON pointer escape')
        key = encoded.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', key):
                raise ValueError('Invalid JSON pointer list index')
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise ValueError('JSON pointer traverses a scalar')
    return value


def _mentions(value, name, ref=None):
    """Conservative token hit, never proof of a semantic Blueprint binding."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    if ref and ref in text:
        return True
    return re.search(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])', text) is not None


def _bound_sidecar(path, kind, current_binding, asset_path, widgets, snapshot_module, bindings):
    if path is None:
        return []
    value, binding = _read(path)
    _validate(value, kind)
    bindings.append(binding)
    if value['assetPath'] != asset_path or value['currentSnapshot'] != current_binding:
        raise ValueError(kind + ' must bind the exact current snapshot bytes and target asset')
    seen = set()
    for row in value['records']:
        key = row['widgetName'] if kind == 'ownership' else row['id']
        if key in seen or row['widgetName'] not in widgets:
            raise ValueError(kind + ' duplicate record or unknown current widget')
        seen.add(key)
        evidence_path = snapshot_module.bound_path(row['evidence'], path)
        evidence, evidence_binding = _read(evidence_path)
        bindings.append(evidence_binding)
        fragment = _pointer(evidence, row['jsonPointer'])
        widget = widgets[row['widgetName']]
        if not _mentions(fragment, row['widgetName'], widget.get('widgetRefPath')):
            raise ValueError(kind + ' evidence pointer does not mention the widget identity')
    return value['records']


def _descendants(children, root):
    result, pending = set(), [root]
    while pending:
        name = pending.pop()
        if name in result:
            continue
        result.add(name)
        pending.extend(children.get(name, ()))
    return result


def _differences(before, after, pointer=''):
    """Report exact changed JSON leaves; shared float32 equality is supplied by caller."""
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            child = pointer + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in before:
                result.append({'pointer': child, 'change': 'added', 'before': None, 'after': after[key]})
            elif key not in after:
                result.append({'pointer': child, 'change': 'removed', 'before': before[key], 'after': None})
            else:
                result.extend(_differences(before[key], after[key], child))
        return result
    if type(before) is type(after) and before == after:
        return []
    return [{'pointer': pointer, 'change': 'changed', 'before': before, 'after': after}]


def _operation_status(operation, current, widgets, same):
    kind, name = operation['kind'], operation.get('widgetName')
    widget = widgets.get(name)
    if kind == 'set-designer-mode':
        actual = current['designSizeMode']
    elif kind in {'set-property', 'set-slot'}:
        if widget is None:
            return 'conflict', None, 'The planned widget is absent from current evidence.'
        properties = widget['properties'] if kind == 'set-property' else widget['slot']['properties']
        if operation['property'] not in properties:
            return 'conflict', None, 'The planned field is absent from the current native observation.'
        actual = properties[operation['property']]
    elif kind == 'reparent-widget':
        if widget is None:
            return 'conflict', None, 'The reparent source widget is absent.'
        actual = {'parentWidgetName': widget['parentWidgetName'], 'slot': widget['slot']}
        if same(actual, {key: operation['after'][key] for key in actual}):
            return 'target-observed', actual, 'Parent and Slot match; final sibling order is checked separately.'
        if same(actual, {key: operation['before'][key] for key in actual}):
            return 'pending', actual, 'Parent and Slot still match the reviewed baseline.'
        return 'conflict', actual, 'Current parent or Slot differs from both baseline and planned target.'
    elif kind == 'add-widget':
        if widget is None:
            return 'pending', None, 'Planned name is absent; this is not permission to create it.'
        return 'conflict', widget, 'Planned addition name already exists; its generation ownership is not inferred.'
    else:
        return 'unsupported', None, 'Operation is outside this supplemental review contract.'
    if same(actual, operation['after']):
        return 'target-observed', actual, 'Current value equals this planned target; other gates remain required.'
    if same(actual, operation['before']):
        return 'pending', actual, 'Current value still equals the reviewed baseline.'
    return 'conflict', actual, 'Current value differs from both the reviewed baseline and target.'


def build_review(layout_path, current_path, *, plugin_root=DEFAULT_PLUGIN, ownership_path=None, dependencies_path=None):
    plugin = Path(plugin_root).resolve(strict=True)
    update, sm, same, authority = _load_authority(plugin)
    layout_path, current_path = Path(layout_path).resolve(strict=True), Path(current_path).resolve(strict=True)
    layout, layout_binding = _read(layout_path)
    current_snapshot, current_binding = _read(current_path)
    sm.validate_snapshot(current_snapshot, snapshot_path=current_path, check_evidence=True)
    validation = update.validate_existing_asset_update_v2(layout, spec_path=layout_path)
    if not validation['valid']:
        raise ValueError('Canonical Layout0.4 validation failed: ' + json.dumps(validation['errors'], ensure_ascii=False))
    plan = update.build_update_plan_v2(layout_path, layout)
    baseline_snapshot, baseline_asset, baseline_widgets = update._baseline(layout, layout_path)
    baseline_path = sm.bound_path(layout['baseline']['snapshot'], layout_path)
    _, baseline_binding = _read(baseline_path)
    current_asset = _asset(current_snapshot, plan['assetPath'])
    current_widgets = {widget['widgetName']: widget for widget in current_asset['widgets']}
    current_children = {}
    for name, widget in current_widgets.items():
        current_children.setdefault(widget['parentWidgetName'], []).append(name)
    bindings = [layout_binding, baseline_binding, current_binding]
    for snapshot_value, snapshot_path in ((baseline_snapshot, baseline_path), (current_snapshot, current_path)):
        for asset in snapshot_value['assets']:
            for key in ('rawEvidence', 'sourceAsset'):
                bindings.append(sm.binding(sm.bound_path(asset[key], snapshot_path)))
    ownership_records = _bound_sidecar(ownership_path, 'ownership', current_binding, plan['assetPath'], current_widgets, sm, bindings)
    dependency_records = _bound_sidecar(dependencies_path, 'dependencies', current_binding, plan['assetPath'], current_widgets, sm, bindings)
    claims = {row['widgetName']: row for row in ownership_records}
    raw = sm.read_bound(current_asset['rawEvidence'], current_path)
    own_rows, hits = [], []
    graph_text = json.dumps(raw['graphs'], ensure_ascii=False, sort_keys=True)
    graph_tokens = set(re.findall(r'[A-Za-z0-9_]+', graph_text))
    named_slot_hits = {}
    for index, slot in enumerate(raw['namedSlots']):
        for ref in {sm._ref(slot.get('hostWidget')), sm._ref(slot.get('contentWidget'))} - {None}:
            named_slot_hits.setdefault(ref, []).append(index)
    protected_names = set(current_asset['protectedReferences'])
    for name, widget in current_widgets.items():
        claim = claims.get(name)
        if widget['isInherited']:
            if claim:
                raise ValueError('An ownership declaration cannot relabel an observed inherited widget: ' + name)
            owner_kind, ownership_status, reason = 'inherited', 'observed', 'Actual snapshot isInherited is true.'
        elif claim:
            owner_kind, ownership_status, reason = claim['ownerKind'], 'evidence-bound-declaration', claim['reason']
        else:
            owner_kind, ownership_status, reason = 'unknown', 'unproven', 'No generation record or manual ownership declaration is bound.'
        own_rows.append({'widgetName': name, 'objectStatus': 'actual-uobject', 'ownerKind': owner_kind, 'ownershipStatus': ownership_status,
                         'ownershipProven': widget['isInherited'], 'reason': reason,
                         'evidence': claim['evidence'] if claim else current_asset['rawEvidence']})
        if widget['isVariable']:
            hits.append({'widgetName': name, 'kind': 'exposed-variable', 'certainty': 'observed',
                         'evidence': current_asset['rawEvidence'], 'jsonPointer': '', 'reason': 'Actual bIsVariable; variable exposure alone is not proof of a consumer.'})
        if name in protected_names:
            hits.append({'widgetName': name, 'kind': 'protected-reference', 'certainty': 'observed',
                         'evidence': current_asset['rawEvidence'], 'jsonPointer': '', 'reason': 'Existing snapshot marks this name protected; its complete dependency set remains unknown.'})
        if name in graph_tokens:
            hits.append({'widgetName': name, 'kind': 'blueprint', 'certainty': 'possible-text-hit',
                         'evidence': current_asset['rawEvidence'], 'jsonPointer': '/graphs', 'reason': 'Bound graph evidence mentions the identity; this conservative text hit does not resolve binding semantics.'})
        for index in named_slot_hits.get(widget['widgetRefPath'], []):
            hits.append({'widgetName': name, 'kind': 'named-slot', 'certainty': 'observed',
                         'evidence': current_asset['rawEvidence'], 'jsonPointer': '/namedSlots/' + str(index), 'reason': 'Actual NamedSlot host/content reference matches this UObject.'})
    for widget in current_asset['declaredInheritedWidgets']:
        own_rows.append({'widgetName': widget['widgetName'], 'objectStatus': 'inherited-declaration-without-uobject',
                         'ownerKind': 'inherited', 'ownershipStatus': 'observed', 'ownershipProven': True,
                         'reason': 'Actual inherited declaration has no editable UObject; it is never a mutation target.',
                         'evidence': current_asset['rawEvidence']})
    for row in dependency_records:
        hits.append({'widgetName': row['widgetName'], 'kind': row['referenceKind'], 'certainty': 'reported-evidence-bound',
                     'evidence': row['evidence'], 'jsonPointer': row['jsonPointer'], 'reason': row['reason']})
    hits_by_name = {}
    for hit in hits:
        hits_by_name.setdefault(hit['widgetName'], []).append(hit)
    ownership_by_name = {row['widgetName']: row for row in own_rows}
    issues, operations = [], []
    def issue(code, message, operation_id=None, widget_name=None):
        issues.append({'code': code, 'message': message, 'operationId': operation_id, 'widgetName': widget_name})
    before_state = next(asset for asset in sm.state(baseline_snapshot) if asset['assetPath'] == plan['assetPath'])
    now_state = next(asset for asset in sm.state(current_snapshot) if asset['assetPath'] == plan['assetPath'])
    baseline_matches = before_state == now_state
    if not baseline_matches:
        issue('baseline-drift', 'Current saved/native evidence differs from the reviewed baseline; the original executor must stop and a new reviewed plan is required.')
    for operation in plan['operations']:
        status, actual, explanation = _operation_status(operation, current_asset, current_widgets, same)
        name, kind = operation.get('widgetName'), operation['kind']
        affected = {name} if name in current_widgets else set()
        if kind == 'reparent-widget':
            if name in current_widgets:
                affected.update(_descendants(current_children, name))
                affected.add(current_widgets[name]['parentWidgetName'])
            affected.add(operation['after'].get('parentWidgetName'))
        if kind == 'add-widget':
            affected.add(operation['parentWidgetName'])
        affected = sorted(affected - {None})
        operation_hits = [hit for affected_name in affected for hit in hits_by_name.get(affected_name, [])]
        if status in {'conflict', 'unsupported'}:
            issue('operation-' + status, explanation, operation['id'], name)
        if kind in {'reparent-widget', 'add-widget'}:
            issue('structural-reference-coverage-incomplete', 'Animation/native/external Lua references are not fully enumerated. Ask the programmer to resolve the scoped dependency gap before structural changes.', operation['id'], name)
            unknown = [affected_name for affected_name in affected if affected_name not in ownership_by_name or not ownership_by_name[affected_name]['ownershipProven']]
            if unknown:
                issue('structural-ownership-unproven', 'Affected ownership is unproven or only declared: ' + ', '.join(unknown), operation['id'], name)
            if operation_hits:
                issue('structural-protected-references', 'Affected widgets have observed, reported or possible references. Preserve identities and review the listed evidence.', operation['id'], name)
        operations.append({'operationId': operation['id'], 'kind': kind, 'widgetName': name, 'property': operation.get('property'),
                           'before': operation['before'], 'after': operation['after'], 'current': actual, 'status': status,
                           'explanation': explanation, 'affectedWidgetNames': affected, 'referenceHitCount': len(operation_hits)})
    old_names, new_names = set(baseline_widgets), set(current_widgets)
    drift = []
    for name in sorted(old_names | new_names):
        before, after = baseline_widgets.get(name), current_widgets.get(name)
        if before is None or after is None:
            drift.append({'widgetName': name, 'changes': [{'pointer': '', 'change': 'added' if before is None else 'removed', 'before': before, 'after': after}]})
        elif not same(before, after):
            drift.append({'widgetName': name, 'changes': _differences(before, after)})
    order = {'baseline': baseline_asset['widgetOrder'], 'current': current_asset['widgetOrder'],
             'plannedRootOrder': plan['expectedRootOrder'], 'plannedChildOrder': plan['expectedChildOrder']}
    if baseline_asset['widgetOrder'] != current_asset['widgetOrder']:
        issue('widget-order-drift', 'Current WidgetTree order differs from the baseline; do not infer an allowed reorder from the planned target.')
    bindings.extend(authority)
    for binding in bindings:
        if not _same_file(binding):
            raise ValueError('Input or authority changed during review: ' + binding['path'])
    report = {'kind': KIND, 'version': '1', 'assetPath': plan['assetPath'], 'status': 'blocked' if issues else 'review-ready',
              'readOnly': True, 'executionAllowed': False, 'formalGatesValidated': False, 'visualVerified': False,
              'inputs': {'layout': layout_binding, 'baselineSnapshot': baseline_binding, 'currentSnapshot': current_binding,
                         'ownership': sm.binding(ownership_path) if ownership_path else None,
                         'dependencies': sm.binding(dependencies_path) if dependencies_path else None},
              'authority': authority, 'targetPlanSha256': sm.digest(plan), 'baselineMatchesCurrent': baseline_matches,
              'ownership': own_rows, 'plannedGeneratedWidgets': [op['widgetName'] for op in plan['operations'] if op['kind'] == 'add-widget'],
              'referenceCoverage': {'complete': False, 'missingKinds': ['animation-enumeration', 'native-enumeration', 'external-lua-enumeration'],
                                    'reportedKinds': sorted({row['referenceKind'] for row in dependency_records}), 'hits': hits},
              'operations': operations, 'currentDrift': drift, 'widgetOrder': order, 'issues': issues,
              'summary': {'actualWidgetCount': len(current_widgets), 'unknownOwnershipCount': sum(row['ownerKind'] == 'unknown' for row in own_rows),
                          'declaredOwnershipCount': sum(row['ownershipStatus'] == 'evidence-bound-declaration' for row in own_rows),
                          'operationCount': len(operations), 'pendingCount': sum(row['status'] == 'pending' for row in operations),
                          'targetObservedCount': sum(row['status'] == 'target-observed' for row in operations), 'blockingIssueCount': len(issues)},
              'nextActions': ['Keep the complete Requirement, Accepted Build View, Bundle/Coverage, actual schema/CAS, compile/save and readback gates.',
                              'For baseline drift or conflicts, preserve actual edits and derive a new scoped plan; do not replay or automatically roll back.',
                              'Resolve structural ownership and animation/native/Lua dependency uncertainty with programmers; declarations do not grant permission.',
                              'After any permitted execution, capture current evidence again and complete the separate controlled-render/result acceptance.'],
              'designReference': REFERENCE_URL}
    _validate(report, 'report')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--current-snapshot', type=Path, required=True)
    parser.add_argument('--plugin-root', type=Path, default=DEFAULT_PLUGIN)
    parser.add_argument('--ownership', type=Path, help='Optional evidence-bound ownership declarations; never auto-authoritative.')
    parser.add_argument('--dependencies', type=Path, help='Optional programmer/extractor reference evidence; coverage remains incomplete.')
    parser.add_argument('--output', type=Path, help='New diagnostic JSON file; existing files are never overwritten.')
    args = parser.parse_args()
    try:
        report = build_review(args.layout, args.current_snapshot, plugin_root=args.plugin_root,
                              ownership_path=args.ownership, dependencies_path=args.dependencies)
        payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.output:
            output = args.output.resolve()
            # Creating only an explicit diagnostic is not an Editor operation.
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(payload)
            print(json.dumps({'status': report['status'], 'readOnly': True, 'executionAllowed': False,
                              'output': str(output), 'summary': report['summary']}, ensure_ascii=False))
        else:
            print(payload, end='')
        return 2 if report['status'] == 'blocked' else 0
    except Exception as exc:
        print(json.dumps({'kind': KIND, 'version': '1', 'status': 'invalid-input', 'readOnly': True,
                          'executionAllowed': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
