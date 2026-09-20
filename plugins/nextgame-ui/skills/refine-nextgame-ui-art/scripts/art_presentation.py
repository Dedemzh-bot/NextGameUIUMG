"""Opt-in presentation-review/1 checks. Pure file/snapshot validation, never UE.

Configuration arithmetic is not measured Widget geometry. Unknown layout and
actual geometry remain pending, even when every native property agrees.
"""
from __future__ import annotations

import math
from pathlib import Path

from art_common import ArtError, bound_path, index_snapshot, validate

CAPABILITY = 'presentation-review/1'
IMAGE_CLASSES = frozenset(('/Script/UIFramework.GameImage', '/Script/UMG.Image'))
TEXT_CLASSES = frozenset(('/Script/UMG.TextBlock',))


def enabled(request):
    return CAPABILITY in request.get('capabilities', [])


def _fail(code, message):
    raise ArtError('presentation.' + code, message)


def _close(a, b):
    return isinstance(a, (int, float)) and not isinstance(a, bool) and math.isfinite(a) and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)


def _static_resource_aspect_close(size, frame):
    """Allow only four-decimal dimension quantization and its float32 readback.

    Intersect the two possible uniform-scale intervals. Each dimension has at
    most half a 0.0001 design-unit rounding step plus half a native float32 ULP;
    this is not a relaxed relative ratio tolerance or measured Widget geometry.
    """
    if _close(size[0] / frame[0], size[1] / frame[1]):
        return True
    errors = []
    for value in size:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            return False
        exponent = math.frexp(value)[1]
        if exponent > 128:
            return False
        half_ulp = math.ldexp(1.0, max(exponent - 24, -149)) / 2
        # Restrict this extra allowance to decimal-grid values or their actual
        # float32 representation. Cap the per-axis budget at 0.001 design units.
        if abs(value - round(value, 4)) > half_ulp + 1e-12 or 0.00005 + half_ulp > 0.001:
            return False
        errors.append(0.00005 + half_ulp)
    lower = max((value - error) / source for value, error, source in zip(size, errors, frame))
    upper = min((value + error) / source for value, error, source in zip(size, errors, frame))
    return 0 < lower <= upper


def _values(actual, expected, label):
    if len(actual) != len(expected) or any(not _close(a, b) for a, b in zip(actual, expected)):
        _fail('native_mismatch', label + ' differs from the explicit presentation decision.')


def _vec(value, keys):
    if not isinstance(value, dict) or any(k not in value for k in keys):
        _fail('native_missing', 'Required native fields are missing: ' + ', '.join(keys))
    values = [value[k] for k in keys]
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in values):
        _fail('native_invalid', 'Native numeric fields must be finite.')
    return values


def _ref(value):
    path = value.get('refPath') if isinstance(value, dict) else value
    if path in (None, 'None', ''):
        return None
    if not isinstance(path, str) or not path.startswith('/Game/'):
        _fail('resource_ref', 'Expected a project resource object reference.')
    if '.' in path:
        asset, obj = path.rsplit('.', 1)
        if obj != asset.rsplit('/', 1)[-1]:
            _fail('resource_ref', 'Unexpected resource subobject reference.')
        path = asset
    return path


def _scope_nodes(request, snapshot, removed):
    _, nodes = index_snapshot(snapshot)
    scoped = {}
    for scope in request['scope']:
        names = scope.get('widgetNames')
        if names is not None and (len(names) != len(set(names)) or any((scope['assetPath'], n) not in nodes and (scope['assetPath'], n) not in removed for n in names)):
            _fail('scope', 'Every explicitly scoped widget must resolve exactly once.')
        scoped.update({key: node for key, node in nodes.items() if key[0] == scope['assetPath'] and (names is None or key[1] in names)})
    return nodes, scoped


