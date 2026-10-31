# coding: utf-8
r"""
LaTeX 公式 -> 「手写风」二维图片 (基于 matplotlib 的 mathtext)

mathtext 只支持 LaTeX 的一个子集, 本模块负责:
  1. 语法归一化(花括号感知): \dfrac->\frac, \ge->\geq, \iff->\Leftrightarrow,
     \frac1{n'^2}->\frac{1}{n'^2} 等; 以及 cases/aligned/matrix 等环境的排版;
  2. 用自定义字体(默认 霞鹜文楷)把公式排成**二维**样式(帽子/角标/分数线/根号);
  3. 渲染成透明底 PNG, 并返回**基线**信息, 供排版器与正文文字对齐。

对外主要接口:
    render_formula(latex, font_path, font_size, dpi, color) -> Formula
    Formula.image    : PIL.Image (RGBA, 已裁紧)
    Formula.depth    : 基线以下的高度(像素)
    Formula.height   : 图片高度(像素)
    Formula.above    : 基线以上的高度(像素) = height - depth
"""

import os
import re
import numpy as np

import matplotlib
matplotlib.use("Agg")

from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib import font_manager as fm
from PIL import Image, ImageDraw, ImageFont

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FONT = os.path.join(_HERE, "fonts", "LXGWWenKai-Regular.ttf")

_family_cache = {}


def _register(font_path):
    """把字体注册进 matplotlib, 返回其 family 名。"""
    if font_path not in _family_cache:
        if not os.path.exists(font_path):
            raise FileNotFoundError(font_path)
        fm.fontManager.addfont(font_path)
        _family_cache[font_path] = fm.FontProperties(fname=font_path).get_name()
    return _family_cache[font_path]


def _hex(color):
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return "#%02x%02x%02x" % tuple(int(c) for c in color[:3])
    return color


# ---------------------------------------------------------------------------
# 1. LaTeX -> mathtext 归一化
# ---------------------------------------------------------------------------

# 两参数命令(分数线/组合等): 统一写成 \frac{}{}
_TWOARG = {"frac", "dfrac", "tfrac", "cfrac", "binom"}

# 单参数命令: 统一补花括号, 如 \hat p -> \hat{p}
_ONEARG = {
    "sqrt", "hat", "widehat", "vec", "tilde", "widetilde", "bar", "overline",
    "underline", "dot", "ddot", "breve", "check", "acute", "grave",
    "mathring", "boldsymbol", "mathbf", "mathrm", "mathit", "mathcal",
    "mathbb", "mathfrak", "mathsf", "mathtt", "operatorname", "bcancel",
}
_ONEARG_ALIAS = {"text": "mathrm", "mbox": "mathrm", "operatorname": "mathrm"}

# 只保留内容、丢弃外层包裹的命令(兰姆达/花括号标注)
_DROP_WRAP = {"underbrace", "overbrace"}

# 简单名称映射
_CMD_MAP = {
    "dfrac": "frac", "tfrac": "frac", "cfrac": "frac",
    "ge": "geq", "le": "leq", "ne": "neq",
    "iff": "Leftrightarrow", "implies": "Rightarrow", "impliedby": "Leftarrow",
    "to": "rightarrow", "mapsto": "rightarrow", "gets": "leftarrow",
    "displaystyle": "", "limits": "", "nolimits": "",
    "big": "", "Big": "", "bigg": "", "Bigg": "",
    "left": "left", "right": "right",
}


def _match_brace(s, i):
    """s[i]=='{', 返回配对的 '}' 之后的下标。"""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(s)


def _read_arg(s, i):
    """读取一个参数: 返回 (参数字符串, 新下标)。参数可为 {..} / 单字符 / 单命令。"""
    n = len(s)
    while i < n and s[i] == " ":
        i += 1
    if i >= n:
        return "", i
    if s[i] == "{":
        j = _match_brace(s, i)
        return s[i:j], j
    if s[i] == "\\":
        j = i + 1
        while j < n and s[j].isalpha():
            j += 1
        return s[i:j], j
    return s[i], i + 1


