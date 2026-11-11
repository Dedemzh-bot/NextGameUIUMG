#!/usr/bin/env python3
"""Closed UILayoutSpec 0.4 planning. Offline only; never an Editor executor.

0.3 is deliberately unchanged. Native targets are already lowered by the
canonical build path. Full accepted Requirement/View/Bundle checks remain
mandatory in addition to the local validation below.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
import existing_asset_update as legacy

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = SKILL_ROOT / 'assets/existing-asset-update-v2.schema.json'
CAPABILITY = 'existing-asset-layout-update/2'
PLAN_KIND = 'nextgame-ui-existing-asset-layout-update-plan'
COLLECTION_FIELDS = frozenset({'entryWidth', 'entryHeight', 'horizontalEntrySpacing', 'verticalEntrySpacing'})
SCALE_BOX_FIELDS = frozenset({'stretch','stretchDirection','ignoreInheritedScale'})
PROGRESS_BAR_FIELDS = frozenset({'fillColorAndOpacity'})
SCALE_BOX_ENUMS = {
    'stretch':frozenset({'None','Fill','ScaleToFit','ScaleToFitX','ScaleToFitY','ScaleToFill','ScaleBySafeZone','UserSpecified','UserSpecifiedWithClipping'}),
    'stretchDirection':frozenset({'Both','DownOnly','UpOnly'}),
}
COLLECTION_CLASSES = frozenset({'/Script/UIFramework.LuaTileView', '/Script/UIFramework.LuaListView'})
NEW_CLASSES = frozenset({'/Script/UIFramework.GameImage', '/Script/UMG.TextBlock', '/Script/UMG.Button',
    '/Script/UMG.CanvasPanel', '/Script/UMG.Overlay', '/Script/UMG.HorizontalBox',
    '/Script/UMG.VerticalBox', '/Script/UMG.SizeBox', '/Script/UMG.ScaleBox'})
PARENT_SLOTS = {'/Script/UMG.' + a: '/Script/UMG.' + b for a,b in (
    ('CanvasPanel','CanvasPanelSlot'),('Overlay','OverlaySlot'),('HorizontalBox','HorizontalBoxSlot'),
    ('VerticalBox','VerticalBoxSlot'),('Button','ButtonSlot'),('SizeBox','SizeBoxSlot'),('ScaleBox','ScaleBoxSlot'))}
MULTI_PARENTS = frozenset({'/Script/UMG.CanvasPanel','/Script/UMG.Overlay','/Script/UMG.HorizontalBox','/Script/UMG.VerticalBox'})
REUSABLE_WIDGET_CLASSES = frozenset('/Game/UI/UMG/Widgets/'+n+'.'+n+'_C' for n in (
    'uw_common_bag_item_slot','uw_common_bag_weapon_slot','uw_common_bag_augment_slot',
    'uw_common_bag_shield_slot','uw_common_bag_core_slot','uw_common_currency',
    'uw_common_back','uw_common_quickbtns','uw_common_roleinfo','uw_common_skill'))
exact = legacy.exact
asset_path = legacy.asset_path


def _issue(code: str, message: str, path: str = '$') -> dict:
    return {'code':'existing-update-v2.' + code,'path':path,'message':message}


def validate_scale_box_fields(class_path, properties, *, require_complete=False):
    """Only fields discovered from the native ScaleBox class are added in v2."""
    touched=set(properties)&SCALE_BOX_FIELDS
    if touched and class_path!='/Script/UMG.ScaleBox':raise ValueError('ScaleBox native fields cannot be written on another class')
    if require_complete and class_path=='/Script/UMG.ScaleBox' and touched!=SCALE_BOX_FIELDS:raise ValueError('New ScaleBox requires explicit stretch/stretchDirection/ignoreInheritedScale')
    for key in touched:
        value=properties[key]
        if key in SCALE_BOX_ENUMS and (not isinstance(value,str) or value not in SCALE_BOX_ENUMS[key]):raise ValueError('Unknown ScaleBox native enum: '+key)
        if key=='ignoreInheritedScale' and type(value) is not bool:raise ValueError('ignoreInheritedScale must be an explicit boolean')


def validate_progress_bar_fields(class_path, properties):
    if not (set(properties)&PROGRESS_BAR_FIELDS):return
    if class_path!='/Script/UMG.ProgressBar':raise ValueError('ProgressBar fill color cannot be written on another class')
    color=properties['fillColorAndOpacity']
    if not isinstance(color,dict) or set(color)!={'r','g','b','a'} or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in color.values()):raise ValueError('ProgressBar fillColorAndOpacity requires exact finite nonnegative native RGBA')


@lru_cache(maxsize=1)
def _snapshot_module():
    path = SKILL_ROOT / 'scripts/existing_asset_snapshot_v2.py'
    spec = importlib.util.spec_from_file_location('_existing_layout_snapshot_v2', path)
    if spec is None or spec.loader is None:
        raise ValueError('Snapshot v2 authority is unavailable: ' + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ref(value):
    if value is None or value == 'None': return None
    return value.get('refPath') if isinstance(value,dict) else value


def _baseline(layout: dict, spec_path: Path):
    sm = _snapshot_module()
    snapshot = sm.read_bound(layout['baseline']['snapshot'], spec_path)
    snapshot_path = sm.bound_path(layout['baseline']['snapshot'],spec_path)
    sm.validate_snapshot(snapshot,snapshot_path=snapshot_path,check_evidence=True)
    if sm.state_hash(snapshot) != layout['baseline']['stateSha256']:
        raise ValueError('Snapshot v2 state hash differs from the bound baseline')
    assets, widgets = sm.index_snapshot(snapshot)
    path = asset_path(layout)
    if path not in assets: raise ValueError('Target asset is absent from the snapshot')
    asset = assets[path]
    observed = {n:w for (a,n),w in widgets.items() if a==path}
    raw = sm.read_bound(layout['baseline']['rawTree'],spec_path)
    if not isinstance(raw,dict) or not isinstance(raw.get('info'),dict) or not isinstance(raw.get('widgets'),list):
        raise ValueError('rawTree must bind the complete GetWidgets info/widgets payload')
    evidence=sm.read_bound(asset['rawEvidence'],snapshot_path)
    if not exact(raw,evidence['tree']):raise ValueError('rawTree must exactly match the snapshot raw GetWidgets payload, including every flag/count')
    declarations = {w['widgetName']:w for w in asset['declaredInheritedWidgets']}
    names = [w['widgetName'] for w in raw['widgets']]
    if names != asset['widgetOrder'] or len(set(names)) != len(names) or set(names)!=set(observed)|set(declarations):
        raise ValueError('Raw GetWidgets order or full declared/actual identity coverage differs')
    if _ref(raw['info'].get('parentClass'))!=asset['parentClassPath']:
        raise ValueError('Raw parent class differs from snapshot')
    for item in raw['widgets']:
        name=item['widgetName']
        if name in declarations:
            w=declarations[name]
            if _ref(item.get('widget')) is not None or not item.get('bInherited'):
                raise ValueError('Inherited declaration must retain null UObject and inheritance')
        else:
            w=observed[name]
            if _ref(item.get('widget'))!=w['widgetRefPath'] or _ref(item.get('slot'))!=w['slotRefPath']:
                raise ValueError('Raw object/Slot reference differs: '+name)
            if not legacy._observed_class_matches(_ref(item.get('widgetClassPath')),w['classPath']):
                raise ValueError('Raw class differs: '+name)
        if item.get('bIsVariable')!=w['isVariable'] or _ref(item.get('parent'))!=w['parentRefPath'] or _ref(item.get('namedSlotHost'))!=w['namedSlotHostRefPath']:
            raise ValueError('Raw parent/variable/NamedSlot identity differs: '+name)
    return snapshot,asset,observed


def _rect(node):
    x,y,w,h=node['rect']
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in node['rect']) or x<0 or y<0 or w<=0 or h<=0 or x+w>1+1e-9 or y+h>1+1e-9:
        raise ValueError(node['id']+': rect must be positive normalized screen/asset bounds within [0,1]')


def _nodes(layout):
    allnodes=layout['nodes']+layout['additions']
    nodes={n['id']:n for n in allnodes};names={n['name']:n for n in allnodes}
    if len(nodes)!=len(allnodes) or len(names)!=len(allnodes):raise ValueError('Duplicate node id/name')
    return nodes,names


def _reparent_map(layout):
    result={r['nodeId']:r for r in layout['reparents']}
    if len(result)!=len(layout['reparents']):raise ValueError('Duplicate reparent node')
    return result


def _final_parent(n, reparents):
    return reparents[n['id']]['afterParent'] if n['id'] in reparents else n['parent']


def _slot_check(values: dict, cls: str):
    # Structural work is intentionally limited to ordinary panel Slots.
    if cls not in PARENT_SLOTS.values():raise ValueError('Unsupported or NamedSlot target Slot class: '+str(cls))
    allowed=legacy._art_module('art_editor').SLOT_PROPERTIES
    if set(values)-allowed:raise ValueError('Unsupported native Slot fields')
    if cls=='/Script/UMG.CanvasPanelSlot':
        if not {'layoutData','bAutoSize','zOrder'} <= set(values):raise ValueError('New Canvas Slot requires complete layoutData/bAutoSize/zOrder')
        d=values['layoutData'];o=d.get('offsets',{});a=d.get('anchors',{});al=d.get('alignment',{})
        if set(o)!={'left','top','right','bottom'} or set(al)!={'x','y'} or set(a)!={'minimum','maximum'}:raise ValueError('Incomplete Canvas geometry')
        for axis in ('x','y'):
            lo,hi=a['minimum'].get(axis),a['maximum'].get(axis)
            if type(lo) not in (int,float) or type(hi) not in (int,float) or not 0<=lo<=hi<=1 or not 0<=al[axis]<=1:raise ValueError('Invalid Canvas anchors/alignment')
        if values['bAutoSize'] is not False:raise ValueError('New/reparent Canvas geometry requires explicit non-AutoSize')
    elif cls=='/Script/UMG.ScaleBoxSlot':
        if set(values)!={'horizontalAlignment','verticalAlignment'}:
            raise ValueError('ScaleBoxSlot supports only explicit horizontal/vertical alignment; padding is not exposed')
    elif not {'padding','horizontalAlignment','verticalAlignment'}<=set(values):
        raise ValueError('New flow/content Slot requires explicit padding and alignment')


def _operations(layout, observed):
    editor=legacy._art_module('art_editor');operations=[]
    collections={c['nodeId']:c for c in layout['collections']}
    if len(collections)!=len(layout['collections']):raise ValueError('Duplicate collection contracts')
    reparents=_reparent_map(layout)
    for node in layout['nodes']:
        current=observed[node['name']]
        validate_scale_box_fields(current['classPath'],node['nativeProperties'])
        validate_progress_bar_fields(current['classPath'],node['nativeProperties'])
        accepted={v['property'] for v in node.get('contentStateAcceptance',[])}
        if len(accepted)!=len(node.get('contentStateAcceptance',[])):raise ValueError('Duplicate text/visibility acceptance')
        allowed_properties=editor.WRITE_PROPERTIES|COLLECTION_FIELDS|(SCALE_BOX_FIELDS if current['classPath']=='/Script/UMG.ScaleBox' else frozenset())|(PROGRESS_BAR_FIELDS if current['classPath']=='/Script/UMG.ProgressBar' else frozenset())
        for kind,field,before,allowed in [('set-property','nativeProperties',current['properties'],allowed_properties),('set-slot','nativeSlot',current['slot']['properties'],editor.SLOT_PROPERTIES)]:
            if kind=='set-slot' and node['id'] in reparents:
                if node[field]:raise ValueError('Reparent Slot targets belong only in reparent.nativeSlot')
                continue
            if set(node[field])-set(before) or set(node[field])-allowed:raise ValueError(node['id']+': target is unobserved or protected')
            for key,target in node[field].items():
                after=legacy._merge_observed(before[key],target,node['id']+'.'+field+'.'+key)
                if exact(before[key],after):continue
                if key in {'text','visibility'} and key not in accepted:raise ValueError(node['id']+': text/visibility requires explicit accepted native target')
                if key in COLLECTION_FIELDS and node['id'] not in collections:raise ValueError(node['id']+': collection size/spacing needs provider/host coordination')
                if key=='font' and 'size' in target and (type(after['size']) is not int or after['size']<=0 or after['size']%2):raise ValueError('Native font must already use canonical compensated even Slate size')
                if kind=='set-slot' and current['slot']['classPath'] is None:raise ValueError('Root has no mutable parent Slot')
                operations.append({'id':kind+'-'+node['id']+'-'+key,'kind':kind,'assetPath':asset_path(layout),'widgetName':node['name'],'property':key,'before':copy.deepcopy(before[key]),'after':after})
    return operations


def _validate_collections(layout, observed, spec_path):
    sm=_snapshot_module();nodes,_=_nodes(layout)
    for c in layout['collections']:
        n=nodes.get(c['nodeId'])
        if n is None or n['name'] not in observed:raise ValueError('Collection must identify an existing node')
        w=observed[n['name']]
        if w['classPath'] not in COLLECTION_CLASSES or n['role'] not in {'collection.lua-tile','collection.lua-list'}:raise ValueError('Collection native class/semantic role mismatch')
        props=copy.deepcopy(w['properties'])
        for key,val in n['nativeProperties'].items():props[key]=legacy._merge_observed(props[key],val,key)
        if _ref(props.get('entryWidgetClass'))!=c['entryClassPath']:raise ValueError('Collection EntryClass must remain exact')
        if c['entryClassPath']!=c['providerAssetPath']+'.'+c['providerAssetPath'].split('/')[-1]+'_C':raise ValueError('Provider asset does not match EntryClass')
        if w['classPath'].endswith('.LuaTileView'):
            if c['layoutMode']=='single-entry':
                if c['columns']!=1 or any(not pitch<=host<2*pitch for pitch,host in zip(c['entrySize'],c['hostSize'])):raise ValueError('Single-entry Tile contract must allocate exactly one cell on each axis')
                if props.get('orientation') not in {'Orient_Vertical','Orient_Horizontal'}:raise ValueError('Unknown preserved Tile orientation')
            elif c['layoutMode']!='grid' or props.get('orientation')!='Orient_Vertical':raise ValueError('Multi-column grid requires preserved vertical Tile flow')
            if [props.get('entryWidth'),props.get('entryHeight')]!=c['entrySize']:raise ValueError('Tile entry size differs from coordinated size')
            if c['spacing']!=[0,0]:raise ValueError('LuaTileView native spacing contracts content inward; visible gaps must use entry pitch minus visibleSize')
            if any(v>pitch for v,pitch in zip(c['visibleSize'],c['entrySize'])):raise ValueError('Visible footprint cannot exceed allocated entry pitch')
            if int((c['hostSize'][0]+1e-6)//c['entrySize'][0])!=c['columns']:raise ValueError('Tile host width must allocate the full final cell pitch and exactly the intended column count')
        elif any(k in n['nativeProperties'] for k in ('entryWidth','entryHeight')) or c['layoutMode']!='linear':raise ValueError('ListView requires linear layout and cannot use TileView dimensions')
        if [props.get('horizontalEntrySpacing'),props.get('verticalEntrySpacing')]!=c['spacing']:raise ValueError('Spacing differs from coordinated size')
        if c['columns']*c['entrySize'][0]>c['hostSize'][0]+1e-6:raise ValueError('Columns exceed host width')
        expected=[n['rect'][2]*layout['referenceSize'][0],n['rect'][3]*layout['referenceSize'][1]]
        if any(abs(a-b)>1e-5 for a,b in zip(expected,c['hostSize'])):raise ValueError('Collection hostSize differs from normalized rect')
        provider=sm.read_bound(c['providerLayout'],spec_path)
        schema=json.loads(SCHEMA.read_text(encoding='utf-8'))
        if list(Draft202012Validator(schema).iter_errors(provider)):raise ValueError('Bound provider Layout0.4 fails closed schema')
        if provider.get('version')!='0.4' or provider.get('capability')!=CAPABILITY or asset_path(provider)!=c['providerAssetPath']:raise ValueError('Provider must bind an explicit existing Layout0.4')
        ps=provider.get('profile',{}).get('providerSizing',{})
        expected_visible=c['entrySize'] if ps.get('contentSizing')=='fill-host' else ps.get('visibleSize')
        if expected_visible!=c['visibleSize']:raise ValueError('Provider visible footprint policy differs from coordinated design size')
        if provider['profile'].get('listRole')!='entry' or c['entrySize'] not in ps.get('supportedSizes',[]):raise ValueError('Provider sizing contract does not support host entry size')
        if ps.get('sizingMode')=='fixed' and ps.get('targetSize')!=c['entrySize']:raise ValueError('Fixed provider sizing differs from host')
        if ps.get('sizingMode') not in {'fixed','host-adaptive'}:raise ValueError('Provider requires explicit fixed/host-adaptive policy')
        if not any(x.get('assetPath')==asset_path(layout) and x.get('widgetName')==n['name'] and x.get('entrySize')==c['entrySize'] for x in ps.get('consumers',[])):raise ValueError('Provider does not explicitly list this coordinated consumer')
    if layout['profile']['listRole']=='entry':
        dimensions={'widthOverride','heightOverride','bOverride_WidthOverride','bOverride_HeightOverride','minDesiredWidth','minDesiredHeight','maxDesiredWidth','maxDesiredHeight'}
        resized=any(set(n['nativeProperties'])&dimensions or n['nativeSlot'] for n in layout['nodes'])
        if resized and 'providerSizing' not in layout['profile']:raise ValueError('Entry/provider geometry changes require explicit consumer coordination')
    if layout['profile'].get('providerSizing'):_provider_sizing_proof(layout,observed,spec_path)


def _provider_sizing_proof(layout, observed, spec_path, seen=()):
    ps=layout['profile'].get('providerSizing');nodes,_=_nodes(layout);sm=_snapshot_module()
    if not ps:raise ValueError('Provider chain member lacks explicit sizing contract')
    if asset_path(layout) in seen:raise ValueError('Provider inheritance contract cycle')
    if ps:
        if ps['targetSize']!=layout['referenceSize']:raise ValueError('Provider targetSize must match reference dimensions')
        if ps['targetSize'] not in ps['supportedSizes']:raise ValueError('Provider supportedSizes must include reference targetSize')
        if ps['sizingMode']=='fixed' and ps['supportedSizes']!=[ps['targetSize']]:raise ValueError('Fixed provider cannot declare alternative host sizes')
        if any(c['entrySize'] not in ps['supportedSizes'] for c in ps['consumers']):raise ValueError('Every declared consumer must use a supported size')
        for consumer in ps['consumers']:
            if consumer.get('kind','collection')=='named-slot-content':
                if 'hostEvidence' not in consumer or 'slotName' not in consumer:raise ValueError('NamedSlot consumer requires exact read-only host snapshot and slot name')
                hs=sm.read_bound(consumer['hostEvidence'],spec_path);hp=sm.bound_path(consumer['hostEvidence'],spec_path);sm.validate_snapshot(hs,snapshot_path=hp,check_evidence=True)
                hosts,hwidgets=sm.index_snapshot(hs);host=hosts.get(consumer['assetPath'])
                if host is None:raise ValueError('NamedSlot consumer host absent from bound actual evidence')
                visited=set();found=False
                while host is not None:
                    if host['assetPath'] in visited:raise ValueError('Actual NamedSlot host inheritance cycle')
                    visited.add(host['assetPath']);widget=hwidgets.get((host['assetPath'],consumer['widgetName']))
                    hraw=sm.read_bound(host['rawEvidence'],hp)
                    declared=any(slot.get('slotName')==consumer['slotName'] and (consumer['widgetName']==consumer['slotName'] or widget is not None and _ref(slot.get('hostWidget'))==widget['widgetRefPath']) for slot in hraw['namedSlots'])
                    actual_named=widget is not None and widget['classPath']=='/Script/UMG.NamedSlot' and widget['widgetName']==consumer['slotName']
                    if declared or actual_named:found=True;break
                    parent_class=host['parentClassPath']
                    if not parent_class.startswith('/Game/UI/UMG/'):break
                    parent_path=parent_class.split('.')[0];parent=hosts.get(parent_path)
                    if parent is None or parent_class!=parent_path+'.'+parent_path.rsplit('/',1)[-1]+'_C':raise ValueError('NamedSlot host proof requires every actual parent Blueprint in the bound snapshot')
                    host=parent
                if not found:raise ValueError('NamedSlot consumer is not proven by actual host or complete parent-chain evidence')
            elif 'hostEvidence' in consumer or 'slotName' in consumer:raise ValueError('Collection consumer cannot carry a misleading NamedSlot contract')
        if ps['contentSizing']=='fixed-footprint' and any(v>axis_size for supported in ps['supportedSizes'] for v,axis_size in zip(ps['visibleSize'],supported)):raise ValueError('Visible provider footprint exceeds a supported host pitch')
        if ps['rootSizingNodeId'] is None:
            if 'inheritedProviderLayout' not in ps:raise ValueError('Inherited sizing requires exact parent provider Layout binding')
            _,asset,_=_baseline(layout,spec_path)
            raw=sm.read_bound(asset['rawEvidence'],sm.bound_path(layout['baseline']['snapshot'],spec_path))
            if _ref(raw['tree']['info'].get('rootWidgetClass')) is not None:raise ValueError('Own-root asset cannot claim inherited-only sizing')
            parent=sm.read_bound(ps['inheritedProviderLayout'],spec_path);parent_path=sm.bound_path(ps['inheritedProviderLayout'],spec_path)
            schema=json.loads(SCHEMA.read_text(encoding='utf-8'))
            if list(Draft202012Validator(schema).iter_errors(parent)):raise ValueError('Inherited parent provider fails closed Layout schema')
            if asset['parentClassPath']!=asset_path(parent)+'.'+parent['asset']['name']+'_C':raise ValueError('Inherited provider is not the actual Blueprint parent class')
            _,parent_asset,parent_observed=_baseline(parent,parent_path)
            _validate_structure(parent,parent_asset,parent_observed,parent_path);_operations(parent,parent_observed)
            pp=_provider_sizing_proof(parent,parent_observed,parent_path,seen+(asset_path(layout),))
            for key in ('targetSize','visibleSize','sizingMode','contentSizing','supportedSizes'):
                if not exact(ps[key],pp[key]):raise ValueError('Inherited sizing must preserve complete parent sizing policy: '+key)
            return ps
        if 'inheritedProviderLayout' in ps:raise ValueError('Own sizing proof cannot also claim inherited provider')
        if ps['rootSizingNodeId'] not in nodes:raise ValueError('Missing actual provider sizing node')
        n=nodes[ps['rootSizingNodeId']]
        if n['parent'] is None or nodes[n['parent']]['parent'] is not None:raise ValueError('Provider sizing node must be a real root-direct content boundary')
        current=observed.get(n['name']);slot=copy.deepcopy(current['slot']['properties']) if current else {}
        for k,v in n['nativeSlot'].items():slot[k]=legacy._merge_observed(slot[k],v,k) if k in slot else copy.deepcopy(v)
        ld=slot.get('layoutData',{});a=ld.get('anchors',{});o=ld.get('offsets',{})
        if ps['contentSizing']=='fixed-footprint':
            if slot.get('bAutoSize') is not False or a.get('minimum')!=a.get('maximum') or [o.get('right'),o.get('bottom')]!=ps['visibleSize']:raise ValueError('Fixed visible footprint must match actual/target root-direct non-AutoSize Canvas content geometry')
        else:
            if ps['visibleSize']!=ps['targetSize'] or slot.get('bAutoSize') is not False or a!={'minimum':{'x':0,'y':0},'maximum':{'x':1,'y':1}} or any(o.get(edge)!=0 for edge in ('left','top','right','bottom')):raise ValueError('Fill-host provider must have an explicit zero-offset full-fill root-direct content boundary')
    return ps


def _designer_mode_operation(layout, observed, spec_path=None, seen=()):
    profile=layout['profile'];target=profile.get('designSizeModeTarget',profile['designSizeMode'])
    if 'designSizeModeTarget' not in profile:return None
    if layout['asset']['name'].startswith('umg_') and target!='FillScreen':raise ValueError('umg_ assets must target FillScreen')
    if target=='Desired':
        proof=profile.get('desiredSizeProof');nodes,_=_nodes(layout)
        if proof and proof['nodeId'] is None:
            if spec_path is None:raise ValueError('Inherited Desired proof requires physical layout evidence')
            if asset_path(layout) in seen:raise ValueError('Inherited Desired proof cycle')
            ps=_provider_sizing_proof(layout,observed,spec_path)
            if ps['rootSizingNodeId'] is not None or ps['targetSize']!=proof['size']:raise ValueError('Inherited Desired size differs from verified parent sizing chain')
            sm=_snapshot_module();parent=sm.read_bound(ps['inheritedProviderLayout'],spec_path);ppath=sm.bound_path(ps['inheritedProviderLayout'],spec_path)
            _,_,pobserved=_baseline(parent,ppath)
            if parent['profile'].get('designSizeModeTarget')!='Desired' or not parent['profile'].get('desiredSizeProof'):raise ValueError('Inherited Desired requires explicit reviewed Desired mode and positive size proof in parent Layout')
            _designer_mode_operation(parent,pobserved,ppath,seen+(asset_path(layout),))
            if target==profile['designSizeMode']:return None
            return {'id':'set-designer-mode','kind':'set-designer-mode','assetPath':asset_path(layout),'before':profile['designSizeMode'],'after':target}
        if not proof or proof['nodeId'] not in nodes:raise ValueError('Explicit Desired migration requires a real positive root-direct sizing node')
        n=nodes[proof['nodeId']];rs=_reparent_map(layout);par=_final_parent(n,rs)
        if par is None or _final_parent(nodes[par],rs) is not None:raise ValueError('Desired proof must be a direct child of the actual root')
        current=observed.get(n['name']);slot=copy.deepcopy(current['slot']['properties']) if current else {}
        targets=rs[n['id']]['nativeSlot'] if n['id'] in rs else n['nativeSlot']
        for k,v in targets.items():slot[k]=legacy._merge_observed(slot[k],v,k) if k in slot else copy.deepcopy(v)
        dims=None
        ld=slot.get('layoutData',{})
        if slot.get('bAutoSize') is False and ld.get('anchors',{}).get('minimum')==ld.get('anchors',{}).get('maximum') and ld.get('anchors'):
            dims=[ld['offsets']['right'],ld['offsets']['bottom']]
        if n['classPath']=='/Script/UMG.SizeBox':
            props=copy.deepcopy(current['properties']) if current else {}
            for k,v in n['nativeProperties'].items():props[k]=legacy._merge_observed(props[k],v,k) if k in props else copy.deepcopy(v)
            if props.get('bOverride_WidthOverride') is True and props.get('bOverride_HeightOverride') is True:dims=[props.get('widthOverride'),props.get('heightOverride')]
        if dims is None or any(type(v) not in (int,float) or v<=0 for v in dims) or dims!=proof['size']:raise ValueError('Desired proof does not match positive actual/target fixed sizing; inherited chains need separate evidence capability')
    elif 'desiredSizeProof' in profile:raise ValueError('Desired-size proof supplied for non-Desired migration')
    if target==profile['designSizeMode']:return None
    return {'id':'set-designer-mode','kind':'set-designer-mode','assetPath':asset_path(layout),'before':profile['designSizeMode'],'after':target}


def _validate_structure(layout, asset, observed, spec_path):
    sm=_snapshot_module();nodes,names=_nodes(layout);reparents=_reparent_map(layout)
    if {n['name'] for n in layout['nodes']}!=set(observed):raise ValueError('Every actual existing UObject node must be covered exactly once')
    declared={w['widgetName'] for w in asset['declaredInheritedWidgets']}
    if declared&set(names):raise ValueError('Unmaterialized inherited declarations cannot become editable nodes')
    root=[]
    for n in layout['nodes']:
        _rect(n);w=observed[n['name']]
        parent=nodes[n['parent']]['name'] if n['parent'] in nodes else None
        if n['parent'] is not None and n['parent'] not in nodes:raise ValueError('Missing existing parent node')
        if n['classPath']!=w['classPath'] or n['isVariable']!=w['isVariable'] or parent!=w['parentWidgetName'] or n['slotClassPath']!=w['slot']['classPath']:raise ValueError('Existing class/variable/parent/Slot identity changed without structural declaration')
        if n['id'] not in reparents:legacy._validate_slot_metadata(n,nodes.get(n['parent']),w)
        if n['parent'] is None:root.append(n['id'])
    baseline_path=sm.bound_path(layout['baseline']['snapshot'],spec_path)
    raw=sm.read_bound(asset['rawEvidence'],baseline_path)
    if _ref(raw['tree']['info'].get('rootWidgetClass')) is not None:
        if len(root)!=1:raise ValueError('Actual own-root WidgetTree must preserve its unique root')
    else:
        if not asset['parentClassPath'].startswith('/Game/UI/UMG/'):raise ValueError('Rootless/empty WidgetTree requires actual project Widget Blueprint parent evidence')
        content_refs={_ref(s.get('contentWidget')) for s in raw['namedSlots']}
        if any(observed[nodes[i]['name']]['widgetRefPath'] not in content_refs for i in root):raise ValueError('Every composition root must be proven by actual inherited NamedSlot content evidence')
        if layout['additions'] and not layout['nodes']:raise ValueError('Cannot invent an own tree root for an inherited-only asset')
    for n in layout['additions']:
        _rect(n)
        if re.search(r'(?:^|_)(?:ai|r\d+|rev\d+)(?:_|$)',n['name'],re.I):raise ValueError('New instance names cannot contain prototype/revision tokens')
        cls=n['classPath']
        if cls not in NEW_CLASSES:
            if cls not in REUSABLE_WIDGET_CLASSES or 'reuseEvidence' not in n:raise ValueError('New class is not on the explicit common Widget whitelist or lacks actual reuse evidence')
            evidence=sm.read_bound(n['reuseEvidence'],spec_path);ep=sm.bound_path(n['reuseEvidence'],spec_path)
            sm.validate_snapshot(evidence,snapshot_path=ep,check_evidence=True)
            found=any(a['assetPath']+'.'+a['assetPath'].split('/')[-1]+'_C'==cls for a in evidence['assets'])
            if not found:raise ValueError('Reusable Widget class lacks actual bound snapshot identity')
        elif 'reuseEvidence' in n:raise ValueError('Basic UI class must not carry irrelevant reuse evidence')
        expected_prefix='Btn' if cls=='/Script/UMG.Button' else 'Img' if cls=='/Script/UIFramework.GameImage' else 'Txt' if cls=='/Script/UMG.TextBlock' else 'Sca' if cls=='/Script/UMG.ScaleBox' else 'Panel' if cls in PARENT_SLOTS else None
        if expected_prefix and not n['name'].startswith(expected_prefix):raise ValueError('New instance requires semantic '+expected_prefix+' prefix')
        validate_scale_box_fields(cls,n['nativeProperties'],require_complete=True)
        allowed=(legacy._art_module('art_editor').WRITE_PROPERTIES-COLLECTION_FIELDS)|(SCALE_BOX_FIELDS if cls=='/Script/UMG.ScaleBox' else frozenset())
        if set(n['nativeProperties'])-allowed:raise ValueError('New node property attempts binding/input/class mutation')
        if n['nativeProperties'].get('visibility') not in {'Visible','HitTestInvisible','SelfHitTestInvisible','Collapsed','Hidden'}:raise ValueError('New node must declare explicit reviewed visibility')
        if cls!='/Script/UMG.Button' and n['nativeProperties']['visibility']=='Visible' and cls in NEW_CLASSES:raise ValueError('New passive visuals/layout must not intercept input')
        font=n['nativeProperties'].get('font')
        if font is not None and ('size' not in font or type(font['size']) is not int or font['size']<=0 or font['size']%2):raise ValueError('New font must use canonical pre-lowered positive even Slate size')
    for r in layout['reparents']:
        n=nodes.get(r['nodeId'])
        if n is None or n['name'] not in observed:raise ValueError('Only existing actual widgets may reparent')
        w=observed[n['name']]
        if r['beforeParent']!=n['parent'] or r['beforeSlotClassPath']!=n['slotClassPath'] or r['afterParent']==r['beforeParent']:raise ValueError('Reparent before identity differs or action is no-op')
        if w.get('isInherited') or w.get('namedSlotHostRefPath') or n['classPath']=='/Script/UMG.NamedSlot':raise ValueError('Inherited/NamedSlot mutation is unsupported')
    for n in layout['additions']+[nodes[r['nodeId']] for r in layout['reparents']]:
        r=reparents.get(n['id']);par=r['afterParent'] if r else n['parent'];slot=r['afterSlotClassPath'] if r else n['slotClassPath'];values=r['nativeSlot'] if r else n['nativeSlot']
        if par not in nodes or PARENT_SLOTS.get(nodes[par]['classPath'])!=slot:raise ValueError('New/reparent target requires a known compatible ordinary panel')
        _slot_check(values,slot)
    counts={i:0 for i in nodes}
    for n in nodes.values():
        seen=set();cur=n['id']
        par=_final_parent(n,reparents)
        if par is not None:counts[par]+=1
        while cur is not None:
            if cur in seen or cur not in nodes:raise ValueError('Missing parent or final tree cycle')
            seen.add(cur);cur=_final_parent(nodes[cur],reparents)
    for i,count in counts.items():
        if nodes[i]['classPath'] in PARENT_SLOTS and nodes[i]['classPath'] not in MULTI_PARENTS and count>1:raise ValueError('Single-content parent would receive multiple children')
    for n in layout['additions']:
        if n['childIndex']>=counts[n['parent']]:raise ValueError('Addition childIndex exceeds final child count')
    for r in layout['reparents']:
        if r['childIndex']>=counts[r['afterParent']]:raise ValueError('Reparent childIndex exceeds final child count')
    reserved=set()
    for n in layout['additions']:
        key=(n['parent'],n['childIndex'])
        if key in reserved:raise ValueError('Two structural additions/moves reserve the same final child index')
        reserved.add(key)
    for r in layout['reparents']:
        key=(r['afterParent'],r['childIndex'])
        if key in reserved:raise ValueError('Two structural additions/moves reserve the same final child index')
        reserved.add(key)


def validate_existing_asset_update_v2(layout: Any, *, spec_path: Path | None=None) -> dict:
    errors=[]
    try:
        schema=json.loads(SCHEMA.read_text(encoding='utf-8'))
        errors=[_issue('schema',e.message,'$'+''.join('['+str(p)+']' for p in e.path)) for e in Draft202012Validator(schema).iter_errors(layout)]
        json.dumps(layout,allow_nan=False)
        if errors:return {'valid':False,'errors':errors,'warnings':[]}
        if spec_path is None:raise ValueError('Physical spec_path required for immutable evidence bindings')
        _,asset,observed=_baseline(layout,Path(spec_path))
        if layout['mode']=='production' and not asset_path(layout).startswith('/Game/UI/UMG/'):raise ValueError('Production target must remain in formal UMG folders')
        if layout['mode']=='prototype' and not asset_path(layout).startswith('/Game/UI/AIPrototype/'):raise ValueError('Prototype target must remain in AIPrototype')
        if layout['profile']['assetKind']=='screen' and layout['referenceSize']!=[2560,1440]:raise ValueError('Project screen canvas must be2560x1440')
        if layout['profile']['assetKind']=='screen' and layout['profile']['listRole']!='none':raise ValueError('A screen cannot be a list Entry/provider')
        if layout['profile']['designSizeMode']!=asset['designSizeMode']:raise ValueError('0.4 preserves actual Designer mode; migration needs separate capability')
        _validate_structure(layout,asset,observed,Path(spec_path))
        _operations(layout,observed)
        _validate_collections(layout,observed,Path(spec_path))
        _designer_mode_operation(layout,observed,Path(spec_path))
    except Exception as exc:
        errors.append(_issue('validation',str(exc)))
    return {'valid':not errors,'errors':errors,'warnings':[]}


def build_existing_asset_update_v2_plan(layout: dict, *, spec_path: Path) -> dict:
    report=validate_existing_asset_update_v2(layout,spec_path=spec_path)
    if not report['valid']:raise ValueError(json.dumps(report['errors']))
    raw=Path(spec_path).read_bytes()
    if not exact(json.loads(raw.decode('utf-8-sig')),layout):raise ValueError('Plan input must equal physical sourceSpec')
    _,asset,observed=_baseline(layout,spec_path)
    nodes,_=_nodes(layout);operations=[];rs=_reparent_map(layout)
    # Preserve unchanged siblings in original GetWidgets order. Structural
    # insertions reserve explicit final indices. Executor must append first,
    # then reconcile these exact lists, rather than guessing transient indices.
    old_children={i:[] for i in nodes}
    old_id={n['name']:n['id'] for n in layout['nodes']}
    for name in asset['widgetOrder']:
        if name in old_id:
            n=nodes[old_id[name]]
            if n['parent'] is not None:old_children[n['parent']].append(n['id'])
    final_children={i:[c for c in children if c not in rs] for i,children in old_children.items()}
    insertions={i:[] for i in nodes}
    for n in layout['additions']:insertions[n['parent']].append((n['childIndex'],n['id']))
    for r in layout['reparents']:insertions[r['afterParent']].append((r['childIndex'],r['nodeId']))
    for par,items in insertions.items():
        stable=iter(final_children[par]);count=len(final_children[par])+len(items);reserved=dict(items)
        final_children[par]=[reserved[i] if i in reserved else next(stable) for i in range(count)]
    # Add parents before children. Existing roots are never created or replaced.
    pending=list(layout['additions']);known={n['id'] for n in layout['nodes']}
    while pending:
        ready=[n for n in pending if n['parent'] in known]
        if not ready:raise ValueError('Addition dependency cycle')
        for n in ready:
            operations.append({'id':'add-widget-'+n['id'],'kind':'add-widget','assetPath':asset_path(layout),'widgetName':n['name'],'before':None,'after':copy.deepcopy(n),'parentWidgetName':nodes[n['parent']]['name'],'insertionPolicy':'append-then-reconcile-reviewed-final-order'})
            known.add(n['id']);pending.remove(n)
    for r in layout['reparents']:
        n=nodes[r['nodeId']];w=observed[n['name']]
        operations.append({'id':'reparent-widget-'+n['id'],'kind':'reparent-widget','assetPath':asset_path(layout),'widgetName':n['name'],'before':{'parentWidgetName':w['parentWidgetName'],'slot':copy.deepcopy(w['slot']),'widgetRefPath':w['widgetRefPath'],'childIndex':old_children[n['parent']].index(n['id'])},'after':{'parentWidgetName':nodes[r['afterParent']]['name'],'slot':{'classPath':r['afterSlotClassPath'],'properties':copy.deepcopy(r['nativeSlot'])},'childIndex':r['childIndex']},'insertionPolicy':'append-then-reconcile-reviewed-final-order'})
    operations.extend(_operations(layout,observed))
    mode_op=_designer_mode_operation(layout,observed,spec_path)
    if mode_op:operations.append(mode_op)
    snapshot_path=_snapshot_module().bound_path(layout['baseline']['snapshot'],spec_path)
    evidence=_snapshot_module().read_bound(asset['rawEvidence'],snapshot_path)
    return {'kind':PLAN_KIND,'version':'0.4','capability':CAPABILITY,'sourceSpec':str(spec_path),'sourceSpecSha256':hashlib.sha256(raw).hexdigest(),'assetPath':asset_path(layout),'baseline':copy.deepcopy(layout['baseline']),'executionStatus':'not-executed','executionAllowed':False,'executorContract':{'genericCreateExecutorAllowed':False,'requiresAcceptedRequirementViewBundle':True,'requiresCurrentBaselineRevalidation':True,'requiresCurrentAssetFileCAS':True,'requiresNativeSchemaDiscovery':True,'requiresPostSaveReadback':True,'requiresCompileSave':True,'requiresProtectedReferencesAndNamedSlotsUnchanged':True,'requiresWidgetOrderReconciliation':True,'snapshotVersion':'2'},'steps':[{'stepId':'existing-layout-update-only','operation':'existing_asset_layout_update','contract':CAPABILITY}],'protectedBaseline':{'protectedReferences':copy.deepcopy(asset['protectedReferences']),'referencesDigest':asset['referencesDigest'],'declaredInheritedWidgets':copy.deepcopy(asset['declaredInheritedWidgets']),'widgetOrder':copy.deepcopy(asset['widgetOrder']),'namedSlots':copy.deepcopy(evidence['namedSlots']),'sourceAsset':copy.deepcopy(asset['sourceAsset']),'originalAssetFilePath':asset['originalAssetFilePath']},'expectedRootOrder':[name for name in asset['widgetOrder'] if name in observed and observed[name]['parentWidgetName'] is None],'expectedChildOrder':{nodes[i]['name']:[nodes[c]['name'] for c in children] for i,children in final_children.items() if children},'operations':operations,'collectionCoordination':copy.deepcopy(layout['collections'])}


def build_update_plan_v2(spec_path: Path, layout: dict) -> dict:
    return build_existing_asset_update_v2_plan(layout,spec_path=spec_path)


def source_entries_v2(layout: dict, *, spec_path: Path, asset: dict, mappings: list[dict]) -> dict:
    report=validate_existing_asset_update_v2(layout,spec_path=spec_path)
    if not report['valid'] or asset.get('assetPath')!=asset_path(layout):raise ValueError('Invalid/foreign source: '+json.dumps(report['errors']))
    nodes,_=_nodes(layout);rs=_reparent_map(layout)
    selected=[m for m in mappings if m.get('assetId')==asset['id']]
    byid={m['layoutNodeId']:m for m in selected}
    if len(byid)!=len(selected) or set(byid)!=set(nodes):raise ValueError('Complete own-asset mapping required including additions')
    return {(asset_path(layout),n['name']):{'classPath':n['classPath'],'parentWidgetName':nodes[_final_parent(n,rs)]['name'] if _final_parent(n,rs) else None,'isVariable':n['isVariable'],'properties':copy.deepcopy(n['nativeProperties']),'slot':copy.deepcopy(rs[n['id']]['nativeSlot'] if n['id'] in rs else n['nativeSlot']),'requirementRefs':byid[n['id']]['requirementRefs']} for n in nodes.values()}


def validate_bundle_layout_v2(layout: dict, asset: dict, bundle: dict, requirement: dict, *, spec_path: Path, accepted_claim_ids: set[str]) -> list[dict]:
    errors=validate_existing_asset_update_v2(layout,spec_path=spec_path)['errors']
    if errors:return errors
    plans=[p for p in requirement.get('assetPlan',[]) if p.get('id')==asset.get('assetPlanId')]
    if len(plans)!=1 or plans[0].get('assetPath')!=asset_path(layout) or asset.get('assetPath')!=asset_path(layout):return [_issue('asset','Accepted assetPlan/Bundle must match target')]
    plan=plans[0];nodes,_=_nodes(layout);rs=_reparent_map(layout);added={n['id'] for n in layout['additions']}
    expected_kind='list-entry' if layout['profile']['listRole']=='entry' else layout['profile']['assetKind']
    if asset.get('assetKind')!=expected_kind:errors.append(_issue('asset-kind','Accepted asset boundary differs'))
    if plan.get('designSizeModeDecision',{}).get('mode')!=layout['profile'].get('designSizeModeTarget',layout['profile']['designSizeMode']):errors.append(_issue('designer-mode','Accepted Designer mode must match explicitly targeted/preserved mode'))
    elements={e['id']:e for e in requirement.get('uiModel',{}).get('elements',[])};owned=set(plan.get('coversElementIds',[]))
    mappings=[m for m in bundle.get('nodeMappings',[]) if m.get('assetId')==asset['id']]
    if len(mappings)!=len(nodes) or {m.get('layoutNodeId') for m in mappings}!=set(nodes):errors.append(_issue('coverage','Every existing and new node needs exactly one mapping'))
    accepted_by_node={}
    for m in mappings:
        n=nodes.get(m.get('layoutNodeId'))
        if n is None:continue
        matches=[]
        for ref in m.get('requirementRefs',[]):
            e=elements.get(ref)
            if e is None:continue
            if ref not in owned or e.get('inBuildScope') is not True or not (set(e.get('claimIds',[]))&set(m.get('claimIds',[]))&accepted_claim_ids):errors.append(_issue('acceptance','Node element is not owned/in scope/accepted: '+ref));continue
            p=e.get('properties',{});parent=nodes[n['parent']]['name'] if n['parent'] else None
            expected={'nativeProperties':n['nativeProperties'],'nativeSlot':n['nativeSlot'],'targetClassPath':n['classPath'],'observedIsVariable':n['isVariable'],'observedParentWidgetName':parent,'owningAssetPath':asset_path(layout)}
            if n['id'] in added:expected.update({'existingUpdateOperation':'add-widget','observedParentWidgetName':None,'observedIsVariable':None,'targetIsVariable':n['isVariable'],'targetParentWidgetName':parent,'targetChildIndex':n['childIndex']})
            if n['id'] in rs:
                r=rs[n['id']];expected.update({'existingUpdateOperation':'reparent-widget','targetParentWidgetName':nodes[r['afterParent']]['name'],'targetSlotClassPath':r['afterSlotClassPath'],'targetNativeSlot':r['nativeSlot'],'targetChildIndex':r['childIndex']})
            for k,v in expected.items():
                if k not in p or not exact(p[k],v):errors.append(_issue('exact-target',ref+'.'+k+' differs from native target/identity'))
            if e.get('nameHint')!=n['name']:errors.append(_issue('name','Accepted native name differs: '+ref))
            expected_role={'text':'text.label','image':'visual.image','button':'input.button'}.get(e.get('kind'))
            if expected_role and n['role']!=expected_role:errors.append(_issue('role','Accepted semantic role differs: '+ref))
            if n['id'] in added and n['acceptedRequirementRef']!=ref:errors.append(_issue('addition-acceptance','Addition acceptance reference differs'))
            matches.append(ref)
        if not matches:errors.append(_issue('target-acceptance','Every node, including unchanged nodes, needs an accepted own element'))
        accepted_by_node[n['id']]=set(matches)
        for cs in n.get('contentStateAcceptance',[]):
            if cs['acceptedRequirementRef'] not in matches:errors.append(_issue('content-state-acceptance','Text/visibility acceptance must resolve to this exact accepted element'))
    for r in layout['reparents']:
        if r['acceptedRequirementRef'] not in accepted_by_node.get(r['nodeId'],set()):errors.append(_issue('reparent-acceptance','Reparent must bind its accepted own element'))
    for c in layout['collections']:
        if c['acceptedRequirementRef'] not in accepted_by_node.get(c['nodeId'],set()):errors.append(_issue('collection-acceptance','Collection contract must bind its accepted own element'))
        else:
            e=elements[c['acceptedRequirementRef']]
            if not exact(e.get('properties',{}).get('collectionCoordination'),c):errors.append(_issue('collection-target','Full collection/provider coordination differs from accepted target'))
        providers=[a for a in bundle.get('assets',[]) if a.get('assetPath')==c['providerAssetPath']]
        _snapshot_module().bound_path(c['providerLayout'],spec_path)
        if len(providers)!=1 or providers[0].get('layoutSpecSha256')!=c['providerLayout']['sha256']:
            errors.append(_issue('provider-bundle','Coordinated provider must be present in the same fully accepted Bundle at the exact bound layout hash'))
    ps=layout['profile'].get('providerSizing')
    if ps:
        ref=ps['acceptedRequirementRef']
        e=elements.get(ref,{})
        inherited=ps['rootSizingNodeId'] is None
        accepted=(ref in owned and e.get('inBuildScope') is True and bool(set(e.get('claimIds',[]))&accepted_claim_ids) and e.get('properties',{}).get('owningAssetPath')==asset_path(layout)) if inherited else ref in accepted_by_node.get(ps['rootSizingNodeId'],set())
        if not accepted or not exact(e.get('properties',{}).get('providerSizing'),ps):errors.append(_issue('provider-acceptance','Full provider sizing/consumer variants require exact accepted own-asset evidence; inherited-only policy must not invent a node'))
        if inherited:
            parent=_snapshot_module().read_bound(ps['inheritedProviderLayout'],spec_path)
            matching=[a for a in bundle.get('assets',[]) if a.get('assetPath')==asset_path(parent)]
            if len(matching)!=1 or matching[0].get('layoutSpecSha256')!=ps['inheritedProviderLayout']['sha256']:errors.append(_issue('inherited-provider-bundle','Full actual parent provider chain must be present in the same accepted Bundle at the bound hashes'))
    proof=layout['profile'].get('desiredSizeProof')
    if proof:
        ref=proof['acceptedRequirementRef']
        e=elements.get(ref,{})
        accepted=(ref in owned and e.get('inBuildScope') is True and bool(set(e.get('claimIds',[]))&accepted_claim_ids) and e.get('properties',{}).get('owningAssetPath')==asset_path(layout)) if proof['nodeId'] is None else ref in accepted_by_node.get(proof['nodeId'],set())
        if not accepted or not exact(e.get('properties',{}).get('desiredSizeProof'),proof):errors.append(_issue('desired-proof-acceptance','Desired sizing proof requires exact accepted native or complete inherited sizing evidence'))
    for op in bundle.get('crossAssetOperations',[]):
        if asset['id'] in (op.get('sourceAssetId'),op.get('targetAssetId')):errors.append(_issue('cross-asset','This capability does not authorize cross-asset structural/EntryClass writes'))
    return errors
