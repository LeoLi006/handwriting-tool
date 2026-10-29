# coding: utf-8
r"""
Markdown(.md) -> 手写体图片 转换引擎（混合排版）

区别于旧的"逐字符一维流"做法, 本引擎:
  - 正文: 逐字绘制 (手写字体 + 位置/字号/旋转微抖动,
          使同一字每次出现写法都略有不同), 按宽度自动换行、分页;
  - 公式: 行内 $...$ 与行间 $$...$$ 都用 matplotlib 排成**二维**样式
          (帽子/角标/分数线/根号), 采用手写字体, 与正文按基线混排;
  - 背景: A4 横线本。

命令行:
    python handwriting.py 输入.md -o 输出目录
    python handwriting.py 输入.md --font MaShanZheng --line-spacing 1.2
    python handwriting.py --list-fonts
"""

import argparse
import copy
import math
import os
import random
import re
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import formula as fml
except Exception as e:                                    # pragma: no cover
    sys.exit(f"缺少公式模块依赖(需要 matplotlib): {e}")

FONT_DIR = os.path.join(HERE, "fonts")
FALLBACK = os.path.join(FONT_DIR, "LXGWWenKai-Regular.ttf")   # 符号最全, 也用于公式
FONTS_JSON = os.path.join(FONT_DIR, "fonts.json")
COLOR = (28, 30, 66)


# ----------------------------------------------------------------------------
# 0. 字体: 注册表 + 缺字自动回退合并
# ----------------------------------------------------------------------------

# 需要保证可用的符号(缺了就用回退字体补)
_NEED = set(map(ord, "ℏ∂∇∫∑√∞≈→≥≤±·εψφμ²₀ₓ†‾─"))
_FALLBACK_RANGES = [(0x0000, 0x024F), (0x0370, 0x03FF), (0x1D00, 0x1DBF),
                    (0x1E00, 0x1EFF), (0x2000, 0x206F), (0x2070, 0x209F),
                    (0x20A0, 0x20CF), (0x2100, 0x214F), (0x2150, 0x218F),
                    (0x2190, 0x21FF), (0x2200, 0x22FF), (0x2300, 0x23FF),
                    (0x2500, 0x257F), (0x2580, 0x259F), (0x25A0, 0x25FF),
                    (0x2600, 0x26FF), (0x27C0, 0x27EF), (0x2980, 0x29FF),
                    (0x2A00, 0x2AFF), (0x2C60, 0x2C7F), (0x2E00, 0x2E7F),
                    (0x3000, 0x303F), (0xA700, 0xA71F), (0xFF00, 0xFFEF)]


def _wanted(cp: int) -> bool:
    return any(a <= cp <= b for a, b in _FALLBACK_RANGES)


def _coverage(path: str) -> set:
    from fontTools.ttLib import TTFont
    f = TTFont(path, fontNumber=0, lazy=True)
    cm = set()
    for t in f["cmap"].tables:
        if t.isUnicode():
            cm |= set(t.cmap.keys())
    return cm


def _has_glyf(path: str) -> bool:
    from fontTools.ttLib import TTFont
    return "glyf" in TTFont(path, fontNumber=0, lazy=True).keys()


def _merge_fallback(base_path: str, donor_path: str, out_path: str):
    """把 donor 中 base 缺失的(拉丁/希腊/数学等)字形复制进 base, 生成回退字体。"""
    from fontTools.ttLib import TTFont
    base = TTFont(base_path, fontNumber=0)
    donor = TTFont(donor_path, fontNumber=0)
    base_cmap, donor_cmap = base.getBestCmap(), donor.getBestCmap()
    base_glyf, donor_glyf = base["glyf"], donor["glyf"]
    base_hmtx, donor_hmtx = base["hmtx"], donor["hmtx"]
    base_names = set(base.getGlyphOrder())

    needed = [cp for cp in donor_cmap if cp not in base_cmap and _wanted(cp)]
    to_copy, seen = [], set()
    stack = [donor_cmap[cp] for cp in needed]
    while stack:
        g = stack.pop()
        if g in seen or g in base_names:
            continue
        seen.add(g)
        to_copy.append(g)
        try:
            gl = donor_glyf[g]
            if gl.isComposite():
                stack.extend(c.component.glyphName for c in gl.components)
        except Exception:
            pass

    base.setGlyphOrder(base.getGlyphOrder() + [g for g in to_copy if g not in base_names])
    fallback_adv = donor_hmtx.metrics.get(donor_cmap.get(0x20), (1000, 0))
    for g in to_copy:
        base_glyf[g] = copy.deepcopy(donor_glyf[g])
        base_hmtx.metrics[g] = donor_hmtx.metrics.get(g, fallback_adv)

    for table in base["cmap"].tables:
        if not table.isUnicode():
            continue
        for cp in needed:
            if table.format == 4 and cp > 0xFFFF:
                continue
            table.cmap[cp] = donor_cmap[cp]

    base["maxp"].numGlyphs = len(base.getGlyphOrder())
    base.save(out_path)