def _strip_braces(a):
    a = a.strip()
    if len(a) >= 2 and a[0] == "{" and a[-1] == "}":
        return a[1:-1]
    return a


def normalize(s: str) -> str:
    """把常见 LaTeX 归一化成 mathtext 能解析的形式(花括号感知)。"""
    s = s.strip()
    s = re.sub(r"^\$\$?", "", s)          # 去外层 $ 或 $$
    s = re.sub(r"\$\$?$", "", s)
    s = re.sub(r"\\begin\{[a-zA-Z*]+\}|\\end\{[a-zA-Z*]+\}", "", s)
    s = re.sub(r"\\\\\s*\[[^\]]*\]", r"\\\\", s)   # 去掉换行间距提示 \\[4pt]

    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            j = i + 1
            while j < n and s[j].isalpha():
                j += 1
            name = s[i + 1:j]
            if name in _TWOARG:
                a1, j = _read_arg(s, j)
                a2, j = _read_arg(s, j)
                out.append("\\frac{%s}{%s}" %
                           (normalize(_strip_braces(a1)),
                            normalize(_strip_braces(a2))))
                i = j
                continue
            if name in _DROP_WRAP:
                a1, j = _read_arg(s, j)
                if j < n and s[j] == "_":         # 吃掉 _{标签}
                    _, j = _read_arg(s, j + 1)
                out.append(normalize(_strip_braces(a1)))
                i = j
                continue
            if name in _ONEARG or name in _ONEARG_ALIAS:
                a1, j = _read_arg(s, j)
                out_name = _ONEARG_ALIAS.get(name, name)
                out.append("\\%s{%s}" % (out_name, normalize(_strip_braces(a1))))
                i = j
                continue
            if name in _CMD_MAP:
                v = _CMD_MAP[name]
                out.append(("\\" + v) if v else "")
                i = j
                continue
            out.append(s[i:j])
            i = j
            continue
        out.append(c)
        i += 1

    res = "".join(out)
    res = res.replace(r"\!", "").replace(r"\/", "")
    res = re.sub(r"(?<!\\)\\ ", r"\\,", res)     # 控制空格 "\ " -> 细空格 "\,
    res = re.sub(r"\s+", " ", res).strip()
    return res


# ---------------------------------------------------------------------------
# 2. 二维渲染（精确记录基线）
# ---------------------------------------------------------------------------

class Formula:
    __slots__ = ("image", "depth", "source")

    def __init__(self, image, depth, source):
        self.image = image
        self.depth = depth          # 基线以下像素
        self.source = source

    @property
    def height(self):
        return self.image.height

    @property
    def width(self):
        return self.image.width

    @property
    def above(self):
        return self.image.height - self.depth


_cache = {}

_ENV_FIND = re.compile(
    r"\\begin\{(cases|aligned|alignedat|gathered|split|matrix|pmatrix|"
    r"bmatrix|vmatrix|Bmatrix|array)\}(.*?)\\end\{\1\}", re.S)
_BRACED_ENVS = {"cases"}
_MATRIX_ENVS = {"matrix", "pmatrix", "bmatrix", "vmatrix", "Bmatrix", "array"}


