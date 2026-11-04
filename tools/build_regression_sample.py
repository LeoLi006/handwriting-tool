"""Create only original, deterministic Markdown fixtures and local PNG assets."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw


def build(root=None):
    root = Path(root or Path(__file__).resolve().parents[1]/'examples'/'regression')
    assets = root/'assets'; assets.mkdir(parents=True, exist_ok=True)
    for name, size in [('small', (240, 100)), ('wide', (1500, 180)), ('tall', (120, 1800))]:
        image = Image.new('RGB', size, '#edf5f2'); draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, size[0]-3, size[1]-3), outline='#29796b', width=3)
        draw.line((10, 10, size[0]-10, size[1]-10), fill='#29796b', width=3)
        draw.text((12, 20), name.upper(), fill='black')
        image.save(assets/(name+'.png'))
    text = r'''# 原创综合回归样本

固定种子 20231029，A4、150 DPI、40 像素字号。每项以 T 编号；E 项为故意错误。

## T01 基础 Markdown

预期：标题层级可辨；强调、删除线、引用与链接保留语义或明确报告替代；嵌套列表保持层级，任务状态不丢失。

### 三级标题

普通段落：**加粗重点**、*倾斜重点*、~~已撤销结论~~、`inline code`。

> 数据仅用于软件排版验证。

- 一级项目
  - 二级项目
    - 三级项目
- [x] 已完成实验
- [ ] 待复查实验

1. 步骤一
2. 步骤二：[示例链接](https://example.org)

---

## T02 数学表达

预期：公式二维排版，基线一致，不与正文或下一行重叠；嵌套方框完整。

行内 $a_i^2+\frac{b}{\sqrt{c}}$ 后面接正常中文，下一句仍然可读。

$$\sum_{k=1}^{n} k=\frac{n(n+1)}{2},\quad \int_0^1 x^2\,dx=\frac13,\quad \lim_{x\to0}\frac{\sin x}{x}=1$$

$$M=\begin{pmatrix}1&2\\3&4\end{pmatrix},\quad f(x)=\begin{cases}x^2,&x\ge0\\-x,&x<0\end{cases}$$

$$\begin{aligned}u&=\sqrt{1+t^2}\\v&=\boxed{\frac{1}{\boxed{1+t}}}\end{aligned}$$

## T03 混合表格

预期：中文英文、公式、转义竖线与空格保持；长单元格换行，边框不压字。

| 项目 | English / 公式 | 说明 |
|---|---|---|
| 中文 | $\frac{1}{1+x^2}$ | 长说明用于观察换行，自动换行不能丢掉最后几个字符：结束。 |
| pipe | a\|b | $|x|$ |
| 空单元格 | | |

## T04 字符图与混合线型

预期：横轴实线，辅助边界虚线；零点空心，极点叉号；交点各方向线型独立。

```polezero
       ↑ Im
   ○   │   ×
┄┄┄┄┄┄┄┼┄┄┄┄┄┄
       │
───────┼────────→ Re
       ┆
       ┆
```

```constellation
     ┆     ↑     ┆
  ×  ┆  ×  │  ×  ┆  ×
┄┄┄┄┄┼┄┄┄┄┄┼┄┄┄┄┄┼┄┄┄┄
─────┼─────┼─────┼────→ I
  ×  ┆  ×  │  ×  ┆  ×
```

## T05 本地图片

预期：解析相对路径，图片完整等比显示，图注紧跟图片；横图、竖图不能裁切。

![小图及其说明](assets/small.png)

![宽图及其说明](./assets/wide.png)

![高图及其说明](assets/tall.png)

## T06 长词与特殊字符

预期：超长英文可折行；特殊符号完整或明确报告缺字，不越过右页边。

ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789

符号：α β Ω ∞ ≈ ± ≤ ≥ → ← × ○ ℃ ℏ ①。

## T07 超宽公式

预期：整式等比缩放并报告缩放比例，不静默裁切；过小应提示拆分公式。

$$W=\frac{a_1+b_1}{c_1}+\frac{a_2+b_2}{c_2}+\frac{a_3+b_3}{c_3}+\frac{a_4+b_4}{c_4}+\frac{a_5+b_5}{c_5}+\frac{a_6+b_6}{c_6}+\frac{a_7+b_7}{c_7}+\frac{a_8+b_8}{c_8}+\frac{a_9+b_9}{c_9}+\frac{a_{10}+b_{10}}{c_{10}}$$

## T08 超宽表格

预期：列数过多时报告密度问题，保留全部内容；不能悄悄裁掉最后一列。

'''
    text += '|'+ '|'.join(f'列{i}' for i in range(1, 15))+'|\n'
    text += '|'+ '|'.join(['---']*14)+'|\n'
    text += '|'+ '|'.join(f'值{i}' for i in range(1, 15))+'|\n'
    text += '\n## T09 跨页长表格\n\n预期：80 行编号 001—080 各出现一次，跨页重复表头，不丢行。\n\n| 编号 | 测量值 | 备注 |\n|---|---|---|\n'
    text += '\n'.join(f'| {i:03d} | {i/10:.1f} | 原创记录，序号 {i:03d}。 |' for i in range(1,81))
    text += '\n\n## T10 超高字符图与分页\n\n预期：超高图等比缩放并提示；标题不孤立在页底。\n\n```diagram\n↑ y\n'+'│\n'*55+'└────→ x\n```\n'
    text += r'''
## T11 精确坐标描述

预期：采用安全 JSON，不执行代码；坐标轴实线，非零门限虚线，空心零点与极点位置准确。

```plot
{"xlim":[-4,4],"ylim":[-3,3],"axes":true,"points":[{"x":-2,"y":1,"kind":"zero","label":"z1"},{"x":2,"y":-1,"kind":"pole","label":"p1"},{"x":1,"y":1,"kind":"star"}],"lines":[{"from":[-2,-3],"to":[-2,3],"style":"dashed"},{"from":[-4,2],"to":[4,2],"style":"dashed"}],"labels":[{"x":0.2,"y":2.7,"text":"Q"},{"x":3.6,"y":-0.3,"text":"I"}]}
```

## E01 故意错误：公式

预期：错误定位到本章节和公式行；保留原文替代，不能画成正确答案。

$$\unsupportedcommand{x}$$

## E02 故意错误：缺失图片

预期：显示缺失文件的具体路径、行号与替代文字。

![故意缺失的图片](assets/DOES-NOT-EXIST.png)

## E03 故意不支持：HTML

预期：报告不支持 HTML 布局，保留源文字；不执行 HTML。

<div style="color:red">故意不支持的 HTML 样例</div>

## E04 故意错误：坐标图配置

预期：不执行对象中的代码；报告非法配置而不是生成错误图。

```plot
{"xlim":[0,0],"run":"print('NEVER EXECUTE')"}
```
'''
    (root/'综合回归.md').write_text(text, encoding='utf-8')
    return root/'综合回归.md'


if __name__ == '__main__':
    print(build())
