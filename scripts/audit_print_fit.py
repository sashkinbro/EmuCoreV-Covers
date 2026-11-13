"""Source-derived full-bleed UV audit of every original, plus paged visual review."""
import argparse,json,hashlib,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageOps
from pipeline import ROOT,read,write,sha,renderer_fingerprint
from renderer import VERSION,case_size,case_shape,printable_sheet,split_print,LAYOUT_OVERRIDES

def audit(output,served=False):
    games=read(ROOT/'manifest.json')['games'];rows=[];recipe=renderer_fingerprint();ds=read(ROOT/'derivatives.json') if served else {}
    for number,(gid,g) in enumerate(games.items(),1):
        if sha(ROOT/g['original_path'])!=g['original']['sha256']:raise ValueError('Original changed')
        with Image.open(ROOT/g['original_path']) as original:
            original.seek(g.get('derivative_source_frame',0));source=original.convert('RGBA')
            if gid in LAYOUT_OVERRIDES and LAYOUT_OVERRIDES[gid]['source_sha256']!=g['original']['sha256']:raise ValueError('Reviewed source changed '+gid)
            canvas=case_size(source,gid);hf,fit=case_shape(source);uv,box,p=printable_sheet(source,canvas[0]/1200,fit,title=g['name'],game_id=gid)
            if p['requires_portrait_review']:raise ValueError('Unreviewed portrait framing '+gid)
            if (hf,fit)!=(1,1):raise ValueError('Case shape changed '+gid)
            x,y,w,h=box;actual=uv.crop((x,p['header']+y,x+w,p['header']+y+h));crop=p['source_crop_box'];cw,ch=crop[2]-crop[0],crop[3]-crop[1];expected=source.resize(actual.size,Image.Resampling.LANCZOS,box=crop)
            if not(abs(actual.height-ch*actual.width/cw)<=.5 or abs(actual.width-cw*actual.height/ch)<=.5):raise ValueError('Source aspect changed '+gid)
            body=uv.crop((0,p['header'],uv.width,uv.height));regions=[(0,0,body.width,y),(0,y+h,body.width,body.height),(0,y,x,y+h),(x+w,y,body.width,y+h)];designed=[]
            for rect in regions:
                if rect[2]<=rect[0] or rect[3]<=rect[1]:continue
                area=body.crop(rect).convert('RGB');extrema=area.getextrema()
                if max(v[1] for v in extrema)<40 or all(b-a<2 for a,b in extrema) and area.width*area.height>200:raise ValueError('Empty/black design filler '+gid)
                designed.append(list(rect))
            if p['composition'] in ('full_source_wrap','reviewed_portrait_crop_wrap') and (box!=(0,0,body.width,body.height) or designed):raise ValueError('Normal spine does not share the source print '+gid)
            ah=hashlib.sha256(actual.tobytes()).hexdigest();eh=hashlib.sha256(expected.tobytes()).hexdigest()
            if ah!=eh:raise ValueError('Source pixels cropped/filled/mirrored '+gid)
            strips=split_print(uv,p);rebuilt=Image.new('RGBA',uv.size);x=0
            for strip in strips:rebuilt.paste(strip,(x,0));x+=strip.width
            if x!=uv.width or rebuilt.tobytes()!=uv.tobytes():raise ValueError('Discontinuous UV '+gid)
            if max(canvas)>16384 or canvas[0]*canvas[1]>64*1024*1024:raise ValueError('Runtime canvas limit '+gid)
            if served:
                for style,d in ds[gid].items():
                    if d['renderer_sha256']!=recipe or d['source_sha256']!=g['original']['sha256']:raise ValueError('Stale served recipe '+gid)
                d=ds[gid]['3d']
                if d['art_box']!=list(box) or d['printable_bounds']!=list(body.size) or d['composition']!=p['composition'] or d['source_crop_box']!=list(crop) or d['case_geometry']!='canonical_vertical_vita':raise ValueError('Served 3D window mismatch '+gid)
                flat=ds[gid]['flat'];x,y,w,h=flat['art_box'];fw,fh=flat['width'],flat['height']
                with Image.open(ROOT/flat['path']) as im:
                    alpha=im.convert('RGBA').getchannel('A')
                    for rect in [(0,0,fw,y),(0,y+h,fw,fh),(0,y,x,y+h),(x+w,y,fw,y+h)]:
                        if rect[2]>rect[0] and rect[3]>rect[1] and alpha.crop(rect).getextrema()[1]!=0:raise ValueError('Opaque flat padding '+gid)
            rows.append({'igdb_id':gid,'source_sha256':g['original']['sha256'],'source_dimensions':list(source.size),'source_frame':g.get('derivative_source_frame',0),'canvas_dimensions':list(canvas),'composition':p['composition'],'source_art_box':list(box),'source_crop_box':list(crop),'print_window_dimensions':list(body.size),'designed_regions':designed,'blank_design_regions':0,'canonical_vertical_case':True,'expected_source_rgba_sha256':eh,'actual_print_rgba_sha256':ah,'continuous_shared_uv':True,'originals_and_flat_complete':True,'selected_source_pixels_preserved':True})
        if number%250==0:print(f'Source fit checked {number}/{len(games)}',flush=True)
    result={'renderer_policy':VERSION,'renderer_sha256':recipe,'originals_checked':len(rows),'served_derivative_validation':served,'policy':'Same canonical vertical case for every source. Whole original source panel, continuous shared UV, normal direct artwork wrap; outliers have designed title/platform panels with no blank filler or invented features. Genuine source black/transparency preserved.','records':rows}
    write(output,result);return result

