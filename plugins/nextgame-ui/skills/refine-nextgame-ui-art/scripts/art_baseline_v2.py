"""Evidence-backed resource-property deferrals for development-baseline/2 only.

No Editor or CLI. This validates accepted source -> exact actual resource gaps;
it never completes checks or relaxes final Readback/Bundle/document validation.
"""
from __future__ import annotations

from art_common import ArtError, aware_time, digest, load_json, read_bound, sha256, validate


def _fail(code, message):
    raise ArtError('baseline.' + code, message)


def contract_digest(contract):
    return digest({key: value for key, value in contract.items() if key != 'primaryReview'})


def _resource(value):
    return value.get('refPath') if isinstance(value, dict) else value


def _pending_judgments(requirement, accepted):
    """Art judgment text remains open; it is never a native value or exemption."""
    from _document_contract_common import is_accepted_in_scope
    records = {}
    for index, element in enumerate(requirement.get('uiModel', {}).get('elements', [])):
        if not is_accepted_in_scope(element, accepted):
            continue
        properties = element.get('properties', {})
        names = [key for key in ('nineSliceMarginStatus', 'nineSliceStatus')
                 if isinstance(properties.get(key), str) and 'pending' in properties[key].lower()]
        if properties.get('textEffectJudgment') == 'unresolved':
            names += ['textEffectJudgment', 'textEffectReason']
        procedural = properties.get('artMaterialCapability') in {'procedural-ui-material/1', 'procedural-ui-material/2'}
        if procedural:
            names += ['staticAppearance', 'artMaterialCapability', 'artMaterialExecutionStatus']
        for key in names:
            value = properties.get(key)
            if key == 'staticAppearance':
                if not isinstance(value, dict) or not value:
                    _fail('judgment_source', 'Procedural art intent needs the original nonempty static appearance object.')
            elif not isinstance(value, str) or not value:
                _fail('judgment_source', 'Unresolved art judgment needs its explicit original reason.')
            pointer = f'/uiModel/elements/{index}/properties/{key}'
            records[pointer] = {'elementId': element['id'], 'sourcePointer': pointer, 'sourceValue': value}
    return records


def _resource_gaps(requirement, bundle, readback, snapshot, accepted):
    """Enumerate only fixed accepted source -> Brush mappings, independently of IDs."""
    from _document_contract_common import is_accepted_in_scope

    assets = {a['id']: a for a in bundle['assets']}
    actual = {a['assetPath']: (ai, a) for ai, a in enumerate(snapshot['assets'])}
    normalized = {a['assetId']: a for a in readback['assets']}
    mapping_actual = {m['nodeMappingId']: (a, m) for a in readback['assets'] for m in a['nodeMappings']}
    gaps = {}
    for ei, element in enumerate(requirement.get('uiModel', {}).get('elements', [])):
        if not is_accepted_in_scope(element, accepted):
            continue
        properties = element.get('properties', {})
        source_fields = [key for key in ('defaultBrushResourceObject', 'drawAs', 'mirrorDesign') if key in properties]
        if not source_fields:
            continue
        mappings = [m for m in bundle['nodeMappings'] if element['id'] in m.get('requirementRefs', [])]
        if not mappings:
            _fail('deferral_mapping', 'An accepted resource element has no Bundle mapping: ' + element['id'])
        for mapping in mappings:
            aid, mid = mapping['assetId'], mapping['id']
            if mid not in mapping_actual or aid not in normalized:
                _fail('deferral_mapping', 'Resource mapping has no actual readback identity: ' + mid)
            ra, rm = mapping_actual[mid]
            if ra['assetId'] != aid or rm['layoutNodeId'] != mapping['layoutNodeId']:
                _fail('deferral_mapping', 'Resource mapping identity differs in actual readback.')
            asset = assets[aid]
            if asset['assetPath'] not in actual:
                _fail('deferral_actual', 'Resource asset has no actual snapshot.')
            ai, snap = actual[asset['assetPath']]
            candidates = [(wi, w) for wi, w in enumerate(snap['widgets']) if w['widgetName'] == rm['widgetName']]
            if len(candidates) != 1:
                _fail('deferral_actual', 'Resource mapping must identify exactly one actual widget.')
            wi, widget = candidates[0]
            # Only these three exact accepted resource-related Brush mappings exist.
            # Slots, text, state, interaction, variable/EntryClass and geometry are
            # deliberately not admissible deferred field types.
            if widget['classPath'] != '/Script/UIFramework.GameImage':
                _fail('deferral_actual', 'Brush resource deferral requires an actual GameImage.')
            brush = widget['properties'].get('brush')
            for source_field in source_fields:
                expected = properties[source_field]
                native = {'defaultBrushResourceObject': 'resourceObject', 'drawAs': 'drawAs', 'mirrorDesign': 'mirroring'}[source_field]
                allowed = ({'NoDrawType', 'Box', 'Border', 'Image', 'RoundedBox'} if native == 'drawAs' else
                           {'NoMirror', 'Horizontal', 'Vertical', 'Both', 'MirrorHorizontal', 'MirrorVertical', 'MirrorBoth'})
                if not isinstance(expected, str) or (not expected.startswith('/Game/') if native == 'resourceObject' else expected not in allowed):
                    _fail('deferral_source', 'Accepted art field must be an exact supported native Brush value.')
                expected_native = ({'MirrorHorizontal': 'Horizontal', 'MirrorVertical': 'Vertical', 'MirrorBoth': 'Both'}
                                   .get(expected, expected) if native == 'mirroring' else expected)
                if not isinstance(brush, dict) or native not in brush:
                    _fail('deferral_actual', 'Missing actual Brush observation cannot prove an art property gap.')
                observed = brush[native]
                if (_resource(observed) if native == 'resourceObject' else observed) == expected_native:
                    continue
                source_pointer = f'/uiModel/elements/{ei}/properties/{source_field}'
                record = {'assetId': aid, 'elementId': element['id'], 'nodeMappingId': mid,
                    'widgetName': widget['widgetName'], 'sourcePointer': source_pointer,
                    'sourceValue': expected, 'expectedNativeValue': expected_native, 'nativeProperty': 'brush.' + native,
                    'actualSnapshotPointer': f'/assets/{ai}/widgets/{wi}/properties/brush/{native}',
                    'actualValue': observed}
                gaps[(source_pointer, mid)] = record
    return gaps


