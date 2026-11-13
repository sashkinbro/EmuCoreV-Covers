"""Fetch authoritative Vita identities/aliases; credentials remain in memory only.
Use environment IGDB_CLIENT_ID/IGDB_CLIENT_SECRET, or an explicit external Python
configuration containing literal TWITCH_CLIENT_ID/TWITCH_CLIENT_SECRET values.
No configuration, credential, token or request header is written to the repository.
"""
import argparse,ast,hashlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
from pipeline import ROOT,write

FIELDS='id,name,slug,alternative_names.name,alternative_names.comment,cover.image_id,cover.url,cover.width,cover.height,platforms,game_type,parent_game,version_parent,external_games.uid,external_games.platform,external_games.external_game_source,game_localizations.name,game_localizations.region,game_localizations.cover.image_id,game_localizations.cover.url,game_localizations.cover.width,game_localizations.cover.height'

def credentials(path=None):
    cid=os.getenv('IGDB_CLIENT_ID') or os.getenv('TWITCH_CLIENT_ID');secret=os.getenv('IGDB_CLIENT_SECRET') or os.getenv('TWITCH_CLIENT_SECRET')
    if path:
        for node in ast.parse(Path(path).read_text(encoding='utf-8-sig')).body:
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
                for target in node.targets:
                    if isinstance(target,ast.Name) and target.id in ('IGDB_CLIENT_ID','TWITCH_CLIENT_ID'):cid=node.value.value
                    if isinstance(target,ast.Name) and target.id in ('IGDB_CLIENT_SECRET','TWITCH_CLIENT_SECRET'):secret=node.value.value
    if not cid or not secret:raise ValueError('IGDB metadata credentials are not configured; existing image URLs do not require them')
    return cid,secret

def fetch(path=None,output=ROOT/'data/igdb-metadata.json',fact_ids=(),facts_only=False,release_facts_only=False):
    cid,secret=credentials(path)
    body=urlencode({'client_id':cid,'client_secret':secret,'grant_type':'client_credentials'}).encode()
    with urlopen(Request('https://id.twitch.tv/oauth2/token',data=body,method='POST'),timeout=30) as response:token=json.loads(response.read())['access_token']
    headers={'Client-ID':cid,'Authorization':'Bearer '+token,'Content-Type':'text/plain','User-Agent':'EmuCoreV-Covers/1.0'}
    hashes=[];queries=[]
    def api(endpoint,query):
        for attempt in range(3):
            try:
                time.sleep(.4)
                with urlopen(Request('https://api.igdb.com/v4/'+endpoint,data=query.encode(),headers=headers,method='POST'),timeout=40) as response:raw=response.read(32*1024*1024)
                hashes.append(hashlib.sha256(raw).hexdigest());queries.append({'endpoint':endpoint,'query':query});return json.loads(raw)
            except HTTPError as error:
                if error.code not in (429,500,502,503,504) or attempt==2:raise RuntimeError(f'IGDB metadata request failed with HTTP {error.code}; credentials and response body omitted') from None
                time.sleep(2**attempt)
    if release_facts_only:
        ids=sorted(set(fact_ids));games=[]
        if not ids:raise ValueError('Release facts require explicit public game IDs')
        fields='id,name,platforms,game_type,parent_game,version_parent,game_status.status,release_dates.date,release_dates.human,release_dates.platform,release_dates.status.name,release_dates.release_region.region'
        for offset in range(0,len(ids),100):games.extend(api('games','fields '+fields+'; where id = ('+','.join(map(str,ids[offset:offset+100]))+'); sort id asc; limit 100;'))
        if {g['id'] for g in games}!=set(ids):raise ValueError('Incomplete release-fact snapshot')
        write(output,{'schema_version':1,'source':'https://api.igdb.com/v4/games','documentation':'https://api-docs.igdb.com/#release-date','fetched_at':datetime.now(timezone.utc).isoformat(),'requested_ids':ids,'queries':queries,'response_sha256':hashes,'games':games,'scope':'Provider release/status assertions, not proof of native commercial shipping. Game status can be global; per-platform release rows remain distinct.','credentials_persisted':False});print(json.dumps({'release_fact_records':len(games),'credentials_persisted':False}));return
    if facts_only:
        result=json.loads(output.read_text(encoding='utf-8'))
        facts=api('games','fields id,name,summary,platforms,game_type,parent_game,version_parent; where id = ('+','.join(map(str,fact_ids))+'); limit 100;')
        prior={g['id']:g for g in result.get('identity_facts',[])};prior.update({g['id']:g for g in facts});result['identity_facts']=list(prior.values());result['queries'].extend(queries);result['response_sha256'].extend(hashes);result['facts_updated_at']=datetime.now(timezone.utc).isoformat();write(output,result);print(json.dumps({'additional_public_fact_records':len(facts),'credentials_persisted':False}));return
    platform=api('platforms','fields id,name,slug; where id = 46; limit 1;')
    if len(platform)!=1 or platform[0]['name']!='PlayStation Vita':raise ValueError('Unexpected platform identity')
    count=api('games/count','where platforms = (46);')['count'];games=[]
    for offset in range(0,count,500):
        games.extend(api('games',f'fields {FIELDS}; where platforms = (46); sort id asc; limit 500; offset {offset};'))
        print(f'IGDB public metadata records {len(games)}/{count}',flush=True)
    if len({g['id'] for g in games})!=count:raise ValueError('Incomplete or duplicate IGDB metadata snapshot')
    ids=sorted({x['external_game_source'] for g in games for x in g.get('external_games',[]) if x.get('platform')==46 and x.get('external_game_source')})
    external_sources=api('external_game_sources','fields id,name; where id = ('+','.join(map(str,ids))+'); limit 100;') if ids else []
    facts=api('games','fields id,name,summary,platforms,game_type,parent_game,version_parent; where id = ('+','.join(map(str,fact_ids))+'); limit 100;') if fact_ids else []
    result={'schema_version':1,'source':'https://api.igdb.com/v4/games','documentation':'https://api-docs.igdb.com/','fetched_at':datetime.now(timezone.utc).isoformat(),'platform':platform[0],'game_count':count,'queries':queries,'response_sha256':hashes,'games':games,'external_game_sources':external_sources,'identity_facts':facts,'credentials_persisted':False}
    write(output,result);print(json.dumps({'metadata_games':count,'status':'downloaded; no credentials persisted'}))

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--credentials-file',type=Path);p.add_argument('--output',type=Path);p.add_argument('--fact-ids',type=int,nargs='*',default=[]);p.add_argument('--facts-only',action='store_true');p.add_argument('--release-facts-only',action='store_true');a=p.parse_args();fetch(a.credentials_file,a.output or ROOT/('data/igdb-release-facts.json' if a.release_facts_only else 'data/igdb-metadata.json'),a.fact_ids,a.facts_only,a.release_facts_only)
