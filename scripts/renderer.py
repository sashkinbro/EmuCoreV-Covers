"""Canonical vertical Vita case; continuous A-derived wrap and H-like outlier print.
Real Vita plastic/header marks; full original artwork with designed neutral title/
platform panels for outliers. No fabricated edition, rating or game feature badges.
"""
from pathlib import Path
import json,math
import numpy as np
from PIL import Image,ImageDraw,ImageOps,ImageFilter,ImageFont
ROOT=Path(__file__).resolve().parents[1]
VERSION="vita-canonical-retail-v6-reviewed-framing"
ASSET_FILES=('playstation-logo.png','vita-logo.png','vita-plastic-palette.json','psn-retail.png','DejaVuSans.ttf','portrait-layout-overrides.json')
PALETTE=json.loads((ROOT/'scripts/assets/vita-plastic-palette.json').read_text(encoding='utf-8'))
LAYOUT_OVERRIDES=json.loads((ROOT/'scripts/assets/portrait-layout-overrides.json').read_text(encoding='utf-8'))['games']


def contain(source,size):
    art=ImageOps.contain(source.convert('RGBA'),size,Image.Resampling.LANCZOS)
    out=Image.new('RGBA',size);x=(size[0]-art.width)//2;y=(size[1]-art.height)//2
    out.paste(art,(x,y));return out,(x,y,art.width,art.height)

def portrait_size(source):
    unit=max(300,math.ceil(source.width/2),math.ceil(source.height/3))
    return (unit*2,unit*3)


def case_size(source,game_id=None):
    review=LAYOUT_OVERRIDES.get(str(game_id),{})
    poster=review.get('layout')=='designed_whole_poster' or not review and source.width/source.height<600/838
    unit=math.ceil(600*max(1,source.width/1066,source.height/(1015 if poster else 1385)))
    return unit*2,unit*3

def case_shape(source):
    # Every source uses the identical canonical physical case, never a square
    # or landscape shell. Resolution scales uniformly, not the case proportions.
    return 1,1

def source_crop_box(source_size,target_size,anchor_y):
    sw,sh=source_size;tw,th=target_size
    if not 0<=anchor_y<=1:raise ValueError('Invalid reviewed anchor')
    if sw/sh<tw/th:
        height=sw*th/tw;y=(sh-height)*anchor_y
        return (0,y,sw,y+height)
    width=sh*tw/th;x=(sw-width)/2
    return (x,0,x+width,sh)

def source_layout(source,scale,game_id=None):
    t=2*scale;w,h,head=round(650*t),round(900*t),round(62*t);ah=h-head
    nw=round(ah*source.width/source.height)
    review=LAYOUT_OVERRIDES.get(str(game_id));crop=(0,0,source.width,source.height);needs_review=False
    if review and review['source_dimensions']!=[source.width,source.height]:raise ValueError('Reviewed portrait dimensions changed')
    if review and review['layout']=='reviewed_portrait_crop_wrap':
        box=(0,0,w,ah);mode='reviewed_portrait_crop_wrap';crop=source_crop_box((source.width,source.height),(w,ah),review['anchor_y'])
    elif review and review['layout']=='designed_whole_poster' or not review and nw<round(600*t):
        art_h=round(615*t);art_w=round(art_h*source.width/source.height);box=(round(50*t)+round((600*t-art_w)/2),round(95*t),art_w,art_h);mode='designed_whole_poster';needs_review=not bool(review)
    elif round(600*t)<=nw<=w:box=(0,0,nw,ah);w=nw;mode='full_source_wrap'
    elif nw>w:
        arth=round(w*source.height/source.width);free=ah-arth;top=round(free*.38) if free>round(60*t) else 0
        box=(0,top,w,arth);mode='designed_title_and_platform_footer'
    else:raise ValueError('Unclassified source')
    return dict(front=w-round(w*50/650),height=h,header=head,spine=round(w*50/650),bevel=round(w*8/650),source_art_box=box,composition=mode,source_crop_box=crop,requires_portrait_review=needs_review)

