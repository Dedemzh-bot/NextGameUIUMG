"""Read-only adoption of existing completed Art lineage and real Retainer evidence.

No request rewrite, apply replay, Editor call, synthetic geometry or acceptance.
The narrow provider interpretation uses real retained production native paint,
official runtime/full-state getter results and exact byte-domain Retainer PNGs.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import math
import json
from pathlib import Path
import struct
from urllib.parse import urlparse

from art_common import (ArtError, aware_time, binding, bound_path, load_json,
                        canonical, read_bound, sha256, state_hash, validate, write_json)

CAPABILITY = 'measured-presentation-geometry/1'
PRODUCER = 'euw-retainer-nativevm/1'
PROVIDER_STATUS = 'retainer-nativevm-production-contract/1'
EPSILON = 0.001


def require(ok, message):
    if not ok:
        raise ArtError('geometry.evidence', message)


def _ref(value):
    return value.get('refPath') if isinstance(value, dict) else value


def _close(a, b):
    return abs(a - b) <= EPSILON


def _numbers(value, count):
    require(isinstance(value, list) and len(value) == count
            and all(type(x) in (int, float) and math.isfinite(x) for x in value), 'Expected finite native coordinates.')
    return value


def _same(actual, expected, message):
    require(len(actual) == len(expected) and all(_close(a, b) for a, b in zip(actual, expected)), message)


def _bindings(records, owner):
    paths = [bound_path(record, owner) for record in records]
    require(len(paths) == len(set(paths)), 'Duplicate helper/source bindings are forbidden.')
    return paths


def configuration(adoption_path, plan_path, execution_path):
    """Re-read exact original lineage; never add capability/config to its request."""
    from art_pipeline import _validated_plan
    adoption_path = Path(adoption_path).resolve(strict=True)
    adoption = validate(load_json(adoption_path), 'measuredGeometryAdoption')
    plan_path, execution_path = Path(plan_path).resolve(strict=True), Path(execution_path).resolve(strict=True)
    require(bound_path(adoption['plan'], adoption_path) == plan_path
            and bound_path(adoption['execution'], adoption_path) == execution_path, 'Adoption plan/execution identity differs.')
    plan, request, request_path = _validated_plan(plan_path)
    decisions_path = bound_path(plan['decisions'], plan_path)
    require(bound_path(adoption['request'], adoption_path) == request_path
            and bound_path(adoption['decisions'], adoption_path) == decisions_path, 'Adoption request/decisions differ from original plan.')
    execution = validate(load_json(execution_path), 'execution')
    require(execution['status'] == 'completed' and execution['planSha256'] == sha256(plan_path)
            and execution['completedIds'] == [o['id'] for o in plan['operations']]
            and execution['currentOperation'] is None
            and execution['expectedStateSha256'] == plan['expectedStateSha256'], 'Require the exact real completed execution and every original operation.')
    snapshot_path = bound_path(execution['readback'], execution_path)
    require(bound_path(adoption['finalSnapshot'], adoption_path) == snapshot_path, 'Adoption must bind the exact completed execution readback.')
    snapshot = validate(load_json(snapshot_path), 'snapshot')
    require(state_hash(snapshot) == plan['expectedStateSha256'] and snapshot['acquisition']['method'] != 'fixture', 'Final actual state does not match original expected state.')
    created = aware_time(adoption['createdAt'])
    require(aware_time(execution['updatedAt']) <= created and aware_time(snapshot['capturedAt']) <= created,
            'Adoption must follow the actual completed apply and final saved readback.')
    config = adoption['configuration']
    require({'presentation-review/1', 'preserve-hierarchy/1', 'mapped-source-reference/1'} <= set(request.get('capabilities', [])), 'Original authority lacks required presentation/source protections.')
    require(request['goal'] == 'formal-art' and 'target' not in request
            and len(request['scope']) == len(request['references']) == 1, 'Only one original formal static pilot/reference is supported.')
    reference = request['references'][0]
    require(config['referenceId'] == reference['id'] and reference['assetPath'] == request['scope'][0]['assetPath']
            and reference['context']['dpiScale'] == 1 and len(reference['regions']) == 1, 'Adoption cannot replace the original exact reference/context.')
    require([case['scale'] for case in config['cases']] == [1, 0.75]
            and len({case['id'] for case in config['cases']}) == 2, 'Only original and whole-instance 0.75 cases are supported.')
    project = Path(config['projectRoot']).resolve(strict=True)
    require(project.is_dir() and len(list(project.glob('*.uproject'))) == 1, 'Bind the actual explicit project root.')
    collector = bound_path(adoption['collector'], adoption_path)
    require(collector.suffix == '.py' and collector.is_relative_to(project / 'Saved'), 'Bind frozen task-local collector source.')
    helpers = _bindings(adoption['helpers'], adoption_path)
    require(collector not in helpers, 'Collector must not be repeated as its own helper.')
    host_path = bound_path(adoption['hostEvidence'], adoption_path)
    host = validate(load_json(host_path), 'retainerHostEvidence')
    require(aware_time(host['observedAt']) <= created
            and host['processName'] in {'UnrealEditor.exe', 'UnrealEditor-Cmd.exe'}
            and len({row['LocalPort'] for row in host['endpoints']}) == 2
            and all(row['OwningProcess'] == host['expectedPid'] and row['LocalAddress'] == '127.0.0.1' for row in host['endpoints']),
            'Frozen actual OS host/endpoints do not establish one Editor process.')
    identities = [(path, load_json(path)) for path in helpers if path.suffix.lower() == '.json']
    identities = [(path, document) for path, document in identities
                  if isinstance(document, dict) and document.get('kind') == 'nextgame-ui-retainer-nativevm-helper-identity']
    require(len(identities) == 1, 'Freeze exactly one actual native helper identity/topology.')
    helper_path, helper = identities[0]
    validate(helper, 'retainerHelperIdentity')
    topology_path = bound_path(helper['topology'], helper_path)
    require(topology_path in helpers and helper['processId'] == host['expectedPid']
            and Path(helper['projectRoot']).resolve(strict=True) == project
            and aware_time(helper['observedAt']) <= created
            and helper['graphRef'] == helper['blueprint'] + ':' + helper['function'], 'Frozen helper graph/source/host identity differs.')
    topology = _value(load_json(topology_path))
    require(isinstance(topology, list) and len(topology) == 11, 'Require the exact complete reviewed 11-node native helper topology.')
    font_path = bound_path(adoption['fontEvidence'], adoption_path)
    font = load_json(font_path)
    require(font.get('kind') == 'nextgame-ui-saved-font-readback' and font.get('version') == '1'
            and font.get('status') == 'readback-dependency-matched' and font.get('readOnly') is True
            and font.get('assetsSavedByThisScript') == [] and font.get('fontToFaceDependencyObserved') is True
            and font.get('faceToFontReferencerObserved') is True, 'Require actual saved Font/Face dependency readback.')
    require(font['font']['class'] == '/Script/Engine.Font' and font['face']['class'] == '/Script/Engine.FontFace', 'Wrong native font receiver.')
    source = bound_path(font['source'], font_path)
    require(source.suffix.lower() == '.ttf' and len(font['savedFiles']) == 2
            and reference['context']['fontSetDigest'] == sha256(source), 'Bind complete static font source/packages.')
    packages = set()
    for record in font['savedFiles']:
        package = bound_path({key: record[key] for key in ('path', 'sha256')}, font_path)
        require(package.stat().st_size == record['bytes'], 'Saved font package size changed.')
        packages.add(package)
    expected = {(project / 'Content' / (p.split('.')[0][len('/Game/'):] + '.uasset')).resolve(strict=True)
                for p in (font['font']['path'], font['face']['path'])}
    require(packages == expected and source == Path(font['face']['sourceFilename']).resolve(strict=True)
            and font['font']['path'].split('.')[0] in font['faceReferencers']
            and font['face']['path'].split('.')[0] in font['fontDependencies'], 'Font source/project/dependency identity changed.')
    bundle = read_bound(request['baseline']['bundle'], request_path)
    require(len(bundle['assets']) == 1 and bundle['assets'][0]['assetPath'] == reference['assetPath']
            and bundle['assets'][0]['referenceSize'] == config['designContentSize'], 'Adoption design basis differs from accepted Bundle.')
    decisions = load_json(decisions_path)
    _source_expectations(request, request_path, snapshot, decisions, config)
    return {'adoption': adoption, 'adoptionPath': adoption_path, 'created': created, 'config': config,
            'project': project, 'plan': plan, 'request': request, 'requestPath': request_path,
            'execution': execution, 'executionPath': execution_path, 'snapshot': snapshot,
            'snapshotPath': snapshot_path, 'decisions': decisions, 'font': font, 'fontPath': font_path,
            'collector': collector, 'helpers': helpers, 'reference': reference, 'host': host, 'hostPath': host_path,
            'helper': helper, 'helperPath': helper_path}


def _rectangle(geometry):
    require(isinstance(geometry, dict), 'Missing actual cached/paint geometry.')
    local = _numbers(geometry.get('localSize'), 2)
    absolute = _numbers(geometry.get('absoluteSize'), 2)
    corners = geometry.get('transformedCorners')
    require(min(local + absolute) > 0 and isinstance(corners, list) and len(corners) == 4,
            'Nonpositive/absent actual Widget dimensions cannot pass.')
    p0, p1, p2, p3 = [_numbers(p, 2) for p in corners]
    width, height = p1[0] - p0[0], p3[1] - p0[1]
    require(width > 0 and height > 0, 'Mirrored, zero or reversed geometry is unsupported.')
    _same(p1, [p0[0] + width, p0[1]], 'Rotated/sheared geometry is outside this receiver.')
    _same(p3, [p0[0], p0[1] + height], 'Rotated/sheared geometry is outside this receiver.')
    _same(p2, [p0[0] + width, p0[1] + height], 'Inconsistent actual quadrilateral.')
    _same(absolute, [width, height], 'Native absolute dimensions disagree with actual corners.')
    return [p0[0], p0[1], width, height]


def _visible(value):
    # Exact known native enum spellings; no substring acceptance of arbitrary data.
    mapping = {'Visible': 'Visible', 'SelfHitTestInvisible': 'SelfHitTestInvisible', 'HitTestInvisible': 'HitTestInvisible',
        '<SlateVisibility.VISIBLE: 0>': 'Visible', '<SlateVisibility.HIT_TEST_INVISIBLE: 3>': 'HitTestInvisible',
        '<SlateVisibility.SELF_HIT_TEST_INVISIBLE: 4>': 'SelfHitTestInvisible'}
    require(value in mapping, 'Invisible/unknown native visibility is unsupported by this static receiver.')
    return mapping[value]


def _source_expectations(request, request_path, snapshot, decisions, config):
    require(decisions['presentationReview']['families'] == [], 'Measured family geometry is not supported by this opt-in.')
    asset = snapshot['assets'][0]
    require(len(snapshot['assets']) == 1 and asset['assetPath'] == request['scope'][0]['assetPath']
            and asset['parentClassPath'] == '/Script/UMG.UserWidget' and len(asset['widgets']) == 4,
            'Only the actual four-node native static pilot is supported.')
    rows = {w['widgetName']: w for w in asset['widgets']}
    require(len(rows) == 4, 'Duplicate actual Widget identity.')
    root = rows.get(config['contentRootWidgetName'])
    require(root is not None and root['classPath'] == '/Script/UMG.CanvasPanel' and root['parentWidgetName'] is None,
            'The named design-content root must be the actual native Canvas root.')
    images = {w['widgetName']: w for w in rows.values() if w['classPath'] == '/Script/UIFramework.GameImage'}
    texts = {w['widgetName']: w for w in rows.values() if w['classPath'] == '/Script/UMG.TextBlock'}
    require(len(images) == 2 and len(texts) == 1 and all(w['parentWidgetName'] == root['widgetName'] for w in list(images.values()) + list(texts.values())),
            'Only two direct GameImages and one direct native TextBlock are supported.')
    baseline = read_bound(request['baseline']['snapshot'], request_path)
    basic = lambda s: {(w['widgetName'], w['classPath'], w['parentWidgetName'], w['isVariable']) for w in s['assets'][0]['widgets']}
    require(basic(snapshot) == basic(baseline), 'The static native identity/tree/variables changed.')
    requirement = read_bound(request['baseline']['requirement'], request_path)
    normalized = read_bound(request['baseline']['readback'], request_path)
    bundle = read_bound(request['baseline']['bundle'], request_path)
    correspond = {m['nodeMappingId']: m['widgetName'] for a in normalized['assets'] for m in a['nodeMappings']}
    elements = {e['id']: e for e in requirement['uiModel']['elements']}
    width, height = config['designContentSize']
    expected = {root['widgetName']: [0, 0, width, height]}
    image_reviews = {i['widgetName']: i for i in decisions['presentationReview']['images']}
    for mapping in bundle['nodeMappings']:
        name = correspond.get(mapping['id'])
        if name == root['widgetName']:
            continue
        source = [elements[r] for r in mapping['requirementRefs'] if r in elements]
        require(len(source) == 1 and name in rows, 'Each native pilot receiver needs one accepted source element.')
        element = source[0]
        x, y, w, h = element['bounds']
        rectangle = [x * width, y * height, w * width, h * height]
        if name in images:
            review = image_reviews[name]
            require(review['aspectMode'] == 'preserve' and review['source']['kind'] == 'resource'
                    and review['familyId'] is None, 'Only complete-frame preserved standalone images are supported.')
            brush = rows[name]['properties'].get('brush', {})
            require(brush.get('mirroring') == 'NoMirror' and brush.get('tiling') == 'NoTile'
                    and isinstance(brush.get('uVRegion'), dict) and brush['uVRegion'].get('bIsValid') is False,
                    'Full-frame measured images cannot mirror, tile or override the native UV frame.')
            frame = review['source']['frameSize']
            require(frame == element['properties'].get('sourceFrameSize'), 'Source frame differs from the accepted resource.')
            rectangle = element['properties'].get('sourceRenderBounds', rectangle)
            require(rectangle[2:] == frame, 'This narrow receiver requires the accepted full-frame one-to-one source basis.')
        require(name not in expected, 'Duplicate accepted geometry mapping.')
        expected[name] = rectangle
    require(set(expected) == set(rows), 'Accepted source geometry must exactly cover the four native receivers.')
    for widget in rows.values():
        props = widget['properties']
        require(props.get('clipping') == 'Inherit', 'Clipping requires a separately supported actual-render interpretation.')
        _visible(props.get('visibility'))
        transform = props.get('renderTransform', {})
        local_scale = transform.get('scale', {})
        require(transform.get('angle') == 0 and transform.get('shear') == {'x': 0, 'y': 0}
                and transform.get('translation') == {'x': 0, 'y': 0}
                and type(local_scale.get('x')) in (int, float) and local_scale['x'] > 0
                and local_scale.get('y') == local_scale['x'], 'Only positive uniform native scaling without translation/rotation/shear is supported.')
    return rows, expected, images, next(iter(texts.values()))


def _consume_provider(config, raw, raw_path):
    """Recompute actual Retainer/nativeVM evidence; visual acceptance is separate."""
    require(raw['processId'] == config['host']['expectedPid'] and raw['engine'] == config['helper']['engine']
            and raw['world'] == config['helper']['world'] and raw['commandLine'] == config['helper']['commandLine']
            and raw['sourceAssetAfterSha256'] == config['host']['sourceAssetSha256'], 'Actual collector differs from its frozen host/helper/source.')
    loaded = _loaded_acquisitions(config, raw, raw_path)
    rectangles, identities, measured = [], [], []
    previous_locale = None
    rows, _, images, text = _source_expectations(config['request'], config['requestPath'], config['snapshot'], config['decisions'], config['config'])
    for index, sample in enumerate(raw['captures']):
        producer_path = bound_path(sample['producerReadback'], raw_path)
        producer = validate(load_json(producer_path), 'retainerProducerReadback')
        geometry_path = bound_path(sample['geometryReadback'], raw_path)
        geometry = validate(load_json(geometry_path), 'retainerNativePaintReadback')
        _native_pixels(config, raw, raw_path, sample, producer, producer_path)
        runtime_rows, identity, runtime = _runtime_receivers(config, raw, raw_path, sample, producer, producer_path)
        _producer_topology(config, raw, sample, producer, producer_path, geometry, identity, runtime_rows)
        prefix = ('unit', 'scale075')[index]
        before, after = loaded[prefix + '-before'], loaded[prefix + '-after']
        stamp = aware_time(sample['capturedAt'])
        require(bound_path(producer['loadedSnapshotBefore'], producer_path) == before['snapshotPath']
                and bound_path(producer['loadedSnapshotAfter'], producer_path) == after['snapshotPath']
                and aware_time(runtime['completedAt']) <= aware_time(geometry['capturedAt'])
                and before['completedAt'] <= aware_time(geometry['capturedAt']) <= stamp <= after['startedAt'],
                'Actual runtime and full source reads must finish before this case paint/export, followed by full after read.')
        native_rectangles = _native_paint(config, raw, sample, geometry, runtime_rows)
        rectangles.append(native_rectangles)
        identities.append({name: row['objectPath'] for name, row in runtime_rows.items()})
        locale = producer['localeReadback']
        require(locale['locale'] == sample['context']['locale'] and (previous_locale is None or locale == previous_locale), 'Actual native locale is wrong or changed between cases.')
        previous_locale = locale
        interpretation = producer['staticPreviewInterpretation']
        actual_text = runtime_rows[text['widgetName']]['properties']['text']
        require(interpretation['dataId'] == sample['context']['dataId']
                and interpretation['stateId'] == sample['context']['stateId']
                and interpretation['quantityText'] == actual_text == text['properties']['text'], 'Static preview data/state interpretation does not match actual native source/receiver.')
        require(bound_path(producer['fontEvidence'], producer_path) == config['fontPath'], 'Producer Font source differs from frozen adoption.')
        measured.append({'id': sample['id'], 'image': binding(bound_path(sample['image'], raw_path)),
                         'capturedAt': sample['capturedAt'], 'rectangles': native_rectangles})
    require(identities[0] == identities[1], 'The whole same receiver set must survive both actual scale cases.')
    require(raw['captures'][0]['image']['sha256'] != raw['captures'][1]['image']['sha256'], 'Native PNG did not respond to actual whole-instance compression.')
    return {'capability': CAPABILITY, 'cases': measured, 'keys': {(raw['assetPath'], name) for name in images},
            'inspectedRegions': {'geometry:' + case['id'] for case in config['config']['cases']}}


def _producer_topology(config, raw, sample, producer, producer_path, geometry, identity, runtime_rows):
    require(bound_path(producer['hostEvidence'], producer_path) == config['hostPath'], 'Native producer host proof differs from adoption.')
    actual = producer['runtimeIdentities']
    require(actual['pilot'] == identity['pilotInstance'] and actual['retainer']['path'] == sample['retainerInstance']
            and actual['captureCanvas']['path'] == geometry['captureCanvasInstance']
            and actual['host']['class'] == config['helper']['blueprint'] + '_C'
            and actual['hostRoot']['class'] == actual['captureCanvas']['class'] == '/Script/UMG.CanvasPanel'
            and actual['retainer']['class'] == '/Script/UMG.RetainerBox', 'Native EUW/Retainer/Canvas/pilot identities do not form the supported capture host.')
    for role, key in [('Host', 'host'), ('ProbeCanvas', 'hostRoot'), ('Retainer', 'retainer'), ('CaptureCanvas', 'captureCanvas'), ('PilotInstance', 'pilot')]:
        if role in geometry['rawNativePaint']:
            require(geometry['rawNativePaint'][role]['widgetPath'] == actual[key]['path'], 'Native VM geometry targets another capture host role.')
    relations = producer['runtimeRelations']
    require(relations['hostRootChildren'] == [actual['retainer']['path']]
            and relations['retainerContent'] == actual['captureCanvas']['path']
            and relations['captureCanvasChildren'] == [sample['widgetInstance']], 'Actual capture topology contains extra, missing or unrelated content.')
    for name, row in runtime_rows.items():
        chain = relations['receiverOuterChains'][name]
        require(chain[0] == row['outerPath'] and sample['widgetInstance'] in chain
                and len(chain) == len(set(chain)), 'Actual receiver outer chain does not reach this same pilot.')
    require(geometry['helperFunction'] == config['helper']['function'], 'Native paint helper differs from frozen graph identity.')
    association = producer['renderTargetAssociation']
    before = {row['path']: row for row in association['before']}
    after = {row['path']: row for row in association['after']}
    added = {row['path']: row for row in association['new']}
    require(len(before) == len(association['before']) and len(after) == len(association['after'])
            and len(added) == len(association['new']) == 1
            and set(added) == set(after) - set(before) == {sample['renderTarget']}
            and added[sample['renderTarget']] == after[sample['renderTarget']]
            and association['uniqueNewTargetPath'] == sample['renderTarget']
            and association['retainerInstance'] == sample['retainerInstance']
            and association['frame'] <= sample['frame']
            and datetime.fromtimestamp(raw['startedAt'], timezone.utc) <= aware_time(association['observedAt']) <= aware_time(sample['capturedAt']), 'Actual unique Retainer target association is missing or inconsistent.')
    target = producer['renderTarget']
    require(all(added[sample['renderTarget']][key] == target[key] for key in ('path', 'class', 'outer', 'size')), 'Actual exported target differs from the uniquely observed native target.')


def _value(value):
    result = value.get('returnValue') if isinstance(value, dict) and 'returnValue' in value else value
    if isinstance(result, str):
        try:
            return json.loads(result)
        except ValueError:
            pass
    return result


def _native_value(value):
    if isinstance(value, float):
        value = struct.unpack('<f', struct.pack('<f', value))[0]
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        return {key: _native_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_native_value(item) for item in value]
    return value


class _RetainedReadTransport:
    """Pure matching of retained getter envelopes; never dispatches any Tool."""
    def __init__(self, rows, start, finish, runtime=False):
        self.rows, self.index, self.start, self.finish, self.runtime = rows, 0, start, finish, runtime

    def _read(self, kind, toolset, tool=None, arguments=None):
        require(self.index < len(self.rows), 'Missing retained actual getter response.')
        row = self.rows[self.index]
        self.index += 1
        request = row['request'] if self.runtime else row
        require(row['kind'] == kind and request['toolset'] == toolset
                and (kind == 'describe' or (request['tool'] == tool and request['arguments'] == arguments)),
                'Retained actual requests differ from the original read-only reader program.')
        require(self.start <= aware_time(row['startedAt']) <= aware_time(row['completedAt']) <= self.finish,
                'Actual getter request is outside its acquisition interval.')
        return row['response'] if self.runtime else row['result']

    def describe(self, toolset):
        return self._read('describe', toolset)

    def call(self, toolset, tool, arguments):
        return self._read('call', toolset, tool, arguments)

    def complete(self):
        require(self.index == len(self.rows), 'Unexpected extra actual transport calls in reader evidence.')


def _endpoint(config, value):
    endpoint = urlparse(value)
    require(endpoint.scheme == 'http' and endpoint.hostname == '127.0.0.1'
            and endpoint.path == '/mcp' and not endpoint.query and not endpoint.fragment
            and endpoint.port in {row['LocalPort'] for row in config['host']['endpoints']}, 'Official endpoint is not bound to this actual OS host.')


def _runtime_receivers(config, raw, raw_path, sample, producer, producer_path):
    """Reconstruct actual properties/classes from retained official getter calls."""
    path = bound_path(sample['runtimeReadback'], raw_path)
    require(path == bound_path(producer['runtimeReadback'], producer_path), 'Producer/runtime snapshot bindings differ.')
    record = validate(load_json(path), 'retainerRuntimeReadback')
    identity_path = bound_path(record['runtimeIdentity'], path)
    require(identity_path == bound_path(producer['runtimeIdentity'], producer_path), 'Runtime identity bindings disagree.')
    identity = validate(load_json(identity_path), 'retainerRuntimeIdentity')
    _endpoint(config, record['officialEndpoint'])
    require(record['reportedEditorPid'] == identity['editorPid'] == raw['processId'] == config['host']['expectedPid']
            and record['officialEndpoint'] == identity['officialEndpoint']
            and record['caseId'] == identity['caseId'] == sample['id']
            and identity['pilotInstance']['path'] == sample['widgetInstance']
            and identity['pilotInstance']['class'] == raw['assetPath'] + '.' + raw['assetPath'].rsplit('/', 1)[-1] + '_C'
            and identity['assetPath'] == raw['assetPath'] and identity['frame'] <= sample['frame'], 'Runtime reader identity/host/case differs.')
    require(bound_path(record['sourceExecution'], path) == config['executionPath']
            and bound_path(record['sourceSnapshot'], path) == config['snapshotPath']
            and bound_path(record['readerSource'], path) in config['helpers']
            and bound_path(identity['collectorSource'], identity_path) == config['collector'], 'Runtime reader source/lineage is not frozen by adoption.')
    start, finish = aware_time(record['startedAt']), aware_time(record['completedAt'])
    require(datetime.fromtimestamp(raw['startedAt'], timezone.utc) <= aware_time(identity['capturedAt'])
            == aware_time(record['identityCapturedAt']) <= start <= finish <= aware_time(sample['capturedAt']), 'Runtime properties must actually precede export in this adopted case.')
    source_rows = {row['widgetName']: row for row in config['snapshot']['assets'][0]['widgets']}
    entries = identity['widgets']
    require(len({entry['name'] for entry in entries}) == 4 and {entry['name'] for entry in entries} == set(source_rows), 'Runtime identity names are incomplete or duplicated.')
    payload = []
    seen = set()
    for entry in entries:
        source = source_rows[entry['name']]
        require(entry['class'] == source['classPath'] and entry['path'] == entry['outer'] + '.' + entry['name']
                and entry['path'].startswith(sample['widgetInstance'] + '.WidgetTree')
                and entry['path'] not in seen, 'Runtime receiver does not identify the actual native WidgetTree child.')
        seen.add(entry['path'])
        slot = entry['slot']
        require((slot is None) == (source['slot']['classPath'] is None), 'Runtime slot presence differs from saved state.')
        if slot:
            require(slot['class'] == source['slot']['classPath'] and slot['path'].startswith(sample['widgetInstance'] + '.WidgetTree')
                    and slot['path'] not in seen, 'Actual slot is not owned by this same pilot.')
            seen.add(slot['path'])
        payload.append({'identity': entry, 'widgetKeys': sorted(source['properties']), 'slotKeys': sorted(source['slot']['properties'])})
    reader = bound_path(record['readerSource'], path)
    tree = ast.parse(reader.read_text(encoding='utf-8-sig'))
    bodies = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'BODY' for target in node.targets)]
    require(len(bodies) == 1 and isinstance(bodies[0], str), 'Actual frozen runtime reader has no unique literal getter program.')
    from art_editor import ArtEditor, OBJ, PROGRAM
    transport = _RetainedReadTransport(record['transportCalls'], start, finish, runtime=True)
    editor = ArtEditor(transport)
    environment = _value(editor._call(PROGRAM, 'get_execution_environment', {}))
    require(environment == record['programmaticEnvironment'], 'Runtime environment differs from actual retained response.')
    require(environment.get('language') == 'python' and 'execute_tool' in environment.get('instructions', '')
            and 'json' in [item.get('name') for item in environment.get('supported_modules', [])], 'Unsupported actual runtime getter environment.')
    editor.environment = environment
    calls = [(OBJ, name) for name in ('list_properties', 'get_properties', 'get_class')]
    schemas = []
    for toolset, tool in [(PROGRAM, 'get_execution_environment'), (PROGRAM, 'execute_tool_script')] + calls:
        schema = editor._schema(toolset, tool)
        schemas.append({key: schema[key] for key in ('name', 'inputSchema', 'outputSchema')})
    require(schemas == record['relatedToolSchemas'], 'Runtime getter input/output schemas differ from retained official discovery.')
    program = editor._program(bodies[0], {'receivers': payload, 'tools': [ts + '.' + name for ts, name in calls]}, calls)
    transport.complete()
    require(program == record['programmaticRaw'] and program.get('status') == 'collected' and program.get('error') is None
            and program.get('calls') == record['nativeCalls'], 'Runtime raw program/native ledgers differ.')
    native = record['nativeCalls']
    index, rebuilt, observed_program = 0, {}, []
    for entry in entries:
        source = source_rows[entry['name']]
        pieces = []
        for target, properties in [(entry, source['properties'])] + ([(entry['slot'], source['slot']['properties'])] if entry['slot'] else []):
            actual = []
            for tool, arguments in [('list_properties', {'instance': {'refPath': target['path']}}),
                                    ('get_properties', {'instance': {'refPath': target['path']}, 'properties': sorted(properties)}),
                                    ('get_class', {'instance': {'refPath': target['path']}})]:
                call = native[index]
                index += 1
                require(call['sequence'] == index and call['tool'] == OBJ + '.' + tool and call['arguments'] == arguments
                        and call['error'] is None, 'Actual runtime getter sequence/target/selected keys differs.')
                actual.append(_value(call['response']))
            available = actual[0].get('properties') if isinstance(actual[0].get('properties'), dict) else actual[0]
            require(all(key in available for key in properties) and set(actual[1]) == set(properties)
                    and _ref(actual[2]) == target['class'], 'Actual schema, class or complete runtime properties are missing.')
            require(canonical(_native_value(actual[1])) == canonical(_native_value(properties)), 'Actual runtime Brush/font/layout state differs from final saved source.')
            pieces.append({'schema': actual[0], 'properties': actual[1], 'class': actual[2]})
        observed_program.append({'name': entry['name'], 'widget': pieces[0], 'slot': pieces[1] if entry['slot'] else None})
        slot = None if not entry['slot'] else {'objectPath': entry['slot']['path'], 'outerPath': entry['slot']['outer'],
            'classPath': _ref(pieces[1]['class']), 'properties': pieces[1]['properties']}
        rebuilt[entry['name']] = {'widgetName': entry['name'], 'objectPath': entry['path'], 'outerPath': entry['outer'],
            'classPath': _ref(pieces[0]['class']), 'properties': pieces[0]['properties'], 'slot': slot}
    require(index == 21 == len(native) and observed_program == program['receivers']
            and record['normalized']['widgets'] == rebuilt, 'Runtime normalized projection does not reproduce from all 21 actual getters.')
    return rebuilt, identity, record


def _loaded_acquisitions(config, raw, raw_path):
    """Re-normalize retained actual full reads with a transport that cannot call UE."""
    path = bound_path(raw['loadedAcquisition'], raw_path)
    manifest = validate(load_json(path), 'retainerLoadedAcquisitions')
    _endpoint(config, manifest['officialEndpoint'])
    require(manifest['processId'] == raw['processId'] == config['host']['expectedPid']
            and bound_path(manifest['hostEvidence'], path) == config['hostPath'], 'Full native reads refer to another actual Editor.')
    roles = {record['role']: record for record in manifest['reads']}
    require(len(roles) == 4, 'Full read roles are duplicated or missing.')
    from art_editor import ArtEditor, BP
    results, seen = {}, set()
    for role in ('unit-before', 'unit-after', 'scale075-before', 'scale075-after'):
        entry = roles[role]
        snapshot_path = bound_path(entry['snapshot'], path)
        acquisition_path = bound_path(entry['acquisition'], path)
        require(snapshot_path not in seen and acquisition_path not in seen, 'Full acquisitions must use distinct real files.')
        seen.update((snapshot_path, acquisition_path))
        acquisition = validate(load_json(acquisition_path), 'retainerFullSnapshotAcquisition')
        start, finish = aware_time(acquisition['startedAt']), aware_time(acquisition['completedAt'])
        require(datetime.fromtimestamp(raw['startedAt'], timezone.utc) <= start <= finish
                <= datetime.fromtimestamp(raw['finishedAt'], timezone.utc)
                and acquisition['processId'] == raw['processId']
                and acquisition['officialEndpoint'] == manifest['officialEndpoint']
                and bound_path(acquisition['hostEvidence'], acquisition_path) == config['hostPath']
                and bound_path(acquisition['sourceExecution'], acquisition_path) == config['executionPath']
                and bound_path(acquisition['readerSource'], acquisition_path) in config['helpers']
                and bound_path(acquisition['snapshot'], acquisition_path) == snapshot_path, 'Actual full snapshot acquisition is not in this frozen lineage/host/interval.')
        snapshot = validate(load_json(snapshot_path), 'snapshot')
        require(start <= aware_time(snapshot['capturedAt']) <= finish
                and state_hash(snapshot) == state_hash(config['snapshot']), 'Actual full loaded state differs from final saved source.')
        calls_path = bound_path(acquisition['rawCalls'], acquisition_path)
        calls = validate(load_json(calls_path), 'retainerLoadedRawCalls')
        require(calls['method'] == 'mixed' and calls['officialEndpoint'] == manifest['officialEndpoint']
                and calls['processId'] == raw['processId'] and bound_path(calls['hostEvidence'], calls_path) == config['hostPath'], 'Full actual getter ledger has another provenance.')
        native = calls['nativeMode']
        require(start <= aware_time(native['startedAt']) <= aware_time(native['completedAt']) <= finish,
                'Actual protected-field getter is outside the full read interval.')
        response = native['response']
        require(response.get('ok') is True and response['data']['propertyPath'] == 'DesignSizeMode'
                and response['data']['target']['isDirty'] is False, 'Actual independent protected-field getter failed or source is dirty.')
        getter = json.loads(native['command'][-1])
        require(native['command'][-4:-1] == ['tool', 'manage-property', '--args-json']
                and getter == {'action': 'get', 'objectPath': response['data']['target']['path'], 'propertyPath': 'DesignSizeMode'}, 'Protected-field evidence is not the exact read-only getter.')
        class _RetainedMode:
            def design_size_mode(self, cdo):
                require(cdo == response['data']['target']['path'], 'Native mode targets another generated CDO.')
                return response['data']['value']
        transport = _RetainedReadTransport(calls['officialCalls'], start, finish)
        editor = ArtEditor(transport, nxue=_RetainedMode())
        rebuilt = editor.snapshot([raw['assetPath']])
        cdo = _value(editor._call(BP, 'get_default_object', {
            'blueprint': {'refPath': raw['assetPath'] + '.' + raw['assetPath'].rsplit('/', 1)[-1]}}))
        transport.complete()
        require(_ref(cdo) == getter['objectPath'] and response['data']['value'] == snapshot['assets'][0]['designSizeMode']
                and state_hash(rebuilt) == state_hash(snapshot) == calls['actualSnapshotStateSha256'], 'Full snapshot does not reconstruct from retained actual native results.')
        results[role] = {'snapshotPath': snapshot_path, 'snapshot': snapshot,
                         'startedAt': start, 'completedAt': finish, 'acquisition': acquisition}
    require(results['unit-before']['snapshotPath'] == bound_path(raw['loadedSnapshotBefore'], raw_path)
            and results['scale075-after']['snapshotPath'] == bound_path(raw['loadedSnapshotAfter'], raw_path), 'Global loaded before/after differ from actual four-read coverage.')
    for first, second in zip(('unit-before', 'unit-after', 'scale075-before'), ('unit-after', 'scale075-before', 'scale075-after')):
        require(results[first]['completedAt'] <= results[second]['startedAt'], 'Actual full read chronology is reversed or overlapping.')
    return results


def _paint_rect(entry):
    values = entry['values']
    local = _numbers(values['LocalSize'], 2)
    corners = [_numbers(values[name], 2) for name in ('TopLeft', 'TopRight', 'BottomRight', 'BottomLeft')]
    absolute = [corners[1][0] - corners[0][0], corners[3][1] - corners[0][1]]
    # These extents are derived from the actual VM paint corners. They do not
    # claim that Python FGeometry/GetAbsoluteSize returned a nonzero structure.
    return _rectangle({'localSize': local, 'absoluteSize': absolute, 'transformedCorners': corners}), corners


def _native_paint(config, raw, sample, geometry, runtime_rows):
    """Recompute pixel coordinates from VM paint values, never Slot arithmetic."""
    validate(geometry, 'retainerNativePaintReadback')
    require(geometry['caseId'] == sample['id'] and geometry['frame'] == sample['frame']
            and geometry['processId'] == raw['processId'] and geometry['widgetInstance'] == sample['widgetInstance']
            and aware_time(geometry['capturedAt']) <= aware_time(sample['capturedAt']), 'Native geometry belongs to another case/frame/instance.')
    paint = geometry['rawNativePaint']
    require(paint['PilotInstance']['widgetPath'] == sample['widgetInstance']
            and paint['CaptureCanvas']['widgetPath'] == geometry['captureCanvasInstance']
            and all(row['function'] == geometry['helperFunction'] for row in paint.values()), 'VM target/helper identity differs.')
    _, canvas_corners = _paint_rect(paint['CaptureCanvas'])
    local = paint['CaptureCanvas']['values']['LocalSize']
    size = sample['context']['size']
    _same(local, size, 'Actual fixed capture canvas does not match original target pixels.')
    origin = canvas_corners[0]
    x_basis = [canvas_corners[1][i] - origin[i] for i in range(2)]
    y_basis = [canvas_corners[3][i] - origin[i] for i in range(2)]
    determinant = x_basis[0] * y_basis[1] - x_basis[1] * y_basis[0]
    require(math.isfinite(determinant) and determinant > 0, 'Missing or reversed actual paint-to-target basis.')
    mapping = geometry['captureSpaceMapping']
    for key, value in (('nativeCaptureLocalSize', local), ('topLeft', origin), ('xBasis', x_basis),
                       ('yBasis', y_basis), ('targetPixelSize', size)):
        _same(mapping[key], value, 'Declared mapping differs from actual VM basis: ' + key)
    require(_close(mapping['determinant'], determinant), 'Mapping determinant differs from actual native corners.')
    require(set(geometry['derivedPixelCorners']) <= set(paint), 'Derived diagnostic corners cover another native role set.')
    rectangles = {}
    for name, entry in paint.items():
        _, corners = _paint_rect(entry)
        pixels = []
        for x, y in corners:
            dx, dy = x - origin[0], y - origin[1]
            pixels.append([(dx * y_basis[1] - dy * y_basis[0]) / determinant * size[0],
                           (x_basis[0] * dy - x_basis[1] * dx) / determinant * size[1]])
        if name in geometry['derivedPixelCorners']:
            for actual, recorded in zip(pixels, geometry['derivedPixelCorners'][name]):
                _same(actual, recorded, 'Diagnostic derived corners disagree with recomputed native result: ' + name)
        rectangles[name] = [pixels[0][0], pixels[0][1], pixels[1][0] - pixels[0][0], pixels[3][1] - pixels[0][1]]
    rows, expected, images, _ = _source_expectations(config['request'], config['requestPath'],
                                                   config['snapshot'], config['decisions'], config['config'])
    root_rect = rectangles[config['config']['contentRootWidgetName']]
    scale = sample['wholeWidgetRenderScale'][0]
    for name, native in rows.items():
        require(name in runtime_rows and paint[name]['widgetPath'] == runtime_rows[name]['objectPath'], 'Measured receiver is not the actual official runtime target: ' + name)
        rect = rectangles[name]
        normalized = [(rect[0] - root_rect[0]) / scale, (rect[1] - root_rect[1]) / scale, rect[2] / scale, rect[3] / scale]
        _same(normalized, expected[name], 'Actual native paint differs from accepted source: ' + name)
    _same(rectangles['PilotInstance'], root_rect, 'Measured pilot and actual content root do not share the same complete content bounds.')
    if scale == 1:
        native = [rectangles[name] for name in rows]
        bounds = [min(rect[0] for rect in native), min(rect[1] for rect in native)]
        bounds += [max(rect[0] + rect[2] for rect in native) - bounds[0], max(rect[1] + rect[3] for rect in native) - bounds[1]]
        reference = config['reference']
        _same(bounds, reference['regions'][0]['captureBounds'], 'Native complete-frame comparison bounds differ.')
        _same(bounds[2:], reference['sourceSize'], 'Native primary comparison would resample/crop source pixels.')
    return rectangles


def _native_pixels(config, raw, raw_path, sample, producer, producer_path):
    """Verify real byte-domain RGBA32f against every unmodified exported PNG pixel."""
    validate(producer, 'retainerProducerReadback')
    require(producer['caseId'] == sample['id'] and producer['capturedAt'] == sample['capturedAt']
            and producer['frame'] == sample['frame'] and producer['processId'] == raw['processId']
            and producer['engine'] == raw['engine'] and producer['world'] == raw['world']
            and producer['assetPath'] == raw['assetPath']
            and producer['sourceAssetSha256'] == raw['sourceAssetAfterSha256'], 'Native exporter identity/time/source differs.')
    target = producer['renderTarget']
    require(target['path'] == sample['renderTarget'] and target['size'] == sample['context']['size']
            and producer['wholeWidgetRenderScale'] == sample['wholeWidgetRenderScale'], 'Native Retainer target or actual scale differs.')
    require(bound_path(producer['collectorSource'], producer_path) == config['collector']
            and _bindings(producer['helpers'], producer_path) == config['helpers'], 'Native producer source/helper bindings changed.')
    # Exporter image binding has its own real owner; raw sample binding is
    # independently resolved by validate_capture before this provider stage.
    image = bound_path(producer['png'], producer_path)
    require(image == bound_path(sample['image'], raw_path), 'Native export PNG belongs to another sample.')
    pixels = producer['nativeRawPixels']
    source = bound_path({key: pixels[key] for key in ('path', 'sha256')}, producer_path)
    width, height = sample['context']['size']
    require([pixels['width'], pixels['height']] == [width, height] and pixels['pixelCount'] == width * height,
            'Native raw pixel count differs from actual capture dimensions.')
    data = source.read_bytes()
    require(len(data) == width * height * 4 * 4, 'Native raw RGBA32f byte length differs.')
    values = [value[0] for value in struct.iter_unpack('<f', data)]
    require(all(math.isfinite(value) and 0 <= value <= 255 and value == int(value) for value in values), 'Native RGBA32f is not finite integral byte-domain color.')
    _same(pixels['channelMin'], [min(values[channel::4]) for channel in range(4)], 'Declared native channel minima differ.')
    _same(pixels['channelMax'], [max(values[channel::4]) for channel in range(4)], 'Declared native channel maxima differ.')
    from PIL import Image
    with Image.open(image) as decoded:
        require(decoded.mode == 'RGBA' and list(decoded.size) == [width, height]
                and decoded.tobytes() == bytes(int(value) for value in values), 'PNG pixels do not exactly equal native Retainer raw byte-values.')


def validate_capture(adoption_path, plan_path, execution_path, capture, capture_path):
    """Re-read all bound high-level inputs on bind, verify and independent stage."""
    config = configuration(adoption_path, plan_path, execution_path)
    require(capture.get('version') == 2, 'Adoption accepts capture/2 only; legacy capture/1 is not measurement.')
    validate(capture, 'capture')
    evidence_path = bound_path(capture['geometryEvidence'], capture_path)
    evidence = validate(load_json(evidence_path), 'measuredGeometryEvidence')
    require(bound_path(evidence['adoption'], evidence_path) == config['adoptionPath']
            and bound_path(evidence['finalSnapshot'], evidence_path) == config['snapshotPath']
            and capture['snapshotSha256'] == sha256(config['snapshotPath']), 'Sidecar adoption/final snapshot identity differs.')
    raw_path = bound_path(evidence['collectorRaw'], evidence_path)
    raw = validate(load_json(raw_path), 'retainerGeometryRaw')
    require(bound_path(raw['adoption'], raw_path) == config['adoptionPath']
            and bound_path(raw['finalSnapshot'], raw_path) == config['snapshotPath'], 'Raw refers to another adoption/final snapshot.')
    asset_path = config['reference']['assetPath']
    expected_file = (config['project'] / 'Content' / (asset_path[len('/Game/'):] + '.uasset')).resolve(strict=True)
    source = bound_path(evidence['sourceAsset'], evidence_path)
    require(source == expected_file == bound_path(raw['sourceAsset'], raw_path)
            and raw['assetPath'] == asset_path and Path(raw['projectRoot']).resolve(strict=True) == config['project']
            and raw['sourceAssetBeforeSha256'] == raw['sourceAssetAfterSha256'] == sha256(source), 'Physical source/current saved bytes or project changed.')
    require(bound_path(raw['collectorSource'], raw_path) == config['collector']
            and _bindings(raw['helpers'], raw_path) == config['helpers'], 'Executed collector/helper set differs from frozen adoption.')
    start, finish = raw['startedAt'], raw['finishedAt']
    require(math.isfinite(start) and math.isfinite(finish) and start <= finish, 'Missing finite collector interval.')
    start, finish = datetime.fromtimestamp(start, timezone.utc), datetime.fromtimestamp(finish, timezone.utc)
    require(config['created'] <= start, 'Adoption must be frozen before the real collector starts; probes cannot be retroactively adopted.')
    loaded = []
    loaded_paths = []
    for field in ('loadedSnapshotBefore', 'loadedSnapshotAfter'):
        path = bound_path(evidence[field], evidence_path)
        require(path == bound_path(raw[field], raw_path), 'Duplicate loaded-state bindings disagree.')
        observed = validate(load_json(path), 'snapshot')
        require(observed['acquisition']['method'] in {'official-unreal-mcp', 'mixed'}
                and state_hash(observed) == state_hash(config['snapshot'])
                and start <= aware_time(observed['capturedAt']) <= finish, 'Complete actual loaded state differs from final source or collector interval.')
        loaded.append(observed)
        loaded_paths.append(path)
    require(loaded_paths[0] != loaded_paths[1]
            and aware_time(loaded[0]['capturedAt']) < aware_time(loaded[1]['capturedAt']), 'Before/after must be distinct ordered native acquisitions.')
    bound_path(raw['loadedAcquisition'], raw_path)
    require(evidence['cases'] == [{'id': case['id'], 'captureIndex': index}
            for index, case in enumerate(config['config']['cases'])], 'Sidecar case/index coverage differs.')
    previous = None
    same_instance = None
    for index, (sample, case) in enumerate(zip(raw['captures'], config['config']['cases'])):
        stamp = aware_time(sample['capturedAt'])
        require(sample['id'] == case['id'] and sample['context'] == config['reference']['context'] == capture['context']
                and sample['wholeWidgetRenderScale'] == [case['scale'], case['scale']], 'Case/context/whole-instance scale differs.')
        require(aware_time(loaded[0]['capturedAt']) <= stamp <= aware_time(loaded[1]['capturedAt']), 'Every actual sample must be bracketed by full loaded-state reads.')
        if previous:
            require(stamp > previous[0] and sample['frame'] > previous[1], 'Compressed case must follow original on later real native frames.')
        previous = stamp, sample['frame']
        identity = sample['widgetInstance'], sample['retainerInstance'], sample['renderTarget']
        require(same_instance in (None, identity), 'Both cases must retain the same real pilot/Retainer/target.')
        same_instance = identity
        require(bound_path(sample['fontEvidence'], raw_path) == config['fontPath'], 'Sample uses another font evidence source.')
        for field in ('producerReadback', 'geometryReadback', 'runtimeReadback'):
            bound_path(sample[field], raw_path)
        image = bound_path(sample['image'], raw_path)
        from PIL import Image
        with Image.open(image) as decoded:
            require(list(decoded.size) == config['reference']['context']['size'] and decoded.mode == 'RGBA', 'Original native PNG dimensions/type differ; no resize or opaque substitute.')
            alpha = decoded.getchannel('A')
            require(alpha.getbbox() is not None, 'Empty native image cannot pass.')
            if capture['context']['background'] == [0, 0, 0, 0]:
                require(alpha.getextrema()[0] == 0, 'Requested transparent target has no observed transparent pixel.')
        if index == 0:
            require(image == bound_path(capture['image'], capture_path)
                    and sample['capturedAt'] == capture['capturedAt'], 'Primary capture must equal the exact original sample/time.')
    require(capture['assetPath'] == asset_path, 'Capture identifies another asset.')
    result = _consume_provider(config, raw, raw_path)
    result['geometryEvidence'] = binding(evidence_path)
    result['geometryAdoption'] = binding(config['adoptionPath'])
    return result


def verification_geometry(plan_path, execution_path, captures, captures_owner, *, adoption_path=None):
    """Legacy remains v1. Explicit adoption requires exact complete capture/2."""
    if adoption_path is None:
        require(all(validate(read_bound(record['capture'], captures_owner), 'capture')['version'] == 1 for record in captures), 'Capture/2 requires explicit independent geometry adoption.')
        return None
    config = configuration(adoption_path, plan_path, execution_path)
    require(len(captures) == 1 and captures[0]['referenceId'] == config['reference']['id'], 'Adoption must cover exactly the original reference once.')
    path = bound_path(captures[0]['capture'], captures_owner)
    return validate_capture(adoption_path, plan_path, execution_path, load_json(path), path)


def bind_capture(adoption_path, raw_path, evidence_path, output_path):
    """Late read-only binding; no execution or success receipt is synthesized."""
    adoption_path = Path(adoption_path).resolve(strict=True)
    adoption = validate(load_json(adoption_path), 'measuredGeometryAdoption')
    plan_path = bound_path(adoption['plan'], adoption_path)
    execution_path = bound_path(adoption['execution'], adoption_path)
    config = configuration(adoption_path, plan_path, execution_path)
    raw = validate(load_json(raw_path), 'retainerGeometryRaw')
    evidence = {'kind': 'nextgame-ui-measured-presentation-geometry', 'version': 1,
        'adoption': binding(adoption_path), 'collectorRaw': binding(raw_path),
        'finalSnapshot': binding(config['snapshotPath']), 'sourceAsset': binding(bound_path(raw['sourceAsset'], raw_path)),
        'loadedSnapshotBefore': binding(bound_path(raw['loadedSnapshotBefore'], raw_path)),
        'loadedSnapshotAfter': binding(bound_path(raw['loadedSnapshotAfter'], raw_path)),
        'cases': [{'id': case['id'], 'captureIndex': index} for index, case in enumerate(config['config']['cases'])]}
    validate(evidence, 'measuredGeometryEvidence')
    write_json(evidence_path, evidence)  # An immutable input sidecar is not a success receipt.
    sample = raw['captures'][0]
    capture = {'kind': 'nextgame-ui-art-capture', 'version': 2, 'assetPath': config['reference']['assetPath'],
        'context': config['reference']['context'], 'snapshotSha256': sha256(config['snapshotPath']),
        'image': binding(bound_path(sample['image'], raw_path)), 'capturedAt': sample['capturedAt'],
        'acquisition': {'method': 'mixed', 'fallbackReason': 'Explicit bound EUW RetainerBox/native Blueprint VM receiver.'},
        'canonical': True, 'geometryEvidence': binding(evidence_path)}
    validate_capture(adoption_path, plan_path, execution_path, capture, output_path)
    write_json(output_path, capture)
    return {'referenceId': config['reference']['id'], 'capture': binding(output_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('adoption', 'collector-raw', 'geometry-output', 'output'):
        parser.add_argument('--' + field, type=Path, required=True)
    args = parser.parse_args()
    import json
    try:
        print(json.dumps(bind_capture(args.adoption, args.collector_raw, args.geometry_output, args.output), ensure_ascii=False))
        return 0
    except (ArtError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'pending', 'error': str(exc), 'code': getattr(exc, 'code', 'geometry.invalid'), 'runtimeVerified': False}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