def _evidence(item, request, request_path):
    record = item['reference']
    reference = next((r for r in request['references'] if r['id'] == record['referenceId']), None)
    if reference is None or reference['assetPath'] != item['assetPath']:
        _fail('reference', 'Presentation evidence must refer to a declared reference for the same asset.')
    region = next((r for r in reference['regions'] if r['id'] == record['regionId']), None)
    if region is None or item['widgetName'] not in region['widgetNames']:
        _fail('reference', 'Evidence region must explicitly include the reviewed widget.')
    from PIL import Image
    from art_images import _rect
    with Image.open(bound_path(reference['image'], request_path)) as image:
        bounds = _rect(record['bounds'], image.size, 'presentation reference bounds')
    x, y, w, h = bounds
    rx, ry, rw, rh = region['bounds']
    if x < rx or y < ry or x + w > rx + rw or y + h > ry + rh:
        _fail('reference_bounds', 'Local evidence must stay within its declared reference region.')


def _check(checks, identity, status, details):
    checks.append({'id': 'presentation.' + identity, 'status': status, 'details': details})


def _allocation(key, nodes, seen=None):
    """Narrow static allocation proof, not actual Slate geometry or a claimed size."""
    seen = set() if seen is None else set(seen)
    if key in seen:
        return None
    seen.add(key)
    node = nodes[key]
    slot = node['slot']
    props = slot['properties']
    if slot['classPath'] == '/Script/UMG.CanvasPanelSlot':
        auto = props.get('bAutoSize', props.get('autoSize'))
        if 'bAutoSize' in props and 'autoSize' in props and props['bAutoSize'] != props['autoSize']:
            _fail('slot_alias', 'Conflicting native auto-size aliases.')
        layout = props.get('layoutData', {})
        anchors = layout.get('anchors', {})
        if auto is False and anchors.get('minimum') == anchors.get('maximum') and anchors.get('minimum') is not None:
            size = _vec(layout.get('offsets'), ('right', 'bottom'))
            return size if min(size) > 0 else None
    if slot['classPath'] == '/Script/UMG.OverlaySlot' and node['parentWidgetName'] is not None:
        parent = _allocation((key[0], node['parentWidgetName']), nodes, seen)
        brush = node['properties'].get('brush', {}).get('imageSize')
        desired = _vec(brush, ('x', 'y')) if brush is not None else None
        pad = props.get('padding')
        if pad is None:
            return None
        l, t, r, b = _vec(pad, ('left', 'top', 'right', 'bottom'))
        alignments = (props.get('horizontalAlignment'), props.get('verticalAlignment'))
        result = []
        for axis, (fill, before, after) in enumerate((('HAlign_Fill', l, r), ('VAlign_Fill', t, b))):
            if alignments[axis] == fill and parent is not None:
                result.append(parent[axis] - before - after)
            elif alignments[axis] in (('HAlign_Left', 'HAlign_Center', 'HAlign_Right') if axis == 0 else ('VAlign_Top', 'VAlign_Center', 'VAlign_Bottom')) and desired is not None:
                result.append(desired[axis])
            else:
                return None
        return result if min(result) > 0 else None
    return None


def _transform_scale(key, nodes):
    scale = [1., 1.]
    while key in nodes:
        node = nodes[key]
        # ScaleBox and unobserved transforms require actual layout evidence.
        if node['classPath'] == '/Script/UMG.ScaleBox':
            return None
        transform = node['properties'].get('renderTransform')
        if transform is None:
            return None
        xy = _vec(transform.get('scale'), ('x', 'y'))
        shear = _vec(transform.get('shear'), ('x', 'y'))
        if any(shear) or transform.get('angle') != 0:
            return None
        if 0 in xy:
            _fail('transform', 'Zero image/ancestor scale is degenerate.')
        scale = [a * abs(b) for a, b in zip(scale, xy)]
        parent = node['parentWidgetName']
        if parent is None:
            return scale
        key = (key[0], parent)
    return None


def _family_value(entry, comparison):
    if comparison == 'aspect-mode':
        return entry['mode']
    if comparison.startswith('brush-'):
        pair = entry['brush']
    elif comparison.startswith('slot-'):
        pair = entry['slot']
    else:
        basis = entry.get('evaluationSize') or entry['frame']
        pair = [a / b for a, b in zip(entry['brush'], basis)] if entry['brush'] and basis else None
    if pair is None:
        return None
    if comparison.endswith(('-width', '-x')):
        return [pair[0]]
    if comparison.endswith(('-height', '-y')):
        return [pair[1]]
    return pair


def _same_family_value(left, right):
    if isinstance(left, str) or isinstance(right, str):
        return left == right
    return len(left) == len(right) and all(_close(a, b) for a, b in zip(left, right))