def sheets(output,ids=None,per_page=48,columns=8,thumb=(176,264)):
    output.mkdir(parents=True,exist_ok=True);games=read(ROOT/'manifest.json')['games']
    selected=ids or sorted(games,key=int);pages=[]
    for page,start in enumerate(range(0,len(selected),per_page),1):
        group=selected[start:start+per_page];cw,ch=thumb[0]+4,thumb[1]+36;sheet=Image.new('RGB',(cw*columns,math.ceil(len(group)/columns)*ch),(46,49,54));d=ImageDraw.Draw(sheet)
        for n,gid in enumerate(group):
            x=n%columns*cw;y=n//columns*ch
            with Image.open(ROOT/f'covers/3d/{gid}.webp') as im:
                im=ImageOps.contain(im.convert('RGBA'),thumb,Image.Resampling.LANCZOS);sheet.paste(im,(x+(cw-im.width)//2,y),im)
            g=games[gid];w,h=g['original']['width'],g['original']['height'];d.text((x+3,y+thumb[1]+1),f'{gid} {w}x{h}',fill='white');d.text((x+3,y+thumb[1]+15),g['name'][:48 if columns==3 else 24],fill='white')
        path=output/f'page-{page:03}.jpg';sheet.save(path,quality=94);pages.append({'path':path.name,'sha256':sha(path),'igdb_ids':group})
    write(output/'pages.json',{'renderer_policy':VERSION,'pages':pages})
    print(json.dumps({'contact_sheet_pages':len(pages),'covers_shown':len(selected)}))

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'fit-audit.json');p.add_argument('--sheets',type=Path);p.add_argument('--outliers-only',action='store_true');p.add_argument('--served',action='store_true');p.add_argument('--large',action='store_true');p.add_argument('--ids',nargs='+');a=p.parse_args()
    if a.sheets:
        ids=a.ids
        if a.outliers_only:
            derivatives=read(ROOT/'derivatives.json');ids=sorted((k for k,g in derivatives.items() if g['3d']['composition']!='full_source_wrap'),key=int)
        sheets(a.sheets,ids,6,3,(316,474)) if a.large else sheets(a.sheets,ids)
    else:audit(a.output,a.served)
