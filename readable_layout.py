"""Conservative text grouping and TeX splitting; never interpret document code."""
import re

_TOKEN = re.compile(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?(?:[ \u00a0]?[A-Za-zμµΩ℃°%]{1,8}(?:[/^][A-Za-z0-9μµΩ℃°%]{1,4})?(?![A-Za-z]))?|[A-Za-z]+(?:['-][A-Za-z]+)*")


def text_tokens(text):
    position = 0
    for match in _TOKEN.finditer(text):
        yield from text[position:match.start()]
        yield match[0]
        position = match.end()
    yield from text[position:]


def safe_math_segments(latex):
    """Split before top-level binary =,+,- only. Concatenation equals input.

    Braces, literal/scalable brackets and entire environments are protected.
    Script operands without braces and ambiguous constructs reject splitting.
    """
    if re.search(r'[_^]\s*(?!\{)[+\-=]', latex):
        return [latex], '上下标操作数不明确'
    stack=[]; positions=[]; index=0; previous=''
    pairs={')':'(',']':'[','}':'{'}
    while index<len(latex):
        char=latex[index]
        if char=='\\':
            command=re.match(r'\\(?:[A-Za-z]+|.)',latex[index:])
            if not command: return [latex], '反斜线命令不完整'
            token=command[0]
            openers={r'\langle':r'\rangle',r'\lfloor':r'\rfloor',r'\lceil':r'\rceil',r'\lvert':r'\rvert',r'\lVert':r'\rVert'}
            if token in openers: stack.append(openers[token])
            elif token in openers.values():
                if not stack or stack.pop()!=token: return [latex], '命令括号未配对'
            elif token in {r'\vert',r'\Vert'}: return [latex], '竖线分组不明确'
            if token in {r'\begin',r'\end'}:
                env=re.match(r'\{([^}]+)\}',latex[index+len(token):])
                if not env: return [latex], '环境名称不完整'
                if token==r'\begin': stack.append('env:'+env[1])
                elif not stack or stack.pop()!='env:'+env[1]: return [latex], '环境未正确配对'
                index+=len(token)+env.end(); previous='operand'; continue
            if token in {r'\left',r'\right'}:
                delimiter=re.match(r'\s*(\\[A-Za-z]+|\\.|.)',latex[index+len(token):])
                if not delimiter: return [latex], '伸缩括号不完整'
                if token==r'\left': stack.append('left')
                elif not stack or stack.pop()!='left': return [latex], '伸缩括号未配对'
                index+=len(token)+delimiter.end();previous='operand';continue
            # Escaped braces are visible delimiters and protect their contents.
            if token==r'\{': stack.append('escaped')
            elif token==r'\}':
                if not stack or stack.pop()!='escaped': return [latex], '转义括号未配对'
            elif token in {r'\over',r'\atop',r'\choose',r'\middle'}:
                return [latex], '含不可靠的分组运算符'
            index+=len(token);previous='operand';continue
        if char in '({[': stack.append(char)
        elif char in ')}]':
            if not stack or stack.pop()!=pairs[char]: return [latex], '括号未配对'
        elif char=='|':
            return [latex], '绝对值/条件竖线含义不明确'
        elif char in '=+-' and not stack and previous not in {'','operator','script'}:
            if char=='=' and (latex[:index].rstrip().endswith(('<','>','!',':','=')) or latex[index+1:index+2]=='='):
                index+=1; previous='operator'; continue
            # Never split scientific notation such as 1e-3.
            if not (char in '+-' and index and latex[index-1] in 'eE' and index>1 and latex[index-2].isdigit()):
                positions.append(index)
        if not char.isspace():
            previous='operator' if char in '=+-*/,;' else 'script' if char in '_^' else 'operand'
        index+=1
    if stack: return [latex], '括号或环境未闭合'
    parts=[]; start=0
    for position in positions:
        parts.append(latex[start:position]); start=position
    parts.append(latex[start:])
    if len(parts)<2: return [latex], '未找到可靠的顶层二元等号/加减号'
    return parts, '仅在顶层二元运算符之前分行，运算符及顺序保留'


def fit_math_lines(latex, measure, width):
    segments, reason=safe_math_segments(latex)
    if len(segments)==1: return [latex], reason
    lines=[]; current=''
    for segment in segments:
        candidate=current+segment
        if current and measure(candidate)>width:
            lines.append(current); current=segment
        else: current=candidate
    if current: lines.append(current)
    return lines, reason
