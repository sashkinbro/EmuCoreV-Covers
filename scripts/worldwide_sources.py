"""Public metadata-only Vita identity reconciliation; never saves package/license columns."""
from __future__ import annotations
import argparse, collections, csv, datetime, hashlib, io, json, pathlib, re, unicodedata, urllib.request, urllib.error, urllib.parse, html, sqlite3
BASE=pathlib.Path(__file__).resolve().parents[1]/'data/worldwide'
PREFIX_REGION={'PCSA':'US','PCSE':'US','PCSB':'EU','PCSF':'EU','PCSC':'JP','PCSG':'JP','PCSD':'ASIA','PCSH':'ASIA'}
VITA=re.compile(r'^PCS[ABCDEFGH]\d{5}$')
CID=re.compile(r'^[A-Z]{2}\d{4}-([A-Z]{4}\d{5})_[A-Z0-9]{2}-[A-Z0-9]{16}$')
SAFE_KEYS={'title_id','title','region','content_type','content_id','parent_title_id','alternate_title','version','evidence_url','source_record_id','type_evidence','region_method','source_content_type','source_region'}
CATEGORIES={1:'game',2:'utility',3:'demo',4:'retail_game',5:'unlock',101:'dlc',102:'dlc',103:'other_game_related',201:'theme',301:'avatar',401:'update',402:'update',501:'promotional',601:'playstation_mobile'}

def dump(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True); compact=path.name=='worldwide-identities.json' or path.parent.name=='sources'; path.write_text(json.dumps(obj,ensure_ascii=False,indent=None if compact else 2,sort_keys=True)+'\n',encoding='utf-8')
def digest(b):return hashlib.sha256(b).hexdigest()
def norm(s):
 s=unicodedata.normalize('NFKD',s.replace('®','').replace('™','').replace('℠','')).casefold()
 s=''.join(c for c in s if not unicodedata.combining(c))
 s=s.replace('&',' and ').replace('+',' + ')
 return ' '.join(re.sub(r'[^\w+]+',' ',s,flags=re.UNICODE).split())
def serial(s):
 s=re.sub(r'[\s-]','',s.upper())
 return s if re.fullmatch(r'[A-Z]{4}\d{5}',s) else None

def platform_type(tid,kind):
 if kind in ('legacy_psp','legacy_ps1','playstation_mobile'):return kind
 if VITA.fullmatch(tid):return kind
 if tid.startswith('NPOA') or tid.startswith('NPNA') or tid.startswith('NPPA'):return 'playstation_mobile'
 if tid.startswith(('NPUJ','NPEF','NPJJ','SLUS','SLES','SLPS','SCUS','SCES','SCPS')):return 'legacy_ps1'
 if tid.startswith(('NPUH','NPEG','NPUG','NPEZ','NPJG','NPJH','ULUS','ULES','ULJM','ULJS','UCUS','UCES','UCJS')):return 'legacy_psp'
 return 'other_platform_or_system'

def type_name(title,kind):
 # Trial can be part of a full game's title (Urban Trial Freestyle).
 # Preserve publisher source type unless an explicit demo/trial-version marker exists.
 if kind in ('game','base_application','reported_application','retail_game') and re.search(r'\btrial\s*(?:&|and)\s*unlock\b',title,re.I):return 'trial_and_unlock'
 if kind in ('game','base_application','reported_application','retail_game') and re.search(r'\bdemo\b|\btrial\s+(?:version|edition)\b|\b(?:free\s+)?trial\s*[)\]]?\s*$|体験版|體驗版|试玩版|체험판',title,re.I):return 'demo'
 return kind

