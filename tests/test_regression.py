import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
from PIL import Image, ImageChops
import formula
import handwriting as hw
from preview_cache import PreviewCache, fingerprint
from precise_plot import plot_image


class RegressionTests(unittest.TestCase):
    def test_nested_box_inside_fraction_stays_two_dimensional(self):
        normal = formula.render_formula(r'\frac{1}{1+t}')
        boxed = formula.render_formula(r'\boxed{\frac{1}{\boxed{1+t}}}')
        self.assertGreater(boxed.height, normal.height)
        self.assertGreater(boxed.width, normal.width)
        aligned = formula.render_formula(r'\begin{aligned}u&=1\\v&=\boxed{\frac{1}{\boxed{1+t}}}\end{aligned}')
        self.assertGreater(aligned.height, boxed.height)

    def test_image_relative_path_and_missing_image_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'assets').mkdir()
            Image.new('RGB',(100,40),'red').save(root/'assets'/'a.png')
            with warnings.catch_warnings(record=True):
                pages, r=hw.render_markdown('# A\n\n![图注](assets/a.png)\n\n![缺失](missing.png)',
                    source_path=root/'sample.md',jitter=0,glyph_variation=0)
            self.assertTrue(any(p[0]>200 and p[1]<20 for p in pages[0].getdata()))
            issue=next(i for i in r.issues if i.severity=='错误')
            self.assertEqual(issue.line,5)
            self.assertIn('A',issue.section)
            self.assertIn('missing.png',issue.reason)

    def test_formula_error_has_exact_source_and_preserved_text(self):
        text='# Test\n\n正常。\n\n$$\\badcommand{x}$$'
        with warnings.catch_warnings(record=True):
            _,r=hw.render_markdown(text,jitter=0,glyph_variation=0,source_path='test.md')
        self.assertEqual(len(r.issues),1)
        issue=r.issues[0]
        self.assertEqual((issue.source,issue.line,issue.severity),('test.md',5,'错误'))
        self.assertIn('已保留文字',issue.reason)

    def test_plot_coordinates_styles_and_no_execution(self):
        data=dict(xlim=[-2,2],ylim=[-2,2],axes=False,
                  points=[dict(x=0,y=0,kind='zero')],
                  lines=[{'from':[-2,1],'to':[2,1],'style':'dashed'},
                         {'from':[-2,-1],'to':[2,-1],'style':'solid'}])
        image=plot_image(json.dumps(data),hw.FALLBACK,30,600,400)
        self.assertEqual(image.getpixel((300,200)),(255,255,255,255))
        # Coordinate transform places y=1 at row 124 and y=-1 at 276.
        self.assertTrue(any(image.getpixel((x,124))==(255,255,255,255) for x in range(170,430)))
        self.assertTrue(all(image.getpixel((x,276))!=(255,255,255,255) for x in range(170,430)))
        for bad in ({'run':'__import__("os")'}, {'xlim':[0,0]}, {'points':[{'x':float('nan'),'y':0}]},
                    {'lines':[{'from':[0,0],'to':[9,0]}]}):
            with self.assertRaises(ValueError): plot_image(json.dumps(bad),hw.FALLBACK,30,600)

    def test_cache_reuses_pages_and_invalidates_on_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'a.md'
            image=root/'a.png'; Image.new('RGB',(20,20),'red').save(image)
            source.write_text('![local](a.png)\n\n'+'文字'*700,encoding='utf-8')
            params=dict(jitter=0,glyph_variation=0)
            cache=PreviewCache(root/'cache')
            first,cached=cache.get(source,params,1)
            self.assertFalse(cached)
            with patch.object(hw,'render_markdown',side_effect=AssertionError('must reuse')):
                again,cached=cache.get(source,params,1)
            self.assertTrue(cached); self.assertEqual(first,again)
            old=fingerprint(source,params)
            Image.new('RGB',(20,20),'blue').save(image)
            self.assertNotEqual(old,fingerprint(source,params))
            self.assertNotEqual(old,fingerprint(source,dict(params,font_size=42)))
            source.write_text('changed',encoding='utf-8')
            self.assertNotEqual(old,fingerprint(source,params))

    def test_preview_first_page_exactly_matches_full_output(self):
        text='# 标题\n\n'+'正文与 $x^2$ 的内容。'*200
        params=dict(jitter=.2,glyph_variation=.8)
        with warnings.catch_warnings(record=True):
            preview,_=hw.render_markdown(text,page_limit=1,**params)
            full,_=hw.render_markdown(text,**params)
        self.assertIsNone(ImageChops.difference(preview[0],full[0]).getbbox())

    def test_components_are_independent_of_body_shape(self):
        text='| A | B |\n|---|---|\n| 内容 | $x^2$ |\n\n```diagram\n──┼──\n  │\n```\n\n$$x+1$$'
        with warnings.catch_warnings(record=True):
            first,_=hw.render_markdown(text,jitter=0,glyph_variation=0)
            second,_=hw.render_markdown(text,jitter=0,glyph_variation=1.5)
        self.assertIsNone(ImageChops.difference(first[0],second[0]).getbbox())

    def test_orphan_heading_moves_with_following_lines(self):
        r=hw.Renderer(40,150,False,1.4,0,hw.FALLBACK,hw.FALLBACK,1,jitter=0,glyph_variation=0)
        r.y=r.h-r.bottom-r.line_spacing*2
        r.draw_block(('heading',2,'页底标题'))
        self.assertEqual(r.page_count,2)

    def test_layout_audit_detects_overlap(self):
        r=hw.Renderer(40,150,False,1.4,0,hw.FALLBACK,hw.FALLBACK,1,jitter=0,glyph_variation=0)
        with warnings.catch_warnings(record=True):
            r.record_region('first',(100,100,300,200))
            r.record_region('second',(150,150,350,250))
        self.assertTrue(any('重叠' in item.reason for item in r.issues))

    def test_first_page_does_not_render_later_formula(self):
        with patch.object(formula,'render_formula',side_effect=AssertionError('later formula rendered')) as render:
            hw.render_markdown('正文'*4000+'\n\n$$x^2$$',page_limit=1,jitter=0,glyph_variation=0)
        render.assert_not_called()

    def test_table_headers_repeat_on_every_page(self):
        original=hw.Renderer._draw_char
        headers=[]
        def draw(renderer,char,*args):
            if char=='H': headers.append(renderer.page_count)
            return original(renderer,char,*args)
        text='| H | value |\n|---|---|\n'+'\n'.join(f'| {i} | data |' for i in range(65))
        with patch.object(hw.Renderer,'_draw_char',draw), warnings.catch_warnings(record=True):
            pages,_=hw.render_markdown(text,jitter=0,glyph_variation=0)
        self.assertEqual(headers,list(range(1,len(pages)+1)))

    def test_tall_formula_is_contained_and_reported(self):
        latex=r'\begin{pmatrix}'+r'\\'.join('1' for _ in range(60))+r'\end{pmatrix}'
        with warnings.catch_warnings(record=True):
            _,r=hw.render_markdown('$$'+latex+'$$',jitter=0,glyph_variation=0)
        self.assertLessEqual(r.y,r.h-r.bottom)
        self.assertTrue(any('缩放' in i.reason for i in r.issues))

    def test_issue_callback_points_to_actual_page_after_object_moves(self):
        latex=r'\begin{pmatrix}'+r'\\'.join('1' for _ in range(60))+r'\end{pmatrix}'
        collected=[]
        with warnings.catch_warnings(record=True):
            hw.render_markdown('# 报告\n\n'+'说明文字。'*15+'\n\n$$'+latex+'$$',
                               jitter=0,glyph_variation=0,issue_sink=collected.append)
        issue=next(item for item in collected if item['object']=='独立公式')
        self.assertEqual((issue['line'],issue['page']),(5,2))


if __name__ == '__main__': unittest.main()
