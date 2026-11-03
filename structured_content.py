"""Markdown grid parsing and faithful, display-column based text diagrams."""
import re
import math
import unicodedata
import warnings

from PIL import Image, ImageDraw, ImageFont


def split_table_row(line):
    cells, current, math_mode, code, index = [], [], False, False, 0
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|') and not line.endswith(r'\|'):
        line = line[:-1]
    while index < len(line):
        char = line[index]
        if char == '\\' and index + 1 < len(line):
            current.append(line[index:index + 2]); index += 2; continue
        if char == '$' and not code:
            math_mode = not math_mode
        if char == '`' and not math_mode:
            code = not code
        if char == '|' and not math_mode and not code:
            cells.append(''.join(current).strip()); current = []
        else:
            current.append(char)
        index += 1
    cells.append(''.join(current).strip())
    return [cell.replace(r'\|', '|') for cell in cells]


def table_separator(line):
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell.strip()) for cell in cells)


def display_width(char):
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in {'W', 'F'} else 1


def diagram_image(text, font_path, size, max_width, language='text', max_height=None, cancel_check=None):
    """Redraw line glyphs at their original cells, never infer new point positions."""
    lines = text.expandtabs(4).splitlines() or ['']
    columns = max(sum(display_width(c) for c in line) for line in lines)
    cell = max(8, size * .53)
    line_height = size * 1.22
    pad = size * .55
    width, height = round(columns * cell + 2 * pad), round(len(lines) * line_height + 2 * pad)
    max_height = max_height or max_width*2
    factor = min(1, max_width*2/max(1, width), max_height*2/max(1, height))
    if factor < 1:
        cell *= factor; line_height *= factor; pad *= factor
        size = max(1, round(size*factor))
        width, height = max(1, round(width*factor)), max(1, round(height*factor))
    # Render at readable resolution, then fit without changing the aspect ratio.
    image = Image.new('RGBA', (max(1, width), max(1, height)))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, size)
    ink = (28, 30, 66, 255)
    stroke = max(2, round(size / 20))
    line_glyphs = set('─━│┃┼┬┴├┤┌┐└┘┏┓┗┛┯┷┿╋┆┊┄┈┅┉┇┋╌╍╎╏↑↓←→↔↕')
    schematic = language.lower() in {'diagram', 'ascii', 'polezero', 'constellation'} or sum(c in line_glyphs for c in text) >= 3
    # Use one phase for each canvas direction, including junction arms.
    # Resetting the phase for every glyph can accidentally fill all dash gaps.
    horizontal_glyphs = '─━┄┈┅┉╌╍'
    vertical_glyphs = '│┃┆┊┇┋╎╏'
    dashed_glyphs = '┄┈┅┉╌╍┆┊┇┋╎╏'
    grid = {}
    for row_index, source_line in enumerate(lines):
        col = 0
        for glyph in source_line:
            grid[row_index, col] = glyph
            col += display_width(glyph)

    def dashed_neighbor(row_index, col, direction):
        dr, dc = {'l': (0, -1), 'r': (0, 1), 'u': (-1, 0), 'd': (1, 0)}[direction]
        glyph = grid.get((row_index+dr, col+dc), '')
        return bool(glyph and glyph in dashed_glyphs)

    def segment(start, end, dashed=False):
        if not dashed:
            draw.line((*start, *end), fill=ink, width=stroke)
            return
        vertical_line = start[0] == end[0]
        a, b = sorted((start[1], end[1]) if vertical_line else (start[0], end[0]))
        period = max(stroke*4, line_height*.8 if vertical_line else cell*1.8)
        dash = period*.58
        for index in range(math.floor(a/period), math.floor(b/period)+1):
            lo, hi = max(a, index*period), min(b, index*period+dash)
            if hi > lo:
                points = (start[0], lo, start[0], hi) if vertical_line else (lo, start[1], hi, start[1])
                draw.line(points, fill=ink, width=stroke)

    strokes = []
    origins = []
    for row, line in enumerate(lines):
        if cancel_check:
            cancel_check()
        column = 0
        for index, char in enumerate(line):
            if cancel_check and index % 128 == 0:
                cancel_check()
            span = display_width(char)
            x, y = pad + (column + .5) * cell, pad + (row + .5) * line_height
            column += span
            if char.isspace():
                continue
            before, after = line[max(0, index - 1):index], line[index + 1:index + 2]
            if char in 'O0' and (before in '─━' and before or after in '─━' and after):
                origins.append((x, y))
            horizontal = char in horizontal_glyphs or (char in '-_' and schematic and (before in '-_─' and before or after in '-_─' and after))
            vertical = char in vertical_glyphs or char == '|' and schematic
            if horizontal:
                segment((x-cell/2, y), (x+cell/2, y), char in dashed_glyphs)
            elif vertical:
                segment((x, y-line_height/2), (x, y+line_height/2), char in dashed_glyphs)
            elif schematic and char in '┼┬┴├┤┌┐└┘┏┓┗┛┯┷┿╋+':
                directions = {'┌': 'rd', '┏': 'rd', '┐': 'ld', '┓': 'ld', '└': 'ru', '┗': 'ru',
                              '┘': 'lu', '┛': 'lu', '┬': 'lrd', '┴': 'lru', '├': 'rud', '┤': 'lud'}.get(char, 'lrud')
                for direction, end in [('l', (x-cell/2, y)), ('r', (x+cell/2, y)),
                                       ('u', (x, y-line_height/2)), ('d', (x, y+line_height/2))]:
                    if direction in directions:
                        segment((x, y), end, dashed_neighbor(row, column-span, direction))
            elif schematic and char in '↑↓←→↔↕':
                if char in '↑↓↕':
                    draw.line((x, y-line_height/2, x, y+line_height/2), fill=ink, width=stroke)
                    for sign in (-1, 1):
                        if char == '↕' or char == ('↑' if sign == -1 else '↓'):
                            tip = y + sign * line_height * .47
                            draw.line((x-cell*.3, tip-sign*cell*.5, x, tip, x+cell*.3, tip-sign*cell*.5), fill=ink, width=stroke)
                else:
                    draw.line((x-cell/2, y, x+cell/2, y), fill=ink, width=stroke)
                    for sign in (-1, 1):
                        if char == '↔' or char == ('←' if sign == -1 else '→'):
                            tip = x + sign * cell*.48
                            draw.line((tip-sign*cell*.5, y-cell*.3, tip, y, tip-sign*cell*.5, y+cell*.3), fill=ink, width=stroke)
            elif schematic and char in '/\\' and (not before or before.isspace()) and (not after or after.isspace()):
                strokes.append((row, column-span, char, x, y))
            elif schematic and char in '×✕○●•':
                radius = cell*.3
                if char in '×✕':
                    draw.line((x-radius, y-radius, x+radius, y+radius), fill=ink, width=stroke)
                    draw.line((x-radius, y+radius, x+radius, y-radius), fill=ink, width=stroke)
                else:
                    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=ink if char in '●•' else None, outline=ink, width=stroke)
            else:
                # Each label keeps its original East Asian display-column position.
                l, top, right, bottom = font.getbbox(char, anchor='ls')
                glyph = Image.new('RGBA', (max(1, right-l+2), max(1, bottom-top+2)))
                ImageDraw.Draw(glyph).text((1-l, 1-top), char, font=font, fill=ink, anchor='ls')
                available = max(cell * max(1, span), 1)
                if glyph.width > available:
                    glyph = glyph.resize((max(1, round(available)), glyph.height), Image.Resampling.LANCZOS)
                image.alpha_composite(glyph, (round(x-cell/2+(available-glyph.width)/2), round(y+size*.32+top-1)))
    # Join the explicitly drawn diagonal samples on consecutive rows.
    used = set()
    for start in strokes:
        if start in used:
            continue
        chain = [start]; used.add(start)
        while True:
            row, column, char, x, y = chain[-1]
            candidates = [s for s in strokes if s not in used and s[0] == row+1 and s[2] == char and abs(s[1]-column) <= 4]
            if not candidates:
                break
            target = min(candidates, key=lambda s: abs(s[1]-column))
            chain.append(target); used.add(target)
        if len(chain) == 1:
            row, column, char, x, y = start
            sign = -1 if char == '/' else 1
            points = [(x-cell/2, y-sign*line_height/2), (x+cell/2, y+sign*line_height/2)]
        else:
            points = [(s[3], s[4]) for s in chain]
            first, second, before_last, last = points[0], points[1], points[-2], points[-1]
            points.insert(0, (first[0]-(second[0]-first[0])*.4, first[1]-(second[1]-first[1])*.4))
            points.append((last[0]+(last[0]-before_last[0])*.4, last[1]+(last[1]-before_last[1])*.4))
            # An explicit O/0 on an axis is the named origin of an ASCII ray.
            # Connect to that existing point rather than leaving the text's gaps.
            for origin in origins:
                near = min((points[0], points[-1]), key=lambda p: abs(p[0]-origin[0])+abs(p[1]-origin[1]))
                if abs(near[1]-origin[1]) <= 2.1*line_height and abs(near[0]-origin[0]) <= 12*cell:
                    far = max((points[0], points[-1]), key=lambda p: abs(p[0]-origin[0])+abs(p[1]-origin[1]))
                    points = [origin, far]
                    break
        draw.line(points, fill=ink, width=stroke)
    fit = min(1, max_width/image.width, max_height/image.height)
    if fit*factor < .4:
        warnings.warn('字符图尺寸过大，已整体缩小；建议拆分后检查标签可读性。', UserWarning)
    if fit < 1:
        image = image.resize((max(1, round(image.width*fit)), max(1, round(image.height*fit))), Image.Resampling.LANCZOS)
    return image