def record(tid,title,kind,**kw):
 tid=serial(tid or '')
 if not tid or not title:return None
 title=re.sub(r'https?://[^\s)\]]+','[URL omitted]',title).strip()
 if 'alternate_title' in kw and kw['alternate_title']:
  kw['alternate_title']=re.sub(r'https?://[^\s)\]]+','[URL omitted]',kw['alternate_title']).strip()
 if kw.get('content_id'):
  kw['content_id']=kw['content_id'].strip()
  if not CID.fullmatch(kw['content_id']):kw.pop('content_id')
 kw['source_content_type']=kind
 kind=platform_type(tid,type_name(title,kind))
 region=kw.pop('region',None)
 kw['region_method']='explicit source region' if region else 'title ID prefix convention'
 if region:kw['source_region']=region
 region={'USA':'US','EUR':'EU','Europe':'EU','Japan':'JP','Asia':'ASIA','Korea':'KR'}.get(region,region)
 r={'title_id':tid,'title':title.strip(),'region':region or PREFIX_REGION.get(tid[:4],'UNKNOWN'),'content_type':kind,**kw}
 return {k:v for k,v in r.items() if k in SAFE_KEYS and v not in (None,'')}

def fetch(url):
 # Only metadata endpoints supplied by the source publisher. No derived URLs are followed.
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 EmuCoreV-metadata-reconciliation/1.0','Origin':'https://vita3k.org','Referer':'https://nopaystation.com/'})
 with urllib.request.urlopen(req,timeout=60) as r:
  h=hashlib.sha256(); lines=[]
  for line in r:
   h.update(line); lines.append(line)
  return b''.join(lines),h.hexdigest()

def parse_nps(raw,kind,url):
 return parse_nps_lines(io.StringIO(raw.decode('utf-8-sig')),kind,url)[0]

def parse_nps_lines(lines,kind,url):
 rows=[];rejected=[]
 for i,d in enumerate(csv.DictReader(lines,delimiter='\t'),start=2):
  # Allowlist immediately; no raw row can leave this function.
  keep={k:d.get(k,'') for k in ('Title ID','Name','Region','Content ID','Original Name','Update Version')}
  d.clear()
  r=record(keep['Title ID'],keep['Name'],kind,region=keep['Region'],content_id=keep['Content ID'],alternate_title=keep['Original Name'],version=keep['Update Version'],source_record_id=str(i),evidence_url=url,type_evidence='publisher metadata feed category')
  if r: rows.append(r)
  else:rejected.append({'title_id':keep['Title ID'],'title':re.sub(r'https?://[^\s)\]]+','[URL omitted]',keep['Name']),'source_record_id':str(i),'evidence_url':url,'missing_reason':'invalid_title_id'})
 return rows,rejected

def fetch_nps(url,kind):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 EmuCoreV-metadata-reconciliation/1.0','Referer':'https://nopaystation.com/'})
 h=hashlib.sha256();n=0
 with urllib.request.urlopen(req,timeout=60) as response:
  def lines():
   nonlocal n
   for line in response:
    h.update(line);n+=len(line)
    yield line.decode('utf-8-sig')
  rows,rejected=parse_nps_lines(lines(),kind,url)
 return rows,rejected,h.hexdigest(),n

def sql_values(text):
 # Restricted SQL literal tokenizer. SQL is never executed.
 # sqlite .dump encodes embedded line breaks as replace(literal, '\n', char(10)).
 def unreplace(m):
  value=m[1].replace("''", "'").replace(m[2].replace("''", "'"),chr(int(m[3])))
  return "'"+value.replace("'", "''")+"'"
 text=re.sub(r"replace\('((?:[^']|'')*)','((?:[^']|'')*)',char\((10|13)\)\)",unreplace,text)
 out=[]; pos=0
 token=re.compile(r"\s*(?:'((?:[^']|'')*)'|(NULL)|(-?\d+))\s*(,|$)",re.S)
 while pos<len(text):
  m=token.match(text,pos)
  if not m:raise ValueError('Unsupported SQL literal; raw data omitted')
  out.append(m[1].replace("''", "'") if m[1] is not None else (None if m[2] else int(m[3])))
  pos=m.end()
 return out

