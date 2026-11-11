#!/usr/bin/env python3
"""Execute an accepted existing-layout-update/2 Bundle with durable receipts.

No create-Blueprint, delete, rename, graph or business-code routes exist here.
An interrupted/failed output directory is never automatically resumed or rolled
back. A completed run can be checked again read-only with the same arguments.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT=Path(__file__).resolve().parent.parent
PLUGIN=ROOT.parents[1]
sys.path.insert(0,str(ROOT.parent/'refine-nextgame-ui-art/scripts'))
import art_editor as art
import existing_asset_update_v2 as update
import existing_asset_snapshot_v2 as snapshot

# Reuse the exact trusted ArtEditor binary32 equality authority, rather than
# introducing a second tolerance or float-normalization implementation.
_native_compare_scope={'math':math,'json':json}
exec(art._FLOAT32_PROGRAM,_native_compare_scope)


def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def equal(a,b): return _native_compare_scope['same_property'](a,b)


def durable(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.flush();os.fsync(stream.fileno())
    os.replace(tmp,path)


class Journal:
    def __init__(self,out):self.out=out;self.sequence=0
    def step(self,label,payload,fn):
        self.sequence+=1;path=self.out/'steps'/f'{self.sequence:05d}.json'
        row={'sequence':self.sequence,'label':label,'startedAt':now(),'status':'intent-recorded','request':payload}
        durable(path,row)
        try:
            value=fn();row.update(status='completed',completedAt=now(),response=value);durable(path,row);return value
        except Exception as exc:
            row.update(status='failed',completedAt=now(),error=str(exc));durable(path,row);raise


class Editor(art.ArtEditor):
    """Separate adapter; old ArtEditor allowlists and methods remain unchanged."""
    def __init__(self,project,url,timeout,journal):
        super().__init__(art.HttpTransport(url,timeout),nxue=art.NxueFallback(project,timeout))
        self.project=project;self.journal=journal;self.timeout=timeout
    def invoke(self,ts,tool,args):
        if tool in {'CreateWidgetBlueprint','DeleteWidget','RemoveWidget','RenameWidget','SetNamedSlotContent'} or ts==art.BP and tool not in {'get_default_object','list_graphs','read_graph_dsl'}:
            raise RuntimeError('Forbidden structural/business tool: '+tool)
        return self.journal.step(ts+'.'+tool,args,lambda:art._value(self._call(ts,tool,args)))
    def property_batch(self,ops):
        if not ops:return {'status':'completed','results':[]}
        if len(ops)>256:raise ValueError('Batch limit exceeded')
        seen=set();specific_classes={}
        for op in ops:
            if op['kind'] not in {'set-property','set-slot'}:raise ValueError('Not a native set operation')
            specific_allowed=frozenset()
            if op['kind']=='set-property' and op['property'] in update.SCALE_BOX_FIELDS|update.PROGRESS_BAR_FIELDS:
                identity=(op['assetPath'],op['widgetName'])
                if identity not in specific_classes:
                    w=self.widget(*identity)
                    cls=self.invoke(art.OBJ,'get_class',{'instance':w['widget']})
                    specific_classes[identity]=art._ref(cls)
                update.validate_scale_box_fields(specific_classes[identity],{op['property']:op['after']})
                update.validate_progress_bar_fields(specific_classes[identity],{op['property']:op['after']})
                specific_allowed=update.SCALE_BOX_FIELDS if specific_classes[identity]=='/Script/UMG.ScaleBox' else update.PROGRESS_BAR_FIELDS if specific_classes[identity]=='/Script/UMG.ProgressBar' else frozenset()
            allowed=art.SLOT_PROPERTIES if op['kind']=='set-slot' else art.WRITE_PROPERTIES|update.COLLECTION_FIELDS|specific_allowed
            if op['property'] not in allowed:raise ValueError('Outside explicit v2 native allowlist')
            key=(op['assetPath'],op['widgetName'],op['kind'],op['property'])
            if key in seen:raise ValueError('Duplicate property operation')
            seen.add(key)
        result=self.journal.step('v2-native-set-batch',{'operations':ops},lambda:self._program(art._SET_BATCH_PROGRAM,{'operations':ops},[(art.UMG,'GetWidgets'),(art.OBJ,'list_properties'),(art.OBJ,'get_properties'),(art.OBJ,'set_properties')],modules=('math',)))
        if not isinstance(result,dict) or result.get('status')!='completed' or len(result.get('results',[]))!=len(ops):raise RuntimeError('Native batch incomplete; inspect durable per-operation receipt')
        return result
    def tree(self,path):return self.invoke(art.UMG,'GetWidgets',{'widgetBlueprint':art._object(path)})
    def widget(self,path,name):
        matches=[x for x in self.tree(path)['widgets'] if x['widgetName']==name]
        if len(matches)!=1 or not art._ref(matches[0].get('widget')):raise RuntimeError('Missing/ambiguous actual UObject '+name)
        return matches[0]
    def values(self,instance,keys):
        schema=self.invoke(art.OBJ,'list_properties',{'instance':instance})
        if not set(keys)<=set(schema):raise RuntimeError('Property missing from actual native schema: '+str(set(keys)-set(schema)))
        return self.invoke(art.OBJ,'get_properties',{'instance':instance,'properties':list(keys)}) if keys else {}
    def initialize(self,path,name,values,slot=False):
        if not values:return
        w=self.widget(path,name);instance=w['slot' if slot else 'widget']
        if not art._ref(instance):raise RuntimeError('No actual Slot after structural operation')
        before=self.values(instance,values)
        # Recheck on the new instance; a class CDO observation alone cannot
        # authorize changing serialized fields absent from the editable schema.
        check_schema_fields(values,self.invoke(art.OBJ,'list_properties',{'instance':instance}),before=before)
        ops=[]
        for k,v in values.items():
            after=update.legacy._merge_observed(before[k],v,name+'.'+k)
            if not equal(before[k],after):ops.append({'id':'initialize-'+name+'-'+k,'kind':'set-slot' if slot else 'set-property','assetPath':path,'widgetName':name,'property':k,'before':before[k],'after':after})
        self.property_batch(ops)
    def nx(self,arguments,label):
        cmd=[sys.executable,'-B',str(self.project/'Tools/nxue/nxue.py'),*arguments]
        def run():
            result=subprocess.run(cmd,cwd=self.project,capture_output=True,text=True,encoding='utf-8',timeout=self.timeout)
            if result.returncode:raise RuntimeError('NxUE fallback failed: '+result.stderr[-1500:])
            value=json.loads(result.stdout)
            if value.get('ok') is not True:raise RuntimeError('NxUE fallback did not report success: '+result.stdout[-1500:])
            return value
        return self.journal.step(label,{'command':cmd},run)


def dirty_check(editor,paths):
    official={p:editor.invoke(art.ASSET,'is_dirty',{'asset_path':p}) for p in paths}
    if all(v is False for v in official.values()):return {'method':'official','dirty':[],'official':official}
    if any(type(v) is not bool for v in official.values()):raise RuntimeError('Official dirty result has unknown shape')
    # The host has produced contradictory dirty results. This fixed read-only
    # fallback queries actual dirty-package membership and never saves packages.
    source="import unreal,json\na=unreal.get_nxue_args()\nd=[p.get_path_name() for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]\nprint('NX_DIRTY='+json.dumps({'paths':a['paths'],'dirty':[p for p in d if p in a['paths']]}))"
    env=editor.nx(['exec-python','--script',source,'--args-json',json.dumps({'paths':paths})],'readonly-native-dirty-fallback')
    lines=[x[len('NX_DIRTY='):] for x in env['data']['output'].splitlines() if x.startswith('NX_DIRTY=')]
    if len(lines)!=1:raise RuntimeError('Native dirty fallback missing exact receipt')
    actual=json.loads(lines[0])
    if actual['paths']!=paths or actual['dirty']:raise RuntimeError('Scoped assets have unsaved changes: '+str(actual))
    return {'method':'mixed','fallbackReason':'Official dirty result requires actual native package membership verification','official':official,'native':actual}


def gates(args,out,journal):
    req=args.requirement.resolve(strict=True);view=args.accepted_build_view.resolve(strict=True);bundle=args.bundle.resolve(strict=True)
    packet=args.request_packet or req.parent/'request-packet.json'
    packet=packet.resolve(strict=True)
    scripts=PLUGIN/'skills/analyze-nextgame-ui-requirements/scripts'
    first=[str(req),'--request-packet',str(packet),'--check-findings-files']
    if args.review_draft:first+=['--review-draft',str(args.review_draft.resolve(strict=True))]
    specs=[('validate_requirement_spec.py',first),('validate_accepted_build_view.py',[str(view),'--requirement',str(req)]),('validate_build_bundle.py',[str(bundle),'--requirement',str(req),'--accepted-build-view',str(view)]),('validate_requirement_coverage.py',[str(bundle),'--requirement',str(req),'--accepted-build-view',str(view)])]
    for script,options in specs:
        cmd=[sys.executable,'-B',str(scripts/script),*options]
        def run(command=cmd):
            r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
            result={'command':command,'returnCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
            durable(out/('gate-'+Path(command[2]).stem+'.json'),result)
            if r.returncode:raise RuntimeError('Formal validator failed: '+Path(command[2]).name)
            return result
        journal.step('formal-validation',{'command':cmd},run)
    return {k:{'path':str(p),'sha256':sha(p)} for k,p in [('requirement',req),('acceptedBuildView',view),('bundle',bundle),('requestPacket',packet)]}


def capture(paths,out,project,url,timeout,label):
    dest=out/label;dest.mkdir(parents=True,exist_ok=False)
    p=dest/'snapshot.json'
    value=snapshot.capture(paths,p,dest/'raw',project,url,timeout)
    return value,p


def bound_asset(snapshot_value,path):
    return next(a for a in snapshot_value['assets'] if a['assetPath']==path)


def materialize_specs(bundle_path):
    result=[]
    for asset in load(bundle_path)['assets']:
        p=Path(asset['layoutSpecPath']);p=p if p.is_absolute() else bundle_path.parent/p;p=p.resolve(strict=True)
        if sha(p)!=asset['layoutSpecSha256']:raise RuntimeError('Layout physical hash differs from Bundle')
        layout=load(p)
        if layout.get('version')!='0.4' or layout.get('capability')!=update.CAPABILITY:raise RuntimeError('This executor accepts only explicit Layout0.4 capability/2 assets')
        plan=update.build_update_plan_v2(p,layout)
        if plan['assetPath']!=asset['assetPath']:raise RuntimeError('Plan asset differs from Bundle')
        if path_name(plan['assetPath'])=='W_GameButton_DrawNone' and plan['operations']:raise RuntimeError('W_GameButton_DrawNone is read-only parent evidence, never a mutation target')
        result.append({'asset':asset,'path':p,'layout':layout,'plan':plan})
    paths=[s['plan']['assetPath'] for s in result]
    if not paths or len(paths)!=len(set(paths)):raise RuntimeError('Unique nonempty target assets required')
    return result


def path_name(path):return path.rsplit('/',1)[-1]


def before_check(spec,current,current_path,project):
    plan=spec['plan'];layout=spec['layout'];path=plan['assetPath']
    base,asset,_=update._baseline(layout,spec['path']);now_asset=bound_asset(current,path)
    source=Path(asset['originalAssetFilePath']).resolve(strict=True)
    expected=(project/'Content'/(path.removeprefix('/Game/')+'.uasset')).resolve(strict=True)
    if source!=expected or not source.is_relative_to(project/'Content'):raise RuntimeError('Original saved asset path is outside exact project Content target')
    if sha(source)!=asset['sourceAsset']['sha256']:raise RuntimeError('Saved asset changed since reviewed baseline: '+path)
    # Hash-normalized float32 comparison, while preserving every identity and
    # raw evidence digest. Captured file locations are not native state.
    current_state=next(a for a in snapshot.state(current) if a['assetPath']==path)
    base_state=next(a for a in snapshot.state(base) if a['assetPath']==path)
    if current_state!=base_state:raise RuntimeError('Current complete native snapshot differs from reviewed baseline: '+path)
    return now_asset


SERIALIZED_BRUSH_FIELDS=frozenset({'uVRegion','bIsDynamicallyLoaded'})


def check_schema_fields(values,schema,*,before=None,owner_type=None):
    for k,v in values.items():
        if k not in schema:
            if (owner_type=='SlateBrush' and {'drawAs','imageSize','tintColor'}<=set(schema) and k in SERIALIZED_BRUSH_FIELDS
                    and isinstance(before,dict) and k in before and equal(v,before[k])):
                continue
            raise RuntimeError('Target native field not exposed by actual class schema, or serialized preservation differs: '+k)
        definition=schema[k]
        if 'enum' in definition and v not in definition['enum']:raise RuntimeError('Unsupported enum '+k)
        if isinstance(v,dict) and 'properties' in definition:
            check_schema_fields(v,definition['properties'],before=before.get(k) if isinstance(before,dict) else None,owner_type=definition.get('title'))


def _needs_serialized_preservation(values,schema):
    for key,value in values.items():
        if key not in schema and key in SERIALIZED_BRUSH_FIELDS:return True
        definition=schema.get(key,{})
        if isinstance(value,dict) and isinstance(definition.get('properties'),dict):
            if _needs_serialized_preservation(value,definition['properties']):return True
    return False


def _class_default_values(editor,cls,values):
    package,separator,class_name=cls.rpartition('.')
    if not separator:raise RuntimeError('Cannot resolve exact class default object identity')
    cdo={'refPath':package+'.Default__'+class_name}
    actual=editor.invoke(art.OBJ,'get_class',{'instance':cdo})
    if art._ref(actual)!=cls:raise RuntimeError('Actual class CDO type differs from the approved new-widget class')
    return editor.values(cdo,list(values))


def preflight_capabilities(editor,specs):
    # Discover input and output schema before any mutation; persist discoveries.
    required={(art.UMG,'GetWidgets'),(art.OBJ,'list_properties'),(art.OBJ,'get_properties'),(art.OBJ,'get_class'),(art.OBJ,'set_properties'),(art.UMG,'CompileWidgetBlueprint'),(art.ASSET,'save_assets'),(art.ASSET,'is_dirty'),(art.PROGRAM,'get_execution_environment'),(art.PROGRAM,'execute_tool_script')}
    for s in specs:
        for op in s['plan']['operations']:
            if op['kind']=='add-widget':required|={(art.UMG,'AddWidget'),(art.UMG,'ToggleWidgetAsVariable'),(art.UMG,'MoveWidget')}
            elif op['kind']=='reparent-widget':required.add((art.UMG,'MoveWidget'))
            elif op['kind']=='set-designer-mode':required.add((art.BP,'get_default_object'))
    for ts,t in sorted(required):editor.journal.step('discover-tool',{'toolset':ts,'tool':t},lambda ts=ts,t=t:editor._schema(ts,t))
    editor.environment=editor.invoke(art.PROGRAM,'get_execution_environment',{})
    if editor.environment.get('language')!='python' or 'execute_tool' not in editor.environment.get('instructions',''):raise RuntimeError('Unsupported official programmatic environment')
    if not {'json','math'}<={m.get('name') for m in editor.environment.get('supported_modules',[])}:raise RuntimeError('Official programmatic JSON/math support required for exact native comparison')
    class_schemas={};property_groups={};trees={}
    for s in specs:
        for op in s['plan']['operations']:
            if op['kind']=='add-widget':
                n=op['after']
                for cls,values in [(n['classPath'],n['nativeProperties']),(n['slotClassPath'],n['nativeSlot'])]:
                    if cls not in class_schemas:class_schemas[cls]=editor.invoke(art.OBJ,'list_properties',{'instance':{'refPath':cls}})
                    before=_class_default_values(editor,cls,values) if _needs_serialized_preservation(values,class_schemas[cls]) else None
                    check_schema_fields(values,class_schemas[cls],before=before)
            elif op['kind']=='reparent-widget':
                slot=op['after']['slot'];cls=slot['classPath']
                if cls not in class_schemas:class_schemas[cls]=editor.invoke(art.OBJ,'list_properties',{'instance':{'refPath':cls}})
                check_schema_fields(slot['properties'],class_schemas[cls])
            elif op['kind'] in {'set-property','set-slot'}:
                key=(op['assetPath'],op['widgetName'],op['kind'])
                property_groups.setdefault(key,[]).append(op)
            elif op['kind']=='set-designer-mode':designer_preflight(editor,op)
    for (path,name,kind),ops in property_groups.items():
        if path not in trees:trees[path]=editor.tree(path)
        matches=[w for w in trees[path]['widgets'] if w['widgetName']==name]
        if len(matches)!=1:raise RuntimeError('Preflight widget identity not unique')
        instance=matches[0]['slot' if kind=='set-slot' else 'widget']
        if not art._ref(instance):raise RuntimeError('Preflight mutable object/Slot missing')
        keys=[op['property'] for op in ops]
        native_schema=editor.invoke(art.OBJ,'list_properties',{'instance':instance})
        if not set(keys)<=set(native_schema):raise RuntimeError('Preflight native property missing from actual schema')
        values=editor.invoke(art.OBJ,'get_properties',{'instance':instance,'properties':keys})
        for op in ops:
            if not equal(values[op['property']],op['before']):raise RuntimeError('Native property changed before any write: '+path+':'+name+'.'+op['property'])
            check_schema_fields({op['property']:op['after']},native_schema,before=values)


def designer_preflight(editor,op):
    if op['after'] not in {'FillScreen','Desired'}:raise RuntimeError('Designer fallback target must be an explicitly supported reviewed mode')
    path=op['assetPath'];cdo=editor.invoke(art.BP,'get_default_object',{'blueprint':art._object(path)})
    ref=art._ref(cdo)
    if ref!=path+'.Default__'+path_name(path)+'_C':raise RuntimeError('Unexpected generated CDO identity')
    schema=editor.invoke(art.OBJ,'list_properties',{'instance':cdo})
    if 'designSizeMode' in schema:
        before=editor.values(cdo,['designSizeMode'])['designSizeMode']
        if before!=op['before']:raise RuntimeError('Designer mode CAS failed')
        check_schema_fields({'designSizeMode':op['after']},schema)
        return {'route':'official','cdo':cdo,'ref':ref}
    desc=editor.nx(['describe-tool','manage-property'],'discover-exact-designer-fallback')
    # NxUE tools/describe exposes tool metadata, not JSON Schema. The narrow
    # protocol is documented by Build SKILL's protected Designer-mode route;
    # verify the live tool actions and the exact typed CDO property separately.
    metadata=desc.get('data',{})
    if (metadata.get('name')!='manage-property' or metadata.get('writes') is not True
            or metadata.get('requiresEditor') is not True
            or not {'list','get','set'}<=set(metadata.get('actions',[]))
            or set(metadata.get('writeActions',[]))!={'set'}):
        raise RuntimeError('NxUE metadata does not support the documented exact Designer-mode protocol')
    listing=editor.nx(['tool','manage-property','--args-json',json.dumps({'action':'list','objectPath':ref})],'discover-exact-designer-property')
    data=listing.get('data',{});target=data.get('target',{})
    fields=[p for p in data.get('properties',[]) if isinstance(p,dict) and p.get('name')=='DesignSizeMode']
    if (target.get('path')!=ref or target.get('classPath')!=path+'.'+path_name(path)+'_C'
            or target.get('packageName')!=path or target.get('isAsset') is not False
            or len(fields)!=1 or fields[0].get('type')!='EnumProperty'):
        raise RuntimeError('NxUE exact CDO DesignSizeMode EnumProperty identity is unavailable')
    editor.journal.step('designer-fallback-protocol',{'evidenceKind':'tool-metadata-and-documented-contract',
        'document':'skills/build-nextgame-umg/SKILL.md','jsonSchemaAvailable':False,
        'setArguments':{'action':'set','objectPath':ref,'propertyPath':'DesignSizeMode','value':op['after']},
        'enumTargets':['FillScreen','Desired']},lambda:{'supported':True,'propertyType':'EnumProperty'})
    before=editor.journal.step('designer-fallback-before',{'CDO':ref,'property':'DesignSizeMode','reason':'Official CDO schema omits protected property'},lambda:editor.nxue.design_size_mode(ref))
    if before!=op['before']:raise RuntimeError('Fallback Designer mode CAS failed')
    return {'route':'nxue-protected-property','cdo':cdo,'ref':ref}


def designer_mode(editor,op):
    route=designer_preflight(editor,op);cdo=route['cdo'];ref=route['ref']
    if route['route']=='official':
        result=editor.invoke(art.OBJ,'set_properties',{'instance':cdo,'values':json.dumps({'designSizeMode':op['after']})})
        if result is not True or editor.values(cdo,['designSizeMode'])['designSizeMode']!=op['after']:raise RuntimeError('Official Designer mode write/read failed; no blind fallback after attempted write')
        return
    editor.nx(['tool','manage-property','--args-json',json.dumps({'action':'set','objectPath':ref,'propertyPath':'DesignSizeMode','value':op['after']})],'set-exact-designer-mode-fallback')
    after=editor.journal.step('designer-fallback-after',{'CDO':ref,'property':'DesignSizeMode'},lambda:editor.nxue.design_size_mode(ref))
    if after!=op['after']:raise RuntimeError('Fallback Designer mode post-read mismatch')


def apply_structure(editor,spec):
    plan=spec['plan'];path=plan['assetPath'];movable=set();slots={}
    for op in plan['operations']:
        if op['kind']=='add-widget':
            n=op['after'];tree=editor.tree(path)
            if any(w['widgetName']==n['name'] for w in tree['widgets']):raise RuntimeError('Added name already exists; refusing replay')
            parent=editor.widget(path,op['parentWidgetName'])
            info=editor.invoke(art.UMG,'AddWidget',{'widgetBlueprint':art._object(path),'widgetClass':{'refPath':n['classPath']},'widgetDisplayName':n['name'],'parentWidget':parent['widget'],'childIndex':-1})
            if not isinstance(info,dict) or info.get('widgetName')!=n['name'] or not art._ref(info.get('widget')):raise RuntimeError('AddWidget returned unexpected identity')
            editor.invoke(art.UMG,'ToggleWidgetAsVariable',{'widgetBlueprint':art._object(path),'widget':info['widget'],'bIsVariable':n['isVariable']})
            w=editor.widget(path,n['name'])
            if w['bIsVariable']!=n['isVariable'] or not update.legacy._observed_class_matches(art._ref(w['widgetClassPath']),n['classPath']):raise RuntimeError('New class/variable did not match approved identity')
            editor.initialize(path,n['name'],n['nativeProperties']);slots[n['name']]=n['nativeSlot'];movable.add(n['name'])
        elif op['kind']=='reparent-widget':
            w=editor.widget(path,op['widgetName']);parent=editor.widget(path,op['after']['parentWidgetName']);old_parent=editor.widget(path,op['before']['parentWidgetName'])
            if art._ref(w['widget'])!=op['before']['widgetRefPath'] or art._ref(w['parent'])!=art._ref(old_parent['widget']):raise RuntimeError('Reparent object/old parent CAS failed')
            current=editor.values(w['slot'],op['before']['slot']['properties'])
            if not equal(current,op['before']['slot']['properties']):raise RuntimeError('Reparent old Slot CAS failed')
            info=editor.invoke(art.UMG,'MoveWidget',{'widgetBlueprint':art._object(path),'widget':w['widget'],'newParent':parent['widget'],'childIndex':-1})
            if not isinstance(info,dict) or art._ref(info.get('widget'))!=art._ref(w['widget']):raise RuntimeError('Move replaced object identity')
            slots[op['widgetName']]=op['after']['slot']['properties'];movable.add(op['widgetName'])
    # Move only authorized/new widgets; stable old siblings are never moved.
    for parent_name,expected in plan['expectedChildOrder'].items():
        if not (set(expected)&movable):continue
        parent=editor.widget(path,parent_name)
        for index,name in enumerate(expected):
            if name not in movable:continue
            tree=editor.tree(path);actual=[w['widgetName'] for w in tree['widgets'] if art._ref(w.get('parent'))==art._ref(parent['widget'])]
            if actual.index(name)==index:continue
            w=editor.widget(path,name)
            info=editor.invoke(art.UMG,'MoveWidget',{'widgetBlueprint':art._object(path),'widget':w['widget'],'newParent':parent['widget'],'childIndex':index})
            if not isinstance(info,dict) or art._ref(info.get('widget'))!=art._ref(w['widget']):raise RuntimeError('Ordering replaced widget identity')
        tree=editor.tree(path);actual=[w['widgetName'] for w in tree['widgets'] if art._ref(w.get('parent'))==art._ref(parent['widget'])]
        if actual!=expected:raise RuntimeError('Final reviewed sibling order mismatch')
    for name,values in slots.items():editor.initialize(path,name,values,slot=True)


def merged(before,target):
    result=copy.deepcopy(before)
    for k,v in target.items():result[k]=update.legacy._merge_observed(result[k],v,k)
    return result


def verify_final(spec,actual,actual_path):
    layout=spec['layout'];plan=spec['plan'];path=plan['assetPath']
    _,base,old=update._baseline(layout,spec['path']);new_asset=bound_asset(actual,path);new={w['widgetName']:w for w in new_asset['widgets']}
    adds={n['name']:n for n in layout['additions']};nodes,_=update._nodes(layout);rs=update._reparent_map(layout)
    if set(new)!=set(old)|set(adds):raise RuntimeError('Post-save tree has missing or unexpected actual widgets')
    if [w['widgetName'] for w in new_asset['widgets'] if w['parentWidgetName'] is None]!=plan['expectedRootOrder']:raise RuntimeError('Own/inherited composition-root order changed')
    old_decl=[{k:v for k,v in d.items() if k!='treeIndex'} for d in base['declaredInheritedWidgets']]
    new_decl=[{k:v for k,v in d.items() if k!='treeIndex'} for d in new_asset['declaredInheritedWidgets']]
    if not equal(old_decl,new_decl):raise RuntimeError('Inherited declarations changed')
    if new_asset['parentClassPath']!=base['parentClassPath']:raise RuntimeError('Blueprint parent class changed')
    if not set(base['protectedReferences'])<=set(new_asset['protectedReferences']):raise RuntimeError('Original protected reference names lost')
    raw_before=snapshot.read_bound(base['rawEvidence'],snapshot.bound_path(layout['baseline']['snapshot'],spec['path']))
    raw_after=snapshot.read_bound(new_asset['rawEvidence'],actual_path)
    for key in ('graphs','namedSlots'):
        if not equal(raw_before[key],raw_after[key]):raise RuntimeError('Protected '+key+' changed')
    for n in layout['nodes']:
        before=old[n['name']];after=new[n['name']]
        for key in ('widgetName','isVariable','isInherited','classPath','widgetRefPath','namedSlotHostRefPath'):
            if not equal(before[key],after[key]):raise RuntimeError(n['name']+' protected identity changed: '+key)
        expected_parent=nodes[update._final_parent(n,rs)]['name'] if update._final_parent(n,rs) else None
        if after['parentWidgetName']!=expected_parent:raise RuntimeError('Final parent mismatch')
        if not equal(after['properties'],merged(before['properties'],n['nativeProperties'])):raise RuntimeError(n['name']+' complete property delta mismatch')
        if n['id'] in rs:
            r=rs[n['id']]
            if after['slot']['classPath']!=r['afterSlotClassPath']:raise RuntimeError('Reparent Slot class mismatch')
            for k,v in r['nativeSlot'].items():
                if not equal(after['slot']['properties'].get(k),v):raise RuntimeError('Reparent Slot target mismatch')
        else:
            if after['slot']['classPath']!=before['slot']['classPath'] or after['slotRefPath']!=before['slotRefPath'] or not equal(after['slot']['properties'],merged(before['slot']['properties'],n['nativeSlot'])):raise RuntimeError(n['name']+' undeclared Slot delta')
    for name,n in adds.items():
        w=new[name]
        if w['classPath']!=n['classPath'] or w['isVariable']!=n['isVariable'] or w['parentWidgetName']!=nodes[n['parent']]['name'] or w['slot']['classPath']!=n['slotClassPath']:raise RuntimeError('New node identity differs')
        for field,target in [('properties',n['nativeProperties']),('slot',n['nativeSlot'])]:
            actual_fields=w['slot']['properties'] if field=='slot' else w['properties']
            for k,v in target.items():
                if not equal(merged({k:actual_fields[k]},{k:v})[k],actual_fields[k]):raise RuntimeError('New node native target differs')
    for parent_name,expected in plan['expectedChildOrder'].items():
        order=[w['widgetName'] for w in new_asset['widgets'] if w['parentWidgetName']==parent_name]
        if order!=expected:raise RuntimeError('Post-save sibling order mismatch')
    target=layout['profile'].get('designSizeModeTarget',layout['profile']['designSizeMode'])
    if new_asset['designSizeMode']!=target:raise RuntimeError('Saved Designer mode mismatch')
    # Every approved target now equals actual; repeated application has no
    # outstanding sets, additions or moves. Do not issue a second write pass.
    return {'assetPath':path,'matched':True,'status':'read-only-noop-verified' if not plan['operations'] else 'saved-readback-matched','hasPlannedChanges':bool(plan['operations']),'repeatPendingWrites':0,'visualVerified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path);parser.add_argument('--requirement',type=Path,required=True);parser.add_argument('--accepted-build-view',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--project',type=Path,required=True);parser.add_argument('--request-packet',type=Path);parser.add_argument('--review-draft',type=Path)
    parser.add_argument('--url',default='http://127.0.0.1:8000/mcp');parser.add_argument('--timeout',type=float,default=180)
    args=parser.parse_args();project=args.project.resolve(strict=True);out=args.output.resolve();args.bundle=args.bundle.resolve(strict=True)
    if not out.is_relative_to(project/'Saved'):raise ValueError('Execution evidence must remain inside project Saved')
    previous=load(out/'receipt.json') if (out/'receipt.json').exists() else None
    if out.exists() and (previous is None or previous.get('status')!='saved-readback-matched-visual-pending'):raise RuntimeError('Existing interrupted/unrecognized output is not replayable; inspect receipts and replan explicitly')
    repeat=previous is not None
    if repeat:
        out=out/('readonly-repeat-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    out.mkdir(parents=True,exist_ok=False);journal=Journal(out)
    receipt={'kind':'nextgame-ui-existing-update-execution','version':'2','status':'preflight','startedAt':now(),'visualVerified':False,'repeatReadOnly':repeat,'assets':[]}
    durable(out/'receipt.json',receipt)
    try:
        bindings=gates(args,out,journal);receipt['formalBindings']=bindings
        if repeat and bindings!=previous['formalBindings']:raise RuntimeError('Completed receipt belongs to different formal inputs')
        specs=materialize_specs(args.bundle);paths=[s['plan']['assetPath'] for s in specs]
        editor=Editor(project,args.url,args.timeout,journal)
        receipt['cleanBefore']=dirty_check(editor,paths);durable(out/'receipt.json',receipt)
        current,current_path=capture(paths,out,project,args.url,args.timeout,'before')
        if repeat:
            for s in specs:receipt['assets'].append(verify_final(s,current,current_path))
            receipt.update(status='readonly-repeat-matched',completedAt=now(),assetWrites=0);durable(out/'receipt.json',receipt);return
        for s in specs:
            before_check(s,current,current_path,project)
            durable(out/'plans'/(s['plan']['assetPath'].split('/')[-1]+'.json'),s['plan'])
        preflight_capabilities(editor,specs)
        # Full gate again after preflight; detect on-disk formal input changes.
        if gates(args,out,journal)!=bindings:raise RuntimeError('Formal evidence changed during preflight')
        receipt['status']='running';durable(out/'receipt.json',receipt)
        for s in specs:
            path=s['plan']['assetPath'];base=bound_asset(current,path)
            dirty_check(editor,[path])
            if sha(base['originalAssetFilePath'])!=base['sourceAsset']['sha256']:raise RuntimeError('Asset disk CAS changed before scoped writes')
            if not s['plan']['operations']:
                receipt['assets'].append({'assetPath':path,'status':'read-only-noop','assetWrites':0})
                durable(out/'receipt.json',receipt)
                continue
            journal.step('asset-plan-intent',{'plan':s['plan']},lambda:{'approvedOperationCount':len(s['plan']['operations'])})
            apply_structure(editor,s)
            ops=[o for o in s['plan']['operations'] if o['kind'] in {'set-property','set-slot'}]
            for i in range(0,len(ops),256):editor.property_batch(ops[i:i+256])
            compiled=editor.invoke(art.UMG,'CompileWidgetBlueprint',{'widgetBlueprint':art._object(path)})
            if compiled is not True:raise RuntimeError('CompileWidgetBlueprint failed: '+path)
            # Structural compilation may regenerate the CDO. Reacquire it and
            # retain the original before-CAS before setting the reviewed mode.
            for op in s['plan']['operations']:
                if op['kind']=='set-designer-mode':designer_mode(editor,op)
            saved=editor.invoke(art.ASSET,'save_assets',{'asset_paths':[path]})
            if saved is not True:raise RuntimeError('Asset save failed: '+path)
            row={'assetPath':path,'status':'saved-awaiting-full-readback'};receipt['assets'].append(row);durable(out/'receipt.json',receipt)
        actual,actual_path=capture(paths,out,project,args.url,args.timeout,'after')
        receipt['assets']=[verify_final(s,actual,actual_path) for s in specs]
        receipt['cleanAfter']=dirty_check(editor,paths)
        receipt.update(status='saved-readback-matched-visual-pending',completedAt=now(),afterSnapshot=snapshot.binding(actual_path));durable(out/'receipt.json',receipt)
        print(json.dumps({'status':receipt['status'],'receipt':str(out/'receipt.json'),'assets':len(specs),'visualVerified':False}))
    except Exception as exc:
        receipt.update(status='failed-stop-inspect-required',failedAt=now(),error=str(exc),automaticRollback=False)
        durable(out/'receipt.json',receipt)
        raise


if __name__=='__main__':main()
