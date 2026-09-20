"""Closed procedural-ui-material/1 and /2 evidence, read-only and opt-in.

This validates captured official calls and current saved bytes; it does not run
Unreal, create evidence, certify Custom HLSL semantics, or infer rendered geometry.
Version 1 deliberately supports one UV -> Custom opacity / constant RGB graph.
Version 2 supports one UV feeding separate Custom RGB and opacity expressions.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from art_common import ArtError, aware_time, bound_path, canonical, digest, load_json, validate

CAPABILITY = 'procedural-ui-material/1'
MULTICOLOR_CAPABILITY = 'procedural-ui-material/2'
CAPABILITIES = frozenset((CAPABILITY, MULTICOLOR_CAPABILITY))
MATERIAL = 'editor_toolset.toolsets.material.MaterialTools'
OBJECT = 'editor_toolset.toolsets.object.ObjectTools'
ASSET = 'editor_toolset.toolsets.asset.AssetTools'
UV = '/Script/Engine.MaterialExpressionTextureCoordinate'
CUSTOM = '/Script/Engine.MaterialExpressionCustom'
COLOR = '/Script/Engine.MaterialExpressionConstant3Vector'
MATERIAL_PROPERTIES = ('materialDomain', 'blendMode', 'twoSided', 'numCustomizedUVs')
EXPRESSION_PROPERTIES = {
    UV: ('coordinateIndex', 'uTiling', 'vTiling', 'unMirrorU', 'unMirrorV'),
    CUSTOM: ('code', 'outputType', 'inputs', 'additionalOutputs', 'additionalDefines', 'includeFilePaths'),
    COLOR: ('constant',),
}


def _fail(code, message):
    raise ArtError('material.' + code, message)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _time(value):
    try:
        return aware_time(value)
    except (TypeError, ValueError) as exc:
        _fail('time', 'Official material call timestamps must be valid and timezone-aware: ' + str(exc))


def _native(value, fields):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                _fail('properties', 'Duplicate native property key: ' + key)
            result[key] = item
        return result
    try:
        value = json.loads(value, object_pairs_hook=pairs)
        canonical(value)
    except (TypeError, ValueError) as exc:
        _fail('properties', 'Native get_properties must return finite JSON: ' + str(exc))
    if not isinstance(value, dict) or set(value) != set(fields):
        _fail('properties', 'Native readback must cover exactly the queried properties.')
    return value


def validate_material_source(source, owner, resource, *, capability=CAPABILITY):
    """Revalidate a material source on each plan/apply/final presentation check.

    ``owner`` is the decisions file; ``resource`` is the observed canonical
    package path from Brush.resourceObject, not a desired operation value.
    Callers must pass the exact request capability and enforce preserve-aspect.
    The default remains /1 for existing callers; it never infers /2 from evidence.
    """
    if not isinstance(capability, str) or capability not in CAPABILITIES:
        _fail('capability', 'An explicit supported procedural material capability is required.')
    version = 2 if capability == MULTICOLOR_CAPABILITY else 1
    validate(source, 'presentationMaterialSource')
    if resource != source['materialPath']:
        _fail('resource', 'Actual Brush material must exactly match the declared material path.')
    if any(not _number(v) or v <= 0 for v in source['evaluationSize']):
        _fail('evaluation_size', 'Evaluation size is a finite positive domain, never texture pixels.')
    evidence_path = bound_path(source['evidence'], owner)
    evidence = validate(load_json(evidence_path),
                        'proceduralMaterialReadbackV2' if version == 2 else 'proceduralMaterialReadback')
    if evidence['materialPath'] != source['materialPath']:
        _fail('identity', 'Bound evidence belongs to another material.')
    project_file = bound_path(evidence['projectFile'], evidence_path)
    if project_file.suffix.lower() != '.uproject':
        _fail('project', 'Bind the explicit Unreal project file.')
    content = (project_file.parent / 'Content').resolve()
    saved_file = bound_path(evidence['savedFile'], evidence_path)
    expected = (content / (source['materialPath'].removeprefix('/Game/') + '.uasset')).resolve()
    if not expected.is_relative_to(content) or saved_file != expected or not saved_file.stat().st_size:
        _fail('saved_file', 'Saved bytes must be the exact nonempty material package under the bound project Content.')

    receipt_path = bound_path(evidence['executionReceipt'], evidence_path)
    receipt = load_json(receipt_path)
    if (not isinstance(receipt, dict) or receipt.get('kind') != 'task-native-material-execution'
            or type(receipt.get('version')) is not int or receipt['version'] != 1
            or 'currentOperation' not in receipt or not isinstance(receipt.get('savedFile'), str)
            or not isinstance(receipt.get('records'), list)
            or receipt.get('status') != 'completed' or receipt.get('currentOperation') is not None
            or receipt.get('savedFileSha256') != evidence['savedFile']['sha256']
            or Path(receipt.get('savedFile', '')).resolve() != saved_file):
        _fail('execution_receipt', 'Bind the completed native-material execution/1 receipt for these exact saved bytes.')
    calls = evidence['calls']
    for tool, index in (('recompile', 0), ('save_assets', 1)):
        records = [r for r in receipt.get('records', []) if isinstance(r, dict) and r.get('tool') == tool]
        if len(records) != 1:
            _fail('execution_receipt', 'Compile/save must each resolve once in the bound original execution receipt.')
        row = records[0]
        projected = {k: row.get(k) for k in ('toolset', 'tool', 'arguments', 'result', 'completedAt')}
        projected['startedAt'] = row.get('beganAt')
        if calls[index] != projected:
            _fail('execution_receipt', 'Sidecar compile/save must be an exact projection of original official receipt rows.')
    capture_time = _time(evidence['capturedAt'])
    previous = None
    indexed = {}
    for index, call in enumerate(calls):
        start, end = _time(call['startedAt']), _time(call['completedAt'])
        if end < start or (previous is not None and start < previous) or end > capture_time:
            _fail('time', 'Material receipts must be sequential, completed and no later than capture.')
        previous = end
        key = (call['toolset'], call['tool'], canonical(call['arguments']))
        if key in indexed:
            _fail('call', 'Duplicate official material call identity.')
        indexed[key] = (index, call['result'])
    consumed = set()

    def take(toolset, tool, arguments):
        key = (toolset, tool, canonical(arguments))
        if key not in indexed:
            _fail('call', 'Missing exact official call: ' + tool)
        consumed.add(key)
        index, result = indexed[key]
        return index, result

    def read(toolset, tool, arguments):
        index, result = take(toolset, tool, arguments)
        if index <= 1:
            _fail('order', 'Graph/property evidence must be collected after compile and save.')
        return result['returnValue']

    package = source['materialPath']
    material_ref = {'refPath': package + '.' + package.rsplit('/', 1)[-1]}
    compile_index, _ = take(MATERIAL, 'recompile', {'material_or_function': material_ref})
    save_index, _ = take(ASSET, 'save_assets', {'asset_paths': [package]})
    if compile_index != 0 or save_index != 1:
        _fail('order', 'Successful exact-material compile then save must precede independent readback.')
    if read(ASSET, 'load_asset', {'asset_path': package}) != material_ref:
        _fail('identity', 'Official load_asset must return the exact saved material object.')
    if read(OBJECT, 'get_class', {'instance': material_ref}) != {'refPath': '/Script/Engine.Material'}:
        _fail('class', 'This capability accepts a saved native Material, not an instance, texture or guessed class.')
    material_properties = _native(read(OBJECT, 'get_properties', {
        'instance': material_ref, 'properties': list(MATERIAL_PROPERTIES)}), MATERIAL_PROPERTIES)
    if (material_properties['materialDomain'] != 'MD_UI' or material_properties['blendMode'] != 'BLEND_Translucent'
            or material_properties['twoSided'] is not True or type(material_properties['numCustomizedUVs']) is not int
            or material_properties['numCustomizedUVs'] != 0):
        _fail('domain', 'Actual material must be UI/Translucent/two-sided with no customized UV inputs.')
    expressions = read(MATERIAL, 'get_expressions', {'material_or_function': material_ref})
    by_class, graph = {}, []
    for expression in expressions:
        path = expression['refPath']
        if not path.startswith(material_ref['refPath'] + ':') or not path.partition(':')[2] or ':' in path.partition(':')[2]:
            _fail('graph', 'Every expression must be an owned subobject of this exact material.')
        class_path = read(OBJECT, 'get_class', {'instance': expression})['refPath']
        if version == 1:
            if class_path not in EXPRESSION_PROPERTIES or class_path in by_class:
                _fail('class', 'Version 1 needs exactly one native TextureCoordinate, Custom and Constant3Vector.')
        elif class_path not in (UV, CUSTOM) or (class_path == UV and class_path in by_class):
            _fail('class', 'Version 2 needs one native TextureCoordinate and two native Custom expressions.')
        fields = EXPRESSION_PROPERTIES[class_path]
        properties = _native(read(OBJECT, 'get_properties', {'instance': expression, 'properties': list(fields)}), fields)
        inputs = read(MATERIAL, 'get_expression_inputs', {'material_or_function': material_ref, 'expression': expression})
        outputs = read(MATERIAL, 'get_expression_output_names', {'expression': expression})
        row = {'ref': expression, 'classPath': class_path, 'properties': properties, 'inputs': inputs, 'outputs': outputs}
        by_class[class_path] = row
        graph.append(row)
    if version == 1:
        if set(by_class) != set(EXPRESSION_PROPERTIES):
            _fail('graph', 'The entire three-expression material graph must be covered.')
        uv, custom, color = (by_class[c] for c in (UV, CUSTOM, COLOR))
        custom_rows = [(custom, 'CMOT_Float1')]
    else:
        customs = [row for row in graph if row['classPath'] == CUSTOM]
        if set(by_class) != {UV, CUSTOM} or len(graph) != 3 or len(customs) != 2:
            _fail('graph', 'The entire UV and two-Custom graph must be covered.')
        if any(row['properties']['outputType'] not in ('CMOT_Float1', 'CMOT_Float3') for row in customs):
            _fail('custom', 'Version 2 Custom output types must be scalar opacity or RGB.')
        by_output = {row['properties']['outputType']: row for row in customs}
        if set(by_output) != {'CMOT_Float1', 'CMOT_Float3'}:
            _fail('custom', 'Version 2 requires exactly one scalar opacity and one RGB Custom output.')
        uv, custom, color = by_class[UV], by_output['CMOT_Float1'], by_output['CMOT_Float3']
        custom_rows = [(custom, 'CMOT_Float1'), (color, 'CMOT_Float3')]
        if any(len(row['outputs']) != 1 for row in graph):
            _fail('wiring', 'Version 2 expressions must each have exactly one default output.')
    p = uv['properties']
    if (type(p['coordinateIndex']) is not int or p['coordinateIndex'] != 0
            or any(not _number(p[k]) or p[k] != 1 for k in ('uTiling', 'vTiling'))
            or p['unMirrorU'] is not False or p['unMirrorV'] is not False or uv['inputs']):
        _fail('uv', 'Only unmodified full-image TexCoord0 is supported.')
    for row, output_type in custom_rows:
        p = row['properties']
        if (not isinstance(p['code'], str) or not p['code'].strip() or p['outputType'] != output_type
                or p['additionalOutputs'] != [] or p['additionalDefines'] != [] or p['includeFilePaths'] != []
                or not isinstance(p['inputs'], list) or len(p['inputs']) != 1
                or not isinstance(p['inputs'][0], dict) or p['inputs'][0].get('inputName') != 'UV'):
            _fail('custom', 'Custom requires complete code, one UV input and no unbound outputs/defines/includes.')
        if version == 2 and '#' in p['code']:
            _fail('custom', 'Version 2 forbids inline preprocessor directives as well as external include files.')
        native_input = p['inputs'][0].get('input')
        expected_input = {'expression': uv['ref'], 'outputIndex': 0, 'inputName': 'None',
                          'mask': 0, 'maskR': 0, 'maskG': 0, 'maskB': 0, 'maskA': 0}
        if (set(p['inputs'][0]) != {'inputName', 'input'} or native_input != expected_input
                or any(type(native_input.get(k)) is not int for k in ('outputIndex', 'mask', 'maskR', 'maskG', 'maskB', 'maskA'))):
            _fail('wiring', 'Native Custom input fields must agree with the unmasked default UV connection.')
    if version == 1:
        rgba = color['properties']['constant']
        if (not isinstance(rgba, dict) or set(rgba) != {'r', 'g', 'b', 'a'}
                or any(not _number(v) or v < 0 for v in rgba.values()) or color['inputs']):
            _fail('color', 'Constant color must be completely observed finite nonnegative RGBA with no input dependency.')

    def edge(value, origin, input_name):
        if (value['expression'] != origin['ref'] or value['input_name'] != input_name
                or value['output_name'] not in ('', origin['outputs'][0])):
            _fail('wiring', 'Official graph wiring must use the declared default source output and exact input.')
    for row, _ in custom_rows:
        if len(row['inputs']) != 1:
            _fail('wiring', 'Every Custom must have exactly one connected UV input.')
        edge(row['inputs'][0], uv, 'UV')
    outputs = {}
    for name, origin in (('MP_Opacity', custom), ('MP_EmissiveColor', color)):
        outputs[name] = read(MATERIAL, 'get_property_input', {'material': material_ref, 'material_property': name})
        edge(outputs[name], origin, '')
    dirty_index, _ = take(ASSET, 'is_dirty', {'asset_path': package})
    if dirty_index != len(calls) - 1:
        _fail('order', 'The last official read must prove the material has no unsaved changes.')
    if consumed != set(indexed):
        _fail('call', 'Unexpected/unconsumed material calls cannot supplement or replace required evidence.')
    # Recheck mutable bytes after all graph checks, using existing binding rules.
    for binding in (evidence['projectFile'], evidence['savedFile'], evidence['executionReceipt']):
        bound_path(binding, evidence_path)
    bound_path(source['evidence'], owner)
    return {'materialPath': package, 'evaluationSize': source['evaluationSize'],
            'graphSha256': digest({'material': material_properties, 'expressions': sorted(graph, key=lambda r: r['ref']['refPath']), 'outputs': outputs}),
            'savedFileSha256': evidence['savedFile']['sha256']}