def parse_vitadb(raw,url):
 rows=[]; apps={}; updates=[]
 for n,line in enumerate(raw.decode('utf-8-sig').splitlines(),start=1):
  m=re.fullmatch(r'INSERT INTO (Apps|Updates) VALUES\((.*)\);',line)
  if not m:continue
  v=sql_values(m[2])
  if m[1]=='Apps':
   tid,title,alt,cid,parent,cat=v[:6]
   r=record(tid,title,CATEGORIES.get(cat,'unknown'),alternate_title=alt,content_id=cid,parent_title_id=(CID.fullmatch(parent)[1] if parent and CID.fullmatch(parent) else None),source_record_id=str(n),evidence_url=url,type_evidence='VitaDB category '+str(cat))
   if r: rows.append(r); apps[cid]=r
  else:updates.append((v[0],str(v[1]),str(n)))
  v.clear()
 for cid,ver,n in updates:
  a=apps.get(cid)
  if a:
   r=record(a['title_id'],a['title'],'update',content_id=cid,version=ver,region=a['region'],parent_title_id=a['title_id'],source_record_id=n,evidence_url=url,type_evidence='VitaDB Updates table')
   if r: rows.append(r)
 return rows

def parse_dat(raw,url):
 text=raw.decode('utf-8-sig'); rows=[]
 # libretro DAT publisher uses one metadata game block per line group.
 for n,block in enumerate(re.split(r'(?m)^game \(\s*$',text)[1:],start=1):
  fields=dict(re.findall(r'^\s*(name|serial|region)\s+"([^"]*)"',block,re.M))
  title=fields.get('name',''); regions=re.findall(r'\(([^()]*)\)',title)
  region=next((x for x in regions if x in ['USA','Europe','Japan','Asia','Korea','China','World']),None)
  # Only source metadata tags, never editions, '+' signs or sequel tokens.
  title=re.sub(r'\s*\((USA|Europe|Japan|Asia|Korea|China|World)(, [^()]*)?\)','',title)
  title=re.sub(r'\s*\(([A-Z][a-z])(?:,[A-Z][a-z])*\)','',title)
  for tid in re.findall(r'[A-Z]{4}-?\d{5}',fields.get('serial','')):
   r=record(tid,title,'retail_game' if '(PSN)' not in url else 'base_application',region={'USA':'US','Europe':'EU','Japan':'JP'}.get(region,region),source_record_id=str(n),evidence_url=url,type_evidence='libretro No-Intro metadata DAT')
   if r:rows.append(r)
 return rows


def parse_nointro_wiki(raw,url):
 # Public documentary list: headings carry utility/soundtrack distinctions.
 text=raw.decode('utf-8-sig');rows=[];kind='base_application'
 for n,part in enumerate(re.split(r'(<h[234][^>]*>.*?</h[234]>|<pre[^>]*>.*?</pre>)',text,flags=re.S),start=1):
  clean=html.unescape(re.sub('<[^>]+>','',part))
  if part.startswith('<h'):
   kind='utility' if 'Software Applications' in clean else ('soundtrack' if 'Soundtrack' in clean else 'base_application')
  if not part.startswith('<pre'):continue
  for j,line in enumerate(clean.splitlines(),start=1):
   m=re.search(r'(PCS[A-H]-?\d{5})',line)
   if not m:continue
   title=line[:m.start()].strip()
   title=re.sub(r'\s*\[(.*?)\]','',title).strip()
   title=re.sub(r'\s*\((AS|KO|JP)\)','',title).strip()
   # Remove source preservation-status notes, retain actual edition/version qualifiers.
   title=re.sub(r'\s*\(Dump avaliable in [^)]*\)','',title).strip()
   rec=record(m[1],title,kind,source_record_id=f'{n}:{j}',evidence_url=url,type_evidence='No-Intro documented undumped/delisted list section')
   if rec:rows.append(rec)
 return rows

