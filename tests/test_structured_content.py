import unittest
from unittest.mock import patch

import formula
import handwriting as hw
from structured_content import split_table_row, diagram_image


class StructuredContentTests(unittest.TestCase):
    def test_markdown_keeps_table_math_and_diagram(self):
        source = '| 项目 | 数值 |\n|---|---|\n| A | $|x|$ |\n\n```text\n  ↑\n──┼──→ x\n  │\n```'
        blocks = hw.markdown_to_blocks(source)
        self.assertEqual(blocks[0], ('table', [['项目', '数值'], ['A', '$|x|$']]))
        self.assertEqual(blocks[1][0], 'diagram')
        self.assertIn('──┼──→', blocks[1][1])
        self.assertEqual(split_table_row(r'| a\|b | $|x|$ |'), ['a|b', '$|x|$'])

    def test_multi_page_table_does_not_drop_or_repeat_body_rows(self):
        text = '| 条目 | 说明 |\n|---|---|\n' + '\n'.join(f'| {i:03d} | 内容文字 |' for i in range(80))
        digits = []
        original = hw.Renderer._draw_char
        def draw(renderer, char, *args):
            if char.isdigit():
                digits.append(char)
            return original(renderer, char, *args)
        with patch.object(hw.Renderer, '_draw_char', draw):
            pages, _ = hw.render_markdown(text, jitter=0, glyph_variation=0)
        self.assertGreater(len(pages), 1)
        self.assertEqual(''.join(digits), ''.join(f'{i:03d}' for i in range(80)))

    def test_boxed_answers_in_aligned_and_with_nested_braces(self):
        inner = formula.render_formula(r'\frac{1}{2}')
        framed = formula.render_formula(r'\boxed{\frac{1}{2}}')
        self.assertGreater(framed.width, inner.width)
        self.assertGreater(framed.depth, inner.depth)
        for expression in [r'\boxed{a},\qquad\boxed{b}',
                           r'\begin{aligned}a&=1\\&=\boxed{\sqrt{1}}\end{aligned}',
                           r'\boxed{S=\left\{1,2\right\}}', r'a\overset d=b',
                           r'\boxed{a}\quad\text{按模 $2\pi$ 理解}']:
            self.assertGreater(formula.render_formula(expression).width, 0)

    def test_diagram_preserves_canvas_geometry_and_fits_width(self):
        source = '     ↑ Im\n ○   │   ×\n─────┼──────→ Re\n     │'
        image = diagram_image(source, hw.FALLBACK, 32, 500, 'polezero')
        self.assertLessEqual(image.width, 500)
        self.assertIsNotNone(image.getbbox())
        pages, _ = hw.render_markdown('```polezero\n'+source+'\n```', jitter=0)
        self.assertEqual(len(pages), 1)

    def test_tall_boxed_formula_reserves_its_full_height(self):
        latex = r'\boxed{\frac{\frac{1}{2}}{\frac{3}{4}}}'
        image = formula.render_formula(latex)
        for text in ('$$'+latex+'$$', '结果为 $'+latex+'$。'):
            _, renderer = hw.render_markdown(text, jitter=0, glyph_variation=0)
            self.assertGreaterEqual(renderer.y-renderer.top, image.height)
