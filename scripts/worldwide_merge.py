"""Merge exact public identities and retain every sanitized source assertion.
No fuzzy names, inferred translations, base-edition substitution or ownership data.
"""
from collections import defaultdict,Counter
import hashlib,json,re
from pathlib import Path
from worldwide_sources import norm,platform_type,type_name,VITA,GAME_TYPES

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v,compact=False):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.part');t.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=None if compact else 2)+'\n',encoding='utf-8');t.replace(p)
def region(tid):return {'PCSA':'USA','PCSE':'USA','PCSB':'EUR','PCSF':'EUR','PCSC':'JPN','PCSG':'JPN','PCSD':'ASIA','PCSH':'ASIA'}.get(tid[:4],'unknown')
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def source_anomalies(rows):
    """Preserve conflicting source identifiers; never infer a parent title ID."""
    anomalies=[]
    for row in rows:
        match=re.match(r'^[A-Z]{2}\d{4}-([A-Z]{4}\d{5})_',row.get('content_id',''))
        if match and match[1]!=row['title_id']:
            anomalies.append({'kind':'declared_title_id_content_id_disagreement','declared_title_id':row['title_id'],'content_id_title_id':match[1],'content_id':row['content_id'],'content_type':row['content_type'],'source':row['source'],'source_record_id':row['source_record_id'],'evidence_url':row['evidence_url'],'automatic_parent_or_runtime_join_allowed':False,'disposition':'Both source claims retained unchanged; no inferred parent association or runtime join.'})
    return sorted(anomalies,key=lambda x:(x['source'],str(x['source_record_id'])))

PACKAGE_EDITION=re.compile(r'\b(?:limited|launch|premium|collectors?|special|bikini party)\s+(?:s\s+)?edition\b',re.I)
EDITION_WORD=re.compile(r'\bedition\b|限定|特装|初回',re.I)

def eligible_names(game,exclusions=()):
    """Provider aliases remain evidence, with edition qualifiers preserved."""
    gid=str(game['id']);primary=game['name'];yield primary,'primary',None
    package=bool(PACKAGE_EDITION.search(primary))
    for alias in game.get('alternative_names',[]):
        title=alias['name'];comment=alias.get('comment','')
        if (gid,norm(title)) in exclusions:continue
        if any(w in comment.lower() for w in ('acronym','working title','misspell','unofficial','short title')):continue
        if package and not EDITION_WORD.search(title):continue
        if primary.count('+') and title.count('+') and primary.count('+')!=title.count('+'):continue
        yield title,'alternative_name',{'id':alias['id'],'comment':comment}
    for localized in game.get('game_localizations',[]):
        title=localized.get('name')
        if not title or (gid,norm(title)) in exclusions:continue
        if package and not EDITION_WORD.search(title):continue
        if primary.count('+') and title.count('+') and primary.count('+')!=title.count('+'):continue
        yield title,'localization',{'id':localized['id'],'region':localized.get('region')}

def exact_name_index(catalog,api,exclusions=()):
    names=defaultdict(set);proof=defaultdict(list)
    for game in catalog:
        key=norm(game['name']);gid=str(game['igdb_id']);names[key].add(gid);proof[(key,gid)].append({'kind':'bundled_catalog_primary','name':game['name']})
    for game in api:
        for title,kind,extra in eligible_names(game,exclusions):
            key=norm(title);gid=str(game['id']);names[key].add(gid);proof[(key,gid)].append({'kind':'igdb_'+kind,'name':title,'provider_record':extra})
    return names,proof

def merge_additions(mapped,additions,available):
    """The accepted additive snapshot cannot replace a current identity."""
    for serial,gid in additions['serials'].items():
        if gid not in available:raise ValueError('Accepted addition references unavailable verified artwork')
        if serial in mapped and mapped[serial]['igdb_id']!=gid:raise ValueError('Additive snapshot attempted to replace current serial')
        if serial not in mapped:
            record=dict(additions['serial_metadata'][serial]);record['region']=region(serial);record['source_regions']=sorted({record.get('region','unknown')});mapped[serial]=record
    return mapped

