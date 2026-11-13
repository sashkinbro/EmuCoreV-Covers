"""Independent structural and deterministic-regeneration checks after full audit."""
import json,re,tempfile,shutil,sys,platform,argparse
from collections import Counter
from pathlib import Path
from importlib.metadata import version
from PIL import Image,features
from pipeline import ROOT,read,write,sha,generate,region,renderer_fingerprint,VERSION
from renderer import ASSET_FILES

def verify(root=ROOT,local_report=None):
    idx=read(root/'index.json');identity=read(root/'identity-manifest.json');manifest=read(root/'manifest.json');ds=read(root/'derivatives.json');coverage=read(root/'coverage.json');recipe=renderer_fingerprint()
    if set(idx['games'])!=set(manifest['games']):raise ValueError('Catalog coverage incomplete')
    for s,gid in idx['serials'].items():
        if not re.fullmatch(r'PCS[A-H][0-9]{5}',s) or gid not in idx['games']:raise ValueError('Invalid serial index')
        meta=identity['serial_metadata'][s]
        if meta['igdb_id']!=gid or meta['region']!=region(s) or not meta['evidence']:raise ValueError('Identity provenance mismatch')
    local_count=None
    if local_report:
        private=read(local_report)
        actual=sorted(s for s in private['full_game_ids'] if s not in idx['serials'])
        if actual!=private['unresolved_ids']:raise ValueError('Private acceptance report does not match actual runtime coverage')
        local_count=len(private['full_game_ids'])
    if any(x['title_id'] in idx['serials'] for x in identity['unresolved']):raise ValueError('Unresolved identity leaked into runtime')
    for gid,g in idx['games'].items():
        for field,style in [('path','flat'),('path_3d','3d')]:
            if g[field]!=f'covers/{"3d/" if style=="3d" else ""}{gid}.webp':raise ValueError('Invalid asset path')
            d=ds[gid][style]
            if d['renderer_sha256']!=recipe:raise ValueError('Renderer/encoder recipe fingerprint mismatch')
            if d['width']*3!=d['height']*2:raise ValueError('Invalid portrait canvas ratio')
            if style=='flat' and (d['width']<g['original_width'] or d['height']<g['original_height']):raise ValueError('Flat canvas lost original dimensions')
            if style=='3d' and (d['width']<1200 or d['height']<1800):raise ValueError('3D canvas below quality minimum')
            box=d['art_box'];bw,bh=d['printable_bounds']
            if style=='3d' and (d['case_geometry']!='canonical_vertical_vita' or d['composition'] in ('full_source_wrap','reviewed_portrait_crop_wrap') and box!=[0,0,bw,bh]):raise ValueError('Canonical case or normal art wrap changed')
            poster=style=='3d' and d['composition']=='designed_whole_poster'
            if not poster and max(box[2]/bw,box[3]/bh)<.999 or box[0]<0 or box[1]<0 or box[0]+box[2]>bw or box[1]+box[3]>bh:raise ValueError('Artwork outside approved printable layout')
            cb=d.get('source_crop_box',[0,0,g['original_width'],g['original_height']]);cw,ch=cb[2]-cb[0],cb[3]-cb[1]
            if abs(box[3]-ch*box[2]/cw)>1:raise ValueError('Selected source aspect ratio changed')
            if max(d['width'],d['height'])>16384 or d['width']*d['height']>64*1024*1024 or d['bytes']>32*1024*1024:raise ValueError('Runtime image bounds exceeded')
        if g['artwork_scope']!='game' or g['regional_artwork_verified'] is not False:raise ValueError('Unverified region artwork claim')
    fit=read(root/'fit-audit.json')
    if fit['renderer_sha256']!=recipe or fit['served_derivative_validation'] is not True or {r['igdb_id'] for r in fit['records']}!=set(manifest['games']):raise ValueError('Incomplete final source/window audit')
    for r in fit['records']:
        if r['source_sha256']!=manifest['games'][r['igdb_id']]['original']['sha256'] or r['blank_design_regions']!=0 or r['canonical_vertical_case'] is not True or r['expected_source_rgba_sha256']!=r['actual_print_rgba_sha256']:raise ValueError('Invalid source/window pixel proof')
    fonts=read(root/'font-coverage.json')
    if fonts['renderer_sha256']!=recipe or fonts['unsupported_glyphs']!=0 or fonts['layout_counts']!=dict(Counter(pair['3d']['composition'] for pair in ds.values())):raise ValueError('Stale/incomplete actual-layout font audit')
    samples=['119','236','107044','8616','59408','63419','98664','52534','91029','390722']
    regenerated=[];sampled=[]
    with tempfile.TemporaryDirectory(prefix='emucorev-covers-verify-') as directory:
        tmp=Path(directory)
        for gid in samples:
            g=manifest['games'][gid];src=root/g['original_path'];target=tmp/g['original_path'];target.parent.mkdir(exist_ok=True);shutil.copyfile(src,target)
            _,out=generate((str(tmp),gid,g,ds[gid]['flat']['renderer_sha256']))
            for style in ('flat','3d'):
                if out[style]['sha256']!=ds[gid][style]['sha256']:raise ValueError(f'Regeneration changed asset bytes: {gid} {style}')
                with Image.open(root/ds[gid][style]['path']) as im:
                    im.load();sample=im.convert('RGBA').resize((720,1080),Image.Resampling.LANCZOS);sample.load()
                    sampled.append({'igdb_id':gid,'style':style,'software_sample_dimensions':list(sample.size),'rgba_sha256':__import__('hashlib').sha256(sample.tobytes()).hexdigest()})
            regenerated.append({'igdb_id':gid,'flat_sha256':out['flat']['sha256'],'three_dimensional_sha256':out['3d']['sha256']})
    maxima={'bytes':max(d['bytes'] for pair in ds.values() for d in pair.values()),'width':max(d['width'] for pair in ds.values() for d in pair.values()),'height':max(d['height'] for pair in ds.values() for d in pair.values()),'pixels':max(d['width']*d['height'] for pair in ds.values() for d in pair.values())}
    result={'catalog_games':len(idx['games']),'exact_title_ids':len(idx['serials']),'external_inventory_count':local_count,'structural_validation':'passed','runtime_image_maxima':maxima,'software_sample_decode':'Full Pillow decode then RGBA resize to 720x1080; not an on-device Android decoder assertion','software_sample_decodes':sampled,'deterministic_regeneration_samples':regenerated,'coverage_sha256':sha(root/'coverage.json'),'index_sha256':sha(root/'index.json'),'manifest_sha256':sha(root/'manifest.json'),'derivatives_sha256':sha(root/'derivatives.json'),'identity_sha256':sha(root/'identity-manifest.json')}
    write(root/'verification.json',result)
    write(root/'reproducibility.json',{'python':platform.python_version(),'pillow':version('Pillow'),'numpy':version('numpy'),'webp':features.version('webp'),'renderer_policy':VERSION,'renderer_and_encoder_sha256':renderer_fingerprint(),'pipeline_sha256':sha(root/'scripts/pipeline.py'),'renderer_file_sha256':sha(root/'scripts/renderer.py'),'renderer_assets_sha256':{name:sha(root/'scripts/assets'/name) for name in ASSET_FILES},'sources':{p.name:sha(p) for p in sorted((root/'data').glob('*.json'))}})
    print(json.dumps({k:v for k,v in result.items() if k in ('catalog_games','exact_title_ids','external_inventory_count','structural_validation')}))

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--local-report',type=Path);a=p.parse_args();verify(local_report=a.local_report)
