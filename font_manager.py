"""On-demand official font downloads with hashes, atomic installation and cancellation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen
import zipfile

HERE = Path(__file__).resolve().parent


def catalog():
    return json.loads((HERE / 'fonts' / 'catalog.json').read_text(encoding='utf-8'))


def cache_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / '.cache')) / 'Mojian' / 'fonts'


def font_path(key, cache=None):
    info = catalog()[key]
    bundled = HERE / 'fonts' / info['filename']
    if bundled.is_file():
        return bundled
    return Path(cache or cache_directory()) / info['filename']


def installed(key, cache=None):
    return font_path(key, cache).is_file()


def install_font(key, cancel=lambda: False, progress=lambda n: None, cache=None):
    info = catalog()[key]
    destination = Path(cache or cache_directory())
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / info['filename']
    from handwriting import ConversionCancelled
    with tempfile.TemporaryDirectory(prefix='.font-', dir=destination) as temp:
        download = Path(temp) / 'download'
        request = Request(info['download_url'], headers={'User-Agent': 'Mojian-Handwriting/1.0'})
        with urlopen(request, timeout=30) as response, download.open('wb') as stream:
            total = 0
            while True:
                if cancel():
                    raise ConversionCancelled('已取消字体下载')
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    raise ValueError('字体下载大小异常')
                stream.write(chunk); progress(total)
        font = download
        if info.get('archive_member'):
            font = Path(temp) / 'font.ttf'
            with zipfile.ZipFile(download) as archive:
                member = archive.getinfo(info['archive_member'])
                if member.file_size != info['size']:
                    raise ValueError('字体压缩包大小校验失败')
                font.write_bytes(archive.read(member))
        if font.stat().st_size != info['size'] or hashlib.sha256(font.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError('字体 SHA-256 校验失败，请重试')
        license_request = Request(info['license_url'], headers={'User-Agent': 'Mojian-Handwriting/1.0'})
        with urlopen(license_request, timeout=30) as response:
            license_data = response.read(256 * 1024)
        if b'SIL OPEN FONT LICENSE' not in license_data:
            raise ValueError('未能读取有效的字体授权文件')
        if cancel():
            raise ConversionCancelled('已取消字体下载')
        license_temp = Path(temp) / 'OFL.txt'; license_temp.write_bytes(license_data)
        os.replace(license_temp, destination / (key + '-OFL.txt'))
        os.replace(font, target)
    return target
