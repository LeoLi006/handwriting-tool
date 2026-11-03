"""Handwritten table cells, formula baselines, page splits and repeated headers."""
from PIL import Image


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
                    from formula import Formula
                    value = Formula(value.image.resize((max(1, round(value.width*scale)), max(1, round(value.height*scale))), Image.Resampling.LANCZOS),
                                    round(value.depth*scale), value.source)
                if x and x + value.width > width:
                    finish()
                parts.append(('math', value, x))
                x += value.width + size*.12
                above, below = max(above, value.above), max(below, value.depth)
            else:
                for char in value:
                    if char == '\n':
                        finish(); continue
                    advance = renderer._adv(char, size)
                    if x and x + advance > width:
                        finish()
                    parts.append(('text', char, x)); x += advance
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
    widths = [width//columns]*columns
    widths[-1] += width-sum(widths)
    origin = renderer.location

    def plan(row, row_index):
        result = []
        for column, (text, cell_width) in enumerate(zip(row, widths), 1):
            renderer.location = f'{origin}/表格第 {row_index} 行第 {column} 列'
            result.append(_cell_lines(renderer, text, max(1, cell_width-2*pad), size))
        renderer.location = origin
        return result

    def height(cells):
        return max(sum(line['height'] for line in cell) for cell in cells) + 2*pad

    def paint(cells, offsets, ends, header=False):
        used = [sum(line['height'] for line in cell[start:end]) for cell, start, end in zip(cells, offsets, ends)]
        row_height = max(used) + 2*pad
        top = renderer.y
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
        raise ValueError('表头过长，无法在一页内显示，请缩短表头或拆分表格。')

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
                raise ValueError('表格单元格内容过高，请减小字号或拆分公式。')
            paint(cells, offsets, ends)
            offsets = ends
    renderer.location = origin
    renderer.y += round(renderer.line_spacing*.4)
