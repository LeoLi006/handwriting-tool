# 手写体转换器（Markdown → 手写体图片）

把 `.md`（或 `.txt`）文档自动转写成**手写体风格**的 PNG 图片（A4、横线本背景、自动分页），
无需自己手抄。正文逐字手写，**数学公式二维排版**（真正的上下标 / 分式 / 根号 / 矩阵），
整体风格统一、与正文笔迹一致。文字排版基于开源库 [HandRight](https://github.com/Gsllchb/Handright)，
公式基于 [matplotlib mathtext](https://matplotlib.org/stable/tutorials/text/mathtext.html)。

完整操作步骤、示例与故障排查见 [使用说明书](使用说明书.md)，可直接试用 [示例文档](examples/示例.md)。

## 快速开始

安装 Python 3.9+，下载仓库并解压，保留 `fonts` 文件夹。在项目目录执行：

```bash
python -m pip install -r requirements.txt
python gui.py
```

Windows 也可双击 `启动GUI.bat`；首次启动可能联网安装依赖。将 UTF-8 编码的 `.md`、`.markdown` 或 `.txt` 文件拖入窗口，默认在源文件旁的 `手写体` 文件夹生成 PNG。

## 目录结构

```
手写体工具/
├── 启动GUI.bat          # 双击运行（Windows 一键启动）
├── gui.py               # 图形界面（拖拽文件即可转换）
├── handwriting.py       # 转换引擎（混合排版）+ 命令行工具
├── formula.py           # LaTeX → 二维公式贴图（mathtext + 手写字体）
├── requirements.txt     # 依赖清单
├── fonts/               # 字体 + 字体注册表
│   ├── fonts.json       # {风格名: 字体文件}
│   ├── LXGWWenKai-Regular.ttf   # 霞鹜文楷（符号最全，作为回退基准）
│   ├── MaShanZheng-Regular.ttf
│   ├── LongCang-Regular.ttf
│   ├── LiuJianMaoCao-Regular.ttf
│   ├── ZhiMangXing-Regular.ttf
│   ├── ZCOOLKuaiLe-Regular.ttf
│   └── _merged_*.ttf    # 自动生成的"嫁接回退符号"字体（可删，会重建）
└── README.md
```

## 一、图形界面（推荐）

1. 双击 **`启动GUI.bat`**（会自动检查并安装依赖）。
2. 在左侧选择 **字体 / 字号 / 行距 / 字距**，勾选是否要横线本背景。
3. 勾选 **「公式二维渲染」**，并选择 **公式字体**（默认霞鹜文楷，符号最全、公式最稳）。
4. 把 `.md` 文件**拖进右侧窗口**（可多选 / 可点击选择）；
   转换会自动开始，右侧显示第一页预览。
5. 输出默认在「源文件同级目录 / `手写体`」下，点「打开输出目录」查看。

- **行距**滑块：越大越稀疏，越小越紧凑（推荐 1.2 ~ 1.6）。
- **字距**滑块：像素值，负数更挤、正数更松。
- **位置/旋转随机度**：控制字的位置、倾斜、字号和字距抖动；0 保持整齐，默认 1。
- **字形变化强度**：独立控制同一个字内部的比例和笔画位置变化；0 关闭，默认 1，上限 1.8。
  想整齐又不重复，可设位置/旋转为 0～0.2、字形变化为 1～1.5。两个参数都为 0 时关闭全部随机变化。
  字形变化仍基于字体，不会生成新的笔顺或连笔写法；这两个参数只影响正文字符，公式沿用原有渲染。
- **公式二维渲染**：勾选后 `$...$`（行内）与 `$$...$$`（行间）公式都会排成真正的
  二维手写公式；取消勾选则退化为纯文本近似（仅用于排错对比）。

## 二、命令行

```bash
# 查看所有风格字体
python handwriting.py --list-fonts

# 基本用法（输出到 输入文件同级/手写体）
python handwriting.py ../../总结/第三章总结.md

# 指定字体 / 行距 / 字距 / 输出目录
python handwriting.py 输入.md --font MaShanZheng --line-spacing 1.2 --word-spacing 2 -o out

# 关闭公式二维渲染（退回文本）
python handwriting.py 输入.md --no-formula

# 只出第一页（快速看效果）
python handwriting.py 输入.md --max-pages 1
```

主要参数：

| 参数 | 说明 | 默认 |
|------|------|------|
| `--font` | 风格名（WenKai / MaShanZheng / LongCang / LiuJianMaoCao / ZhiMangXing / ZCOOLKuaiLe）或字体路径 | WenKai |
| `--font-size` | 字号（像素） | 40 |
| `--line-spacing` | 行距倍数（越小越紧凑） | 1.4 |
| `--word-spacing` | 字距（像素，可负） | 0 |
| `--jitter` | 位置/旋转、字号及字距抖动；0 保持整齐 | 1.0 |
| `--glyph-variation` | 独立字形变化强度；0 关闭，1.8 起达到上限 | 1.0 |
| `--dpi` | A4 渲染 dpi | 150 |
| `--no-ruled` | 不要横线本背景 | 关 |
| `--no-formula` | 关闭公式二维渲染（退回文本近似） | 关（即默认开启） |
| `--max-pages` / `--page` | 限定 / 只输出某页 | 0（全部） |

## 三、字体说明

- **霞鹜文楷（WenKai）**：工整清晰，且几乎包含全部数学符号，作为默认、公式字体与符号回退基准。
- 其余为 Google Fonts 中文手写体，风格各异（毛笔楷书 / 行书 / 草书 / 卡通），
  但**缺少数学符号**（`ℏ ∂ ∇ ∫ ∑ …`）。
- 引擎会自动检测缺字，并从霞鹜文楷中「**嫁接**」缺失字形生成 `_merged_*.ttf` 缓存，
  从而让所有风格字体都能正确显示符号。
- **公式字体**：公式用所选字体（默认霞鹜文楷）经 mathtext 渲染成二维图像；
  建议选符号齐全的字体，否则个别符号可能缺字。

## 四、转换能力

- Markdown 语法（标题、加粗、引用、列表、代码块等）→ 结构化的手写排版；
- **数学公式二维排版**（核心特性）：
  - 行内公式 `$...$` 与行间公式 `$$...$$` 均支持；
  - 真正的上下标、分式 `\frac/\dfrac`、根号 `\sqrt`、求和 `\sum`、积分 `\int`、
    帽标 `\hat/\bar/\vec/\tilde`、希腊字母、`≥ ≤ ≠ ⟺` 等；
  - 分段函数 `\begin{cases}`、多行对齐 `\begin{aligned}`、矩阵 `\begin{...matrix}` 等环境；
  - 归一化层会自动把 `\frac1{2}`→`\frac{1}{2}`、`\iff`→`⇔` 等补成 mathtext 可解析的形式；
- 自动分页，每页输出一张 A4 PNG。

## 五、依赖

```bash
pip install -r requirements.txt
```

> Python 3.9+；tkinter 随 Python 自带，Windows 上无需额外安装。
> matplotlib 为启动必需依赖；`--no-formula` 只关闭二维公式排版，不能代替安装 matplotlib。
