"""Record original-vs-transformed evidence and build a local visual review sheet."""
import argparse,io,json,hashlib
from urllib.request import Request,urlopen
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
from pipeline import ROOT,read,write

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--probe',action='store_true');p.add_argument('--sheet',type=Path);p.add_argument('--ids',nargs='*');a=p.parse_args();m=read(ROOT/'manifest.json')['games']
    ids=a.ids or ['119','236','1545','6363','21000','147222','52832','91029','3180','7355','20113','10142']
    if a.probe:
        result=[]
        for k in ids[:6]:
            g=m[k];u=g['cover_url'].replace('/t_cover_big/','/t_1080p/')
            with urlopen(Request(u,headers={'User-Agent':'EmuCoreV-Covers/1.0'}),timeout=30) as response:b=response.read(32*1024*1024)
            with Image.open(io.BytesIO(b)) as im:im.load();w,h=im.size
            result.append({'igdb_id':k,'image_id':g['source_image_id'],'original':g['original'],'transformed_1080p':{'url':u,'width':w,'height':h,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()},'selection':'retain_original_bytes; transformed dimension increases may be interpolation'})
        write(ROOT/'quality-probes.json',{'documentation':'https://api-docs.igdb.com/#images','note':'1080p is documented; t_original availability and actual dimensions verified empirically. Source dimensions are never inferred from transformation labels.','samples':result})
    if a.sheet:
        valid=[k for k in ids if (ROOT/f'covers/3d/{k}.webp').is_file()]
        sheet=Image.new('RGB',(1600,((len(valid)+3)//4)*345),(38,42,48));d=ImageDraw.Draw(sheet);font=ImageFont.truetype(str(ROOT/'scripts/assets/DejaVuSans.ttf'),15)
        for n,k in enumerate(valid):
            x=(n%4)*400;y=(n//4)*345
            for j,path in enumerate([f'covers/{k}.webp',f'covers/3d/{k}.webp']):
                with Image.open(ROOT/path) as im:
                    im=ImageOps.contain(im.convert('RGBA'),(195,292));sheet.paste(im,(x+j*200,y),im)
            name=m[k]['name'];d.text((x+5,y+296),f'{k} {name[:37]}',font=font,fill='white');o=m[k]['original'];d.text((x+5,y+317),f'Original {o["width"]}x{o["height"]}',font=font,fill='white')
        a.sheet.parent.mkdir(parents=True,exist_ok=True);sheet.save(a.sheet,quality=92)

if __name__=='__main__':main()
