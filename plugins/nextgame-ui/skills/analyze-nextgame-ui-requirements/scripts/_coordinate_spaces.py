"""Trial source/target coordinate contracts; never substitutes for actual geometry."""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

CAPABILITY = 'source-target-coordinates/1'
SLOT_KEYS = ('parent', 'anchor', 'zOrder', 'slotLayout', 'overlaySlot', 'flowSlot', 'scrollSlot', 'buttonSlot', 'sizeBoxSlot', 'sizeBoxConstraints', 'adaptiveLayout', 'fullHeight', 'contentDrivenSize')
CORE_KEYS = ('assetId', 'layoutNodeKey', 'subjectRefs', 'coordinateSpace', 'rectPixels', 'slotContract')
SCHEMA = Path(__file__).resolve().parent.parent / 'assets/ui-requirement-spec.schema.json'

def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def error(code, message, path='$.coordinateContract'):
    return {'code': 'coordinate.' + code, 'path': path, 'message': message}

def _numbers(value, count):
    return isinstance(value, list) and len(value) == count and all(type(x) in (int, float) and math.isfinite(x) for x in value)

def close(left, right, tolerance=1e-6):
    return _numbers(left, len(right)) and all(abs(a-b) <= tolerance for a,b in zip(left,right))

def _resolve(base, path):
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    if base is None:
        raise ValueError('Relative coordinate evidence requires the containing contract path.')
    return (Path(base).parent / candidate).resolve()

def _bound(binding, base, *, json_value=True):
    if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
        raise ValueError('Coordinate evidence requires a file path and SHA-256.')
    path = _resolve(base, binding['path'])
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != binding.get('sha256'):
        raise ValueError('Coordinate evidence file SHA-256 mismatch: ' + str(path))
    return (json.loads(data.decode('utf-8-sig')) if json_value else data), path

