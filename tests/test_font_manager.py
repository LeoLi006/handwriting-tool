import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import font_manager as fonts
import handwriting as hw


class FontManagerTests(unittest.TestCase):
    def test_atomic_verified_install_and_failed_hash_preserves_file(self):
        data = b'test-font-data'
        item = dict(filename='test.ttf', download_url='https://example.test/font',
                    license_url='https://example.test/license', size=len(data),
                    sha256=hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            def response(request, **kwargs):
                return io.BytesIO(b'SIL OPEN FONT LICENSE' if request.full_url.endswith('license') else data)
            with patch.object(fonts, 'catalog', return_value={'test': item}), patch.object(fonts, 'urlopen', response):
                path = fonts.install_font('test', cache=directory)
                self.assertEqual(path.read_bytes(), data)
                item['sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    fonts.install_font('test', cache=directory)
                self.assertEqual(path.read_bytes(), data)

    def test_cancelled_download_does_not_install(self):
        item = dict(filename='test.ttf', download_url='https://example.test/font')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(fonts, 'catalog', return_value={'test': item}), patch.object(fonts, 'urlopen', return_value=io.BytesIO(b'font')):
                with self.assertRaises(hw.ConversionCancelled):
                    fonts.install_font('test', cancel=lambda: True, cache=directory)
            self.assertFalse((Path(directory) / 'test.ttf').exists())
