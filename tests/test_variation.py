"""Verify glyph changes and layout randomness are independent."""
import unittest

import handwriting as hw


class VariationTests(unittest.TestCase):
    def render(self, jitter, glyph_variation):
        pages, renderer = hw.render_markdown(
            '的的的的的，学习数学。' * 8, seed=123,
            jitter=jitter, glyph_variation=glyph_variation)
        return pages[0].tobytes(), renderer

    def test_shape_does_not_consume_layout_randomness(self):
        plain, a = self.render(1, 0)
        varied, b = self.render(1, 1.5)
        self.assertNotEqual(plain, varied)
        self.assertEqual(a.rand.getstate(), b.rand.getstate())
        self.assertEqual(a.y, b.y)
        self.assertEqual(a._writing_slant, b._writing_slant)
        self.assertEqual(a._writing_scale, b._writing_scale)

    def test_shapes_work_with_layout_randomness_disabled(self):
        plain, _ = self.render(0, 0)
        varied, a = self.render(0, 1.5)
        repeat, _ = self.render(0, 1.5)
        self.assertNotEqual(plain, varied)
        self.assertEqual(varied, repeat)
        self.assertEqual(a._writing_slant, 0)
        self.assertEqual(a._writing_scale, 0)

    def test_layout_does_not_consume_shape_randomness(self):
        plain, a = self.render(0, 1)
        moved, b = self.render(1, 1)
        self.assertNotEqual(plain, moved)
        self.assertEqual(a.shape_rand.getstate(), b.shape_rand.getstate())


if __name__ == '__main__':
    unittest.main()