def load_registry() -> dict:
    """读取字体注册表 {风格名: 文件名}。"""
    if os.path.exists(FONTS_JSON):
        import json
        with open(FONTS_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def resolve_font(name_or_path: str) -> str:
    """返回字形齐全、可直接给 Pillow 使用的字体路径。"""
    if os.path.exists(name_or_path):
        path = name_or_path
    else:
        registry = load_registry()
        key = name_or_path.strip()
        if key in registry:
            path = os.path.join(FONT_DIR, registry[key])
        elif os.path.exists(os.path.join(FONT_DIR, key)):
            path = os.path.join(FONT_DIR, key)
        else:
            avail = ", ".join(registry.keys()) or "(空)"
            sys.exit(f"未找到字体 '{name_or_path}'。可选: {avail}")

    if not os.path.exists(path):
        sys.exit(f"字体文件不存在: {path}")

    if _NEED <= _coverage(path):
        return path

    cache = os.path.join(FONT_DIR, "_merged_" +
                         os.path.splitext(os.path.basename(path))[0] + ".ttf")
    if os.path.exists(cache) and _coverage(cache) >= _NEED:
        return cache
    if os.path.exists(FALLBACK) and _has_glyf(path) and _has_glyf(FALLBACK):
        try:
            _merge_fallback(path, FALLBACK, cache)
            return cache
        except Exception as e:
            print(f"[警告] 字体合并失败({e}), 退回原字体, 符号可能显示为方框",
                  file=sys.stderr)
    return path


def list_fonts():
    registry = load_registry()
    print("可用风格字体 (--font 传风格名):")
    for style, fn in registry.items():
        ok = "√" if _NEED <= _coverage(os.path.join(FONT_DIR, fn)) else "需要合并"
        print(f"  {style:16s} {fn:34s} {ok}")


def pick_font(name_or_path=None):
    """默认字体: 内置霞鹜文楷(WenKai), 退回系统楷体。"""
    if name_or_path:
        return resolve_font(name_or_path)
    registry = load_registry()
    default = registry.get("WenKai", "LXGWWenKai-Regular.ttf")
    cand = os.path.join(FONT_DIR, default)
    if os.path.exists(cand):
        return resolve_font(cand)
    for name in ["simkai.ttf", "STKAITI.TTF", "simfang.ttf", "STXINGKA.TTF"]:
        p = os.path.join(r"C:\Windows\Fonts", name)
        if os.path.exists(p):
            return resolve_font(p)
    sys.exit("未找到可用中文字体, 请用 --font 手动指定 (或 --list-fonts 查看)")


# ----------------------------------------------------------------------------
# 1. Markdown -> 结构化块
# ----------------------------------------------------------------------------

_INLINE_MATH = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$", re.S)
_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.S)      # 行间公式 $$...$$
_WORD = re.compile(r"[A-Za-z0-9]+(?:[.'\-][A-Za-z0-9]+)*")


def _clean_md(s: str) -> str:
    s = s.replace("**", "").replace("__", "").replace("`", "")
    s = re.sub(r"^\s*>\s?", "", s)
    return s


