"""Retain all current provider Vita cover entities independently of serial joins.

Provider platform tags do not prove native commercial release. Per-entity review
keeps legacy, DLC, bundles, homebrew, announced and conflicting claims distinct.
"""
from copy import deepcopy
from collections import Counter
from pathlib import Path
import argparse,json
from pipeline import ROOT,read,write,sha

def release_review(facts,review):
    decisions={r['id']:r for r in review['all104_new']};historical={r['id'] for r in review['historical33']};rows=[]
    for g in facts['games']:
        d=decisions.get(g['id'],{});vita=[r for r in g.get('release_dates',[]) if r.get('platform')==46]
        rows.append({'igdb_id':g['id'],'name':g['name'],'review_class':d.get('review_class','historical_bundle_not_current_platform_tag'),'review_evidence_urls':d.get('evidence_urls',[]),'historical_retained':g['id'] in historical,'provider_global_game_status':g.get('game_status'),'provider_vita_release_rows':vita,'provider_release_evidence_shape':'dated_vita_row' if any(r.get('date') for r in vita) else ('vita_row_date_tbd' if vita else 'no_vita_release_row'),'publisher_or_developer_platform_conflict':d.get('review_class')=='provider_platform_conflict','automatic_native_promotion_or_serial_join':False})
    return {'schema_version':1,'source':'data/igdb-release-facts.json','scope':'104 current provider additions plus 33 historical IDs; dates/status remain provider assertions. Dated rows do not override publisher conflicts or infer native application IDs.','records':rows,'by_provider_release_evidence_shape':dict(Counter(r['provider_release_evidence_shape'] for r in rows)),'by_provider_vita_release_region':dict(Counter(x.get('release_region',{}).get('region','unspecified') for r in rows for x in r['provider_vita_release_rows']))}

def extend_catalog(catalog,metadata,review,snapshot_hash):
    out=deepcopy(catalog);existing={str(g['igdb_id']):g for g in out['games']};added=[]
    decisions={str(r['id']):r for r in review['all104_new']}
    for game in metadata['games']:
        gid=str(game['id'])
        if gid in existing or not game.get('cover'):continue
        if 46 not in game.get('platforms',[]):raise ValueError('Not a provider Vita entity')
        if gid not in decisions:raise ValueError('New provider entity lacks explicit retention review')
        row={'igdb_id':game['id'],'name':game['name'],'cover_url':game['cover']['url'],'metadata_source':'https://api.igdb.com/v4/games','source_snapshot':'data/igdb-metadata.json','source_snapshot_sha256':snapshot_hash,'provider_platforms':game['platforms'],'provider_game_type':game.get('game_type'),'provider_parent_game':game.get('parent_game'),'provider_version_parent':game.get('version_parent'),'provider_review_class':decisions[gid]['review_class'],'provider_review_evidence':'data/provider-corpus-review.json','native_release_asserted':False,'asset_scope':'Own IGDB entity artwork only; no native release, title-ID, regional packaging or entitlement inference'}
        out['games'].append(row);existing[gid]=row;added.append(gid)
    out['games'].sort(key=lambda x:x['igdb_id'])
    out['coverage_scope']='All covered current IGDB platform-46 entities plus historical bundled artwork. Provider tags include legacy/content/bundles/homebrew/announced/conflicting records; not a complete verified native worldwide release library.'
    return out,sorted(added,key=int)

def audit(root):
    api=read(root/'data/igdb-metadata.json')['games'];catalog=read(root/'data/catalog.json')['games'];manifest=read(root/'manifest.json')['games'];review=read(root/'data/provider-corpus-review.json')
    ids={str(g['igdb_id']) for g in catalog};current={str(g['id']) for g in api};covered={str(g['id']) for g in api if g.get('cover')};missing=sorted(covered-ids,key=int)
    if missing:raise ValueError('Current provider covers missing from catalog')
    result={'complete_worldwide':False,'current_provider_entities':len(current),'current_provider_entities_with_covers':len(covered),'current_provider_entities_without_covers':len(current-covered),'historical_retained_entities':len(ids-current),'asset_catalog_entities':len(ids),'originals_downloaded':sum(g.get('status')=='downloaded' for g in manifest.values()),'provider_native_release_assertion':'Platform-46 metadata only except separately cited review facts; not all entries are native commercial games.','reviewed_new_entity_classes':dict(Counter(r['review_class'] for r in review['all104_new'])),'no_cover_entities':[{'igdb_id':g['id'],'name':g['name'],'provider_game_type':g.get('game_type'),'provider_platforms':g.get('platforms'),'reason':'igdb_cover_not_available'} for g in api if not g.get('cover')],'source_snapshot_sha256':sha(root/'data/igdb-metadata.json'),'review_ledger_sha256':sha(root/'data/provider-corpus-review.json')}
    if (root/'data/igdb-release-facts.json').exists():
        releases=release_review(read(root/'data/igdb-release-facts.json'),review);releases['source_snapshot_sha256']=sha(root/'data/igdb-release-facts.json');write(root/'data/provider-release-review.json',releases);result['release_review_path']='data/provider-release-review.json';result['release_facts_entities']=len(releases['records'])
    write(root/'data/provider-corpus-coverage.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('command',choices=['extend','audit']);a=p.parse_args()
    if a.command=='extend':
        out,added=extend_catalog(read(ROOT/'data/catalog.json'),read(ROOT/'data/igdb-metadata.json'),read(ROOT/'data/provider-corpus-review.json'),sha(ROOT/'data/igdb-metadata.json'));write(ROOT/'data/catalog.json',out);print(json.dumps({'added_igdb_ids':added,'catalog_entities':len(out['games'])}))
    else:print(json.dumps({k:v for k,v in audit(ROOT).items() if isinstance(v,(int,bool))}))