def printable_size(source,game_id=None):
    p=source_layout(source,case_size(source,game_id)[0]/1200,game_id)
    return p['front']+p['spine'],p['height']-p['header']

def texture_parts(scale,source_size=(650,838),fit=1):
    class Shape:
        def __init__(self):self.width,self.height=source_size
    if fit!=1:raise ValueError('Canonical case cannot adapt its physical shape')
    return source_layout(Shape(),scale)


def coords(points,scale,height_factor=1,fit=1):
    # Canonical A-derived Vita shell, uniformly scaled only for pixel resolution.
    if height_factor!=1 or fit!=1:raise ValueError('Every source requires the same canonical vertical case')
    return [(round(((x*2-600)*fit+600)*scale),round(((y-450)*.92*height_factor*2*fit+900)*scale)) for x,y in points]

def warp(source,corners,size):
    # Unchanged inverse-perspective solve from A.warp().
    w,h=source.size;matrix=[];values=[]
    for (x,y),(u,v) in zip(corners,[(0,0),(w,0),(w,h),(0,h)]):
        matrix.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);values.extend([u,v])
    co=np.linalg.solve(np.array(matrix,float),np.array(values,float))
    return source.transform(size,Image.Transform.PERSPECTIVE,co,Image.Resampling.BICUBIC)

def template(scale=1,muted=False,height_factor=1,fit=1):
    size=(round(1200*scale),round(1800*scale));out=Image.new('RGBA',size);shadow=Image.new('RGBA',size)
    ImageDraw.Draw(shadow).polygon(coords([(35,75),(100,33),(577,69),(579,835),(88,874),(29,847)],scale,height_factor,fit),fill=(0,0,0,100))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18*scale*fit)))
    draw=ImageDraw.Draw(out)
    # Same A molded surfaces, with visible Vita plastic sampled from Sony's
    # official retail packshot. Exact rectangles/medians are in the palette asset.
    palette=[tuple(rgb)+(255,) for rgb in PALETTE['materials']]
    surfaces=[([(29,51),(78,29),(578,65),(578,830),(79,865),(29,841)],palette[0]),
              ([(29,51),(78,29),(578,65),(568,73),(81,43),(35,59)],palette[1]),
              ([(29,51),(35,59),(35,834),(76,853),(79,865),(29,841)],palette[2]),
              ([(76,43),(81,43),(81,852),(76,853)],palette[3]),
              ([(568,73),(578,65),(578,830),(568,819)],palette[4])]
    for points,color in surfaces:draw.polygon(coords(points,scale,height_factor,fit),fill=color)
    return out

def white_mark(path,crop=None):
    with Image.open(path) as im:
        rgba=im.convert('RGBA')
        if crop:rgba=rgba.crop(crop)
        mark=Image.new('RGBA',rgba.size,'white');mark.putalpha(rgba.getchannel('A'));return mark.crop(mark.getbbox())

def fit_title(draw, title, width, maxsize):
    probe=ImageFont.truetype(str(ROOT/'scripts/assets/DejaVuSans.ttf'),32)
    missing=probe.getmask(chr(0x10ffff));missing=(missing.size,bytes(missing))
    for char in set(title):
        if char.isspace():continue
        mask=probe.getmask(char)
        if (mask.size,bytes(mask))==missing:raise ValueError('Generated title needs a licensed font with this glyph; no invented romanization')
    for size in range(maxsize, 9, -1):
        f = ImageFont.truetype(str(ROOT / 'scripts/assets/DejaVuSans.ttf'), size)
        if draw.textbbox((0, 0), title, font=f)[2] <= width:
            return f
    return f

