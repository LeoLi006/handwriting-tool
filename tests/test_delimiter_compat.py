import unittest

import formula


class DelimiterCompatibilityTests(unittest.TestCase):
    def test_fixed_size_variants_preserve_delimiters(self):
        for size in ('big', 'Big', 'bigg', 'Bigg'):
            for side in ('l', 'r', 'm'):
                with self.subTest(size=size, side=side):
                    self.assertEqual(formula.normalize('\\' + size + side + '['), '[')
        # A fixed-size delimiter need not have a matching opposite command.
        self.assertGreater(formula.render_formula(r'\Bigl|_{u=0}').width, 0)

    def test_original_aligned_and_cases_shapes(self):
        # Original regression data, independent of user homework.
        samples = [
            r'\begin{aligned}Q&=\frac12\int_0^1\bigl[\sin(t)+\cos(t)\bigr]\,\mathrm dt\\'
            r'&=\left[\frac{\sin(t)}{2}-\frac{\cos(t)}{2}\right]_0^1.\end{aligned}',
            r'P(u)=\begin{cases}2,&|u|\le1,\\'
            r'\dfrac{2}{3}\bigl[1+\cos\bigl(2(|u|-1)\bigr)\bigr],&1<|u|\le3,\\'
            r'0,&|u|>3.\end{cases}',
        ]
        for source in samples:
            with self.subTest(source=source):
                result = formula.render_formula(source)
                self.assertGreater(result.height, 60)
                self.assertIsNotNone(result.image.getbbox())

    def test_environment_error_exposes_underlying_command(self):
        with self.assertRaisesRegex(ValueError, r'Unknown symbol.*\\doesnotexist'):
            formula.render_formula(r'\begin{cases}\doesnotexist{x}&x>0\end{cases}')
