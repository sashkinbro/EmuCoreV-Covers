import unittest
from PIL import Image
from pipeline import image_identity, normalize, resolve, contain, download_one, inspect, ImageRedirectHandler, portrait_size, case_size, render3d
from unittest.mock import patch
from pathlib import Path
import tempfile,io
from renderer import printable_sheet, split_print, printable_size, case_shape, coords, fit_title,LAYOUT_OVERRIDES
from pipeline import generate,sha
from PIL import ImageDraw

class PipelineTests(unittest.TestCase):
    def test_image_host_and_identity_fail_closed(self):
        self.assertEqual(image_identity('https://images.igdb.com/igdb/image/upload/t_cover_big/co123.jpg'), ('co123','jpg'))
        for u in ['http://images.igdb.com/igdb/image/upload/t_cover_big/co123.jpg','https://evil.example/co123.jpg','https://images.igdb.com/igdb/image/upload/t_cover_big/co123.jpg?x=1']:
            with self.assertRaises(ValueError): image_identity(u)

    def test_mapping_does_not_accept_partial_or_ambiguous_name(self):
        games={'1':{'name':'Persona 4 Golden'},'2':{'name':'Mortal Kombat'},'3':{'name':'Mortal Kombat'}}
        self.assertEqual(resolve('Persona 4 GOLDEN',games), ['1'])
        self.assertEqual(resolve('Persona',games), [])
        self.assertEqual(resolve('Mortal Kombat',games), ['2','3'])
        self.assertEqual(normalize('HELLDIVERS™'),normalize('Helldivers'))

    def test_foreign_redirect_rejected_before_request(self):
        with self.assertRaises(ValueError):ImageRedirectHandler().redirect_request(None,None,302,'',{},'https://example.com/art.png')

    def test_original_png_bytes_preserved_even_for_jpg_url_and_resumed(self):
        b=io.BytesIO();Image.new('RGB',(41,59),'purple').save(b,'PNG');raw=b.getvalue()
        class Response(io.BytesIO):
            url='https://images.igdb.com/igdb/image/upload/t_original/co123.jpg'
            headers={}
        g={'igdb_id':1,'name':'Fixture','cover_url':'https://images.igdb.com/igdb/image/upload/t_cover_big/co123.jpg'}
        with tempfile.TemporaryDirectory() as d:
            with patch('pipeline.IMAGE_OPENER.open',return_value=Response(raw)) as network:
                key,out=download_one((d,g,{}))
            self.assertEqual(out['original_path'],'originals/co123.png')
            self.assertEqual((Path(d)/out['original_path']).read_bytes(),raw)
            with patch('pipeline.IMAGE_OPENER.open',side_effect=AssertionError('Resume must not fetch')):
                _,resumed=download_one((d,g,out))
            self.assertEqual(resumed,out)

    def test_animated_original_bytes_retained_and_static_frame_choice_explicit(self):
        b=io.BytesIO();frames=[Image.new('RGB',(41,59),c) for c in ['purple','green']]
        frames[0].save(b,'GIF',save_all=True,append_images=frames[1:],duration=100,loop=0);raw=b.getvalue()
        class Response(io.BytesIO):
            url='https://images.igdb.com/igdb/image/upload/t_original/co123.jpg'
            headers={}
        g={'igdb_id':1,'name':'Animated fixture','cover_url':'https://images.igdb.com/igdb/image/upload/t_cover_big/co123.jpg'}
        with tempfile.TemporaryDirectory() as d:
            with patch('pipeline.IMAGE_OPENER.open',return_value=Response(raw)):
                _,out=download_one((d,g,{}))
            self.assertEqual(out['status'],'downloaded');self.assertEqual(out['original_path'],'originals/co123.gif')
            self.assertEqual((Path(d)/out['original_path']).read_bytes(),raw)
            self.assertEqual(out['original']['frame_count'],2);self.assertEqual(out['derivative_source_frame'],0)

    def test_contain_preserves_all_four_corners(self):
        im=Image.new('RGB',(400,100),'red')
        im.paste((0,255,0),(0,0,40,30));im.paste((0,0,255),(360,70,400,100))
        out,box=contain(im,(600,900))
        self.assertEqual(box,(0,375,600,150))
        self.assertEqual(out.getpixel((0,375)),(0,255,0,255))
        self.assertEqual(out.getpixel((599,524)),(0,0,255,255))
        self.assertEqual(out.getpixel((0,0))[3],0)

    def test_flat_contain_fills_a_bound_without_cropping_or_stretching(self):
        expected=[((600,800),(0,50,600,800)),((100,100),(0,150,600,600)),((640,360),(0,300,640,360)),((3376,4501),(0,281,3376,4501))]
        for size,expected_box in expected:
            im=Image.new('RGB',size,'red');canvas=portrait_size(im);out,box=contain(im,canvas)
            self.assertEqual(canvas[0]*3,canvas[1]*2)
            self.assertEqual(box,expected_box)
            self.assertEqual(max(box[2]/canvas[0],box[3]/canvas[1]),1)

    def test_case_contains_whole_art_at_full_printable_bounds(self):
        for size in [(600,800),(100,100),(640,360)]:
            im=Image.new('RGB',size,'red');out,box=render3d(im)
            self.assertGreaterEqual(out.width,1200);self.assertGreaterEqual(out.height,1800)
            bounds=printable_size(im)
            self.assertEqual(max(box[2]/bounds[0],box[3]/bounds[1]),1)
            self.assertLess(abs(box[3]-size[1]*box[2]/size[0]),1)
            self.assertEqual(out.getpixel((0,0))[3],0)
        large=Image.new('RGB',(3376,4501),'red');self.assertGreater(case_size(large)[0],3700)

    def test_spine_bevel_front_reconstruct_one_exact_print_sheet(self):
        # Every unique source column must occur once; reflected/duplicated title
        # strips and stretched edge pixels cannot satisfy byte-exact reassembly.
        im=Image.new('RGB',(650,838))
        for x in range(im.width):
            for y in range(im.height):im.putpixel((x,y),(x%256,y%256,(x+y)%256))
        uv,box,parts=printable_sheet(im,scale=0.5)
        spine,bevel,front=split_print(uv,parts)
        rebuilt=Image.new('RGBA',uv.size);x=0
        for strip in (spine,bevel,front):rebuilt.paste(strip,(x,0));x+=strip.width
        self.assertEqual(x,uv.width)
        self.assertEqual(rebuilt.tobytes(),uv.tobytes())
        # This source exactly fits the combined body without any image crop.
        self.assertEqual(box,(0,0,650,838))
        self.assertEqual(uv.crop((0,parts['header'],650,900)).convert('RGB').tobytes(),im.tobytes())

    def test_case_dimensions_meet_runtime_bounds_for_all_corpus_aspects(self):
        for w,h in [(600,800),(100,100),(640,360),(3376,4501)]:
            im=Image.new('RGB',(w,h));cw,ch=case_size(im)
            self.assertEqual(cw*3,ch*2)
            self.assertLessEqual(max(cw,ch),16384)
            self.assertLessEqual(cw*ch,64*1024*1024)

    def test_canonical_composition_preserves_whole_source_without_edge_fill(self):
        for size in [(600,800),(100,100),(640,360),(3376,4501),(50,1000),(1000,50)]:
            im=Image.new('RGBA',size,'purple')
            im.paste('black',(0,0,size[0],max(1,size[1]//9)))
            uv,box,p=printable_sheet(im,scale=.5,title='Fixture')
            x,y,w,h=box;art=uv.crop((x,p['header']+y,x+w,p['header']+y+h))
            self.assertEqual(p['height'],900)
            expected=im.resize(art.size,Image.Resampling.LANCZOS)
            self.assertEqual(art.tobytes(),expected.tobytes())
            self.assertTrue(abs(art.height-size[1]*art.width/size[0])<=.5 or abs(art.width-size[0]*art.height/size[1])<=.5)
            self.assertEqual(art.getpixel((art.width//2,0)),(0,0,0,255))

    def test_fullbleed_print_preserves_original_transparent_pixels_too(self):
        im=Image.new('RGBA',(650,838),(128,0,128,0));im.putpixel((40,50),(255,0,0,128))
        uv,box,p=printable_sheet(im,.5)
        self.assertEqual(uv.crop((0,p['header'],650,900)).tobytes(),im.tobytes())

    def test_authentic_white_marks_occupy_left_spine_and_right_front_header(self):
        uv,_,p=printable_sheet(Image.new('RGB',(650,838),'purple'),scale=0.5)
        # White logo pixels must be present in each separate intended area.
        for rect in [(0,0,p['spine'],p['header']),(p['spine'],0,p['spine']+330,p['header']),(uv.width-60,0,uv.width,p['header'])]:
            pixels=uv.crop(rect).get_flattened_data()
            self.assertGreater(sum(r>240 and g>240 and b>240 and a>240 for r,g,b,a in pixels),10)
        # The front artwork itself keeps its source color, including purple.
        self.assertEqual(uv.getpixel((uv.width//2,p['header']+100)),(128,0,128,255))

    def test_retail_header_has_compact_single_line_left_marks_without_caption(self):
        uv,_,p=printable_sheet(Image.new('RGB',(650,838),'purple'),.5)
        header=uv.crop((p['spine'],0,p['spine']+280,p['header']))
        ys=[y for y in range(header.height) for x in range(header.width) if min(header.getpixel((x,y))[:3])>240]
        self.assertGreater(min(ys),p['header']*.19)
        self.assertLess(max(ys),p['header']*.81)
        # Separate front-left glyph and authentic wordmark, each with white ink.
        for x0,x1 in [(18,63),(73,261)]:
            self.assertTrue(any(min(uv.getpixel((p['spine']+x,y))[:3])>240 for x in range(x0,x1) for y in range(p['header'])))

    def test_every_source_uses_same_canonical_vertical_case_geometry(self):
        geometry=[(76,43),(568,73),(568,819),(76,853)]
        base=coords(geometry,1)
        for size in [(600,800),(100,100),(640,360),(3376,4501),(50,1000),(1000,50)]:
            source=Image.new('RGB',size);self.assertEqual(case_shape(source),(1,1))
            scale=case_size(source)[0]/1200
            for actual,expected in zip(coords(geometry,scale),base):
                self.assertLessEqual(abs(actual[0]/scale-expected[0]),.51)
                self.assertLessEqual(abs(actual[1]/scale-expected[1]),.51)

    def test_normal_art_itself_wraps_over_entire_spine_not_a_blue_strip(self):
        source=Image.new('RGBA',(600,800),'orange');source.paste('purple',(0,0,25,800))
        uv,box,p=printable_sheet(source,.5,title='Normal fixture')
        self.assertEqual(p['composition'],'full_source_wrap')
        self.assertEqual(box,(0,0,uv.width,uv.height-p['header']))
        spine,bevel,front=split_print(uv,p)
        self.assertEqual(spine.getpixel((0,p['header']+100)),(128,0,128,255))
        self.assertEqual(uv.crop((0,p['header'],uv.width,uv.height)).tobytes(),source.resize((uv.width,box[3]),Image.Resampling.LANCZOS).tobytes())

    def test_square_and_landscape_have_source_title_and_platform_ink_panels(self):
        for size in [(100,100),(640,360)]:
            source=Image.new('RGBA',size,'purple');uv,box,p=printable_sheet(source,.5,title='Whole source title + Edition')
            self.assertEqual(p['composition'],'designed_title_and_platform_footer')
            x,y,w,h=box;top=uv.crop((0,p['header'],uv.width,p['header']+y)).convert('RGB')
            bottom=uv.crop((0,p['header']+y+h,uv.width,uv.height)).convert('RGB')
            for panel in (top,bottom):
                self.assertGreater(panel.height,0)
                self.assertGreater(max(v[1] for v in panel.getextrema()),220)

    def test_unsupported_generated_title_glyph_is_not_silently_tofu(self):
        draw=ImageDraw.Draw(Image.new('RGBA',(600,200)))
        with self.assertRaises(ValueError):fit_title(draw,'Unsupported '+chr(0x10ffff),500,40)

    def test_short_footer_graphics_never_overlap_world_election_source_panel(self):
        source=Image.new('RGBA',(558,650),'purple')
        uv,box,p=printable_sheet(source,.5,title='World Election')
        x,y,w,h=box;actual=uv.crop((x,p['header']+y,x+w,p['header']+y+h))
        self.assertEqual(actual.tobytes(),source.resize((w,h),Image.Resampling.LANCZOS).tobytes())

    def test_normal_two_by_three_portrait_is_reviewed_full_bleed_wrap_not_columns(self):
        source=Image.new('RGBA',(720,1080),'purple')
        uv,box,p=printable_sheet(source,.5,title="Jack N' Jill DX",game_id='107044')
        self.assertEqual(p['composition'],'reviewed_portrait_crop_wrap')
        self.assertEqual(box,(0,0,650,838))
        self.assertGreater(p['source_crop_box'][1],0)
        spine,_,_=split_print(uv,p)
        self.assertEqual(spine.getpixel((0,p['header']+30)),(128,0,128,255))

    def test_unsafe_destination_crop_remains_complete_source_poster_exception(self):
        source=Image.new('RGBA',(359,512),'purple')
        uv,box,p=printable_sheet(source,.5,title='Vitamin X Destination',game_id='98664')
        self.assertEqual(p['composition'],'designed_whole_poster')
        self.assertEqual(p['source_crop_box'],(0,0,359,512))
        x,y,w,h=box;self.assertEqual(uv.crop((x,p['header']+y,x+w,p['header']+y+h)).tobytes(),source.resize((w,h),Image.Resampling.LANCZOS).tobytes())

    def test_reviewed_anchor_is_bound_to_original_bytes_not_only_game_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.png';Image.new('RGB',(720,1080),'purple').save(path)
            game={'name':"Jack N' Jill DX",'original_path':'fixture.png','original':{'sha256':sha(path)}}
            with self.assertRaisesRegex(ValueError,'Reviewed portrait original changed'):
                generate((directory,'107044',game,'fixture-recipe'))

    def test_reviewed_source_specific_intermediates_and_five_exceptions_do_not_drift(self):
        self.assertEqual(LAYOUT_OVERRIDES['8616']['anchor_y'],.70)
        self.assertEqual(LAYOUT_OVERRIDES['90630']['anchor_y'],.25)
        self.assertEqual({k for k,r in LAYOUT_OVERRIDES.items() if r['layout']=='designed_whole_poster'},{'52534','60766','62078','80952','98664'})

if __name__=='__main__': unittest.main()