def header(t, width=None, height=None):
    w = width or round(650 * t)
    h = height or round(62 * t)
    t = w / 650
    side = round(50 * t)
    im = Image.new('RGBA', (w, h))
    d = ImageDraw.Draw(im)
    dark, light = PALETTE['header_gradient_rgb']
    for x in range(w):
        d.line((x, 0, x, h), fill=tuple((round(a + (b - a) * x / (w - 1)) for a, b in zip(dark, light))) + (255,))
    vita = white_mark(ROOT / 'scripts/assets/vita-logo.png', (116, 32, 1838, 310))
    vita = ImageOps.contain(vita, (round(188 * t), round(33 * t)), Image.Resampling.LANCZOS)
    ps = white_mark(ROOT / 'scripts/assets/playstation-logo.png')
    left = ImageOps.contain(ps, (round(45 * t), round(40 * t)), Image.Resampling.LANCZOS)
    spine = ImageOps.contain(ps, (round(32 * t), round(37 * t)), Image.Resampling.LANCZOS)
    im.alpha_composite(left, (side + round(18 * t), (h - left.height) // 2))
    im.alpha_composite(vita, (side + round(73 * t), (h - vita.height) // 2))
    im.alpha_composite(spine, ((side - spine.width) // 2, (h - spine.height) // 2))
    with Image.open(ROOT / 'scripts/assets/psn-retail.png') as a:
        psn = ImageOps.contain(a.convert('RGBA'), (round(220 * t), round(42 * t)), Image.Resampling.LANCZOS)
    im.alpha_composite(psn, (w - round(18 * t) - psn.width, (h - psn.height) // 2))
    return im

def buttons(draw, x, y, t, size):
    s = round(size * t)
    gap = round(10 * t)
    ink = (203, 224, 249, 255)
    for k in range(4):
        x0 = x + k * (s + gap)
        draw.rounded_rectangle((x0, y, x0 + s, y + s), radius=round(6 * t), fill=(24, 69, 128, 255), outline=(63, 125, 197, 255), width=max(1, round(t)))
        a = x0 + s * 0.25
        b = y + s * 0.25
        c = x0 + s * 0.75
        e = y + s * 0.75
        wd = max(1, round(1.6 * t))
        if k == 0:
            draw.line([(a, e), ((a + c) / 2, b), (c, e), (a, e)], fill=ink, width=wd)
        elif k == 1:
            draw.ellipse((a, b, c, e), outline=ink, width=wd)
        elif k == 2:
            draw.line((a, b, c, e), fill=ink, width=wd)
            draw.line((a, e, c, b), fill=ink, width=wd)
        else:
            draw.rectangle((a, b, c, e), outline=ink, width=wd)

def poster_sheet(source, title, scale):
    t = 2 * scale
    w, h, head = (round(650 * t), round(900 * t), round(62 * t))
    ah = h - head
    body = Image.new('RGBA', (w, ah))
    d = ImageDraw.Draw(body)
    for y in range(ah):
        d.line((0, y, w, y), fill=(15 + round(y / ah * 8), 45 + round(y / ah * 20), 85 + round(y / ah * 30), 255))
    for x in range(-ah, w, round(50 * t)):
        d.line((x, 0, x + ah, ah), fill=(30, 78, 134, 255), width=max(1, round(t)))
    margin = round(24 * t)
    side = round(50 * t)
    top = round(95 * t)
    art_h = round(615 * t)
    art_w = round(art_h * source.width / source.height)
    x = side + round((600 * t - art_w) / 2)
    font = fit_title(d, title, w - side - margin * 2, round(43 * t))
    bb = d.textbbox((0, 0), title, font=font)
    d.text((side + margin, round(40 * t) - bb[1]), title, font=font, fill='white')
    d.line((side + margin, top - round(12 * t), w - margin, top - round(12 * t)), fill=(66, 154, 226, 255), width=max(2, round(2 * t)))
    d.rectangle((x - round(3 * t), top - round(3 * t), x + art_w + round(3 * t), top + art_h + round(3 * t)), outline=(173, 202, 233, 255), width=max(1, round(t)))
    art = source.convert('RGBA').resize((art_w, art_h), Image.Resampling.LANCZOS)
    ps = white_mark(ROOT / 'scripts/assets/playstation-logo.png')
    ps = ImageOps.contain(ps, (round(66 * t), round(65 * t)), Image.Resampling.LANCZOS)
    ps.putalpha(ps.getchannel('A').point(lambda v: round(v * 0.6)))
    body.alpha_composite(ps, (side + round(10 * t), top + round(130 * t)))
    for n in range(4):
        cy = top + round((220 + n * 65) * t)
        cx = w - round(75 * t)
        s = round(35 * t)
        d.rounded_rectangle((cx, cy, cx + s, cy + s), radius=round(5 * t), fill=(36, 84, 143, 255), outline=(93, 153, 211, 255), width=max(1, round(t)))
        d.ellipse((cx + round(11 * t), cy + round(11 * t), cx + round(24 * t), cy + round(24 * t)), outline=(193, 219, 246, 255), width=max(1, round(t)))
    footer = top + art_h + round(24 * t)
    mark = white_mark(ROOT / 'scripts/assets/vita-logo.png', (116, 32, 1838, 310))
    mark = ImageOps.contain(mark, (round(210 * t), round(40 * t)), Image.Resampling.LANCZOS)
    body.alpha_composite(mark, (side + margin, footer + round(18 * t)))
    buttons(ImageDraw.Draw(body), w - margin - round(170 * t), footer + round(20 * t), t, 32)
    body.paste(art, (x, top))
    uv = Image.new('RGBA', (w, h))
    uv.paste(body, (0, head))
    uv.alpha_composite(header(t))
    return (uv, (x, top, art_w, art_h), 'designed title/poster/platform footer; no side strips')

def print_sheet(source, title, scale, game_id=None):
    layout=source_layout(source,scale,game_id)
    if layout['composition']=='designed_whole_poster':return poster_sheet(source,title,scale)
    if layout['composition']=='reviewed_portrait_crop_wrap':
        w=layout['front']+layout['spine'];head=layout['header'];ah=layout['height']-head
        art=source.convert('RGBA').resize((w,ah),Image.Resampling.LANCZOS,box=layout['source_crop_box'])
        uv=Image.new('RGBA',(w,layout['height']));uv.paste(art,(0,head));uv.alpha_composite(header(2*scale,w,head))
        return uv,(0,0,w,ah),'reviewed A-style proportional source crop shared over spine/bevel/front'
    t = 2 * scale
    w, h, head, side = (round(650 * t), round(900 * t), round(62 * t), round(50 * t))
    ah = h - head
    body = Image.new('RGBA', (w, ah))
    d = ImageDraw.Draw(body)
    for y in range(ah):
        f = y / max(1, ah - 1)
        d.line((0, y, w, y), fill=(round(14 + 9 * f), round(43 + 19 * f), round(80 + 35 * f), 255))
    for x in range(-ah, w, round(50 * t)):
        d.line((x, 0, x + ah, ah), fill=(30, 77, 132, 255), width=max(1, round(1.2 * t)))
    a = source.convert('RGBA')
    nativew = round(ah * a.width / a.height)
    if round(600 * t) <= nativew <= w:
        art = a.resize((nativew, ah), Image.Resampling.LANCZOS)
        uv = Image.new('RGBA', (nativew, h))
        uv.paste(art, (0, head))
        uv.alpha_composite(header(t, nativew, head))
        return (uv, (0, 0, nativew, ah), 'one whole proportional source UV wraps spine, bevel and front')
    elif nativew > w:
        arth = round(w * a.height / a.width)
        free = ah - arth
        top = round(free * 0.38) if free > round(60 * t) else 0
        art = a.resize((w, arth), Image.Resampling.LANCZOS)
        box = (0, top, w, arth)
        body.paste(art, (0, top))
        mode = 'whole art with designed title marquee and platform footer'
        margin = round(24 * t)
        if top > round(30 * t):
            d = ImageDraw.Draw(body)
            font = fit_title(d, title, w - side - margin * 2, round(min(76 * t, top * 0.48)))
            bb = d.textbbox((0, 0), title, font=font)
            tx = side + margin
            ty = round((top - (bb[3] - bb[1])) / 2) - bb[1]
            d.text((tx, ty), title, font=font, fill=(248, 251, 255, 255))
            d.line((side + margin, top - round(9 * t), w - margin, top - round(9 * t)), fill=(64, 155, 228, 255), width=max(2, round(3 * t)))
        bottom = top + arth
        bh = ah - bottom
        if bh > round(45 * t):
            mark = white_mark(ROOT / 'scripts/assets/playstation-logo.png')
            mark = ImageOps.contain(mark, (round(190 * t), round(bh * 0.65)), Image.Resampling.LANCZOS)
            mark.putalpha(mark.getchannel('A').point(lambda v: round(v * 0.12)))
            body.alpha_composite(mark, (side + margin, bottom + max(0, round((bh - mark.height) / 2))))
            label_height=min(round(68*t),max(1,bh-round(16*t)))
            label = Image.new('RGBA', (round(240*t),label_height), (0,0,0,0))
            ld = ImageDraw.Draw(label)
            ld.rounded_rectangle((0, 0, label.width - 1, label.height - 1), radius=round(5 * t), fill=(229, 239, 250, 255))
            word = white_mark(ROOT / 'scripts/assets/vita-logo.png', (116, 32, 1838, 310))
            color = Image.new('RGBA', word.size, (30, 82, 149, 255))
            color.putalpha(word.getchannel('A'))
            word_height=max(1,min(round(40*t),label.height-round(16*t)))
            word = ImageOps.contain(color, (round(204*t),word_height), Image.Resampling.LANCZOS)
            label.alpha_composite(word, ((label.width - word.width) // 2, (label.height - word.height) // 2))
            body.alpha_composite(label, (side + margin, bottom + round((bh - label.height) / 2)))
            d = ImageDraw.Draw(body)
            bs = 30 if bh < round(160 * t) else 40
            buttons(d, w - margin - round((4 * bs + 30) * t), bottom + round((bh - bs * t) / 2), t, bs)
            d.line((side + margin, ah - round(13 * t), w - margin, ah - round(13 * t)), fill=(59, 144, 217, 255), width=max(1, round(t)))
    else:
        raise ValueError('Unclassified source composition')
    # Protect the complete original after all decorative drawing. Design panels
    # may never paint over the source, including transparent original pixels.
    body.paste(art,box[:2])
    uv = Image.new('RGBA', (w, h))
    uv.paste(body, (0, head))
    uv.alpha_composite(header(t))
    return (uv, box, mode)

def printable_sheet(source,scale,fit=1,title='',game_id=None):
    if fit!=1:raise ValueError('Canonical case cannot adapt its physical shape')
    uv,box,mode=print_sheet(source,title,scale,game_id);p=source_layout(source,scale,game_id)
    if box!=p['source_art_box'] or uv.size!=(p['front']+p['spine'],p['height']):raise ValueError('Print layout mismatch')
    return uv,box,p


def split_print(uv,p):
    # Disjoint continuous strips reconstruct the exact original sheet.
    side=p['spine'];bevel=p['bevel'];height=p['height']
    return uv.crop((0,0,side-bevel,height)),uv.crop((side-bevel,0,side,height)),uv.crop((side,0,uv.width,height))

def render3d(source, title='', game_id=None):
    size = case_size(source,game_id)
    scale = size[0] / 1200
    t = 2 * scale
    out = template(scale, height_factor=1, fit=1)
    uv, box, mode = print_sheet(source, title, scale,game_id)
    side = round(uv.width * 50 / 650)
    bevel = round(uv.width * 8 / 650)
    h = uv.height
    front = uv.crop((side, 0, uv.width, h))
    spine = uv.crop((0, 0, side - bevel, h))
    corner = uv.crop((side - bevel, 0, side, h))

    def project(p):
        return coords(p, scale, 1, 1)
    fc = project([(76, 43), (568, 73), (568, 819), (76, 853)])
    out.alpha_composite(warp(front, fc, size))
    spine.alpha_composite(Image.new('RGBA', spine.size, (0, 0, 0, 43)))
    out.alpha_composite(warp(spine, project([(35, 59), (70, 45.34), (70, 850.22), (35, 834)]), size))
    out.alpha_composite(warp(corner, project([(70, 45.34), (76, 43), (76, 853), (70, 850.22)]), size))
    ImageDraw.Draw(out).line([fc[0], fc[1], fc[2]], fill=(172, 197, 224, 170), width=max(1, round(scale)))
    return (out, box)
