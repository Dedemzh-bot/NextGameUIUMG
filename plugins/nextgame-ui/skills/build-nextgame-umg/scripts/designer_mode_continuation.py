#!/usr/bin/env python3
"""Explicit, narrowly scoped Designer-mode continuation; never resumes Create.

inspect/validate are offline. execute requires a separate precise capability,
the accepted formal inputs, an explicit saved-file CAS and before enum. The
original failed checkpoint stays failed and is bound byte-for-byte.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

sys.dont_write_bytecode = True
import execute_existing_update_v2 as existing
from execute_plan import resolve
from execute_plan_programmatic import _reference_expressions, plan_digest
from art_common import aware_time

CAPABILITY = 'designer-mode-continuation/1'
KIND = 'nextgame-ui-designer-mode-continuation'
ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT.parents[1]
SCHEMA = ROOT / 'assets/designer-mode-continuation.schema.json'
MODES = {'FillScreen', 'Desired', 'DesiredOnScreen', 'Custom', 'CustomOnScreen'}
SUBSTITUTED = ('list-design-size-mode-property', 'get-design-size-mode-before',
               'set-design-size-mode', 'get-saved-blueprint-default-object', 'verify-design-size-mode')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON: ' + x)))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha(path)}


def bound(ref, owner):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'Invalid exact file binding')
    path = Path(ref['path'])
    path = path.resolve(strict=True) if path.is_absolute() else (Path(owner).parent / path).resolve(strict=True)
    require(sha(path) == ref['sha256'], 'Bound file changed: ' + str(path))
    return path


def event_result(event, checkpoint, checkpoint_path):
    """Hydrate an event's actual sidecar, never the checkpoint's final saved map."""
    value = event.get('result')
    if isinstance(value, dict) and 'resultSha256' in value:
        key = value['resultSha256']
        descriptor = checkpoint.get('evidence', {}).get('results', {}).get(key)
        require(isinstance(descriptor, dict) and all(value.get(k) == descriptor.get(k)
                for k in ('resultSha256', 'mimeType', 'byteLength', 'artifactPath')), 'Event result sidecar is unbound')
        path = Path(descriptor['artifactPath'])
        if not path.is_absolute():
            path = Path(checkpoint_path).parent / path
        require(sha(path) == key and path.stat().st_size == descriptor['byteLength'], 'Event result sidecar changed')
        return load(path)
    return value


def ordered_arguments(steps, events, checkpoint, checkpoint_path):
    """Resolve every call from only earlier ordered completed event results."""
    saved, arguments = {}, []
    for index, (step, event) in enumerate(zip(steps, events), 1):
        require(event.get('status') == 'completed' and event.get('index') == index
                and event.get('stepId') == step.get('stepId')
                and event.get('tool') == step.get('toolsetName', '') + '.' + step.get('toolName', ''),
                'Completed event does not match its original ordered step')
        list(_reference_expressions(step.get('arguments', {})))
        arguments.append(resolve(step.get('arguments', {}), saved))
        if step.get('saveResultAs'):
            saved[step['saveResultAs']] = event_result(event, checkpoint, checkpoint_path)
    return arguments, saved


def inspect_failed(plan_path, checkpoint_path):
    plan, checkpoint = load(plan_path), load(checkpoint_path)
    require(plan.get('version') == '0.2', 'Only original new-build plan 0.2 is supported')
    path = plan.get('assetPath')
    require(isinstance(path, str) and path.startswith('/Game/UI/UMG/'), 'Require exact formal UI asset')
    obj = path + '.' + path.rsplit('/', 1)[-1]
    cdo = path + '.Default__' + path.rsplit('/', 1)[-1] + '_C'
    target = plan.get('designSizeMode')
    require(plan.get('objectPath') == obj and target in {'FillScreen', 'Desired'}, 'Unsupported target or Designer mode')
    contract = plan.get('executorContract', {}).get('designSizeModeWrite', {})
    require(contract == {'primary': 'official-unreal-mcp generated-CDO ObjectTools list/get/set',
            'fallback': 'nxue manage-property only when the official route does not expose the protected CDO field',
            'cdoObjectPath': cdo, 'propertyPath': 'DesignSizeMode', 'expectedValue': target,
            'requiresPostSaveReadback': True}, 'Original plan lacks the exact existing protected-field fallback contract')
    steps, events = plan.get('steps'), checkpoint.get('events')
    prefix = checkpoint.get('completedPrefix')
    require(isinstance(steps, list) and isinstance(events, list) and type(prefix) is int and 2 <= prefix < len(steps), 'Invalid failed prefix')
    require(checkpoint.get('formatVersion') == 2 and checkpoint.get('planSha256') == plan_digest(plan)
            and checkpoint.get('status') == 'failed' and type(checkpoint.get('requiresGetWidgets')) is bool,
            'Require the exact unchanged failed programmatic checkpoint')
    require(steps[prefix]['stepId'] == SUBSTITUTED[0]
            and steps[prefix-1]['stepId'] == 'get-blueprint-default-object'
            and steps[prefix-2]['stepId'] == 'compile', 'Failure must be immediately after final compile/CDO acquisition')
    require(len(events) > prefix, 'Missing original failure suffix')
    resolved, saved = ordered_arguments(steps[:prefix], events[:prefix], checkpoint, checkpoint_path)
    require(resolved[-2] == {'widgetBlueprint': {'refPath': obj}}
            and event_result(events[prefix-2], checkpoint, checkpoint_path).get('returnValue') is True,
            'Original final compile must prove exact target and true result')
    require(resolved[-1] == {'blueprint': {'refPath': obj}}
            and saved.get('blueprintDefaultObject', {}).get('returnValue', {}).get('refPath') == cdo,
            'Original CDO result identity mismatch')
    for event in events[prefix:]:
        require(event.get('status') == 'failed' and event.get('index') == prefix+1
                and event.get('stepId') == steps[prefix]['stepId']
                and event.get('tool') == existing.art.OBJ + '.list_properties',
                'Only repeated failures of the same unsupported schema step are permitted')
    tail = steps[prefix:]
    require([s['stepId'] for s in tail[:7]] == [SUBSTITUTED[0], SUBSTITUTED[1], SUBSTITUTED[2],
            'save', SUBSTITUTED[3], SUBSTITUTED[4], 'verify-tree'], 'Unknown original Designer/save/verify tail')
    for step in tail[7:]:
        require(step.get('operation', 'call_tool') == 'call_tool' and step.get('toolsetName') == existing.art.OBJ
                and step.get('toolName') == 'get_properties' and step['stepId'].startswith('verify-layout-'),
                'Continuation tail may contain only original post-save layout reads')
    return {'plan': plan, 'checkpoint': checkpoint, 'saved': saved, 'prefix': prefix,
            'assetPath': path, 'objectPath': obj, 'cdoPath': cdo, 'targetMode': target,
            'tail': tail, 'resolvedPrefix': resolved}


def _mode_from_journal(row, expected_cdo):
    require(row['provider'] == 'nxue-agent' and row['request'] == {'CDO': expected_cdo, 'property': 'DesignSizeMode'}
            and row['response'] in MODES, 'Invalid exact Designer-mode getter evidence')
    return row['response']


def _status_port(data, project):
    require(isinstance(data, dict) and data.get('server_running') is True
            and type(data.get('server_port')) is int and 0 < data['server_port'] < 65536
            and isinstance(data.get('project_dir'), str) and Path(data['project_dir']).resolve() == project,
            'NxUE status must bind the explicit project directory and live server port')
    project_files = list(project.glob('*.uproject'))
    require(len(project_files) == 1 and data.get('project_name') == project_files[0].stem,
            'NxUE project name mismatch')
    return data['server_port']


def listener_pid(url):
    parsed = urlparse(url)
    require(parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
            and parsed.username is None and parsed.password is None and parsed.port is not None,
            'Provide explicit loopback MCP URL with port and no credentials')
    # Port is parsed as an integer, never interpolated from untrusted shell text.
    command = ['powershell', '-NoProfile', '-NonInteractive', '-Command',
               '(Get-NetTCPConnection -State Listen -LocalPort ' + str(parsed.port)
               + ' -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique) | ConvertTo-Json -Compress']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
    require(result.returncode == 0, 'Cannot obtain local MCP listener process identity')
    value = json.loads(result.stdout)
    pids = value if isinstance(value, list) else [value]
    require(len(set(pids)) == 1 and all(type(p) is int and p > 0 for p in pids), 'Ambiguous MCP listener process')
    return {'url': url, 'port': parsed.port, 'pid': pids[0], 'method': 'local-tcp-listener-owner'}


class AuditJournal(existing.Journal):
    def __init__(self, out):
        super().__init__(out)
        self.rows = []

    def step(self, label, payload, fn):
        provider = ('official-unreal-mcp' if label.startswith(('UMGToolSet.', 'editor_toolset.')) else
                    'offline-formal-validator' if label == 'formal-validation' else
                    'local-os' if label.startswith(('mcp-listener-', 'nxue-listener-')) else
                    'local-filesystem' if label.startswith('asset-file-cas-') else
                    'derived-contract' if label == 'designer-fallback-protocol' else 'nxue-agent')
        sequence = self.sequence + 1
        try:
            return super().step(label, payload, fn)
        finally:
            path = self.out / 'steps' / f'{sequence:05d}.json'
            if path.exists():
                row = load(path)
                row['provider'] = provider
                existing.durable(path, row)
                self.rows.append(bind(path))


class ContinuationEditor(existing.Editor):
    def __init__(self, project, url, timeout, journal, cas_guard):
        super().__init__(project, url, timeout, journal)
        self.url, self.identity, self.cas_guard = url, None, cas_guard

    def same_process(self, label):
        status = super().nx(['status'], 'nxue-status-' + label)
        port = _status_port(status.get('data'), self.project)
        owner = self.journal.step('mcp-listener-' + label, {'url': self.url}, lambda: listener_pid(self.url))
        nxue_url = 'http://127.0.0.1:' + str(port)
        nxue_owner = self.journal.step('nxue-listener-' + label, {'url': nxue_url}, lambda: listener_pid(nxue_url))
        pid = nxue_owner['pid']
        require(owner['pid'] == pid, 'MCP and NxUE refer to different Editor processes')
        require(self.identity is None or self.identity == pid, 'Editor process changed during continuation')
        self.identity = pid
        return pid

    def invoke(self, ts, tool, args):
        if tool in {'CompileWidgetBlueprint', 'save_assets'}:
            self.same_process('before-' + tool)
            self.cas_guard('before-' + tool)
        return super().invoke(ts, tool, args)

    def nx(self, arguments, label):
        if arguments[:2] == ['tool', 'manage-property']:
            payload = json.loads(arguments[arguments.index('--args-json')+1])
            if payload.get('action') == 'set':
                self.same_process('before-designer-set')
                self.cas_guard('before-designer-set')
        return super().nx(arguments, label)


def _tree_identity(tree):
    rows = []
    for widget in tree['widgets']:
        require(isinstance(widget.get('widgetName'), str), 'GetWidgets lacks actual widget identity')
        reference = existing.art._ref(widget.get('widget'))
        class_path = existing.art._ref(widget.get('widgetClassPath'))
        if reference:
            require(class_path and type(widget.get('bIsVariable')) is bool and type(widget.get('bInherited')) is bool,
                    'GetWidgets lacks actual class or variable/inheritance fields')
        rows.append((widget['widgetName'], reference, class_path, existing.art._ref(widget.get('parent')),
                     existing.art._ref(widget.get('slot')), existing.art._ref(widget.get('namedSlotHost')),
                     widget.get('bIsVariable'), widget.get('bInherited')))
    return {'parentClass': existing.art._ref(tree['info'].get('parentClass')),
            'rootWidgetClass': existing.art._ref(tree['info'].get('rootWidgetClass')), 'orderedWidgets': rows}


def canonical_plan(context, project, layout_path):
    import prepare_build
    declared = Path(context['plan']['sourceSpec'])
    actual = declared.resolve() if declared.is_absolute() else (project / declared).resolve()
    require(actual == Path(layout_path).resolve(strict=True), 'Plan source layout identity mismatch')
    rebuilt = prepare_build.build_plan(declared, load(actual), load(prepare_build.DEFAULT_CATALOG), load(prepare_build.DEFAULT_RULES))
    require(rebuilt == context['plan'], 'Plan differs from the current canonical source-layout lowering')


def approved_plan_link(context, layout_path, requirement_path, view_path, bundle_path):
    """The exact plan target must be the unique accepted asset/layout/mode."""
    requirement, view, bundle = load(requirement_path), load(view_path), load(bundle_path)
    require(requirement.get('version') == '0.2', 'Continuation/1 currently supports structured-source Requirement 0.2 only')
    link = bundle['requirement']
    linked_path = Path(link['path'])
    linked_path = linked_path.resolve() if linked_path.is_absolute() else (Path(bundle_path).parent/linked_path).resolve()
    review = requirement['reviewGate']
    require(linked_path == Path(requirement_path).resolve() and link['sha256'] == sha(requirement_path)
            and link['requestId'] == requirement['requestId'] == view['requestId']
            and link['revision'] == requirement['revision'] == view['revision']
            and review['status'] == link['reviewStatus'] == 'accepted'
            and review['approvedContentSha256'] == link['approvedContentSha256'] == view['bindings']['approvedContentSha256']
            and view['bindings']['requirementFileSha256'] == sha(requirement_path) and view['buildAllowed'] is True,
            'Requirement/View/Bundle source identity or accepted approval differs')
    candidates = [a for a in bundle['assets'] if a['assetPath'] == context['assetPath']]
    require(len(candidates) == 1, 'Plan target is not the unique approved Bundle asset')
    asset = candidates[0]
    bound_layout = Path(asset['layoutSpecPath'])
    bound_layout = bound_layout.resolve() if bound_layout.is_absolute() else (Path(bundle_path).parent/bound_layout).resolve()
    require(bound_layout == Path(layout_path).resolve() and asset['layoutSpecSha256'] == sha(layout_path),
            'Plan layout path/bytes are not the approved Bundle layout')
    plans = [a for a in requirement['assetPlan'] if a['id'] == asset['assetPlanId'] and a['assetPath'] == context['assetPath']]
    projected = [a for a in view['requirement']['assetPlan'] if a['id'] == asset['assetPlanId'] and a['assetPath'] == context['assetPath']]
    require(len(plans) == len(projected) == 1 and plans[0].get('inBuildScope') is True
            and projected[0] == plans[0]
            and plans[0]['designSizeModeDecision']['mode'] == context['targetMode']
            and load(layout_path)['profile']['designSizeMode'] == context['targetMode'],
            'Accepted Requirement/View do not authorize this exact target Designer mode')


def development_bundle_link(source_path, development_path, receipt_path, started_at):
    """Allow only observed lifecycle/evidence advancement of an immutable source."""
    source, development = load(source_path), load(development_path)
    before, after = copy.deepcopy(source), copy.deepcopy(development)
    for document, owner in ((before, source_path), (after, development_path)):
        # A later frozen file may use a different relative spelling for exactly
        # the same immutable Requirement/Layout files. Normalize those two
        # existing binding surfaces; all other content remains exact.
        for record, key in [(document['requirement'], 'path')] + [(a, 'layoutSpecPath') for a in document['assets']]:
            path = Path(record[key])
            record[key] = str(path.resolve() if path.is_absolute() else (Path(owner).parent/path).resolve())
    require(before['execution']['status'] in {'pending', 'running'} and after['execution']['status'] == 'running',
            'Development lifecycle must advance an unfinished execution to running')
    require('completedAt' not in before['execution'] and 'completedAt' not in after['execution'], 'Development Bundle cannot claim final execution completion')
    before['execution'].pop('status'); after['execution'].pop('status')
    if 'startedAt' not in before['execution']:
        require('startedAt' in after['execution'] and aware_time(after['execution']['startedAt']) <= aware_time(started_at),
                'Development start must be the actual build interval, no later than continuation start')
        after['execution'].pop('startedAt')
    require(len(before['assets']) == len(after['assets']), 'Asset obligations changed')
    for old, new in zip(before['assets'], after['assets']):
        require(old['status'] in {'planned', 'built'} and new['status'] == 'built', 'Only planned/built-to-built asset advancement is supported')
        old.pop('status'); new.pop('status')
    checks_before, checks_after = before['verification']['checks'], after['verification']['checks']
    require(len(checks_before) == len(checks_after), 'Verification obligations changed')
    for old, new in zip(checks_before, checks_after):
        old_status, new_status = old.pop('status'), new.pop('status')
        require(old_status in {'pending', 'passed'} and new_status in {'pending', 'passed'}
                and (old_status != 'passed' or new_status == 'passed'), 'Cannot erase failure or regress an already passed obligation')
        if old_status == 'pending' and old['type'] in {'schema', 'compile', 'save', 'widget-tree', 'key-properties'}:
            if old['type'] in {'compile', 'save'}:
                require(new_status == 'passed' and 'artifactPath' in new, 'Actual continuation compile/save evidence is required')
                artifact = Path(new['artifactPath'])
                artifact = artifact.resolve() if artifact.is_absolute() else (Path(development_path).parent/artifact).resolve()
                require(artifact == Path(receipt_path).resolve(), 'Compile/save points to another continuation receipt')
            old.pop('artifactPath', None); new.pop('artifactPath', None)
    require(before == after, 'Development Bundle changed immutable requirement/layout/mapping/check obligations or unsupported fields')


def execute(args):
    require(args.capability == CAPABILITY, 'Exact continuation capability required')
    require(args.review_draft is None, 'Continuation/1 does not support raw-analysis review-draft execution')
    project = args.project.resolve(strict=True)
    out = args.output.resolve()
    require(out.is_relative_to(project / 'Saved') and not out.exists(), 'Use a new output directory inside project Saved')
    context = inspect_failed(args.plan, args.failed_checkpoint)
    out.mkdir(parents=True, exist_ok=False)
    journal = AuditJournal(out)
    receipt = {'kind': KIND, 'version': '1', 'capability': CAPABILITY, 'status': 'started',
               'assetPath': context['assetPath'], 'objectPath': context['objectPath'], 'expectedMode': context['targetMode'],
               'beforeMode': args.before_mode, 'startedAt': existing.now(), 'visualVerified': False,
               'originalCheckpointStatus': 'unchanged-failed', 'substitutedStepIds': list(SUBSTITUTED), 'journal': [], 'tailReadbacks': []}
    original_hashes = {Path(args.plan).resolve(): sha(args.plan), Path(args.failed_checkpoint).resolve(): sha(args.failed_checkpoint)}
    receipt_path = out / 'receipt.json'
    existing.durable(receipt_path, receipt)
    try:
        project_files = list(project.glob('*.uproject'))
        require(len(project_files) == 1, 'Project directory must identify exactly one uproject')
        require(args.before_mode in MODES, 'Explicit observed before mode required')
        asset_file = project / 'Content' / (context['assetPath'][len('/Game/'):] + '.uasset')
        require(sha(asset_file) == args.asset_sha256, 'Saved asset CAS differs from the explicitly reviewed baseline')
        (out / 'before.uasset').write_bytes(asset_file.read_bytes())
        layout_path = Path(context['plan']['sourceSpec'])
        if not layout_path.is_absolute():
            layout_path = project / layout_path
        canonical_plan(context, project, layout_path)
        approved_plan_link(context, layout_path, args.requirement, args.accepted_build_view, args.bundle)
        receipt['inputs'] = {'plan': bind(args.plan), 'failedCheckpoint': bind(args.failed_checkpoint),
            'projectFile': bind(project_files[0]), 'beforeAsset': bind(out / 'before.uasset'),
            'layout': bind(layout_path), 'requirement': bind(args.requirement), 'acceptedBuildView': bind(args.accepted_build_view), 'bundle': bind(args.bundle)}
        receipt.update(planSha256=plan_digest(context['plan']), originalCompletedPrefix=context['prefix'],
                       sourceAssetFile=str(asset_file), mcpURL=args.url)
        receipt['formalBindings'] = existing.gates(args, out, journal)
        def cas_guard(label):
            def check():
                for ref in list(receipt['inputs'].values()) + list(receipt['formalBindings'].values()):
                    bound(ref, receipt_path)
                observed = sha(asset_file)
                require(observed == args.asset_sha256, 'Physical saved asset CAS changed before mutation')
                return {'observedSha256': observed}
            return journal.step('asset-file-cas-'+label, {'path': str(asset_file), 'expectedSha256': args.asset_sha256}, check)
        editor = ContinuationEditor(project, args.url, args.timeout, journal, cas_guard)
        editor.same_process('preflight')
        tree_before = editor.tree(context['assetPath'])  # independent recovery; old checkpoint remains unchanged
        receipt['recoveryGetWidgetsSequence'] = journal.sequence
        require(editor.invoke(existing.art.ASSET, 'is_dirty', {'asset_path': context['assetPath']}) is False,
                'Current asset must have an explicit clean official result')
        require(sha(asset_file) == args.asset_sha256, 'Saved asset changed during preflight')
        compiled = editor.invoke(existing.art.UMG, 'CompileWidgetBlueprint', {'widgetBlueprint': {'refPath': context['objectPath']}})
        require(compiled is True, 'Continuation compile failed')
        receipt['compileSequence'] = journal.sequence
        # The existing exact typed preflight/CAS implementation is the only
        # setter path; this runner neither writes generic properties nor Python.
        op = {'assetPath': context['assetPath'], 'before': args.before_mode, 'after': context['targetMode']}
        route = existing.designer_preflight(editor, op)
        require(route['route'] == 'nxue-protected-property',
                'Official field is available; protected-field continuation must stop before attempting a write')
        editor.nx(['tool', 'manage-property', '--args-json', json.dumps({'action': 'set', 'objectPath': route['ref'],
                  'propertyPath': 'DesignSizeMode', 'value': context['targetMode']})], 'set-exact-designer-mode-fallback')
        immediate = journal.step('designer-fallback-after', {'CDO': route['ref'], 'property': 'DesignSizeMode'},
                                 lambda: editor.nxue.design_size_mode(route['ref']))
        require(immediate == context['targetMode'], 'Immediate Designer mode post-read mismatch')
        saved = editor.invoke(existing.art.ASSET, 'save_assets', {'asset_paths': [context['assetPath']]})
        require(saved is True, 'Continuation save failed')
        receipt['saveSequence'] = journal.sequence
        saved_asset_sha = sha(asset_file)
        (out / 'after.uasset').write_bytes(asset_file.read_bytes())
        require(sha(out/'after.uasset') == saved_asset_sha, 'Saved asset changed while acquiring immutable after bytes')
        cdo = editor.invoke(existing.art.BP, 'get_default_object', {'blueprint': {'refPath': context['objectPath']}})
        require(existing.art._ref(cdo) == context['cdoPath'], 'Post-save CDO changed identity')
        after_mode = journal.step('continuation-post-save-mode', {'CDO': context['cdoPath'], 'property': 'DesignSizeMode'},
                                  lambda: editor.nxue.design_size_mode(context['cdoPath']))
        require(after_mode == context['targetMode'], 'Saved Designer mode mismatch')
        receipt['postSaveModeSequence'] = journal.sequence
        saved_values = copy.deepcopy(context['saved'])
        saved_values['savedBlueprintDefaultObject'] = {'returnValue': cdo}
        for step in context['tail'][6:]:
            arguments = resolve(step.get('arguments', {}), saved_values)
            result = editor.invoke(step['toolsetName'], step['toolName'], arguments)
            receipt['tailReadbacks'].append({'stepId': step['stepId'], 'arguments': arguments, 'sequence': journal.sequence})
            if step.get('saveResultAs'):
                saved_values[step['saveResultAs']] = {'returnValue': result}
            if step['stepId'] == 'verify-tree':
                require(_tree_identity(tree_before) == _tree_identity(result), 'Tree identity changed across the protected-mode-only continuation')
        require(editor.invoke(existing.art.ASSET, 'is_dirty', {'asset_path': context['assetPath']}) is False,
                'Asset must have an explicit clean official result after post-save reads')
        editor.same_process('completed')
        require(sha(asset_file) == saved_asset_sha, 'Another save changed the physical asset during post-save verification')
        receipt.update(status='completed', completedAt=existing.now(), finalMode=after_mode, editorPid=editor.identity,
                       afterAsset=bind(out / 'after.uasset'), journal=journal.rows)
        for path, digest in original_hashes.items():
            require(sha(path) == digest, 'Original plan or failed checkpoint changed during continuation')
        receipt['authority'] = [bind(p) for p in (Path(__file__), SCHEMA, Path(existing.__file__), Path(existing.art.__file__))]
        existing.durable(receipt_path, receipt)
        validate_receipt(receipt_path, args.plan)
        return {'status': 'completed', 'receipt': str(receipt_path), 'originalCheckpointChanged': False, 'visualVerified': False}
    except Exception as exc:
        receipt.update(status='failed-stop-inspect-required', failedAt=existing.now(), error=str(exc), journal=journal.rows)
        existing.durable(receipt_path, receipt)
        raise


def validate_receipt(receipt_path, expected_plan, expected_bundle=None):
    """Validate the separate truthful mixed-provider evidence; no Editor calls."""
    import jsonschema
    receipt_path = Path(receipt_path).resolve(strict=True)
    receipt = load(receipt_path)
    jsonschema.Draft202012Validator(load(SCHEMA)).validate(receipt)
    require(receipt['status'] == 'completed', 'Continuation is not completed')
    inputs = {key: bound(ref, receipt_path) for key, ref in receipt['inputs'].items()}
    require(inputs['plan'] == Path(expected_plan).resolve(strict=True), 'Continuation belongs to another plan')
    if expected_bundle is not None:
        development_bundle_link(inputs['bundle'], Path(expected_bundle).resolve(strict=True), receipt_path, receipt['startedAt'])
    context = inspect_failed(inputs['plan'], inputs['failedCheckpoint'])
    canonical_plan(context, inputs['projectFile'].parent, inputs['layout'])
    approved_plan_link(context, inputs['layout'], inputs['requirement'], inputs['acceptedBuildView'], inputs['bundle'])
    require(receipt['assetPath'] == context['assetPath'] and receipt['objectPath'] == context['objectPath']
            and receipt['expectedMode'] == receipt['finalMode'] == context['targetMode']
            and receipt['planSha256'] == plan_digest(context['plan']) and receipt['originalCompletedPrefix'] == context['prefix'],
            'Continuation target/prefix binding mismatch')
    for ref in receipt['authority']:
        bound(ref, receipt_path)
    require({bound(ref, receipt_path) for ref in receipt['authority']} ==
            {Path(__file__).resolve(), SCHEMA.resolve(), Path(existing.__file__).resolve(), Path(existing.art.__file__).resolve()},
            'Continuation authority set differs from the exact capability implementation')
    bound(receipt['afterAsset'], receipt_path)
    rows = [load(bound(ref, receipt_path)) for ref in receipt['journal']]
    require(rows and [r['sequence'] for r in rows] == list(range(1, len(rows)+1))
            and all(r['status'] == 'completed' for r in rows), 'Incomplete or unordered continuation journal')
    row_schema = load(SCHEMA)
    row_validator = jsonschema.Draft202012Validator({'$ref': '#/$defs/journalRow', '$defs': row_schema['$defs']})
    for row in rows:
        row_validator.validate(row)
    phases = ('preflight', 'before-CompileWidgetBlueprint', 'before-designer-set', 'before-save_assets', 'completed')
    allowed = {'formal-validation', 'designer-fallback-protocol', 'designer-fallback-before', 'designer-fallback-after',
               'discover-exact-designer-fallback', 'discover-exact-designer-property', 'set-exact-designer-mode-fallback',
               'continuation-post-save-mode', existing.art.UMG+'.GetWidgets', existing.art.UMG+'.CompileWidgetBlueprint',
               existing.art.BP+'.get_default_object', existing.art.OBJ+'.list_properties', existing.art.OBJ+'.get_properties',
               existing.art.ASSET+'.save_assets', existing.art.ASSET+'.is_dirty'}
    allowed.update(prefix+phase for prefix in ('nxue-status-', 'mcp-listener-', 'nxue-listener-') for phase in phases)
    allowed.update('asset-file-cas-'+phase for phase in phases if phase.startswith('before-'))
    require(all(row['label'] in allowed for row in rows), 'Unexpected operation in single-purpose continuation')
    for label, expected_count in ((existing.art.UMG+'.CompileWidgetBlueprint', 1), (existing.art.ASSET+'.save_assets', 1),
                                  ('set-exact-designer-mode-fallback', 1), (existing.art.UMG+'.GetWidgets', 2),
                                  (existing.art.ASSET+'.is_dirty', 2), (existing.art.OBJ+'.list_properties', 1)):
        require(sum(row['label'] == label for row in rows) == expected_count, 'Unexpected call multiplicity: '+label)
    formal = [row for row in rows if row['label'] == 'formal-validation']
    require(len(formal) == 4 and all(row['provider'] == 'offline-formal-validator' and row['response'].get('returnCode') == 0
            for row in formal), 'Missing successful formal gate receipts')
    gate_names = {'validate_requirement_spec.py', 'validate_accepted_build_view.py', 'validate_build_bundle.py',
                  'validate_requirement_coverage.py'}
    observed_gate_names = set()
    expected_gate_arguments = {
        'validate_requirement_spec.py': [str(inputs['requirement']), '--request-packet',
            str(bound(receipt['formalBindings']['requestPacket'], receipt_path)), '--check-findings-files'],
        'validate_accepted_build_view.py': [str(inputs['acceptedBuildView']), '--requirement', str(inputs['requirement'])],
        'validate_build_bundle.py': [str(inputs['bundle']), '--requirement', str(inputs['requirement']),
            '--accepted-build-view', str(inputs['acceptedBuildView'])],
        'validate_requirement_coverage.py': [str(inputs['bundle']), '--requirement', str(inputs['requirement']),
            '--accepted-build-view', str(inputs['acceptedBuildView'])],
    }
    for row in formal:
        command = row['request'].get('command', [])
        require(len(command) >= 3 and command[1] == '-B' and row['response'].get('command') == command,
                'Formal gate command/response differ')
        script = Path(command[2]).resolve()
        require(script.parent == (PLUGIN/'skills/analyze-nextgame-ui-requirements/scripts').resolve()
                and script.name in gate_names and script.name not in observed_gate_names, 'Unexpected formal validator authority')
        require(command[3:] == expected_gate_arguments[script.name], 'Formal validator arguments do not name the exact bound sources')
        observed_gate_names.add(script.name)
    require(receipt['formalBindings']['requirement'] == receipt['inputs']['requirement']
            and receipt['formalBindings']['acceptedBuildView'] == receipt['inputs']['acceptedBuildView']
            and receipt['formalBindings']['bundle'] == receipt['inputs']['bundle'], 'Formal input bindings differ')
    for ref in receipt['formalBindings'].values():
        bound(ref, receipt_path)
    start, finish = aware_time(receipt['startedAt']), aware_time(receipt['completedAt'])
    require(start <= finish, 'Invalid continuation interval')
    for row in rows:
        require(start <= aware_time(row['startedAt']) <= aware_time(row['completedAt']) <= finish,
                'Journal call outside continuation interval')
    def one(sequence, label, provider, request=None, response=None):
        require(type(sequence) is int and 1 <= sequence <= len(rows), 'Invalid evidence sequence')
        row = rows[sequence-1]
        require(row['label'] == label and row['provider'] == provider, 'Wrong provider or semantic call')
        if request is not None:
            require(row['request'] == request, 'Call targets another object or arguments')
        if response is not None:
            require(row['response'] == response, 'Unsupported call result')
        return row
    one(receipt['recoveryGetWidgetsSequence'], existing.art.UMG+'.GetWidgets', 'official-unreal-mcp',
        {'widgetBlueprint': {'refPath': context['objectPath']}})
    one(receipt['compileSequence'], existing.art.UMG+'.CompileWidgetBlueprint', 'official-unreal-mcp',
        {'widgetBlueprint': {'refPath': context['objectPath']}}, True)
    one(receipt['saveSequence'], existing.art.ASSET+'.save_assets', 'official-unreal-mcp', {'asset_paths': [context['assetPath']]}, True)
    mode = one(receipt['postSaveModeSequence'], 'continuation-post-save-mode', 'nxue-agent')
    require(_mode_from_journal(mode, context['cdoPath']) == context['targetMode'], 'Wrong saved Designer enum')
    require(receipt['compileSequence'] < receipt['saveSequence'] < receipt['postSaveModeSequence'], 'Compile/save/read order mismatch')
    labels = {row['label']: row for row in rows if row['label'] in {'set-exact-designer-mode-fallback', 'designer-fallback-before',
              'designer-fallback-after', 'discover-exact-designer-fallback', 'discover-exact-designer-property'}}
    require(len(labels) == 5, 'Missing live protected-property protocol evidence')
    metadata = labels['discover-exact-designer-fallback']['response'].get('data', {})
    require(metadata.get('name') == 'manage-property' and metadata.get('requiresEditor') is True and metadata.get('writes') is True
            and {'list', 'get', 'set'} <= set(metadata.get('actions', [])) and set(metadata.get('writeActions', [])) == {'set'},
            'Unsupported live NxUE protected-property metadata')
    listing = labels['discover-exact-designer-property']['response'].get('data', {})
    target = listing.get('target', {})
    fields = [p for p in listing.get('properties', []) if p.get('name') == 'DesignSizeMode']
    require(target.get('path') == context['cdoPath'] and target.get('classPath') == context['objectPath']+'_C'
            and target.get('packageName') == context['assetPath'] and target.get('isAsset') is False
            and len(fields) == 1 and fields[0].get('type') == 'EnumProperty', 'Exact typed CDO identity is unproved')
    before = labels['designer-fallback-before']
    require(before['provider'] == 'nxue-agent' and before['request'].get('CDO') == context['cdoPath']
            and before['response'] == receipt['beforeMode'], 'Before enum CAS mismatch')
    require(labels['designer-fallback-after']['response'] == context['targetMode'], 'Immediate post-set enum mismatch')
    set_row = labels['set-exact-designer-mode-fallback']
    command = set_row['request'].get('command', [])
    require(set_row['provider'] == 'nxue-agent' and '--args-json' in command
            and json.loads(command[command.index('--args-json')+1]) == {'action': 'set', 'objectPath': context['cdoPath'],
            'propertyPath': 'DesignSizeMode', 'value': context['targetMode']}, 'Only the exact protected field may be written')
    require(before['sequence'] < set_row['sequence'] < labels['designer-fallback-after']['sequence'] < receipt['saveSequence'], 'Fallback CAS ordering mismatch')
    asset_file = inputs['projectFile'].parent/'Content'/(context['assetPath'][len('/Game/'):] + '.uasset')
    require(receipt['sourceAssetFile'] == str(asset_file), 'Physical asset CAS path differs from approved target')
    for phase, mutation_sequence in (('before-CompileWidgetBlueprint', receipt['compileSequence']),
                                     ('before-designer-set', set_row['sequence']), ('before-save_assets', receipt['saveSequence'])):
        cas_rows = [r for r in rows if r['label'] == 'asset-file-cas-'+phase]
        require(len(cas_rows) == 1, 'Missing precise pre-mutation physical CAS')
        cas = cas_rows[0]
        require(cas['provider'] == 'local-filesystem' and cas['request'] == {'path': str(asset_file),
                'expectedSha256': receipt['inputs']['beforeAsset']['sha256']}
                and cas['response'] == {'observedSha256': receipt['inputs']['beforeAsset']['sha256']}
                and cas['sequence'] == mutation_sequence-1, 'Saved-file CAS was not immediately before the exact mutation')
    for phase in phases:
        statuses = [r for r in rows if r['label'] == 'nxue-status-'+phase]
        owners = [r for r in rows if r['label'] == 'mcp-listener-'+phase]
        nxue_owners = [r for r in rows if r['label'] == 'nxue-listener-'+phase]
        require(len(statuses) == len(owners) == len(nxue_owners) == 1, 'Missing same-process identity proof')
        port = _status_port(statuses[0]['response'].get('data'), inputs['projectFile'].parent)
        owner = owners[0]
        nxue_owner = nxue_owners[0]
        require(statuses[0]['provider'] == 'nxue-agent' and owner['provider'] == 'local-os'
                and owner['request'] == {'url': receipt['mcpURL']} and owner['response']['url'] == receipt['mcpURL']
                and nxue_owner['provider'] == 'local-os' and nxue_owner['response']['port'] == port
                and nxue_owner['request'] == {'url': 'http://127.0.0.1:'+str(port)}
                and owner['response']['method'] == nxue_owner['response']['method'] == 'local-tcp-listener-owner'
                and owner['response']['port'] == urlparse(receipt['mcpURL']).port
                and owner['response']['pid'] == nxue_owner['response']['pid'] == receipt['editorPid'], 'MCP/NxUE process identity mismatch')
    # Official schema observations must really lack the field; no fallback after
    # a failed official write or on arbitrary absent properties is permitted.
    schema_rows = [r for r in rows if r['label'] == existing.art.OBJ+'.list_properties'
                   and r['request'] == {'instance': {'refPath': context['cdoPath']}}]
    require(schema_rows and all(r['provider'] == 'official-unreal-mcp' and isinstance(r['response'], dict)
            and 'designSizeMode' not in r['response'] for r in schema_rows), 'Missing official protected-field omission evidence')
    official_allowed = {
        existing.art.UMG+'.GetWidgets': {'widgetBlueprint': {'refPath': context['objectPath']}},
        existing.art.UMG+'.CompileWidgetBlueprint': {'widgetBlueprint': {'refPath': context['objectPath']}},
        existing.art.BP+'.get_default_object': {'blueprint': {'refPath': context['objectPath']}},
        existing.art.OBJ+'.list_properties': {'instance': {'refPath': context['cdoPath']}},
        existing.art.ASSET+'.save_assets': {'asset_paths': [context['assetPath']]},
        existing.art.ASSET+'.is_dirty': {'asset_path': context['assetPath']},
    }
    for row in rows:
        if row['label'] in official_allowed:
            require(row['provider'] == 'official-unreal-mcp' and row['request'] == official_allowed[row['label']],
                    'Unexpected official target or provider')
        if row['label'] == existing.art.ASSET+'.is_dirty':
            require(row['response'] is False, 'Clean-state observation missing')
    readonly = context['tail'][6:]
    require([r['stepId'] for r in receipt['tailReadbacks']] == [s['stepId'] for s in readonly], 'Original post-save read coverage changed')
    saved = copy.deepcopy(context['saved'])
    saved['savedBlueprintDefaultObject'] = {'returnValue': {'refPath': context['cdoPath']}}
    for step, recorded in zip(readonly, receipt['tailReadbacks']):
        arguments = resolve(step.get('arguments', {}), saved)
        require(recorded['arguments'] == arguments and recorded['sequence'] > receipt['postSaveModeSequence'], 'Readback target/order mismatch')
        row = one(recorded['sequence'], step['toolsetName']+'.'+step['toolName'], 'official-unreal-mcp', arguments)
        if step.get('saveResultAs'):
            saved[step['saveResultAs']] = {'returnValue': row['response']}
    final_tree_record = receipt['tailReadbacks'][0]
    require(final_tree_record['stepId'] == 'verify-tree' and
            _tree_identity(rows[receipt['recoveryGetWidgetsSequence']-1]['response']) ==
            _tree_identity(rows[final_tree_record['sequence']-1]['response']), 'Before/after actual WidgetTree identity differs')
    compile_check = {'tool': existing.art.UMG+'.CompileWidgetBlueprint', 'arguments': {'widgetBlueprint': {'refPath': context['objectPath']}},
                     'result': {'returnValue': True}, 'completedAt': rows[receipt['compileSequence']-1]['completedAt']}
    save_check = {'tool': existing.art.ASSET+'.save_assets', 'arguments': {'asset_paths': [context['assetPath']]},
                  'result': {'returnValue': True}, 'completedAt': rows[receipt['saveSequence']-1]['completedAt']}
    return {'valid': True, 'assetPath': context['assetPath'], 'startedAt': receipt['startedAt'], 'completedAt': receipt['completedAt'],
            'steps': {'compile': compile_check, 'save': save_check}, 'originalCheckpointStatus': 'unchanged-failed', 'visualVerified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--plan', type=Path, required=True)
    inspect.add_argument('--failed-checkpoint', type=Path, required=True)
    verify = commands.add_parser('validate')
    verify.add_argument('receipt', type=Path)
    verify.add_argument('--plan', type=Path, required=True)
    run = commands.add_parser('execute')
    for name in ('plan', 'failed-checkpoint', 'project', 'output', 'requirement', 'accepted-build-view', 'bundle'):
        run.add_argument('--'+name, type=Path, required=True)
    run.add_argument('--request-packet', type=Path)
    run.add_argument('--review-draft', type=Path)
    run.add_argument('--capability', choices=[CAPABILITY], required=True)
    run.add_argument('--asset-sha256', required=True)
    run.add_argument('--before-mode', choices=sorted(MODES), required=True)
    run.add_argument('--url', required=True)
    run.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            context = inspect_failed(args.plan, args.failed_checkpoint)
            result = {'valid': True, 'capability': CAPABILITY, 'assetPath': context['assetPath'],
                      'completedPrefix': context['prefix'], 'failedSuffixCount': len(context['checkpoint']['events'])-context['prefix'],
                      'expectedMode': context['targetMode'], 'originalCheckpointStatus': 'unchanged-failed',
                      'executionPerformed': False, 'runtimePreflight': 'not-performed'}
        elif args.command == 'validate':
            result = validate_receipt(args.receipt, args.plan)
        else:
            result = execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'valid': False, 'error': str(exc), 'executionAuthorization': 'not-awarded'}, ensure_ascii=False, indent=2))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
