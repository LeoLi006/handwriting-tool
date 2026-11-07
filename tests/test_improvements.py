from pathlib import Path
import tempfile
import unittest
import warnings
from unittest.mock import patch
from PIL import ImageChops
import handwriting as hw
from readable_layout import safe_math_segments, fit_math_lines, text_tokens
from table_render import column_widths, _cell_lines


def renderer():
    return hw.Renderer(40,150,False,1.4,0,hw.FALLBACK,hw.FALLBACK,1,jitter=0,glyph_variation=0)


class ReadabilityTests(unittest.TestCase):
    def test_intrinsic_columns_give_description_more_room(self):
        r=renderer()
        widths=column_widths(r,[['序号','value','说明'],['1','12.50 mV','reconstruction 中文说明较长，必须获得更多宽度']],32,10)
        self.assertGreater(widths[2],widths[0]*2)
        self.assertGreaterEqual(widths[1],r._adv('12.50 mV',32)+20)
        self.assertEqual(sum(widths),r.w-r.left-r.right)

    def test_short_expressions_are_not_split_between_cell_lines(self):
        r=renderer()
        for expression in ['reconstruction','12.50 mV','1.25e-3 A','125.75']:
            width=r._adv(expression,32)+1
            lines=_cell_lines(r,'前文 '+expression,width,32)
            strings=[''.join(value for kind,value,_ in line['parts'] if kind=='text') for line in lines]
            self.assertTrue(any(expression in line for line in strings),strings)
        self.assertIn('12.50 mV',list(text_tokens('值为 12.50 mV。')))

    def test_formula_split_preserves_source_and_protects_groups(self):
        source=r'X=\frac{a+b}{c-d}+\sqrt{e+f}+(g-h)+q_{i+1}+\begin{matrix}1&2\\3&4\end{matrix}'
        parts,reason=safe_math_segments(source)
        self.assertEqual(''.join(parts),source)
        for protected in [r'\frac{a+b}{c-d}',r'\sqrt{e+f}','(g-h)','q_{i+1}',r'\begin{matrix}1&2\\3&4\end{matrix}']:
            self.assertTrue(any(protected in part for part in parts),parts)
        lines,_=fit_math_lines(source,len,40)
        self.assertEqual(''.join(lines),source)
        for unsafe in [r'\left(a+b\right)',r'\langle a+b\rangle',r'|a+b|']:
            self.assertEqual(safe_math_segments(unsafe)[0],[unsafe])

    def test_formula_reflows_instead_of_shrinking_complete_sum(self):
        source='W='+'+'.join(r'\frac{a_{%d}+b_{%d}}{c_{%d}}'%(i,i,i) for i in range(20))
        with warnings.catch_warnings(record=True):
            _,r=hw.render_markdown('$$'+source+'$$',jitter=0,glyph_variation=0)
        self.assertTrue(any(i.object=='公式分行' for i in r.issues))
        self.assertFalse(any('等比缩放' in i.reason for i in r.issues))

    def test_control_character_in_math_is_reported(self):
        with warnings.catch_warnings(record=True):
            _,r=hw.render_markdown('$$a+'+chr(12)+'rac{b}{c}$$',jitter=0,glyph_variation=0)
        self.assertTrue(any(i.severity=='错误' and i.object=='控制字符' for i in r.issues))

    def test_original_fixture_contains_real_tex_commands(self):
        text=(Path(__file__).resolve().parents[1]/'examples'/'regression'/'综合回归.md').read_text(encoding='utf-8')
        self.assertFalse(any(ord(c)<32 and c not in '\r\n\t' for c in text))
        formula=next(b[1] for b in hw.markdown_to_blocks(text) if b[0]=='formula' and b[1].startswith('R='))
        self.assertIn(chr(92)+'frac{a_1+b_1}',formula)
        self.assertIn(chr(92)+'sqrt{u_1+v_1}',formula)

    def test_split_formula_page_limit_does_not_fall_back_and_repaint(self):
        original=hw.Renderer.__init__
        def initialize(r,*args,**kwargs):
            original(r,*args,**kwargs);r.y=r.h-r.bottom-80
        source='$$R='+'+'.join(f'x_{{{i}}}' for i in range(60))+'$$'
        with patch.object(hw.Renderer,'__init__',initialize),warnings.catch_warnings(record=True):
            first,_=hw.render_markdown(source,page_limit=1,jitter=0,glyph_variation=0)
            full,_=hw.render_markdown(source,jitter=0,glyph_variation=0)
        self.assertGreater(len(full),1)
        self.assertIsNone(ImageChops.difference(first[0],full[0]).getbbox())