def validate_property_deferrals(request, request_path, paths, requirement, bundle, readback, context):
    """Return exact deferred IDs only after source, actual gaps, and primary review pass."""
    contract = request['developmentBaseline']
    if contract['version'] != 2 or request.get('capabilities', []).count('development-baseline/2') != 1:
        _fail('deferral_capability', 'Resource deferral requires explicit development-baseline/2.')
    checks = {c['id']: c for c in bundle['verification']['checks']}
    assets = {a['id']: a for a in bundle['assets']}
    basic = contract['basicPropertyCheckIds']
    basics = [checks.get(cid, {}) for cid in basic]
    if (len(basic) != len(assets) or len(set(basic)) != len(basic)
            or {c.get('assetId') for c in basics} != set(assets)
            or any(c.get('type') != 'key-properties' or c.get('status') != 'passed' for c in basics)):
        _fail('basic_properties', 'Every asset needs one explicitly identified passed basic property check.')
    snapshot = validate(load_json(paths['snapshot']), 'snapshot')
    accepted = context['acceptedClaimIds']
    judgments = _pending_judgments(requirement, accepted)
    declared = {}
    for item in contract['pendingArtJudgments']:
        pointer = item['sourcePointer']
        if pointer in declared or judgments.get(pointer) != {k: item[k] for k in ('elementId', 'sourcePointer', 'sourceValue')}:
            _fail('judgment_source', 'Pending art judgments must preserve exact accepted source records.')
        for cid in item['closureCheckIds']:
            check = checks.get(cid, {})
            if check.get('type') != 'preview' or check.get('status') != 'pending':
                _fail('judgment_check', 'Open art judgment must retain an original pending preview closure obligation.')
        declared[pointer] = judgments[pointer]
    if declared != judgments:
        _fail('judgment_coverage', 'Every unresolved art judgment must remain explicit; native defaults cannot close it.')
    expected_gaps = _resource_gaps(requirement, bundle, readback, snapshot, accepted)
    records = contract['deferredPropertyChecks']
    deferred = set()
    observed_gaps = {}
    for record in records:
        identity = record['check']
        cid = identity['id']
        original = checks.get(cid)
        if cid in deferred or cid in basic or original is None:
            _fail('deferral_check', 'Deferred IDs must be distinct original non-basic checks.')
        if (original.get('status') != 'pending' or original.get('type') != 'key-properties'
                or identity != {key: original.get(key) for key in ('id', 'type', 'assetId', 'requirementRefs', 'claimIds')}
                or identity['assetId'] not in assets or not set(identity['claimIds']) <= accepted):
            _fail('deferral_check', 'Deferred check must preserve exact accepted ID/type/asset/refs/claims and be pending.')
        deferred.add(cid)
        for field in record['fields']:
            key = (field['sourcePointer'], field['nodeMappingId'])
            if key not in expected_gaps or field != expected_gaps[key]:
                _fail('deferral_field', 'Deferred field must exactly match an accepted-source / actual-Brush resource gap.')
            # One source field can support several independent pending checks. It
            # may not be repeated within a check or presented with conflicting data.
            if record['fields'].count(field) != 1:
                _fail('deferral_field', 'Repeated field evidence within a check is not permitted.')
            observed_gaps[key] = field
    pending_properties = {cid for cid, c in checks.items() if c['type'] == 'key-properties' and c['status'] == 'pending'}
    if deferred != pending_properties or observed_gaps != expected_gaps:
        _fail('deferral_coverage', 'Deferred checks and accepted actual resource gaps require exact exhaustive coverage.')
    review = validate(read_bound(contract['primaryReview'], request_path), 'developmentBaselineReview')
    for name in ('requirement', 'bundle', 'readback', 'snapshot'):
        if review[name + 'Sha256'] != sha256(paths[name]):
            _fail('deferral_review', 'Primary review must bind all four current baseline sources.')
    if review['contractSha256'] != contract_digest(contract):
        _fail('deferral_review', 'Primary review must bind the exact complete version 2 contract.')
    if aware_time(review['reviewedAt']) < max(aware_time(contract['structureCompletedAt']),
            aware_time(readback['capturedAt']), aware_time(snapshot['capturedAt'])):
        _fail('deferral_review', 'Primary review must follow the observed structural result.')
    return frozenset(deferred)
