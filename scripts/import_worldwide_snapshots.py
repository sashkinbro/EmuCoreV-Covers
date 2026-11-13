"""Import reviewed sanitized worldwide snapshots, never raw package/key feeds."""
import argparse,json,hashlib
from pathlib import Path
from worldwide_sources import SAFE_KEYS,platform_type,type_name
from worldwide_merge import read,write
from pipeline import ROOT

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--input',type=Path,required=True);a=p.parse_args();dest=ROOT/'data/worldwide';dest.mkdir(parents=True,exist_ok=True);changes=[];manifest=[]
    for src in sorted((a.input/'sources').glob('*.json')):
        doc=read(src);rows=[]
        for prior in doc['records']:
            row={k:v for k,v in prior.items() if k in SAFE_KEYS}
            old=row['content_type'];row['content_type']=platform_type(row['title_id'],type_name(row['title'],row.get('source_content_type',old)))
            if old!=row['content_type']:changes.append({'source':doc['source']['id'],'source_record_id':row['source_record_id'],'title_id':row['title_id'],'title':row['title'],'previous_type':old,'corrected_type':row['content_type']})
            rows.append(row)
        meta=doc['source'];meta['sanitized_records_sha256']=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest();manifest.append(meta)
        write(dest/'sources'/src.name,dict(doc,source=meta,records=rows),True)
    write(dest/'source-manifest.json',manifest)
    write(dest/'parser-corrections.json',{'policy':'Explicit demo/trial-version markers only; Trial within Urban Trial Freestyle is a game title. Trial & Unlock remains its own type. Source type/content IDs retained. Japanese trial markers do not require Latin word boundaries.','changes':changes})
    for original,target in [('safe-additions.json','accepted-additions.json'),('existing-review-required.json','initial-existing-review.json'),('platform-disambiguation.json','platform-disambiguation.json')]:
        doc=read(a.input/original);path=dest/target
        if path.exists() and read(path)!=doc:raise ValueError(f'Review plan changed: {target}; review and replace it explicitly before importing')
        write(path,doc)
    print(json.dumps({'sanitized_source_snapshots':len(manifest),'source_assertions':sum(x['records'] for x in manifest),'classifier_corrections':len(changes)}))

if __name__=='__main__':main()
