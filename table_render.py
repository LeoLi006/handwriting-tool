"""Handwritten table cells, formula baselines, page splits and repeated headers."""
from PIL import Image
import re
import warnings
from readable_layout import text_tokens


def column_widths(renderer, rows, size, pad):
    """Allocate intrinsic minimums, then distribute remaining width by demand."""
    count=len(rows[0]); available=renderer.w-renderer.left-renderer.right
    minimum=[size+2*pad]*count; preferred=minimum.copy()
    measured_math=[0]
    old=renderer.size; renderer.size=size
    try:
        for row_index,row in enumerate(rows):
            renderer.check_cancel()
            for col,text in enumerate(row):
                natural=0; longest=size
                position=0
                pieces=[]
                for match in re.finditer(r'(?<!\\)\$(.+?)(?<!\\)\$',text):
                    pieces.append(('text',text[position:match.start()]))
                    pieces.append(('math',match[1]));position=match.end()
                pieces.append(('text',text[position:]))
                for kind,value in pieces:
                    if kind=='math':
                        # Width planning never consumes handwriting randomness.
                        # Bound expensive formula measurement; remaining cells
                        # use an estimate and retain exact layout at paint time.
                        formula_width=renderer._adv(re.sub(r'\\[A-Za-z]+','x',value),size)
                        if measured_math[0]<16:
                            measured_math[0]+=1
                            try:
                                import formula
                                with warnings.catch_warnings(record=True):
                                    formula_width=formula.render_formula(value,renderer.ffont,size,renderer.dpi).width
                            except Exception: pass
                        natural+=formula_width;longest=max(longest,formula_width)
                    else:
                        natural+=renderer._adv(value,size)
                        longest=max(longest,max((renderer._adv(t,size) for t in text_tokens(value)),default=0))
                if row_index==0:longest=max(longest,natural)
                minimum[col]=max(minimum[col],min(available*.38,longest+2*pad))
                preferred[col]=max(preferred[col],min(available*.7,natural+2*pad))
    finally: renderer.size=old
    if sum(minimum)>=available:
        widths=[max(1,int(x*available/sum(minimum))) for x in minimum]
    else:
        demand=[max(1,p-m) for p,m in zip(preferred,minimum)]
        extra=available-sum(minimum)
        widths=[int(m+extra*d/sum(demand)) for m,d in zip(minimum,demand)]
    widths[-1]+=available-sum(widths)
    return widths


def _cell_lines(renderer, text, width, size):
    font = renderer._font(size)
    ascent, descent = font.getmetrics()
    lines, parts, x = [], [], 0
    above, below = ascent, descent

    def finish():
        nonlocal parts, x, above, below
        lines.append(dict(parts=parts, above=above, height=above+below+max(3, round(size*.14))))
        parts, x, above, below = [], 0, ascent, descent

    original_size = renderer.size
    renderer.size = size
    try:
        for kind, value in renderer._inline_items(text.replace('<br>', '\n').replace('**', '').replace('`', '')):
            renderer.check_cancel()
            if kind == 'math':
                scale = min(1, width/max(1, value.width), (renderer.h-renderer.top-renderer.bottom)*.5/max(1, value.height))
                if scale < 1:
                    renderer.issue('警告', '表格公式', f'{renderer.location}：公式已等比缩放至 {scale:.0%}，请检查可读性')
                    from formula import Formula
                    value = Formula(value.image.resize((max(1, round(value.width*scale)), max(1, round(value.height*scale))), Image.Resampling.LANCZOS),
                                    round(value.depth*scale), value.source)
                if x and x + value.width > width:
                    finish()
                parts.append(('math', value, x))
                x += value.width + size*.12
                above, below = max(above, value.above), max(below, value.depth)
            else:
                for token in text_tokens(value):
                    if token == '\n':
                        finish(); continue
                    fragments=list(token) if renderer._adv(token,size)>width else [token]
                    for fragment in fragments:
                        advance=renderer._adv(fragment,size)
                        if x and x+advance>width: finish()
                        for char in fragment:
                            parts.append(('text',char,x)); x+=renderer._adv(char,size)
        if parts or not lines:
            finish()
    finally:
        renderer.size = original_size
    return lines