def apply_dispositions(mapped,dispositions,available):
    for serial,decision in {**dispositions['existing'],**dispositions['additional_conflict_resolutions'],**dispositions.get('additional_reviews',{})}.items():
        gid=decision['selected_igdb_id']
        if gid is None:mapped.pop(serial,None);continue
        if gid not in available:raise ValueError('Reviewed disposition references unavailable artwork')
        title=decision.get('selected_title') or available[gid].get('name') or serial
        mapped[serial]={'igdb_id':gid,'title':title,'region':region(serial),'match_method':'public_edition_platform_review','evidence':[{'kind':'public_identity_review','source':u,'title':title} for u in decision['evidence']],'review_rationale':decision['rationale'],'artwork_scope':'game','regional_artwork_verified':False}
    return mapped

def build(root,mapped,prior_unresolved):
    """Return identity metadata; write complete worldwide evidence and coverage."""
    folder=root/'data/worldwide'
    if not (folder/'source-manifest.json').exists():return mapped,prior_unresolved,None
    catalog=read(root/'data/catalog.json')['games'];assets={str(g['igdb_id']):g for g in catalog};snapshot=read(root/'data/igdb-metadata.json');api=snapshot['games'];api_by_id={str(g['id']):g for g in api}
    exclusions={(str(x['igdb_id']),norm(x['name'])) for x in read(root/'data/alias-exclusions.json')['exclusions']}
    names,proof=exact_name_index(catalog,api,exclusions)
    accepted=read(folder/'accepted-additions.json');decisions=read(folder/'review-dispositions.json')
    expected={r['title_id'] for r in read(folder/'initial-existing-review.json')}
    if set(decisions['existing'])!=expected:raise ValueError('Every initial existing review requires exactly one disposition')
    # Capture the accepted initial snapshot before applying explicit corrections.
    merge_additions(mapped,accepted,assets)
    apply_dispositions(mapped,decisions,{**api_by_id,**assets})
    manual={**read(root/'data/reviewed-mappings.json'),**decisions['existing'],**decisions['additional_conflict_resolutions'],**decisions.get('additional_reviews',{})}
    blocked={s:d for s,d in manual.items() if 'selected_igdb_id'in d and d['selected_igdb_id'] is None}
    excluded=set(decisions['excluded_new'])
    groups=defaultdict(list);source_meta=[];changes=[]
    for p in sorted((folder/'sources').glob('*.json')):
        doc=read(p);source_meta.append(doc['source'])
        canonical=json.dumps(doc['records'],sort_keys=True,ensure_ascii=False).encode()
        if doc['source'].get('sanitized_records_sha256') and hashlib.sha256(canonical).hexdigest()!=doc['source']['sanitized_records_sha256']:raise ValueError('Sanitized source snapshot hash mismatch')
        for original in doc['records']:
            row=dict(original,source=doc['source']['id']);kind=platform_type(row['title_id'],type_name(row['title'],row.get('source_content_type',row['content_type'])))
            if kind!=row['content_type']:changes.append({'source':row['source'],'source_record_id':row['source_record_id'],'title_id':row['title_id'],'previous_type':row['content_type'],'corrected_type':kind})
            row['content_type']=kind;groups[(row['title_id'],kind)].append(row)
    by_serial=defaultdict(list);records=[]
    for (serial,kind),rows in sorted(groups.items()):
        record={'title_id':serial,'content_type':kind,'titles':sorted({r['title'] for r in rows}),'regions':sorted({r['region'] for r in rows}),'source_records':rows,'evidence':sorted({r['evidence_url'] for r in rows})};records.append(record);by_serial[serial].append(record)
    candidates={};candidate_proof={};runtime_conflicts=[]
    for serial,rs in by_serial.items():
        if not VITA.fullmatch(serial):
            for record in rs:record['identity_status']='outside_native_vita_scope';record['missing_reason']='legacy_or_other_platform'
            continue
        base=[x for x in rs if x['content_type'] in GAME_TYPES];ids=set();hits=[]
        for record in base:
            for row in record['source_records']:
                for title in (row['title'],row.get('alternate_title','')):
                    if not title:continue
                    found=names.get(norm(title),set());ids.update(found)
                    for gid in found:hits.append({'igdb_id':gid,'source':row['source'],'source_record_id':row['source_record_id'],'title':title,'name_evidence':proof[(norm(title),gid)]})
        candidates[serial]=ids;candidate_proof[serial]=hits
        if serial in blocked or serial in excluded:mapped.pop(serial,None);continue
        if serial in manual:continue
        if len(ids)>1 or serial in mapped and ids and mapped[serial]['igdb_id'] not in ids:
            if serial in mapped:runtime_conflicts.append({'title_id':serial,'previous_igdb_id':mapped[serial]['igdb_id'],'candidate_igdb_ids':sorted(ids),'reason':'new_authoritative_alias_or_source_identity_conflict'})
            mapped.pop(serial,None);continue
        if len(ids)==1:
            gid=next(iter(ids));ev=[{'kind':'worldwide_exact_igdb_identity','source':r['evidence_url'],'title':r['title']} for b in base for r in b['source_records']]
            mapped[serial]={'igdb_id':gid,'title':base[0]['titles'][0],'region':region(serial),'source_regions':sorted({r['region'] for b in base for r in b['source_records']}),'match_method':'exact_full_igdb_primary_alternative_or_localized_name','evidence':ev,'igdb_name_evidence':hits,'artwork_scope':'game','regional_artwork_verified':False}
    # A provider-confirmed exact identity without artwork stays known but absent from runtime index.
    new_art=[];missing_art=[]
    for serial,meta in mapped.items():
        gid=meta['igdb_id'];meta['content_types']=sorted(r['content_type'] for r in by_serial.get(serial,[]));meta['source_regions']=sorted({v for r in by_serial.get(serial,[]) for v in r['regions']});meta['region']=region(serial)
        meta['regional_artwork_verified']=False
        if gid not in assets:
            game=api_by_id.get(gid)
            if game and game.get('cover'):new_art.append({'title_id':serial,'igdb_id':gid,'name':game['name'],'cover':game['cover'],'identity_method':meta['match_method'],'evidence':meta['evidence']})
            else:missing_art.append({'title_id':serial,'igdb_id':gid,'reason':'igdb_cover_not_available','evidence':meta['evidence']})
    unresolved=[]
    for serial,rs in by_serial.items():
        if not VITA.fullmatch(serial):continue
        base=[r for r in rs if r['content_type'] in GAME_TYPES]
        if serial in blocked:reason=blocked[serial]['reason']
        elif serial in excluded:reason='excluded_unresolved_source_content_or_edition_conflict'
        elif serial in mapped and mapped[serial]['igdb_id'] in assets:reason=None
        elif serial in mapped:reason='igdb_cover_not_available' if not api_by_id.get(mapped[serial]['igdb_id'],{}).get('cover') else 'verified_new_artwork_pending'
        elif len(candidates.get(serial,set()))>1:reason='ambiguous_or_conflicting_exact_igdb_identities'
        else:reason='no_exact_igdb_identity'
        if base and reason:unresolved.append({'title_id':serial,'titles':sorted({t for r in base for t in r['titles']}),'candidate_igdb_ids':sorted(candidates.get(serial,set())),'reason':reason})
        for record in rs:
            if not VITA.fullmatch(serial):record['identity_status']='outside_native_vita_scope';record['missing_reason']='legacy_or_other_platform'
            elif record['content_type'] not in GAME_TYPES:record['identity_status']='typed_non_base_content';record['missing_reason']='non_base_content_type'
            elif serial in mapped:
                record['mapped_igdb_id']=mapped[serial]['igdb_id'];record['identity_status']='matched';record['artwork_status']='available' if mapped[serial]['igdb_id'] in assets else 'not_available';record['missing_reason']=reason;record['match_method']=mapped[serial]['match_method']
            else:record['identity_status']='unresolved';record['missing_reason']=reason
            if serial in decisions['existing']:record['review_disposition']=decisions['existing'][serial]
            elif serial in decisions.get('additional_reviews',{}):record['review_disposition']=decisions['additional_reviews'][serial]
            record['candidate_igdb_ids']=sorted(candidates.get(serial,set())) if record['content_type'] in GAME_TYPES else []
    def stats(rs):
        native=[r for r in rs if VITA.fullmatch(r['title_id'])];base=[r for r in native if r['content_type'] in GAME_TYPES]
        return {'records':len(rs),'title_ids':len({r['title_id'] for r in rs}),'native_base_title_ids':len({r['title_id'] for r in base}),'base_identity_matched':len({r['title_id'] for r in base if r.get('identity_status')=='matched'}),'base_artwork_available':len({r['title_id'] for r in base if r.get('artwork_status')=='available'}),'base_identity_unresolved':len({r['title_id'] for r in base if r.get('identity_status')=='unresolved'}),'missing_reasons':dict(Counter(r.get('missing_reason') or 'mapped' for r in native))}
    base=[r for r in records if VITA.fullmatch(r['title_id']) and r['content_type'] in GAME_TYPES]
    coverage={'schema_version':2,'scope':'Sourced worldwide native Vita identity union; region/title-ID/content-type/edition evidence retained. Not proof of worldwide historical completeness.','complete_worldwide':False,'source_assertions':sum(len(r['source_records']) for r in records),'content_ids':len({x['content_id'] for r in records for x in r['source_records'] if x.get('content_id')}),'native_vita_title_ids':len({r['title_id'] for r in records if VITA.fullmatch(r['title_id'])}),'native_base_title_ids':len({r['title_id'] for r in base}),'runtime_title_ids_with_artwork':sum(m['igdb_id'] in assets for m in mapped.values()),'native_base_status':stats(base),'by_source':{s['id']:stats([r for r in records if any(x['source']==s['id'] for x in r['source_records'])]) for s in source_meta},'by_region':{region:stats([r for r in records if region in r['regions']]) for region in sorted({x for r in records for x in r['regions']})},'by_type':{kind:stats([r for r in records if r['content_type']==kind]) for kind in sorted({r['content_type'] for r in records})},'by_missing_reason':dict(Counter(r.get('missing_reason') or 'mapped' for r in base)),'existing_review_dispositions':len(decisions['existing']),'additional_alias_conflicts':runtime_conflicts,'source_gaps':['No verified complete official Sony worldwide historical native Vita title-ID feed.','Current No-Intro bulk export unavailable in the source-worker session; dated libretro snapshots and documentary missing list are supplementary.','GameTDB returned403; no verified Vita bulk feed established.','Redump optical-disc sources do not establish a native Vita cartridge union.','Community sources can omit delisted/regional/retail-only/undumped releases. IGDB aliases do not prove packaging or entitlement.'],'igdb_metadata_source':{'games':snapshot['game_count'],'source':snapshot['source'],'fetched_at':snapshot['fetched_at'],'sha256':digest(root/'data/igdb-metadata.json'),'authentication':'Existing configuration used in memory only; no credential blocker; public snapshots reproduce identity joins without credentials.'},'artwork_scope':'game; regional packaging not verified'}
    write(folder/'worldwide-identities.json',{'schema_version':2,'records':records},True);write(folder/'coverage.json',coverage);write(folder/'unmatched-native-identities.json',{'records':unresolved});write(folder/'new-artwork-plan.json',{'records':new_art});write(folder/'missing-artwork.json',{'records':missing_art});write(folder/'additional-alias-conflicts.json',{'records':runtime_conflicts});write(folder/'source-manifest.json',source_meta)
    write(folder/'source-anomalies.json',{'schema_version':1,'records':source_anomalies([x for r in records for x in r['source_records']]),'policy':'Source contradictions remain explicit; neither identifier is corrected or used to infer parent associations.'})
    return mapped,unresolved,coverage