def _emit_text(s, blocks, style="text", lvl=0):
    """把一段文字按行间公式 $$...$$ 切开: 公式单独成块, 其余作为文本块。
    这样既能处理独立成行的 $$...$$, 也能处理夹在句子/项目符号里的 $$...$$。"""
    s = s.strip()
    if not s:
        return
    pos, segs = 0, []
    for m in _DISPLAY_MATH.finditer(s):
        if m.start() > pos:
            segs.append(("txt", s[pos:m.start()]))
        segs.append(("math", m.group(1)))
        pos = m.end()
    if pos < len(s):
        segs.append(("txt", s[pos:]))
    for kind, val in segs:
        val = val.strip()
        if not val:
            continue
        if kind == "math":
            blocks.append(("formula", val))
        elif style == "heading":
            blocks.append(("heading", lvl, val))
        else:
            blocks.append((style, val))


def markdown_to_blocks(md: str):
    """把 markdown 拆成 [('heading',lvl,txt)|('text',txt)|('bullet',txt)|
    ('formula',latex)|('rule',)]。"""
    md = re.sub(r"```.*?```", "", md, flags=re.S)
    blocks, buf = [], []

    def flush():
        if buf:
            _emit_text(" ".join(buf), blocks)
            buf.clear()

    for raw in md.splitlines():
        st = raw.strip()
        if not st:
            flush(); continue
        if re.fullmatch(r"[-*_]{3,}", st):
            flush(); blocks.append(("rule",)); continue
        m = re.match(r"^(#{1,6})\s*(.+)$", st)
        if m:
            flush()
            _emit_text(_clean_md(m.group(2)), blocks,
                       style="heading", lvl=len(m.group(1)))
            continue
        m = re.match(r"^[-*+]\s+(.+)$", st)
        if m:
            flush(); _emit_text(_clean_md(m.group(1)), blocks, style="bullet")
            continue
        m = re.match(r"^(\d+[.)])\s+(.+)$", st)
        if m:
            flush()
            _emit_text(f"{m.group(1)} {_clean_md(m.group(2))}", blocks,
                       style="bullet")
            continue
        buf.append(_clean_md(st))
    flush()
    return blocks


# ----------------------------------------------------------------------------
# 2. 背景 & 渲染
# ----------------------------------------------------------------------------

def make_background(size, line_spacing, top_margin, bottom_margin,
                    left_margin, right_margin, ruled=True):
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    if ruled:
        rule = (208, 214, 222)
        for y in range(top_margin + line_spacing, size[1] - bottom_margin + 1, line_spacing):
            d.line([(left_margin - 20, y), (size[0] - right_margin + 20, y)],
                   fill=rule, width=1)
    y0 = top_margin - 24
    d.line([(left_margin - 20, y0), (size[0] - right_margin + 20, y0)],
           fill=(150, 160, 175), width=2)
    return img


