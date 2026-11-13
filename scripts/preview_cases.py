"""Render reproducible quality previews outside the repository's published assets."""
import argparse,json,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
from pipeline import ROOT,read,sha,renderer_fingerprint
from renderer import VERSION,contain,portrait_size,render3d,printable_size,source_layout

def preview(output,ids):
    output.mkdir(parents=True,exist_ok=True);manifest=read(ROOT/'manifest.json')['games'];records=[]
    sheet=Image.new('RGB',(700,len(ids)*525),(37,40,45));draw=ImageDraw.Draw(sheet)
    for row,gid in enumerate(ids):
        g=manifest[gid]
        if sha(ROOT/g['original_path'])!=g['original']['sha256']:raise ValueError('Original identity changed')
        with Image.open(ROOT/g['original_path']) as source:
            flat,flat_box=contain(source,portrait_size(source));case,case_box=render3d(source,g['name'],gid);bounds=printable_size(source,gid)
            record={'igdb_id':gid,'name':g['name'],'source_sha256':g['original']['sha256'],'source_dimensions':list(source.size),'printable_bounds':list(bounds),'source_panel_box':list(case_box),'source_crop_box':list(source_layout(source,case.width/1200,gid)['source_crop_box']),'composition':source_layout(source,case.width/1200,gid)['composition'],'case_geometry':'canonical_vertical_vita','styles':{}}
            for column,(style,im) in enumerate([('flat',flat),('3d',case)]):
                p=output/f'{gid}-{style}.webp';im.save(p,'WEBP',quality=98,method=4)
                if p.stat().st_size>32*1024*1024 or max(im.size)>16384 or im.width*im.height>64*1024*1024:raise ValueError('Runtime limit exceeded')
                with Image.open(p) as check:check.load();sample=check.convert('RGBA').resize((720,1080),Image.Resampling.LANCZOS);sample.load()
                record['styles'][style]={'path':p.name,'dimensions':list(im.size),'bytes':p.stat().st_size,'sha256':sha(p),'software_720x1080_rgba_sha256':hashlib.sha256(sample.tobytes()).hexdigest()}
                small=ImageOps.contain(im,(320,480),Image.Resampling.LANCZOS);sheet.paste(small,(20+column*350,row*525+35),small if small.mode=='RGBA' else None)
            draw.text((20,row*525+12),f'{gid} {g["name"]} | original {source.width}x{source.height}',fill='white')
            records.append(record)
    sheet.save(output/'preview-pairs.jpg',quality=95)
    result={'renderer_policy':VERSION,'renderer_sha256':renderer_fingerprint(),'policy':'Same canonical vertical case and continuous shared UV. Whole-source wrap or recorded reviewed A-style normal-portrait crop; complete art in designed outlier panels. No reflection, stretched-edge fill or invented game-feature badges.','records':records}
    (output/'preview-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(str((output/'preview-pairs.jpg').resolve()))

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--ids',nargs='+',default=['21569','59408','63419','91029']);args=p.parse_args();preview(args.output,args.ids)
