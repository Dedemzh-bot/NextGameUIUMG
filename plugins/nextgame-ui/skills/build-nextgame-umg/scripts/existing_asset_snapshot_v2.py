"""Opt-in, read-only existing-asset snapshot/2. Art snapshot/1 is unchanged.

Inherited declarations without UObjects are evidence, never writable widgets.
The capture uses schema-discovered official tools and the existing exact-CDO
read-only fallback for protected Designer mode. No method writes Unreal assets.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / 'assets/existing-asset-snapshot-v2.schema.json'
KIND = 'nextgame-ui-existing-asset-snapshot'
MODES = {'FillScreen', 'Desired', 'Custom', 'CustomOnScreen', 'DesiredOnScreen'}
SCALE_BOX_FIELDS = frozenset({'stretch','stretchDirection','ignoreInheritedScale'})
PROGRESS_BAR_FIELDS = frozenset({'fillColorAndOpacity'})

def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def binding(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def bound_path(record, owner):
    if not isinstance(record, dict) or set(record) != {'path', 'sha256'}:
        raise ValueError('Expected closed path/sha256 evidence binding')
    p = Path(record['path'])
    if not p.is_absolute():
        p = Path(owner).resolve().parent / p
    p = p.resolve(strict=True)
    if hashlib.sha256(p.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Stale evidence: ' + str(p))
    return p

def read_bound(record, owner):
    return load_json(bound_path(record, owner))

def _ref(value):
    if value in (None, 'None', ''):
        return None
    if isinstance(value, dict) and set(value) == {'refPath'} and isinstance(value['refPath'], str) and value['refPath']:
        return value['refPath']
    raise ValueError('Unrecognized object reference: ' + repr(value))

def _art():
    key = '_nextgame_existing_snapshot_v2_art'
    if key in sys.modules:
        return sys.modules[key]
    p = ROOT.parent / 'refine-nextgame-ui-art/scripts/art_editor.py'
    spec = importlib.util.spec_from_file_location(key, p)
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module

def validate_snapshot(snapshot, snapshot_path=None, check_evidence=False):
    validator = Draft202012Validator(load_json(SCHEMA), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(snapshot), key=lambda e: str(list(e.path)))
    if errors:
        raise ValueError('snapshot/2 schema ' + str(list(errors[0].path)) + ': ' + errors[0].message)
    digest(snapshot)  # reject non-finite JSON values
    paths = set()
    for a in snapshot['assets']:
        if a['assetPath'] in paths:
            raise ValueError('Duplicate asset')
        paths.add(a['assetPath'])
        records = a['widgets'] + a['declaredInheritedWidgets']
        names = [w['widgetName'] for w in records]
        refs = [w['widgetRefPath'] for w in a['widgets']]
        if len(set(names)) != len(names) or len(set(refs)) != len(refs):
            raise ValueError('Duplicate widget identity')
        ordered = sorted(records, key=lambda w: w['treeIndex'])
        if [w['treeIndex'] for w in ordered] != list(range(len(records))) or a['widgetOrder'] != [w['widgetName'] for w in ordered]:
            raise ValueError('Incomplete original WidgetTree ordering')
        if not set(a['protectedReferences']) <= set(names):
            raise ValueError('Unknown protected reference')
        by_name = {w['widgetName']: w for w in a['widgets']}
        by_ref = {w['widgetRefPath']: w for w in a['widgets']}
        for w in a['widgets']:
            for field in ('parentRefPath', 'namedSlotHostRefPath'):
                if w[field] is not None and w[field] not in by_ref:
                    raise ValueError('Unresolved actual ' + field + ': ' + w['widgetName'])
            expected = w['parentRefPath'] or w['namedSlotHostRefPath']
            if w['parentWidgetName'] != (by_ref[expected]['widgetName'] if expected else None):
                raise ValueError('Normalized parent differs from actual reference')
            seen = {w['widgetName']}
            parent = w['parentWidgetName']
            while parent is not None:
                if parent not in by_name or parent in seen:
                    raise ValueError('Missing parent or widget cycle')
                seen.add(parent)
                parent = by_name[parent]['parentWidgetName']
        if check_evidence:
            if snapshot_path is None:
                raise ValueError('snapshot_path required to validate evidence')
            raw = read_bound(a['rawEvidence'], snapshot_path)
            bound_path(a['sourceAsset'], snapshot_path)
            if raw['assetPath'] != a['assetPath'] or [w['widgetName'] for w in raw['tree']['widgets']] != a['widgetOrder']:
                raise ValueError('Raw tree identity/order mismatch')
            actual = normalize_asset(raw, a['designSizeMode'], a['rawEvidence'], a['sourceAsset'], a['originalAssetFilePath'])
            if actual != a:
                raise ValueError('Normalized snapshot differs from raw source evidence')
    return snapshot

def index_snapshot(snapshot):
    validate_snapshot(snapshot)
    assets = {a['assetPath']: a for a in snapshot['assets']}
    widgets = {(a['assetPath'], w['widgetName']): w for a in snapshot['assets'] for w in a['widgets']}
    return assets, widgets

def state(snapshot):
    validate_snapshot(snapshot)
    def native(v):
        if isinstance(v, float):
            if not math.isfinite(v):
                raise ValueError('Nonfinite value')
            v = struct.unpack('f', struct.pack('f', v))[0]
            return int(v) if v.is_integer() else v
        if isinstance(v, list):
            return [native(x) for x in v]
        if isinstance(v, dict):
            return {k: native(x) for k, x in v.items()}
        return v
    assets = native(copy.deepcopy(snapshot['assets']))
    for a in assets:
        # Evidence locations/capture order are not asset state; widget order is.
        a['rawEvidence'] = {'sha256': a['rawEvidence']['sha256']}
        a['sourceAsset'] = {'sha256': a['sourceAsset']['sha256']}
    return sorted(assets, key=lambda a: a['assetPath'])

def state_hash(snapshot):
    return digest(state(snapshot))

def normalize_asset(raw, mode, raw_binding, source_binding, original_asset_path):
    if mode not in MODES and mode is not None:
        raise ValueError('Unknown actual Designer mode')
    observed_mode = raw['cdoProperties'].get('designSizeMode')
    if observed_mode is None and 'designerModeFallback' in raw:
        fallback = raw['designerModeFallback']
        if (fallback.get('method') != 'nxue-readonly-fallback' or fallback.get('cdoRefPath') != _ref(raw['cdo']) or fallback.get('property') != 'DesignSizeMode'):
            raise ValueError('Invalid exact-CDO Designer mode fallback identity')
        observed_mode = fallback.get('value')
    if mode != observed_mode:
        raise ValueError('Designer mode differs from actual raw receipt')
    tree = raw['tree']; infos = tree['widgets']
    refs = {}
    for info in infos:
        ref = _ref(info['widget'])
        if ref:
            if ref in refs:
                raise ValueError('Duplicate actual UObject')
            refs[ref] = info['widgetName']
        elif info['bInherited'] is not True:
            raise ValueError('Non-inherited widget has no actual UObject')
    protected = {i['widgetName'] for i in infos if i['bIsVariable'] or i['bInherited']}
    for slot in raw['namedSlots']:
        for field in ('hostWidget', 'contentWidget'):
            ref = _ref(slot.get(field))
            if ref in refs:
                protected.add(refs[ref])
    graph_text = json.dumps(raw['graphs'], ensure_ascii=False)
    protected.update(i['widgetName'] for i in infos if i['widgetName'] in graph_text)
    entries = {e['info']['widgetName']: e for e in raw['widgets']}
    if len(entries) != len(raw['widgets']):
        raise ValueError('Duplicate actual records')
    widgets, declarations = [], []
    for index, info in enumerate(infos):
        name = info['widgetName']; ref = _ref(info['widget'])
        fields = {'widgetName': name, 'treeIndex': index, 'isVariable': info['bIsVariable'], 'isInherited': info['bInherited'], 'widgetRefPath': ref,
                  'parentRefPath': _ref(info['parent']), 'slotRefPath': _ref(info['slot']), 'namedSlotHostRefPath': _ref(info['namedSlotHost'])}
        if ref is None:
            if name in entries:
                raise ValueError('Inherited declaration was falsely collected as instance')
            declarations.append(dict(fields, declaredClassPath=_ref(info['widgetClassPath'])))
            continue
        e = entries.pop(name)
        if e['info'] != info:
            raise ValueError('Widget record differs from original tree')
        parent = fields['parentRefPath'] or fields['namedSlotHostRefPath']
        if parent and parent not in refs:
            raise ValueError('Unknown actual parent/NamedSlot host reference')
        cls = _ref(e['actualClass'])
        if not cls:
            raise ValueError('Actual widget class missing')
        if bool(fields['slotRefPath']) != bool(_ref(e['slotClass'])):
            raise ValueError('Actual Slot reference/class disagreement')
        widgets.append(dict(fields, classPath=cls, parentWidgetName=refs[parent] if parent else None,
                            properties=e['properties'], slot={'classPath': _ref(e['slotClass']), 'properties': e['slotProperties']}))
    if entries:
        raise ValueError('Foreign actual widget records')
    expected_declarations = [i for i in infos if _ref(i['widget']) is None]
    if raw['declaredInheritedWidgets'] != expected_declarations:
        raise ValueError('Raw inherited declarations differ from complete tree')
    references = {'graphs': raw['graphs'], 'namedSlots': raw['namedSlots'], 'protected': sorted(protected), 'complete': False, 'parentClass': tree['info']['parentClass']}
    return {'assetPath': raw['assetPath'], 'parentClassPath': _ref(tree['info']['parentClass']), 'designSizeMode': mode,
            'protectedReferences': sorted(protected), 'referencesComplete': False, 'referencesDigest': digest(references),
            'uncertainties': ['Animation bindings, native and external Lua references are not completely enumerated.'] + (['Actual Designer mode unavailable.'] if mode is None else []),
            'widgets': widgets, 'declaredInheritedWidgets': declarations, 'widgetOrder': [i['widgetName'] for i in infos],
            'rawEvidence': raw_binding, 'sourceAsset': source_binding, 'originalAssetFilePath': original_asset_path}

PROGRAM = """assets=[]
for path in data['paths']:
 blueprint={'refPath':path+'.'+path.rsplit('/',1)[-1]}
 tree=unpack(call_0({'widgetBlueprint':blueprint}))
 records=[]
 declarations=[]
 for info in tree['widgets']:
  ref=info['widget']
  if ref is None or ref=='None':
   if info['bInherited'] is not True:raise RuntimeError('Non-inherited null widget')
   declarations.append(info)
   continue
  if not isinstance(ref,dict) or not ref.get('refPath'):raise RuntimeError('Unknown widget reference')
  actualclass=unpack(call_3({'instance':ref}))
  schema=unpack(call_1({'instance':ref}))
  keys=[k for k in data['visualProperties'] if k in schema]
  if isinstance(actualclass,dict) and actualclass.get('refPath')=='/Script/UMG.ScaleBox':
   if any(k not in schema for k in data['scaleBoxProperties']):raise RuntimeError('Required native ScaleBox fields unavailable')
   keys.extend(data['scaleBoxProperties'])
  if isinstance(actualclass,dict) and actualclass.get('refPath')=='/Script/UMG.ProgressBar':
   if any(k not in schema for k in data['progressBarProperties']):raise RuntimeError('Required native ProgressBar fields unavailable')
   keys.extend(data['progressBarProperties'])
  props=unpack(call_2({'instance':ref,'properties':keys})) if keys else {}
  slot=info['slot']
  slotprops={}
  slotclass=None
  if isinstance(slot,dict) and slot.get('refPath'):
   ss=unpack(call_1({'instance':slot}))
   sk=[k for k in data['slotProperties'] if k in ss]
   slotprops=unpack(call_2({'instance':slot,'properties':sk})) if sk else {}
   slotclass=unpack(call_3({'instance':slot}))
  elif slot is not None and slot!='None':raise RuntimeError('Unknown Slot reference')
  records.append({'info':info,'actualClass':actualclass,'properties':props,'slotProperties':slotprops,'slotClass':slotclass})
 cdo=unpack(call_4({'blueprint':blueprint}))
 cs=unpack(call_1({'instance':cdo}))
 cp=unpack(call_2({'instance':cdo,'properties':['designSizeMode']})) if 'designSizeMode' in cs else {}
 slots=unpack(call_5({'widgetBlueprint':blueprint}))
 graphs=[]
 for graph in unpack(call_6({'blueprint':blueprint})):
  graphs.append({'ref':graph,'dsl':unpack(call_7({'graph':graph}))})
 assets.append({'assetPath':path,'tree':tree,'widgets':records,'declaredInheritedWidgets':declarations,'namedSlots':slots,'graphs':graphs,'cdo':cdo,'cdoProperties':cp})
