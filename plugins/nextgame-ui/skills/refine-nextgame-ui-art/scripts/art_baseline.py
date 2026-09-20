"""Explicit development-baseline/1 authority, not a final delivery validator.

No Editor calls and no standalone screening command. Completed compile/save
evidence uses the existing programmatic executor checkpoint format.
"""
from __future__ import annotations

import sys

from art_common import (ArtError, PLUGIN_ROOT, aware_time, bound_path, index_snapshot,
                        load_json, read_bound, sha256, validate)

CAPABILITY = 'development-baseline/1'
CAPABILITY_V2 = 'development-baseline/2'
STRUCTURAL = {'compile', 'save', 'widget-tree', 'key-properties'}


def _fail(code, message):
    raise ArtError('baseline.' + code, message)


def _checks(bundle):
    checks = bundle.get('verification', {}).get('checks', [])
    ids = [c.get('id') for c in checks]
    if len(ids) != len(set(ids)):
        _fail('duplicate_check', 'Baseline check IDs must be unique.')
    return {c['id']: c for c in checks}


def _build_evidence(contract, request_path, bundle, bundle_path, completed):
    from _document_contract_common import resolve_request_path
    build_scripts = str(PLUGIN_ROOT / 'skills/build-nextgame-umg/scripts')
    if build_scripts not in sys.path:
        sys.path.insert(0, build_scripts)
    from execute_plan_programmatic import plan_digest

    checks = _checks(bundle)
    expected = {key: c for key, c in checks.items() if c['type'] in {'compile', 'save'}}
    records = contract['buildEvidence']
    if len(records) != len({r['checkId'] for r in records}) or {r['checkId'] for r in records} != set(expected):
        _fail('build_evidence_coverage', 'Evidence must exactly cover every compile/save check once.')
    assets = {a['id']: a for a in bundle['assets']}
    times = {}
    started = aware_time(bundle['execution']['startedAt'])
    for record in records:
        check = expected[record['checkId']]
        asset = assets.get(check.get('assetId'))
        if asset is None:
            _fail('build_asset', 'Compile/save check must name an actual Bundle asset.')
        plan_path = bound_path(record['plan'], request_path)
        checkpoint_path = bound_path(record['checkpoint'], request_path)
        if not check.get('artifactPath') or resolve_request_path(bundle_path, check['artifactPath']) != checkpoint_path:
            _fail('build_artifact', 'Check artifactPath must name its exact bound execution checkpoint.')
        plan, checkpoint = load_json(plan_path), load_json(checkpoint_path)
        steps, events = plan.get('steps', []), checkpoint.get('events', [])
        if (plan.get('assetPath') != asset['assetPath'] or checkpoint.get('formatVersion') != 2
                or checkpoint.get('planSha256') != plan_digest(plan)
                or checkpoint.get('status') != 'completed' or checkpoint.get('requiresGetWidgets')
                or checkpoint.get('completedPrefix') != len(steps) or not steps or len(events) != len(steps)):
            _fail('build_checkpoint', 'Require the complete current executor checkpoint and exact asset plan.')
        for index, (step, event) in enumerate(zip(steps, events), 1):
            if (event.get('status') != 'completed' or event.get('index') != index
                    or event.get('stepId') != step.get('stepId')
                    or event.get('tool') != step.get('toolsetName', '') + '.' + step.get('toolName', '')):
                _fail('build_events', 'Checkpoint must prove every ordered plan step, without gaps.')
        candidates = [(s, e) for s, e in zip(steps, events) if s.get('stepId') == record['stepId']]
        if len(candidates) != 1:
            _fail('build_step', 'Build evidence step must resolve exactly once.')
        step, event = candidates[0]
        path = asset['assetPath']
        expected_tool, expected_args = (
            ('UMGToolSet.UMGToolSet.CompileWidgetBlueprint',
             {'widgetBlueprint': {'refPath': path + '.' + path.rsplit('/', 1)[-1]}})
            if check['type'] == 'compile' else
            ('editor_toolset.toolsets.asset.AssetTools.save_assets', {'asset_paths': [path]})
        )
        if (step.get('operation', 'call_tool') != 'call_tool' or event['tool'] != expected_tool
                or step.get('arguments') != expected_args or event.get('result', {}).get('returnValue') is not True):
            _fail('build_result', 'Compile/save must have the supported official tool, exact target and true result.')
        stamp = aware_time(checkpoint.get('updatedAt', ''))
        if not started <= stamp <= completed:
            _fail('build_time', 'Actual compile/save checkpoint must fall within the structural build interval.')
        times.setdefault((asset['id'], check['type']), []).append(stamp)
    for asset_id in assets:
        if max(times[(asset_id, 'compile')]) > min(times[(asset_id, 'save')]):
            _fail('build_time', 'Each asset must be saved after its last compile.')


