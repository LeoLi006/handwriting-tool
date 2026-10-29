import pathlib
import tempfile
import unittest
import warnings
import zipfile

import handwriting as hw
from word_reader import NS, read_docx


class WordReaderTests(unittest.TestCase):
    def document(self, directory, body, styles=''):
        path = pathlib.Path(directory) / 'input.docx'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml',
                f'<w:document xmlns:w="{NS["w"]}" xmlns:m="{NS["m"]}">'
                f'<w:body>{body}</w:body></w:document>')
            if styles:
                archive.writestr('word/styles.xml', styles)
        return path

    def test_order_styles_links_lists_and_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(directory, '''
              <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>标题</w:t></w:r></w:p>
              <w:p><w:hyperlink><w:r><w:t>链接文字</w:t></w:r></w:hyperlink></w:p>
              <w:p><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>列表</w:t></w:r></w:p>
              <w:tbl><w:tr><w:tc><w:p><w:r><w:t>甲</w:t></w:r></w:p></w:tc>
              <w:tc><w:p><w:r><w:t>乙</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
              <w:p><w:r><w:t>最后</w:t></w:r></w:p>''')
            self.assertEqual(read_docx(path), '# 标题\n\n链接文字\n\n- 列表\n\n甲 ｜ 乙\n\n最后')

    def test_native_math_and_end_to_end_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(directory, '''<w:p><w:r><w:t>公式</w:t></w:r>
              <m:oMath><m:f><m:num><m:r><m:t>1</m:t></m:r></m:num>
              <m:den><m:r><m:t>2</m:t></m:r></m:den></m:f></m:oMath></w:p>''')
            self.assertIn(r'$\frac{1}{2}$', read_docx(path))
            output = hw.convert_file(path, outdir=directory, jitter=0, glyph_variation=0)
            self.assertEqual(len(output), 1)
            self.assertTrue(pathlib.Path(output[0]).exists())

    def test_images_warn_and_deleted_text_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.document(directory, '''<w:p><w:r><w:t>保留</w:t><w:drawing/></w:r>
              <w:del><w:r><w:delText>删除内容</w:delText></w:r></w:del></w:p>''')
            with warnings.catch_warnings(record=True) as notices:
                warnings.simplefilter('always')
                self.assertEqual(read_docx(path), '保留')
            self.assertTrue(any('图片' in str(n.message) for n in notices))

    def test_inherited_heading_and_radical_superscript(self):
        with tempfile.TemporaryDirectory() as directory:
            styles = f'''<w:styles xmlns:w="{NS['w']}">
              <w:style w:styleId="Base"><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>
              <w:style w:styleId="Custom"><w:basedOn w:val="Base"/></w:style></w:styles>'''
            path = self.document(directory, '''<w:p><w:pPr><w:pStyle w:val="Custom"/></w:pPr>
              <w:r><w:t>继承标题</w:t></w:r></w:p><w:p><m:oMath><m:rad>
              <m:e><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e>
              <m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:e>
              </m:rad></m:oMath></w:p>''', styles)
            self.assertEqual(read_docx(path), '## 继承标题\n\n$\\sqrt{{x}^{2}}$')

    def test_invalid_and_legacy_files_have_actionable_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'broken.docx'
            path.write_text('broken')
            with self.assertRaisesRegex(ValueError, '有效'):
                read_docx(path)
            with self.assertRaisesRegex(ValueError, '另存为'):
                hw.convert_file(path.with_suffix('.doc'))


if __name__ == '__main__':
    unittest.main()