def _closed(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(label + ' has missing or unsupported fields.')

def slot_projection(node):
    return {k: node[k] for k in SLOT_KEYS if k in node}

def target_core(target):
    return {k: target[k] for k in CORE_KEYS}

def target_record(requirement, asset_id, node_key, subject_ref=None):
    records = [r for r in requirement.get('coordinateContract', {}).get('targets', []) if r.get('assetId') == asset_id and r.get('layoutNodeKey') == node_key and (subject_ref is None or subject_ref in r.get('subjectRefs', []))]
    return records[0] if len(records) == 1 else None

def expected_rect(requirement, asset_id, node_key, subject_ref, legacy):
    if 'coordinateContract' not in requirement:
        return legacy
    target = target_record(requirement, asset_id, node_key, subject_ref)
    asset = next((a for a in requirement.get('assetPlan', []) if a.get('id') == asset_id), {})
    size = asset.get('referenceSize')
    if target is None or not _numbers(size, 2) or min(size) <= 0:
        return None
    rect = target['rectPixels']
    return [rect[0]/size[0], rect[1]/size[1], rect[2]/size[0], rect[3]/size[1]]

def _registered_rect(binding, base, contract):
    doc, path = _bound(binding, base)
    if doc.get('kind') != 'source-whole-frame-registration' or type(doc.get('version')) is not int or doc.get('version') != 1:
        raise ValueError('Unsupported whole-frame registration format.')
    reference = doc.get('reference', {})
    _bound(reference, path, json_value=False)
    _bound(doc.get('script'), path, json_value=False)
    if reference.get('sha256') != contract['sourceSha256'] or reference.get('size') != contract['sourceSize']:
        raise ValueError('Whole-frame registration must bind the original source image and dimensions.')
    records = [r for r in doc.get('results', []) if r.get('id') == binding['recordKey']]
    if len(records) != 1 or records[0].get('status') != 'source-registration-supported-by-low-residual':
        raise ValueError('Whole-frame registration requires one supported source observation.')
    record = records[0]
    _bound(record.get('source'), path, json_value=False)
    best = record.get('best', {})
    position, size = best.get('sourceScreenshotFramePosition'), best.get('resizedFrameSize')
    if not _numbers(position, 2) or not _numbers(size, 2) or min(size) <= 0:
        raise ValueError('Whole-frame registration requires finite source position and full frame size.')
    return position + size

def _derived(target, base, request_id):
    proof, proof_path = _bound(target['derivationEvidence'], base)
    _closed(proof, ('kind','version','requestId','boundary','script','inputs','records'), 'Design derivation')
    if type(proof['version']) is not int:
        raise ValueError('Design derivation version must be integer 1.')
    if (proof['kind'], proof['version'], proof['requestId'], proof['boundary']) != ('coordinate-design-derivation',1,request_id,'design-derived-not-source-transform-proof'):
        raise ValueError('Design derivation must identify this request and its non-measurement boundary.')
    _bound(proof['script'], proof_path, json_value=False)
    if not isinstance(proof['inputs'], list) or not proof['inputs']:
        raise ValueError('Design derivation requires bound inputs.')
    for binding in proof['inputs']:
        _closed(binding, ('path','sha256'), 'Derivation input')
        _bound(binding, proof_path, json_value=False)
    core = target_core(target)
    records = [r for r in proof['records'] if r.get('assetId') == target['assetId'] and r.get('layoutNodeKey') == target['layoutNodeKey']]
    if len(records) != 1 or records[0] != core:
        raise ValueError('Design derivation must contain this exact target geometry and Slot record.')
    review, _ = _bound(target['reviewEvidence'], base)
    _closed(review, ('kind','version','requestId','status','reviewer','reviewedAt','derivationSha256','records'), 'Design review')
    if type(review['version']) is not int:
        raise ValueError('Design review version must be integer 1.')
    if (review['kind'], review['version'], review['requestId'], review['status'], review['derivationSha256']) != ('coordinate-design-review',1,request_id,'passed',target['derivationEvidence']['sha256']):
        raise ValueError('Independent design review must bind this request and exact derivation file.')
    if not isinstance(review['reviewer'], str) or not review['reviewer'].strip():
        raise ValueError('Design review must name the actual reviewer.')
    when = datetime.fromisoformat(review['reviewedAt'].replace('Z','+00:00'))
    if when.tzinfo is None:
        raise ValueError('Design review requires an actual timezone-aware review timestamp.')
    expected = {'assetId':target['assetId'],'layoutNodeKey':target['layoutNodeKey'],'recordSha256':canonical_sha(core)}
    matching = [r for r in review['records'] if r.get('assetId') == target['assetId'] and r.get('layoutNodeKey') == target['layoutNodeKey']]
    if matching != [expected]:
        raise ValueError('Independent design review must approve this exact target record once.')

def validate_contract(requirement, *, spec_path=None):
    if 'coordinateContract' not in requirement:
        return []
    contract = requirement['coordinateContract']
    try:
        from _contract_common import validate_schema_instance
        schema = json.loads(SCHEMA.read_text(encoding='utf-8-sig'))
        sub = {'$defs':schema['$defs'], '$ref':'#/$defs/coordinateContract'}
        problems = validate_schema_instance(contract, sub, path='$.coordinateContract')
        if problems:
            return problems
        sources = {s['id']:s for s in requirement.get('sources', [])}
        from validate_requirement_spec import build_requirement_index
        entities = {e['id']:e for _, _, e in build_requirement_index(requirement)['entities']}
        evidence = {e['id']:e for e in requirement.get('evidence', [])}
        claims = {c['id']:c for c in requirement.get('claims', [])}
        accepted = set(requirement.get('reviewGate', {}).get('acceptedClaimIds', []))
        assets = {a['id']:a for a in requirement.get('assetPlan', [])}
        source = sources.get(contract['sourceId'], {})
        if source.get('kind') != 'image' or source.get('dimensions') != contract['sourceSize'] or source.get('contentSha256') != contract['sourceSha256']:
            raise ValueError('Coordinate source must match the original image source dimensions and SHA-256.')
        _bound({'path':source.get('path'),'sha256':contract['sourceSha256']}, spec_path, json_value=False)
        observations, _ = _bound(contract['sourceObservations'], spec_path)
        from _contract_common import compute_approved_content_sha256
        original_review = observations.get('reviewGate', {})
        if observations.get('version') not in ('0.1', '0.2') or original_review.get('status') != 'accepted' or original_review.get('approvedContentSha256') != compute_approved_content_sha256(observations):
            raise ValueError('Source observations must preserve an accepted Requirement content hash.')
        if observations.get('requestId') != requirement.get('requestId') or 'coordinateContract' in observations:
            raise ValueError('Source observations must bind the original same-request pre-coordinate Requirement snapshot.')
        original_sources = {s['id']:s for s in observations.get('sources', [])}
        if any(original_sources.get(contract['sourceId'], {}).get(k) != source.get(k) for k in ('kind','dimensions','contentSha256')):
            raise ValueError('Original coordinate image source identity/dimensions must remain unchanged.')
        original_evidence = {e['id']:e for e in observations.get('evidence', [])}
        for kind in ('regions','elements'):
            for original in observations.get('uiModel',{}).get(kind,[]):
                current = entities.get(original['id'])
                if current is None or any((k in current) != (k in original) or current.get(k) != original.get(k) for k in ('bounds','geometryEvidenceId')):
                    raise ValueError('Existing source observation identity/bounds/evidence must remain unchanged: ' + original['id'])
                geometry_key = original.get('geometryEvidenceId')
                if geometry_key is not None and (geometry_key not in original_evidence or evidence.get(geometry_key) != original_evidence[geometry_key]):
                    raise ValueError('Existing geometry evidence must remain unchanged: ' + geometry_key)

        frame, size, scale = contract['contentFrame'], contract['targetSize'], contract['uniformScale']
        if not _numbers(frame,4) or min(frame[2:]) <= 0 or min(frame[:2]) < 0 or frame[0]+frame[2] > contract['sourceSize'][0] or frame[1]+frame[3] > contract['sourceSize'][1]:
            raise ValueError('Content frame must be a positive rectangle inside the original source image.')
        if not close([frame[2]*scale, frame[3]*scale], size):
            raise ValueError('Both content-frame axes must use the same declared uniform scale into the target canvas.')
        def refs(record, subjects):
            if any(e not in evidence for e in record['evidenceIds']):
                raise ValueError('Coordinate evidence reference is unknown.')
            if any(c not in accepted or claims.get(c,{}).get('status') != 'accepted' for c in record['claimIds']):
                raise ValueError('Coordinate decisions require accepted and reviewed claims.')
            if subjects and any(not any(s in claims[c].get('subjectRefs',[]) for c in record['claimIds']) for s in subjects):
                raise ValueError('Accepted coordinate claims must cover every target subject.')
        refs(contract, [])
        seen=set()
        for target in contract['targets']:
            key=(target['assetId'],target['layoutNodeKey'])
            if key in seen:
                raise ValueError('Duplicate coordinate target asset/node key.')
            seen.add(key)
            if any(s not in entities for s in target['subjectRefs']):
                raise ValueError('Coordinate target subjects must name existing canonical Requirement entities.')
            refs(target,target['subjectRefs'])
            asset = assets.get(target['assetId'], {})
            reference = asset.get('referenceSize')
            rect = target['rectPixels']
            if not _numbers(reference,2) or not _numbers(rect,4) or min(rect[2:]) <= 0 or min(rect[:2]) < -1e-6 or rect[0]+rect[2] > reference[0]+1e-6 or rect[1]+rect[3] > reference[1]+1e-6:
                raise ValueError('Target design rect must fit its accepted asset reference size.')
            if (target['coordinateSpace'] == 'screen-design') != (asset.get('assetKind') == 'screen'):
                raise ValueError('Coordinate space must match the accepted screen/local asset kind.')
            if asset.get('assetKind') == 'screen' and reference != size:
                raise ValueError('Screen asset reference size must equal the coordinate target canvas.')
            if target['mode'] == 'source-transform':
                if 'wholeFrameRegistration' in target:
                    raw = _registered_rect(target['wholeFrameRegistration'], spec_path, contract)
                else:
                    ent = entities.get(target['sourceRef'], {})
                    ev = evidence.get(target['geometryEvidenceId'], {})
                    if target['sourceRef'] not in target['subjectRefs'] or ent.get('geometryEvidenceId') != target['geometryEvidenceId'] or ev.get('sourceId') != contract['sourceId'] or ev.get('sourceDimensions') != contract['sourceSize'] or ev.get('measurementMethod') != 'image-measurement':
                        raise ValueError('Source transform must bind the unchanged entity image measurement and original source frame.')
                    raw=ev.get('pixelBounds')
                    if not _numbers(raw,4):
                        raise ValueError('Source transform needs finite measured raw pixelBounds.')
                    normalized=[raw[0]/contract['sourceSize'][0],raw[1]/contract['sourceSize'][1],raw[2]/contract['sourceSize'][0],raw[3]/contract['sourceSize'][1]]
                    if not close(ent.get('bounds'),normalized,0.003) or not close(ev.get('bounds'),normalized,0.003):
                        raise ValueError('Source observation bounds drifted from original pixel measurements.')
                if min(raw[:2]) < 0 or min(raw[2:]) <= 0 or raw[0]+raw[2] > contract['sourceSize'][0] or raw[1]+raw[3] > contract['sourceSize'][1]:
                    raise ValueError('Measured source rectangle is outside the original image.')
                transformed=[(raw[0]-frame[0])*scale,(raw[1]-frame[1])*scale,raw[2]*scale,raw[3]*scale]
                if not close(rect,transformed):
                    raise ValueError('Target rect differs from the declared content-frame uniform transform.')
            else:
                _derived(target,spec_path,requirement.get('requestId'))
        return []
    except (ValueError, TypeError, KeyError, OSError, AttributeError, OverflowError) as exc:
        return [error('invalid',str(exc))]

def validate_layout_binding(layout, *, spec_path=None, requirement=None, requirement_path=None):
    binding = layout.get('coordinateBinding')
    if binding is None:
        return [] if not isinstance(requirement,dict) or 'coordinateContract' not in requirement else [error('layout.binding','Opt-in Requirement requires an explicit Layout coordinateBinding.')]
    try:
        _closed(binding,('capability','version','contractSha256','assetId','requirement'),'Layout coordinate binding')
        bound, path = _bound(binding['requirement'], spec_path)
        if requirement is not None and bound != requirement:
            raise ValueError('Layout coordinate binding differs from the current Requirement.')
        requirement=bound
        errors=validate_contract(requirement,spec_path=path)
        if errors:return errors
        contract=requirement.get('coordinateContract')
        if not contract or binding['capability'] != CAPABILITY or type(binding['version']) is not int or binding['version'] != 1 or binding['contractSha256'] != canonical_sha(contract):
            raise ValueError('Layout coordinate binding must exactly match the opt-in Requirement contract.')
        from _contract_common import compute_approved_content_sha256
        if requirement.get('reviewGate',{}).get('approvedContentSha256') != compute_approved_content_sha256(requirement):
            raise ValueError('Coordinate lowering requires the unchanged accepted Requirement content hash.')
        if requirement.get('reviewGate',{}).get('status') != 'accepted':
            raise ValueError('Coordinate lowering requires the accepted Requirement.')
        asset=next((a for a in requirement.get('assetPlan',[]) if a.get('id') == binding['assetId']),{})
        expected_path=layout.get('asset',{}).get('folder','').rstrip('/') + '/' + layout.get('asset',{}).get('name','')
        if asset.get('assetPath') != expected_path or asset.get('referenceSize') != layout.get('referenceSize'):
            raise ValueError('Layout coordinate asset identity/reference size mismatch.')
        targets={r['layoutNodeKey']:r for r in contract['targets'] if r['assetId'] == binding['assetId']}
        nodes=layout.get('nodes',[])
        if len(nodes) != len(targets) or {n.get('id') for n in nodes} != set(targets):
            raise ValueError('Every Layout node requires exactly one accepted target geometry record.')
        for node in nodes:
            target=targets[node['id']]
            rect=expected_rect(requirement,binding['assetId'],node['id'],None,None)
            if not close(node.get('rect'),rect,1e-9) or slot_projection(node) != target['slotContract']:
                raise ValueError('Layout rect/Slot contract differs from its accepted target geometry: '+node['id'])
        return []
    except (ValueError,TypeError,KeyError,OSError,AttributeError) as exc:
        return [error('layout.invalid',str(exc),'$.coordinateBinding')]

def validate_bundle_binding(bundle,requirement,*,bundle_path=None):
    contract=requirement.get('coordinateContract')
    binding=bundle.get('coordinateBinding')
    if contract is None:
        if binding is not None:
            return [error('bundle.unbound','Bundle coordinate binding requires the Requirement opt-in.')]
        if bundle_path is not None:
            for asset in bundle.get('assets', []) if isinstance(bundle.get('assets'), list) else []:
                if not isinstance(asset,dict) or not asset.get('layoutSpecPath'):
                    continue
                try:
                    layout=json.loads(_resolve(bundle_path,asset['layoutSpecPath']).read_text(encoding='utf-8-sig'))
                except (OSError, ValueError):
                    continue  # Existing linked-file validation reports unreadable legacy layouts.
                if 'coordinateBinding' in layout:
                    return [error('bundle.unbound','An opt-in Layout cannot be attached to a legacy Requirement.')]
        return []
    try:
        expected={'capability':CAPABILITY,'version':1,'contractSha256':canonical_sha(contract)}
        targets={(r['assetId'],r['layoutNodeKey']):r for r in contract.get('targets',[])}
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return [error('bundle.contract',str(exc))]
    errors=[]
    if binding != expected or not isinstance(binding,dict) or type(binding.get('version')) is not int:
        errors.append(error('bundle.binding','Bundle must bind the exact accepted coordinate contract.'))
    assets={a.get('id'):a for a in bundle.get('assets',[])}
    for target in targets.values():
        matching_assets=[a for a in assets.values() if a.get('assetPlanId') == target['assetId']]
        if len(matching_assets) != 1:
            errors.append(error('bundle.asset','Coordinate target requires one exact assetPlan identity.'))
            continue
        asset=matching_assets[0]
        maps=[m for m in bundle.get('nodeMappings',[]) if m.get('assetId') == asset.get('id') and m.get('layoutNodeId') == target['layoutNodeKey']]
        if len(maps) != 1 or set(maps[0].get('requirementRefs',[])) != set(target['subjectRefs']):
            errors.append(error('bundle.subjects','Coordinate target subjects must exactly match the Bundle node mapping.'))
    if bundle_path is not None:
        for asset in assets.values():
            layout_ref=asset.get('layoutSpecPath')
            if layout_ref:
                try:
                    path=_resolve(bundle_path,layout_ref)
                    layout=json.loads(path.read_text(encoding='utf-8-sig'))
                    errors.extend(validate_layout_binding(layout,spec_path=path,requirement=requirement))
                except (OSError,ValueError) as exc:
                    errors.append(error('bundle.layout',str(exc)))
    return errors