def _image(item, node, nodes, catalog, owner, checks, phase, capabilities=()):
    key = (item['assetPath'], item['widgetName'])
    identity = key[0] + ':' + key[1]
    props = node['properties']
    brush = props.get('brush')
    if not isinstance(brush, dict):
        _fail('native_missing', 'Image Brush was not observed: ' + identity)
    source, mode = item['source'], item['aspectMode']
    resource = _ref(brush.get('resourceObject'))
    if source['kind'] == 'procedural':
        if resource is not None or mode not in ('stretch', 'no-draw'):
            _fail('procedural', 'Procedural judgments require no resource and an explicit stretch/no-draw role.')
        allowed = ('NoDrawType',) if mode == 'no-draw' else ('RoundedBox', 'Box', 'Image')
        if brush.get('drawAs') not in allowed:
            _fail('draw_mode', 'Procedural image DrawAs conflicts with its explicit judgment.')
        if 'nineSlice' in item:
            _fail('nine_slice', 'Procedural images cannot claim source-frame pixel cuts.')
        _check(checks, identity + ':native', 'passed', 'Observed resource-free Brush agrees with its explicit procedural judgment; visual review remains required.')
        size = _vec(brush['imageSize'], ('x', 'y')) if 'imageSize' in brush else None
        return {'brush': size if size and min(size) > 0 else None, 'frame': None, 'slot': _allocation(key, nodes), 'mode': mode}
    is_material = source['kind'] == 'material'
    if is_material:
        from art_materials import CAPABILITIES as MATERIAL_CAPABILITIES, validate_material_source
        material_capabilities = MATERIAL_CAPABILITIES.intersection(capabilities)
        if len(material_capabilities) != 1:
            _fail('capability', 'Material sources require exactly one explicit procedural-ui-material capability version.')
        if mode != 'preserve' or 'nineSlice' in item:
            _fail('material_mode', 'Material evaluation domains support preservation only, never texture pixel cuts.')
        verified = validate_material_source(source, owner, resource, capability=next(iter(material_capabilities)))
        basis = verified['evaluationSize']
        frame = None
        uv_region = brush.get('uVRegion')
        if brush.get('mirroring') != 'NoMirror' or not isinstance(uv_region, dict) or uv_region.get('bIsValid') is not False:
            _fail('material_uv', 'Material Brush must observe NoMirror and an invalid atlas UV override for the full domain.')
        _values(_vec(brush.get('margin'), ('left', 'top', 'right', 'bottom')), [0, 0, 0, 0], 'Material Brush margin')
    else:
        if catalog is None:
            _fail('resource_catalog', 'Resource images require the existing independently validated import catalog.')
        matches = [r for r in catalog['resources'] if r['id'] == source['catalogResourceId']]
        if len(matches) != 1:
            _fail('resource_identity', 'Catalog resource ID must resolve exactly once.')
        record = matches[0]
        source_path = bound_path(source['image'], owner)
        if (source['image']['sha256'] != record['sourceSha256'] or source_path != Path(record['sourcePath']).resolve()
                or resource != _ref(record['brushResourceObject'])):
            _fail('resource_identity', 'Source file, validated import identity and native Brush resource disagree.')
        from PIL import Image
        from art_images import _bounds
        with Image.open(source_path) as image:
            frame = list(image.size)
            alpha = _bounds(image.convert('RGBA'))
        if source['frameSize'] != frame or source['alphaBounds'] != alpha or record['dimensions'] != frame:
            _fail('source_frame', 'Full source frame and alpha bounds must match decoded source pixels and actual import dimensions.')
        if 'atlas' in record and record['atlas']['sourceDimensions'] != frame:
            _fail('source_frame', 'Sprite frame dimensions must match the source; the atlas sheet is not a source frame.')
        basis = frame
    size = _vec(brush.get('imageSize'), ('x', 'y'))
    if min(size) <= 0:
        _fail('brush_size', 'Brush image size must be positive.')
    target, transform = _allocation(key, nodes), _transform_scale(key, nodes)
    if mode == 'preserve':
        if brush.get('drawAs') != 'Image' or brush.get('tiling') != 'NoTile':
            _fail('draw_mode', 'Preservation currently supports an untiled Image Brush only.')
        brush_aspect = (_close(size[0] / basis[0], size[1] / basis[1]) if is_material
                        else _static_resource_aspect_close(size, basis))
        if not brush_aspect:
            _fail('aspect', 'Brush distorts the material evaluation domain.' if is_material else 'Brush distorts the full source frame (alpha bounds cannot replace it).')
        if target is not None and transform is not None:
            allocation_aspect = _close(target[0] * transform[0] / basis[0], target[1] * transform[1] / basis[1])
            # Do not use pixel rounding to excuse anisotropic transforms or a
            # material domain. Exact uniform scale preserves the static ratio.
            if not allocation_aspect and not is_material and transform[0] == transform[1]:
                allocation_aspect = _static_resource_aspect_close(target, basis)
            if not allocation_aspect:
                _fail('aspect', 'Slot allocation and cumulative render transforms distort the material evaluation domain.' if is_material else 'Slot allocation and cumulative render transforms distort the full source frame.')
    elif mode == 'nine-slice':
        if brush.get('drawAs') != 'Box' or brush.get('tiling') != 'NoTile':
            _fail('draw_mode', 'Pixel-cut nine-slicing currently supports an untiled Box Brush only.')
        spec = item.get('nineSlice')
        if spec is None:
            _fail('nine_slice', 'Nine-slice images require explicit source cuts and protected regions.')
        l, t, r, b = spec['cutPixels']
        if l + r >= frame[0] or t + b >= frame[1]:
            _fail('nine_slice', 'Source cuts must leave a positive center region.')
        basis = spec['basisScale']
        _values(size, [v * basis for v in frame], 'Nine-slice Brush/source basis')
        _values(_vec(brush.get('margin'), ('left', 'top', 'right', 'bottom')),
                [l / frame[0], t / frame[1], r / frame[0], b / frame[1]], 'Native normalized nine-slice margin')
        from art_images import _rect
        ids = set()
        for region in spec['protectedRegions']:
            if region['id'] in ids:
                _fail('protected_region', 'Protected region IDs must be unique.')
            ids.add(region['id'])
            x, y, w, h = _rect(region['bounds'], tuple(frame), 'protected source region')
            if ('x' in spec['stretchAxes'] and 'x' in region['preserveAxes'] and x < frame[0] - r and x + w > l
                    or 'y' in spec['stretchAxes'] and 'y' in region['preserveAxes'] and y < frame[1] - b and y + h > t):
                _fail('protected_region', 'A protected graphic, border or shadow intersects an allowed stretch band.')
        if target is not None:
            if target[0] < (l + r) * basis or target[1] < (t + b) * basis:
                _fail('nine_slice_target', 'Target is smaller than protected fixed caps.')
            for axis, name in enumerate(('x', 'y')):
                if name not in spec['stretchAxes'] and not _close(target[axis], size[axis]):
                    _fail('stretch_axis', 'Target changes an axis not authorized for stretching.')
        if transform is not None and not _close(transform[0], transform[1]):
            _fail('nine_slice_transform', 'Nonuniform cumulative transform distorts protected nine-slice graphics.')
    elif mode == 'no-draw':
        if brush.get('drawAs') != 'NoDrawType':
            _fail('draw_mode', 'No-draw judgment requires native NoDrawType even when a resource is retained.')
    elif mode != 'stretch':
        _fail('draw_mode', 'Unsupported resource image judgment.')
    if mode != 'nine-slice' and 'nineSlice' in item:
        _fail('nine_slice', 'Pixel cuts are only meaningful for nine-slice judgments.')
    _check(checks, identity + ':native', 'passed',
           'Saved UI Material, official graph/property evidence and native Brush/evaluation domain agree; this is not measured geometry.' if is_material
           else 'Source identity, full frame, alpha bounds and observed Brush configuration agree; this is not measured geometry.')
    if mode in ('preserve', 'nine-slice'):
        pending = phase == 'actual' or target is None or transform is None
        _check(checks, identity + ':geometry', 'pending' if pending else 'passed',
               'Actual Widget geometry is unavailable; configuration arithmetic cannot prove rendered dimensions.' if phase == 'actual'
               else ('Static allocation/transform proof is incomplete; actual layout evidence is required.' if pending
                     else 'Narrow static allocation/transform arithmetic agrees; no actual geometry is claimed.'))
    return {'brush': size, 'frame': frame, 'slot': target, 'mode': mode,
            **({'evaluationSize': basis} if is_material else {})}