class PageGroupTests(unittest.TestCase):
    def test_explicit_group_moves_heading_diagram_and_caption_together(self):
        r=renderer();r.y=r.h-r.bottom-100
        blocks=hw.markdown_to_blocks('<!-- keep-start -->\n## 标题\n```diagram\n──┼──\n  │\n```\n<!-- caption: 原创图注 -->\n<!-- keep-end -->',include_locations=True)
        with warnings.catch_warnings(record=True):
            for block in blocks: r.draw_block(block)
        selected=[b for b in r.block_map if b['kind'] in {'heading','diagram','caption'}]
        self.assertEqual({b['page'] for b in selected},{2})
        self.assertEqual(len(selected),3)

    def test_pagebreak_does_not_emit_empty_leading_or_trailing_pages(self):
        with warnings.catch_warnings(record=True):
            pages,_=hw.render_markdown('<!-- pagebreak -->\n一\n<!-- pagebreak -->\n<!-- pagebreak -->\n二\n<!-- pagebreak -->',jitter=0,glyph_variation=0)
        self.assertEqual(len(pages),2)

    def test_manual_break_inside_keep_group_is_never_ignored(self):
        with warnings.catch_warnings(record=True):
            pages,r=hw.render_markdown('之前\n\n<!-- keep-start -->\n<!-- pagebreak -->\n之后\n<!-- keep-end -->',jitter=0,glyph_variation=0)
        self.assertEqual(len(pages),2)
        self.assertTrue(any('手动分页优先' in item.reason for item in r.issues))

    def test_oversized_group_degrades_once_without_losing_text(self):
        source='<!-- keep-start -->\n'+'文字'*1800+'\n<!-- keep-end -->'
        with warnings.catch_warnings(record=True):
            pages,r=hw.render_markdown(source,jitter=0,glyph_variation=0)
        self.assertGreater(len(pages),1)
        self.assertEqual(sum(i.object=='同页组合' and '超过一页' in i.reason for i in r.issues),1)

    def test_group_preview_and_full_first_page_match(self):
        source='正文。\n\n<!-- keep-next -->\n## 标题\n```diagram\n──┼──\n  │\n```\n<!-- caption: 图注 -->\n\n'+'正文'*1000
        with warnings.catch_warnings(record=True):
            first,_=hw.render_markdown(source,page_limit=1)
            full,_=hw.render_markdown(source)
        self.assertIsNone(ImageChops.difference(first[0],full[0]).getbbox())


