#!/usr/bin/env python3
"""Shared contracts and deterministic guards for the optional art phase.

This module never connects to Unreal, calls a model, or accepts a UI result.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
import struct
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]
SCHEMA = SKILL_ROOT / 'assets' / 'art-contract.schema.json'
ART_GOALS = ('formal-art', 'upgrade-art', 'local-art')
WIDGET_PROPERTIES = frozenset(('brush', 'colorAndOpacity', 'renderOpacity', 'font', 'shadowOffset',
    'shadowColorAndOpacity', 'justification', 'wrapTextAt', 'visibility', 'renderTransform',
    'renderTransformPivot', 'clipping'))
SLOT_PROPERTIES = frozenset(('layoutData', 'bAutoSize', 'zOrder', 'padding', 'horizontalAlignment',
    'verticalAlignment', 'size'))
KINDS = ('set-property', 'set-slot', 'add-widget', 'remove-widget', 'reparent-widget', 'import-resource')
STATIC_CLASSES = frozenset(('/Script/UIFramework.GameImage', '/Script/UMG.CanvasPanel',
    '/Script/UMG.Overlay', '/Script/UMG.HorizontalBox', '/Script/UMG.VerticalBox'))


class ArtError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def aware_time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ArtError('time.timezone', 'Evidence timestamps must include a timezone.')
    return parsed


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    def invalid(value):
        raise ArtError('json.nonfinite', f'Non-finite JSON value: {value}')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid)


def write_json(path, value, *, replace=False):
    path = Path(path).resolve()
    if path.is_relative_to(PLUGIN_ROOT):
        raise ArtError('output.plugin', 'Runtime evidence must be outside the plugin package.')
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if path.exists():
        if path.read_text(encoding='utf-8') == data:
            return
        if not replace:
            raise ArtError('output.immutable', f'Choose a new revision; refusing to overwrite {path.name}.')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def binding(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha256(path)}


def bound_path(record, owner):
    if not isinstance(record, dict) or set(record) != {'path', 'sha256'}:
        raise ArtError('binding.shape', 'Expected a closed path/SHA-256 binding.')
    path = Path(record['path'])
    if not path.is_absolute():
        path = Path(owner).resolve().parent / path
    path = path.resolve()
    if not path.is_file() or sha256(path) != record['sha256']:
        raise ArtError('binding.stale', f'Missing or changed bound file: {path.name}.')
    return path


def read_bound(record, owner):
    return load_json(bound_path(record, owner))


def validate(value, definition):
    schema = load_json(SCHEMA)
    validator = Draft202012Validator({'$schema': schema['$schema'], '$ref': '#/$defs/' + definition,
                                     '$defs': schema['$defs']})
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        raise ArtError('schema.' + definition, f'{list(error.path)}: {error.message}')
    canonical(value)
    return value


def state(snapshot):
    """Stable actual-state projection; capture times/transient refs are not state."""
    validate(snapshot, 'snapshot')
    def native_numbers(value):
        if isinstance(value,float):
            converted=struct.unpack('f',struct.pack('f',value))[0]
            return int(converted) if converted.is_integer() else converted
        if isinstance(value,dict): return {k:native_numbers(v) for k,v in value.items()}
        if isinstance(value,list): return [native_numbers(v) for v in value]
        return value
    result = native_numbers(copy.deepcopy(snapshot['assets']))
    for asset in result:
        asset['widgets'].sort(key=lambda item: item['widgetName'])
        asset['protectedReferences'].sort()
    result.sort(key=lambda item: item['assetPath'])
    return result


def state_hash(snapshot):
    return digest(state(snapshot))


def index_snapshot(snapshot):
    state(snapshot)
    assets, widgets = {}, {}
    for asset in snapshot['assets']:
        path = asset['assetPath']
        if path in assets:
            raise ArtError('snapshot.duplicate_asset', path)
        assets[path] = asset
        names = [w['widgetName'] for w in asset['widgets']]
        if len(names) != len(set(names)):
            raise ArtError('snapshot.duplicate_widget', path)
        if not set(asset['protectedReferences']) <= set(names):
            raise ArtError('snapshot.reference', 'Protected reference names must resolve.')
        for widget in asset['widgets']:
            widgets[(path, widget['widgetName'])] = widget
        for widget in asset['widgets']:
            visited = set()
            current = widget
            while current['parentWidgetName'] is not None:
                parent = current['parentWidgetName']
                if parent in visited or (path, parent) not in widgets:
                    raise ArtError('snapshot.hierarchy', 'Missing parent or WidgetTree cycle.')
                visited.add(parent)
                current = widgets[(path, parent)]
    return assets, widgets


def validate_preview_contract(request, request_path):
    """Validate identity, regions and mandatory screen viewport coverage."""
    from PIL import Image
    from art_reference import source_size, validate_regions, CAPABILITY
    if 'resourceCatalog' in request:
        from art_resources import validate_catalog
        validate_catalog(bound_path(request['resourceCatalog'],request_path))
    source=request.get('target',request['baseline'])
    bundle=read_bound(source['bundle'],request_path)
    assets={a['assetPath']:a for a in bundle['assets']}
    scope={s['assetPath'] for s in request['scope']}
    if len(scope)!=len(request['scope']):
        raise ArtError('preview.scope','Each asset may occur only once in the requested scope.')
    identities=set()
    by_asset={}
    for reference in request['references']:
        if reference['id'] in identities or reference['assetPath'] not in scope:
            raise ArtError('preview.identity','References must have unique IDs and belong to the requested assets.')
        identities.add(reference['id'])
        size=reference['context']['size']
        native_size=source_size(request, reference)
        with Image.open(bound_path(reference['image'],request_path)) as image:
            if list(image.size)!=native_size:
                raise ArtError('preview.reference_size','Reference pixels must match their declared coordinate system.')
        region_ids=set()
        for region in reference['regions']:
            x,y,w,h=region['bounds']
            if region['id'] in region_ids or min(x,y)<0 or min(w,h)<=0 or x+w>native_size[0] or y+h>native_size[1]:
                raise ArtError('preview.region','Regions must be unique, positive, and inside the image.')
            region_ids.add(region['id'])
        if CAPABILITY in request.get('capabilities', []):
            validate_regions(reference)
        by_asset.setdefault(reference['assetPath'],[]).append(size)
    if set(by_asset)!=scope:
        raise ArtError('preview.scope','Every scoped asset needs visual reference coverage.')
    for path,sizes in by_asset.items():
        if path not in assets:
            raise ArtError('preview.asset','Reference asset is absent from the target Bundle.')
        if assets[path]['assetKind']=='screen':
            if [2560,1440] not in sizes or not any(w>2560 and h==1440 for w,h in sizes) or not any(h>1440 and w==2560 for w,h in sizes):
                raise ArtError('preview.viewports','Screen art needs 2560x1440 and explicit wider and taller reference checks.')


def check_operation(operation):
    validate(operation, 'operation')
    kind = operation['kind']
    if kind in ('set-property', 'set-slot'):
        allowed = WIDGET_PROPERTIES if kind == 'set-property' else SLOT_PROPERTIES
        if operation.get('property') not in allowed:
            raise ArtError('operation.property', 'Only declared art properties can be changed.')
        value = operation['after']
        if operation['property'] == 'visibility' and value not in ('SelfHitTestInvisible', 'Collapsed', 'Hidden'):
            raise ArtError('operation.hit_test', 'Art operations cannot take ownership of input.')
        if operation['property'] == 'font' and isinstance(value, dict) and 'size' in value:
            size = value['size']
            if not isinstance(size, int) or isinstance(size, bool) or size <= 0 or size % 2:
                raise ArtError('operation.font', 'Font size must be a positive even integer.')
        if operation['property'] == 'wrapTextAt' and (not isinstance(value, (int, float)) or value <= 0):
            raise ArtError('operation.wrap', 'Wrap width must be positive.')
    elif kind == 'add-widget':
        node = operation['after']
        validate(node, 'widget')
        if node['widgetName'] != operation['widgetName'] or node['isVariable'] or node['classPath'] not in STATIC_CLASSES:
            raise ArtError('operation.static_only', 'New art nodes must be supported static visual nodes.')
        if node['classPath'].endswith('.GameImage') and not node['widgetName'].startswith('Img'):
            raise ArtError('operation.naming', 'GameImage names must start with Img.')
        if node['properties'].get('visibility') != 'SelfHitTestInvisible':
            raise ArtError('operation.visibility', 'New static art must be SelfHitTestInvisible.')
        if set(node['properties']) - WIDGET_PROPERTIES or set(node['slot']['properties']) - SLOT_PROPERTIES:
            raise ArtError('operation.property', 'New node contains unsupported art properties.')
    elif kind == 'import-resource':
        value = operation['after']
        if not isinstance(value, dict) or set(value) != {'sourcePath', 'sha256', 'destinationPath'}:
            raise ArtError('operation.import', 'Import requires exact source hash and destination.')
        source = Path(value['sourcePath'])
        if not source.is_absolute() or not source.is_file() or sha256(source) != value['sha256']:
            raise ArtError('operation.source', 'Import source is missing or changed.')
        if not value['destinationPath'].startswith('/Game/UI/') or '..' in value['destinationPath']:
            raise ArtError('operation.destination', 'Import target must be under /Game/UI/.')


def advance_snapshot(snapshot, operation, *, check_before=True):
    """Simulate permitted changes for diff planning; never label this actual readback."""
    check_operation(operation)
    expected = copy.deepcopy(snapshot)
    assets, nodes = index_snapshot(expected)
    key = (operation['assetPath'], operation['widgetName'])
    if key[0] not in assets:
        raise ArtError('operation.asset', 'Operation targets an asset outside the baseline.')
    asset = assets[key[0]]
    kind = operation['kind']
    node = nodes.get(key)
    if kind == 'import-resource':
        return expected
    if kind in ('set-property', 'set-slot'):
        if node is None:
            raise ArtError('operation.widget', 'Target widget does not exist.')
        props = node['properties'] if kind == 'set-property' else node['slot']['properties']
        prop = operation['property']
        if prop not in props:
            raise ArtError('operation.unobserved_property', 'Property was not captured from Unreal.')
        if check_before and props[prop] != operation['before']:
            raise ArtError('operation.stale', 'Expected property value differs from actual baseline.')
        props[prop] = copy.deepcopy(operation['after'])
    else:
        if kind != 'add-widget' and not asset['referencesComplete']:
            raise ArtError('operation.references_incomplete', 'Structural changes require complete reference evidence.')
        protected = set(asset['protectedReferences']) | {w['widgetName'] for w in asset['widgets'] if w['isVariable']}
        if kind == 'add-widget':
            if node is not None:
                raise ArtError('operation.duplicate', 'New widget already exists.')
            asset['widgets'].append(copy.deepcopy(operation['after']))
        else:
            if node is None or key[1] in protected:
                raise ArtError('operation.protected', 'Cannot remove or reparent a missing or protected widget.')
            if kind == 'remove-widget':
                if any(w['parentWidgetName'] == key[1] for w in asset['widgets']):
                    raise ArtError('operation.children', 'Remove explicitly approved leaf decorations in child-first order.')
                if check_before and node != operation['before']:
                    raise ArtError('operation.stale', 'Node differs from approved removal baseline.')
                asset['widgets'].remove(node)
            elif kind == 'reparent-widget':
                descendants = {key[1]}
                while True:
                    expanded = descendants | {w['widgetName'] for w in asset['widgets'] if w['parentWidgetName'] in descendants}
                    if expanded == descendants:
                        break
                    descendants = expanded
                if descendants & protected:
                    raise ArtError('operation.protected_subtree', 'Cannot move an ancestor of a protected widget.')
                if check_before and node['parentWidgetName'] != operation['before']:
                    raise ArtError('operation.stale', 'Parent differs from actual baseline.')
                node['parentWidgetName'] = operation['after']
    index_snapshot(expected)
    return expected


def run_validator(script, arguments):
    completed = subprocess.run([sys.executable, str(script), *map(str, arguments)],
                               capture_output=True, text=True, encoding='utf-8', timeout=180)
    try:
        report = json.loads(completed.stdout)
    except (ValueError, TypeError):
        raise ArtError('authority.validator', f'{Path(script).name} did not produce valid JSON.')
    if completed.returncode or not report.get('valid'):
        details = report.get('errors', [])[:3]
        raise ArtError('authority.invalid', f'{Path(script).name}: {details}')


def validate_authority(request, request_path):
    """Always revalidate full canonical sources, rather than trusting compact packets."""
    baseline = request['baseline']
    paths = {name: bound_path(value, request_path) for name, value in baseline.items()}
    docs = PLUGIN_ROOT / 'skills' / 'document-nextgame-umg' / 'scripts'
    if 'development-baseline/1' in request.get('capabilities', []):
        from art_baseline import validate_development_baseline
        validate_development_baseline(request, request_path, paths)
    else:
        run_validator(docs / 'validate_unreal_widget_readback.py', [paths['readback'], '--requirement',
                      paths['requirement'], '--bundle', paths['bundle']])
    target = request.get('target', {})
    if target:
        target_paths = {name: bound_path(value, request_path) for name, value in target.items()}
        analysis = PLUGIN_ROOT / 'skills' / 'analyze-nextgame-ui-requirements' / 'scripts'
        run_validator(analysis / 'validate_build_bundle.py', [target_paths['bundle'], '--requirement', target_paths['requirement']])
    return paths


def validate_art_stage(stage, *, bundle_path, requirement, requirement_path, readback=None, final_bundle=None):
    """Bundle/document gate. No recursive Bundle validation and no model judgments."""
    errors = []
    try:
        scripts = str(SKILL_ROOT / 'scripts')
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        validate(stage, 'stage')
        request_path = bound_path(stage['request'], bundle_path)
        plan_path = bound_path(stage['plan'], bundle_path)
        verification_path = bound_path(stage['verification'], bundle_path)
        request = validate(load_json(request_path), 'request')
        validate_preview_contract(request,request_path)
        plan = validate(load_json(plan_path), 'plan')
        verification = validate(load_json(verification_path), 'verification')
        if 'development-baseline/1' in request.get('capabilities', []):
            from art_baseline import validate_baseline_closure
            validate_baseline_closure(request, request_path, final_bundle)
        from art_pipeline import _validated_plan
        _validated_plan(plan_path, validate_sources=False)
        if stage['goal'] != request['goal'] or plan['request']['sha256'] != sha256(request_path):
            raise ArtError('art.binding', 'Art stage does not bind the current request and plan.')
        if verification['plan']['sha256'] != sha256(plan_path) or verification['status'] != 'passed':
            raise ArtError('art.incomplete', 'Art verification is incomplete or refers to a different plan.')
        target_requirement = request.get('target', request['baseline'])['requirement']
        if target_requirement['sha256'] != sha256(requirement_path) or request['requestId'] != requirement.get('requestId'):
            raise ArtError('art.requirement', 'Art request does not bind the current accepted Requirement.')
        # Check every source, approval, comparison image and actual-state receipt.
        for source in request['baseline'].values():
            bound_path(source, request_path)
        for source in request.get('target', {}).values():
            bound_path(source, request_path)
        for source in request.get('samples',[]):
            sample_path=bound_path(source,request_path)
            sample=load_json(sample_path)
            for key in ('reference','readback'): bound_path(sample[key],sample_path)
            for resource in sample.get('resources',[]): bound_path({k:resource[k] for k in ('path','sha256')},sample_path)
        for reference in request['references']:
            bound_path(reference['image'], request_path)
        bound_path(plan['decisions'], plan_path)
        snapshot_path = bound_path(verification['snapshot'], verification_path)
        snapshot = validate(load_json(snapshot_path), 'snapshot')
        if any(a['designSizeMode'] is None for a in snapshot['assets']):
            raise ArtError('art.design_mode', 'Unknown actual Designer mode cannot pass production verification.')
        if state_hash(snapshot) != plan['expectedStateSha256']:
            raise ArtError('art.actual_state', 'Actual art readback does not match the approved operation result.')
        from art_presentation import validate_presentation
        decisions_path = bound_path(plan['decisions'], plan_path)
        presentation = validate_presentation(request, load_json(decisions_path), snapshot, request_path, decisions_path, phase='actual')
        if 'presentation-review/1' in request.get('capabilities', []):
            presentation_ids = {c['id'] for c in presentation['checks']}
            expected_ids = presentation_ids | {'capture:' + r['id'] for r in request['references']}
            recorded_ids = [c['id'] for c in verification['checks']]
            recorded_presentation = [c for c in verification['checks'] if c['id'] in presentation_ids]
            if (len(recorded_ids) != len(set(recorded_ids)) or set(recorded_ids) != expected_ids
                    or recorded_presentation != presentation['checks']):
                raise ArtError('art.presentation_checks', 'Checks must exactly cover deterministic presentation and capture IDs, with recomputed presentation values.')
        if presentation['issues'] or any(c['status'] != 'passed' for c in presentation['checks']):
            raise ArtError('art.presentation_pending', 'Unresolved presentation judgments or unavailable actual geometry cannot pass formal art.')
        if snapshot['acquisition']['method'] == 'fixture':
            raise ArtError('art.fixture', 'Fixture readback cannot satisfy a production art gate.')
        execution_path = bound_path(verification['execution'], verification_path)
        execution = validate(load_json(execution_path), 'execution')
        if execution.get('status') != 'completed' or execution.get('planSha256') != sha256(plan_path):
            raise ArtError('art.execution', 'Missing current completed execution receipt.')
        if execution['completedIds'] != [o['id'] for o in plan['operations']] or execution['currentOperation'] is not None or execution['expectedStateSha256'] != plan['expectedStateSha256']:
            raise ArtError('art.execution_prefix', 'Execution must prove every operation and the final state.')
        if bound_path(execution['readback'], execution_path) != snapshot_path:
            raise ArtError('art.execution_readback', 'Verification must use the exact completed execution readback.')
        review = read_bound(verification['visualReview'], verification_path)
        validate(review, 'visualReview')
        if review['status'] != 'passed' or review['snapshotSha256'] != sha256(snapshot_path) or review['unresolved']:
            raise ArtError('art.visual_review', 'Visual review is missing or stale.')
        reviewer = review['reviewer']
        if (reviewer['actorType'], reviewer['confirmationSource']) not in {
            ('user', 'direct-user-message'), ('agent', 'visual-inspection')}:
            raise ArtError('art.visual_review', 'Declare the actual visual reviewer; this is not post-build user acceptance.')
        expected_comparisons = {digest(c) for c in verification['comparisons']}
        if {digest(c) for c in review['comparisons']} != expected_comparisons:
            raise ArtError('art.visual_review', 'Reviewed comparisons do not exactly cover the verification result.')
        for comparison in verification['comparisons']:
            comparison_path=bound_path(comparison,verification_path)
            evidence = load_json(comparison_path)
            from art_reference import CAPABILITY, source_size, validate_mapped
            mapped = CAPABILITY in request.get('capabilities', [])
            if not mapped and evidence.get('dimensionAgreement') is not True:
                raise ArtError('art.preview_size', 'Comparison sizes must agree.')
            for field in (('reference', 'actual', 'fullView') if mapped else ('reference', 'actual', 'overlay', 'diff')):
                record = evidence.get(field, {})
                bound_path({k: record[k] for k in ('path', 'sha256')}, comparison_path)
            capture_path = bound_path(evidence['capture'], comparison_path)
            capture = validate(load_json(capture_path), 'capture')
            reference = next((r for r in request['references'] if r['id'] == evidence.get('referenceId')), None)
            if reference is None or capture['assetPath'] != reference['assetPath'] or capture.get('context') != reference['context'] or capture.get('canonical') is not True:
                raise ArtError('art.capture', 'Preview must prove the declared size, DPI, data, font and state context.')
            compared_reference=bound_path({k:evidence['reference'][k] for k in ('path','sha256')},comparison_path)
            compared_actual=bound_path({k:evidence['actual'][k] for k in ('path','sha256')},comparison_path)
            if compared_reference!=bound_path(reference['image'],request_path) or compared_actual!=bound_path(capture['image'],capture_path):
                raise ArtError('art.comparison_identity','Comparison must use the exact requested artwork and captured image.')
            from art_images import validate_comparison
            if mapped:
                validate_mapped(evidence, reference, comparison_path)
            else:
                validate_comparison(evidence,reference['regions'],comparison_path)
            if capture.get('snapshotSha256') != sha256(snapshot_path) or capture.get('image', {}).get('sha256') != evidence['actual']['sha256']:
                raise ArtError('art.capture', 'Capture is not bound to the final art state and compared image.')
            from PIL import Image
            for source, owner, expected_size in ((reference['image'], request_path, source_size(request, reference)), (capture['image'], capture_path, reference['context']['size'])):
                with Image.open(bound_path(source, owner)) as image:
                    if list(image.size) != expected_size:
                        raise ArtError('art.capture_size', 'Decoded pixels must match the declared preview dimensions.')
            if not (aware_time(snapshot['capturedAt']) <= aware_time(capture['capturedAt']) <= aware_time(review['reviewedAt']) <= aware_time(verification['verifiedAt'])):
                raise ArtError('art.time', 'Capture, inspection and verification must follow actual final readback.')
        if {read_bound(c, verification_path).get('referenceId') for c in verification['comparisons']} != {r['id'] for r in request['references']}:
            raise ArtError('art.preview_coverage', 'Every required state/viewport reference must be compared.')
        expected_regions = {r['id'] + ':' + region['id'] for r in request['references'] for region in r['regions']}
        if set(review['inspectedRegions']) != expected_regions:
            raise ArtError('art.region_coverage', 'Visual inspection must cover every required region.')
        if not verification['checks'] or any(c['status'] != 'passed' for c in verification['checks']):
            raise ArtError('art.checks', 'Every art check must pass.')
        if readback is not None:
            if aware_time(readback['capturedAt']) < aware_time(verification['verifiedAt']):
                raise ArtError('art.readback_time','Final normalized readback must follow art verification.')
            art_assets, _ = index_snapshot(snapshot)
            actual_assets = {a['assetPath']: a for a in readback.get('assets', [])}
            if set(art_assets) != set(actual_assets):
                raise ArtError('art.readback_coverage', 'Art and document readbacks must cover the same assets.')
            for path, art_asset in art_assets.items():
                actual = actual_assets[path]
                if actual.get('designSizeMode') != art_asset['designSizeMode']:
                    raise ArtError('art.readback_mode', 'Designer mode changed after art verification.')
                if actual.get('parentClassPath') != art_asset['parentClassPath']:
                    raise ArtError('art.readback_parent','Blueprint parent class changed after art verification.')
                basic = lambda w: (w['widgetName'], w['classPath'], w['parentWidgetName'], w['isVariable'])
                if {basic(w) for w in art_asset['widgets']} != {basic(w) for w in actual.get('widgets', [])}:
                    raise ArtError('art.readback_tree', 'WidgetTree changed after art verification.')
                observed = {w['widgetName']: w for w in actual.get('widgets', [])}
                for widget in art_asset['widgets']:
                    for key in ('entryWidgetClass', 'visibility'):
                        if key in observed[widget['widgetName']] and observed[widget['widgetName']][key] != widget['properties'].get(key):
                            raise ArtError('art.readback_property', f'{key} changed after art verification.')
    except (ArtError, OSError, ValueError, KeyError, TypeError) as exc:
        errors.append({'code': getattr(exc, 'code', 'art.invalid'), 'path': '$.artStage', 'message': str(exc)})
    return errors
