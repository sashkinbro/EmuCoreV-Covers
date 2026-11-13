"""Refresh public identity snapshots from a read-only database and SFO inventory.
No game payloads are opened. Only TITLE_ID, TITLE, CATEGORY are retained.
"""
import argparse, hashlib, json, sqlite3
from pathlib import Path
from urllib.request import Request,urlopen
from pipeline import write,ROOT

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--database',type=Path,required=True);p.add_argument('--inventory',type=Path);p.add_argument('--local-output',type=Path);p.add_argument('--refresh-vita3k',action='store_true');a=p.parse_args()
    with sqlite3.connect(a.database.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        db.row_factory=sqlite3.Row;games=[dict(x) for x in db.execute('SELECT igdb_id,name,cover_url FROM games ORDER BY igdb_id')]
    write(ROOT/'data/catalog.json',{'database_sha256':hashlib.sha256(a.database.read_bytes()).hexdigest(),'games':games})
    if a.inventory:
        if not a.local_output or ROOT==a.local_output.resolve() or ROOT in a.local_output.resolve().parents:raise ValueError('Private inventory --local-output must be outside the cover repository')
        titles={}
        for row in json.loads(a.inventory.read_text(encoding='utf-8-sig')):
            for t in row.get('titles',[]):
                s=t.get('TITLE_ID')
                if s and (s not in titles or t.get('CATEGORY')=='gd'):titles[s]={k:t[k] for k in ['TITLE_ID','TITLE','CATEGORY'] if k in t}
        write(a.local_output,{'source_inventory_sha256':hashlib.sha256(a.inventory.read_bytes()).hexdigest(),'titles':titles})
    if a.refresh_vita3k:
        url='https://api.vita3k.org/list/commercial'
        req=Request(url,headers={'User-Agent':'Mozilla/5.0','Origin':'https://vita3k.org','Referer':'https://vita3k.org/'})
        with urlopen(req,timeout=40) as response:result=json.loads(response.read(4*1024*1024))
        if not isinstance(result.get('list'),list):raise ValueError('Invalid Vita3K response')
        write(ROOT/'data/vita3k-commercial.json',result)

if __name__=='__main__':main()