class DocumentProfileTests(unittest.TestCase):
    def test_conversion_records_do_not_embed_full_private_source_path(self):
        from managed_output import generate_document
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'personal'/'one.md';source.parent.mkdir()
            source.write_text('![缺失](missing.png)',encoding='utf-8')
            with warnings.catch_warnings(record=True):
                result=generate_document(source,root/'output',jitter=0,glyph_variation=0)
            for path in (root/'output').rglob('*'):
                if path.suffix in {'.json','.txt'}:
                    text=path.read_text(encoding='utf-8')
                    self.assertNotIn(str(root),text)
                    self.assertNotIn(str(root).replace(chr(92),chr(92)*2),text)
            self.assertEqual(result.issues[0]['source'],'one.md')

    def test_rename_and_copy_do_not_share_identity(self):
        from document_settings import DocumentSettings
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);a=root/'first.md';a.write_text('original',encoding='utf-8')
            store=DocumentSettings(root/'app'/'documents.json');store.save(a,dict(font='WenKai',font_size=42,export_format='PDF 文件'))
            moved=root/'moved.md';a.rename(moved)
            self.assertEqual(store.load(moved)[0]['font_size'],42)
            copy=root/'other'/'moved.md';copy.parent.mkdir();copy.write_bytes(moved.read_bytes())
            self.assertEqual(store.load(copy)[0],{})
            moved.write_text('edited in place',encoding='utf-8')
            self.assertEqual(store.load(moved)[0]['font_size'],42)
            self.assertNotIn(str(root),store.path.read_text(encoding='utf-8'))
            self.assertNotIn('edited in place',store.path.read_text(encoding='utf-8'))
            store.reset(moved);self.assertEqual(store.load(moved)[0],{})

    def test_same_path_replaced_by_different_file_does_not_inherit(self):
        from document_settings import DocumentSettings
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'same.md';source.write_text('one')
            store=DocumentSettings(root/'profiles.json');store.save(source,dict(font_size=44))
            old=root/'old.md';source.rename(old);source.write_text('different')
            data,note=store.load(source)
            self.assertEqual(data,{});self.assertIn('身份',note)

    def test_invalid_config_is_not_silently_overwritten(self):
        from document_settings import DocumentSettings
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'one.md';source.write_text('one')
            store=DocumentSettings(root/'profiles.json');store.path.write_text('{broken')
            self.assertEqual(store.load(source)[0],{})
            with self.assertRaises(ValueError):store.save(source,dict(font_size=42))
            note=store.reset(source);self.assertIn('备份',note)
            self.assertEqual(len(list(root.glob('profiles.invalid-*.json'))),1)

    def test_legacy_profile_requires_both_path_and_content_hash(self):
        import json
        from document_settings import DocumentSettings, identity
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'one.md';source.write_text('one')
            store=DocumentSettings(root/'profiles.json');ident=identity(source);ident.pop('file_key')
            store.path.write_text(json.dumps(dict(version=1,records={'legacy':dict(ident,settings=dict(font_size=42,export_format='PNG + PDF'))})))
            data,note=store.load(source)
            self.assertEqual(data['export_format'],'PDF 文件');self.assertIn('迁移',note)
            self.assertEqual(json.loads(store.path.read_text())['version'],2)


class ComparisonTests(unittest.TestCase):
    def test_both_sides_force_identical_seed_and_dpi(self):
        from comparison import comparable_params, differences
        before=comparable_params(dict(jitter=0,seed=1));after=comparable_params(dict(jitter=1,seed=9))
        self.assertEqual(differences(before,after),{'jitter':(0,1)})

    def test_formula_cache_invalidates_when_font_file_is_replaced(self):
        import shutil
        import formula
        with tempfile.TemporaryDirectory() as directory:
            font=Path(directory)/'font.ttf';shutil.copyfile(hw.FALLBACK,font)
            before=formula.render_formula('abc+123',str(font)).image
            shutil.copyfile(Path(hw.FONT_DIR)/'MaShanZheng-Regular.ttf',font)
            after=formula.render_formula('abc+123',str(font)).image
            self.assertTrue(before.size!=after.size or before.tobytes()!=after.tobytes())
            formula.fm.fontManager.ttflist[:]=[item for item in formula.fm.fontManager.ttflist if item.fname!=str(font)]
            formula._family_cache.pop(str(font),None)
            for cache in (getattr(formula.fm,'_get_font',None),getattr(formula.fm.fontManager,'_findfont_cached',None)):
                if hasattr(cache,'cache_clear'):cache.cache_clear()
            import gc
            gc.collect()


class BatchProfileTests(unittest.TestCase):
    def test_saved_document_parameters_override_global_for_each_job(self):
        from batch_tasks import run_batch
        received=[]
        def converter(path,**params):
            received.append((path,params['font_size'],params['export_format']))
            return ['result.png']
        jobs=[dict(id='a',path='first.md',params=dict(font_size=32,export_format='pdf')),
              dict(id='b',path='second.md',params=dict(font_size=48,export_format='png'))]
        result=run_batch(jobs,dict(font_size=40,export_format='png'),lambda:False,lambda *a:None,converter)
        self.assertTrue(all(item['status']=='完成' for item in result))
        self.assertEqual(received,[('first.md',32,'pdf'),('second.md',48,'png')])


if __name__=='__main__': unittest.main()
