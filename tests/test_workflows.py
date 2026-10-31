import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import handwriting as hw
from app_settings import PRESETS, load_settings, save_settings
from batch_tasks import run_batch
from managed_output import document_directory, generate_document


class WorkflowTests(unittest.TestCase):
    def test_settings_recover_and_presets_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            save_settings(dict(PRESETS['工整笔记'], outdir='目录'), path)
            self.assertEqual(load_settings(path)['outdir'], '目录')
            path.write_text('bad')
            self.assertEqual(load_settings(path), {})

    def test_preview_stops_before_later_content(self):
        count = 0
        draw = hw.Renderer._draw_char
        def counted(renderer, *args):
            nonlocal count
            count += 1
            return draw(renderer, *args)
        with patch.object(hw.Renderer, '_draw_char', counted):
            pages, _ = hw.render_markdown('的' * 10000, page_limit=1, jitter=0, glyph_variation=0)
        self.assertEqual(len(pages), 1)
        self.assertLess(count, 1200)

    def test_failed_job_does_not_stop_batch(self):
        def convert(path, **params):
            if path == 'bad':
                raise ValueError('bad input')
            return ['ok.png']
        jobs = [dict(id='0', path='bad'), dict(id='1', path='good')]
        result = run_batch(jobs, {}, lambda: False, lambda *args: None, convert)
        self.assertEqual([r['status'] for r in result], ['失败', '完成'])

    def test_cancel_stops_char_drawing(self):
        event = threading.Event()
        draw = hw.Renderer._draw_char
        count = 0
        def counted(renderer, *args):
            nonlocal count
            count += 1
            if count == 10:
                event.set()
            return draw(renderer, *args)
        with patch.object(hw.Renderer, '_draw_char', counted):
            with self.assertRaises(hw.ConversionCancelled):
                hw.render_markdown('的' * 10000, cancel=event.is_set)
        self.assertEqual(count, 10)

    def test_new_generation_removes_only_old_managed_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'notes.md'; source.write_text('的' * 1000, encoding='utf-8')
            output = Path(directory) / 'output'
            old = generate_document(source, outdir=output, jitter=0, glyph_variation=0)
            self.assertGreater(len(old), 1)
            keep = Path(old[0]).parent / 'my-notes.txt'; keep.write_text('keep')
            source.write_text('短文', encoding='utf-8')
            new = generate_document(source, outdir=output, jitter=0, glyph_variation=0)
            self.assertEqual(len(new), 1)
            self.assertTrue(keep.exists())
            self.assertFalse(any(Path(p).exists() for p in old))
            latest = document_directory(source, output) / 'latest.json'
            before = latest.read_bytes()
            with self.assertRaises(hw.ConversionCancelled):
                generate_document(source, outdir=output, cancel=lambda: True)
            self.assertEqual(before, latest.read_bytes())
            self.assertTrue(Path(new[0]).exists())
            other = Path(directory) / 'other' / source.name
            self.assertNotEqual(document_directory(source, output), document_directory(other, output))

    def test_streaming_pages_match_in_memory_render(self):
        text = '学习数学。' * 400
        pages, _ = hw.render_markdown(text, jitter=0, glyph_variation=0)
        recorded = []
        retained, renderer = hw.render_markdown(text, jitter=0, glyph_variation=0,
            page_sink=lambda image, index: recorded.append(image.tobytes()))
        self.assertEqual(recorded, [page.tobytes() for page in pages])
        self.assertEqual(len(retained), 1)
        self.assertEqual(renderer.page_count, len(pages))

    def test_pdf_page_count_and_cancel_preserves_existing_pdf(self):
        from PIL import PdfParser
        from pdf_export import write_pdf
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'notes.md'
            source.write_text('的' * 900, encoding='utf-8')
            paths = generate_document(source, outdir=Path(directory)/'out', export_format='both',
                                      jitter=0, glyph_variation=0)
            pdf = Path(paths[0]).parent / 'document.pdf'
            with PdfParser.PdfParser(filename=str(pdf)) as document:
                self.assertEqual(len(document.pages), len(paths))
            old = pdf.read_bytes()
            with self.assertRaises(hw.ConversionCancelled):
                write_pdf(paths, pdf, cancel=lambda: True)
            self.assertEqual(pdf.read_bytes(), old)


if __name__ == '__main__':
    unittest.main()
