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
    if kind == 'd':
        def delimiter(name, default):
            prop = node.find('m:dPr/m:' + name, NS)
            return prop.get('{' + NS['m'] + '}val', default) if prop is not None else default
        content = delimiter('sepChr', '|').join(_math(c) for c in node.findall('m:e', NS))
        return delimiter('begChr', '(') + content + delimiter('endChr', ')')
    if kind in {'nary', 'm', 'eqArr', 'acc', 'limLow', 'limUpp', 'groupChr', 'bar', 'func'}:
        warnings.warn('部分 Word 公式结构暂不支持，已提取其中的文字；请检查公式。', UserWarning)
    return ''.join(_math(child) for child in node)


def _inline(node):
    kind = _tag(node)
    if node.tag == '{' + NS['m'] + '}oMath':
        return '$' + _math(node) + '$'
    if node.tag == '{' + NS['m'] + '}oMathPara':
        return '\n$$\n' + ''.join(_math(c) for c in node if _tag(c) == 'oMath') + '\n$$\n'
    if kind in {'pPr', 'rPr', 'del', 'drawing', 'pict', 'object'}:
        return ''
    if kind == 't':
        return node.text or ''
    if kind == 'tab':
        return '    '
    if kind in {'br', 'cr'}:
        return '\n'
    return ''.join(_inline(child) for child in node)


def read_docx(path):
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

    def paragraph(node):
        text = _inline(node).strip()
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

    def blocks(parent):
        result = []
        for child in parent:
            kind = _tag(child)
            if kind == 'p':
                result.append(paragraph(child))
            elif kind == 'tbl':
                for row in child.findall('w:tr', NS):
                    cells = [' / '.join(blocks(cell)) for cell in row.findall('w:tc', NS)]
                    result.append(' ｜ '.join(cells))
            elif kind in {'sdt', 'sdtContent', 'ins'}:
                result.extend(blocks(child))
        return [text for text in result if text.strip()]

    body = root.find('w:body', NS)
    if body is None:
        raise ValueError('Word 文档中没有正文。')
    if any(_tag(node) in {'drawing', 'pict', 'object'} for node in body.iter()):
        warnings.warn('Word 中的图片、嵌入对象或图片公式未转写，仅提取文本与支持的原生公式。', UserWarning)
    return '\n\n'.join(blocks(body))
