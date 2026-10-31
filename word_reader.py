"""Extract DOCX content with the Python standard library; no Word installation needed."""
import re
import warnings
import zipfile
from xml.etree import ElementTree as ET

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}


def _tag(node):
    return node.tag.rsplit('}', 1)[-1]


def _math(node):
    """Translate common native Word equations to the existing mathtext input."""
    kind = _tag(node)
    def part(name):
        child = node.find('m:' + name, NS)
        return _math(child) if child is not None else ''
    if kind == 't':
        return node.text or ''
    if kind.endswith('Pr'):
        return ''
    if kind == 'f':
        return r'\frac{' + part('num') + '}{' + part('den') + '}'
    if kind == 'sSup':
        return '{' + part('e') + '}^{' + part('sup') + '}'
    if kind == 'sSub':
        return '{' + part('e') + '}_{' + part('sub') + '}'
    if kind == 'sSubSup':
        return '{' + part('e') + '}_{' + part('sub') + '}^{' + part('sup') + '}'
    if kind == 'rad':
        degree = part('deg')
        return r'\sqrt' + ('[' + degree + ']' if degree else '') + '{' + part('e') + '}'
    if kind == 'nary':
        prop = node.find('m:naryPr/m:chr', NS)
        symbol = prop.get('{' + NS['m'] + '}val', '∫') if prop is not None else '∫'
        operator = {'∑': r'\sum', '∏': r'\prod', '∫': r'\int', '∬': r'\iint',
                    '∭': r'\iiint', '∮': r'\oint', '⋃': r'\bigcup', '⋂': r'\bigcap'}.get(symbol)
        if operator is None:
            warnings.warn(f'不支持的求和/积分运算符 {symbol!r}，已保留文字。', UserWarning)
            operator = symbol
        for name, mark in [('sub', '_'), ('sup', '^')]:
            hidden = node.find('m:naryPr/m:' + name + 'Hide', NS)
            is_hidden = hidden is not None and hidden.get('{' + NS['m'] + '}val', '1') not in {'0', 'false', 'off'}
            if not is_hidden and part(name):
                operator += mark + '{' + part(name) + '}'
        return operator + ' {' + part('e') + '}'
    if kind == 'm':
        rows = [' & '.join(_math(e) for e in row.findall('m:e', NS))
                for row in node.findall('m:mr', NS)]
        return r'\begin{matrix}' + r' \\ '.join(rows) + r'\end{matrix}'
    if kind == 'eqArr':
        return r'\begin{aligned}' + r' \\ '.join(_math(e) for e in node.findall('m:e', NS)) + r'\end{aligned}'
    if kind == 'acc':
        prop = node.find('m:accPr/m:chr', NS)
        symbol = prop.get('{' + NS['m'] + '}val', '̂') if prop is not None else '̂'
        command = {'̂': 'hat', '^': 'hat', '̅': 'bar', '¯': 'bar', '⃗': 'vec',
                   '→': 'vec', '̃': 'tilde', '~': 'tilde', '̇': 'dot', '̈': 'ddot'}.get(symbol)
        if command:
            return '\\' + command + '{' + part('e') + '}'
    if kind == 'func':
        return r'\operatorname{' + part('fName') + '} {' + part('e') + '}'
    if kind == 'd':
        def delimiter(name, default):
            prop = node.find('m:dPr/m:' + name, NS)
            return prop.get('{' + NS['m'] + '}val', default) if prop is not None else default
        content = delimiter('sepChr', '|').join(_math(c) for c in node.findall('m:e', NS))
        left, right = delimiter('begChr', '('), delimiter('endChr', ')')
        environment = {('(', ')'): 'pmatrix', ('[', ']'): 'bmatrix', ('{', '}'): 'Bmatrix',
                       ('|', '|'): 'vmatrix', ('{', ''): 'cases'}.get((left, right))
        if environment and re.fullmatch(r'\\begin\{(matrix|aligned)\}.*\\end\{\1\}', content, re.S):
            content = re.sub(r'^\\begin\{[^}]+\}', '', content)
            content = re.sub(r'\\end\{[^}]+\}$', '', content)
            return '\\begin{' + environment + '}' + content + '\\end{' + environment + '}'
        return left + content + right
    if kind not in {'oMath', 'oMathPara', 'e', 'r', 'num', 'den', 'sub', 'sup', 'deg', 'mr', 'fName'}:
        warnings.warn(f'Word 公式结构 {kind} 暂不支持准确转换，已保留其中的文字。', UserWarning)
    return ''.join(_math(child) for child in node)


