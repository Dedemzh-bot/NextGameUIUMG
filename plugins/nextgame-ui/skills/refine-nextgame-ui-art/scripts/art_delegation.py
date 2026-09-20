"""Explicit request-scoped appearance choices; never a visual acceptance gate."""
from __future__ import annotations
import hashlib
from art_common import ArtError, bound_path, load_json, validate
CAPABILITY='delegated-art-choice/1'
FIELDS=('assetPath','widgetName','reference','reason','effect','effectTypeConfidence','parameterConfidence','outline','shadow')
def fail(message):raise ArtError('presentation.delegation',message)
def delegated_choices(request,request_path):
    if CAPABILITY not in request.get('capabilities',[]):
        if 'delegatedArtChoice' in request:fail('Undeclared art-choice delegation is forbidden.')
        return {}
    if 'presentation-review/1' not in request.get('capabilities',[]) or 'delegatedArtChoice' not in request:fail('Explicit capability and bound authority are required.')
    path=bound_path(request['delegatedArtChoice'],request_path)
    authority=validate(load_json(path),'delegatedArtChoice')
    if authority['requestId']!=request['requestId']:fail('Delegation belongs to another request.')
    packet=load_json(bound_path(authority['sourcePacket'],path))
    original=load_json(bound_path(authority['authorizationFile'],path))
    source=[s for s in packet.get('sources',[]) if s.get('sourceKey')==authority['sourceKey']]
    if len(source)!=1 or source[0].get('kind')!='user-text' or source[0].get('locatorKind')!='inline':fail('Original direct-user source is required.')
    message=source[0].get('content')
    if not isinstance(message,str) or authority['explicitGrantQuote'] not in message or '高保真美术还原' not in message:fail('Ordinary continuation or a method preference does not grant art-choice delegation.')
    if hashlib.sha256(message.encode('utf8')).hexdigest()!=authority['messageSha256']:fail('Exact original message hash differs.')
    if packet.get('requestId')!=request['requestId'] or message not in packet.get('userRequest',{}).get('originalText',[]):fail('Original packet request/message differs.')
    req=load_json(bound_path(request.get('target',request['baseline'])['requirement'],request_path))
    if req.get('requestId')!=request['requestId'] or req.get('inputDigest')!=packet.get('inputDigest') or message not in req.get('request',{}).get('originalText',[]):fail('Current accepted requirement does not bind the same original request.')
    if original.get('kind')!='request-scoped-user-authorization' or original.get('sourceMessage')!=message:fail('Original authorization record differs.')
    if original.get('freshEvidenceRequired') is not True or original.get('mayContinueWithoutRepeatedQuestions') is not True or original.get('mayFabricatePostResultUserMessage') is not False or original.get('mayReuseOldAssetsOrCachedPlans') is not False:fail('Fresh-evidence and no-fabrication boundaries must be explicit.')
    scope={x['assetPath'] for x in request['scope']}
    if set(authority['assetPaths'])!=scope:fail('Authority must exactly name current scoped assets.')
    result={}
    for choice in authority['texts']:
        key=(choice['assetPath'],choice['widgetName'])
        if key in result or key[0] not in scope:fail('Choice identity is duplicate or outside scope.')
        if choice['effect']=='unknown' or choice['effectTypeConfidence']=='unknown' or choice['parameterConfidence']=='unknown':fail('Delegation cannot disguise an unmade appearance choice.')
        result[key]=choice
    return result
def check_choice(item,choices):
    expected=choices.get((item['assetPath'],item['widgetName']))
    if expected is None or expected!={k:item[k] for k in FIELDS}:fail('Delegated presentation must equal the exact bound coordinator choice, preserving source confidence.')
    if item['confirmations']:fail('A delegated choice cannot impersonate a direct-user confirmation.')
