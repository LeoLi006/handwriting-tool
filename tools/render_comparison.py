"""Create a fair pair using the same short sample, seed, page and pixel scale."""
import argparse
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
import handwriting as hw
from comparison import SAMPLE,comparable_params,differences
from preview_cache import PreviewCache


def render(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    before=comparable_params(dict(font='WenKai',font_size=40,jitter=0,glyph_variation=0,formula_variation=0,table_variation=0,diagram_variation=0))
    after=dict(before,jitter=.8,glyph_variation=1.4)
    cache=PreviewCache(output/'cache',capacity=4)
    left,_=cache.get(SAMPLE,before,1);right,_=cache.get(SAMPLE,after,1)
    for entry,name in [(left,'before.png'),(right,'after.png')]:shutil.copyfile(entry['paths'][0],output/name)
    with Image.open(left['paths'][0]) as a,Image.open(right['paths'][0]) as b:
        assert a.size==b.size
        scale=.45;size=(round(a.width*scale),round(a.height*scale))
        page=Image.new('RGB',(size[0]*2+36,size[1]+120),'#e9eeeb')
        draw=ImageDraw.Draw(page);font=ImageFont.truetype(hw.FALLBACK,22)
        draw.text((12,8),'固定短示例 / 种子 20231029 / 共同第 1 页 / 共同缩放 45%',fill='#243c36',font=font)
        draw.text((12,40),'变化：位置随机度 0 → 0.8；正文字形变化 0 → 1.4；公式/表格/图形均为 0',fill='#243c36',font=font)
        for index,image in enumerate((a,b)):
            x=12+index*(size[0]+12)
            draw.text((x,78),'调整前：固定基准' if index==0 else '调整后：当前参数',fill='#243c36',font=font)
            page.paste(image.resize(size,Image.Resampling.LANCZOS),(x,112))
        page.save(output/'comparison.png')
    report=dict(page=1,scale=.45,seed=20231029,content='examples/regression/参数对照.md',differences=differences(before,after))
    (output/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Comparison generated with common content/seed/page/scale')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='output/comparison');args=parser.parse_args();render(args.output)