def _inline(node, context=None):
    context = context if context is not None else dict(location='正文', equation=0)
    kind = _tag(node)
    if node.tag == '{' + NS['m'] + '}oMath':
        context['equation'] += 1
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter('always', UserWarning)
            value = _math(node)
        excerpt = ''.join(node.itertext()).strip()[:70]
        for notice in notices:
            warnings.warn(f"{context['location']}，公式 {context['equation']}「{excerpt}」：{notice.message}", UserWarning)
        return '$' + value + '$'
    if node.tag == '{' + NS['m'] + '}oMathPara':
        content = [_inline(c, context)[1:-1] for c in node if _tag(c) == 'oMath']
        return '\n$$\n' + ' '.join(content) + '\n$$\n'
    if kind in {'drawing', 'pict', 'object'}:
        warnings.warn(f"{context['location']}：图片、嵌入对象或图片公式未转写。", UserWarning)
        return ''
    if kind in {'pPr', 'rPr', 'del'}:
        return ''
    if kind == 't':
        return node.text or ''
    if kind == 'tab':
        return '    '
    if kind in {'br', 'cr'}:
        return '\n'
    return ''.join(_inline(child, context) for child in node)


def read_docx(path, include_locations=False, cancel=None):
    """Return simplified Markdown, preserving paragraph/table reading order."""
    try:
        with zipfile.ZipFile(path) as archive:
            def xml(name):
                info = archive.getinfo(name)
                if info.file_size > 32 * 1024 * 1024:
                    raise ValueError('Word 文档内容过大，请拆分后转换。')
                return ET.fromstring(archive.read(name))
            root = xml('word/document.xml')
            styles = xml('word/styles.xml') if 'word/styles.xml' in archive.namelist() else None
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError('无法读取 Word 文档，请确认它是有效且未加密的 .docx 文件。') from exc

    style_map = {}
    if styles is not None:
        for style in styles.findall('w:style', NS):
            style_map[style.get('{' + NS['w'] + '}styleId')] = style

    def properties(paragraph):
        own = paragraph.find('w:pPr', NS)
        props = [own] if own is not None else []
        style = paragraph.find('w:pPr/w:pStyle', NS)
        seen = set()
        key = style.get('{' + NS['w'] + '}val') if style is not None else None
        while key in style_map and key not in seen:
            seen.add(key)
            definition = style_map[key]
            prop = definition.find('w:pPr', NS)
            if prop is not None:
                props.append(prop)
            base = definition.find('w:basedOn', NS)
            key = base.get('{' + NS['w'] + '}val') if base is not None else None
        return props, style

    def paragraph(node, location):
        text = _inline(node, dict(location=location, equation=0)).strip()
        if not text:
            return ''
        props, style = properties(node)
        for prop in props:
            level = prop.find('w:outlineLvl', NS)
            if level is not None:
                value = level.get('{' + NS['w'] + '}val', '9')
                if value.isdigit() and int(value) < 6:
                    return '#' * (int(value) + 1) + ' ' + text
        key = style.get('{' + NS['w'] + '}val', '') if style is not None else ''
        if key.lower() in {'title', '标题'}:
            return '# ' + text
        match = re.fullmatch(r'(?:Heading|标题)\s*([1-6])', key, re.I)
        if match:
            return '#' * int(match.group(1)) + ' ' + text
        if any(prop.find('w:numPr', NS) is not None for prop in props):
            return '- ' + text
        return text

    def blocks(parent, location='正文', annotate=True):
        result = []
        for index, child in enumerate(parent, 1):
            if cancel and cancel():
                from handwriting import ConversionCancelled
                raise ConversionCancelled('已取消 Word 读取')
            kind = _tag(child)
            here = f'{location}/第 {index} 段'
            marker = f'<!--mojian:{here}-->\n' if include_locations and annotate else ''
            if kind == 'p':
                value = paragraph(child, here)
                if value:
                    result.append(marker + value)
            elif kind == 'tbl':
                for ri, row in enumerate(child.findall('w:tr', NS), 1):
                    cells = [' / '.join(blocks(cell, f'{location}/第 {index} 块表格/行 {ri} 列 {ci}', False))
                             for ci, cell in enumerate(row.findall('w:tc', NS), 1)]
                    marker = f'<!--mojian:{location}/第 {index} 块表格/行 {ri}-->\n' if include_locations and annotate else ''
                    result.append(marker + ' ｜ '.join(cells))
            elif kind in {'sdt', 'sdtContent', 'ins'}:
                result.extend(blocks(child, here, annotate))
        return [text for text in result if text.strip()]

    body = root.find('w:body', NS)
    if body is None:
        raise ValueError('Word 文档中没有正文。')
    return '\n\n'.join(blocks(body))
