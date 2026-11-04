"""Strict JSON coordinates drawn with Pillow. No eval, scripts or network I/O."""
import json
import math
from PIL import Image, ImageDraw, ImageFont


def plot_image(text, font_path, size, width, height=None, cancel_check=None):
    data = json.loads(text)
    if not isinstance(data, dict) or set(data)-{'xlim','ylim','axes','points','lines','labels'}:
        raise ValueError('仅接受 xlim、ylim、axes、points、lines、labels 字段')

    def number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value)>1e9:
            raise ValueError('坐标必须是有限数字，绝对值不能超过 1e9')
        return value

    def pair(value):
        if not isinstance(value, list) or len(value)!=2:
            raise ValueError('坐标/范围必须是两个数字的数组')
        return tuple(number(v) for v in value)

    xmin, xmax = pair(data.get('xlim', [-4,4])); ymin, ymax = pair(data.get('ylim', [-3,3]))
    if xmax<=xmin or ymax<=ymin:
        raise ValueError('坐标上限必须大于下限')
    if not isinstance(data.get('axes', True), bool):
        raise ValueError('axes 必须是布尔值')
    width = int(width); height = int(height or width*.65)
    margin = max(36, round(size*1.6)); ink = (28,30,66,255)
    unit = min((width-2*margin)/(xmax-xmin), (height-2*margin)/(ymax-ymin))
    left = (width-(xmax-xmin)*unit)/2
    top = (height-(ymax-ymin)*unit)/2
    image = Image.new('RGBA', (width,height), 'white'); draw=ImageDraw.Draw(image)
    font=ImageFont.truetype(font_path, max(12, round(size*.7)))
    def point(value):
        x,y=pair(value)
        if not xmin<=x<=xmax or not ymin<=y<=ymax:
            raise ValueError(f'坐标 {(x,y)} 超出坐标范围；请扩大 xlim/ylim')
        return (left+(x-xmin)*unit, top+(ymax-y)*unit)
    def segment(a,b,style):
        if style not in {'solid','dashed','dotted'}:
            raise ValueError('线型必须为 solid、dashed 或 dotted')
        length=math.dist(a,b); period=max(10,size*.65)
        if style=='solid':
            draw.line((*a,*b), fill=ink,width=2); return
        dash=period*(.58 if style=='dashed' else .12)
        for i in range(math.ceil(length/period)):
            start=i*period/max(length,1); end=min(1,(i*period+dash)/max(length,1))
            draw.line((a[0]+(b[0]-a[0])*start,a[1]+(b[1]-a[1])*start,
                       a[0]+(b[0]-a[0])*end,a[1]+(b[1]-a[1])*end),fill=ink,width=2)
    if data.get('axes',True):
        if ymin<=0<=ymax:
            a,b=point([xmin,0]),point([xmax,0]); segment(a,b,'solid')
            draw.line((b[0]-9,b[1]-5,*b,b[0]-9,b[1]+5),fill=ink,width=2)
        if xmin<=0<=xmax:
            a,b=point([0,ymin]),point([0,ymax]); segment(a,b,'solid')
            draw.line((b[0]-5,b[1]+9,*b,b[0]+5,b[1]+9),fill=ink,width=2)
    for category, allowed in [('lines',{'from','to','style'}),('points',{'x','y','kind','label'}),('labels',{'x','y','text'})]:
        items=data.get(category,[])
        if not isinstance(items,list) or len(items)>500:
            raise ValueError(f'{category} 必须是数组，最多 500 项')
        for item in items:
            if cancel_check: cancel_check()
            if not isinstance(item,dict) or set(item)-allowed:
                raise ValueError(f'{category} 含未知字段')
            if category=='lines':
                segment(point(item['from']),point(item['to']),item.get('style','solid')); continue
            x,y=point([item['x'],item['y']]); r=max(4,size*.17)
            if category=='points':
                kind=item.get('kind','star')
                if kind=='zero': draw.ellipse((x-r,y-r,x+r,y+r),outline=ink,width=2)
                elif kind=='pole':
                    draw.line((x-r,y-r,x+r,y+r),fill=ink,width=2)
                    draw.line((x-r,y+r,x+r,y-r),fill=ink,width=2)
                elif kind=='star': draw.ellipse((x-r,y-r,x+r,y+r),fill=ink)
                else: raise ValueError('点类型必须为 zero、pole 或 star')
            label=item.get('label','') if category=='points' else item.get('text','')
            if not isinstance(label,str) or len(label)>80:
                raise ValueError('标签必须为不超过 80 字的字符串')
            if label:
                pos=(x+r+3,y-r-font.size)
                bbox=draw.textbbox(pos,label,font=font)
                if bbox[2]>=width or bbox[1]<0 or bbox[3]>=height:
                    raise ValueError('标签超出图像，请缩短标签或调整坐标')
                draw.text(pos,label,font=font,fill=ink)
    return image
