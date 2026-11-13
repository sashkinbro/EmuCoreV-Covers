"""Audit actual final layout branches and generated title glyphs, without rendering."""
from collections import Counter
from PIL import Image,ImageDraw,ImageFont
from pipeline import ROOT,read,write,sha,renderer_fingerprint
from renderer import VERSION,case_size,source_layout,fit_title

def main():
    manifest=read(ROOT/'manifest.json')['games'];rows=[];branches=Counter();designed=0
    probe=ImageFont.truetype(str(ROOT/'scripts/assets/DejaVuSans.ttf'),32)
    missing=probe.getmask(chr(0x10ffff));missing=(missing.size,bytes(missing))
    draw=ImageDraw.Draw(Image.new('RGBA',(1,1)))
    for gid,g in manifest.items():
        class Shape:pass
        source=Shape();source.width=g['original']['width'];source.height=g['original']['height'];source.size=source.width,source.height
        scale=case_size(source,gid)[0]/1200;t=2*scale;p=source_layout(source,scale,gid);branches[p['composition']]+=1
        if p['composition'] not in ('designed_whole_poster','designed_title_and_platform_footer'):continue
        designed+=1
        for char in set(g['name']):
            if char.isspace():continue
            mask=probe.getmask(char)
            if (mask.size,bytes(mask))==missing:raise ValueError('Unsupported source-title glyph '+gid)
        top=p['source_art_box'][1]
        if p['composition']=='designed_whole_poster':size=round(43*t)
        elif top>round(30*t):size=round(min(76*t,top*.48))
        else:continue
        width=p['front']-round(48*t);font=fit_title(draw,g['name'],width,size);bbox=draw.textbbox((0,0),g['name'],font=font)
        if bbox[2]>width:raise ValueError('Generated source title overflows '+gid)
        rows.append({'igdb_id':gid,'source_title':g['name'],'composition':p['composition'],'font_size_pixels':font.size,'text_bbox':list(bbox),'available_width':width,'glyphs_supported':True,'invented_romanization':False})
    result={'renderer_policy':VERSION,'renderer_sha256':renderer_fingerprint(),'layout_counts':dict(branches),'designed_source_title_strings_checked':designed,'actual_title_marquees':len(rows),'unsupported_glyphs':0,'font_path':'scripts/assets/DejaVuSans.ttf','font_sha256':sha(ROOT/'scripts/assets/DejaVuSans.ttf'),'license_path':'scripts/assets/FONT-LICENSE.txt','records':rows}
    write(ROOT/'font-coverage.json',result);print({k:v for k,v in result.items() if isinstance(v,(int,dict)) and k!='records'})

if __name__=='__main__':main()