def validate_presentation(request, decisions, snapshot, request_path, decisions_path, *, phase='planned'):
    """Return deterministic checks/issues, or reject a concrete inconsistency.

    An opt-in plan can remain executable with pending *actual geometry*, but
    unresolved art judgments prevent execution. Actual checks never infer a
    measured size from a proposed rectangle or from native Slot fields.
    """
    if phase not in ('planned', 'actual'):
        raise ValueError('Unsupported presentation check phase')
    validate(request, 'request')
    validate(decisions, 'decisions')
    opted = enabled(request)
    if not opted:
        if 'presentationReview' in decisions:
            _fail('capability', 'Presentation review requires explicit presentation-review/1 capability.')
        return {'checks': [], 'issues': []}
    if 'presentationReview' not in decisions:
        _fail('coverage', 'Opt-in requests require a complete presentationReview.')
    review = decisions['presentationReview']
    # The planner has already checked accepted source revision, before-state and
    # operation scope. Final coverage excludes only those explicit removals.
    removed = {(d['operation']['assetPath'], d['operation']['widgetName']) for d in decisions['decisions']
               if d['operation']['kind'] == 'remove-widget' and d['resolution'] != 'unresolved'
               and (d['resolution'] != 'confirmed' or d.get('confirmation'))}
    nodes, scoped = _scope_nodes(request, snapshot, removed)
    from art_delegation import delegated_choices
    delegated = delegated_choices(request, request_path)
    checks, issues, records, image_values = [], [], {}, {}
    catalog = None
    if any(i['source']['kind'] == 'resource' for i in review['images']):
        if 'resourceCatalog' not in request:
            _fail('resource_catalog', 'Bind a verified existing import catalog for resource images.')
        from art_resources import validate_catalog
        catalog = validate_catalog(bound_path(request['resourceCatalog'], request_path))
    for group, classes in (('images', IMAGE_CLASSES), ('texts', TEXT_CLASSES)):
        expected = {key for key, node in scoped.items() if node['classPath'] in classes}
        found = set()
        for item in review[group]:
            key = (item['assetPath'], item['widgetName'])
            if key in found or key not in expected:
                _fail('coverage', 'Presentation judgments must cover each scoped image/text exactly once, with the correct class.')
            found.add(key)
            records[key] = item
            _evidence(item, request, request_path)
            if item['resolution'] == 'unresolved':
                issues.append({'code': 'presentation.unresolved', 'message': item['reason'], 'assetPath': key[0], 'widgetName': key[1]})
            if group == 'images':
                if item['resolution'] == 'confirmed' and not item.get('confirmation'):
                    _fail('confirmation', 'Confirmed image decisions require appearance confirmation, not method approval.')
                image_values[key] = _image(item, nodes[key], nodes, catalog, decisions_path, checks, phase, request.get('capabilities', ()))
                continue
            is_delegated = item['resolution'] == 'delegated'
            if is_delegated:
                from art_delegation import check_choice
                check_choice(item, delegated)
                _check(checks, key[0] + ':' + key[1] + ':delegated-choice', 'passed', 'The coordinator selected these exact appearance parameters under the original scoped grant; source confidence is preserved and actual local visual verification is still mandatory.')
            confirmations = item['confirmations']
            kinds = [c['scope'] for c in confirmations]
            if len(kinds) != len(set(kinds)):
                _fail('confirmation', 'Text confirmation scopes must be unique.')
            if item['resolution'] == 'confirmed' and not confirmations:
                _fail('confirmation', 'Confirmed text needs explicit effect/appearance confirmation.')
            for field, confirm_scope in (('effectTypeConfidence', 'effect-type'), ('parameterConfidence', 'appearance-parameters')):
                if item[field] != 'high' and confirm_scope not in kinds and not is_delegated:
                    issues.append({'code': 'presentation.text_ambiguous', 'message': 'Local text evidence requires ' + confirm_scope + ' annotation: ' + item['reason'], 'assetPath': key[0], 'widgetName': key[1]})
            if item['effect'] == 'none' and item['effectTypeConfidence'] == 'unknown' and 'effect-type' not in kinds:
                _fail('text_unknown_none', 'Unknown effect type must be recorded as unknown, never none.')
            if item['effect'] == 'unknown':
                issues.append({'code': 'presentation.text_unknown', 'message': item['reason'], 'assetPath': key[0], 'widgetName': key[1]})
            effect = item['effect']
            outline, shadow = item['outline'], item['shadow']
            has_outline = outline['size'] > 0 and outline['color'][3] > 0
            has_shadow = shadow['color'][3] > 0
            if effect != 'unknown' and (has_outline, has_shadow) != {
                    'none': (False, False), 'outline': (True, False), 'shadow': (False, True), 'outline-and-shadow': (True, True)}[effect]:
                _fail('text_effect', 'Text effect label conflicts with explicit outline/shadow values.')
            native = nodes[key]['properties']
            native_outline = native.get('font', {}).get('outlineSettings', {})
            _values([native_outline.get('outlineSize')], [outline['size']], 'Native outline size')
            _values(_vec(native_outline.get('outlineColor'), ('r', 'g', 'b', 'a')), outline['color'], 'Native outline color')
            _values(_vec(native.get('shadowOffset'), ('x', 'y')), shadow['offset'], 'Native shadow offset')
            _values(_vec(native.get('shadowColorAndOpacity'), ('r', 'g', 'b', 'a')), shadow['color'], 'Native shadow color')
            _check(checks, key[0] + ':' + key[1] + ':text-native', 'passed', 'Explicit outline/shadow values match native properties; parameter presence is not visual similarity or identification confidence.')
        if found != expected:
            _fail('coverage', 'Every scoped image/text, including unchanged and collapsed nodes, needs an explicit judgment.')
    families = {}
    for family in review['families']:
        if family['id'] in families:
            _fail('family', 'Family IDs must be unique.')
        members = [(m['assetPath'], m['widgetName']) for m in family['members']]
        if len(set(members)) != len(members) or any(key not in image_values or records[key]['familyId'] != family['id'] for key in members):
            _fail('family', 'Family members must be explicit reviewed images with reciprocal familyId.')
        families[family['id']] = set(members)
        exceptions = {}
        for exception in family['exceptions']:
            key = (exception['assetPath'], exception['widgetName'])
            identity = (key, exception['comparison'])
            if key not in members[1:] or exception['comparison'] not in family['comparisons'] or identity in exceptions:
                _fail('family_exception', 'Each exception must name one non-baseline family member and one declared comparison exactly once.')
            if not exception['reason'].strip():
                _fail('family_exception', 'Family differences need a concrete nonempty reason.')
            value = exception['expectedValue']
            exceptions[identity] = value if isinstance(value, (list, str)) else [value]
        for comparison in family['comparisons']:
            values = [_family_value(image_values[key], comparison) for key in members]
            for key, value in zip(members[1:], values[1:]):
                target = exceptions.get((key, comparison), values[0])
                if (key, comparison) in exceptions and values[0] is not None and _same_family_value(target, values[0]):
                    _fail('family_exception', 'An exception equal to the baseline is unused; remove it.')
                if value is not None and target is not None and not _same_family_value(value, target):
                    _fail('family_mismatch', 'Same-family ' + comparison + ' differs without an exact matching per-member exception.')
            pending = any(v is None for v in values) or phase == 'actual' and comparison.startswith('slot-')
            _check(checks, 'family:' + family['id'] + ':' + comparison, 'pending' if pending else 'passed',
                   'Requested family comparison lacks complete actual/static geometry; explicit exceptions do not create evidence.' if pending
                   else 'Explicit same-family native configuration and any exact member differences agree.')
    for key, item in records.items():
        if key in image_values and item['familyId'] is not None and key not in families.get(item['familyId'], set()):
            _fail('family', 'Image familyId must resolve to explicit reciprocal membership.')
    for index, issue in enumerate(issues):
        _check(checks, 'judgment:' + str(index), 'pending', issue['message'])
    return {'checks': checks, 'issues': issues}