def validate_development_baseline(request, request_path, paths=None):
    """Strict actual-state validation for the sole explicit unfinished art route."""
    validate(request, 'request')
    if not {CAPABILITY, CAPABILITY_V2} & set(request.get('capabilities', [])) or request['goal'] != 'formal-art':
        _fail('capability', 'Development baseline requires explicit formal-art capability version 1 or 2.')
    paths = paths or {key: bound_path(value, request_path) for key, value in request['baseline'].items()}
    docs = str(PLUGIN_ROOT / 'skills/document-nextgame-umg/scripts')
    if docs not in sys.path:
        sys.path.insert(0, docs)
    from _document_contract_common import (READBACK_SCHEMA, validate_requirement_and_bundle_sources)
    from validate_unreal_widget_readback import _validate_readback_actual_state

    requirement, bundle, readback = (load_json(paths[key]) for key in ('requirement', 'bundle', 'readback'))
    if request['requestId'] != requirement.get('requestId'):
        _fail('request_identity', 'Art request must retain the accepted baseline request identity.')
    if bundle.get('version') not in {'0.1', '0.2', '0.3'}:
        _fail('bundle_version', 'Development baseline requires a pre-art Bundle 0.1–0.3.')
    errors, context = validate_requirement_and_bundle_sources(
        requirement, bundle, requirement_path=paths['requirement'], bundle_path=paths['bundle'],
        check_linked_files=True,
    )
    if errors:
        _fail('sources', str(errors[:3]))
    execution, verification = bundle['execution'], bundle['verification']
    if execution['status'] != 'running' or 'completedAt' in execution or verification['status'] != 'pending':
        _fail('lifecycle', 'Development Bundle remains running/pending, without a final completedAt.')
    if any(a['status'] != 'built' for a in bundle['assets']):
        _fail('asset_status', 'Every development asset must be built, not final-verified, planned or failed.')
    contract = request['developmentBaseline']
    completed = aware_time(contract['structureCompletedAt'])
    if aware_time(execution.get('startedAt', '')) > completed:
        _fail('build_time', 'Structural completion cannot precede execution start.')
    checks = _checks(bundle)
    pending = {key for key, c in checks.items() if c['status'] == 'pending'}
    if pending != set(contract['pendingCheckIds']):
        _fail('pending_coverage', 'Declared pending IDs must exactly equal all original pending checks.')
    deferred = frozenset()
    if contract['version'] == 2:
        from art_baseline_v2 import validate_property_deferrals
        deferred = validate_property_deferrals(request, request_path, paths, requirement, bundle, readback, context)
    if any(c['status'] == 'failed' or (c['status'] != 'passed' and c['type'] != 'preview' and key not in deferred) for key, c in checks.items()):
        _fail('check_status', 'Only preview checks may remain pending; failures and unfinished structure are rejected.')
    structural_types = STRUCTURAL | ({'schema'} if contract['version'] == 2 else set())
    for asset in bundle['assets']:
        covered = {c['type'] for c in checks.values() if c.get('assetId') == asset['id'] and c['status'] == 'passed'}
        if not structural_types <= covered:
            _fail('structural_coverage', 'Every asset needs passed compile, save, widget-tree and key-properties checks.')
    _build_evidence(contract, request_path, bundle, paths['bundle'], completed)
    report = _validate_readback_actual_state(
        readback, load_json(READBACK_SCHEMA), readback_path=paths['readback'], requirement=requirement,
        requirement_path=paths['requirement'], bundle=bundle, bundle_path=paths['bundle'],
        context=context, source_completed_at=contract['structureCompletedAt'],
        deferred_property_check_ids=deferred,
    )
    if not report['valid']:
        _fail('readback', str(report['errors'][:3]))
    snapshot = validate(load_json(paths['snapshot']), 'snapshot')
    if snapshot['acquisition']['method'] == 'fixture' or aware_time(snapshot['capturedAt']) < completed:
        _fail('snapshot', 'Development snapshot must be an actual post-save acquisition.')
    actual, _ = index_snapshot(snapshot)
    normalized = {a['assetPath']: a for a in readback['assets']}
    if set(actual) != set(normalized):
        _fail('snapshot_coverage', 'Art snapshot and normalized actual readback must cover the same assets.')
    basic = lambda w: (w['widgetName'], w['classPath'], w['parentWidgetName'], w['isVariable'])
    for path, art in actual.items():
        record = normalized[path]
        if (art['designSizeMode'] is None or art['designSizeMode'] != record.get('designSizeMode')
                or art['parentClassPath'] != record.get('parentClassPath')
                or {basic(w) for w in art['widgets']} != {basic(w) for w in record['widgets']}):
            _fail('snapshot_identity', 'Art snapshot must agree with verified actual identity, tree and Designer mode.')
        observed = {w['widgetName']: w for w in record['widgets']}
        for widget in art['widgets']:
            for key in ('visibility', 'entryWidgetClass'):
                actual_value = widget['properties'].get(key)
                if key == 'entryWidgetClass' and isinstance(actual_value, dict):
                    actual_value = actual_value.get('refPath')
                if key in observed[widget['widgetName']] and observed[widget['widgetName']][key] != actual_value:
                    _fail('snapshot_property', 'Art snapshot must match observed normalized ' + key + '.')
    return paths


def validate_baseline_closure(request, request_path, final_bundle):
    """All baseline obligations survive unchanged and pass in the final Bundle."""
    if not {CAPABILITY, CAPABILITY_V2} & set(request.get('capabilities', [])):
        return
    validate_development_baseline(request, request_path)
    if final_bundle is None:
        return  # Art-side verification is followed by mandatory final Bundle validation.
    baseline = read_bound(request['baseline']['bundle'], request_path)
    final = _checks(final_bundle)
    for check_id, original in _checks(baseline).items():
        current = final.get(check_id)
        if current is None or current.get('status') != 'passed':
            _fail('closure_pending', 'Final Bundle must retain and pass every original baseline check: ' + check_id)
        for key in ('type', 'assetId', 'requirementRefs', 'claimIds'):
            if current.get(key) != original.get(key):
                _fail('closure_identity', 'Final check cannot replace its original obligation: ' + check_id)