def _make_brace(font_path, h, color, char='{'):
    """用 PIL 把 '{' 缩放成高度约 h 的大括号 PNG。"""
    probe = ImageFont.truetype(font_path, 100)
    l, t, r, b = probe.getbbox(char)
    gh = max(1, b - t)
    size = max(12, int(round(100 * h / gh)))
    f = ImageFont.truetype(font_path, size)
    l, t, r, b = f.getbbox(char)
    img = Image.new("RGBA", (max(1, r - l) + 4, max(1, b - t) + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((-l + 2, -t + 2), char, font=f, fill=tuple(color[:3]) + (255,))
    return img


def _render_environment(env, body, font_path, font_size, dpi, color):
    """排版 cases / aligned / matrix 等环境: 逐单元格渲染后二维拼装。"""
    body = re.sub(r"\\\\\s*\[[^\]]*\]", r"\\\\", body)        # 去行距提示
    if env == "array":
        body = re.sub(r"^\s*\{[^}]*\}", "", body)             # 去列格式
    rows = [r.strip() for r in body.split("\\\\")]
    rows = [r for r in rows if r]

    grid = []
    for r in rows:
        cells = []
        for c in r.split("&"):
            c = c.strip()
            if not c or c in (r"\ ", r"\quad"):
                cells.append(None)
                continue
            try:
                cells.append(render_formula(c, font_path, font_size, dpi, color))
            except Exception as exc:
                raise ValueError(f'{env} 第 {len(grid)+1} 行、第 {len(cells)+1} 列公式无法渲染：{c}') from exc
        grid.append(cells)
    if not grid:
        raise ValueError("空环境")

    ncol = max(len(r) for r in grid)
    gap = int(font_size * 0.4)
    row_gap = int(font_size * 0.2)
    col_w = [0] * ncol
    row_h = []
    for imgs in grid:
        h = font_size
        for ci, im in enumerate(imgs):
            if im:
                col_w[ci] = max(col_w[ci], im.width)
                h = max(h, im.height)
        row_h.append(h)

    pad = int(font_size * 0.2)
    total_h = sum(row_h) + row_gap * (len(grid) - 1)

    # 先把左大括号画出来, 再按它的真实宽度预留左边距, 避免与首列重叠
    brace = None
    brace_w = 0
    delimiters = {'cases': ('{', ''), 'pmatrix': ('(', ')'), 'bmatrix': ('[', ']'),
                  'Bmatrix': ('{', '}'), 'vmatrix': ('|', '|')}
    left_char, right_char = delimiters.get(env, ('', ''))
    right_brace = _make_brace(font_path, total_h, color, right_char) if right_char else None
    if left_char:
        brace = _make_brace(font_path, total_h, color, left_char)
        brace_w = brace.width + int(font_size * 0.18)
    total_w = brace_w + sum(col_w) + gap * max(0, ncol - 1) + pad
    if right_brace:
        total_w += right_brace.width + pad

    canvas = Image.new("RGBA", (max(1, total_w), max(1, total_h)), (0, 0, 0, 0))
    y, top_above = 0, font_size
    for ri, imgs in enumerate(grid):
        h = row_h[ri]
        x = brace_w
        for ci, im in enumerate(imgs):
            if im is not None:
                oy = y + (h - im.height) // 2
                canvas.paste(im.image, (x, oy), im.image)
                if ri == 0 and ci == 0:
                    top_above = oy + im.above
            x += col_w[ci] + gap
        y += h + row_gap

    if brace is not None:
        canvas.paste(brace, (0, (total_h - brace.height) // 2), brace)
    if right_brace is not None:
        canvas.paste(right_brace, (total_w - right_brace.width, (total_h - right_brace.height) // 2), right_brace)

    depth = max(0, min(total_h, total_h - top_above))
    return Formula(canvas, depth, env)


def _compose(parts, font_size, gap):
    """把若干 Formula 按基线横向拼接成一个 Formula。"""
    above = max(p.above for p in parts)
    depth = max(p.depth for p in parts)
    h = above + depth
    w = sum(p.width for p in parts) + gap * (len(parts) - 1)
    canvas = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    x = 0
    for p in parts:
        canvas.paste(p.image, (int(x), int(above - p.above)), p.image)
        x += p.width + gap
    return Formula(canvas, depth, "compose")


def render_formula(latex: str, font_path: str = DEFAULT_FONT, font_size: int = 40,
                   dpi: int = 150, color=(28, 30, 66)) -> Formula:
    """渲染单个公式, 返回 Formula。font_size 为像素(与正文一致)。"""
    key = (latex.strip(), font_path, font_size, dpi, tuple(color))
    if key in _cache:
        return _cache[key]

    stripped = re.sub(r"^\$\$?", "", latex.strip())
    stripped = re.sub(r"\$\$?$", "", stripped).strip()

    # 环境(cases/aligned/matrix...)可能出现在公式中间, 如 V(x)=\begin{cases}...
    # 拆成 文本片段 + 环境片段, 各自渲染后按基线横向拼接。
    segs, pos, found = [], 0, False
    for m in _ENV_FIND.finditer(stripped):
        found = True
        if m.start() > pos:
            segs.append(("tex", stripped[pos:m.start()]))
        segs.append(("env", m.group(1), m.group(2)))
        pos = m.end()
    if pos < len(stripped):
        segs.append(("tex", stripped[pos:]))
    if found:
        parts = []
        for seg in segs:
            if seg[0] == "tex":
                t = seg[1].strip()
                if t:
                    parts.append(render_formula(t, font_path, font_size, dpi,
                                                color))
            else:
                parts.append(_render_environment(seg[1], seg[2], font_path,
                                                 font_size, dpi, color))
        f = parts[0] if len(parts) == 1 else \
            _compose(parts, font_size, int(font_size * 0.18))
        _cache[key] = f
        return f

    expr = normalize(latex)
    if not expr:
        raise ValueError("空公式")

    family = _register(font_path)
    matplotlib.rcParams.update({
        "mathtext.fontset": "custom",
        "mathtext.rm": family, "mathtext.it": family,
        "mathtext.bf": family, "mathtext.cal": family, "mathtext.sf": family,
        "mathtext.default": "regular",     # 字母直立, 更接近手写
        "font.family": family,
    })
    # matplotlib 的 size 单位是磅: 1pt = dpi/72 像素, 故按像素换算
    size_pt = font_size * 72.0 / dpi
    prop = fm.FontProperties(fname=font_path, size=size_pt)

    # 画布留足空间, 防止长公式/深分数被裁掉
    w_px = max(240, int(len(expr) * font_size * 0.85) + 120)
    h_px = max(160, int(font_size * 6)) + 120
    fig = Figure(figsize=(w_px / dpi, h_px / dpi), dpi=dpi)
    fig.patch.set_alpha(0.0)
    canvas = FigureCanvasAgg(fig)

    y_frac = 0.5
    color = _hex(color)
    # 关键: matplotlib 只有在文本被 $...$ 包裹时才按数学公式排版,
    # normalize() 已去掉外层 $, 这里必须补回来, 否则会当普通文本逐字渲染。
    fig.text(0.02, y_frac, "$" + expr + "$", fontproperties=prop, color=color,
             va="baseline", ha="left")
    canvas.draw()

    buf = np.asarray(canvas.buffer_rgba())
    alpha = buf[:, :, 3]
    rows = np.where(alpha.any(axis=1))[0]
    cols = np.where(alpha.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        raise ValueError(f"渲染为空: {latex!r}")

    top, bottom = int(rows[0]), int(rows[-1]) + 1
    left, right = int(cols[0]), int(cols[-1]) + 1
    sub = buf[top:bottom, left:right]
    img = Image.fromarray(sub, "RGBA")

    baseline_row = (1.0 - y_frac) * buf.shape[0]
    depth = int(round(bottom - baseline_row))
    depth = max(0, min(depth, img.height))     # 夹紧

    f = Formula(img, depth, latex)
    _cache[key] = f
    return f


if __name__ == "__main__":
    for t in [r"\hat{L}=\hat{\vec r}\times\hat{\vec p}=-i\hbar\,\vec r\times\nabla",
              r"\hat T=\frac{\hat p^2}{2\mu}=-\frac{\hbar^2}{2\mu}\nabla^2",
              r"[\hat L_x,\hat L_y]=i\hbar\hat L_z",
              r"\tilde\nu=R\left(\frac1{n'^2}-\frac1{n^2}\right)",
              r"U(\vec r)=U(r)\quad(\text{球对称})",
              r"V(x)=\begin{cases}V_1, & x<a\\ V_2, & x>a\end{cases}"]:
        f = render_formula(t)
        print(f"ok  {f.width}x{f.height} depth={f.depth}  <= {t}")
