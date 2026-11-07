"""Repeatable PNG/PDF/preview verification; visual review remains mandatory."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import warnings
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageChops, ImageStat
from build_regression_sample import build
from managed_output import generate_document
from preview_cache import PreviewCache


def run(output, poppler=None):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    (output/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(output/'tmp')
    source=build()
    params=dict(jitter=.1,glyph_variation=.7,formula_variation=0,table_variation=0,diagram_variation=0)
    with warnings.catch_warnings(record=True):
        warnings.simplefilter('always')
        png=generate_document(source,output/'png',export_format='png',**params)
        pdf=generate_document(source,output/'pdf',export_format='pdf',**params)
        cache=PreviewCache(output/'preview')
        preview,_=cache.get(source,params,1)
        again,cached=cache.get(source,params,1)
    with Image.open(png[0]) as full, Image.open(preview['paths'][0]) as first:
        identical=ImageChops.difference(full,first).getbbox() is None
    if not identical or not cached or len(preview['paths'])!=1:
        raise AssertionError('单页预览与最终第一页不一致，或未复用缓存')
    assert len(list((output/'pdf').iterdir()))==1, 'PDF-only 输出不应创建结果文件夹/额外文件'
    report=dict(source='examples/regression/综合回归.md',pages=len(png),
                png=[Path(path).relative_to(output).as_posix() for path in png],pdf=Path(pdf[0]).relative_to(output).as_posix(),
                preview_matches=identical,preview_cache_hit=cached,issues=png.issues,
                visual_review='待逐页人工检查；自动检查不证明排版正确')
    if poppler:
        rendered=output/'pdf-render';rendered.mkdir(exist_ok=True)
        subprocess.run([str(poppler),'-r','150','-png',pdf[0],str(rendered/'page')],check=True)
        pages=sorted(rendered.glob('page-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
        assert len(pages)==len(png), 'PDF 页数与 PNG 不同'
        errors=[]; normalized_errors=[]
        for path,reference in zip(pages,png):
            with Image.open(path) as page,Image.open(reference) as expected:
                if page.size!=expected.size:
                    if any(abs(a-b)>1 for a,b in zip(page.size,expected.size)):
                        raise AssertionError('PDF 页面尺寸不匹配')
                    page=page.crop((0,0,*expected.size))
                errors.append(sum(ImageStat.Stat(ImageChops.difference(page.convert('RGB'),expected.convert('RGB'))).mean)/3)
                # Poppler antialiases raster-image boundaries while source PNG
                # has hard pixel edges. Compare common 75-DPI area averages too.
                small=(expected.width//2,expected.height//2)
                a=page.convert('RGB').resize(small,Image.Resampling.BOX)
                b=expected.convert('RGB').resize(small,Image.Resampling.BOX)
                normalized_errors.append(sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/3)
        report['pdf_png_mean_errors']=errors
        report['pdf_png_75dpi_mean_errors']=normalized_errors
        assert max(normalized_errors)<5, 'PDF 与 PNG 面积平均后的视觉差异异常'
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key not in {'png','issues'}},ensure_ascii=True,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='output/regression')
    parser.add_argument('--poppler',default=shutil.which('pdftoppm'));args=parser.parse_args()
    run(args.output,args.poppler)