def draw_table(renderer, rows):
    if not rows or not rows[0]:
        return
    size = max(18, round(renderer.size*.8))
    pad = max(7, round(size*.3))
    columns = len(rows[0])
    width = renderer.w - renderer.left - renderer.right
    widths = column_widths(renderer, rows, size, pad)
    origin = renderer.location
    source_line = renderer.source_line
    def fields(body_rows,start=2):
        for row_index,row in enumerate(body_rows,start):
            renderer.source_line=source_line+row_index
            renderer._draw_flow([('text',f'表格第 {row_index-1} 条')],size)
            for header,value in zip(rows[0],row):
                renderer._draw_flow(renderer._inline_items(f'{header}：{value}'),size,indent=size)
        renderer.source_line=source_line
    if min(widths)-2*pad < size*1.5:
        renderer.issue('警告', '表格密度', f'{columns} 列导致单元格过窄，已逐字换行；建议拆分表格或减少列数')
    if min(widths)-2*pad < size:
        renderer.issue('替代', '超宽表格', '列宽不足以容纳一个中文字符，已采用逐行字段显示，保留所有单元格')
        if len(rows)==1:renderer._draw_flow(renderer._inline_items(' / '.join(rows[0])),size)
        fields(rows[1:])
        return

    def plan(row, row_index):
        result = []
        for column, (text, cell_width) in enumerate(zip(row, widths), 1):
            renderer.location = f'{origin}/表格第 {row_index} 行第 {column} 列'
            renderer.source_line = source_line + (row_index if row_index > 1 else 0)
            result.append(_cell_lines(renderer, text, max(1, cell_width-2*pad), size))
        renderer.location = origin
        renderer.source_line = source_line
        return result

    def height(cells):
        return max(sum(line['height'] for line in cell) for cell in cells) + 2*pad

    def paint(cells, offsets, ends, header=False):
        used = [sum(line['height'] for line in cell[start:end]) for cell, start, end in zip(cells, offsets, ends)]
        row_height = max(used) + 2*pad
        top = renderer.y
        renderer.record_region('表格行', (renderer.left,top,renderer.w-renderer.right,top+row_height))
        renderer.draw.rectangle((renderer.left, top, renderer.w-renderer.right, top+row_height), fill=(255,255,255))
        x = renderer.left
        for cell, start, end, cell_width in zip(cells, offsets, ends, widths):
            y = top+pad
            for line in cell[start:end]:
                baseline = y+line['above']
                for kind, value, dx in line['parts']:
                    if kind == 'math':
                        renderer.page.paste(value.image, (round(x+pad+dx), round(baseline-value.above)), value.image)
                    else:
                        renderer._draw_char(value, x+pad+dx, baseline, size)
                y += line['height']
            renderer.draw.line((x, top, x, top+row_height), fill=(28,30,66), width=1)
            x += cell_width
        renderer.draw.line((x, top, x, top+row_height), fill=(28,30,66), width=1)
        for y in (top, top+row_height):
            renderer.draw.line((renderer.left, y, x, y), fill=(28,30,66), width=2 if header else 1)
        renderer.y += row_height

    header = plan(rows[0], 1)
    header_height = height(header)
    body_height = renderer.h-renderer.top-renderer.bottom
    if header_height > body_height*.6:
        renderer.issue('替代','过长表头','表头过长，已采用逐行字段显示，保留全部表头与单元格文字')
        if len(rows)==1:renderer._draw_flow(renderer._inline_items(' / '.join(rows[0])),size)
        fields(rows[1:]);return

    def paint_header():
        paint(header, [0]*columns, [len(cell) for cell in header], True)

    renderer._ensure(header_height + size*2)
    paint_header()
    for row_index, row in enumerate(rows[1:], 2):
        cells = plan(row, row_index)
        offsets = [0]*columns
        while any(start < len(cell) for start, cell in zip(offsets, cells)):
            renderer.check_cancel()
            room = renderer.h-renderer.bottom-renderer.y-2*pad
            minimum = max((cell[start]['height'] for start, cell in zip(offsets, cells) if start<len(cell)), default=0)
            if room < minimum:
                renderer._new_page()
                paint_header()
                room = renderer.h-renderer.bottom-renderer.y-2*pad
            ends = []
            for start, cell in zip(offsets, cells):
                end, used = start, 0
                while end < len(cell) and used + cell[end]['height'] <= room:
                    used += cell[end]['height']; end += 1
                ends.append(end)
            if ends == offsets:
                renderer.issue('替代','过高单元格','单元格与重复表头无法同时容纳，剩余行已采用逐行字段显示')
                # No part of this row has been painted if there was no progress.
                if not any(offsets):fields(rows[row_index-1:],row_index)
                else:
                    # A split row: preserve just its remaining planned lines.
                    for column,(cell,start) in enumerate(zip(cells,offsets),1):
                        renderer._draw_flow([('text',f'续行/第 {column} 列')],size)
                        for line in cell[start:]:
                            renderer._draw_flow([(kind,value) for kind,value,_ in line['parts']],size)
                    fields(rows[row_index:],row_index+1)
                return
            paint(cells, offsets, ends)
            offsets = ends
    renderer.location = origin
    renderer.y += round(renderer.line_spacing*.4)
