#!/usr/bin/env python3
"""Plan, apply and verify the same optional art stage from a coordinator or CLI."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from art_common import (ART_GOALS, ArtError, PLUGIN_ROOT, advance_snapshot, binding, bound_path,
    canonical, check_operation, digest, index_snapshot, load_json, read_bound, run_validator,
    sha256, state_hash, utc_now, validate, validate_art_stage, validate_authority, validate_preview_contract, write_json)


def route(goal, *, has_baseline=False, has_resources=False):
    if goal == 'developer-only':
        return {'goal': goal, 'artRequired': False, 'nextAction': 'existing-build-workflow'}
    if goal not in ART_GOALS:
        raise ArtError('route.goal', 'An explicit task goal must be one of developer-only, formal-art, upgrade-art, local-art.')
    missing = [label for present, label in ((has_baseline, 'verified-umg-baseline'), (has_resources, 'art-resources')) if not present]
    return {'goal': goal, 'artRequired': True, 'complete': False,
            'nextAction': 'refine-nextgame-ui-art' if not missing else 'complete-art-inputs', 'missing': missing}


def initialize_request(job_path, output_path):
    """Expand a compact job into immutable hash-bound inputs; never infer authorization."""
    job = load_json(job_path)
    required = {'goal','originalText','scope','baseline','references','resourceDir','authorizedAssetPaths'}
    if not isinstance(job, dict) or not required <= set(job) or set(job) - required - {'target','budget','samples','resourceCatalog','developmentBaseline','referenceMode'}:
        raise ArtError('job.shape', 'Job needs goal, originalText, scope, baseline paths, references, resourceDir and exact authorizedAssetPaths.')
    def resolve(p):
        path = Path(p)
        return path.resolve() if path.is_absolute() else (Path(job_path).resolve().parent/path).resolve()
    baseline = {key:binding(resolve(value)) for key,value in job['baseline'].items()}
    requirement = read_bound(baseline['requirement'], output_path)
    references = copy.deepcopy(job['references'])
    for reference in references:
        reference['image'] = binding(resolve(reference['image']))
    request = {'kind':'nextgame-ui-art-request','version':1,'requestId':requirement['requestId'],
        'goal':job['goal'],'originalText':job['originalText'],'scope':job['scope'],'baseline':baseline,
        'references':references,'resourceDir':str(resolve(job['resourceDir'])),
        'productionAuthorized':all(s['assetPath'] in job['authorizedAssetPaths'] for s in job['scope']),
        'budget':job.get('budget',{'maxCorrectionRounds':2,'maxModelCalls':16,'tokenLimits':{}}),
        'capabilities':['presentation-review/1']}
    if 'referenceMode' in job:
        from art_reference import CAPABILITY
        if job['referenceMode'] != CAPABILITY:
            raise ArtError('job.reference_mode', 'Unsupported source-to-capture comparison capability.')
        request['capabilities'].append(CAPABILITY)
    if 'developmentBaseline' in job:
        request['capabilities'].append('development-baseline/1')
        request['developmentBaseline'] = copy.deepcopy(job['developmentBaseline'])
        for record in request['developmentBaseline'].get('buildEvidence', []):
            for key in ('plan', 'checkpoint'):
                record[key] = binding(resolve(record[key]))
    if 'target' in job:
        request['target']={key:binding(resolve(value)) for key,value in job['target'].items()}
    if 'samples' in job: request['samples']=[binding(resolve(p)) for p in job['samples']]
    if 'resourceCatalog' in job: request['resourceCatalog']=binding(resolve(job['resourceCatalog']))
    validate(request,'request')
    validate_authority(request,output_path)
    write_json(output_path,request)
    return {'request':binding(output_path),'nextAction':'packets'}


def check_model_budget(request_path, ledger_path, call_records):
    """Reuse exact provider-receipt measurement; never convert local proxies to tokens."""
    request=validate(load_json(request_path),'request')
    if len(call_records)>request['budget']['maxModelCalls']:
        raise ArtError('budget.model_calls','Actual reserved calls exceed the request limit.')
    limits=request['budget']['tokenLimits']
    if not limits:
        return {'status':'within-call-limit','reservedCalls':len(call_records),'actualTokens':'not-budgeted'}
    if any(limit==0 for limit in limits.values()):
        raise ArtError('budget.exhausted','A zero remaining token allowance prevents another model call.')
    if not call_records:
        return {'status':'first-call','reservedCalls':0,'actualTokens':'no-calls-yet'}
    if ledger_path is None:
        raise ArtError('budget.receipts','A configured token budget needs provider usage receipts before another call.')
    command=[sys.executable,str(PLUGIN_ROOT/'scripts/token_telemetry.py'),'check-budget',str(ledger_path),
             '--measurement-boundary-id','art-'+common_request_digest(request_path)[:24],
             '--run-id-digest',common_request_digest(request_path)]
    # Reservation requires remaining budget, not merely equality with the limit.
    # A provider can still exceed the remaining allowance within one call.
    for metric,limit in limits.items(): command += ['--limit',f'{metric}={limit-1}']
    for call in call_records: command += ['--expected-call','art:art-judgment:'+call['callIdDigest']]
    completed=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=60)
    if completed.returncode:
        raise ArtError('budget.exceeded_or_unmeasured',completed.stdout.strip() or completed.stderr.strip())
    return json.loads(completed.stdout)


def common_request_digest(request_path):
    return sha256(request_path)


def reserve_call(request_path, packet_path, journal_path, call_key, ledger_path=None):
    request_path,packet_path,journal_path=map(lambda p:Path(p).resolve(),(request_path,packet_path,journal_path))
    request=validate(load_json(request_path),'request')
    packet=load_json(packet_path)
    if packet.get('requestSha256')!=sha256(request_path):
        raise ArtError('packet.stale','Decision packet belongs to a different request.')
    for image in packet.get('images',[]): bound_path(image,packet_path)
    if not call_key:
        raise ArtError('call.identity','Predetermine a stable logical call key.')
    # A journal is a single-coordinator dispatch record; an exclusive sibling lock
    # prevents overlapping reservations. Stale lock cleanup requires explicit review.
    journal_path.parent.mkdir(parents=True,exist_ok=True)
    lock=journal_path.with_suffix(journal_path.suffix+'.reserve-lock')
    try:
        descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc:
        raise ArtError('call.locked','Another reservation is in progress; inspect a stale lock before recovery.') from exc
    try:
        os.close(descriptor)
        journal=load_json(journal_path) if journal_path.exists() else {'requestSha256':sha256(request_path),'calls':[]}
        if journal.get('requestSha256')!=sha256(request_path): raise ArtError('call.request','Journal belongs to another request.')
        call_digest=digest({'request':sha256(request_path),'packet':sha256(packet_path),'key':call_key})
        if any(c['callIdDigest']==call_digest for c in journal['calls']):
            return {'status':'already-reserved','dispatchAllowed':False,'callIdDigest':call_digest}
        check_model_budget(request_path,ledger_path,journal['calls'])
        if len(journal['calls'])>=request['budget']['maxModelCalls']:
            raise ArtError('budget.model_calls','Model-call budget exhausted; no new call reserved.')
        journal['calls'].append({'callIdDigest':call_digest,'packet':binding(packet_path),'reservedAt':utc_now()})
        write_json(journal_path,journal,replace=True)
        return {'status':'reserved','dispatchAllowed':True,'callIdDigest':call_digest,
            'runIdDigest':sha256(request_path),'measurementBoundaryId':'art-'+sha256(request_path)[:24],
            'stage':'art','agentRole':'art-judgment','actualModelCallsExecuted':0}
    finally:
        lock.unlink(missing_ok=True)


def _source_nodes(request, request_path):
    """Derive locked Unreal values with the existing deterministic build lowering."""
    source = request.get('target', request['baseline'])
    bundle_path = bound_path(source['bundle'], request_path)
    bundle = load_json(bundle_path)
    requirement = read_bound(source['requirement'], request_path)
    if requirement.get('requestId') != request['requestId'] or requirement.get('reviewGate', {}).get('status') != 'accepted':
        raise ArtError('design.not_accepted', 'The target must be the accepted design of this task.')
    build_dir = PLUGIN_ROOT / 'skills/build-nextgame-umg/scripts'
    if str(build_dir) not in sys.path:
        sys.path.insert(0, str(build_dir))
    from prepare_build import build_plan
    catalog = load_json(build_dir.parent / 'references/component-catalog.json')
    rules = load_json(build_dir.parent / 'references/rule-index.json')
    classes = {c['role']: c['classPath'] for c in catalog['components']}
    entries = {}
    for asset in bundle['assets']:
        if not asset.get('layoutSpecPath'):
            continue
        layout_path = bound_path({'path': asset['layoutSpecPath'], 'sha256': asset['layoutSpecSha256']}, bundle_path)
        layout = load_json(layout_path)
        lowered = build_plan(layout_path, layout, catalog, rules)
        steps = {s['stepId']: s for s in lowered['steps']}
        names = {n['id']: n['name'] for n in layout['nodes']}
        mappings = {m['layoutNodeId']: m for m in bundle['nodeMappings'] if m['assetId'] == asset['id']}
        for node in layout['nodes']:
            ident = node['id']
            props = steps.get('set-widget-properties-' + ident, {}).get('arguments', {}).get('values', {})
            slot = {}
            for prefix in ('set-slot-properties-', 'set-flow-slot-properties-', 'set-scroll-slot-properties-',
                           'set-overlay-slot-properties-', 'set-button-slot-properties-'):
                slot.update(steps.get(prefix + ident, {}).get('arguments', {}).get('values', {}))
            entries[(asset['assetPath'], node['name'])] = {
                'classPath': classes[node['role']], 'parentWidgetName': names.get(node.get('parent')),
                'isVariable': node.get('isVariable', False), 'properties': props, 'slot': slot,
                'requirementRefs': mappings.get(ident, {}).get('requirementRefs', [])}
    return entries


def _contains(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _contains(actual[k], v) for k, v in expected.items())
    return actual == expected


def _check_design(operation, locked, request):
    key = (operation['assetPath'], operation['widgetName'])
    desired = locked.get(key)
    kind = operation['kind']
    if kind == 'remove-widget':
        if not request.get('target') or desired is not None:
            raise ArtError('design.revision_required', 'Removal must already be represented in a newly accepted target design.')
        return
    if desired is None or operation['sourceElementId'] not in desired['requirementRefs']:
        raise ArtError('design.mapping', 'Operation must map to the same asset/node in the accepted design.')
    if kind in ('set-property', 'set-slot'):
        group = desired['properties'] if kind == 'set-property' else desired['slot']
        if operation['property'] in group and not _contains(operation['after'], group[operation['property']]):
            raise ArtError('design.locked', 'Revise and accept the design source before changing its locked value.')
    elif kind == 'add-widget':
        node = operation['after']
        if not all(node[k] == desired[k] for k in ('classPath', 'parentWidgetName', 'isVariable')):
            raise ArtError('design.structure', 'New art structure differs from the accepted target design.')
        if not _contains(node['properties'], desired['properties']) or not _contains(node['slot']['properties'], desired['slot']):
            raise ArtError('design.structure', 'New node does not preserve accepted property/Slot values.')
    elif kind == 'reparent-widget' and operation['after'] != desired['parentWidgetName']:
        raise ArtError('design.structure', 'Reparenting must match the accepted target design.')


def _plan_baseline(plan, plan_path, request, request_path):
    if 'previousVerification' in plan:
        previous = validate(read_bound(plan['previousVerification'], plan_path), 'verification')
        return validate(read_bound(previous['snapshot'], bound_path(plan['previousVerification'], plan_path)), 'snapshot')
    return validate(read_bound(request['baseline']['snapshot'], request_path), 'snapshot')


def create_plan(request_path, decisions_path, *, round_number=0, previous_verification_path=None, validate_sources=True):
    request_path, decisions_path = Path(request_path).resolve(), Path(decisions_path).resolve()
    request = validate(load_json(request_path), 'request')
    decisions = validate(load_json(decisions_path), 'decisions')
    if decisions['requestSha256'] != sha256(request_path):
        raise ArtError('decisions.stale', 'Decisions refer to a different art request.')
    if previous_verification_path is not None:
        previous = validate(load_json(previous_verification_path), 'verification')
        old_plan_path = bound_path(previous['plan'], previous_verification_path)
        old_plan, _, _ = _validated_plan(old_plan_path, validate_sources=False)
        if old_plan['request']['sha256'] != sha256(request_path):
            raise ArtError('correction.request', 'Correction must remain bound to the same task request.')
        previous_snapshot_path=bound_path(previous['snapshot'],previous_verification_path)
        previous_snapshot=validate(load_json(previous_snapshot_path),'snapshot')
        execution_path=bound_path(previous['execution'],previous_verification_path)
        execution=validate(load_json(execution_path),'execution')
        if (old_plan['status']!='ready' or state_hash(previous_snapshot)!=old_plan['expectedStateSha256']
                or execution['status']!='completed' or execution['planSha256']!=sha256(old_plan_path)
                or execution['completedIds']!=[o['id'] for o in old_plan['operations']]
                or execution['currentOperation'] is not None or execution['expectedStateSha256']!=old_plan['expectedStateSha256']
                or bound_path(execution['readback'],execution_path)!=previous_snapshot_path):
            raise ArtError('correction.baseline','Correction must start from the exact completed previous plan and actual readback.')
        round_number = old_plan['round'] + 1
        if previous['status'] == 'passed':
            raise ArtError('correction.complete', 'A passed result needs a new requested revision, not automatic correction.')
        if 'previousVerification' in old_plan:
            older = read_bound(old_plan['previousVerification'], old_plan_path)
            current_error = sum(read_bound(c, previous_verification_path).get('mae') or 0 for c in previous['comparisons'])
            older_path = bound_path(old_plan['previousVerification'], old_plan_path)
            older_error = sum(read_bound(c, older_path).get('mae') or 0 for c in older['comparisons'])
            if current_error >= older_error:
                raise ArtError('correction.no_improvement', 'Last correction did not improve the comparison; collect review issues.')
    elif round_number != 0:
        raise ArtError('correction.evidence', 'A correction round requires the previous verification, not a claimed counter.')
    if round_number > request['budget']['maxCorrectionRounds']:
        raise ArtError('budget.rounds', 'Automatic correction budget exhausted; collect unresolved issues.')
    if round_number < 0:
        raise ArtError('budget.rounds', 'Round cannot be negative.')
    if validate_sources:
        validate_authority(request, request_path)
    validate_preview_contract(request,request_path)
    baseline = (validate(read_bound(previous['snapshot'], previous_verification_path), 'snapshot')
                if previous_verification_path is not None else validate(read_bound(request['baseline']['snapshot'], request_path), 'snapshot'))
    assets, _ = index_snapshot(baseline)
    if any(a['designSizeMode'] is None for a in assets.values()):
        raise ArtError('snapshot.design_mode', 'Actual Designer mode must be observed before planning a mutation.')
    scope = {s['assetPath']: s.get('widgetNames') for s in request['scope']}
    if len(scope) != len(request['scope']) or not set(scope) <= set(assets):
        raise ArtError('scope.assets', 'Scope assets must be unique and present in actual readback.')
    locked = _source_nodes(request, request_path)
    expected, operations, issues = copy.deepcopy(baseline), [], []
    seen = set()
    for decision in decisions['decisions']:
        op = copy.deepcopy(decision['operation'])
        check_operation(op)
        if op['id'] in seen:
            raise ArtError('operation.duplicate_id', 'Operation IDs must be unique.')
        seen.add(op['id'])
        if op['assetPath'] not in scope or (scope[op['assetPath']] is not None and op['widgetName'] not in scope[op['assetPath']]):
            raise ArtError('scope.operation', 'Operation is outside the requested local scope.')
        if decision['resolution'] == 'unresolved' or (decision['resolution'] == 'confirmed' and not decision.get('confirmation')):
            issues.append({'code': 'decision.unresolved', 'message': decision['evidence'],
                           'assetPath': op['assetPath'], 'widgetName': op['widgetName']})
            continue
        _check_design(op, locked, request)
        expected = advance_snapshot(expected, op)
        if op['before'] != op['after'] or op['kind'] in ('add-widget', 'remove-widget', 'import-resource'):
            operations.append(op)
    from art_presentation import validate_presentation
    presentation = validate_presentation(request, decisions, expected, request_path, decisions_path)
    issues.extend(presentation['issues'])
    plan = {'kind': 'nextgame-ui-art-plan', 'version': 1, 'request': binding(request_path),
        'decisions': binding(decisions_path), 'baselineStateSha256': state_hash(baseline),
        'expectedStateSha256': state_hash(expected), 'operations': operations,
        'status': 'needs-review' if issues else 'ready', 'issues': issues, 'round': round_number}
    if previous_verification_path is not None:
        plan['previousVerification'] = binding(previous_verification_path)
    return validate(plan, 'plan')


def _validated_plan(plan_path, *, validate_sources=True):
    plan_path = Path(plan_path).resolve()
    plan = validate(load_json(plan_path), 'plan')
    request_path = bound_path(plan['request'], plan_path)
    decisions_path = bound_path(plan['decisions'], plan_path)
    previous = bound_path(plan['previousVerification'], plan_path) if 'previousVerification' in plan else None
    rebuilt = create_plan(request_path, decisions_path, round_number=plan['round'], previous_verification_path=previous, validate_sources=validate_sources)
    if canonical(plan) != canonical(rebuilt):
        raise ArtError('plan.modified', 'Plan no longer reproduces from its sources and decisions.')
    if plan['status'] != 'ready':
        raise ArtError('plan.not_ready', 'Resolve the concentrated review issues before applying.')
    return plan, load_json(request_path), request_path


def _set_batch(operations, expected):
    """Select a bounded, unambiguous pure-set prefix; unsupported work stays legacy."""
    from art_editor import SLOT_PROPERTIES, WRITE_PROPERTIES
    selected, keys, hashes = [], [], {state_hash(expected)}
    for op in operations[:256]:
        kind = op['kind']
        if kind not in ('set-property', 'set-slot'):
            break
        field = op['property']
        if field.split('.')[0] not in (SLOT_PROPERTIES if kind == 'set-slot' else WRITE_PROPERTIES):
            break
        key = (op['assetPath'], op['widgetName'], kind, field)
        if any(key[:3] == prior[:3] and (field == prior[3] or field.startswith(prior[3] + '.')
                or prior[3].startswith(field + '.')) for prior in keys):
            break
        candidate = advance_snapshot(expected, op)
        stamp = state_hash(candidate)
        if stamp in hashes:
            break
        selected.append(op); keys.append(key); hashes.add(stamp); expected = candidate
    return selected if len(selected) > 1 else []


def _batch_artifact(checkpoint_path, label, value):
    path = checkpoint_path.with_name(checkpoint_path.stem + '.' + label + '.' + digest(value)[:16] + '.json')
    write_json(path, value)
    return binding(path)


def _native_value(value):
    # Exactly the native binary32 domain used by art_common.state, never an epsilon.
    import struct
    if isinstance(value, float):
        result = struct.unpack('f', struct.pack('f', value))[0]
        return int(result) if result.is_integer() else result
    if isinstance(value, dict):
        return {key: _native_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_native_value(item) for item in value]
    return value


def _batch_report_prefix(report, operations):
    """Check real per-operation receipts. A false setter never becomes a success."""
    def fail():
        raise ArtError('execution.batch_report', 'Batch result does not prove its successful operation prefix.')
    if not isinstance(report, dict) or set(report) != {'kind', 'version', 'status', 'results', 'referenceTrees'}:
        fail()
    if report['kind'] != 'nextgame-ui-art-set-batch-result' or report['version'] != 1 or report['status'] not in ('completed', 'failed'):
        fail()
    rows, trees = report['results'], report['referenceTrees']
    if not isinstance(rows, list) or not 1 <= len(rows) <= len(operations) or not isinstance(trees, list):
        fail()
    if report['status'] == 'completed' and len(rows) != len(operations):
        fail()
    by_asset = {}
    for item in trees:
        if not isinstance(item, dict) or set(item) != {'assetPath', 'tree'} or item['assetPath'] in by_asset:
            fail()
        if item['assetPath'] not in {o['assetPath'].split('.')[0] for o in operations} or not isinstance(item['tree'], dict):
            fail()
        by_asset[item['assetPath']] = item['tree']
    keys = {'operationId', 'assetPath', 'widgetName', 'property', 'instance', 'propertySchema',
            'before', 'after', 'setResult', 'status', 'stage', 'error'}
    for index, row in enumerate(rows):
        op = operations[index]
        if not isinstance(row, dict) or set(row) != keys:
            fail()
        if any(row[key] != op[source] for key, source in (('operationId', 'id'), ('assetPath', 'assetPath'),
                ('widgetName', 'widgetName'), ('property', 'property'))):
            fail()
        passed = report['status'] == 'completed' or index < len(rows) - 1
        if not passed:
            if row['status'] != 'failed' or not isinstance(row['error'], str) or not row['error']:
                fail()
            continue
        if row['status'] != 'passed' or row['stage'] != 'complete' or row['error'] is not None or row['setResult'] is not True:
            fail()
        tree = by_asset.get(op['assetPath'].split('.')[0], {})
        matches = [w for w in tree.get('widgets', []) if w.get('widgetName') == op['widgetName']]
        if len(matches) != 1 or row['instance'] != matches[0].get('slot' if op['kind'] == 'set-slot' else 'widget'):
            fail()
        if not isinstance(row['instance'], dict) or not row['instance'].get('refPath') or not isinstance(row['propertySchema'], dict):
            fail()
        for actual, intended in ((row['before'], op['before']), (row['after'], op['after'])):
            for part in op['property'].split('.'):
                if not isinstance(actual, dict) or part not in actual:
                    fail()
                actual = actual[part]
            if canonical(_native_value(actual)) != canonical(_native_value(intended)):
                fail()
    return len(rows) if report['status'] == 'completed' else len(rows) - 1


def _batch_result_path(checkpoint_path, intent):
    identity = {key: intent[key] for key in ('operationIds', 'operationsSha256', 'beforeStateSha256', 'beforeSnapshot', 'startedAt')}
    return checkpoint_path.with_name(checkpoint_path.stem + '.batch-result.' + digest(identity)[:24] + '.json')


def _resolve_batch(plan, checkpoint, checkpoint_path, expected, actual, *, recovery):
    intent = checkpoint['currentBatch']
    validate(intent, 'setBatchIntent')
    start = len(checkpoint['completedIds'])
    operations = plan['operations'][start:start + len(intent['operationIds'])]
    if checkpoint['currentOperation'] is not None or intent['operationIds'] != [o['id'] for o in operations] or intent['operationsSha256'] != digest(operations):
        raise ArtError('execution.batch_intent', 'Batch intent does not bind the exact next plan operations.')
    if len(_set_batch(operations, expected)) != len(operations):
        raise ArtError('execution.batch_ambiguous', 'Batch has duplicate targets or indistinguishable native prefixes.')
    result_path = _batch_result_path(checkpoint_path, intent)
    if intent['resultPath'] != str(result_path):
        raise ArtError('execution.batch_intent', 'Batch result location does not match its durable identity.')
    if 'result' in intent and bound_path(intent['result'], checkpoint_path) != result_path:
        raise ArtError('execution.batch_intent', 'Batch result binding differs from its declared immutable file.')
    if 'result' not in intent and result_path.is_file():
        intent['result'] = binding(result_path)
        write_json(checkpoint_path, checkpoint, replace=True)
    before = read_bound(intent['beforeSnapshot'], checkpoint_path)
    if intent['beforeStateSha256'] != state_hash(expected) or state_hash(before) != state_hash(expected):
        raise ArtError('execution.batch_intent', 'Batch before snapshot does not match the confirmed plan prefix.')
    candidates = [expected]
    for op in operations:
        candidates.append(advance_snapshot(candidates[-1], op))
    actual_hash = state_hash(actual)
    matches = [index for index, candidate in enumerate(candidates) if state_hash(candidate) == actual_hash]
    if len(matches) != 1:
        raise ArtError('execution.manual_recovery', 'Batch actual state does not uniquely match a declared prefix.')
    count = matches[0]
    report = read_bound(intent['result'], checkpoint_path) if 'result' in intent else None
    if report is not None and count != _batch_report_prefix(report, operations):
        raise ArtError('execution.manual_recovery', 'Batch actual prefix contradicts real setter results; no failed operation was accepted.')
    if report is None and not recovery:
        raise ArtError('execution.batch_report', 'A live batch requires its actual result receipt.')
    after_binding = _batch_artifact(checkpoint_path, 'batch-after', actual)
    receipt = {'kind': 'nextgame-ui-art-set-batch-receipt', 'version': 1, 'planSha256': checkpoint['planSha256'],
        'operationIds': intent['operationIds'], 'completedIds': intent['operationIds'][:count],
        'mode': 'actual-prefix-recovery' if recovery else 'official-result',
        'beforeSnapshot': intent['beforeSnapshot'], 'afterSnapshot': after_binding,
        'completedStateSha256': actual_hash, 'recordedAt': utc_now()}
    if report is not None:
        receipt['result'] = intent['result']
    validate(receipt, 'setBatchReceipt')
    checkpoint.setdefault('batchReceipts', []).append(_batch_artifact(checkpoint_path, 'batch-receipt', receipt))
    checkpoint['completedIds'].extend(intent['operationIds'][:count])
    checkpoint.update(currentBatch=None, currentOperation=None, expectedStateSha256=actual_hash, updatedAt=utc_now())
    write_json(checkpoint_path, checkpoint, replace=True)
    return candidates[count], count, report is not None and report['status'] == 'failed'


def _verify_batch_history(plan, baseline, checkpoint, checkpoint_path):
    """Receipts stay bound to actual snapshots and this plan on every replay."""
    ids = [o['id'] for o in plan['operations']]
    last_end = 0
    for source in checkpoint.get('batchReceipts', []):
        receipt = validate(read_bound(source, checkpoint_path), 'setBatchReceipt')
        if receipt['planSha256'] != checkpoint['planSha256'] or receipt['operationIds'][0] not in ids:
            raise ArtError('execution.batch_history', 'Batch receipt belongs to another plan.')
        start = ids.index(receipt['operationIds'][0]); count = len(receipt['completedIds'])
        operations = plan['operations'][start:start + len(receipt['operationIds'])]
        if start < last_end or receipt['operationIds'] != [o['id'] for o in operations] or receipt['completedIds'] != receipt['operationIds'][:count] or start + count > len(checkpoint['completedIds']):
            raise ArtError('execution.batch_history', 'Batch receipt is not a confirmed contiguous plan segment.')
        before = baseline
        for op in plan['operations'][:start]:
            before = advance_snapshot(before, op)
        after = before
        for op in operations[:count]:
            after = advance_snapshot(after, op)
        if state_hash(read_bound(receipt['beforeSnapshot'], checkpoint_path)) != state_hash(before) or state_hash(read_bound(receipt['afterSnapshot'], checkpoint_path)) != state_hash(after) or receipt['completedStateSha256'] != state_hash(after):
            raise ArtError('execution.batch_history', 'Batch actual evidence differs from its confirmed plan states.')
        if 'result' in receipt:
            if _batch_report_prefix(read_bound(receipt['result'], checkpoint_path), operations) != count:
                raise ArtError('execution.batch_history', 'Batch result contradicts its confirmed prefix.')
        elif receipt['mode'] != 'actual-prefix-recovery':
            raise ArtError('execution.batch_history', 'Official batch receipt is missing the actual result.')
        last_end = start + count


def apply_plan(plan_path, checkpoint_path, editor, *, validate_sources=True):
    """Compare-and-apply with durable intent, actual-state recovery and a process lock."""
    plan_path, checkpoint_path = Path(plan_path).resolve(), Path(checkpoint_path).resolve()
    plan, request, request_path = _validated_plan(plan_path, validate_sources=validate_sources)
    if not request['productionAuthorized'] and any(s['assetPath'].startswith('/Game/UI/UMG/') for s in request['scope']):
        raise ArtError('authorization.target', 'Updating the exact formal assets has not been authorized.')
    baseline = _plan_baseline(plan, plan_path, request, request_path)
    paths = [a['assetPath'] for a in baseline['assets']]
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = checkpoint_path.with_suffix(checkpoint_path.suffix + '.lock')
    with lock_path.open('a+b') as lock:
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            if lock.read(1) == b'':
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ArtError('execution.locked', 'Another process owns this art execution.') from exc
        else:
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ArtError('execution.locked', 'Another process owns this art execution.') from exc
        checkpoint = load_json(checkpoint_path) if checkpoint_path.exists() else {
            'kind': 'nextgame-ui-art-execution', 'version': 1, 'planSha256': sha256(plan_path),
            'status': 'running', 'completedIds': [], 'currentOperation': None,
            'expectedStateSha256': plan['baselineStateSha256'], 'startedAt': utc_now(), 'updatedAt': utc_now()}
        validate(checkpoint, 'execution')
        if checkpoint['planSha256'] != sha256(plan_path):
            raise ArtError('execution.stale_checkpoint', 'Checkpoint belongs to another plan.')
        prefix = len(checkpoint['completedIds'])
        if checkpoint['completedIds'] != [o['id'] for o in plan['operations'][:prefix]]:
            raise ArtError('execution.prefix', 'Checkpoint is not a contiguous plan prefix.')
        expected = baseline
        for op in plan['operations'][:prefix]:
            expected = advance_snapshot(expected, op)
        if checkpoint['expectedStateSha256'] != state_hash(expected):
            raise ArtError('execution.checkpoint_state', 'Checkpoint state does not match its confirmed prefix.')
        if checkpoint['status'] == 'completed' and (prefix != len(plan['operations']) or checkpoint.get('currentBatch') is not None or checkpoint['currentOperation'] is not None):
            raise ArtError('execution.prefix', 'Completed checkpoint has unfinished operations.')
        _verify_batch_history(plan, baseline, checkpoint, checkpoint_path)
        actual = editor.snapshot(paths)
        if checkpoint.get('currentBatch') is not None:
            expected, _, _ = _resolve_batch(plan, checkpoint, checkpoint_path, expected, actual, recovery=True)
            prefix = len(checkpoint['completedIds'])
        if checkpoint['currentOperation'] is not None:
            if prefix >= len(plan['operations']) or checkpoint['currentOperation'] != plan['operations'][prefix]['id']:
                raise ArtError('execution.intent', 'Invalid interrupted operation identity.')
            candidate = advance_snapshot(expected, plan['operations'][prefix])
            if plan['operations'][prefix]['kind'] == 'import-resource':
                # Import must independently inspect destination/source identity; execute is idempotent.
                pass
            elif state_hash(actual) == state_hash(candidate):
                expected = candidate
                checkpoint['completedIds'].append(checkpoint['currentOperation'])
                checkpoint['expectedStateSha256'] = state_hash(expected)
                checkpoint.update(currentOperation=None, updatedAt=utc_now())
                write_json(checkpoint_path, checkpoint, replace=True)
                prefix += 1
            elif state_hash(actual) != state_hash(expected):
                raise ArtError('execution.manual_recovery', 'Interrupted mutation differs from both before and after state.')
        if state_hash(actual) != state_hash(expected):
            raise ArtError('execution.stale_baseline', 'Actual Unreal state changed; take a new baseline and replan.')
        if hasattr(editor, 'preflight'):
            editor.preflight(plan['operations'])
        if hasattr(editor,'verify_import'):
            for op in plan['operations'][:prefix]:
                if op['kind']=='import-resource': editor.verify_import(op,require_exists=True)
        if checkpoint['status'] == 'completed':
            read_bound(checkpoint['readback'], checkpoint_path)
            return {'status': 'completed', 'changed': False, 'completedOperations': prefix,
                    'readback': checkpoint['readback']}
        # Before any mutation, every backend capability and import source must be available.
        try:
            while prefix < len(plan['operations']):
                batch = _set_batch(plan['operations'][prefix:], expected) if callable(getattr(editor, 'execute_batch', None)) else []
                if batch:
                    # actual is the complete initial/post-operation snapshot; each setter also CASes live state.
                    before = _batch_artifact(checkpoint_path, 'batch-before', actual)
                    checkpoint.update(status='running', currentOperation=None, currentBatch={
                        'capability': 'official-set-batch/1', 'version': 1,
                        'operationIds': [o['id'] for o in batch], 'operationsSha256': digest(batch),
                        'beforeStateSha256': state_hash(expected), 'beforeSnapshot': before, 'startedAt': utc_now()}, updatedAt=utc_now())
                    result_path = _batch_result_path(checkpoint_path, checkpoint['currentBatch'])
                    checkpoint['currentBatch']['resultPath'] = str(result_path)
                    checkpoint.pop('failure', None)
                    write_json(checkpoint_path, checkpoint, replace=True)
                    result = editor.execute_batch(batch)
                    write_json(result_path, result)
                    checkpoint['currentBatch']['result'] = binding(result_path)
                    write_json(checkpoint_path, checkpoint, replace=True)
                    actual = editor.snapshot(paths)
                    expected, count, failed = _resolve_batch(plan, checkpoint, checkpoint_path, expected, actual, recovery=False)
                    prefix += count
                    if failed:
                        raise ArtError('execution.batch_failed', 'Official batch stopped at a failed operation; its actual prefix was recorded.')
                    continue
                op = plan['operations'][prefix]
                checkpoint.update(status='running', currentOperation=op['id'], updatedAt=utc_now())
                checkpoint.pop('failure', None)
                write_json(checkpoint_path, checkpoint, replace=True)
                current = editor.snapshot(paths)
                if state_hash(current) != state_hash(expected):
                    raise ArtError('execution.concurrent_change', 'Widget state changed before the next operation.')
                next_state = advance_snapshot(expected, op)
                editor.execute(op)
                observed = editor.snapshot(paths)
                if state_hash(observed) != state_hash(next_state):
                    raise ArtError('execution.postcondition', 'Actual result differs from the planned property/node change.')
                expected, actual = next_state, observed
                prefix += 1
                checkpoint['completedIds'].append(op['id'])
                checkpoint.update(currentOperation=None, expectedStateSha256=state_hash(expected), updatedAt=utc_now())
                write_json(checkpoint_path, checkpoint, replace=True)
            if plan['operations']:
                editor.compile_save(sorted({o['assetPath'] for o in plan['operations']}))
            observed = editor.snapshot(paths)
            if state_hash(observed) != plan['expectedStateSha256']:
                raise ArtError('execution.saved_state', 'Post-save actual state differs from the approved result.')
            final_path = checkpoint_path.with_name(checkpoint_path.stem + '.' + digest(observed)[:16] + '.readback.json')
            write_json(final_path, observed)
            checkpoint.update(status='completed', currentOperation=None, readback=binding(final_path), updatedAt=utc_now())
            write_json(checkpoint_path, checkpoint, replace=True)
            return {'status': 'completed', 'changed': bool(plan['operations']),
                    'completedOperations': len(plan['operations']), 'readback': checkpoint['readback']}
        except Exception as exc:
            checkpoint.update(status='failed', failure=str(exc), updatedAt=utc_now())
            try:
                write_json(checkpoint_path, checkpoint, replace=True)
            except OSError:
                raise ArtError('execution.checkpoint_failure', 'Reacquire Unreal state before retrying; checkpoint could not be saved.') from exc
            raise


def prepare_packets(request_path, output_dir):
    from art_images import index_resources, match_candidates, create_review_sheet
    request_path, output_dir = Path(request_path).resolve(), Path(output_dir).resolve()
    request = validate(load_json(request_path), 'request')
    validate_preview_contract(request,request_path)
    imported={}
    if 'resourceCatalog' in request:
        from art_resources import validate_catalog
        catalog=validate_catalog(bound_path(request['resourceCatalog'],request_path))
        for resource in catalog['resources']:
            imported.setdefault(resource['sourceSha256'],[]).append(resource)
    if output_dir.is_relative_to(Path(request['resourceDir']).resolve()):
        raise ArtError('resources.output_overlap','Generated resources must not be written inside the indexed input directory.')
    inventory = index_resources(Path(request['resourceDir']), output_dir / 'resources', output_dir / '.resource-cache')
    write_json(output_dir / 'resource-index.json', inventory, replace=True)
    snapshot = read_bound(request['baseline']['snapshot'], request_path)
    _, nodes = index_snapshot(snapshot)
    packets = []
    calls = 0
    old_receipt_path=output_dir/'packet-receipt.json'
    old_receipt=load_json(old_receipt_path) if old_receipt_path.is_file() else {}
    previous_bindings={b['path']:b['sha256'] for b in old_receipt.get('packets',[])}
    samples=[]
    for source in request.get('samples',[]):
        sample_path=bound_path(source,request_path)
        sample=load_json(sample_path)
        if sample.get('version')!=1 or sample.get('status')!='reference-only' or sample.get('globalStandard') is not False:
            raise ArtError('sample.scope','Only scoped reference samples are accepted; samples are not global standards.')
        for key in ('reference','readback'): bound_path(sample[key],sample_path)
        for resource in sample['resources']: bound_path({k:resource[k] for k in ('path','sha256')},sample_path)
        samples.append((source,sample))
    region_count=sum(len(r['regions']) for r in request['references'])
    if region_count>request['budget']['maxModelCalls']:
        raise ArtError('budget.packet_scope','Region count exceeds one-call-per-region scope budget; consolidate reusable families or narrow the request.')
    for reference in request['references']:
        source = bound_path(reference['image'], request_path)
        for region in reference['regions']:
            key = digest({'request': sha256(request_path), 'reference': reference, 'region': region, 'baseline': request['baseline']['snapshot'],
                          'resources': [(r['id'], r['sha256']) for r in inventory['resources']],
                          'authority':[sha256(__file__),sha256(Path(__file__).with_name('art_images.py')),
                                       sha256(Path(__file__).with_name('art_presentation.py'))], 'algorithm': 1})
            packet_path = output_dir / 'packets' / (key + '.json')
            if packet_path.exists() and previous_bindings.get(str(packet_path))==sha256(packet_path):
                packet = load_json(packet_path)
                try:
                    intact=all(bound_path(b,packet_path) for b in packet['images'])
                except (ArtError,OSError,KeyError):
                    intact=False
                if packet.get('cacheKey') == key and packet.get('requestSha256') == sha256(request_path) and intact:
                    packets.append(binding(packet_path))
                    continue
            candidates = match_candidates(source, region['bounds'], inventory, limit=3)
            indexed={r['id']:r for r in inventory['resources']}
            for candidate in candidates:
                resource=indexed[candidate['resourceId']]
                matches=imported.get(resource['sha256'],[])
                # Keep distinct paths when identical PNG bytes were intentionally
                # imported to different systems. A model must not pick by basename.
                candidate['importedAssets']=[{k:entry[k] for k in ('sourceRelative','assetPath','classPath','brushResourceObject')} for entry in matches]
            sample_cards=[]
            ids={c['resourceId'] for c in candidates}
            for sample_binding,sample in samples:
                mappings=[m for m in sample['mappings'] if m['resourceId'] in ids]
                if mappings:
                    sample_cards.append({'sample':sample_binding,'scope':sample['scope'],'mappings':mappings,
                        'use':'reference-only; validate compatibility with the current accepted design'})
            sample_cards=sample_cards[:2]
            preview = output_dir / 'packets' / (key + '.png')
            preview.parent.mkdir(parents=True, exist_ok=True)
            create_review_sheet(source, [region], inventory, preview, {region['id']: candidates})
            needed = [nodes[(reference['assetPath'], n)] for n in region['widgetNames'] if (reference['assetPath'], n) in nodes]
            packet = {'kind': 'nextgame-ui-art-decision-packet', 'version': 1, 'cacheKey': key,
                'requestSha256': sha256(request_path), 'referenceId': reference['id'], 'regionId': region['id'],
                'assetPath': reference['assetPath'], 'widgets': needed, 'candidates': candidates,
                'samples':sample_cards,
                'images': [binding(preview)], 'outputContract': 'art-contract.schema.json#/$defs/decisions',
                'instruction': 'Choose among candidates using the local image. Report uncertainty. Preserve locked design and protected bindings; return decisions, not UE code.'}
            if 'presentation-review/1' in request.get('capabilities', []):
                packet['presentationReview'] = {
                    'capability':'presentation-review/1',
                    'coverage':'Every scoped Image/GameImage and TextBlock, including unchanged and collapsed widgets, needs a judgment. Merge by exact asset/widget identity.',
                    'imageChecks':'Use full source frame and separately observed alpha bounds. Bind the verified import catalog and native Brush. Declare preservation/stretch, source-pixel cuts and protected graphics/borders/shadows. Declare same-family membership explicitly; names and matching scores do not prove intent.',
                    'textChecks':'Inspect each text locally. Separate native property presence, visual fit, effect-type confidence and parameter confidence. Unknown is not none. Ask only residual ambiguous effect/parameter questions; method approval does not confirm appearance parameters.',
                    'evidenceBoundary':'These local images and static Slot arithmetic are not measured Widget geometry or canonical captures.'}
            write_json(packet_path, packet, replace=True)
            packets.append(binding(packet_path))
            calls += 1
    receipt = {'requestSha256': sha256(request_path), 'packets': packets, 'newPackets': calls,
               'reusedPackets': len(packets) - calls, 'modelCallsExecuted': 0}
    write_json(output_dir / 'packet-receipt.json', receipt, replace=True)
    return receipt


def verify_plan(plan_path, execution_path, captures_path, output_path, *, visual_review_path=None):
    from art_images import compare_images
    from art_reference import CAPABILITY, source_size, compare_mapped
    plan, request, request_path = _validated_plan(plan_path)
    execution_path, output_path = Path(execution_path).resolve(), Path(output_path).resolve()
    execution = validate(load_json(execution_path), 'execution')
    if execution['status'] != 'completed' or execution['planSha256'] != sha256(plan_path):
        raise ArtError('verify.execution', 'Verification needs the matching completed execution.')
    snapshot_path = bound_path(execution['readback'], execution_path)
    snapshot = read_bound(execution['readback'], execution_path)
    if state_hash(snapshot) != plan['expectedStateSha256']:
        raise ArtError('verify.readback', 'Actual snapshot does not match the final plan state.')
    captures = load_json(captures_path)
    if not isinstance(captures, list) or len(captures) != len(request['references']):
        raise ArtError('verify.captures', 'Supply one canonical capture binding per required reference.')
    by_ref = {c['referenceId']: c['capture'] for c in captures}
    if len(by_ref) != len(captures) or set(by_ref) != {r['id'] for r in request['references']}:
        raise ArtError('verify.coverage', 'Capture reference IDs must cover every reference exactly once.')
    from art_presentation import validate_presentation
    decisions_path = bound_path(plan['decisions'], plan_path)
    presentation = validate_presentation(request, load_json(decisions_path), snapshot, request_path, decisions_path, phase='actual')
    comparisons, checks = [], list(presentation['checks'])
    for reference in request['references']:
        capture_path = bound_path(by_ref[reference['id']], captures_path)
        capture = validate(load_json(capture_path), 'capture')
        if capture['assetPath'] != reference['assetPath'] or capture.get('canonical') is not True or capture.get('context') != reference['context'] or capture.get('snapshotSha256') != sha256(snapshot_path):
            raise ArtError('verify.capture_context', 'Capture must bind actual final state and the exact preview context.')
        source = bound_path(reference['image'], request_path)
        actual = bound_path(capture['image'], capture_path)
        from PIL import Image
        for image_path, expected_size in ((source, source_size(request, reference)), (actual, reference['context']['size'])):
            with Image.open(image_path) as image:
                if list(image.size) != expected_size:
                    raise ArtError('verify.size', 'Decoded image dimensions do not match the required context.')
        folder = output_path.parent / 'comparisons' / digest({'reference':reference,'plan':sha256(plan_path),'snapshot':sha256(snapshot_path),'capture':sha256(capture_path)})[:20]
        mapped = CAPABILITY in request.get('capabilities', [])
        comparison = compare_mapped(source, actual, folder, reference) if mapped else compare_images(source, actual, folder, reference['regions'])
        comparison.update(capture=binding(capture_path), referenceId=reference['id'])
        comparison_path = folder / 'bound-comparison.json'
        write_json(comparison_path, comparison)
        comparisons.append(binding(comparison_path))
        check_id = 'capture:' + reference['id'] if 'presentation-review/1' in request.get('capabilities', []) else reference['id']
        checks.append({'id': check_id, 'status': 'passed' if (comparison['coordinateSystemsVerified'] if mapped else comparison['dimensionAgreement']) else 'failed',
                       'details': 'Native source and canonical capture coordinate systems are separately verified; no pixel equivalence is asserted.' if mapped else 'Captured context and dimensions agree; local visual inspection remains required.'})
    if visual_review_path is None:
        review = {'kind': 'nextgame-ui-art-visual-review', 'version': 1, 'status': 'needs-review',
            'snapshotSha256': sha256(snapshot_path), 'comparisons': comparisons, 'reviewedAt': utc_now(),
            'reviewer': {'actorType': 'agent', 'confirmationSource': 'visual-inspection'},
            'message': 'Pending actual image inspection; this template is not acceptance.', 'inspectedRegions':
            [r['id'] + ':' + region['id'] for r in request['references'] for region in r['regions']],
            'unresolved': [{'code': 'visual.pending', 'message': 'Inspect all listed region comparisons.'}]}
        visual_review_path = output_path.with_name(output_path.stem + '.review-template.json')
        write_json(visual_review_path, review)
    else:
        review = validate(load_json(visual_review_path), 'visualReview')
    passed = review['status'] == 'passed' and not review['unresolved'] and all(c['status'] == 'passed' for c in checks)
    verification = {'kind': 'nextgame-ui-art-verification', 'version': 1, 'plan': binding(plan_path),
        'snapshot': binding(snapshot_path), 'execution': binding(execution_path), 'visualReview': binding(visual_review_path),
        'comparisons': comparisons, 'status': 'passed' if passed else 'needs-review', 'checks': checks, 'verifiedAt': utc_now()}
    validate(verification, 'verification')
    write_json(output_path, verification)
    if passed:
        requirement_path = bound_path(request.get('target', request['baseline'])['requirement'], request_path)
        stage = {'goal': request['goal'], 'request': binding(request_path), 'plan': binding(plan_path), 'verification': binding(output_path)}
        errors = validate_art_stage(stage, bundle_path=output_path, requirement=load_json(requirement_path), requirement_path=requirement_path)
        if errors:
            raise ArtError('verify.failed', str(errors))
    return {'status': verification['status'], 'verification': binding(output_path), 'visualReview': binding(visual_review_path), 'comparisons': comparisons}


def _editor(url, timeout):
    from art_editor import create_editor
    return create_editor(url, timeout=timeout)


def capture_reference(plan_path, execution_path, reference_id, output_path, editor):
    plan,request,request_path=_validated_plan(plan_path)
    execution=validate(load_json(execution_path),'execution')
    if execution['status']!='completed' or execution['planSha256']!=sha256(plan_path):
        raise ArtError('capture.execution','Capture requires the current completed art execution.')
    snapshot_path=bound_path(execution['readback'],execution_path)
    snapshot=load_json(snapshot_path)
    paths=[a['assetPath'] for a in snapshot['assets']]
    if state_hash(editor.snapshot(paths))!=state_hash(snapshot): raise ArtError('capture.stale','Unreal state changed after save.')
    reference=next((r for r in request['references'] if r['id']==reference_id),None)
    if reference is None: raise ArtError('capture.reference','Unknown required reference.')
    image_path=Path(output_path).with_suffix('.png')
    receipt=editor.capture(reference['assetPath'],image_path,reference['context'])
    # Renderer must itself prove the context, not merely echo a requested value.
    receipt.update(kind='nextgame-ui-art-capture',version=1,snapshotSha256=sha256(snapshot_path))
    validate(receipt,'capture')
    if receipt['assetPath']!=reference['assetPath'] or receipt['context']!=reference['context']:
        raise ArtError('capture.context','Renderer did not report the exact actual preview context.')
    if state_hash(editor.snapshot(paths))!=state_hash(snapshot): raise ArtError('capture.mutated','Preview changed the production baseline.')
    write_json(output_path,receipt)
    return {'referenceId':reference_id,'capture':binding(output_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('route', help='Choose the optional phase from the user task goal.')
    p.add_argument('--goal', choices=('developer-only', *ART_GOALS), required=True)
    p.add_argument('--has-baseline', action='store_true'); p.add_argument('--has-resources', action='store_true')
    p = commands.add_parser('validate'); p.add_argument('file', type=Path); p.add_argument('--type', required=True)
    p = commands.add_parser('init'); p.add_argument('job',type=Path); p.add_argument('--output',type=Path,required=True)
    p = commands.add_parser('packets'); p.add_argument('request', type=Path); p.add_argument('--output-dir', type=Path, required=True)
    p = commands.add_parser('plan'); p.add_argument('request', type=Path); p.add_argument('--decisions', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--round', type=int, default=0)
    p.add_argument('--previous-verification', type=Path)
    p = commands.add_parser('apply'); p.add_argument('plan', type=Path); p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--url', default='http://127.0.0.1:8000/mcp'); p.add_argument('--timeout', type=float, default=30)
    p = commands.add_parser('collect'); p.add_argument('--asset', action='append', required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--url', default='http://127.0.0.1:8000/mcp')
    p.add_argument('--timeout', type=float, default=30)
    p = commands.add_parser('capture'); p.add_argument('plan',type=Path); p.add_argument('--execution',type=Path,required=True)
    p.add_argument('--reference',required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--url',default='http://127.0.0.1:8000/mcp'); p.add_argument('--timeout',type=float,default=30)
    p = commands.add_parser('reserve-call'); p.add_argument('request',type=Path); p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--journal',type=Path,required=True); p.add_argument('--call-key',required=True); p.add_argument('--ledger',type=Path)
    p = commands.add_parser('sample'); p.add_argument('--reference',type=Path,required=True); p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--inventory',type=Path,required=True); p.add_argument('--mappings',type=Path,required=True)
    p.add_argument('--scope',required=True); p.add_argument('--output-dir',type=Path,required=True)
    p = commands.add_parser('verify'); p.add_argument('plan', type=Path); p.add_argument('--execution', type=Path, required=True)
    p.add_argument('--captures', type=Path, required=True); p.add_argument('--visual-review', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('stage'); p.add_argument('verification', type=Path); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--bundle-path',type=Path,required=True,help='Final Bundle location; emitted bindings resolve relative to its directory.')
    args = parser.parse_args(argv)
    try:
        if args.command == 'route':
            result = route(args.goal, has_baseline=args.has_baseline, has_resources=args.has_resources)
        elif args.command == 'validate':
            validate(load_json(args.file), args.type); result = {'valid': True}
        elif args.command == 'init':
            result=initialize_request(args.job,args.output)
        elif args.command == 'reserve-call':
            result=reserve_call(args.request,args.packet,args.journal,args.call_key,args.ledger)
        elif args.command == 'sample':
            from art_images import export_sample
            validate(load_json(args.snapshot),'snapshot')
            result=export_sample(args.reference,args.snapshot,load_json(args.inventory),load_json(args.mappings),args.output_dir,args.scope)
        elif args.command == 'packets':
            result = prepare_packets(args.request, args.output_dir)
        elif args.command == 'plan':
            plan = create_plan(args.request, args.decisions, round_number=args.round, previous_verification_path=args.previous_verification)
            write_json(args.output, plan)
            result = {'status': plan['status'], 'operationCount': len(plan['operations']), 'issues': plan['issues'], 'plan': binding(args.output)}
        elif args.command == 'apply':
            result = apply_plan(args.plan, args.checkpoint, _editor(args.url, args.timeout))
        elif args.command == 'collect':
            snapshot = _editor(args.url, args.timeout).snapshot(args.asset)
            validate(snapshot, 'snapshot'); write_json(args.output, snapshot)
            result = {'snapshot': binding(args.output), 'assetCount': len(snapshot['assets'])}
        elif args.command == 'capture':
            result=capture_reference(args.plan,args.execution,args.reference,args.output,_editor(args.url,args.timeout))
        elif args.command == 'verify':
            result = verify_plan(args.plan, args.execution, args.captures, args.output, visual_review_path=args.visual_review)
        elif args.command == 'stage':
            verification = validate(load_json(args.verification), 'verification')
            plan_path = bound_path(verification['plan'], args.verification)
            plan, request, request_path = _validated_plan(plan_path)
            def relative_binding(path):
                value=binding(path)
                value['path']=Path(os.path.relpath(Path(path).resolve(),args.bundle_path.resolve().parent)).as_posix()
                return value
            stage = {'goal': request['goal'], 'request': relative_binding(request_path), 'plan': relative_binding(plan_path), 'verification': relative_binding(args.verification)}
            requirement_path = bound_path(request.get('target', request['baseline'])['requirement'], request_path)
            errors = validate_art_stage(stage, bundle_path=args.bundle_path, requirement=load_json(requirement_path), requirement_path=requirement_path)
            if errors:
                raise ArtError('stage.incomplete', str(errors))
            write_json(args.output, stage)
            result = {'stage': binding(args.output), 'nextAction': 'finalize-bundle-0.4-and-fresh-normalized-readback', 'userAcceptance': 'still-required'}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ArtError, OSError, ValueError, KeyError, RuntimeError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': {'code': getattr(exc, 'code', 'art.failure'), 'message': str(exc)}}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