class Renderer:
    """混合排版器: 正文逐字手写 + 公式二维贴图, 自动换行/分页。"""

    def __init__(self, font_size, dpi, ruled, line_spacing_ratio, word_spacing,
                 body_font, formula_font, seed, jitter=1.0):
        self.size = font_size
        self.dpi = dpi
        self.ruled = ruled
        self.word_spacing = word_spacing
        self.body = body_font
        self.ffont = formula_font
        self.rand = random.Random(seed)
        self.jitter = max(0.0, float(jitter))   # 笔迹随机度: 0=关闭, 1=默认
        self._writing_slant = 0.0
        self._writing_scale = 0.0

        # A4 210x297mm
        self.w = int(210 / 25.4 * dpi)
        self.h = int(297 / 25.4 * dpi)
        self.left = self.right = int(self.w * 0.07)
        self.top = int(self.h * 0.05)
        self.bottom = int(self.h * 0.045)
        self.line_spacing = max(int(font_size + 2), int(font_size * line_spacing_ratio))

        self._fonts = {}
        self.ascent, self.descent = self._metrics(font_size)
        self.pages = []
        self._new_page()

    # -- 基础 ---------------------------------------------------------------
    def _font(self, size):
        if size not in self._fonts:
            self._fonts[size] = ImageFont.truetype(self.body, size)
        return self._fonts[size]

    def _metrics(self, size):
        return self._font(size).getmetrics()

    def _adv(self, s, size):
        return self.draw.textlength(s, font=self._font(size))

    def _gauss(self, sig):
        return self.rand.gauss(0, sig)

    def _deform_char(self, tile, size):
        """使用连续位移场和共享网格改变字内部比例，保持图块边界固定。"""
        amplitude = size * 0.035 * min(self.jitter, 2.5)
        coefficients = [self.rand.uniform(-amplitude, amplitude) for _ in range(6)]
        width, height = tile.size

        def source(x, y):
            u, v = x / width, y / height
            envelope = math.sin(math.pi * u) * math.sin(math.pi * v)
            a, b, c, d, e, f = coefficients
            dx = envelope * (a + b * math.cos(math.pi * u) + c * math.cos(math.pi * v))
            dy = envelope * (d + e * math.cos(math.pi * u) + f * math.cos(math.pi * v))
            return x + dx, y + dy

        xs = sorted(set(round(width * i / 6) for i in range(7)))
        ys = sorted(set(round(height * i / 6) for i in range(7)))
        mesh = []
        for top, bottom in zip(ys, ys[1:]):
            for left, right in zip(xs, xs[1:]):
                quad = (source(left, top) + source(left, bottom)
                        + source(right, bottom) + source(right, top))
                mesh.append(((left, top, right, bottom), quad))
        return tile.transform(tile.size, Image.Transform.MESH, mesh,
                              resample=Image.Resampling.BICUBIC)

    def _draw_char(self, ch, x, y, size):
        """绘制字形，叠加内部局部形变与缓慢变化的书写节奏。
        (x, y) 为该字基线左端坐标。
        """
        j = self.jitter
        if j > 0:
            self._writing_slant = 0.88 * self._writing_slant + self.rand.uniform(-0.35, 0.35)
            self._writing_scale = 0.88 * self._writing_scale + self.rand.uniform(-0.003, 0.003)
            sz = max(8, int(round(size * (1 + self._writing_scale * j
                                         + self._gauss(0.012 * j)))))
        else:
            sz = size
        f = self._font(sz)
        asc, desc = f.getmetrics()
        pad = max(3, int(size * 0.14))
        w = int(self._adv(ch, sz)) + 2 * pad
        h = asc + desc + 2 * pad
        tile = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        td.text((pad, pad + asc), ch, font=f, fill=COLOR, anchor="ls")
        if j > 0:
            if not ch.isspace():
                tile = self._deform_char(tile, sz)
            ang = (self._writing_slant + self._gauss(0.9)) * j
            if abs(ang) > 0.15:
                # expand=False: 绕中心旋转, 基线位置基本不变
                tile = tile.rotate(ang, resample=Image.BICUBIC)
        self.page.paste(tile, (int(x - pad), int(y - (pad + asc))), tile)

    def _new_page(self):
        bg = make_background((self.w, self.h), self.line_spacing, self.top,
                             self.bottom, self.left, self.right, self.ruled)
        self.page = bg
        self.draw = ImageDraw.Draw(bg)
        self.y = self.top                       # 当前行"顶"的 y
        self.pages.append(bg)

    def _ensure(self, need):
        if self.y + need > self.h - self.bottom:
            self._new_page()

    # -- 行内解析 -----------------------------------------------------------
    def _inline_items(self, text):
        items, pos = [], 0
        for m in _INLINE_MATH.finditer(text):
            if m.start() > pos:
                items.append(("text", text[pos:m.start()]))
            latex = m.group(1).strip()
            try:
                items.append(("math",
                              fml.render_formula(latex, self.ffont, self.size,
                                                 self.dpi, COLOR)))
            except Exception:
                items.append(("text", latex))
            pos = m.end()
        if pos < len(text):
            items.append(("text", text[pos:]))
        return items

    def _tokens(self, s, size):
        toks, i = [], 0
        for m in _WORD.finditer(s):
            if m.start() > i:
                for ch in s[i:m.start()]:
                    toks.append((ch, self._adv(ch, size)))
            toks.append((m.group(0), self._adv(m.group(0), size)))
            i = m.end()
        for ch in s[i:]:
            toks.append((ch, self._adv(ch, size)))
        return toks

    # -- 绘制 ---------------------------------------------------------------
    def _draw_flow(self, items, size, indent=0):
        if not items:
            return
        self._ensure(self._metrics(size)[0] + self._metrics(size)[1])
        ascent = self._metrics(size)[0]
        x = self.left + indent
        limit = self.w - self.right
        for kind, val in items:
            if kind == "text":
                for tok, tw in self._tokens(val, size):
                    if tok == " ":
                        x += tw
                        continue
                    tw += self.word_spacing * len(tok)
                    if x + tw > limit and x > self.left + indent:
                        self.y += self.line_spacing
                        self._ensure(ascent + self._metrics(size)[1])
                        x = self.left + indent
                    cx = x
                    j = self.jitter
                    for ch in tok:
                        self._draw_char(
                            ch,
                            cx + self._gauss(size * 0.03 * j),
                            self.y + ascent + self._gauss(size * 0.03 * j),
                            size)
                        cx += self._adv(ch, size) + self.word_spacing \
                            + self._gauss(size * 0.02 * j)
                    x = cx
            else:                                   # math
                fi = val
                if x + fi.width > limit and x > self.left + indent:
                    self.y += self.line_spacing
                    self._ensure(ascent + self._metrics(size)[1])
                    x = self.left + indent
                py = self.y + ascent - fi.above
                self.page.paste(fi.image, (int(x), int(py)), fi.image)
                x += fi.width + size * 0.18
        self.y += self.line_spacing

    def _draw_display_formula(self, latex):
        try:
            fi = fml.render_formula(latex, self.ffont, self.size, self.dpi, COLOR)
        except Exception:
            self._draw_flow([("text", latex)], self.size)
            return
        maxw = self.w - self.left - self.right
        if fi.width > maxw:                          # 过宽则等比缩小
            s = maxw / fi.width
            fi = fml.Formula(
                fi.image.resize((max(1, int(fi.width * s)),
                                 max(1, int(fi.height * s)))),
                int(fi.depth * s), fi.source)
        gap = int(self.line_spacing * 0.35)
        self._ensure(fi.height + gap + self.ascent)
        base = self.y + self.ascent
        top_y = base - fi.above
        if top_y < self.top:                         # 防止超出上边界
            self.y += (self.top - top_y)
            base = self.y + self.ascent
            top_y = base - fi.above
        cx = self.left + max(0, (maxw - fi.width) // 2)
        self.page.paste(fi.image, (int(cx), int(top_y)), fi.image)
        self.y = top_y + fi.height + gap

    def _draw_rule(self):
        self._ensure(self.line_spacing)
        yy = self.y + self.ascent * 0.55
        self.draw.line([(self.left - 10, yy), (self.w - self.right + 10, yy)],
                       fill=(150, 160, 175), width=1)
        self.y += int(self.line_spacing * 0.9)

    # -- 入口 ---------------------------------------------------------------
    def draw_block(self, block, formula=True):
        kind = block[0]
        if kind == "formula":
            if formula:
                self._draw_display_formula(block[1])
            else:
                self._draw_flow([("text", block[1])], self.size)
        elif kind == "heading":
            lvl, txt = block[1], block[2]
            txt = "【 " + txt + " 】" if lvl == 1 else \
                  ("◆ " + txt if lvl == 2 else "· " + txt)
            size = int(self.size * 1.12)
            self._draw_flow(self._inline_items(txt), size)
        elif kind == "bullet":
            self._draw_flow([("text", "· ")] + self._inline_items(block[1]),
                            self.size, indent=int(self.size * 0.7))
        elif kind == "rule":
            self._draw_rule()
        else:
            self._draw_flow(self._inline_items(block[1]), self.size)


def render_markdown(md, *, font=None, font_size=40, dpi=150, seed=20231029,
                    ruled=True, line_spacing_ratio=1.4, word_spacing=0.0,
                    formula=True, formula_font=None, jitter=1.0):
    """把 markdown 文本渲染成若干页 PIL.Image, 返回 (pages, renderer)。"""
    body = pick_font(font)
    ffont = formula_font or FALLBACK
    if not os.path.exists(ffont):
        ffont = body
    r = Renderer(font_size, dpi, ruled, line_spacing_ratio, word_spacing,
                 body, ffont, seed, jitter=jitter)
    for blk in markdown_to_blocks(md):
        r.draw_block(blk, formula=formula)
    return r.pages, r


def convert_text(text, outdir, stem, *, font=None, font_size=40, dpi=150,
                 seed=20231029, ruled=True, line_spacing_ratio=1.4,
                 word_spacing=0.0, formula=True, formula_font=None,
                 jitter=1.0, page=0, max_pages=0, progress=None):
    """把 (markdown) 文本渲染成手写体 PNG, 返回输出文件路径列表。"""
    os.makedirs(outdir, exist_ok=True)
    pages, r = render_markdown(
        text, font=font, font_size=font_size, dpi=dpi, seed=seed, ruled=ruled,
        line_spacing_ratio=line_spacing_ratio, word_spacing=word_spacing,
        formula=formula, formula_font=formula_font, jitter=jitter)
    out_paths = []
    for i, pg in enumerate(pages, 1):
        if page and i != page:
            continue
        if max_pages and len(out_paths) >= max_pages:
            break
        path = os.path.join(outdir, f"{stem}_p{i}.png")
        pg.save(path)
        out_paths.append(path)
        if progress:
            progress(len(out_paths), len(pages))
    return out_paths


def convert_file(input_path, outdir=None, *, font=None, font_size=40, dpi=150,
                 seed=20231029, ruled=True, line_spacing_ratio=1.4,
                 word_spacing=0.0, formula=True, formula_font=None,
                 jitter=1.0, page=0, max_pages=0, progress=None):
    """把 .md 文件转成手写体 PNG, 返回输出路径列表。"""
    with open(input_path, encoding="utf-8") as f:
        md = f.read()
    if not md.strip():
        raise ValueError("文件为空")
    stem = os.path.splitext(os.path.basename(input_path))[0]
    if outdir is None:
        outdir = os.path.join(os.path.dirname(os.path.abspath(input_path)), "手写体")
    return convert_text(md, outdir, stem, font=font, font_size=font_size,
                        dpi=dpi, seed=seed, ruled=ruled,
                        line_spacing_ratio=line_spacing_ratio,
                        word_spacing=word_spacing, formula=formula,
                        formula_font=formula_font, jitter=jitter, page=page,
                        max_pages=max_pages, progress=progress)


def main():
    ap = argparse.ArgumentParser(description="Markdown -> 手写体图片 (正文手写+公式二维)")
    ap.add_argument("input", nargs="?", help="输入的 .md 文件")
    ap.add_argument("-o", "--outdir", default=None, help="输出目录(默认 输入文件同级/手写体)")
    ap.add_argument("--font", default=None, help="风格名 / 字体文件名 / 绝对路径")
    ap.add_argument("--list-fonts", action="store_true", help="列出所有可用风格字体")
    ap.add_argument("--font-size", type=int, default=40)
    ap.add_argument("--dpi", type=int, default=150, help="A4 页面渲染 dpi")
    ap.add_argument("--seed", type=int, default=20231029, help="随机种子(保证可复现)")
    ap.add_argument("--no-ruled", action="store_true", help="不要横线本背景")
    ap.add_argument("--no-formula", action="store_true", help="公式不做二维渲染(退回文本)")
    ap.add_argument("--line-spacing", type=float, default=1.4,
                    help="行距倍数(越小越紧凑, 默认 1.4)")
    ap.add_argument("--word-spacing", type=float, default=0.0,
                    help="字距(像素, 默认 0)")
    ap.add_argument("--jitter", type=float, default=1.0,
                    help="笔迹随机度(0=每个字都一模一样, 1=默认, 可调大更有手写感)")
    ap.add_argument("--max-pages", type=int, default=0, help="最多输出几页(0=全部)")
    ap.add_argument("--page", type=int, default=0, help="只输出第几页(0=全部)")
    args = ap.parse_args()

    if args.list_fonts:
        list_fonts()
        return
    if not args.input:
        ap.error("需要提供输入的 .md 文件 (或用 --list-fonts 查看字体)")

    outdir = args.outdir or os.path.join(
        os.path.dirname(os.path.abspath(args.input)), "手写体")
    paths = convert_file(
        args.input, outdir, font=args.font, font_size=args.font_size,
        dpi=args.dpi, seed=args.seed, ruled=not args.no_ruled,
        formula=not args.no_formula,
        line_spacing_ratio=args.line_spacing, word_spacing=args.word_spacing,
        jitter=args.jitter, page=args.page, max_pages=args.max_pages)
    print(f"完成: 共 {len(paths)} 页, 输出到 {outdir}")


if __name__ == "__main__":
    main()