def fetch_sources(covers):
 specs=[]
 for pending in ('','pending/'):
  for typ,kind in [('GAMES','base_application'),('DEMOS','demo'),('DLCS','dlc'),('THEMES','theme'),('UPDATES','update')]:
   specs.append(('nps_'+('pending_' if pending else '')+typ.lower(),'https://nopaystation.com/tsv/'+pending+'PSV_'+typ+'.tsv','nps',kind,'NoPayStation community contributors; no explicit metadata redistribution license identified'))
 for name,kind in [('PSP_GAMES','legacy_psp'),('PSX_GAMES','legacy_ps1'),('PSM_GAMES','playstation_mobile')]:
  specs.append(('nps_'+name.lower(),'https://nopaystation.com/tsv/'+name+'.tsv','nps',kind,'NoPayStation community contributors; no explicit metadata redistribution license identified'))
 specs.append(('nointro_documented_missing','https://wiki.no-intro.org/index.php?title=Sony_-_PlayStation_Vita_undumped','wiki',None,'No-Intro Wiki contributors; documentary list, last edited 2026-02-10; source data rights apply.'))
 specs.append(('vitasmith_vitadb','https://raw.githubusercontent.com/VitaSmith/VitaDB/master/VitaDB.sql','vitadb',None,'VitaSmith/VitaDB repository GPL-3.0; source metadata derived from Sony/community. Preserve attribution; artwork rights separate.'))
 for name in ['Sony - PlayStation Vita.dat','Sony - PlayStation Vita (PSN).dat']:
  specs.append(('libretro_nointro_'+('psn' if '(PSN)' in name else 'retail'),'https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/no-intro/'+urllib.parse.quote(name),'dat',None,'libretro-database/No-Intro contributors; per-source metadata licensing not assumed from software license. Preserve attribution.'))
 sources=[]
 for sid,url,parser,kind,license_note in specs:
  meta={'id':sid,'url':url,'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'attribution':license_note,'official_sony_feed':False}
  try:
   if parser=='nps':rows,rejected,h,nbytes=fetch_nps(url,kind)
   else:
    raw,h=fetch(url);nbytes=len(raw);rejected=[]
    rows={'vitadb':lambda:parse_vitadb(raw,url),'dat':lambda:parse_dat(raw,url),'wiki':lambda:parse_nointro_wiki(raw,url)}[parser]()
    del raw
   meta.update(status='ok',raw_response_sha256=h,source_bytes=nbytes,rejected_invalid_title_id_records=len(rejected),records=len(rows),unique_title_ids=len({r['title_id'] for r in rows}),sanitized_records_sha256=digest(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()))
   dump(BASE/'sources'/f'{sid}.json',{'source':meta,'records':rows,'rejected_records':rejected})
  except Exception as e:
   meta.update(status='unavailable',error_class=type(e).__name__,http_status=getattr(e,'code',None),records=0,unique_title_ids=0)
   dump(BASE/'sources'/f'{sid}.json',{'source':meta,'records':[]})
  sources.append(meta); print(sid,meta['status'],meta.get('records',0),flush=True)
 raw=(covers/'data/vita3k-commercial.json').read_bytes(); rows=[]
 for x in json.loads(raw)['list']:
  r=record(x['titleId'],x['name'],'reported_application',source_record_id=str(x['issueId']),evidence_url='https://github.com/Vita3K/compatibility/issues/'+str(x['issueId']),type_evidence='Compatibility report; does not prove full game entitlement')
  if r:rows.append(r)
 meta={'id':'vita3k','url':'https://api.vita3k.org/list/commercial','fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'raw_response_sha256':digest(raw),'status':'ok','records':len(rows),'unique_title_ids':len({r['title_id'] for r in rows}),'attribution':'Vita3K compatibility report contributors; repository license/individual report rights apply. Existing sanitized snapshot.','official_sony_feed':False}
 dump(BASE/'sources/vita3k.json',{'source':meta,'records':rows});sources.append(meta)
 # Existing supplemental public software title assertions are distinct from the private inventory.
 raw=(covers/'data/title-assertions.json').read_bytes(); rows=[]
 for tid,x in json.loads(raw).items():
  rec=record(tid,x['title'],'reported_application',source_record_id=tid,evidence_url=x['source'],type_evidence='Supplemental public TITLE_ID/TITLE identity assertion; no full-game entitlement claim')
  if rec:rows.append(rec)
 meta={'id':'public_title_assertions','url':'PARAM.SFO public TITLE_ID/TITLE identity assertions','status':'ok','fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'raw_response_sha256':digest(raw),'records':len(rows),'unique_title_ids':len({r['title_id'] for r in rows}),'attribution':'Existing sanitized public software identity assertions; no archive paths or ownership inventory included.','official_sony_feed':False}
 dump(BASE/'sources/public_title_assertions.json',{'source':meta,'records':rows});sources.append(meta)
 dump(BASE/'source-manifest.json',sources)

GAME_TYPES={'game','base_application','reported_application','retail_game'}
def reconcile(covers,database=None):
 catalog=json.loads((covers/'data/catalog.json').read_text(encoding='utf-8'))['games']; byname=collections.defaultdict(set)
 for g in catalog:byname[norm(g['name'])].add(str(g['igdb_id']))
 overrides=json.loads((covers/'data/reviewed-mappings.json').read_text(encoding='utf-8'))
 # Exact duplicate name disambiguated only by the immutable source catalog's explicit platform statement.
 db=pathlib.Path(database) if database else None
 platform_path=BASE/'platform-disambiguation.json'
 platform_evidence=json.loads(platform_path.read_text(encoding='utf-8')) if platform_path.exists() else {}
 if db and db.exists():
  con=sqlite3.connect(db.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
  for gid,name,summary in con.execute('SELECT igdb_id,name,summary FROM games'):
   if len(byname[norm(name)])>1 and summary and summary.strip()=='PlayStation Vita port of Madden NFL 13.':
    platform_evidence[norm(name)]={'igdb_id':str(gid),'title':name,'summary':summary,'source':'Bundled immutable IGDB metadata snapshot','public_platform_evidence':'https://www.esrb.org/ratings/32326/madden-nfl-13/'}
  con.close()
 dump(BASE/'platform-disambiguation.json',platform_evidence)
 groups=collections.defaultdict(list); source_coverage={}
 for f in sorted((BASE/'sources').glob('*.json')):
  d=json.loads(f.read_text(encoding='utf-8')); sid=d['source']['id']; rr=d['records']
  source_coverage[sid]={'records':len(rr),'title_ids':len({r['title_id'] for r in rr}),'regions':dict(collections.Counter(r['region'] for r in rr)),'types':dict(collections.Counter(r['content_type'] for r in rr))}
  for r in rr:groups[(r['title_id'],r['content_type'])].append({'source':sid,**r})
 records=[]; candidates=collections.defaultdict(list)
 for (tid,kind),assertions in sorted(groups.items()):
  titles=sorted({x['title'] for x in assertions}); regions=sorted({x['region'] for x in assertions}); conflicts=[]
  rr={'title_id':tid,'title':titles[0],'titles':titles,'region':regions[0] if len(regions)==1 else 'MULTIPLE','regions':regions,'content_type':kind,'source_records':assertions,'evidence':sorted({x['evidence_url'] for x in assertions}),'conflicts':conflicts}
  parents=sorted({x['parent_title_id'] for x in assertions if 'parent_title_id' in x})
  if len(parents)==1:rr['parent_title_id']=parents[0]
  elif parents:conflicts.append({'kind':'parent_conflict','values':parents})
  if not VITA.fullmatch(tid):reason='outside_vita_native_library'
  elif kind not in GAME_TYPES:reason='non_base_content_type'
  else:
   ids=set(); matches=[]
   for a in assertions:
    for title in (a['title'],a.get('alternate_title','')):
     if not title:continue
     found=byname.get(norm(title),set())
     if len(found)>1 and norm(title) in platform_evidence:found={platform_evidence[norm(title)]['igdb_id']}
     ids|=found
     if found:matches.append({'source':a['source'],'title':title,'igdb_ids':sorted(found)})
   ov=overrides.get(tid)
   if ov:
    target=str(ov['igdb_id']); rr['mapped_igdb_id']=target;rr['match_method']='existing_reviewed_title_id_override';rr['mapping_evidence']={'source':ov['source'],'title':ov['title'],'note':ov.get('note','')}
    if ids-{target}:conflicts.append({'kind':'reviewed_override_disagrees_with_exact_title','exact_candidates':sorted(ids),'reviewed_igdb_id':target})
    reason=None
   elif len(ids)==1:
    rr['mapped_igdb_id']=next(iter(ids));rr['match_method']='unique_full_normalized_title';rr['mapping_evidence']=matches;reason=None
    if any(norm(x['title']) in platform_evidence for x in matches):
     rr['match_method']='exact_title_with_explicit_vita_catalog_platform';rr['platform_evidence']=next(platform_evidence[norm(x['title'])] for x in matches if norm(x['title']) in platform_evidence)
   elif len(ids)>1:
    reason='ambiguous_or_conflicting_exact_titles';conflicts.append({'kind':'exact_title_igdb_conflict','igdb_ids':sorted(ids),'matches':matches})
   else:reason='no_exact_catalog_identity'
   if 'mapped_igdb_id' in rr:candidates[tid].append(rr)
  rr['missing_reason']=reason
  if len({norm(t) for t in titles})>1:rr['title_variants_present']=True
  records.append(rr)
 serials={};metadata={};serial_conflicts=[]
 
 for tid,rs in sorted(candidates.items()):
  ids={r['mapped_igdb_id'] for r in rs}
  if len(ids)>1:
   serial_conflicts.append({'title_id':tid,'igdb_ids':sorted(ids),'reason':'different base-content categories map to different games'})
   for r in rs:r['conflicts'].append({'kind':'serial_mapping_conflict','igdb_ids':sorted(ids)});r.pop('mapped_igdb_id',None);r['missing_reason']='serial_mapping_conflict';r['match_method']='blocked_conflict'
  else:
   serials[tid]=next(iter(ids)); metadata[tid]={'igdb_id':next(iter(ids)),'title':rs[0]['title'],'region':rs[0]['region'],'match_method':rs[0]['match_method'],'evidence':[{'kind':'worldwide_public_metadata','source':u,'title':r['title']} for r in rs for u in r['evidence']],'artwork_scope':'game','regional_artwork_verified':False,'content_types':sorted({r['content_type'] for r in records if r['title_id']==tid}),'mapping_evidence':[r.get('mapping_evidence') for r in rs],'platform_evidence':[r['platform_evidence'] for r in rs if 'platform_evidence' in r]}
 current=json.loads((covers/'index.json').read_text(encoding='utf-8'))['serials'];disagreements=[{'title_id':tid,'existing_igdb_id':current[tid],'worldwide_igdb_id':gid} for tid,gid in serials.items() if tid in current and str(current[tid])!=gid]
 conflicted_serials={r['title_id'] for r in records if r['conflicts']}
 additions={k:v for k,v in serials.items() if k not in current and k not in conflicted_serials};removals={k:v for k,v in current.items() if k not in serials}
 coverage={'schema_version':1,'scope':'Sourced worldwide native PS Vita identities, all regions; community-source union is not proof of complete released worldwide library. Legacy/non-game content retained and typed.','complete_worldwide':False,'records':len(records),'unique_title_ids':len({r['title_id'] for r in records}),'native_vita_title_ids':len({r['title_id'] for r in records if VITA.fullmatch(r['title_id'])}),'native_base_title_ids':len({r['title_id'] for r in records if VITA.fullmatch(r['title_id']) and r['content_type'] in GAME_TYPES}),'mapped_serials':len(serials),'new_serial_candidates':len(additions),'current_serials_not_reconciled':len(removals),'existing_disagreements':disagreements,'serial_conflicts':serial_conflicts,'by_source':source_coverage,'by_region':dict(collections.Counter(r['region'] for r in records)),'by_type':dict(collections.Counter(r['content_type'] for r in records)),'by_missing_reason':dict(collections.Counter(r['missing_reason'] or 'mapped' for r in records)),'records_with_conflicts':sum(bool(r['conflicts']) for r in records),'artwork_scope':'game; no regional packaging verification','source_gaps':['No known complete official Sony worldwide historical Vita title-ID feed was found.','Current No-Intro DAT-o-MATIC metadata requires Terms/Privacy acceptance; libretro public snapshots are dated supplementary metadata.','GameTDB homepage returned 403; no authoritative Vita bulk feed established.','Redump is optical-disc focused; no native Vita cartridge/database feed established.','Community feeds may omit retail-only, regional, delisted or undumped releases; no claim of completeness.','Names absent from the bundled IGDB catalog or editions with no exact identity stay unresolved; no fuzzy aliases are inferred.']}
 # Each source/region/type receives explicit matched, unmatched and conflict counts.
 def stats(rs):
  return {'records':len(rs),'unique_title_ids':len({r['title_id'] for r in rs}),'matched_records':sum('mapped_igdb_id'in r for r in rs),'unmatched_records':sum('mapped_igdb_id'not in r for r in rs),'conflict_records':sum(bool(r['conflicts']) for r in rs),'missing_reasons':dict(collections.Counter(r['missing_reason'] or 'mapped' for r in rs))}
 coverage['source_status']={x['id']:x['status'] for x in json.loads((BASE/'source-manifest.json').read_text(encoding='utf-8'))}
 coverage['by_source_status']={sid:stats([r for r in records if any(x['source']==sid for x in r['source_records'])]) for sid in source_coverage}
 coverage['by_region_status']={reg:stats([r for r in records if reg in r['regions']]) for reg in sorted({reg for r in records for reg in r['regions']})}
 coverage['by_type_status']={kind:stats([r for r in records if r['content_type']==kind]) for kind in sorted({r['content_type'] for r in records})}
 native_base=[r for r in records if VITA.fullmatch(r['title_id']) and r['content_type'] in GAME_TYPES]
 coverage['native_base_status']=stats(native_base)
 coverage['unmatched_native_base_title_ids']=len({r['title_id'] for r in native_base}-set(serials))
 coverage['native_base_by_region']={reg:{'title_ids':len({r['title_id'] for r in native_base if reg in r['regions']}),'mapped_title_ids':len({r['title_id'] for r in native_base if reg in r['regions']} & set(serials))} for reg in sorted({reg for r in native_base for reg in r['regions']})}
 coverage['input_sha256']={name:digest((covers/name).read_bytes()) for name in ['data/catalog.json','data/reviewed-mappings.json','index.json']}
 if db and db.exists():coverage['platform_catalog_database_sha256']=digest(db.read_bytes())
 coverage['source_record_total']=sum(len(r['source_records']) for r in records)
 coverage['unique_content_ids']=len({x['content_id'] for r in records for x in r['source_records'] if x.get('content_id')})
 coverage['new_serial_candidates']=len(additions)
 coverage['source_gaps'][1]='Current No-Intro DAT-o-MATIC Terms/Data license read; public metadata export form returned index HTML instead of a DAT in this session. libretro snapshots remain dated supplementary metadata; current bulk export remains an explicit gap.'
 dump(BASE/'safe-additions.json',{'schema_version':1,'input_sha256':coverage['input_sha256'],'serials':additions,'serial_metadata':{k:metadata[k] for k in additions},'policy':'New title IDs only; exact full identity/current reviewed override, existing game assets, no cross-source type/identity conflict. Existing serials never replaced by this file.'})
 dump(BASE/'unmatched-native-identities.json',{'records':[r for r in native_base if r['title_id'] not in serials]})
 review_ids=set(removals)|{x['title_id'] for x in disagreements}
 review=[]
 for tid in sorted(review_ids):
  review.append({'title_id':tid,'existing_igdb_id':current[tid],'worldwide_igdb_id':serials.get(tid),'claims':[{k:r.get(k) for k in ['titles','content_type','mapped_igdb_id','missing_reason','conflicts','evidence','mapping_evidence']} for r in records if r['title_id']==tid and r['content_type'] in GAME_TYPES]})
 dump(BASE/'existing-review-required.json',review)
 dump(BASE/'conflicts.json',{'serial_conflicts':serial_conflicts,'existing_disagreements':disagreements,'records':[r for r in records if r['conflicts']]})
 dump(BASE/'worldwide-identities.json',{'schema_version':1,'records':records});dump(BASE/'coverage.json',coverage);dump(BASE/'merge-candidates.json',{'schema_version':1,'serials':serials,'serial_metadata':metadata,'additions':additions,'disagreements':disagreements,'existing_unreconciled':removals})
 print(json.dumps({k:v for k,v in coverage.items() if k not in ('by_source','scope','source_gaps','artwork_scope','existing_disagreements','serial_conflicts','by_source_status','by_region_status','by_type_status')},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--covers',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1]);p.add_argument('--database',type=pathlib.Path);p.add_argument('--fetch',action='store_true');a=p.parse_args()
 if a.fetch:fetch_sources(a.covers)
 reconcile(a.covers,a.database)