return {'assets':assets}"""

def _exclusive_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')

def capture(asset_paths, output, evidence_dir, project, url='http://127.0.0.1:8000/mcp', timeout=180):
    art = _art(); output = Path(output).resolve(); evidence_dir = Path(evidence_dir).resolve(); project = Path(project).resolve()
    if output.exists():
        raise ValueError('Refusing to overwrite snapshot evidence')
    paths = [art._asset(p) for p in asset_paths]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError('Nonempty unique assets required')
    source = {}; originals = {}
    for p in paths:
        original = (project / 'Content' / (p.removeprefix('/Game/') + '.uasset')).resolve(strict=True)
        payload = original.read_bytes()
        backup = evidence_dir / 'source-assets' / (p.removeprefix('/Game/') + '.uasset')
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open('xb') as stream:
            stream.write(payload)
        source[p] = binding(backup)
        originals[p] = str(original)
    # Same ArtEditor discovery/preflight, shortened equivalent wrapper for this
    # host's payload limit. This does not modify the Art1 collector or schema.
    class Reader(art.ArtEditor):
        def collect(self, path):
            if self.environment is None:
                self.environment = art._value(self._call(art.PROGRAM, 'get_execution_environment', {}))
                if self.environment.get('language') != 'python' or 'execute_tool' not in self.environment.get('instructions', ''):
                    raise RuntimeError('Unsupported official execution environment')
                if 'json' not in [m.get('name') for m in self.environment.get('supported_modules', [])]:
                    raise RuntimeError('Official programmatic JSON module unavailable')
            calls=[(art.UMG,'GetWidgets'),(art.OBJ,'list_properties'),(art.OBJ,'get_properties'),(art.OBJ,'get_class'),(art.BP,'get_default_object'),(art.UMG,'GetNamedSlots'),(art.BP,'list_graphs'),(art.BP,'read_graph_dsl')]
            wrappers=[]
            for i,(ts,tool) in enumerate(calls):
                self._schema(ts,tool)
                wrappers.append(f'def call_{i}(a):return execute_tool({(ts+"."+tool)!r},json.dumps(a))')
            data={'paths':[path],'visualProperties':sorted(art.VISUAL_PROPERTIES),'slotProperties':sorted(art.SLOT_PROPERTIES),'scaleBoxProperties':sorted(SCALE_BOX_FIELDS),'progressBarProperties':sorted(PROGRESS_BAR_FIELDS)}
            script='import json\n'+'\n'.join(wrappers)+'\ndef unpack(v):\n v=v["returnValue"] if "returnValue" in v else v\n if isinstance(v,str):\n  try:return json.loads(v)\n  except ValueError:pass\n return v\ndef run():\n data='+repr(data)+'\n'+'\n'.join(' '+line for line in PROGRAM.splitlines())
            return art._value(self._call(art.PROGRAM,'execute_tool_script',{'script':script}))['assets'][0]
    reader = Reader(art.HttpTransport(url,timeout), nxue=art.NxueFallback(project,timeout=max(120,timeout)))
    assets=[]; mixed=False
    for p in paths:
        raw=reader.collect(p); mode=raw['cdoProperties'].get('designSizeMode')
        if mode is None:
            mode=reader.nxue.design_size_mode(_ref(raw['cdo'])); mixed=True
            raw['designerModeFallback']={'method':'nxue-readonly-fallback','cdoRefPath':_ref(raw['cdo']),'property':'DesignSizeMode','value':mode}
        if binding(originals[p])['sha256'] != source[p]['sha256']:
            raise RuntimeError('Saved asset changed during read-only capture')
        # Different packages may share a basename; preserve the package path.
        path=evidence_dir/'raw-trees'/(p.removeprefix('/Game/')+'.raw.json')
        _exclusive_json(path,raw)
        assets.append(normalize_asset(raw,mode,binding(path),source[p],originals[p]))
    acquisition={'method':'mixed' if mixed else 'official-unreal-mcp'}
    if mixed:
        acquisition['fallbackReason']='Official generated-CDO schema omits DesignSizeMode; exact returned CDO/property read through existing read-only NxUE fallback.'
    result={'kind':KIND,'version':'2','capturedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'acquisition':acquisition,'assets':assets}
    validate_snapshot(result,output,True)
    _exclusive_json(output,result)
    _exclusive_json(evidence_dir/'capture-receipt.json',{'kind':'existing-asset-snapshot-capture-receipt','version':'2','snapshot':binding(output),'stateSha256':state_hash(result),'readOnly':True,'assets':[{'assetPath':a['assetPath'],'designSizeMode':a['designSizeMode'],'actualWidgets':len(a['widgets']),'declaredInheritedWidgets':len(a['declaredInheritedWidgets'])} for a in assets]})
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    c=sub.add_parser('capture'); c.add_argument('--asset',action='append',required=True);c.add_argument('--output',required=True);c.add_argument('--evidence-dir',required=True);c.add_argument('--project',required=True);c.add_argument('--url',default='http://127.0.0.1:8000/mcp');c.add_argument('--timeout',type=float,default=180)
    v=sub.add_parser('validate');v.add_argument('snapshot');v.add_argument('--check-evidence',action='store_true')
    args=parser.parse_args()
    if args.command=='capture':result=capture(args.asset,args.output,args.evidence_dir,args.project,args.url,args.timeout)
    else:result=validate_snapshot(load_json(args.snapshot),args.snapshot,args.check_evidence)
    print(json.dumps({'valid':True,'kind':KIND,'version':'2','stateSha256':state_hash(result),'assets':[{'assetPath':a['assetPath'],'designSizeMode':a['designSizeMode'],'widgets':len(a['widgets']),'inheritedDeclarations':len(a['declaredInheritedWidgets'])} for a in result['assets']]},ensure_ascii=False))

if __name__=='__main__':
    main()
