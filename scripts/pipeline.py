"""Reproducible PS Vita artwork pipeline. No API credentials or runtime fuzzy match.
Python 3.11+, Pillow, NumPy. Original IGDB bytes are retained unchanged.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from collections import defaultdict
import hashlib, json, os, re, time, unicodedata, math, ast, inspect as pyinspect
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
import numpy as np
from PIL import Image
from renderer import contain, portrait_size, case_size, printable_size, source_layout, warp, render3d, VERSION, ASSET_FILES, LAYOUT_OVERRIDES

ROOT=Path(__file__).resolve().parents[1]
SIZE=(1200,1800)
MAX_BYTES=32*1024*1024
FRONT=[(152,86),(1136,146),(1136,1638),(152,1706)]
SPINE=[(70,118),(152,86),(152,1706),(70,1668)]

class ImageRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urlsplit(newurl)
        if p.scheme!='https' or p.hostname!='images.igdb.com' or p.port or p.username:raise ValueError('Foreign image redirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

IMAGE_OPENER=build_opener(ImageRedirectHandler())

def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+'.part');t.write_text(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');os.replace(t,p)

def normalize(s):
    s=unicodedata.normalize('NFKD',''.join(c for c in s if c not in '™®©').casefold())
    s=''.join(c if c.isalnum() or c=='+' else ' ' for c in s if not unicodedata.combining(c) and c not in '™®©')
    return ' '.join(s.replace('+',' + ').split())

def resolve(name,games): return [k for k,g in games.items() if normalize(name)==normalize(g['name'])]

def image_identity(value):
    p=urlsplit('https:'+value if value.startswith('//') else value)
    m=re.fullmatch(r'/igdb/image/upload/t_[a-z0-9_]+/([A-Za-z0-9_-]+)\.(jpg|png)',p.path)
    if p.scheme!='https' or p.hostname!='images.igdb.com' or p.port or p.query or p.fragment or p.username or not m: raise ValueError('Invalid IGDB image URL')
    return m.groups()

def inspect(p):
    if not 0<Path(p).stat().st_size<=MAX_BYTES:raise ValueError('Image byte limit')
    with Image.open(p) as im:
        w,h=im.size;fmt=im.format
        if fmt not in ('JPEG','PNG','WEBP','GIF') or w*h>80_000_000 or min(w,h)<=0:raise ValueError('Invalid image')
        im.verify()
    frames=1
    with Image.open(p) as im:
        frames=getattr(im,'n_frames',1)
        if frames>512 or frames*w*h>80_000_000:raise ValueError('Animated image decode limit')
        for frame in range(frames):im.seek(frame);im.load()
    info=dict(width=w,height=h,bytes=Path(p).stat().st_size,sha256=sha(p),format=fmt)
    if fmt=='GIF':info['frame_count']=frames
    return info




def region(serial):return {'PCSA':'USA','PCSE':'USA','PCSB':'EUR','PCSF':'EUR','PCSC':'JPN','PCSG':'JPN','PCSD':'ASIA','PCSH':'ASIA'}.get(serial[:4],'unknown')

def mapping(root,local_inventory=None,local_report=None):
    cat=read(root/'data/catalog.json');games={str(g['igdb_id']):g for g in cat['games']}
    compat=read(root/'data/vita3k-commercial.json')['list']
    evidence=defaultdict(list)
    for row in compat:
        if re.fullmatch(r'PCS[A-H][0-9]{5}',row['titleId']):evidence[row['titleId']].append({'title':row['name'],'source':f"https://github.com/Vita3K/compatibility/issues/{row['issueId']}",'kind':'vita3k_report'})
    for s,row in read(root/'data/title-assertions.json').items():evidence[s].append(row)
    overrides=read(root/'data/reviewed-mappings.json') if (root/'data/reviewed-mappings.json').exists() else {}
    names=defaultdict(set)
    for k,g in games.items():names[normalize(g['name'])].add(k)
    mapped={};unresolved=[]
    for serial,ev in sorted(evidence.items()):
        candidates=set(k for e in ev for k in names.get(normalize(e['title']),set()))
        method='unique_full_normalized_title'
        if serial in overrides:
            o=overrides[serial];candidates={str(o['igdb_id'])};method='reviewed_serial_mapping';ev=ev+[{'title':o['title'],'source':o['source'],'kind':'reviewed','note':o['note']}]
        if len(candidates)!=1:
            unresolved.append({'title_id':serial,'titles':list(dict.fromkeys(e['title'] for e in ev)),'candidate_igdb_ids':sorted(candidates),'reason':'ambiguous' if candidates else 'no_exact_catalog_identity'});continue
        key=next(iter(candidates))
        if key not in games:raise ValueError('Mapping references missing IGDB ID')
        mapped[serial]={'igdb_id':key,'region':region(serial),'region_method':'Vita3K title ID prefix convention','title':ev[0]['title'],'match_method':method,'evidence':ev,'artwork_scope':'game'}
        if serial in overrides and overrides[serial].get('release_variant_conflict'):mapped[serial]['release_variant_conflict']=overrides[serial]['release_variant_conflict']
    worldwide=None
    if (root/'data/worldwide/source-manifest.json').exists():
        from worldwide_merge import build
        mapped,unresolved,worldwide=build(root,mapped,unresolved)
    output={'schema_version':2,'serial_metadata':mapped,'unresolved':unresolved,'sources':{p.name:sha(p) for p in sorted((root/'data').glob('*.json'))}}
    if worldwide:output['worldwide_coverage_summary']={k:worldwide[k] for k in ('complete_worldwide','source_assertions','native_vita_title_ids','native_base_title_ids','native_base_status')}
    summary={'games':len(games),'serials':len(mapped),'unresolved':len(unresolved)}
    if local_inventory:
        private=read(local_inventory);local=private['titles'];full=sorted(s for s,r in local.items() if r.get('CATEGORY')=='gd');missing=[s for s in full if s not in mapped or mapped[s]['igdb_id'] not in games]
        conflicts={s:mapped[s]['release_variant_conflict'] for s in full if s in mapped and mapped[s].get('release_variant_conflict')}
        aggregate={'base_applications':len(full),'mapped_base_applications':len(full)-len(missing),'reported_release_variant_conflicts':len(conflicts),'classification':'CATEGORY=gd base application metadata; does not assert full-game entitlement'};output['external_inventory_aggregate']=aggregate;summary.update(aggregate)
        if not local_report:raise ValueError('--local-report outside the repository is required for private inventory coverage')
        report_path=Path(local_report).resolve()
        if report_path==root or root in report_path.parents:raise ValueError('Private inventory report must be outside the cover repository')
        version_evidence={s:{'observed_source_APP_VER':local[s]['APP_VER'],'source':'Private source PARAM.SFO inventory; active installed patch version is not asserted'} for s in missing if local[s].get('APP_VER')}
        write(report_path,{'full_game_ids':full,'unresolved_ids':missing,'release_variant_conflicts':conflicts,'version_evidence':version_evidence,'aggregate':aggregate,'source_inventory_sha256':sha(local_inventory)})
    write(root/'identity-manifest.json',output)
    print(json.dumps(summary),flush=True)

def download_one(task):
    root,game,old=task;root=Path(root);key=str(game['igdb_id']);iid,ext=image_identity(game['cover_url']);p=root/f'originals/{iid}.{ext}';p.parent.mkdir(exist_ok=True)
    url=f'https://images.igdb.com/igdb/image/upload/t_original/{iid}.{ext}'
    base=dict(game,source_image_id=iid,source_url=url,original_path=p.relative_to(root).as_posix(),artwork_scope='game',regional_artwork_verified=False)
    if old.get('source_url')==url and old.get('original_path'):p=root/old['original_path'];base['original_path']=old['original_path']
    if old.get('source_url')==url and p.is_file():
        try:
            info=inspect(p)
            if info['sha256']==old.get('original',{}).get('sha256'):
                if info['format']=='GIF':base['derivative_source_frame']=0
                return key,dict(base,original=info,status='downloaded')
        except (ValueError,OSError):pass
    tmp=p.with_suffix(p.suffix+'.part')
    for attempt in range(3):
        try:
            with IMAGE_OPENER.open(Request(url,headers={'User-Agent':'EmuCoreV-Covers/1.0'}),timeout=40) as resp:
                final=urlsplit(resp.url)
                if final.scheme!='https' or final.hostname!='images.igdb.com':raise ValueError('Foreign redirect')
                if int(resp.headers.get('Content-Length','0'))>MAX_BYTES:raise ValueError('Image byte limit')
                with tmp.open('wb') as f:
                    n=0
                    while b:=resp.read(65536):
                        n+=len(b)
                        if n>MAX_BYTES:raise ValueError('Image byte limit')
                        f.write(b)
            info=inspect(tmp)
            # IGDB t_original can return the original PNG bytes even for a .jpg URL.
            # Preserve those bytes and use their detected format for the local name.
            p=p.with_suffix({'JPEG':'.jpg','PNG':'.png','WEBP':'.webp','GIF':'.gif'}[info['format']]);base['original_path']=p.relative_to(root).as_posix()
            if info['format']=='GIF':base['derivative_source_frame']=0
            os.replace(tmp,p);return key,dict(base,original=info,status='downloaded')
        except Exception as e:
            error=f'{type(e).__name__}: {e}'
            if isinstance(e,HTTPError) and e.code in (400,401,403,404,410):break
            if attempt<2:time.sleep(2**attempt)
        finally:tmp.unlink(missing_ok=True)
    return key,dict(base,status='failed',error=error)

def download(root,workers,ids=None):
    games=read(root/'data/catalog.json')['games'];old=read(root/'manifest.json').get('games',{}) if (root/'manifest.json').exists() else {};out=dict(old) if ids else {}
    if ids:games=[g for g in games if str(g['igdb_id']) in set(ids)]
    # Prioritize local full games, then all remaining catalog IDs.
    ids=set(m['igdb_id'] for m in read(root/'identity-manifest.json')['serial_metadata'].values());games.sort(key=lambda g:(str(g['igdb_id']) not in ids,g['igdb_id']))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs=[pool.submit(download_one,(str(root),g,old.get(str(g['igdb_id']),{}))) for g in games]
        for n,f in enumerate(as_completed(jobs),1):
            k,g=f.result();out[k]=g
            if n%50==0:write(root/'manifest.json',{'schema_version':2,'games':dict(old,**out)});print(f'Downloaded {n}/{len(games)}; failed {sum(g["status"]=="failed" for g in out.values())}',flush=True)
    write(root/'manifest.json',{'schema_version':2,'games':out})
    print(json.dumps({'selected_catalog_records':len(games),'manifest_games':len(out),'failed':sum(g['status']!='downloaded' for g in out.values())}),flush=True)
    return sum(g['status']!='downloaded' for g in out.values())



def generate(task):
    root,key,game,renderer=task;root=Path(root);src=root/game['original_path']
    if sha(src)!=game['original']['sha256']:raise ValueError('Original hash mismatch')
    if key in LAYOUT_OVERRIDES and LAYOUT_OVERRIDES[key]['source_sha256']!=game['original']['sha256']:raise ValueError('Reviewed portrait original changed; framing must be reviewed again')
    with Image.open(src) as im:
        flat,box=contain(im,portrait_size(im));three,facebox=render3d(im,game['name'],key)
        print_size=printable_size(im,key)
        layout=source_layout(im,three.width/1200,key)
        if layout['requires_portrait_review']:raise ValueError('Portrait framing requires source/title review')
        if facebox!=layout['source_art_box']:raise ValueError('Composition/source layout mismatch')
        if max(box[2]/flat.width,box[3]/flat.height)<.999:raise ValueError('Flat art did not fill a portrait bound')
    result={}
    for style,image in [('flat',flat),('3d',three)]:
        path=f'covers/{"3d/" if style=="3d" else ""}{key}.webp';p=root/path;p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.webp.part');image.save(tmp,'WEBP',quality=98,method=4);info=inspect(tmp);os.replace(tmp,p)
        bounds=facebox if style=='3d' else box
        result[style]=dict(info,path=path,source_sha256=game['original']['sha256'],renderer_sha256=renderer,renderer_policy=VERSION,art_box=list(bounds),printable_bounds=list(print_size if style=='3d' else image.size),source_to_print_scale=round(bounds[2]/game['original']['width'],6),resampling='proportional; enlargement creates no new detail; '+('canonical vertical case, recorded reviewed A-style crop or complete source panel; no mirror or stretched-edge fill' if style=='3d' else 'complete original on transparent outer canvas'))
        if style=='3d':result[style].update(composition=layout['composition'],source_crop_box=list(layout['source_crop_box']),case_geometry='canonical_vertical_vita',printed_spine_provenance='One printed UV shared continuously across spine, bevel and front. Normal art wraps directly; specified portraits use reviewed crop anchors; outliers use source-title/platform graphic panels. Not an original regional spine scan.')
    return key,result

def renderer_fingerprint():
    recipe=(ROOT/'scripts/renderer.py').read_bytes().replace(b'\r\n',b'\n')
    encoder=ast.dump(ast.parse(pyinspect.getsource(generate)),include_attributes=False).encode('utf-8')
    assets=b''.join(name.encode()+b'\0'+(ROOT/'scripts/assets'/name).read_bytes()+b'\0' for name in ASSET_FILES)
    return hashlib.sha256(recipe+b'\0'+encoder+b'\0'+assets).hexdigest()

def render(root,workers):
    m=read(root/'manifest.json');old=read(root/'derivatives.json') if (root/'derivatives.json').exists() else {};renderer=renderer_fingerprint();tasks=[]
    for k,g in m['games'].items():
        if g['status']!='downloaded':continue
        prev=old.get(k,{})
        if all(prev.get(s,{}).get('renderer_sha256')==renderer and prev[s].get('source_sha256')==g['original']['sha256'] and (root/prev[s]['path']).is_file() and sha(root/prev[s]['path'])==prev[s]['sha256'] for s in ('flat','3d')):continue
        tasks.append((str(root),k,g,renderer))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n,(k,r) in enumerate(pool.map(generate,tasks),1):
            old[k]=r
            if n%50==0:write(root/'derivatives.json',old);print(f'Rendered {n}/{len(tasks)}',flush=True)
    write(root/'derivatives.json',old)

def audit(root):
    manifest=read(root/'manifest.json');derivatives=read(root/'derivatives.json');identity=read(root/'identity-manifest.json');games={};errors=[];recipe=renderer_fingerprint()
    for key,g in manifest['games'].items():
        if g['status']!='downloaded':errors.append({'igdb_id':key,'reason':g.get('error','source_failed')});continue
        if inspect(root/g['original_path'])!=g['original']:raise ValueError(f'Invalid original {key}')
        ds=derivatives[key]
        for style,d in ds.items():
            if inspect(root/d['path'])!={k:v for k,v in d.items() if k in ('width','height','bytes','sha256','format')} or d['source_sha256']!=g['original']['sha256']:raise ValueError(f'Invalid derivative {key} {style}')
        for style,d in ds.items():
            if d.get('renderer_sha256')!=recipe or d.get('renderer_policy')!=VERSION:raise ValueError(f'Artwork recipe policy mismatch {key}')
            cb=d.get('source_crop_box',[0,0,g['original']['width'],g['original']['height']]);cw,ch=cb[2]-cb[0],cb[3]-cb[1]
            if abs(d['art_box'][3]-ch*d['art_box'][2]/cw)>1:raise ValueError(f'Artwork aspect ratio changed {key}')
            if max(d['width'],d['height'])>16384 or d['width']*d['height']>64*1024*1024 or d['bytes']>32*1024*1024:raise ValueError(f'Runtime image policy exceeded {key}')
        games[key]={'path':ds['flat']['path'],'path_3d':ds['3d']['path'],'sha256':ds['flat']['sha256'],'sha256_3d':ds['3d']['sha256'],'width':ds['flat']['width'],'height':ds['flat']['height'],'width_3d':ds['3d']['width'],'height_3d':ds['3d']['height'],'renderer_policy':VERSION,'source_url':g['source_url'],'source_image_id':g['source_image_id'],'original_path':g['original_path'],'original_sha256':g['original']['sha256'],'original_width':g['original']['width'],'original_height':g['original']['height'],'artwork_scope':'game','regional_artwork_verified':False}
        games[key]['printed_spine_provenance']=ds['3d']['printed_spine_provenance']
        games[key]['framing_3d']=ds['3d']['composition'];games[key]['source_crop_box_3d']=ds['3d']['source_crop_box']
        if g.get('derivative_source_frame') is not None:games[key]['derivative_source_frame']=g['derivative_source_frame'];games[key]['original_frame_count']=g['original']['frame_count']
    serials={s:m['igdb_id'] for s,m in identity['serial_metadata'].items() if m['igdb_id'] in games}
    index={'schema_version':2,'repository':'sashkinbro/EmuCoreV-Covers','games':games,'serials':serials,'serial_metadata':{s:identity['serial_metadata'][s] for s in serials}}
    write(root/'index.json',index);write(root/'3d-manifest.json',{k:ds['3d'] for k,ds in derivatives.items()})
    coverage={'catalog_games':len(manifest['games']),'originals':len(games),'flat_covers':len(games),'three_dimensional_covers':len(games),'mapped_title_ids':len(serials),'external_inventory_aggregate':identity.get('external_inventory_aggregate'),'unresolved_title_ids':identity['unresolved'],'download_failures':errors,'small_originals':[{'igdb_id':k,'width':g['original']['width'],'height':g['original']['height']} for k,g in manifest['games'].items() if g['status']=='downloaded' and g['original']['height']<500],'audit':'all retained originals and flat/3D image bytes decoded and SHA-256 verified; mapping is exact IDs only'}
    coverage['complete_worldwide']=False;coverage['worldwide_coverage_path']='data/worldwide/coverage.json';coverage['worldwide_coverage_summary']=identity.get('worldwide_coverage_summary');coverage['retained_catalog_art_without_runtime_serials']=sum(k not in set(serials.values()) for k in games)
    write(root/'coverage.json',coverage);print(json.dumps({k:v for k,v in coverage.items() if isinstance(v,(int,str))}),flush=True)

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('command',choices=['map','download','render','audit']);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--workers',type=int,choices=range(1,5),default=4);p.add_argument('--local-inventory',type=Path);p.add_argument('--local-report',type=Path);p.add_argument('--ids',nargs='*');a=p.parse_args();root=a.root.resolve();lock=root/f'.{a.command}.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:p.error(f'{a.command} already running; inspect {lock} before removing a stale lock')
    os.close(fd)
    try:
        if a.command=='map':mapping(root,a.local_inventory,a.local_report)
        elif a.command=='download':return 1 if download(root,a.workers,a.ids) else 0
        elif a.command=='render':render(root,a.workers)
        else:audit(root)
    finally:lock.unlink(missing_ok=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
