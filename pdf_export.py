"""Incremental Pillow PDF export; keep at most one decoded page in memory."""
from pathlib import Path
import os
import tempfile

from PIL import Image


def write_pdf(pages, destination, dpi=150, cancel=None, progress=None):
    from handwriting import ConversionCancelled
    if not pages:
        raise ValueError('没有可导出的页面')
    destination = Path(destination)
    handle, name = tempfile.mkstemp(prefix='.pdf-', suffix='.pdf', dir=destination.parent)
    os.close(handle)
    staging = Path(name)
    try:
        for index, path in enumerate(pages):
            if cancel and cancel():
                raise ConversionCancelled('已取消 PDF 导出')
            with Image.open(path) as source:
                with source.convert('RGB') as image:
                    image.save(staging, format='PDF', resolution=dpi, append=index > 0,
                               title=destination.stem, creator='Mojian / Pillow', quality=95)
            if progress:
                progress(index + 1)
        if cancel and cancel():
            raise ConversionCancelled('已取消 PDF 导出')
        os.replace(staging, destination)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    return destination
